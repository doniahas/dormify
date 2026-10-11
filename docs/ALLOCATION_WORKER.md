# The allocation worker

`python manage.py allocation_worker` executes background allocation runs. This document explains what it owns, how runs move through their lifecycle, and what happens when a worker is lost. Code: `backend/api/domains/allocation/jobs.py` (claiming, leases, recovery), `fencing.py` (claim fence), `worker.py` (loop), `orchestration.py` (the run body), `backend/api/management/commands/allocation_worker.py` (entry point).

## Why a separate process

Before this design, `POST /api/allocation/start/` started a daemon thread inside the web process. A run then depended on that process staying alive: a restart left the run RUNNING forever, other web replicas could not see the solver, and nothing re-ran lost work. The worker makes execution independent of the request and of any single process, with PostgreSQL as the only shared state. No message broker is involved.

## The job record

`AllocationRun` is the job. Besides the lifecycle columns the UI already polls, it carries:

| Column | Meaning |
|---|---|
| `job_parameters` | the solver parameters the start request stored (`constraints_config`, `include_assigned`, `allocation_scope`, `max_seconds`). `NULL` marks a run created by the synchronous or retry endpoints (which solve inside the request) or before this design; the worker never claims those. |
| `claimed_by` | identity of the worker that owns the run (`host:pid:random`); `''` while unclaimed |
| `lease_expires_at` | the lease the owner holds; renewed by its heartbeat; `NULL` when no lease is held |
| `attempts` | number of claims; the claim generation (see fencing) and the bound on re-queues |

## Lifecycle

```
QUEUED (job_parameters set)                      <- start request
  | claim: claimed_by = worker, lease, attempts + 1
RUNNING                                          <- first write of the run body
  | solver (stamps search_started_at, mirrors live_snapshot, watches for stop requests)
COMPLETED | FAILED | STOPPED
  | lease dropped (claimed_by kept as the record of who ran it)
```

Operators may request `CANCELLATION_REQUESTED` or `STOP_AND_SAVE_REQUESTED` at any time. During a solve the solver's own watcher polls the database status and interrupts the search; the run body then discards the result (cancel) or keeps the best feasible solution (`stopped_early_by_user`). A request that arrives while the run is still queued is finalized by the worker without a solve: cancellation ends STOPPED, and Stop & Save ends STOPPED with the "no feasible solution before stop" document, because nothing exists yet to save.

## Claiming

One transaction per claim:

```sql
SELECT ... FROM api_allocationrun
 WHERE status IN ('queued','cancellation_requested','stop_and_save_requested')
   AND claimed_by = '' AND job_parameters IS NOT NULL
 ORDER BY started_at, id LIMIT 1 FOR UPDATE SKIP LOCKED;
UPDATE api_allocationrun SET claimed_by = %s, lease_expires_at = %s, attempts = attempts + 1 WHERE id = %s;
```

Concurrent workers skip each other's locked rows and the `claimed_by = ''` predicate is re-evaluated under the lock, so a run is claimed exactly once per generation. Region duplicate protection is separate and unchanged: creating a run takes a row lock on the region and refuses while a queued, claimed, running or stop-requested run exists.

## Leases and heartbeat

A claim grants a lease (`ALLOCATION_WORKER_LEASE_SECONDS`, default 300). While the run body executes, a heartbeat thread renews it every `ALLOCATION_WORKER_HEARTBEAT_SECONDS` (default 30) with an update conditional on the run id, owner and generation. A renewal that updates no row means ownership moved elsewhere: the heartbeat marks the execution's fence as lost and asks the in-process solver to stop searching. A database error during renewal is treated as transient and retried.

## Recovery of lost workers

A run in an in-progress status whose lease has expired belongs to a worker that is gone. Every worker runs recovery at the start of each cycle, each run under its own row lock. The policy depends on what the lost worker had done:

| Situation found | Action |
|---|---|
| solver had not started (`search_started_at` is NULL) | re-queue, while `attempts < ALLOCATION_WORKER_MAX_ATTEMPTS` (default 3); then FAILED |
| solver started, no assignment tagged with the run | FAILED with an explicit message; never re-solved automatically |
| assignments tagged with the run exist but the run was not finalized | FAILED, and those assignments are cancelled with the students restored (the counters of that result died with the worker) |
| cancellation pending | cleanup, STOPPED |
| stop-and-save pending without persisted rows | STOPPED with the no-solution document |

Every recovery action transfers ownership of the row (to the recovering worker, or to nobody for a re-queue).

## Fencing: what a stale worker cannot do

A worker that lost its lease (for example after losing database connectivity for longer than the lease) may come back. Its execution owns one claim generation, the pair `(claimed_by, attempts)` written by its claim, and every write it performs is conditional on that pair still being the row's: the RUNNING transition, the check before calling the solver, the solver's persistence transaction (through a `persistence_guard` invoked first inside that transaction with the run row locked), the solver's own search-start stamp and live-snapshot mirror, the diagnostics and final-state writes, the cancellation cleanup and the lease release. A write that matches no row raises `ClaimLost`, the execution stops, and once the fence has observed the loss it refuses every later operation without touching the database. The solver's stop watcher also interrupts a search whose run no longer belongs to its generation.

The guarantee is therefore: one current claim generation owns a run's writes; stale generations cannot persist assignments or finalize anything; recovery is durable and transfers ownership; automatic re-execution happens only when provably nothing was written. It is not exactly-once execution: a run lost mid-solve is failed and restarted by the operator.

## Running it

```bash
python manage.py allocation_worker                # loop until SIGTERM / Ctrl+C
python manage.py allocation_worker --once         # one cycle: recovery, at most one run, exit
python manage.py allocation_worker --poll-interval 5 --lease-seconds 600 --heartbeat-seconds 60 --max-attempts 2 --worker-id my-worker --log-level DEBUG
docker compose -p dormify-v3 up --scale allocation_worker=2
```

On SIGTERM or SIGINT the worker logs `stop_requested`, lets the run in progress finish, logs `stopped` and exits 0. The Compose service sets `stop_grace_period: 30s`; a solve longer than that is killed with the container and recovered by the next worker once the lease expires, so drain workers before stopping them in production.

## Logging

The worker logs through the `dormify.allocation.worker` logger as `key=value` lines: `started`, `claimed`, `executing`, `finished` (status, stop reason, truncated error, whether the lease was lost or the execution fenced), `recovered` (previous status, action, lost worker), `lease_lost`, `heartbeat_error`, `fenced`, `job_error`, `recovery_error`, `stop_requested`, `stopped`. Lines carry run, region and worker identifiers, never student data. The run body also prints the pre-existing `ASYNC_ALLOCATION_DONE` diagnostic.

## Deployment order

1. Apply migration `0020_allocationrun_durable_job_fields`. It is additive and keeps database defaults on its NOT NULL columns, so web code that predates it keeps creating runs (with `job_parameters` NULL, which workers ignore).
2. Start the worker(s).
3. Roll out the web code that enqueues instead of starting threads.

Rollback: stop the workers, roll back the web code, `python manage.py migrate api 0019`.
