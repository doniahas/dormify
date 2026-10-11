"""
The allocation worker loop: recover runs whose worker is gone, claim the
next queued run, execute it, repeat. ``manage.py allocation_worker`` is
the process entry point; this module holds the loop so it can be driven
one cycle at a time in tests.

A worker never depends on the web replica that accepted a request or on
another worker's memory: every decision is made from the AllocationRun
rows (jobs.py). Several worker processes may run against the same
database; claiming is row-locked so each queued run is executed by one of
them.
"""

import logging
import threading
from dataclasses import dataclass, field

from django.db import close_old_connections

from .jobs import (
    WorkerSettings,
    build_worker_id,
    claim_next_run,
    execute_claimed_run,
    recover_stale_runs,
)

logger = logging.getLogger('dormify.allocation.worker')


@dataclass
class WorkerCycle:
    """What one pass of the loop did."""

    recovered: list = field(default_factory=list)
    claimed: object = None
    outcome: object = None
    error: str = ''

    @property
    def idle(self):
        return self.claimed is None and not self.recovered and not self.error


class AllocationWorker:
    def __init__(self, *, worker_id=None, worker_settings=None, stop_event=None):
        self.worker_id = worker_id or build_worker_id()
        self.settings = worker_settings or WorkerSettings.from_settings()
        self.stop_event = stop_event or threading.Event()

    def request_stop(self):
        """Finish the run in progress (if any), then leave the loop."""
        self.stop_event.set()

    def run_once(self):
        """
        One pass: recover stale runs, then claim and execute at most one
        run. A failure in either step is logged and reported in the
        returned cycle; it never propagates, so the loop survives per-job
        and transient database errors. An exception escaping the run body
        leaves the run's lease in place, and the run is recovered once
        that lease expires.
        """
        cycle = WorkerCycle()
        close_old_connections()
        try:
            cycle.recovered = recover_stale_runs(
                self.worker_id, worker_settings=self.settings,
            )
        except Exception as exc:
            cycle.error = f'recovery: {type(exc).__name__}: {exc}'
            logger.exception('event=recovery_error worker=%s', self.worker_id)
        try:
            cycle.claimed = claim_next_run(
                self.worker_id, lease_seconds=self.settings.lease_seconds,
            )
            if cycle.claimed is not None:
                logger.info(
                    'event=claimed run_id=%s region=%s status=%s attempt=%s lease_until=%s worker=%s',
                    cycle.claimed.run_id, cycle.claimed.region_id, cycle.claimed.status,
                    cycle.claimed.attempt, cycle.claimed.lease_expires_at.isoformat(),
                    self.worker_id,
                )
                cycle.outcome = execute_claimed_run(
                    cycle.claimed, self.worker_id, worker_settings=self.settings,
                )
        except Exception as exc:
            cycle.error = f'job: {type(exc).__name__}: {exc}'
            logger.exception(
                'event=job_error run_id=%s worker=%s',
                getattr(cycle.claimed, 'run_id', None), self.worker_id,
            )
        finally:
            close_old_connections()
        return cycle

    def run_forever(self):
        """Loop until ``request_stop`` is called; waits ``poll_interval_seconds`` when idle or after an error."""
        logger.info(
            'event=started worker=%s poll_interval=%s lease_seconds=%s heartbeat_seconds=%s max_attempts=%s',
            self.worker_id, self.settings.poll_interval_seconds, self.settings.lease_seconds,
            self.settings.heartbeat_seconds, self.settings.max_attempts,
        )
        cycles = 0
        try:
            while not self.stop_event.is_set():
                cycle = self.run_once()
                cycles += 1
                if cycle.claimed is None or cycle.error:
                    self.stop_event.wait(self.settings.poll_interval_seconds)
        finally:
            logger.info('event=stopped worker=%s cycles=%s', self.worker_id, cycles)
        return cycles
