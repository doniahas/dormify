"""
Allocation run orchestration: the execution of one background run
(execute_allocation_run, the job body the durable allocation worker runs
for a claimed AllocationRun), plus the solver-eligibility filter, the
population summary and the run cleanup shared by the allocation entry
points.

The run body builds its solver input, invokes the solver and records the
run's outcome through the allocation-engine boundary (inputs, engine,
persistence modules) - the same one the synchronous workflows in runs.py
use. Claiming, leases and recovery of lost workers live in jobs.py; the
worker loop in worker.py.

The api.views compatibility facade (api/views/__init__.py) imports every
name defined here, so references through the api.views namespace keep
resolving to these same objects.
"""

import traceback

from django.db import transaction
from django.utils import timezone

from ...models import AllocationRun, BedAssignment, Region, Student
# The solver-derived diagnostics block is owned by the engine boundary; the
# api.views facade keeps binding it under this name.
from .engine import run_diagnostics_payload as _run_diagnostics_payload  # noqa: F401
from .fencing import ClaimLost


def _exclude_non_solver_students(students_qs):
    """
    Shared solver-input population filter, used identically by both the
    sync (run_allocation) and async (execute_allocation_run)
    allocation entry points so the two paths cannot silently drift apart.

    Both exclusions are unconditional. category and accessibility_flag are
    permanent fields on the Student model (not optional/dynamic ones), so
    this must never be gated behind a field-existence check — doing so
    would risk silently skipping the accessibility exclusion if that check
    were ever wrong, which is unacceptable for a safety-relevant filter.

      - LEAVING-category students are never sent to the solver.
      - accessibility_flag=True students are imported and saved normally,
        but must never reach the OR-Tools solver — the dorm office
        allocates them manually. This is independent of is_priority (see
        priority_fields_from_special_statuses in the Excel import code);
        exclusion here is a read-time queryset filter only, so it never
        clears or rewrites is_priority/priority_reason/special_status_*/
        accessibility metadata on the Student row itself.
    """
    return students_qs.exclude(
        category=Student.StudentCategory.LEAVING,
    ).exclude(
        accessibility_flag=True,
    )


def _population_summary_for_region(region, *, sent_to_solver_student_ids=None):
    """
    Distinct-count population breakdown explaining why the number of
    students sent to the solver is smaller than the number imported for
    this region — always scoped to this region's Student rows only, never
    a global Student count, and never scoped to a different
    region/upload.

    imported_students   — every Student row accepted into a dorm type in
                           this region (the full "received" population).
    excluded_accessibility / excluded_leaving — counts within that same
                           population; a student in both counts once
                           towards excluded_overlap, so excluded_total is
                           the DISTINCT union, not a naive sum.
    sent_to_solver / sent_to_solver_student_ids — when the caller already
                           knows the exact solver-input population for a
                           specific run (the real `students` queryset),
                           pass their ids in and this reports that exact
                           set. Otherwise (a pre-run preview, before any
                           AllocationRun exists) this derives the same
                           population run_allocation/_execute_allocation_
                           background would build by default: eligible
                           (non-leaving, non-accessibility) and not yet
                           assigned.

    sent_to_solver_student_ids is kept in the returned dict (not just the
    count) so it can be persisted on AllocationRun.diagnostics and later
    used to reconstruct "which of these specific students are still
    unassigned" for the results page and the retry-unassigned workflow —
    without needing a new model field or migration.
    """
    population_qs = Student.objects.filter(accepted_dorm_type__region=region)
    imported_students = population_qs.count()

    excluded_accessibility = population_qs.filter(accessibility_flag=True).count()
    excluded_leaving = population_qs.filter(category=Student.StudentCategory.LEAVING).count()
    excluded_overlap = population_qs.filter(
        accessibility_flag=True,
        category=Student.StudentCategory.LEAVING,
    ).count()
    excluded_total = excluded_accessibility + excluded_leaving - excluded_overlap

    if sent_to_solver_student_ids is None:
        eligible_qs = _exclude_non_solver_students(population_qs).filter(
            assigned_room__isnull=True,
        )
        sent_to_solver_student_ids = list(eligible_qs.values_list('id', flat=True))
    else:
        sent_to_solver_student_ids = list(sent_to_solver_student_ids)

    return {
        'imported_students': imported_students,
        'excluded_accessibility': excluded_accessibility,
        'excluded_leaving': excluded_leaving,
        'excluded_overlap': excluded_overlap,
        'excluded_total': excluded_total,
        'sent_to_solver': len(sent_to_solver_student_ids),
        'sent_to_solver_student_ids': sent_to_solver_student_ids,
    }


def _cleanup_run_assignments(run_id, mark_status, owner=None):
    """
    Atomically cancel ACTIVE BedAssignments created by this run, restore
    student records, and set the run to the given terminal status.
    Returns the count of cancelled assignments.

    ``owner`` (a fencing.ClaimFence) makes the run-status write conditional
    on the caller still owning the run's current claim; when it does not,
    ClaimLost is raised and the whole cleanup is rolled back. Callers
    outside a fenced execution (draft deletion, recovery) pass nothing.
    """
    from django.db import close_old_connections
    close_old_connections()

    with transaction.atomic():
        now = timezone.now()

        assignments_qs = BedAssignment.objects.filter(
            allocation_run_id=run_id,
            status=BedAssignment.Status.ACTIVE,
        )

        student_ids = list(assignments_qs.values_list('student_id', flat=True))
        deleted_count = assignments_qs.count()

        assignments_qs.update(
            status=BedAssignment.Status.CANCELLED,
            ended_at=now,
        )

        if student_ids:
            Student.objects.filter(id__in=student_ids).update(assigned_room=None)

        if owner is None:
            AllocationRun.objects.filter(pk=run_id).update(
                status=mark_status,
                completed_at=now,
            )
        else:
            owner.update(status=mark_status, completed_at=now)

    return deleted_count


def execute_allocation_run(allocation_run_id, region_id, constraints_config,
                           include_assigned, allocation_scope, max_seconds=None,
                           fence=None):
    """
    Execute one background allocation run to completion on the calling
    thread. This is the job body the durable allocation worker
    (api.domains.allocation.jobs / ``manage.py allocation_worker``) runs for
    a claimed AllocationRun. Until R8 the same body ran on a daemon thread
    started by the HTTP request; the request now only queues the run
    (api.views.allocation.start_allocation_run) and the worker owns
    execution, so a run survives the request, the web process and worker
    restarts.

    Every write is a QuerySet.update() on the run row, so the database is
    the authoritative lifecycle state throughout: QUEUED -> RUNNING -> one
    of COMPLETED / FAILED / STOPPED. A stop request that arrived before this
    body started (status already CANCELLATION_REQUESTED or
    STOP_AND_SAVE_REQUESTED) is finalized as STOPPED without a solve; one
    that arrives while the solver runs is observed by the solver's own stop
    watcher (allocation/solver.py: _run_stop_watcher polls the database
    status - the in-process live_registry fast path is only an
    optimization) and acted on in the post-solve branch below. Any
    exception marks the run FAILED. The function opens and closes its own
    database connection, as the thread body always did.

    ``fence`` (fencing.ClaimFence, passed by the durable worker) makes every
    write to the run row conditional on this execution still owning the
    run's current claim generation, hands the solver a persistence guard
    that verifies the same inside its persistence transaction and the
    generation's row lookups for its own run-row writes (search-start
    stamp, live-snapshot mirror, stop watcher), and makes a
    stale execution stop with ClaimLost (re-raised to the caller) instead
    of persisting or finalizing anything. Without a fence every write is
    the plain update it always was.
    """
    from django.db import close_old_connections, connection as db_conn

    run_rows = AllocationRun.objects.filter(pk=allocation_run_id)

    def write_run(**fields):
        if fence is None:
            run_rows.update(**fields)
        else:
            fence.update(**fields)

    try:
        close_old_connections()

        region = Region.objects.get(pk=region_id)
        current_status = AllocationRun.objects.filter(
            pk=allocation_run_id
        ).values_list('status', flat=True).first()

        if current_status == AllocationRun.Status.CANCELLATION_REQUESTED:
            write_run(
                status=AllocationRun.Status.STOPPED,
                completed_at=timezone.now(),
            )
            return

        if current_status == AllocationRun.Status.STOP_AND_SAVE_REQUESTED:
            # A Stop & Save requested while the run was still waiting in the
            # queue has nothing to save - no solve has started - so it ends
            # exactly like a Stop & Save that found no feasible solution
            # (the post-solve branch below). With the request-owned thread
            # this state was practically unreachable; with a durable queue a
            # run can wait long enough for an operator to stop it.
            from .persistence import stopped_without_solution_diagnostics

            write_run(
                status=AllocationRun.Status.STOPPED,
                completed_at=timezone.now(),
                diagnostics=stopped_without_solution_diagnostics(),
            )
            return

        write_run(status=AllocationRun.Status.RUNNING)

        from .engine import SolverInput, SolverOutcome, invoke_solver
        from .inputs import load_solver_population, measure_population
        from .persistence import (
            completed_run_fields,
            empty_run_diagnostics,
            no_rooms_run_fields,
            no_students_run_fields,
            population_summary_with_outcome,
            solved_run_diagnostics,
            stopped_without_solution_diagnostics,
        )

        population = load_solver_population(
            region, include_assigned=include_assigned, allocation_scope=allocation_scope,
        )

        # The region total (read and unused, as before: removing that
        # COUNT changes the run's database work), the exact solver-
        # input ids captured before the solver runs - so the population
        # summary and any later retry-unassigned request can trace
        # exactly who this run considered - and the counts.
        snapshot = measure_population(population)
        population_summary = snapshot.population_summary
        students_count = snapshot.students_count
        rooms_count = snapshot.rooms_count

        empty_diagnostics = empty_run_diagnostics(population_summary)

        if students_count == 0:
            write_run(
                **no_students_run_fields(),
                diagnostics=empty_diagnostics,
            )
            return

        if rooms_count == 0:
            write_run(
                **no_rooms_run_fields(),
                diagnostics=empty_diagnostics,
            )
            return

        close_old_connections()

        if fence is not None:
            # Pre-solver fence: a worker that lost its claim while loading
            # the population must not start solving.
            fence.check()

        result = invoke_solver(SolverInput(
            students=population.students,
            rooms=population.rooms,
            constraints_config=constraints_config,
            allocation_run_id=allocation_run_id,
            max_seconds=max_seconds,
            persistence_guard=fence.persistence_guard if fence is not None else None,
            run_ownership_filter=fence.ownership_filter() if fence is not None else None,
        ))
        outcome = SolverOutcome.from_result(result)
        solved_population_summary = population_summary_with_outcome(population_summary, outcome)

        write_run(
            diagnostics=solved_run_diagnostics(outcome, solved_population_summary),
        )

        # Check for a stop request noticed while the solver was
        # running. Both CANCELLATION_REQUESTED and
        # STOP_AND_SAVE_REQUESTED already triggered a real
        # solver.StopSearch() well before this point (see
        # _run_stop_watcher / _LiveSolutionCallback in
        # allocation/solver.py) - this check only decides what to DO
        # with whatever result the (possibly early-stopped) solve
        # produced: Cancel always discards it; Stop & Save keeps it
        # if - and only if - best-effort persistence already saved a
        # FEASIBLE/OPTIMAL result (unchanged solver.py logic; if
        # nothing was feasible yet, nothing was persisted, so there
        # is nothing to clean up).
        post_status = AllocationRun.objects.filter(
            pk=allocation_run_id
        ).values_list('status', flat=True).first()

        if post_status == AllocationRun.Status.CANCELLATION_REQUESTED:
            _cleanup_run_assignments(
                allocation_run_id,
                mark_status=AllocationRun.Status.STOPPED,
                owner=fence,
            )
            write_run(live_snapshot=None)
            return

        stopped_early_by_user = post_status == AllocationRun.Status.STOP_AND_SAVE_REQUESTED

        if stopped_early_by_user and not outcome.solution_persisted:
            write_run(
                status=AllocationRun.Status.STOPPED,
                completed_at=timezone.now(),
                live_snapshot=None,
                diagnostics=stopped_without_solution_diagnostics(),
            )
            return

        update_fields = {
            **completed_run_fields(outcome, students_count=students_count),
            'live_snapshot': None,
        }
        if stopped_early_by_user:
            # Same diagnostics shape already written above, plus the
            # one extra marker - so a stop-and-save result is
            # indistinguishable from a natural completion except for
            # this flag (used by the frontend to show "not proven
            # optimal, stopped early" instead of a plain success).
            update_fields['diagnostics'] = solved_run_diagnostics(
                outcome, solved_population_summary, stopped_early_by_user=True,
            )

        write_run(**update_fields)

        print(
            f">>> ASYNC_ALLOCATION_DONE run_id={allocation_run_id} "
            f"assignments={outcome.successful_assignments}",
            flush=True,
        )

    except ClaimLost:
        # Ownership of the run moved to another worker: nothing was written
        # by the refused operation and nothing more may be; the caller
        # (the worker) records the fenced execution.
        raise
    except Exception as exc:
        traceback.print_exc()
        try:
            write_run(
                status=AllocationRun.Status.FAILED,
                error_message=str(exc)[:5000],
                completed_at=timezone.now(),
                live_snapshot=None,
            )
        except ClaimLost:
            raise
        except Exception:
            traceback.print_exc()
    finally:
        try:
            db_conn.close()
        except Exception:
            pass
