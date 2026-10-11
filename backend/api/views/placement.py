from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from ..domains.placement.services import (
    _execute_swap,
    _user_can_edit_room,
    assign_student_to_room,
    unassign_student,
)
from ..contracts.requests import room_reference, student_reference, swap_pair
from ..models import BedAssignment, Room, Student
from ..contracts.errors import error_response


def _student_by_reference(value):
    """Prefer the database PK; fall back to the university/student number."""
    try:
        return Student.objects.get(pk=value)
    except (Student.DoesNotExist, ValueError, TypeError):
        return Student.objects.get(student_id=value)


def _get_student_from_request(request, key='student_id'):
    return _student_by_reference(student_reference(request.data, key))


def _get_room_from_request(request, key='room_id'):
    value = room_reference(request.data, key)
    return Room.objects.select_related(
        'apartment',
        'apartment__building',
        'apartment__building__dorm_type',
        'apartment__building__dorm_type__region',
    ).get(pk=value)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def assign_student_room(request):
    """Assign an unassigned student to a room. Backend chooses the first free bed."""
    try:
        student = _get_student_from_request(request)
        room = _get_room_from_request(request)

        if not _user_can_edit_room(request.user, room):
            return error_response(status.HTTP_403_FORBIDDEN, 'אין הרשאה לערוך חדר באזור זה')

        assignment = assign_student_to_room(
            student=student,
            room=room,
            assigned_by=request.user,
            assignment_type=BedAssignment.AssignmentType.MANUAL,
            bed_id=request.data.get('bed_id'),
        )

        return Response({
            'success': True,
            'message': 'Student assigned successfully',
            'assignment_id': assignment.id,
            'student_id': student.id,
            'room_id': room.id,
            'bed_id': assignment.bed_id,
        }, status=status.HTTP_200_OK)

    except (Student.DoesNotExist, Room.DoesNotExist):
        return error_response(status.HTTP_404_NOT_FOUND, 'Student or room not found')
    except Exception as e:
        return error_response(status.HTTP_400_BAD_REQUEST, str(e))


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def move_student_room(request):
    """Move a student to another room. This ends the old active assignment and creates a new one."""
    try:
        student = _get_student_from_request(request)
        room = _get_room_from_request(request)

        if not _user_can_edit_room(request.user, room):
            return error_response(status.HTTP_403_FORBIDDEN, 'אין הרשאה לערוך חדר באזור זה')

        current_room = student.assigned_room
        if current_room and not request.user.is_central_admin:
            current_room = Room.objects.select_related(
                'apartment__building__dorm_type__region'
            ).get(pk=current_room.pk)
            if not _user_can_edit_room(request.user, current_room):
                return error_response(status.HTTP_403_FORBIDDEN, 'אין הרשאה להעביר סטודנט מאזור זה')

        assignment = assign_student_to_room(
            student=student,
            room=room,
            assigned_by=request.user,
            assignment_type=BedAssignment.AssignmentType.MANUAL,
            bed_id=request.data.get('bed_id'),
        )

        return Response({
            'success': True,
            'message': 'Student moved successfully',
            'assignment_id': assignment.id,
            'student_id': student.id,
            'room_id': room.id,
            'bed_id': assignment.bed_id,
        }, status=status.HTTP_200_OK)

    except (Student.DoesNotExist, Room.DoesNotExist):
        return error_response(status.HTTP_404_NOT_FOUND, 'Student or room not found')
    except Exception as e:
        return error_response(status.HTTP_400_BAD_REQUEST, str(e))


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def unassign_student_room(request):
    """Remove a student's active room/bed assignment."""
    try:
        student = _get_student_from_request(request)
        current_assignment = BedAssignment.objects.select_related(
            'bed__room__apartment__building__dorm_type__region'
        ).filter(
            student=student,
            status=BedAssignment.Status.ACTIVE,
        ).first()

        if not current_assignment:
            student.assigned_room = None
            student.save(update_fields=['assigned_room'])
            return Response({'success': True, 'message': 'Student was already unassigned'}, status=status.HTTP_200_OK)

        room = current_assignment.bed.room
        if not _user_can_edit_room(request.user, room):
            return error_response(status.HTTP_403_FORBIDDEN, 'אין הרשאה לערוך חדר באזור זה')

        unassign_student(student, current_assignment)

        return Response({
            'success': True,
            'message': 'Student unassigned successfully',
            'student_id': student.id,
        }, status=status.HTTP_200_OK)

    except Student.DoesNotExist:
        return error_response(status.HTTP_404_NOT_FOUND, 'Student not found')
    except Exception as e:
        return error_response(status.HTTP_400_BAD_REQUEST, str(e))


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def swap_students_rooms(request):
    """Swap the current rooms of two already-assigned students."""
    try:
        student_a_value, student_b_value = swap_pair(request.data)

        if not student_a_value or not student_b_value:
            return error_response(status.HTTP_400_BAD_REQUEST, 'Missing student_a_id or student_b_id')

        student_a = _student_by_reference(student_a_value)
        student_b = _student_by_reference(student_b_value)

        new_a, new_b, room_a, room_b = _execute_swap(student_a, student_b, request.user)

        return Response({
            'success': True,
            'message': 'Students swapped successfully',
            'student_a': {'student_id': student_a.id, 'room_id': room_b.id, 'bed_id': new_a.bed_id},
            'student_b': {'student_id': student_b.id, 'room_id': room_a.id, 'bed_id': new_b.bed_id},
        }, status=status.HTTP_200_OK)

    except Student.DoesNotExist:
        return error_response(status.HTTP_404_NOT_FOUND, 'Student not found')
    except BedAssignment.DoesNotExist:
        return error_response(status.HTTP_400_BAD_REQUEST, 'Both students must have active assignments before swapping')
    except PermissionError as e:
        return error_response(status.HTTP_403_FORBIDDEN, str(e))
    except Exception as e:
        return error_response(status.HTTP_400_BAD_REQUEST, str(e))
