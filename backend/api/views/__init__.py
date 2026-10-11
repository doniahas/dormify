"""Compatibility facade for the ``api.views`` package.

View implementations live in this package's owner modules. This module only
re-exports, as the exact owner objects, the names that form the supported
``api.views`` surface: the views routed by ``api.urls``, names imported from
``api.views`` by tests, and the serializer and lower-layer bindings kept for
backward compatibility.
"""

# Lower-layer compatibility bindings.
from ..permissions import (
    IsCentralAdmin, IsBoss, filter_by_region,
    _resolve_region, resolve_scoped_region,
    _region_scoped_inventory_queryset, _inventory_create_permission_error,
)
from ..pagination import StandardResultsPagination
from ..domains.allocation.config import (
    HARD_ALLOCATION_CONSTRAINTS, SOFT_ALLOCATION_CONSTRAINTS,
    normalize_allocation_constraints, DEFAULT_CONDITIONS, _CONDITIONS_STORE,
)
from ..model_metadata import _get_model_field_names
from ..domains.imports.parsing import (
    EXCEL_DORM_NAME_TO_OFFICIAL_CODE, LEAVING_SHEET_NAMES, COLUMN_ALIASES, is_blank, safe_str,
    safe_int, safe_decimal, normalize_compact, get_row_value, get_alias_value, normalize_phone,
    parse_yes_no_code, extract_roommate_flag, STUDENT_HOUSING_CODE_MAP,
    normalize_student_housing_type, parse_explicit_gender, _housing_type_does_not_require_gender,
    _gender_field_supports_empty_value, validate_gender_model_for_housing_import,
    gender_value_is_valid_for_import, parse_gender_from_housing_type, parse_requested_religion,
    parse_placement_sector, parse_religious, parse_category, get_decision_status,
    is_positive_decision, get_decision_dorm_code, get_decision_dorm_name,
    _normalize_excel_area_code, _find_dorm_type_by_code, get_or_create_dorm_type_from_excel,
    read_accessibility_fields, is_accessibility_priority, _normalize_allocation_group_value,
    ALLOCATION_GROUP_EXCEL_COLUMN_NAME, ALLOCATION_GROUP_VALUE_STAYING, ALLOCATION_GROUP_VALUES_NEW,
    ALLOCATION_GROUP_VALUE_ACCESSIBILITY, _ALLOCATION_GROUP_STAYING_NORMALIZED,
    _ALLOCATION_GROUP_NEW_NORMALIZED, ACCESSIBILITY_ALLOCATION_GROUP_VALUES,
    allocation_group_indicates_accessibility, allocation_group_category,
    classify_allocation_group_bucket, priority_fields_from_special_statuses,
    inject_special_status_marker, filter_payload_to_student_fields, build_student_payload_from_row,
    get_additions_decision_status, get_additions_decision_dorm_code, is_additions_positive_decision,
)
from ..domains.placement.beds import (
    ensure_room_beds, _MISSING_BED_RECORDS_MSG, get_free_bed, get_specific_free_bed,
)
from ..domains.placement.rules import (
    _active_apartment_assignments, _z_compatibility, validate_apartment_assignment,
)
from ..domains.placement.services import (
    end_active_bed_assignments,
    assign_student_to_room,
    _room_region,
    _user_can_edit_room,
    _execute_swap,
)
from ..domains.matching.ranking import (
    _infer_housing_type,
    find_matching_room_options,
)
from ..domains.inventory.queries import (
    _annotate_building_inventory_counts,
    _annotate_apartment_inventory_counts,
    _annotate_room_inventory_counts,
    _annotate_bed_occupancy,
)
from ..domains.analytics.queries import (
    _annotate_analysis_building_occupancy,
    build_analysis_read_model,
    build_home_dashboard_read_model,
    build_statistics_read_model,
)
from ..domains.transfers.services import (
    infer_movement_type,
    user_can_approve_transfer,
    _user_can_review_request,
    _user_can_cancel_request,
    _student_current_region_id,
    _assignment_snapshot,
    _create_student_from_request_data,
    finalize_student_request_creation,
    approve_student_request,
    reject_student_request,
    cancel_student_request,
    create_legacy_transfer,
    approve_legacy_transfer,
    reject_legacy_transfer,
)
from ..domains.allocation.orchestration import (
    _run_diagnostics_payload,
    _exclude_non_solver_students,
    _population_summary_for_region,
    _cleanup_run_assignments,
    execute_allocation_run,
)
from ..domains.allocation.results import _build_unassigned_analysis

# Kept for the views characterization contract, which asserts it is bound here.
from ..models import StudentRequest
from ..serializers import (
    UserSerializer, LoginSerializer,
    RegionSerializer, DormTypeSerializer, BuildingSerializer, ApartmentSerializer,
    RoomSerializer, BedSerializer, StudentSerializer, StudentListSerializer, TransferSerializer,
    StudentRequestSerializer,
    AllocationRunSerializer, ImportBatchSerializer, RegionInboxSerializer,
    check_building_write_conflict, check_apartment_write_conflict, check_room_write_conflict,
)

# View implementations, re-exported from their owner modules.
from .auth import (
    _clear_refresh_cookie,
    _set_refresh_cookie,
    change_email_view,
    change_password_view,
    login_view,
    logout_view,
    me_view,
    refresh_view,
)
from .inventory import (
    ApartmentViewSet,
    BedViewSet,
    BuildingViewSet,
    DormTypeViewSet,
    RegionViewSet,
    RoomViewSet,
    inventory_by_housing_type,
)
from .students import StudentViewSet
from .transfers import (
    StudentRequestViewSet,
    TransferViewSet,
)
from .placement import (
    assign_student_room,
    move_student_room,
    swap_students_rooms,
    unassign_student_room,
)
from .imports import (
    MAX_UPLOAD_FILE_SIZE_BYTES,
    delete_import_batch,
    get_import_batch_status,
    init_import_batch,
    list_batches,
    mark_inbox_processed,
    mark_inbox_viewed,
    region_inbox,
    region_inbox_latest,
    stop_and_delete_import_batch,
    stop_import_batch,
    upload_additions_excel,
    upload_excel,
)
from .allocation import (
    allocation_conditions,
    allocation_history,
    allocation_results,
    allocation_status,
    delete_allocation_run,
    get_active_allocation_run,
    get_allocation_run_detail,
    get_allocation_run_preview,
    retry_unassigned_allocation_run,
    run_allocation,
    start_allocation_run,
    stop_allocation_run,
    stop_and_save_allocation_run,
)
from .assisted import (
    assisted_allocation_assign,
    assisted_allocation_override,
    assisted_allocation_override_check,
    assisted_allocation_queue,
    assisted_allocation_recommendations,
    assisted_allocation_student_detail,
)
from .analytics import (
    allocation_summary,
    analysis_data,
    statistics,
)
from .dashboard import home_dashboard
from .whatif import (
    what_if_availability_confirm,
    what_if_availability_simulate,
    what_if_building_inactivation_confirm,
    what_if_building_inactivation_simulate,
)
from .reports import (
    capacity_report,
    dormify_report,
    manual_review_report,
    student_actions_report,
    student_allocation_report,
)
