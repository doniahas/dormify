"""
Allocation-domain querysets shared by the allocation and assisted-allocation
entry points: solver input populations, the unassigned/accessibility queues
and AllocationRun lookups.
"""

from ...model_metadata import _get_model_field_names
from ...models import AllocationRun, BedAssignment, Room, Student
from .orchestration import _exclude_non_solver_students

# Statuses that mean "a run is in progress" for the read endpoints
# (get_active_allocation_run / allocation_status).
ACTIVE_RUN_STATUSES = (
    AllocationRun.Status.QUEUED,
    AllocationRun.Status.RUNNING,
    AllocationRun.Status.CANCELLATION_REQUESTED,
)

# Statuses that block starting a new async run for the same region.
START_BLOCKING_RUN_STATUSES = (
    AllocationRun.Status.QUEUED,
    AllocationRun.Status.RUNNING,
    AllocationRun.Status.CANCELLATION_REQUESTED,
    AllocationRun.Status.STOP_AND_SAVE_REQUESTED,
)


def solver_rooms_for_region(region):
    """Active rooms (in active apartments/buildings) the solver may fill."""
    return Room.objects.filter(
        apartment__building__dorm_type__region=region,
        is_active=True,
        apartment__is_active=True,
        apartment__building__is_active=True,
    ).select_related(
        'apartment',
        'apartment__building',
        'apartment__building__dorm_type',
    ).prefetch_related('beds')


def solver_students_for_region(region, *, include_assigned=False, allocation_scope=None):
    """
    Solver-input population of an application run (the synchronous run and
    the background worker both build theirs through
    inputs.load_solver_population, which wraps this).

    Returns ``(students_base, students)``: the region's solver-eligible
    population (leavers and accessibility students excluded) and the
    subset actually sent to the solver after the include_assigned /
    allocation_scope narrowing.
    """
    student_fields = _get_model_field_names(Student)

    students_base = Student.objects.filter(
        accepted_dorm_type__region=region
    ).select_related(
        'accepted_dorm_type',
        'accepted_dorm_type__region'
    )
    students_base = _exclude_non_solver_students(students_base)
    students = students_base

    # Default solver scope: allocate only students who are not already assigned.
    # {"include_assigned": true} exists only for debugging/rebuilding full allocations.
    if not include_assigned:
        if 'assigned_bed' in student_fields:
            students = students.filter(assigned_bed__isnull=True)
        elif 'assigned_room' in student_fields:
            students = students.filter(assigned_room__isnull=True)

    # Optional narrow scope: allocate only new/transfer students.
    if allocation_scope == 'new_transfer_only' and 'category' in student_fields:
        students = students.filter(
            category__in=[
                Student.StudentCategory.NEW,
                Student.StudentCategory.TRANSFER,
            ]
        )

    return students_base, students


def retry_population_queryset(original_student_ids):
    """
    Students from a completed run's original solver population who are
    still solver-eligible and still unassigned - a read-time filter only,
    so every existing assignment is left untouched.
    """
    return _exclude_non_solver_students(
        Student.objects.filter(id__in=original_student_ids)
    ).filter(assigned_room__isnull=True).select_related(
        'accepted_dorm_type', 'accepted_dorm_type__region',
    )


def unassigned_students_queryset(region=None):
    """
    Currently-unassigned, solver-eligible students (excludes leaving and
    accessibility-flagged students, who are never part of this population -
    accessibility students are handled entirely by the separate
    accessibility-pending queue, see accessibility_pending_queryset).

    Single source of truth for this population, shared by allocation_results
    and the Assisted Allocation queue endpoint so they can never drift.
    """
    queryset = Student.objects.select_related(
        'accepted_dorm_type',
        'accepted_dorm_type__region',
    ).exclude(
        category=Student.StudentCategory.LEAVING
    ).exclude(
        accessibility_flag=True
    ).filter(
        assigned_room__isnull=True
    )

    if region:
        queryset = queryset.filter(accepted_dorm_type__region=region)

    return queryset.order_by(
        '-is_priority',
        'last_name',
        'first_name',
        'student_id',
    )


def accessibility_pending_queryset(region=None):
    """Accessibility-flagged students who still have no bed assignment."""
    queryset = Student.objects.select_related(
        'accepted_dorm_type',
        'accepted_dorm_type__region',
    ).filter(
        accessibility_flag=True,
        assigned_room__isnull=True,
    )

    if region:
        queryset = queryset.filter(accepted_dorm_type__region=region)

    return queryset.order_by('last_name', 'first_name', 'student_id')


def latest_run_in_statuses(region, statuses):
    """Most recently started run of this region in one of ``statuses``."""
    return AllocationRun.objects.filter(
        region=region,
        status__in=list(statuses),
    ).order_by('-started_at').first()


def latest_run_for_region(region):
    """Most recently started run of this region, whatever its status."""
    return AllocationRun.objects.filter(region=region).order_by('-started_at').first()


def run_has_current_assignments(run):
    """True when the run still owns ACTIVE assignments in active inventory."""
    return BedAssignment.objects.filter(
        allocation_run=run,
        status=BedAssignment.Status.ACTIVE,
        bed__room__is_active=True,
        bed__room__apartment__is_active=True,
        bed__room__apartment__building__is_active=True,
    ).exists()


def current_run_for_region(region):
    """
    The run the allocation page should show for a region: an in-progress
    run, otherwise the latest COMPLETED run only while its assignments
    still exist, otherwise None.
    """
    active_run = latest_run_in_statuses(region, ACTIVE_RUN_STATUSES)
    if active_run:
        return active_run

    latest_completed_run = latest_run_in_statuses(region, (AllocationRun.Status.COMPLETED,))
    if not latest_completed_run:
        return None

    if not run_has_current_assignments(latest_completed_run):
        return None

    return latest_completed_run
