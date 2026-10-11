from django.http import HttpResponse
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated

from ..models import Region
from ..permissions import IsCentralAdmin
from ..contracts.errors import error_response

def _excel_response(buffer, filename):
    """Return an in-memory XLSX workbook as a downloadable HTTP response."""
    response = HttpResponse(
        buffer.getvalue(),
        content_type=(
            'application/vnd.openxmlformats-officedocument.'
            'spreadsheetml.sheet'
        ),
    )
    response['Content-Disposition'] = (
        f'attachment; filename="{filename}"'
    )
    return response

@api_view(['GET'])
@permission_classes([IsAuthenticated, IsCentralAdmin])
def dormify_report(request):
    """
    Generate the complete, all-regions Dormify Excel report.

    Central-admin only: generate_dormify_report() has no region-filtering
    capability at all, so - unlike the other report endpoints below, which
    scope to the caller's region via _resolve_report_region - this one
    cannot be safely offered to regional users without leaking every other
    region's data (§9).
    """
    from ..domains.reports.exports import generate_dormify_report

    try:
        buffer = generate_dormify_report()
    except Exception as exc:
        return error_response(status.HTTP_500_INTERNAL_SERVER_ERROR, str(exc))

    today = timezone.now().strftime('%Y-%m-%d')
    return _excel_response(
        buffer,
        f'Dormify_Report_{today}.xlsx',
    )


def _resolve_report_region(request):
    """
    Resolve the optional report region query parameter.

    §9/§16: a regional user's own region always wins here - a region_id
    sent in the query string is only ever honored for central admins
    (who may deliberately request "all regions" by omitting it, or any one
    region). This prevents a regional employee from pulling another
    region's report by editing the request directly.

    This helper intentionally has a report-specific name so it does not
    overwrite the existing allocation helper `_resolve_region(region_value)`.
    """
    user = request.user

    if not user.is_central_admin:
        if not user.region_id:
            return None, None
        region_id = user.region_id
    else:
        region_id = request.query_params.get('region_id') or None

    if not region_id:
        return None, None

    try:
        region_obj = Region.objects.get(pk=region_id)
        return region_id, region_obj.name
    except (Region.DoesNotExist, ValueError, TypeError):
        return region_id, None


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def student_allocation_report(request):
    """
    Legacy endpoint retained for backward compatibility.

    It delegates to the student-actions report generator - region-scoped
    the same way student_actions_report is (§9/§16), so a regional user
    cannot use the legacy URL to bypass the region restriction.
    """
    from ..domains.reports.exports import generate_student_actions_report

    region_id, region_name = _resolve_report_region(request)

    try:
        buffer = generate_student_actions_report(region_id=region_id, region_name=region_name)
    except Exception as exc:
        return error_response(status.HTTP_500_INTERNAL_SERVER_ERROR, str(exc))

    today = timezone.now().strftime('%Y-%m-%d')
    return _excel_response(
        buffer,
        f'Dormify_Student_Allocation_Report_{today}.xlsx',
    )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def student_actions_report(request):
    """Generate the student-actions report, optionally filtered by region."""
    from ..domains.reports.exports import generate_student_actions_report

    region_id, region_name = _resolve_report_region(request)

    try:
        buffer = generate_student_actions_report(
            region_id=region_id,
            region_name=region_name,
        )
    except Exception as exc:
        return error_response(status.HTTP_500_INTERNAL_SERVER_ERROR, str(exc))

    today = timezone.now().strftime('%Y-%m-%d')
    file_part = region_id or 'All_Regions'

    return _excel_response(
        buffer,
        f'Dormify_Student_Actions_Report_{file_part}_{today}.xlsx',
    )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def capacity_report(request):
    """Generate the capacity report, optionally filtered by region."""
    from ..domains.reports.exports import generate_capacity_report

    region_id, region_name = _resolve_report_region(request)

    try:
        buffer = generate_capacity_report(
            region_id=region_id,
            region_name=region_name,
        )
    except Exception as exc:
        return error_response(status.HTTP_500_INTERNAL_SERVER_ERROR, str(exc))

    today = timezone.now().strftime('%Y-%m-%d')
    file_part = region_id or 'All_Regions'

    return _excel_response(
        buffer,
        f'Dormify_Capacity_Report_{file_part}_{today}.xlsx',
    )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def manual_review_report(request):
    """Generate the manual-review report, optionally filtered by region."""
    from ..domains.reports.exports import generate_manual_review_report

    region_id, region_name = _resolve_report_region(request)

    try:
        buffer = generate_manual_review_report(
            region_id=region_id,
            region_name=region_name,
        )
    except Exception as exc:
        return error_response(status.HTTP_500_INTERNAL_SERVER_ERROR, str(exc))

    today = timezone.now().strftime('%Y-%m-%d')
    file_part = region_id or 'All_Regions'

    return _excel_response(
        buffer,
        f'Dormify_Manual_Review_Report_{file_part}_{today}.xlsx',
    )
