"""Allocation HTTP views: authorization, request parsing, domain calls, response mapping."""

import traceback

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from ..contracts.requests import parse_allocation_run_request
from ..db_connection import refresh_db_connection
from ..domains.allocation.config import (
    _CONDITIONS_STORE,
    DEFAULT_CONDITIONS,
    normalize_allocation_constraints,
    sanitize_allocation_conditions,
)
from ..domains.allocation.jobs import pack_job_parameters
from ..domains.allocation.queries import (
    ACTIVE_RUN_STATUSES,
    START_BLOCKING_RUN_STATUSES,
    current_run_for_region,
    latest_run_for_region,
    latest_run_in_statuses,
    retry_population_queryset,
)
from ..domains.allocation.results import (
    build_allocation_results,
    build_assignment_rows_for_run,
)
from ..domains.allocation.runs import (
    AllocationAlreadyRunning,
    RunNotDeletable,
    create_run_for_region,
    delete_completed_run_results,
    execute_retry_allocation,
    execute_sync_allocation,
    mark_run_failed,
    original_solver_population_ids,
    parse_max_solver_seconds,
    request_run_stop,
)
from ..models import AllocationRun
from ..permissions import _resolve_region, resolve_scoped_region
from ..serializers import AllocationRunSerializer, RegionSerializer
from ..contracts.errors import error_response, failure_response


def _resolve_run_request_region(request, region_value):
    """
    Region a boss / central admin asked to run allocation for
    (AllocationRunRequest.region_value). Returns (region, None) or
    (None, error_response).
    """
    if not region_value:
        if request.user.is_central_admin:
            return None, error_response(status.HTTP_400_BAD_REQUEST, 'נדרש לבחור אזור')
        if not request.user.region:
            return None, error_response(status.HTTP_400_BAD_REQUEST, 'המשתמש אינו משויך לאזור')
        region = request.user.region
    else:
        region = _resolve_region(region_value)
        if not region:
            return None, error_response(status.HTTP_404_NOT_FOUND, 'אזור לא נמצא')

    if not request.user.is_central_admin:
        if not request.user.region or request.user.region != region:
            return None, error_response(status.HTTP_403_FORBIDDEN, 'אין הרשאה להריץ שיבוץ עבור אזור זה')

    return region, None


def _already_running_response(active_run, region, include_run_id=False):
    payload = {
        'success': False,
        'error': 'כבר רץ שיבוץ עבור אזור זה. נא להמתין לסיום ההרצה הקיימת.',
        'error_code': 'ALLOCATION_ALREADY_RUNNING',
        'region': region.id,
    }
    if include_run_id:
        payload['run_id'] = active_run.id
    payload['run'] = AllocationRunSerializer(active_run).data
    return Response(payload, status=status.HTTP_409_CONFLICT)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def run_allocation(request):
    refresh_db_connection()

    # The request body is not echoed to stdout: it names the region, the
    # solver parameters and the operator, and belongs in the run row, not
    # in process output.
    if not (request.user.is_boss or request.user.is_central_admin):
        return error_response(status.HTTP_403_FORBIDDEN, 'רק מנהל אזור או מנהל מרכזי יכולים להריץ שיבוץ')

    run_request = parse_allocation_run_request(request.data)
    region, error = _resolve_run_request_region(request, run_request.region_value)
    if error:
        return error

    constraints_config = normalize_allocation_constraints(run_request.constraints)
    allocation_run = None

    try:
        # Duplicate-run protection: the Region row lock inside
        # create_run_for_region prevents two requests from creating
        # RUNNING allocation jobs for the same region at the same time.
        try:
            allocation_run = create_run_for_region(
                region, request.user,
                status=AllocationRun.Status.RUNNING,
                blocking_statuses=(AllocationRun.Status.RUNNING,),
            )
        except AllocationAlreadyRunning as conflict:
            return _already_running_response(conflict.active_run, region)

        print(
            f">>> ALLOCATION_RUN_CREATED run_id={allocation_run.id} region={region.id} user={request.user.email}",
            flush=True,
        )

        outcome = execute_sync_allocation(
            allocation_run, region,
            constraints_config=constraints_config,
            include_assigned=run_request.include_assigned,
            allocation_scope=run_request.allocation_scope,
        )

        if outcome.kind == 'no_students':
            return Response({
                'success': True,
                'message': 'לא נמצאו סטודנטים זמינים לשיבוץ באזור זה',
                'result': {
                    'students_total_in_region': outcome.students_total_in_region,
                    'students_available_for_allocation': 0,
                    'students_processed': 0,
                    'successful_assignments': 0,
                    'roommate_matches': 0,
                    'mutual_roommate_matches': 0,
                    'one_sided_roommate_matches': 0,
                    'conflicts': 0,
                    'solver_status': 'NO_STUDENTS',
                    'objective_value': None,
                    'wall_time': None,
                    'warnings': [],
                    'students_with_no_feasible_beds': [],
                    'anier_building_179_diagnostics': outcome.anier_building_179_diagnostics,
                    'population_summary': outcome.population_summary,
                    'assignments': [],
                    'run': AllocationRunSerializer(allocation_run).data
                }
            }, status=status.HTTP_200_OK)

        if outcome.kind == 'no_rooms':
            return failure_response(status.HTTP_400_BAD_REQUEST, 'לא נמצאו חדרים פעילים באזור זה')

        result = outcome.result
        return Response({
            'success': True,
            'message': 'השיבוץ הושלם בהצלחה',
            'result': {
                'students_total_in_region': outcome.students_total_in_region,
                'students_available_for_allocation': outcome.students_count,
                'students_processed': result.get('students_processed', outcome.students_count),
                'successful_assignments': result.get('successful_assignments', 0),
                'roommate_matches': outcome.roommate_matches,
                'mutual_roommate_matches': result.get('mutual_roommate_matches', 0),
                'one_sided_roommate_matches': result.get('one_sided_roommate_matches', 0),
                'conflicts': result.get('conflicts', 0),
                'solver_status': result.get('solver_status'),
                'objective_value': result.get('objective_value'),
                'wall_time': result.get('wall_time'),
                'warnings': result.get('warnings', []),
                'students_with_no_feasible_beds': result.get('students_with_no_feasible_beds', []),
                'anier_building_179_diagnostics': outcome.anier_building_179_diagnostics,
                'population_summary': outcome.population_summary,
                'assignments': outcome.assignment_rows,
                'run': AllocationRunSerializer(allocation_run).data
            }
        }, status=status.HTTP_200_OK)

    except Exception as e:
        traceback.print_exc()

        if allocation_run is not None:
            try:
                mark_run_failed(allocation_run, str(e))
            except Exception:
                traceback.print_exc()

        return failure_response(status.HTTP_500_INTERNAL_SERVER_ERROR, f'שגיאה בהרצת השיבוץ: {str(e)}', error_type=e.__class__.__name__, traceback=traceback.format_exc())


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def retry_unassigned_allocation_run(request, run_id):
    """
    "נסה לשבץ שוב את הסטודנטים שלא שובצו" — a narrowly-scoped, explicit
    retry: run the solver only for the specific students that the chosen
    completed run sent to the solver and left unassigned, against
    whatever inventory is currently available. This is NOT a general
    "run allocation again" — it never touches students already
    successfully assigned (by this run or any other), and it refuses to
    run at all if it cannot identify the exact original population.

    See api.domains.allocation.queries.retry_population_queryset and
    api.domains.allocation.runs.execute_retry_allocation for the
    population and persistence rules this endpoint enforces.
    """
    if not (request.user.is_boss or request.user.is_central_admin):
        return error_response(status.HTTP_403_FORBIDDEN, 'רק מנהל אזור או מנהל מרכזי יכולים להריץ שיבוץ')

    try:
        original_run = AllocationRun.objects.select_related('region').get(pk=run_id)
    except AllocationRun.DoesNotExist:
        return error_response(status.HTTP_404_NOT_FOUND, 'הרצה לא נמצאה')

    region = original_run.region

    if not request.user.is_central_admin:
        if not request.user.region or request.user.region != region:
            return error_response(status.HTTP_403_FORBIDDEN, 'אין הרשאה להריץ שיבוץ עבור אזור זה')

    if original_run.status != AllocationRun.Status.COMPLETED:
        return failure_response(status.HTTP_400_BAD_REQUEST, 'ניתן לנסות שוב רק הרצה שהושלמה', error_code='RUN_NOT_COMPLETED')

    original_student_ids = original_solver_population_ids(original_run)

    if not original_student_ids:
        return failure_response(status.HTTP_400_BAD_REQUEST, 'להרצה זו אין נתוני אוכלוסייה שמורים (הרצה ישנה מלפני תכונה זו) — '
                'לא ניתן לנסות שוב באופן בטוח בלי לדעת בדיוק אילו סטודנטים נשלחו '
                'לשיבוץ במקור. יש להריץ שיבוץ מלא חדש במקום.', error_code='MISSING_ORIGINAL_POPULATION')

    retry_students_qs = retry_population_queryset(original_student_ids)
    retry_student_ids = list(retry_students_qs.values_list('id', flat=True))

    if not retry_student_ids:
        return Response({
            'success': True,
            'message': 'כל הסטודנטים מהרצה זו כבר משובצים — אין מה לנסות שוב',
            'result': {
                'retry_of_run_id': original_run.id,
                'retried_student_count': 0,
                'successful_assignments': 0,
                'conflicts': 0,
                'assignments': [],
            },
        }, status=status.HTTP_200_OK)

    try:
        retry_run = create_run_for_region(
            region, request.user,
            status=AllocationRun.Status.RUNNING,
            blocking_statuses=(AllocationRun.Status.RUNNING,),
        )
    except AllocationAlreadyRunning as conflict:
        return _already_running_response(conflict.active_run, region)

    try:
        outcome = execute_retry_allocation(
            original_run, retry_run, retry_students_qs, retry_student_ids,
            constraints_config=normalize_allocation_constraints(
                parse_allocation_run_request(request.data).constraints
            ),
        )
        result = outcome.result

        return Response({
            'success': True,
            'message': 'ניסיון השיבוץ החוזר הושלם',
            'result': {
                'retry_of_run_id': original_run.id,
                'retried_student_count': len(retry_student_ids),
                'students_processed': result.get('students_processed', len(retry_student_ids)),
                'successful_assignments': result.get('successful_assignments', 0),
                'roommate_matches': outcome.roommate_matches,
                'conflicts': result.get('conflicts', 0),
                'solver_status': result.get('solver_status'),
                'warnings': result.get('warnings', []),
                'students_with_no_feasible_beds': result.get('students_with_no_feasible_beds', []),
                'anier_building_179_diagnostics': result.get('anier_building_179_diagnostics', {}),
                'population_summary': outcome.population_summary,
                'assignments': outcome.assignment_rows,
                'run': AllocationRunSerializer(retry_run).data,
            },
        }, status=status.HTTP_200_OK)

    except Exception as e:
        traceback.print_exc()
        try:
            mark_run_failed(retry_run, str(e))
        except Exception:
            traceback.print_exc()

        return failure_response(status.HTTP_500_INTERNAL_SERVER_ERROR, f'שגיאה בניסיון השיבוץ החוזר: {str(e)}', error_type=e.__class__.__name__)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def start_allocation_run(request):
    """
    Async allocation start.  Creates a durable QUEUED AllocationRun carrying
    the solver parameters (202) and returns immediately; the dedicated
    allocation worker (manage.py allocation_worker) claims and executes it,
    independently of this process.  The caller polls
    GET /api/allocation/runs/<run_id>/ for status and results.
    """
    refresh_db_connection()

    if not (request.user.is_boss or request.user.is_central_admin):
        return error_response(status.HTTP_403_FORBIDDEN, 'רק מנהל אזור או מנהל מרכזי יכולים להריץ שיבוץ')

    run_request = parse_allocation_run_request(request.data)
    region, error = _resolve_run_request_region(request, run_request.region_value)
    if error:
        return error

    constraints_config = normalize_allocation_constraints(run_request.constraints)
    include_assigned = run_request.include_assigned
    allocation_scope = run_request.allocation_scope

    try:
        max_solver_seconds = parse_max_solver_seconds(run_request.max_solver_seconds)
    except ValueError as invalid:
        return error_response(status.HTTP_400_BAD_REQUEST, str(invalid))

    try:
        allocation_run = create_run_for_region(
            region, request.user,
            status=AllocationRun.Status.QUEUED,
            blocking_statuses=START_BLOCKING_RUN_STATUSES,
            max_search_seconds=int(max_solver_seconds),
            job_parameters=pack_job_parameters(
                constraints_config=constraints_config,
                include_assigned=include_assigned,
                allocation_scope=allocation_scope,
                max_seconds=max_solver_seconds,
            ),
        )
    except AllocationAlreadyRunning as conflict:
        return _already_running_response(conflict.active_run, region, include_run_id=True)

    print(
        f">>> ASYNC_ALLOCATION_START run_id={allocation_run.id} "
        f"region={region.id} user={request.user.email} "
        f"max_solver_seconds={max_solver_seconds}",
        flush=True,
    )

    return Response({
        'success': True,
        'message': 'השיבוץ החל. עקבו אחר ההתקדמות.',
        'run_id': allocation_run.id,
        'run': AllocationRunSerializer(allocation_run).data,
    }, status=status.HTTP_202_ACCEPTED)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_allocation_run_detail(request, run_id):
    """
    Return the current status of an allocation run plus assignment rows
    once the run is COMPLETED.
    """
    try:
        run = AllocationRun.objects.select_related('region', 'run_by').get(pk=run_id)
    except AllocationRun.DoesNotExist:
        return error_response(status.HTTP_404_NOT_FOUND, 'הרצה לא נמצאה')

    if not request.user.is_central_admin:
        if request.user.region != run.region:
            return error_response(status.HTTP_403_FORBIDDEN, 'אין גישה להרצה זו')

    run_data = AllocationRunSerializer(run).data

    assignment_rows = []
    if run.status == AllocationRun.Status.COMPLETED:
        refresh_db_connection()
        assignment_rows = build_assignment_rows_for_run(run)

    # Diagnostics (warnings, Building-179/ANIR counters) are persisted on
    # AllocationRun.diagnostics by both the sync and async allocation
    # entry points, so this survives worker restarts and is visible
    # across workers — unlike an in-memory store. Falls back to an
    # empty/zeroed structure for a run that predates this field (JSONField
    # default=dict already covers that at the DB level) or is still in
    # progress.
    from ..domains.allocation.gateway import EMPTY_ANIER_BUILDING_179_DIAGNOSTICS
    run_diagnostics = run.diagnostics or {}

    return Response({
        'run': run_data,
        'assignments': assignment_rows,
        'successful_assignments': run.successful_assignments,
        'roommate_matches': run.roommate_matches,
        'conflicts': run.conflicts,
        'warnings': run_diagnostics.get('warnings', []),
        'anier_building_179_diagnostics': run_diagnostics.get(
            'anier_building_179_diagnostics',
            dict(EMPTY_ANIER_BUILDING_179_DIAGNOSTICS),
        ),
        # The imported/excluded breakdown behind "processed = assigned +
        # unassigned" — authoritative for THIS run specifically, as
        # persisted at solve time (see _population_summary_for_region).
        'population_summary': run_diagnostics.get('population_summary', {}),
        # solver_status/optimality_proven are already computed by the
        # solver for every run (see _run_diagnostics_payload); surfacing
        # them here lets the frontend show "stopped early, not proven
        # optimal" for a Stop & Save result. stopped_early_by_user is only
        # ever set True by the Stop & Save finalize branch in
        # _execute_allocation_background.
        'solver_status': run_diagnostics.get('solver_status'),
        'optimality_proven': bool(run_diagnostics.get('optimality_proven', False)),
        'stopped_early_by_user': bool(run_diagnostics.get('stopped_early_by_user', False)),
    }, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_allocation_run_preview(request, run_id):
    """
    Return the current best-feasible-solution-so-far snapshot for a
    RUNNING allocation run, WITHOUT touching the solver or the DB
    assignment tables - "צפה בתוצאה הנוכחית" (View Current Result).

    Deliberately a separate, heavier endpoint from
    get_allocation_run_detail: normal 3s status polling stays
    lightweight (that endpoint never returns assignment rows for a
    non-COMPLETED run), and this richer preview is only fetched when the
    operator explicitly asks to see it.

    Reads AllocationRun.live_snapshot, the persisted copy of the solver's
    best solution so far (mirrored by the solve itself - see
    _LiveSolutionCallback / _run_stop_watcher in allocation/solver.py).
    The solve runs in the dedicated allocation worker process, so this
    persisted snapshot is the only cross-process source of truth; the
    solver's in-process live_registry is never consulted here. Returns
    {'available': False} - not 404/500 - when no feasible solution has
    been found yet; that is an expected, normal state while a run is still
    searching for its first solution.
    """
    try:
        run = AllocationRun.objects.select_related('region').get(pk=run_id)
    except AllocationRun.DoesNotExist:
        return error_response(status.HTTP_404_NOT_FOUND, 'הרצה לא נמצאה')

    if not request.user.is_central_admin:
        if request.user.region != run.region:
            return error_response(status.HTTP_403_FORBIDDEN, 'אין גישה להרצה זו')

    snapshot = run.live_snapshot

    if not snapshot:
        return Response({'available': False, 'snapshot': None}, status=status.HTTP_200_OK)

    return Response({'available': True, 'snapshot': snapshot}, status=status.HTTP_200_OK)


def _user_may_stop_run(user):
    """Region check evaluated under the run's row lock by request_run_stop."""
    def authorize(run):
        return user.is_central_admin or user.region == run.region
    return authorize


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def stop_allocation_run(request, run_id):
    """
    Request cancellation (discard) of an in-progress allocation run -
    the "בטל הרצה" action. Distinct from stop_and_save_allocation_run
    ("עצור ושמור תוצאה"), which keeps the best feasible result found so
    far instead of discarding it. Idempotent: safe to call more than
    once.
    """
    if not (request.user.is_boss or request.user.is_central_admin):
        return error_response(status.HTTP_403_FORBIDDEN, 'אין הרשאה לעצור שיבוץ')

    try:
        outcome = request_run_stop(
            run_id, AllocationRun.Status.CANCELLATION_REQUESTED,
            authorize=_user_may_stop_run(request.user),
        )
    except AllocationRun.DoesNotExist:
        return error_response(status.HTTP_404_NOT_FOUND, 'הרצה לא נמצאה')

    if outcome.outcome == 'forbidden':
        return error_response(status.HTTP_403_FORBIDDEN, 'אין הרשאה לעצור הרצה זו')

    if outcome.outcome == 'terminal':
        return error_response(status.HTTP_409_CONFLICT, 'הרצה זו כבר הסתיימה', status=outcome.run_status)

    if outcome.outcome == 'already_requested':
        return Response({
            'message': 'בקשת עצירה כבר נשלחה',
            'run_id': run_id,
            'status': outcome.run_status,
        }, status=status.HTTP_200_OK)

    if outcome.outcome == 'conflicting_request':
        return error_response(status.HTTP_409_CONFLICT, 'כבר התבקשה עצירה עם שמירת תוצאה עבור הרצה זו', run_id=run_id, status=outcome.run_status)

    return Response({
        'message': 'בקשת עצירה נשלחה. השיבוץ ייעצר בהקדם והנתונים החלקיים יימחקו.',
        'run_id': run_id,
    }, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def stop_and_save_allocation_run(request, run_id):
    """
    Request an early stop that KEEPS the best feasible result found so
    far - the "עצור ושמור תוצאה" action. Distinct from
    stop_allocation_run ("בטל הרצה"), which discards any partial work.

    Interrupts the running CpSolver via StopSearch() (same-process fast
    path, plus the always-running _run_stop_watcher inside the solve
    itself regardless of process - see allocation/solver.py), then lets
    the existing best-effort persistence logic in
    run_improved_ortools_allocation decide the outcome exactly as it
    always has; see _execute_allocation_background's post-solve branch for
    how the run is finalized either way. Idempotent: safe to call more
    than once.
    """
    if not (request.user.is_boss or request.user.is_central_admin):
        return error_response(status.HTTP_403_FORBIDDEN, 'אין הרשאה לעצור שיבוץ')

    try:
        outcome = request_run_stop(
            run_id, AllocationRun.Status.STOP_AND_SAVE_REQUESTED,
            authorize=_user_may_stop_run(request.user),
        )
    except AllocationRun.DoesNotExist:
        return error_response(status.HTTP_404_NOT_FOUND, 'הרצה לא נמצאה')

    if outcome.outcome == 'forbidden':
        return error_response(status.HTTP_403_FORBIDDEN, 'אין הרשאה לעצור הרצה זו')

    if outcome.outcome == 'terminal':
        return error_response(status.HTTP_409_CONFLICT, 'הרצה זו כבר הסתיימה', status=outcome.run_status)

    if outcome.outcome == 'already_requested':
        return Response({
            'message': 'בקשת עצירה ושמירה כבר נשלחה',
            'run_id': run_id,
            'status': outcome.run_status,
        }, status=status.HTTP_200_OK)

    if outcome.outcome == 'conflicting_request':
        return error_response(status.HTTP_409_CONFLICT, 'כבר התבקש ביטול הרצה זו', run_id=run_id, status=outcome.run_status)

    return Response({
        'message': 'בקשת עצירה עם שמירת תוצאה נשלחה. הפתרון הטוב ביותר שנמצא יישמר.',
        'run_id': run_id,
    }, status=status.HTTP_200_OK)


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def delete_allocation_run(request, run_id):
    """
    Delete the draft results of a COMPLETED (not APPROVED) allocation run.
    Cancels all BedAssignments created by that run and restores students.
    Returns 409 if the run is already approved.
    """
    if not (request.user.is_boss or request.user.is_central_admin):
        return error_response(status.HTTP_403_FORBIDDEN, 'אין הרשאה למחוק תוצאות שיבוץ')

    try:
        run = AllocationRun.objects.select_related('region').get(pk=run_id)
    except AllocationRun.DoesNotExist:
        return error_response(status.HTTP_404_NOT_FOUND, 'הרצה לא נמצאה')

    if not request.user.is_central_admin:
        if request.user.region != run.region:
            return error_response(status.HTTP_403_FORBIDDEN, 'אין הרשאה למחוק הרצה זו')

    try:
        deleted_count = delete_completed_run_results(run)
    except RunNotDeletable as blocked:
        if blocked.reason == 'approved':
            return error_response(status.HTTP_409_CONFLICT, 'לא ניתן למחוק הקצאה שאושרה סופית')
        return error_response(status.HTTP_409_CONFLICT, f'לא ניתן למחוק הרצה עם סטטוס: {blocked.run_status}', status=blocked.run_status)

    return Response({
        'message': 'תוצאות השיבוץ נמחקו בהצלחה',
        'run_id': run_id,
        'deleted_assignments': deleted_count,
    }, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_active_allocation_run(request):
    """
    Return an active allocation run, or the latest completed run
    only when its active assignments still exist.
    """
    # G3-08: centralized region resolution - a region_boss/employee can
    # never read another region's active run by supplying ?region=, they
    # get a clean 403 instead.
    region_value = request.query_params.get('region')
    region, error = resolve_scoped_region(request.user, region_value)
    if error:
        return error

    if region is None:
        # central_admin with no region selected - "active run" has no
        # single-region meaning to aggregate, matching prior behavior.
        return Response({'run': None}, status=status.HTTP_200_OK)

    run = current_run_for_region(region)

    return Response(
        {'run': AllocationRunSerializer(run).data if run else None},
        status=status.HTTP_200_OK,
    )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def allocation_history(request):
    queryset = AllocationRun.objects.all()

    if not request.user.is_central_admin:
        queryset = queryset.filter(region=request.user.region)

    serializer = AllocationRunSerializer(queryset[:20], many=True)
    return Response({'runs': serializer.data})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def allocation_results(request):
    """
    Return the current allocation results for the permitted region:

    1. Assigned students
    2. Unassigned allocatable students
    3. Available real Bed records

    The endpoint keeps the existing permission and region-scoping rules.
    """
    region_value = request.query_params.get('region') or None

    # G3-03: centralized helper - region_boss/employee alike are hard-locked
    # to their own region, a mismatched ?region= is a clean 403, never a
    # silent cross-region peek.
    region, error = resolve_scoped_region(request.user, region_value)
    if error:
        return error

    results = build_allocation_results(region)

    return Response({
        'counts': {
            'assigned': len(results['assignments']),
            'unassigned': len(results['unassigned_students']),
            'available_beds': len(results['available_beds']),
        },
        'count': len(results['assignments']),

        'assignments': results['assignments'],
        'unassigned_students': results['unassigned_students'],
        'available_beds': results['available_beds'],
        'unassigned_analysis': results['unassigned_analysis'],
    }, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def allocation_status(request):
    """
    Returns the current allocation status for the user's region:
    the most recent run (any status) plus active counts.
    """
    user = request.user
    region_value = request.query_params.get('region')

    if region_value:
        region = _resolve_region(region_value)
        if not region:
            return error_response(status.HTTP_404_NOT_FOUND, 'אזור לא נמצא')
    elif user.is_central_admin:
        return Response({
            'status': 'not_started',
            'run': None,
            'region': None,
        }, status=status.HTTP_200_OK)
    elif user.region:
        region = user.region
    else:
        return error_response(status.HTTP_400_BAD_REQUEST, 'המשתמש אינו משויך לאזור')

    active_run = latest_run_in_statuses(region, ACTIVE_RUN_STATUSES)

    if active_run:
        return Response({
            'status': active_run.status,
            'run': AllocationRunSerializer(active_run).data,
            'region': RegionSerializer(region).data,
        }, status=status.HTTP_200_OK)

    latest_run = latest_run_for_region(region)

    if not latest_run:
        return Response({
            'status': 'not_started',
            'run': None,
            'region': RegionSerializer(region).data,
        }, status=status.HTTP_200_OK)

    return Response({
        'status': latest_run.status,
        'run': AllocationRunSerializer(latest_run).data,
        'region': RegionSerializer(region).data,
    }, status=status.HTTP_200_OK)


@api_view(['GET', 'PUT'])
@permission_classes([IsAuthenticated])
def allocation_conditions(request):
    """
    Legacy GET/PUT handler for reading and updating per-region allocation
    conditions in the in-memory conditions store.

    This view is not currently registered in backend/api/urls.py and is
    therefore not reachable through the operational API. The frontend
    service still contains getConditions()/updateConditions() helpers that
    reference /api/allocation/conditions/, but that route is not active.
    """
    user = request.user

    region_value = (
        request.query_params.get('region')
        or (request.data.get('region') if request.method == 'PUT' else None)
    )

    if region_value:
        region = _resolve_region(region_value)
        if not region:
            return error_response(status.HTTP_404_NOT_FOUND, 'אזור לא נמצא')
        region_key = str(region.id)
    elif not user.is_central_admin and user.region:
        region = user.region
        region_key = str(region.id)
    else:
        region = None
        region_key = '__global__'

    if request.method == 'GET':
        saved = _CONDITIONS_STORE.get(region_key, DEFAULT_CONDITIONS.copy())
        return Response({
            'region': RegionSerializer(region).data if region else None,
            'conditions': saved,
        }, status=status.HTTP_200_OK)

    # PUT
    if not (user.is_boss or user.is_central_admin):
        return error_response(status.HTTP_403_FORBIDDEN, 'אין הרשאה לשנות תנאי שיבוץ')

    incoming = request.data.get('conditions')
    if not isinstance(incoming, dict):
        return error_response(status.HTTP_400_BAD_REQUEST, 'conditions must be a JSON object')

    validated = sanitize_allocation_conditions(incoming)
    _CONDITIONS_STORE[region_key] = validated

    return Response({
        'message': 'Conditions updated successfully',
        'region': RegionSerializer(region).data if region else None,
        'conditions': validated,
    }, status=status.HTTP_200_OK)
