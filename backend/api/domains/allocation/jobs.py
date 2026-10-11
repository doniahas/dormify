"""
Durable allocation jobs: the AllocationRun row as the job record, the
database-safe claim, the worker lease, claim fencing and the recovery of
runs whose worker is gone.

The HTTP request that starts a background allocation only creates a
QUEUED AllocationRun carrying its solver parameters (``job_parameters``).
A dedicated worker process (``manage.py allocation_worker``, see
worker.py) claims such runs with ``SELECT ... FOR UPDATE SKIP LOCKED``,
holds a lease on the claimed row that a heartbeat thread renews while the
run executes, and executes the run through
``orchestration.execute_allocation_run`` - the R7 engine boundary. The
database is the only lifecycle state: nothing in memory is needed to know
that a run exists, who is executing it or whether its worker is still
alive.

Claim generation and fencing. A claim writes ``claimed_by`` (the worker)
and increments ``attempts``; that pair is the claim generation the
execution owns (``fencing.ClaimFence``). Every transfer of ownership
changes the pair - a re-queue clears ``claimed_by``, the next claim
increments ``attempts``, a recovery takeover writes the recovering worker
into ``claimed_by`` - and every write of a fenced execution is conditional
on its own pair still being the row's: the RUNNING transition, the
pre-solver check, the solver's persistence transaction (through its
``persistence_guard``, with the row locked), the solver's own run-row
writes - search-start stamp and live-snapshot mirror - and its stop
watcher (through its ``run_ownership_filter``; a watcher that finds the
row no longer owned stops the search), the diagnostics write, the
cleanup of a cancelled run and the final state. A write that matches no
row raises ``ClaimLost`` and the stale execution stops; it never persists
assignments or overwrites a newer claim or a recovery outcome. A heartbeat
renewal that matches no row marks the fence lost immediately and asks the
in-process solver to stop searching.

Execution guarantee (not exactly-once): one current claim generation owns
a run; stale generations cannot persist or finalize; the lifecycle is
durable; a run whose lease expired belongs to a lost worker and is
recovered by any live worker according to the crash window it was found
in (``recover_stale_runs``):

- lease expired, solver not started (``search_started_at`` is NULL):
  nothing was written on behalf of the run, so it is re-queued and
  claimed again, up to ``max_attempts`` claims, then FAILED;
- lease expired, solver started, no BedAssignment row tagged with the run:
  the solver's persistence transaction never committed; the run is marked
  FAILED with an explicit message (re-solving would be data-safe but is
  never done implicitly - a solve is never restarted behind the
  operator's back);
- lease expired, BedAssignment rows tagged with the run exist: the solver
  committed a result but the worker was lost before finalizing the run
  row. The counters and diagnostics of that result are gone with the
  worker, so the run is marked FAILED and the tagged assignments are
  cancelled (students restored), exactly as a cancellation does, leaving
  no half-finalized state behind;
- a pending CANCELLATION_REQUESTED is honoured (cleanup, STOPPED) and a
  pending STOP_AND_SAVE_REQUESTED without persisted rows ends STOPPED with
  the no-solution document - the same outcomes the run body itself
  produces for those requests.

Every recovery action takes ownership of the row (``claimed_by`` becomes
the recovering worker, or '' for a re-queue), which is what fences the
lost worker out should it come back. Runs created before the durable
worker (``job_parameters`` NULL) and runs of the synchronous / retry
endpoints are never claimed or recovered here.
"""

import logging
import os
import socket
import threading
import uuid
from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.db import close_old_connections, connection, transaction
from django.db.models import F
from django.utils import timezone

from ...models import AllocationRun, BedAssignment
from .config import normalize_allocation_constraints
from .fencing import ClaimFence, ClaimLost
from .orchestration import _cleanup_run_assignments, execute_allocation_run
from .persistence import stopped_without_solution_diagnostics

logger = logging.getLogger('dormify.allocation.worker')

# Statuses a worker may claim: a queued run, or a run an operator asked to
# stop before any worker picked it up (finalized without a solve).
CLAIMABLE_STATUSES = (
    AllocationRun.Status.QUEUED,
    AllocationRun.Status.CANCELLATION_REQUESTED,
    AllocationRun.Status.STOP_AND_SAVE_REQUESTED,
)

# Statuses in which a run can hold a lease; a run in any other status is
# finished and never recovered.
IN_PROGRESS_STATUSES = (
    AllocationRun.Status.QUEUED,
    AllocationRun.Status.RUNNING,
    AllocationRun.Status.CANCELLATION_REQUESTED,
    AllocationRun.Status.STOP_AND_SAVE_REQUESTED,
)

DEFAULT_POLL_INTERVAL_SECONDS = 2.0
DEFAULT_LEASE_SECONDS = 300
DEFAULT_HEARTBEAT_SECONDS = 30.0
DEFAULT_MAX_ATTEMPTS = 3

LOST_BEFORE_SOLVE_MESSAGE = (
    'The allocation worker was lost before the solver started and the run '
    'exhausted its {attempts} claim attempt(s); nothing was persisted. Start a new run.'
)
LOST_DURING_SOLVE_MESSAGE = (
    'The allocation worker was lost while the solver was running; no '
    'assignments were persisted for this run. Start a new run.'
)
LOST_AFTER_PERSISTENCE_MESSAGE = (
    'The allocation worker was lost after the solver persisted {count} '
    'assignment(s) for this run but before the run was finalized; those '
    'assignments were cancelled and the students restored. Start a new run.'
)


def _log(event, **fields):
    details = ' '.join(f'{key}={value}' for key, value in fields.items())
    logger.info('event=%s %s', event, details)


@dataclass(frozen=True)
class WorkerSettings:
    """Tunables of one worker process; defaults come from Django settings."""

    poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS
    lease_seconds: int = DEFAULT_LEASE_SECONDS
    heartbeat_seconds: float = DEFAULT_HEARTBEAT_SECONDS
    max_attempts: int = DEFAULT_MAX_ATTEMPTS

    @classmethod
    def from_settings(cls, **overrides):
        values = {
            'poll_interval_seconds': float(getattr(
                settings, 'ALLOCATION_WORKER_POLL_INTERVAL_SECONDS', DEFAULT_POLL_INTERVAL_SECONDS,
            )),
            'lease_seconds': int(getattr(
                settings, 'ALLOCATION_WORKER_LEASE_SECONDS', DEFAULT_LEASE_SECONDS,
            )),
            'heartbeat_seconds': float(getattr(
                settings, 'ALLOCATION_WORKER_HEARTBEAT_SECONDS', DEFAULT_HEARTBEAT_SECONDS,
            )),
            'max_attempts': int(getattr(
                settings, 'ALLOCATION_WORKER_MAX_ATTEMPTS', DEFAULT_MAX_ATTEMPTS,
            )),
        }
        values.update({key: value for key, value in overrides.items() if value is not None})
        worker_settings = cls(**values)
        worker_settings.validate()
        return worker_settings

    def validate(self):
        if self.poll_interval_seconds <= 0:
            raise ValueError('poll interval must be positive')
        if self.lease_seconds <= 0:
            raise ValueError('lease seconds must be positive')
        if self.heartbeat_seconds < 0:
            raise ValueError('heartbeat seconds cannot be negative')
        if self.heartbeat_seconds >= self.lease_seconds:
            raise ValueError('heartbeat interval must be shorter than the lease')
        if self.max_attempts < 1:
            raise ValueError('max attempts must be at least 1')


def build_worker_id():
    """A worker identity unique across hosts, processes and restarts."""
    return f'{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:8]}'


# ---------------------------------------------------------------------------
# Job parameters: what the request stores and the worker reads back
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class JobParameters:
    constraints_config: dict
    include_assigned: bool
    allocation_scope: object
    max_seconds: object


def pack_job_parameters(*, constraints_config, include_assigned, allocation_scope, max_seconds):
    """The ``AllocationRun.job_parameters`` document of a queued run."""
    return {
        'constraints_config': constraints_config,
        'include_assigned': bool(include_assigned),
        'allocation_scope': allocation_scope,
        'max_seconds': max_seconds,
    }


def unpack_job_parameters(job_parameters):
    """Read a stored ``job_parameters`` document; None means a legacy run."""
    if not isinstance(job_parameters, dict):
        raise ValueError('the run carries no durable job parameters')
    constraints_config = job_parameters.get('constraints_config')
    if not isinstance(constraints_config, dict):
        constraints_config = normalize_allocation_constraints(None)
    return JobParameters(
        constraints_config=constraints_config,
        include_assigned=bool(job_parameters.get('include_assigned', False)),
        allocation_scope=job_parameters.get('allocation_scope'),
        max_seconds=job_parameters.get('max_seconds'),
    )


# ---------------------------------------------------------------------------
# Claiming and leases
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ClaimedRun:
    run_id: int
    region_id: str
    status: str
    attempt: int  # the claim generation this execution owns
    lease_expires_at: object
    parameters: JobParameters

    def fence(self, worker_id):
        return ClaimFence(run_id=self.run_id, worker_id=worker_id, generation=self.attempt)


def claim_next_run(worker_id, *, lease_seconds, now=None):
    """
    Atomically claim the oldest claimable run for ``worker_id`` and return
    it, or None when nothing is waiting.

    ``SELECT ... FOR UPDATE SKIP LOCKED`` on the candidate row means two
    workers claiming at the same moment lock different rows (or one of
    them finds nothing), and the ``claimed_by = ''`` filter re-evaluated
    under that lock means a row another worker just committed a claim on
    is never claimed twice. The claim increments ``attempts``: the new
    value is the claim generation the execution owns. Legacy runs
    (``job_parameters`` NULL) are not candidates.
    """
    now = now or timezone.now()
    lease_until = now + timedelta(seconds=lease_seconds)
    with transaction.atomic():
        run = (
            AllocationRun.objects.select_for_update(skip_locked=True)
            .filter(
                status__in=CLAIMABLE_STATUSES,
                claimed_by='',
                job_parameters__isnull=False,
            )
            .order_by('started_at', 'pk')
            .first()
        )
        if run is None:
            return None
        AllocationRun.objects.filter(pk=run.pk).update(
            claimed_by=worker_id,
            lease_expires_at=lease_until,
            attempts=F('attempts') + 1,
        )
        attempt = run.attempts + 1
    return ClaimedRun(
        run_id=run.pk,
        region_id=run.region_id,
        status=run.status,
        attempt=attempt,
        lease_expires_at=lease_until,
        parameters=unpack_job_parameters(run.job_parameters),
    )


def renew_lease(run_id, worker_id, generation, *, lease_seconds, now=None):
    """
    Extend the lease of a run this worker holds under ``generation`` and is
    still executing. Returns False when that claim generation is no longer
    the row's (the run was recovered or re-claimed) or the run finished.
    """
    now = now or timezone.now()
    updated = AllocationRun.objects.filter(
        pk=run_id,
        claimed_by=worker_id,
        attempts=generation,
        status__in=IN_PROGRESS_STATUSES,
    ).update(lease_expires_at=now + timedelta(seconds=lease_seconds))
    return updated == 1


def release_lease(run_id, worker_id, generation):
    """Drop the lease once the run finished; ``claimed_by`` stays as a record of who ran it."""
    return AllocationRun.objects.filter(
        pk=run_id, claimed_by=worker_id, attempts=generation,
    ).update(lease_expires_at=None) == 1


class LeaseHeartbeat:
    """
    Renews the lease of one claimed run from its own daemon thread (and
    its own database connection) while the run body executes - the run
    body may spend its whole time inside the solver, so no other point of
    the worker could do it.

    A renewal that matches no row means the claim generation is no longer
    the row's: the fence is marked lost at once (every later fenced
    operation of the execution is refused without touching the database)
    and the in-process solver, if one is registered for the run, is asked
    to stop searching so the doomed execution ends quickly.
    """

    def __init__(self, fence, *, interval_seconds, lease_seconds):
        self.fence = fence
        self.interval_seconds = interval_seconds
        self.lease_seconds = lease_seconds
        self.renewals = 0
        self._stop = threading.Event()
        self._thread = threading.Thread(
            target=self._run, name=f'allocation-lease-{fence.run_id}', daemon=True,
        )

    @property
    def lost(self):
        return self.fence.lost

    def start(self):
        self._thread.start()

    def stop(self, timeout=None):
        self._stop.set()
        self._thread.join(timeout if timeout is not None else self.interval_seconds + 5.0)

    def is_alive(self):
        return self._thread.is_alive()

    def renew_once(self):
        """
        One renewal attempt. Returns True when renewed, False when the
        lease is no longer this execution's (the fence is then marked lost
        and the in-process solver asked to stop); raises on a database
        error, which the loop treats as transient.
        """
        if self.fence.lost:
            return False
        renewed = renew_lease(
            self.fence.run_id, self.fence.worker_id, self.fence.generation,
            lease_seconds=self.lease_seconds,
        )
        if renewed:
            self.renewals += 1
            return True
        self.fence.mark_lost()
        logger.warning(
            'event=lease_lost run_id=%s worker=%s generation=%s',
            self.fence.run_id, self.fence.worker_id, self.fence.generation,
        )
        try:
            from .gateway import live_registry

            live_registry.request_stop_search(self.fence.run_id)
        except Exception:
            pass
        return False

    def _run(self):
        try:
            while not self._stop.wait(self.interval_seconds):
                try:
                    close_old_connections()
                    self.renew_once()
                except Exception as exc:
                    logger.warning(
                        'event=heartbeat_error run_id=%s worker=%s error=%s',
                        self.fence.run_id, self.fence.worker_id, type(exc).__name__,
                    )
        finally:
            try:
                connection.close()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Executing a claimed run
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class JobOutcome:
    run_id: int
    status: str
    error_message: str
    stopped_early_by_user: bool
    lease_lost: bool
    fenced: bool = False  # the execution was refused because its claim generation was no longer current


def execute_claimed_run(claimed, worker_id, *, worker_settings, heartbeat=None, fence=None):
    """
    Execute a claimed run through the allocation-engine boundary
    (orchestration.execute_allocation_run) under its claim fence while a
    heartbeat renews its lease, then drop the lease and report the final
    state. The run body itself records COMPLETED / FAILED / STOPPED on the
    row; a fenced execution that lost its claim stops with ``fenced=True``
    and writes nothing further; an exception escaping the run body (for
    example the database being unreachable) propagates with the lease
    intact, so the run is recovered once the lease expires.
    """
    parameters = claimed.parameters
    if fence is None:
        fence = claimed.fence(worker_id)
    if heartbeat is None and worker_settings.heartbeat_seconds > 0:
        heartbeat = LeaseHeartbeat(
            fence,
            interval_seconds=worker_settings.heartbeat_seconds,
            lease_seconds=worker_settings.lease_seconds,
        )
    _log(
        'executing', run_id=claimed.run_id, region=claimed.region_id,
        attempt=claimed.attempt, status=claimed.status, worker=worker_id,
        max_seconds=parameters.max_seconds, include_assigned=parameters.include_assigned,
        scope=parameters.allocation_scope,
    )
    if heartbeat is not None:
        heartbeat.start()
    fenced = False
    try:
        execute_allocation_run(
            allocation_run_id=claimed.run_id,
            region_id=claimed.region_id,
            constraints_config=parameters.constraints_config,
            include_assigned=parameters.include_assigned,
            allocation_scope=parameters.allocation_scope,
            max_seconds=parameters.max_seconds,
            fence=fence,
        )
    except ClaimLost as lost:
        fenced = True
        logger.warning(
            'event=fenced run_id=%s region=%s attempt=%s worker=%s detail=%s',
            claimed.run_id, claimed.region_id, claimed.attempt, worker_id, lost,
        )
    finally:
        if heartbeat is not None:
            heartbeat.stop()

    close_old_connections()
    if not fenced:
        release_lease(claimed.run_id, worker_id, claimed.attempt)
    row = AllocationRun.objects.filter(pk=claimed.run_id).values(
        'status', 'error_message', 'diagnostics', 'claimed_by', 'attempts',
    ).first() or {}
    diagnostics = row.get('diagnostics') or {}
    outcome = JobOutcome(
        run_id=claimed.run_id,
        status=row.get('status', ''),
        error_message=row.get('error_message', '') or '',
        stopped_early_by_user=bool(diagnostics.get('stopped_early_by_user', False)),
        lease_lost=fence.lost,
        fenced=fenced,
    )
    _log(
        'finished', run_id=outcome.run_id, region=claimed.region_id, status=outcome.status,
        stopped_early_by_user=outcome.stopped_early_by_user,
        stop_reason=diagnostics.get('stop_reason', ''),
        error=outcome.error_message[:200].replace('\n', ' '), lease_lost=outcome.lease_lost,
        fenced=fenced, current_owner=row.get('claimed_by', ''), current_generation=row.get('attempts'),
        worker=worker_id,
    )
    return outcome


# ---------------------------------------------------------------------------
# Recovery of runs whose worker is gone
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RecoveryAction:
    run_id: int
    previous_status: str
    action: str  # 'requeued' | 'failed' | 'stopped' | 'cancelled'
    detail: str
    lost_worker: str = ''


def stale_run_ids(now=None):
    """Runs in progress whose lease has expired: their worker is gone."""
    now = now or timezone.now()
    return list(
        AllocationRun.objects.filter(
            status__in=IN_PROGRESS_STATUSES,
            claimed_by__gt='',
            lease_expires_at__lt=now,
        ).order_by('pk').values_list('pk', flat=True)
    )


def recover_stale_runs(worker_id, *, worker_settings, now=None):
    """
    Apply the recovery policy (module docstring) to every run whose lease
    has expired. Each run is handled under its own row lock, so several
    workers may run this concurrently; a run another worker already
    handled, or whose lease was renewed meanwhile, is skipped. Every action
    transfers ownership of the row away from the lost worker.
    """
    now = now or timezone.now()
    actions = []
    for run_id in stale_run_ids(now):
        action = _recover_run(run_id, worker_id, worker_settings=worker_settings, now=now)
        if action is not None:
            actions.append(action)
            _log(
                'recovered', run_id=action.run_id, previous_status=action.previous_status,
                action=action.action, lost_worker=action.lost_worker, detail=action.detail,
                worker=worker_id,
            )
    return actions


def _recover_run(run_id, worker_id, *, worker_settings, now):
    cleanup = None
    with transaction.atomic():
        run = (
            AllocationRun.objects.select_for_update(skip_locked=True)
            .filter(
                pk=run_id,
                status__in=IN_PROGRESS_STATUSES,
                claimed_by__gt='',
                lease_expires_at__lt=now,
            )
            .first()
        )
        if run is None:
            return None

        previous_status = run.status
        lost_worker = run.claimed_by
        persisted = BedAssignment.objects.filter(allocation_run_id=run_id).count()
        solver_started = run.search_started_at is not None
        run_row = AllocationRun.objects.filter(pk=run_id)
        lease_until = now + timedelta(seconds=worker_settings.lease_seconds)

        if previous_status == AllocationRun.Status.CANCELLATION_REQUESTED:
            # Honour the pending cancellation exactly as the run body does
            # after a solve: cancel whatever the run persisted, restore the
            # students and mark it STOPPED. The cleanup opens its own
            # transaction, so this worker takes the run over (owner, lease,
            # outcome message) under the lock first and acts after the lock
            # is released; the terminal status is written last, so a crash
            # in between leaves an owned, leased, in-progress run that the
            # next recovery handles the same way.
            run_row.update(
                claimed_by=worker_id, lease_expires_at=lease_until,
                error_message='', live_snapshot=None,
            )
            cleanup = AllocationRun.Status.STOPPED
            action = RecoveryAction(
                run_id, previous_status, 'cancelled',
                f'pending cancellation honoured; {persisted} persisted assignment(s) cancelled',
                lost_worker,
            )
        elif previous_status == AllocationRun.Status.STOP_AND_SAVE_REQUESTED and persisted == 0:
            run_row.update(
                status=AllocationRun.Status.STOPPED,
                completed_at=now,
                live_snapshot=None,
                diagnostics=stopped_without_solution_diagnostics(),
                claimed_by=worker_id,
                lease_expires_at=None,
            )
            action = RecoveryAction(
                run_id, previous_status, 'stopped',
                'pending stop-and-save with no persisted solution',
                lost_worker,
            )
        elif persisted > 0:
            run_row.update(
                claimed_by=worker_id, lease_expires_at=lease_until,
                error_message=LOST_AFTER_PERSISTENCE_MESSAGE.format(count=persisted),
                live_snapshot=None,
            )
            cleanup = AllocationRun.Status.FAILED
            action = RecoveryAction(
                run_id, previous_status, 'failed',
                f'worker lost after persistence; {persisted} assignment(s) cancelled',
                lost_worker,
            )
        elif not solver_started:
            if run.attempts < worker_settings.max_attempts:
                run_row.update(
                    status=AllocationRun.Status.QUEUED,
                    claimed_by='',
                    lease_expires_at=None,
                )
                action = RecoveryAction(
                    run_id, previous_status, 'requeued',
                    f'worker lost before the solver started; attempt {run.attempts} of '
                    f'{worker_settings.max_attempts}',
                    lost_worker,
                )
            else:
                run_row.update(
                    status=AllocationRun.Status.FAILED,
                    error_message=LOST_BEFORE_SOLVE_MESSAGE.format(attempts=run.attempts),
                    completed_at=now,
                    live_snapshot=None,
                    claimed_by=worker_id,
                    lease_expires_at=None,
                )
                action = RecoveryAction(
                    run_id, previous_status, 'failed',
                    f'worker lost before the solver started; {run.attempts} attempt(s) exhausted',
                    lost_worker,
                )
        else:
            run_row.update(
                status=AllocationRun.Status.FAILED,
                error_message=LOST_DURING_SOLVE_MESSAGE,
                completed_at=now,
                live_snapshot=None,
                claimed_by=worker_id,
                lease_expires_at=None,
            )
            action = RecoveryAction(
                run_id, previous_status, 'failed',
                'worker lost during the solve; nothing persisted',
                lost_worker,
            )

    if cleanup is not None:
        _cleanup_run_assignments(run_id, mark_status=cleanup)
        AllocationRun.objects.filter(pk=run_id, claimed_by=worker_id).update(lease_expires_at=None)
    return action
