from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from ..domains.analytics.queries import (
    build_allocation_summary_read_model, build_analysis_read_model,
    build_statistics_read_model,
)
from ..permissions import _resolve_region, resolve_scoped_region
from ..serializers import (
    AllocationRunSerializer, ImportBatchSerializer, RegionInboxSerializer,
    RegionSerializer,
)
from ..contracts.errors import error_response

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def allocation_summary(request):
    user = request.user

    # G3-03: centralized region resolution - region_boss/employee can never
    # pull another region's summary via ?region=/?region_id=/?region_name=.
    region_value = (
        request.query_params.get('region')
        or request.query_params.get('region_id')
        or request.query_params.get('region_name')
    )
    region, error = resolve_scoped_region(user, region_value)
    if error:
        return error

    if region is None:
        # central_admin with no region selected - this endpoint has no
        # single-region-independent meaning, matching prior behavior.
        return Response({
                'region': None,
                'total_students': 0,
                'unassigned_students': 0,
                'assigned_students': 0,
                'available_beds': 0,
                'priority_students': 0,
                'total_capacity': 0,
                'occupancy_rate': 0,
                'students_by_category': {
                    'new': 0,
                    'continuing': 0,
                    'transfer': 0,
                    'leaving': 0,
                },
                'students_by_housing_type': {
                    'single_male': 0,
                    'single_female': 0,
                    'single_mixed': 0,
                    'couple': 0,
                    'family': 0,
                    'unknown': 0,
                },
                'inventory_by_type': {
                    'single': {
                        'apartments': 0,
                        'rooms': 0,
                        'total_beds': 0,
                        'occupied_beds': 0,
                        'available_beds': 0,
                    },
                    'couple': {
                        'apartments': 0,
                        'rooms': 0,
                        'total_beds': 0,
                        'occupied_beds': 0,
                        'available_beds': 0,
                    },
                    'family': {
                        'apartments': 0,
                        'rooms': 0,
                        'total_beds': 0,
                        'occupied_beds': 0,
                        'available_beds': 0,
                    },
                },
                'population_summary': {
                    'imported_students': 0,
                    'excluded_accessibility': 0,
                    'excluded_leaving': 0,
                    'excluded_overlap': 0,
                    'excluded_total': 0,
                    'sent_to_solver': 0,
                    'sent_to_solver_student_ids': [],
                },
                'latest_inbox': None,
                'latest_run': None,
            }, status=status.HTTP_200_OK)

    summary = build_allocation_summary_read_model(region)

    return Response({
        'region': RegionSerializer(region).data,
        'total_students': summary['total_students'],
        'unassigned_students': summary['unassigned_students'],
        'assigned_students': summary['assigned_students'],
        'available_beds': summary['available_beds'],
        'priority_students': summary['priority_students'],
        'total_capacity': summary['total_capacity'],
        'occupancy_rate': summary['occupancy_rate'],
        'students_by_category': summary['students_by_category'],
        'students_by_housing_type': summary['students_by_housing_type'],
        'inventory_by_type': summary['inventory_by_type'],
        'population_summary': summary['population_summary'],
        'latest_inbox': (
            RegionInboxSerializer(summary['latest_inbox']).data
            if summary['latest_inbox'] else None
        ),
        'latest_run': (
            AllocationRunSerializer(summary['latest_run']).data
            if summary['latest_run'] else None
        ),
    }, status=status.HTTP_200_OK)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def analysis_data(request):
    user = request.user

    # =========================
    # Resolve region permissions
    # =========================
    if user.is_central_admin:
        region_value = (
            request.query_params.get('region')
            or request.query_params.get('region_id')
            or request.query_params.get('region_name')
        )

        if region_value:
            region = _resolve_region(region_value)
            if not region:
                return error_response(status.HTTP_404_NOT_FOUND, 'אזור לא נמצא')
        else:
            region = None
    else:
        if not user.region:
            return error_response(status.HTTP_400_BAD_REQUEST, 'המשתמש אינו משויך לאזור')
        region = user.region

    read_model = build_analysis_read_model(region)

    return Response({
        'region': RegionSerializer(region).data if region else None,
        'summary': read_model['summary'],
        'students_by_gender': read_model['students_by_gender'],
        'students_by_religion': read_model['students_by_religion'],
        'students_by_religious': read_model['students_by_religious'],
        'students_by_category': read_model['students_by_category'],
        'students_by_housing': read_model['students_by_housing'],
        'students_by_region': read_model['students_by_region'],
        'unassigned_by_region': read_model['unassigned_by_region'],
        'occupancy_data': read_model['occupancy_data'],
        'transfers_by_status': read_model['transfers_by_status'],
        'transfers_by_type': read_model['transfers_by_type'],
        'pending_requests_by_type': read_model['pending_requests_by_type'],
        'latest_run': (
            AllocationRunSerializer(read_model['latest_run']).data
            if read_model['latest_run'] else None
        ),
        'latest_batch': (
            ImportBatchSerializer(read_model['latest_batch']).data
            if read_model['latest_batch'] else None
        ),
    }, status=status.HTTP_200_OK)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def statistics(request):
    user = request.user
    region_value = request.query_params.get('region')

    # G3-03: centralized region resolution - region_boss/employee can never
    # pull another region's statistics via ?region=.
    region, error = resolve_scoped_region(user, region_value)
    if error:
        return error

    return Response(build_statistics_read_model(region))
