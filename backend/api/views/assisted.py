"""Assisted Allocation workbench HTTP views."""

from django.core.exceptions import ValidationError
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from ..domains.assisted.queries import (
    assisted_student_row,
    build_assisted_queue,
    build_recommendations,
    build_student_detail,
    filter_queue_students,
    pending_region_transfer,
)
from ..domains.assisted.services import (
    blocking_violations,
    manual_override_violations,
    override_check,
    record_manual_assignment,
    record_manual_override,
)
from ..contracts.requests import parse_override_request
from ..domains.placement.services import _user_can_edit_room
from ..models import Bed, Student
from ..permissions import resolve_scoped_region
from ..serializers import StudentRequestSerializer
from ..contracts.errors import error_response

_ALREADY_ASSIGNED_ERROR = (
    'הסטודנט/ית כבר משובץ/ת — לא ניתן לבצע שיבוץ ידני נוסף. לשינוי שיבוץ קיים יש להשתמש בבקשת העברה.'
)
_TRANSFER_PENDING_ERROR = (
    'לסטודנט/ית יש בקשת העברה לאזור אחר הממתינה לאישור — לא ניתן לבצע שיבוץ ידני מקומי. '
    'יש לבטל את בקשת ההעברה תחילה אם השיבוץ המקומי נדרש.'
)


def _user_can_access_student_region(user, student):
    """
    Mirrors the region-scoping already used for room-assignment actions
    (_user_can_edit_room), applied to a Student via their accepted dorm
    type's region rather than a Room. A student with no resolvable region
    can only be acted on by a central admin - a regional user can never
    claim jurisdiction over a student the system cannot place in their
    region.
    """
    if not user or not user.is_authenticated:
        return False
    if user.is_central_admin:
        return True
    if not user.region_id:
        return False
    dorm_type = student.accepted_dorm_type
    if not dorm_type or not dorm_type.region_id:
        return False
    return dorm_type.region_id == user.region_id


def _get_student_or_error(user, pk, *select_related):
    """Student lookup plus the caller's region authorization: (student, None) or (None, Response)."""
    try:
        student = Student.objects.select_related(*select_related).get(pk=pk)
    except Student.DoesNotExist:
        return None, error_response(status.HTTP_404_NOT_FOUND, 'הסטודנט לא נמצא')

    if not _user_can_access_student_region(user, student):
        return None, error_response(status.HTTP_403_FORBIDDEN, 'אין הרשאה לאזור זה')

    return student, None


def _get_placement_bed_or_error(user, bed_id, *select_related):
    """Bed lookup plus the caller's room authorization: (bed, None) or (None, Response)."""
    if not bed_id:
        return None, error_response(status.HTTP_400_BAD_REQUEST, 'יש לבחור מיטה')

    try:
        bed = Bed.objects.select_related(*select_related).get(pk=bed_id)
    except Bed.DoesNotExist:
        return None, error_response(status.HTTP_404_NOT_FOUND, 'המיטה לא נמצאה')

    if not _user_can_edit_room(user, bed.room):
        return None, error_response(status.HTTP_403_FORBIDDEN, 'אין הרשאה לחדר זה')

    return bed, None


def _local_placement_blocker(student):
    """
    Why a manual local placement must not proceed for this student, or
    None. A student the workbench already placed must not be silently
    moved again (a correction belongs to the transfer workflow); a
    student mid-transfer to another region must not be placed locally
    (Tab A requests a transfer, Tab B assigns them locally). Both are
    enforced here regardless of what a stale tab or direct API call
    shows; the unique_active_assignment_per_student DB constraint remains
    the backstop against a true concurrent race.
    """
    if student.is_assigned:
        return error_response(status.HTTP_400_BAD_REQUEST, _ALREADY_ASSIGNED_ERROR)
    if pending_region_transfer(student) is not None:
        return error_response(status.HTTP_400_BAD_REQUEST, _TRANSFER_PENDING_ERROR)
    return None


def _placement_error_response(exc):
    if isinstance(exc, ValidationError):
        message = '; '.join(exc.messages) if hasattr(exc, 'messages') else str(exc)
        return error_response(status.HTTP_400_BAD_REQUEST, message)
    return error_response(status.HTTP_400_BAD_REQUEST, str(exc))


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def assisted_allocation_queue(request):
    user = request.user
    region_value = request.query_params.get('region')

    # G3-03: centralized region resolution (see resolve_scoped_region) -
    # region_boss/employee can never pull another region's assisted
    # allocation queue via ?region=.
    region, error = resolve_scoped_region(user, region_value)
    if error:
        return error

    queue = build_assisted_queue(region)

    tab = request.query_params.get('tab', 'needs_placement')
    students, group_of = queue.tab(tab)

    students = filter_queue_students(
        students,
        gender=request.query_params.get('gender'),
        dorm_type_id=request.query_params.get('dorm_type'),
        search=request.query_params.get('search'),
    )

    rows = [
        assisted_student_row(
            s,
            group=group_of.get(s.id, tab),
            is_transfer_requested=s.id in queue.transfer_requested_ids,
        )
        for s in students
    ]

    return Response({
        'counts': queue.counts,
        'students': rows,
        'region_id': region.id if region else None,
        'region_name': region.name if region else None,
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def assisted_allocation_student_detail(request, pk):
    student, error = _get_student_or_error(
        request.user, pk, 'accepted_dorm_type', 'accepted_dorm_type__region', 'assigned_room',
    )
    if error:
        return error

    detail = build_student_detail(student)
    pending_transfer = detail['pending_transfer_request']

    return Response({
        **detail,
        # The SAME StudentRequest row TransfersPage shows/approves/rejects -
        # serialized with the normal StudentRequestSerializer (not a
        # hand-rolled shape) so this can never drift from what that page
        # displays. None when there is no pending region_transfer.
        'pending_transfer_request': (
            StudentRequestSerializer(pending_transfer).data if pending_transfer else None
        ),
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def assisted_allocation_recommendations(request, pk):
    student, error = _get_student_or_error(
        request.user, pk, 'accepted_dorm_type', 'accepted_dorm_type__region',
    )
    if error:
        return error

    return Response(build_recommendations(request.user, student))


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def assisted_allocation_override_check(request, pk):
    student, error = _get_student_or_error(request.user, pk)
    if error:
        return error

    bed, error = _get_placement_bed_or_error(
        request.user, request.query_params.get('bed_id'),
        'room', 'room__apartment', 'room__apartment__building',
        'room__apartment__building__dorm_type', 'room__apartment__building__dorm_type__region',
    )
    if error:
        return error

    return Response(override_check(student, bed.room))


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def assisted_allocation_assign(request, pk):
    student, error = _get_student_or_error(request.user, pk)
    if error:
        return error

    blocker = _local_placement_blocker(student)
    if blocker:
        return blocker

    bed, error = _get_placement_bed_or_error(
        request.user, request.data.get('bed_id'),
        'room', 'room__apartment', 'room__apartment__building',
    )
    if error:
        return error

    try:
        assignment = record_manual_assignment(student, bed.room, bed, request.user)
    except (ValueError, ValidationError) as e:
        return _placement_error_response(e)

    return Response({'message': 'הסטודנט שובץ בהצלחה', 'assignment_id': assignment.id})


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def assisted_allocation_override(request, pk):
    # G3-11: overriding deliberately waives a hard placement/business rule -
    # unlike the normal assign() action (open to any in-region employee),
    # this is an elevated administrative action and requires region_boss or
    # central_admin.
    if not request.user.is_boss:
        return error_response(status.HTTP_403_FORBIDDEN, 'רק מנהל אזור או מנהל מרכזי יכול לבצע שיבוץ בחריגה')

    student, error = _get_student_or_error(request.user, pk)
    if error:
        return error

    blocker = _local_placement_blocker(student)
    if blocker:
        return blocker

    bed_id, note = parse_override_request(request.data)
    if not bed_id:
        return error_response(status.HTTP_400_BAD_REQUEST, 'יש לבחור מיטה')
    if not note:
        return error_response(status.HTTP_400_BAD_REQUEST, 'יש להזין סיבה לחריגה')

    bed, error = _get_placement_bed_or_error(
        request.user, bed_id,
        'room', 'room__apartment', 'room__apartment__building',
    )
    if error:
        return error

    room = bed.room

    # Recomputed server-side - a client-sent violation list is never trusted.
    violations = manual_override_violations(student, room)

    # Structural violations can never be overridden - a note does not make
    # a fundamentally invalid placement valid - regardless of what the
    # client showed.
    blocking = blocking_violations(violations)
    if blocking:
        return error_response(status.HTTP_400_BAD_REQUEST, 'לא ניתן לבצע שיבוץ בחריגה - קיימת חסימה מוחלטת שאינה ניתנת לעקיפה: '
                     + '; '.join(v['label'] for v in blocking), violations=violations)

    try:
        assignment = record_manual_override(
            student, room, bed, request.user, violations=violations, note=note,
        )
    except (ValueError, ValidationError) as e:
        return _placement_error_response(e)

    return Response({
        'message': 'השיבוץ בוצע בחריגה',
        'assignment_id': assignment.id,
        'overridden_rules': violations,
    })
