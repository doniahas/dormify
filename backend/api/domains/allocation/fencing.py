"""
Claim fencing for durable allocation jobs.

A worker executes a run under one claim generation: the (``claimed_by``,
``attempts``) pair the claim wrote on the AllocationRun row. Every transfer
of ownership changes that pair - a re-queue clears ``claimed_by``, a new
claim increments ``attempts``, a recovery takeover writes the recovering
worker into ``claimed_by`` - so an execution can always tell whether it is
still the current owner by matching its own pair against the row.

``ClaimFence`` makes every write of a fenced execution conditional on that
match (``UPDATE ... WHERE id=%s AND claimed_by=%s AND attempts=%s``) and
fails closed: a write that matches no row means ownership was lost, and the
execution stops instead of continuing. The same check, with the row locked,
is handed to the solver as its ``persistence_guard`` so a stale execution
cannot persist assignments either, and the generation's row lookups are
handed to it as ``run_ownership_filter`` so its own run-row writes (the
search-start stamp, the live-snapshot mirror) cannot touch a row another
generation owns. Once the fence has observed the loss
(or the heartbeat reported it), it refuses every later operation without
touching the database.
"""

import threading
from dataclasses import dataclass, field

from ...models import AllocationRun


class ClaimLost(RuntimeError):
    """The execution no longer owns the run's current claim generation."""


@dataclass(eq=False)
class ClaimFence:
    run_id: int
    worker_id: str
    generation: int
    _lost: threading.Event = field(default_factory=threading.Event, repr=False)

    @property
    def lost(self):
        return self._lost.is_set()

    def mark_lost(self):
        """Record that ownership is gone (heartbeat renewal matched no row)."""
        self._lost.set()

    def ownership_filter(self):
        """
        The row lookups that identify this claim generation. Handed to the
        solver (``run_ownership_filter``) so its own run-row writes - the
        search-start stamp and the live-snapshot mirror - and its stop
        watcher only ever act on the row while this generation owns it.
        """
        return {'claimed_by': self.worker_id, 'attempts': self.generation}

    def owned_rows(self):
        """The run row, only while this fence's claim generation is current."""
        return AllocationRun.objects.filter(pk=self.run_id, **self.ownership_filter())

    def _refuse(self, reason):
        self._lost.set()
        raise ClaimLost(
            f'run {self.run_id}: claim generation {self.generation} of worker '
            f'{self.worker_id} {reason}'
        )

    def check(self, *, lock=False):
        """
        Raise ClaimLost unless this claim generation is still the row's.
        With ``lock=True`` the row is locked (FOR UPDATE) for the rest of
        the enclosing transaction, so no recovery can take the run over
        between this check and the writes that follow it.
        """
        if self.lost:
            self._refuse('is no longer owned (lease lost)')
        rows = self.owned_rows()
        if lock:
            rows = rows.select_for_update()
        if not list(rows.values_list('pk', flat=True)):
            self._refuse('is no longer current')

    def update(self, **fields):
        """Write ``fields`` to the run row only while this generation owns it; raise ClaimLost otherwise."""
        if self.lost:
            self._refuse('is no longer owned (lease lost); write refused')
        updated = self.owned_rows().update(**fields)
        if updated != 1:
            self._refuse('is no longer current; write refused')
        return updated

    def persistence_guard(self):
        """The solver's hook: verify ownership inside its persistence transaction."""
        self.check(lock=True)
