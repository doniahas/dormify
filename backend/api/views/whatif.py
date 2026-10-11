"""What-if HTTP views: request parsing, region authorization, domain calls, responses."""

import traceback

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from ..contracts.requests import (
    parse_availability_action,
    parse_building_ids,
    parse_target_selection,
)
from ..domains.whatif.queries import (
    affected_assignments_for_targets,
    buildings_for_ids,
    targets_for_ids,
)
from ..domains.whatif.services import (
    apply_availability_change,
    confirm_building_inactivation,
)
from ..domains.whatif.simulation import (
    simulate_availability_change,
    simulate_building_inactivation,
)
from ..contracts.errors import failure_response


def _what_if_get_buildings_from_request(request):
    """Selected buildings from the request body; ValueError on bad input."""
    return buildings_for_ids(parse_building_ids(request.data))


def _what_if_user_can_access_buildings(user, buildings):
    if user.is_central_admin:
        return True

    if not user.region_id:
        return False

    return not buildings.exclude(dorm_type__region=user.region).exists()


def _what_if_get_targets_from_request(request):
    """Selected target type / ids / rows from the request body; ValueError on bad input."""
    target_type, target_ids = parse_target_selection(request.data)
    return target_type, target_ids, targets_for_ids(target_type, target_ids)


def _what_if_user_can_access_targets(user, target_type, targets):
    if user.is_central_admin:
        return True

    if not user.region_id:
        return False

    if target_type == 'building':
        return not targets.exclude(dorm_type__region=user.region).exists()

    if target_type == 'apartment':
        return not targets.exclude(building__dorm_type__region=user.region).exists()

    return not targets.exclude(apartment__building__dorm_type__region=user.region).exists()


def _what_if_error_response(exc):
    if isinstance(exc, ValueError):
        return failure_response(status.HTTP_400_BAD_REQUEST, str(exc))

    traceback.print_exc()
    return failure_response(status.HTTP_500_INTERNAL_SERVER_ERROR, str(exc), error_type=exc.__class__.__name__)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def what_if_building_inactivation_simulate(request):
    """
    Simulate what happens if one or more buildings are inactivated.
    This endpoint does NOT change the database.
    """
    try:
        buildings = _what_if_get_buildings_from_request(request)

        if not _what_if_user_can_access_buildings(request.user, buildings):
            return failure_response(status.HTTP_403_FORBIDDEN, 'אין הרשאה לבצע סימולציה עבור אחד או יותר מהבניינים שנבחרו.')

        return Response({
            'success': True,
            **simulate_building_inactivation(buildings),
        }, status=status.HTTP_200_OK)

    except Exception as e:
        return _what_if_error_response(e)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def what_if_building_inactivation_confirm(request):
    """
    Confirm building inactivation and create pending StudentRequest rows
    (the model backing the Transfer Requests / בקשות מעבר page) for
    affected active assignments. This does not choose new rooms and does
    not run allocation.
    """
    try:
        if not request.user.is_boss:
            return failure_response(status.HTTP_403_FORBIDDEN, 'רק מנהל יכול לאשר השבתת בניינים ויצירת בקשות העברה.')

        buildings = _what_if_get_buildings_from_request(request)

        if not _what_if_user_can_access_buildings(request.user, buildings):
            return failure_response(status.HTTP_403_FORBIDDEN, 'אין הרשאה להשבית אחד או יותר מהבניינים שנבחרו.')

        reason = request.data.get('reason') or 'Building was inactivated and student needs transfer.'
        inactivate_buildings = request.data.get('inactivate_buildings', True)

        building_ids = list(buildings.values_list('id', flat=True))

        affected_assignments = list(
            affected_assignments_for_targets('building', building_ids)
        )

        created_count, skipped_existing_count, created_request_ids = confirm_building_inactivation(
            buildings, affected_assignments,
            reason=reason,
            requested_by=request.user,
            inactivate_buildings=inactivate_buildings,
        )

        return Response({
            'success': True,
            'message': 'Building inactivation confirmed and transfer requests were created.',
            'inactivated_buildings': inactivate_buildings,
            'selected_building_ids': building_ids,
            'affected_students_count': len(affected_assignments),
            'created_requests': created_count,
            'skipped_existing_requests': skipped_existing_count,
            'created_request_ids': created_request_ids,
        }, status=status.HTTP_200_OK)

    except Exception as e:
        return _what_if_error_response(e)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def what_if_availability_simulate(request):
    """
    Generic What-if simulation for buildings, apartments, and rooms.
    This endpoint does NOT change the database.
    """
    try:
        target_type, target_ids, targets = _what_if_get_targets_from_request(request)

        if not _what_if_user_can_access_targets(request.user, target_type, targets):
            return failure_response(status.HTTP_403_FORBIDDEN, 'אין הרשאה לבצע סימולציה עבור אחד או יותר מהפריטים שנבחרו.')

        return Response({
            'success': True,
            **simulate_availability_change(target_type, target_ids, targets),
        }, status=status.HTTP_200_OK)

    except Exception as e:
        return _what_if_error_response(e)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def what_if_availability_confirm(request):
    """
    Confirm generic availability change for buildings, apartments, or rooms.
    Inactivation affects the database by setting is_active=False.
    It also creates pending StudentRequest rows (the model backing the
    Transfer Requests / בקשות מעבר page) for affected active assignments,
    so occupants stay assigned to their current bed and become visible to
    staff for manual resolution instead of disappearing from workflow.
    """
    try:
        if not request.user.is_boss:
            return failure_response(status.HTTP_403_FORBIDDEN, 'רק מנהל יכול לאשר שינוי זמינות ויצירת בקשות העברה.')

        target_type, target_ids, targets = _what_if_get_targets_from_request(request)

        if not _what_if_user_can_access_targets(request.user, target_type, targets):
            return failure_response(status.HTTP_403_FORBIDDEN, 'אין הרשאה לשנות זמינות עבור אחד או יותר מהפריטים שנבחרו.')

        action = parse_availability_action(request.data)

        reason = request.data.get('reason') or 'Availability changed.'

        affected_assignments = list(
            affected_assignments_for_targets(target_type, target_ids)
        )

        created_count, skipped_existing_count, created_request_ids = apply_availability_change(
            target_type, target_ids, affected_assignments,
            action=action,
            reason=reason,
            requested_by=request.user,
        )

        return Response({
            'success': True,
            'message': 'Availability change confirmed.',
            'target_type': target_type,
            'target_ids': target_ids,
            'action': action,
            'affected_students_count': len(affected_assignments),
            'created_requests': created_count,
            'skipped_existing_requests': skipped_existing_count,
            'created_request_ids': created_request_ids,
        }, status=status.HTTP_200_OK)

    except Exception as e:
        return _what_if_error_response(e)
