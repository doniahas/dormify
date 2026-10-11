"""
What-if confirm workflows: deactivating (or reactivating) inventory and
raising a pending transfer request for every student it shelters, as one
transaction.
"""

from django.db import transaction

from ...models import Apartment, Building, Room, StudentRequest
from ..transfers.services import _assignment_snapshot, _student_current_region_id


def create_deactivation_transfer_request(assignment, reason, requested_by):
    """
    Ensure a pending StudentRequest exists for a student whose current
    inventory (building/apartment/room) was just deactivated.

    StudentRequest — not MovementRequest — is the model the actual
    Transfer Requests / בקשות מעבר page (StudentRequestViewSet, /api/requests/)
    reads. This reuses the same request_type/status/snapshot conventions
    StudentRequestViewSet.perform_create already uses for manually-created
    room/apartment transfer requests (see _assignment_snapshot /
    _student_current_region_id), so deactivation-triggered requests render
    identically on the existing page instead of needing special-cased UI.

    Idempotent: BedAssignment enforces at most one ACTIVE assignment per
    student, so a student who already has a pending room/apartment-type
    request necessarily already has one covering this exact current
    assignment - regardless of which level of the hierarchy
    (building/apartment/room) triggered the deactivation. Returns the
    created StudentRequest, or None when an existing pending request
    already covers this student and nothing was created.
    """
    student = assignment.student

    already_pending = StudentRequest.objects.filter(
        student=student,
        status=StudentRequest.Status.PENDING,
        request_type__in=[
            StudentRequest.RequestType.ROOM,
            StudentRequest.RequestType.APARTMENT,
        ],
    ).exists()
    if already_pending:
        return None

    transfer_request = StudentRequest.objects.create(
        student=student,
        request_type=StudentRequest.RequestType.ROOM,
        status=StudentRequest.Status.PENDING,
        reason=reason,
        requested_by=requested_by,
        transfer_scope=StudentRequest.TransferScope.SAME_REGION,
        source_region_id=_student_current_region_id(student),
        current_assignment_snapshot=_assignment_snapshot(student),
    )
    transfer_request.request_number = f"REQ-{transfer_request.id:06d}"
    transfer_request.save(update_fields=['request_number'])
    return transfer_request


def _raise_transfer_requests(affected_assignments, reason, requested_by):
    created_count = 0
    skipped_existing_count = 0
    created_request_ids = []

    for assignment in affected_assignments:
        transfer_request = create_deactivation_transfer_request(
            assignment=assignment,
            reason=reason,
            requested_by=requested_by,
        )

        if transfer_request is None:
            skipped_existing_count += 1
            continue

        created_count += 1
        created_request_ids.append(transfer_request.id)

    return created_count, skipped_existing_count, created_request_ids


def confirm_building_inactivation(buildings, affected_assignments, *, reason, requested_by,
                                  inactivate_buildings=True):
    """
    Atomically inactivate the selected buildings (unless the caller only
    wants the requests) and raise a pending transfer request for every
    affected assignment. Returns
    (created_count, skipped_existing_count, created_request_ids).
    """
    with transaction.atomic():
        if inactivate_buildings:
            buildings.update(is_active=False)

        return _raise_transfer_requests(affected_assignments, reason, requested_by)


def apply_availability_change(target_type, target_ids, affected_assignments, *, action,
                              reason, requested_by):
    """
    Atomically set is_active on the selected buildings / apartments / rooms
    (``action`` is 'inactivate' or 'reactivate') and, when inactivating,
    raise a pending transfer request for every affected assignment so the
    occupants stay assigned yet visible to staff for manual resolution.
    Returns (created_count, skipped_existing_count, created_request_ids).
    """
    with transaction.atomic():
        new_active_value = action == 'reactivate'

        if target_type == 'building':
            Building.objects.filter(id__in=target_ids).update(
                is_active=new_active_value
            )
        elif target_type == 'apartment':
            Apartment.objects.filter(id__in=target_ids).update(
                is_active=new_active_value
            )
        else:
            Room.objects.filter(id__in=target_ids).update(
                is_active=new_active_value
            )

        if action == 'inactivate':
            return _raise_transfer_requests(affected_assignments, reason, requested_by)

    return 0, 0, []
