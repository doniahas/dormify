"""
Student placement write services.
"""

from django.db import transaction
from django.utils import timezone

from ...model_metadata import _get_model_field_names
from ...models import Apartment, BedAssignment, Room, Student, User
from .beds import get_free_bed, get_specific_free_bed
from .rules import validate_apartment_assignment


def end_active_bed_assignments(student: Student):
    BedAssignment.objects.filter(
        student=student,
        status=BedAssignment.Status.ACTIVE
    ).update(
        status=BedAssignment.Status.ENDED,
        ended_at=timezone.now()
    )


def assign_student_to_room(
    student: Student,
    room: Room,
    assigned_by: User,
    assignment_type=BedAssignment.AssignmentType.MANUAL,
    bed_id=None,
    skip_validation=False,
):
    """
    skip_validation: staff-authorized manual override only (Assisted
    Allocation "manual override" action). Skips the
    validate_apartment_assignment(...) compatibility check below - every
    other safety step (apartment lock, bed re-verification under lock,
    full_clean uniqueness constraints, denormalized assigned_room update)
    still runs unchanged, so an override can never double-book a bed or
    exceed room capacity. Callers passing True must have already computed
    and confirmed the violated rules with
    allocation.manual_placement.evaluate_manual_override.
    """
    # Lock the apartment while validating and assigning so two concurrent
    # requests cannot violate Z6 apartment exclusivity.
    with transaction.atomic():
        locked_apartment = Apartment.objects.select_for_update().get(
            pk=room.apartment_id
        )
        locked_room = Room.objects.select_related(
            'apartment',
            'apartment__building',
        ).get(pk=room.pk)
        locked_room.apartment = locked_apartment

        if not skip_validation:
            validate_apartment_assignment(student, locked_room)

        # A caller may target a specific bed (e.g. the per-bed matching UI) -
        # it is always re-verified free here, under the apartment lock,
        # regardless of what the client last saw. Without an explicit
        # bed_id, fall back to "any free bed in the room".
        if bed_id is not None:
            free_bed = get_specific_free_bed(locked_room, bed_id)
        else:
            free_bed = get_free_bed(locked_room)
        if not free_bed:
            raise ValueError('No available bed in selected room.')

        end_active_bed_assignments(student)

        assignment = BedAssignment(
            student=student,
            bed=free_bed,
            status=BedAssignment.Status.ACTIVE,
            assignment_type=assignment_type,
            assigned_by=assigned_by
        )
        assignment.full_clean()
        assignment.save()

        student.assigned_room = locked_room
        student_fields = _get_model_field_names(Student)
        update_fields = ['assigned_room']
        if 'updated_at' in student_fields:
            update_fields.append('updated_at')
        student.save(update_fields=update_fields)

    return assignment


def _room_region(room):
    try:
        return room.apartment.building.dorm_type.region
    except AttributeError:
        return None


def _user_can_edit_room(user, room):
    if not user or not user.is_authenticated:
        return False

    if user.is_central_admin:
        return True

    if not user.region_id:
        return False

    room_region = _room_region(room)
    if not room_region:
        return False

    return room_region.id == user.region_id


def _execute_swap(student_a, student_b, performed_by):
    """
    Atomically swap two students' active bed assignments. This is the single
    swap implementation (§7, §14) - both the direct
    /api/room-assignments/swap/ endpoint and StudentRequest SWAP approval
    call this instead of duplicating the logic.

    select_for_update() locks both BedAssignment rows in canonical student-ID
    order for the duration of the transaction, so concurrent reversed swaps
    cannot deadlock or reassign either bed out from under this swap. Both
    directions are validated with the same
    validate_apartment_assignment() used everywhere else before *anything*
    is written; if either direction is invalid (or the room-edit permission
    check fails), the whole transaction rolls back and neither student's
    original assignment is touched.

    Raises: Student.DoesNotExist is not caught here (callers resolve
    students first); BedAssignment.DoesNotExist if either lacks an active
    assignment; PermissionError if the caller may not edit one of the rooms
    (this is what makes a cross-region swap require a central admin -
    _user_can_edit_room already restricts regional users to their own
    region); ValueError for any hard-constraint violation.
    """
    with transaction.atomic():
        # select_for_update(of=('self',)) locks only the BedAssignment row
        # itself. Locking across the full select_related chain would fail on
        # Postgres ("FOR UPDATE cannot be applied to the nullable side of an
        # outer join") because Building.dorm_type and DormType.region are
        # nullable FKs, which Django joins as LEFT OUTER JOIN - that join
        # type can never be combined with FOR UPDATE, independent of whether
        # any actual row has a null value there.
        def _lock_active_assignments():
            return [
                assignment
                for assignment in BedAssignment.objects.select_for_update(of=('self',)).select_related(
                    'bed__room__apartment__building__dorm_type__region'
                ).filter(
                    student_id__in=(student_a.pk, student_b.pk),
                    status=BedAssignment.Status.ACTIVE,
                ).order_by('student_id', 'id')
            ]

        locked_assignments = _lock_active_assignments()
        if student_a.pk != student_b.pk and not locked_assignments:
            locked_assignments = _lock_active_assignments()

        assignments_by_student_id = {
            assignment.student_id: assignment
            for assignment in locked_assignments
        }
        try:
            assignment_a = assignments_by_student_id[student_a.pk]
            assignment_b = assignments_by_student_id[student_b.pk]
        except KeyError:
            raise BedAssignment.DoesNotExist(
                'BedAssignment matching query does not exist.'
            ) from None

        room_a = assignment_a.bed.room
        room_b = assignment_b.bed.room

        if room_a.id == room_b.id:
            raise ValueError('שני הסטודנטים כבר נמצאים באותו חדר')

        if not _user_can_edit_room(performed_by, room_a) or not _user_can_edit_room(performed_by, room_b):
            raise PermissionError('אין הרשאה לערוך אחד מהחדרים')

        validate_apartment_assignment(student_a, room_b)
        validate_apartment_assignment(student_b, room_a)

        now = timezone.now()
        assignment_a.status = BedAssignment.Status.ENDED
        assignment_a.ended_at = now
        assignment_a.save(update_fields=['status', 'ended_at'])

        assignment_b.status = BedAssignment.Status.ENDED
        assignment_b.ended_at = now
        assignment_b.save(update_fields=['status', 'ended_at'])

        new_a = assign_student_to_room(
            student=student_a,
            room=room_b,
            assigned_by=performed_by,
            assignment_type=BedAssignment.AssignmentType.TRANSFER,
        )
        new_b = assign_student_to_room(
            student=student_b,
            room=room_a,
            assigned_by=performed_by,
            assignment_type=BedAssignment.AssignmentType.TRANSFER,
        )

    return new_a, new_b, room_a, room_b


def unassign_student(student, current_assignment):
    """
    End the student's active bed assignment and clear the denormalized
    assigned_room, as one transaction. ``current_assignment`` is the ACTIVE
    BedAssignment the caller already looked up (and authorized).
    """
    with transaction.atomic():
        current_assignment.status = BedAssignment.Status.ENDED
        current_assignment.ended_at = timezone.now()
        current_assignment.save(update_fields=['status', 'ended_at'])

        student.assigned_room = None
        student.save(update_fields=['assigned_room'])
