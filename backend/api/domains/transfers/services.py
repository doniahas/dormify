"""
Transfer and student-request domain policies, snapshots, and write services.

The api.views compatibility facade (api/views/__init__.py) imports every
name defined here, so references through the api.views namespace keep
resolving to these same objects.
"""

from django.db import transaction
from django.utils import timezone

from ...model_metadata import _get_model_field_names
from ...models import (
    BedAssignment,
    MovementRequest,
    Room,
    Student,
    StudentRequest,
    Transfer,
    User,
)
from ..matching.ranking import _infer_housing_type
from ..placement.services import _execute_swap, _room_region, assign_student_to_room


def infer_movement_type(from_room: Room, to_room: Room):
    if not from_room or not to_room:
        return MovementRequest.MovementType.INTERNAL

    from_region = (
        from_room.apartment.building.dorm_type.region
        if from_room and from_room.apartment and from_room.apartment.building
        else None
    )
    to_region = (
        to_room.apartment.building.dorm_type.region
        if to_room and to_room.apartment and to_room.apartment.building
        else None
    )

    if from_region and to_region and from_region != to_region:
        return MovementRequest.MovementType.REGION_CHANGE

    from_dorm_type = (
        from_room.apartment.building.dorm_type_id
        if from_room and from_room.apartment and from_room.apartment.building
        else None
    )
    to_dorm_type = (
        to_room.apartment.building.dorm_type_id
        if to_room and to_room.apartment and to_room.apartment.building
        else None
    )

    if from_dorm_type != to_dorm_type:
        return MovementRequest.MovementType.DORM_TYPE_CHANGE

    return MovementRequest.MovementType.INTERNAL


def user_can_approve_transfer(user: User, transfer: Transfer):
    if user.is_central_admin:
        return True

    if not user.is_boss or not user.region:
        return False

    same_from_region = transfer.from_room.apartment.building.dorm_type.region == user.region
    same_to_region = transfer.to_room.apartment.building.dorm_type.region == user.region

    return same_from_region and same_to_region


def _user_can_review_request(user, req):
    if user.is_central_admin:
        return True
    if not user.is_boss or not user.region_id:
        return False

    # region_transfer is reviewed/approved by the DESTINATION region, not
    # wherever the student currently lives: the destination region owns the
    # incoming-placement decision (it has the inventory, checks
    # availability, and either accepts or declines the student). This is
    # the opposite of every other request type below, where "the region"
    # is the student's own/target room's region - deliberately checked
    # FIRST and separately so a region_transfer never falls through to the
    # generic accepted_dorm_type branch (which would incorrectly grant the
    # SOURCE region review authority over its own outgoing request).
    if req.request_type == StudentRequest.RequestType.REGION_TRANSFER:
        return bool(req.target_region_id) and req.target_region_id == user.region_id

    if req.student_id and req.student.accepted_dorm_type_id:
        return req.student.accepted_dorm_type.region_id == user.region_id

    if req.target_room_id:
        region = _room_region(req.target_room)
        return bool(region) and region.id == user.region_id

    # New add_student requests with no student/target room assigned yet:
    # any boss may review, region is enforced once a target room is chosen.
    return True


def _user_can_cancel_request(user, req):
    """
    Non-requester fallback authority for StudentRequestViewSet.cancel().

    Withdrawal is a SOURCE-side decision (the requesting side changing its
    mind before anyone reviews it) - deliberately NOT the same population
    as _user_can_review_request(), which for region_transfer now means the
    DESTINATION region (they own approve/reject, see above). A source-
    region boss must still be able to withdraw a transfer their own region
    asked for, even though they can no longer approve/reject it themselves.
    For every other request type this is identical to review authority -
    there is no separate source/destination split to preserve.
    """
    if user.is_central_admin:
        return True
    if not user.is_boss or not user.region_id:
        return False
    if req.request_type == StudentRequest.RequestType.REGION_TRANSFER:
        source_id = req.source_region_id or _student_current_region_id(req.student)
        return bool(source_id) and source_id == user.region_id
    return _user_can_review_request(user, req)


def _student_current_region_id(student):
    """
    The region the student physically lives in RIGHT NOW (their assigned
    room's region), falling back to their accepted region when unassigned.
    This - not the accepted region - is what "the current region" means for
    a same-region transfer.
    """
    if student is None:
        return None
    room = getattr(student, 'assigned_room', None)
    if room is not None:
        try:
            return room.apartment.building.dorm_type.region_id
        except AttributeError:
            pass
    return student.accepted_dorm_type.region_id if student.accepted_dorm_type_id else None


def _assignment_snapshot(student):
    """
    JSON snapshot of the student's live assignment, persisted on the request
    at creation time so the original placement remains known even after the
    student is later moved.
    """
    if student is None or not student.assigned_room_id:
        return {'assigned': False}
    room = student.assigned_room
    bed = student.current_bed
    region = _room_region(room)
    active = student.bed_assignments.filter(status=BedAssignment.Status.ACTIVE).first()
    return {
        'assigned': True,
        'assignment_id': active.id if active else None,
        'region_id': region.id if region else None,
        'region_name': region.name if region else None,
        'building_id': room.apartment.building_id,
        'building_number': room.apartment.building.number,
        'apartment_id': room.apartment_id,
        'apartment_number': room.apartment.number,
        'room_id': room.id,
        'room_name': room.name,
        'bed_id': bed.id if bed else None,
        'bed_label': bed.label if bed else None,
    }


def _create_student_from_request_data(data):
    """
    G2-02 note: the exists()-then-create() below is still a check-then-act
    shape - two concurrent ADD_STUDENT approvals proposing the same new
    student_id can both pass this exists() check before either commits.
    That race is intentionally NOT closed here with a lock (there is no
    row to lock - the student doesn't exist yet); Student.student_id's
    real DB-level unique=True constraint is the actual backstop, and the
    resulting IntegrityError from student.save() below is caught by the
    caller (StudentRequestViewSet.approve()'s except IntegrityError
    clause) and converted into a clean 4xx; the concurrency suite's
    duplicate-student race test pins that outcome.
    """
    if not data:
        raise ValueError('לא סופקו פרטי סטודנט חדש עבור בקשה זו.')

    required = ['student_id', 'first_name', 'last_name', 'gender']
    missing = [f for f in required if not data.get(f)]
    if missing:
        raise ValueError(f"חסרים שדות חובה עבור סטודנט חדש: {', '.join(missing)}")

    if Student.objects.filter(student_id=data['student_id']).exists():
        raise ValueError(f"סטודנט עם ת.ז {data['student_id']} כבר קיים במערכת.")

    student = Student(
        student_id=data['student_id'],
        first_name=data['first_name'],
        last_name=data['last_name'],
        email=data.get('email', ''),
        phone=data.get('phone', ''),
        city=data.get('city', ''),
        gender=data.get('gender'),
        requested_religion=data.get('requested_religion') or data.get('religion') or Student.Religion.NOT_SPECIFIED,
        housing_type=data.get('housing_type') or _infer_housing_type(data),
        category=Student.StudentCategory.NEW,
    )
    student.full_clean()
    student.save()
    return student


def finalize_student_request_creation(instance):
    """
    Post-create persistence for a StudentRequest the serializer has just
    saved (StudentRequestViewSet.perform_create keeps the
    serializer.save(requested_by=...) boundary): assigns the REQ-NNNNNN
    request number, then persists the server-side region context of
    transfer requests. Not wrapped in a transaction, exactly as before.
    """
    if not instance.request_number:
        instance.request_number = f"REQ-{instance.id:06d}"
        instance.save(update_fields=['request_number'])

    # Transfer requests persist their region context server-side (never
    # trusted from the client): scope default, the source region the
    # student lives in right now, and a snapshot of the current
    # assignment - so the request stays meaningful after refreshes,
    # restarts, and even after the student is eventually moved.
    if instance.request_type in (StudentRequest.RequestType.ROOM, StudentRequest.RequestType.APARTMENT) \
            and instance.student_id:
        changed = []
        if not instance.transfer_scope:
            instance.transfer_scope = StudentRequest.TransferScope.SAME_REGION
            changed.append('transfer_scope')
        if not instance.source_region_id:
            source = _student_current_region_id(instance.student)
            if source:
                instance.source_region_id = source
                changed.append('source_region')
        if instance.current_assignment_snapshot is None:
            instance.current_assignment_snapshot = _assignment_snapshot(instance.student)
            changed.append('current_assignment_snapshot')
        if changed:
            instance.save(update_fields=changed)

    # region_transfer requests get the same source_region/
    # current_assignment_snapshot persistence as ROOM/APARTMENT above -
    # a permanent audit record of where the request started, even after
    # the student is later moved or the request is long resolved - but
    # deliberately NOT transfer_scope, which belongs only to the ROOM/
    # APARTMENT same-region/cross-region system and has no meaning for
    # region_transfer (see StudentRequest.transfer_scope help_text).
    if instance.request_type == StudentRequest.RequestType.REGION_TRANSFER and instance.student_id:
        changed = []
        if not instance.source_region_id:
            source = _student_current_region_id(instance.student)
            if source:
                instance.source_region_id = source
                changed.append('source_region')
        if instance.current_assignment_snapshot is None:
            instance.current_assignment_snapshot = _assignment_snapshot(instance.student)
            changed.append('current_assignment_snapshot')
        if changed:
            instance.save(update_fields=changed)


def approve_student_request(req, reviewer, target_room, bed_id):
    """
    Locked write core of StudentRequestViewSet.approve(). The view has
    already run the boss / unlocked PENDING / _user_can_review_request()
    pre-checks, resolved target_room (or None) and authorized it with
    _user_can_edit_room(), and read bed_id from the payload; it keeps all
    HTTP status/error mapping and the response serialization.

    Returns False, without writing anything, when the locked re-read shows
    the request was already handled; returns True once it is APPROVED.
    PermissionError, ValueError, ValidationError, IntegrityError and any
    other exception propagate after the transaction rolls back.
    """
    with transaction.atomic():
        # G2-01 fix: the view's PENDING check is a fast, unlocked
        # pre-check for the common (non-racing) case - it can go
        # stale between then and here. select_for_update()
        # re-fetches and locks THIS SAME ROW; status is
        # re-verified under that lock, which is the authoritative
        # check a second, concurrent approve() call for the SAME
        # request cannot slip past (it blocks on this
        # select_for_update() until the winning request's
        # transaction commits, then sees the already-updated
        # status). req itself (from get_queryset(), with all its
        # select_related/prefetch chains) is deliberately left
        # untouched and reused by the view for the response - only this
        # lightweight locked copy is used for the status recheck.
        locked_req = StudentRequest.objects.select_for_update().get(pk=req.pk)
        if locked_req.status != StudentRequest.Status.PENDING:
            return False

        if req.request_type in (StudentRequest.RequestType.ROOM, StudentRequest.RequestType.APARTMENT):
            if not req.student:
                raise ValueError('לא נבחר סטודנט עבור בקשה זו')
            room = target_room or req.target_room
            if not room:
                raise ValueError('יש לבחור חדר יעד לפני האישור')

            # The stored transfer scope is authoritative at approval
            # time too - the destination room is revalidated against
            # it, and cross-region approval stays central-admin-only.
            room_region = _room_region(room)
            room_region_id = room_region.id if room_region else None
            if req.transfer_scope == StudentRequest.TransferScope.CROSS_REGION:
                if not reviewer.is_central_admin:
                    raise PermissionError('אין לך הרשאה לבצע מעבר לאזור אחר.')
                allowed_regions = set(req.destination_regions.values_list('id', flat=True))
                if allowed_regions and room_region_id not in allowed_regions:
                    raise ValueError('החדר שנבחר אינו באזורי היעד שנבחרו בבקשה')
            elif req.transfer_scope == StudentRequest.TransferScope.SAME_REGION:
                source_id = req.source_region_id or _student_current_region_id(req.student)
                if source_id and room_region_id and room_region_id != source_id:
                    raise ValueError('החדר שנבחר אינו באזור הנוכחי של הסטודנט (מעבר בתוך האזור)')

            new_assignment = assign_student_to_room(
                student=req.student, room=room, assigned_by=reviewer,
                assignment_type=BedAssignment.AssignmentType.TRANSFER, bed_id=bed_id,
            )
            req.target_room = room
            req.final_assignment = new_assignment

        elif req.request_type == StudentRequest.RequestType.ADD_STUDENT:
            if not req.student:
                req.student = _create_student_from_request_data(req.student_data)
            if target_room:
                req.final_assignment = assign_student_to_room(
                    student=req.student, room=target_room, assigned_by=reviewer,
                    assignment_type=BedAssignment.AssignmentType.MANUAL, bed_id=bed_id,
                )
                req.target_room = target_room

        elif req.request_type == StudentRequest.RequestType.REMOVE_STUDENT:
            if not req.student:
                raise ValueError('לא נבחר סטודנט עבור בקשה זו')
            current = req.student.bed_assignments.filter(status=BedAssignment.Status.ACTIVE).first()
            if current:
                current.status = BedAssignment.Status.ENDED
                current.ended_at = timezone.now()
                current.save(update_fields=['status', 'ended_at'])
            req.student.assigned_room = None
            req.student.save(update_fields=['assigned_room'])

        elif req.request_type == StudentRequest.RequestType.SWAP:
            if not req.student or not req.swap_with_student:
                raise ValueError('בקשת החילוף חסרה סטודנט או שותף לחילוף')
            _execute_swap(req.student, req.swap_with_student, reviewer)

        elif req.request_type == StudentRequest.RequestType.REGION_TRANSFER:
            # Approval authority for region_transfer is the
            # DESTINATION region (or central admin) - already
            # enforced by the view's _user_can_review_request(), plus
            # its _user_can_edit_room() check on whatever target_room
            # the approver picks. No extra central-admin-only gate
            # here: that used to be the ONLY way in (destination-
            # region approval didn't exist yet); now it would just
            # incorrectly re-block the destination region's own
            # boss from approving their own incoming transfer.
            if not req.student:
                raise ValueError('לא נבחר סטודנט עבור בקשה זו')
            room = target_room or req.target_room
            if not room:
                raise ValueError('יש לבחור חדר יעד באזור היעד לפני האישור')
            destination_region = _room_region(room)
            if req.target_region_id and destination_region and req.target_region_id != destination_region.id:
                raise ValueError('החדר שנבחר אינו באזור היעד שביקש הבקשה')
            req.final_assignment = assign_student_to_room(
                student=req.student, room=room, assigned_by=reviewer,
                assignment_type=BedAssignment.AssignmentType.TRANSFER, bed_id=bed_id,
            )
            req.target_room = room

        # 'other' requests are administrative only - no system action required.

        req.status = StudentRequest.Status.APPROVED
        req.reviewed_by = reviewer
        req.reviewed_at = timezone.now()
        req.save()

    return True


def reject_student_request(req, reviewer, read_rejection_reason):
    """
    Locked write core of StudentRequestViewSet.reject(); the view keeps the
    boss / unlocked PENDING / _user_can_review_request() pre-checks.
    read_rejection_reason is a zero-argument callable evaluated under the
    lock, after the PENDING recheck - exactly where reject() always read the
    payload - so a locked-stale request still answers "already handled"
    before its body is parsed. Returns False, without writing, when the
    locked re-read shows the request was already handled; True once it is
    REJECTED.
    """
    with transaction.atomic():
        # Same lock-and-recheck pattern as approve_student_request() above -
        # also closes a pre-existing gap where reject() previously had NO
        # transaction.atomic() at all.
        locked_req = StudentRequest.objects.select_for_update().get(pk=req.pk)
        if locked_req.status != StudentRequest.Status.PENDING:
            return False

        req.status = StudentRequest.Status.REJECTED
        req.reviewed_by = reviewer
        req.reviewed_at = timezone.now()
        req.rejection_reason = read_rejection_reason()
        req.save()

    return True


def cancel_student_request(req, actor):
    """
    Locked write core of StudentRequestViewSet.cancel(); the view keeps the
    unlocked PENDING pre-check and the requester short-circuit /
    _user_can_cancel_request() authorization. Returns False, without
    writing, when the locked re-read shows the request was already
    handled; True once it is CANCELLED (reviewed_by = actor).
    """
    with transaction.atomic():
        # Same lock-and-recheck pattern as approve/reject_student_request() above.
        locked_req = StudentRequest.objects.select_for_update().get(pk=req.pk)
        if locked_req.status != StudentRequest.Status.PENDING:
            return False

        req.status = StudentRequest.Status.CANCELLED
        req.reviewed_by = actor
        req.reviewed_at = timezone.now()
        req.save()

    return True


def create_legacy_transfer(transfer, student, target_bed, movement_type, requested_by):
    """
    Write core of TransferViewSet.perform_create(): creates, full_cleans and
    saves the PENDING MovementRequest for a legacy Transfer the serializer
    has just saved, then links it to that Transfer. Runs inside the view's
    transaction.atomic() block - the view keeps the source-room / region
    checks, validate_apartment_assignment(), infer_movement_type(), the
    get_free_bed() selection with its DRF validation errors, and
    serializer.save(), all in their original order.
    """
    movement_request = MovementRequest(
        student=student,
        from_assignment=student.current_assignment,
        to_bed=target_bed,
        movement_type=movement_type,
        status=MovementRequest.Status.PENDING,
        reason=transfer.reason,
        requested_by=requested_by
    )
    movement_request.full_clean()
    movement_request.save()

    transfer.movement_request = movement_request
    transfer_fields = _get_model_field_names(Transfer)
    update_fields = ['movement_request']
    if 'updated_at' in transfer_fields:
        update_fields.append('updated_at')
    transfer.save(update_fields=update_fields)


def approve_legacy_transfer(transfer, reviewer):
    """
    Locked write core of TransferViewSet.approve(). The view keeps the boss
    / unlocked PENDING / user_can_approve_transfer() / destination-full
    pre-checks, the ValueError / ValidationError / IntegrityError -> 400
    mapping and the response. The original (get_object()) transfer is the
    one mutated; the locked copy is only used for the status recheck.

    Returns False, without writing anything, when the locked re-read shows
    the transfer was already handled; returns True once it is APPROVED.
    """
    with transaction.atomic():
        # G2-01-equivalent fix (Transfer race): the view's PENDING
        # check is a fast, unlocked pre-check for the common
        # (non-racing) case - it can go stale between then and
        # here. select_for_update() re-fetches and locks THIS
        # SAME ROW; status is re-verified under that lock, which
        # is the authoritative check a second, concurrent
        # approve() call for the SAME transfer cannot slip past
        # (it blocks on this select_for_update() until the
        # winning request's transaction commits, then sees the
        # already-updated status).
        locked_transfer = Transfer.objects.select_for_update().get(pk=transfer.pk)
        if locked_transfer.status != Transfer.Status.PENDING:
            return False

        transfer.status = Transfer.Status.APPROVED
        transfer.reviewed_by = reviewer
        transfer.reviewed_at = timezone.now()
        transfer.save()

        student = transfer.student
        # movement_type lives on the related MovementRequest, not
        # on Transfer itself (see create_legacy_transfer() above) - falls
        # back to the regular TRANSFER assignment type when there
        # is no linked MovementRequest, matching this fallback's
        # original intent for any non-PHASE2 movement_type.
        movement_type = (
            transfer.movement_request.movement_type
            if transfer.movement_request_id else None
        )
        assignment_type = (
            BedAssignment.AssignmentType.PHASE2
            if movement_type == MovementRequest.MovementType.PHASE2
            else BedAssignment.AssignmentType.TRANSFER
        )

        new_assignment = assign_student_to_room(
            student=student,
            room=transfer.to_room,
            assigned_by=reviewer,
            assignment_type=assignment_type
        )

        if transfer.movement_request:
            transfer.movement_request.to_bed = new_assignment.bed
            transfer.movement_request.status = MovementRequest.Status.COMPLETED
            transfer.movement_request.approved_by = reviewer
            transfer.movement_request.reviewed_at = timezone.now()
            transfer.movement_request.completed_at = timezone.now()
            transfer.movement_request.full_clean()
            transfer.movement_request.save()

    return True


def reject_legacy_transfer(transfer, reviewer, read_rejection_reason):
    """
    Locked write core of TransferViewSet.reject(); the view keeps the boss /
    unlocked PENDING / user_can_approve_transfer() pre-checks and the
    response (reject has no exception mapping - unchanged).
    read_rejection_reason is a zero-argument callable evaluated under the
    lock, after the PENDING recheck - exactly where reject() always read the
    payload. Returns False, without writing, when the locked re-read shows
    the transfer was already handled; True once it is REJECTED.
    """
    with transaction.atomic():
        # Same lock-and-recheck pattern as approve_legacy_transfer() above - also
        # closes a pre-existing gap where reject() previously had NO
        # transaction.atomic() at all, so a failure between
        # transfer.save() and movement_request.save() could leave
        # inconsistent state.
        locked_transfer = Transfer.objects.select_for_update().get(pk=transfer.pk)
        if locked_transfer.status != Transfer.Status.PENDING:
            return False

        transfer.status = Transfer.Status.REJECTED
        transfer.reviewed_by = reviewer
        transfer.reviewed_at = timezone.now()
        transfer.rejection_reason = read_rejection_reason()
        transfer.save()

        if transfer.movement_request:
            transfer.movement_request.status = MovementRequest.Status.REJECTED
            transfer.movement_request.approved_by = reviewer
            transfer.movement_request.reviewed_at = timezone.now()
            transfer.movement_request.completed_at = None
            transfer.movement_request.full_clean()
            transfer.movement_request.save()

    return True
