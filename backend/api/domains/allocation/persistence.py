"""
Run-outcome persistence boundary: the AllocationRun field sets and the
diagnostics documents the entry points write once a solve has finished or
been skipped.

Ownership of writes around a run:

- the solver (``allocation.solver``) persists the BedAssignment rows and
  the students' ``assigned_room`` atomically inside its own transaction,
  and stamps ``search_started_at``; that is the application of results;
- the entry points persist the run's OUTCOME - status, counters,
  completion time and the diagnostics document - using the records built
  here. The synchronous paths apply them to the model instance and
  ``save()`` (model validation runs); the background worker issues
  ``QuerySet.update`` with these exact column sets and orders;
- ``orchestration._cleanup_run_assignments`` is the result cleanup
  (cancellation and draft deletion).

Nothing here starts a transaction or decides WHEN to write.
"""

from django.utils import timezone

from ...models import AllocationRun
from .engine import SolverOutcome

# The failure recorded when a region has no active room to allocate into.
NO_ACTIVE_ROOMS_MESSAGE = 'לא נמצאו חדרים פעילים באזור זה'


def population_summary_with_outcome(population_summary, outcome):
    """The persisted population summary: the pre-solve summary plus the solve's assigned / unassigned split."""
    return {
        **population_summary,
        'assigned': outcome.successful_assignments,
        'unassigned': outcome.conflicts,
    }


def population_summary_without_solve(population_summary):
    """The population summary of a run that never solved (nothing assigned or unassigned)."""
    return {**population_summary, 'assigned': 0, 'unassigned': 0}


def empty_run_diagnostics(population_summary):
    """
    Diagnostics of a run that completed or failed before the solver ran:
    no warnings, zeroed Building-179 counters, the zero population summary.
    """
    from .gateway import EMPTY_ANIER_BUILDING_179_DIAGNOSTICS

    return {
        'warnings': [],
        'anier_building_179_diagnostics': dict(EMPTY_ANIER_BUILDING_179_DIAGNOSTICS),
        'population_summary': population_summary_without_solve(population_summary),
    }


def stopped_without_solution_diagnostics():
    """Diagnostics of a Stop & Save that found no feasible solution to keep."""
    from .gateway import EMPTY_ANIER_BUILDING_179_DIAGNOSTICS

    return {
        'warnings': [],
        'anier_building_179_diagnostics': dict(EMPTY_ANIER_BUILDING_179_DIAGNOSTICS),
        'stop_reason': 'no_feasible_solution_before_stop',
    }


def solved_run_diagnostics(outcome, population_summary, **markers):
    """
    Diagnostics of a solved run: the solver payload, then the persisted
    population summary (already merged with the outcome, see
    population_summary_with_outcome), then any per-path marker
    (``retry_of_run_id``, ``stopped_early_by_user``) in the order given.
    """
    return {
        **outcome.diagnostics_payload(),
        'population_summary': population_summary,
        **markers,
    }


def completed_run_fields(outcome, *, students_count, completed_at=None):
    """
    The AllocationRun columns a solved run completes with, in the order the
    worker writes them: status, the four counters, completion time.
    """
    return {
        'status': AllocationRun.Status.COMPLETED,
        'students_processed': outcome.students_processed(students_count),
        'successful_assignments': outcome.successful_assignments,
        'roommate_matches': outcome.roommate_matches,
        'conflicts': outcome.conflicts,
        'completed_at': completed_at or timezone.now(),
    }


def no_students_run_fields(completed_at=None):
    """The columns of a run completed without a solver call: every counter zero."""
    return {
        'status': AllocationRun.Status.COMPLETED,
        'students_processed': 0,
        'successful_assignments': 0,
        'roommate_matches': 0,
        'conflicts': 0,
        'completed_at': completed_at or timezone.now(),
    }


def no_rooms_run_fields(completed_at=None):
    """The columns of a run failed because the region has no active room."""
    return {
        'status': AllocationRun.Status.FAILED,
        'error_message': NO_ACTIVE_ROOMS_MESSAGE,
        'completed_at': completed_at or timezone.now(),
    }


def apply_run_fields(run, fields):
    """Set ``fields`` on the AllocationRun instance (the caller saves it)."""
    for name, value in fields.items():
        setattr(run, name, value)
    return run


__all__ = [
    'NO_ACTIVE_ROOMS_MESSAGE',
    'SolverOutcome',
    'apply_run_fields',
    'completed_run_fields',
    'empty_run_diagnostics',
    'no_rooms_run_fields',
    'no_students_run_fields',
    'population_summary_with_outcome',
    'population_summary_without_solve',
    'solved_run_diagnostics',
    'stopped_without_solution_diagnostics',
]
