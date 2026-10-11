"""
AllocationRun lifecycle services: duplicate-run-protected run creation, the
synchronous solve and retry-unassigned workflows, stop / stop-and-save
requests, draft deletion and failure marking.

Every function here takes ordinary Python inputs and model instances; HTTP
status and error-body mapping stays in api.views.allocation. The solver
handover itself goes through the allocation-engine boundary
(inputs.load_solver_population / measure_population, engine.SolverInput /
invoke_solver / SolverOutcome, persistence.*); the background worker in
orchestration.py uses the same boundary.
"""

from dataclasses import dataclass, field

from django.db import transaction
from django.utils import timezone

from ...db_connection import refresh_db_connection
from ...models import AllocationRun, Region
from .engine import SolverInput, SolverOutcome, invoke_solver
from .inputs import load_solver_population, measure_population, retry_population_summary
from .orchestration import _cleanup_run_assignments
from .persistence import (
    apply_run_fields,
    completed_run_fields,
    empty_run_diagnostics,
    no_rooms_run_fields,
    no_students_run_fields,
    population_summary_with_outcome,
    population_summary_without_solve,
    solved_run_diagnostics,
)
from .queries import solver_rooms_for_region
from .results import (
    build_assignment_rows_for_run,
    build_assignment_rows_for_students,
)

TERMINAL_RUN_STATUSES = frozenset({
    AllocationRun.Status.STOPPED,
    AllocationRun.Status.COMPLETED,
    AllocationRun.Status.FAILED,
    AllocationRun.Status.DELETED,
    AllocationRun.Status.APPROVED,
})

# The two "please stop" statuses an operator can request on a live run.
STOP_REQUEST_STATUSES = (
    AllocationRun.Status.CANCELLATION_REQUESTED,
    AllocationRun.Status.STOP_AND_SAVE_REQUESTED,
)


class AllocationAlreadyRunning(Exception):
    """Raised by create_run_for_region when the region already has a live run."""

    def __init__(self, active_run):
        super().__init__('allocation already running for region')
        self.active_run = active_run


class RunNotDeletable(Exception):
    """Raised by delete_completed_run_results for an APPROVED or non-COMPLETED run."""

    def __init__(self, run_status, reason):
        super().__init__(reason)
        self.run_status = run_status
        self.reason = reason  # 'approved' | 'not_completed'


@dataclass(frozen=True)
class StopRequestOutcome:
    """Result of request_run_stop: what the locked transition decided."""

    outcome: str  # 'requested' | 'already_requested' | 'conflicting_request' | 'terminal' | 'forbidden'
    run_status: str


@dataclass
class SyncAllocationOutcome:
    """What a synchronous run produced, for the HTTP layer to map."""

    kind: str  # 'no_students' | 'no_rooms' | 'completed'
    students_total_in_region: int
    students_count: int
    population_summary: dict
    anier_building_179_diagnostics: dict
    result: dict = field(default_factory=dict)
    roommate_matches: int = 0
    assignment_rows: list = field(default_factory=list)


@dataclass
class RetryAllocationOutcome:
    """What a retry-unassigned run produced, for the HTTP layer to map."""

    result: dict
    roommate_matches: int
    population_summary: dict
    assignment_rows: list


def create_run_for_region(region, run_by, *, status, blocking_statuses, **run_fields):
    """
    Create an AllocationRun for ``region`` unless one in ``blocking_statuses``
    already exists. The Region row lock prevents two requests from creating
    live runs for the same region at the same time.

    Raises AllocationAlreadyRunning(active_run) without creating anything
    when a blocking run exists.
    """
    with transaction.atomic():
        Region.objects.select_for_update().get(pk=region.pk)
        active_run = AllocationRun.objects.filter(
            region=region,
            status__in=list(blocking_statuses),
        ).order_by('-started_at').first()

        if active_run is not None:
            raise AllocationAlreadyRunning(active_run)

        return AllocationRun.objects.create(
            region=region,
            run_by=run_by,
            status=status,
            **run_fields,
        )


def parse_max_solver_seconds(raw_value):
    """
    "Maximum search duration" (זמן חיפוש מרבי) chosen by the operator before
    starting a run - a MAXIMUM, not a target: if CP-SAT proves OPTIMAL
    earlier, it still finishes immediately (solver.py:max_time_in_seconds).
    Validated here AND again, independently, inside
    run_improved_ortools_allocation itself - so a malformed/bypassed request
    can never hand CP-SAT an unreasonable duration even if this check were
    ever skipped.

    Returns the solver's default (unchanged type) when the value is absent,
    otherwise a float. Raises ValueError with the user-facing message.
    """
    from .gateway import (
        MIN_USER_SOLVER_TIME_SECONDS,
        MAX_USER_SOLVER_TIME_SECONDS,
        DEFAULT_SOLVER_TIME_SECONDS,
    )

    if raw_value in (None, ''):
        return DEFAULT_SOLVER_TIME_SECONDS

    try:
        max_solver_seconds = float(raw_value)
    except (TypeError, ValueError):
        raise ValueError('זמן חיפוש מרבי חייב להיות מספר') from None

    if not (MIN_USER_SOLVER_TIME_SECONDS <= max_solver_seconds <= MAX_USER_SOLVER_TIME_SECONDS):
        raise ValueError(
            f'זמן חיפוש מרבי חייב להיות בין {MIN_USER_SOLVER_TIME_SECONDS} '
            f'ל-{MAX_USER_SOLVER_TIME_SECONDS} שניות'
        )

    return max_solver_seconds


def original_solver_population_ids(run):
    """The exact student ids a completed run sent to the solver, if persisted."""
    original_summary = (run.diagnostics or {}).get('population_summary') or {}
    return original_summary.get('sent_to_solver_student_ids')


def request_run_stop(run_id, requested_status, *, authorize):
    """
    Move a live run to CANCELLATION_REQUESTED or STOP_AND_SAVE_REQUESTED
    under the run's row lock. ``authorize(run)`` is evaluated under that
    same lock, so the caller's region check sees the locked row exactly as
    before. Idempotent: a repeated request reports 'already_requested'; a
    competing request of the other kind that won the lock first reports
    'conflicting_request' and is never overridden.

    Raises AllocationRun.DoesNotExist for an unknown run id. On
    'requested', also interrupts a solver running in this same process.
    """
    with transaction.atomic():
        run = AllocationRun.objects.select_for_update().get(pk=run_id)

        if not authorize(run):
            return StopRequestOutcome('forbidden', run.status)

        if run.status in TERMINAL_RUN_STATUSES:
            return StopRequestOutcome('terminal', run.status)

        if run.status == requested_status:
            return StopRequestOutcome('already_requested', run.status)

        if run.status in STOP_REQUEST_STATUSES:
            # Race protection: the other kind of stop request already won
            # the row lock first - do not silently override it.
            return StopRequestOutcome('conflicting_request', run.status)

        AllocationRun.objects.filter(pk=run_id).update(status=requested_status)

    # Best-effort same-process fast path: if the solver for this run
    # happens to be running in this exact process, interrupt it
    # immediately instead of waiting for _run_stop_watcher's next poll
    # tick. Harmless no-op otherwise (cross-process case) - the DB flag
    # just written above is what _run_stop_watcher/_LiveSolutionCallback
    # actually rely on to notice the request everywhere else.
    from .gateway import live_registry
    live_registry.request_stop_search(run_id)

    return StopRequestOutcome('requested', requested_status)


def delete_completed_run_results(run):
    """
    Delete the draft results of a COMPLETED (not APPROVED) run: cancels the
    BedAssignments it created, restores the students and marks the run
    DELETED. Returns the number of cancelled assignments.
    """
    if run.status == AllocationRun.Status.APPROVED:
        raise RunNotDeletable(run.status, 'approved')

    if run.status != AllocationRun.Status.COMPLETED:
        raise RunNotDeletable(run.status, 'not_completed')

    return _cleanup_run_assignments(
        run.id,
        mark_status=AllocationRun.Status.DELETED,
    )


def mark_run_failed(run, error_message):
    """Persist a FAILED outcome on a run whose synchronous solve raised."""
    run.status = AllocationRun.Status.FAILED
    run.error_message = error_message
    run.completed_at = timezone.now()

    refresh_db_connection()
    run.save()


def _log_solver_result(result):
    print(">>> SOLVER RAW RESULT TYPE:", type(result), flush=True)

    if isinstance(result, dict):
        assignments_value = result.get("assignments", [])
        conflicts_value = result.get("conflicts", 0)
        no_feasible_value = result.get("students_with_no_feasible_beds", [])

        print(">>> SOLVER RAW RESULT KEYS:", list(result.keys()), flush=True)
        print(">>> SOLVER students_processed:", result.get("students_processed"), flush=True)
        print(">>> SOLVER successful_assignments:", result.get("successful_assignments"), flush=True)
        print(">>> SOLVER conflicts:", conflicts_value, flush=True)
        print(">>> SOLVER solver_status:", result.get("solver_status"), flush=True)
        print(">>> SOLVER objective_value:", result.get("objective_value"), flush=True)
        print(">>> SOLVER wall_time:", result.get("wall_time"), flush=True)
        warnings_value = result.get("warnings", [])
        print(
            ">>> SOLVER warnings len:",
            len(warnings_value) if isinstance(warnings_value, list) else "not-list",
            flush=True,
        )

        print(
            ">>> SOLVER assignments len:",
            len(assignments_value) if isinstance(assignments_value, list) else "not-list",
            flush=True
        )

        # Counts only: the per-student lists and warnings carry student
        # identifiers and are persisted on the run row, not echoed to stdout.
        print(
            ">>> SOLVER students_with_no_feasible_beds len:",
            len(no_feasible_value) if isinstance(no_feasible_value, list) else "not-list",
            flush=True
        )
    else:
        print(">>> SOLVER RAW RESULT: unexpected type", type(result).__name__, flush=True)


def execute_sync_allocation(allocation_run, region, *, constraints_config,
                            include_assigned=False, allocation_scope=None):
    """
    The legacy synchronous allocation workflow for an already-created
    RUNNING run: build the solver population and rooms, short-circuit on an
    empty population (COMPLETED) or no active rooms (FAILED), otherwise
    solve, persist the run's outcome and build this run's assignment rows.

    The solver is invoked WITHOUT this run's id (SolverInput.allocation_run_id
    is None): the assignments it persists are therefore not tagged with the
    run, no live preview is published and stop requests are not honoured -
    the behaviour this endpoint has always had. Its response rows are built
    from the captured solver-input ids instead (build_assignment_rows_for_students).

    Exceptions propagate; the caller marks the run FAILED (see
    mark_run_failed).
    """
    from .gateway import EMPTY_ANIER_BUILDING_179_DIAGNOSTICS

    population = load_solver_population(
        region, include_assigned=include_assigned, allocation_scope=allocation_scope,
    )
    # The region total, the exact solver-input ids (captured before the
    # solver updates assignments - the response table must describe this
    # run, not every historical active assignment in the region), the
    # population summary scoped to this region/run, and the counts, all
    # read before the solver runs.
    snapshot = measure_population(population)
    students_total_in_region = snapshot.students_total_in_region
    students_count = snapshot.students_count
    rooms_count = snapshot.rooms_count
    run_student_ids = snapshot.student_ids
    population_summary = snapshot.population_summary

    print(
        ">>> ALLOCATION_INPUT "
        f"run_id={allocation_run.id} "
        f"region={region.id} "
        f"scope={allocation_scope or 'all_unassigned_non_leaving'} "
        f"include_assigned={include_assigned} "
        f"students_total_in_region={students_total_in_region} "
        f"students_sent_to_solver={students_count} "
        f"rooms_sent_to_solver={rooms_count}",
        flush=True,
    )

    if students_count == 0:
        apply_run_fields(allocation_run, no_students_run_fields())
        allocation_run.error_message = ''
        allocation_run.diagnostics = empty_run_diagnostics(population_summary)

        refresh_db_connection()
        allocation_run.save()

        return SyncAllocationOutcome(
            kind='no_students',
            students_total_in_region=students_total_in_region,
            students_count=0,
            population_summary=population_summary_without_solve(population_summary),
            anier_building_179_diagnostics=dict(EMPTY_ANIER_BUILDING_179_DIAGNOSTICS),
        )

    if rooms_count == 0:
        # Unlike the background worker, the synchronous run records no
        # diagnostics for this failure.
        apply_run_fields(allocation_run, no_rooms_run_fields())

        refresh_db_connection()
        allocation_run.save()

        return SyncAllocationOutcome(
            kind='no_rooms',
            students_total_in_region=students_total_in_region,
            students_count=students_count,
            population_summary=population_summary,
            anier_building_179_diagnostics={},
        )

    print(
        f">>> BEFORE_SOLVER run_id={allocation_run.id} region={region.id} students={students_count} rooms={rooms_count}",
        flush=True,
    )

    result = invoke_solver(SolverInput(
        students=population.students,
        rooms=population.rooms,
        constraints_config=constraints_config,
        allocation_run_id=None,
        max_seconds=None,
    ))

    print(
        f">>> AFTER_SOLVER run_id={allocation_run.id} region={region.id} result_type={type(result).__name__}",
        flush=True,
    )
    _log_solver_result(result)

    if not isinstance(result, dict):
        raise ValueError(f'Unexpected solver result type: {type(result).__name__}')

    outcome = SolverOutcome.from_result(result)
    roommate_matches = outcome.roommate_matches

    apply_run_fields(allocation_run, completed_run_fields(outcome, students_count=students_count))
    population_summary = population_summary_with_outcome(population_summary, outcome)
    allocation_run.diagnostics = solved_run_diagnostics(outcome, population_summary)

    # After a long solver run, reuse a healthy database connection and
    # reconnect only if Django reports that the connection is unusable.
    refresh_db_connection()
    allocation_run.save()

    refresh_db_connection()
    assignment_rows = build_assignment_rows_for_students(region, run_student_ids)

    print(">>> RESPONSE assignment_rows len:", len(assignment_rows), flush=True)

    return SyncAllocationOutcome(
        kind='completed',
        students_total_in_region=students_total_in_region,
        students_count=students_count,
        population_summary=population_summary,
        anier_building_179_diagnostics=outcome.anier_building_179_diagnostics,
        result=result,
        roommate_matches=roommate_matches,
        assignment_rows=assignment_rows,
    )


def execute_retry_allocation(original_run, retry_run, retry_students_qs, retry_student_ids,
                             *, constraints_config):
    """
    Re-solve only the given still-unassigned students of ``original_run``
    against the region's current active inventory, persist the retry run's
    outcome (traceable via diagnostics.retry_of_run_id) and build its
    assignment rows. Exceptions propagate; the caller marks the retry run
    FAILED (see mark_run_failed).

    Unlike a full run, the retry population is the caller's queryset of
    original solver-input students (retry_population_queryset), its
    population summary is the synthetic retry_population_summary, and the
    solver IS given the retry run's id, so the assignments it persists are
    tagged with the retry run.
    """
    result = invoke_solver(SolverInput(
        students=retry_students_qs,
        rooms=solver_rooms_for_region(original_run.region),
        constraints_config=constraints_config,
        allocation_run_id=retry_run.id,
        max_seconds=None,
    ))

    outcome = SolverOutcome.from_result(result)
    roommate_matches = outcome.roommate_matches

    population_summary = population_summary_with_outcome(
        retry_population_summary(retry_student_ids), outcome,
    )

    apply_run_fields(retry_run, completed_run_fields(outcome, students_count=len(retry_student_ids)))
    retry_run.diagnostics = solved_run_diagnostics(
        outcome, population_summary, retry_of_run_id=original_run.id,
    )
    refresh_db_connection()
    retry_run.save()

    return RetryAllocationOutcome(
        result=result,
        roommate_matches=roommate_matches,
        population_summary=population_summary,
        assignment_rows=build_assignment_rows_for_run(retry_run),
    )
