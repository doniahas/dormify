"""Characterization tests for the ``api.views`` package: URL topology, compatibility facade, owner modules and patch contracts."""

import ast
import importlib
import inspect
import json
import os
from pathlib import Path
import subprocess
import sys
import textwrap
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.conf import settings
from django.test import SimpleTestCase, TestCase
from django.urls import URLPattern, URLResolver, reverse
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.test import APIRequestFactory, force_authenticate
from rest_framework_simplejwt.settings import api_settings

from api import serializers, urls, views
from api.models import AllocationRun, Region, StudentRequest, User
from api.tests.characterization.test_serializers_package_characterization import VIEW_IMPORT_NAMES


ROUTER_REGISTRY = (
    ('regions', 'region', 'RegionViewSet'),
    ('dorm-types', 'dorm-type', 'DormTypeViewSet'),
    ('buildings', 'building', 'BuildingViewSet'),
    ('apartments', 'apartment', 'ApartmentViewSet'),
    ('rooms', 'room', 'RoomViewSet'),
    ('beds', 'bed', 'BedViewSet'),
    ('students', 'student', 'StudentViewSet'),
    ('transfers', 'transfer', 'TransferViewSet'),
    ('requests', 'student-request', 'StudentRequestViewSet'),
)

# regex, route name, ViewSet, raw router action map, effective HTTP methods
ROUTER_LOGICAL_ROUTES = (
    (r'^regions/$', 'region-list', 'RegionViewSet', (('get', 'list'), ('post', 'create')), ('get', 'post')),
    (r'^regions/(?P<pk>[^/.]+)/$', 'region-detail', 'RegionViewSet', (('get', 'retrieve'), ('put', 'update'), ('patch', 'partial_update'), ('delete', 'destroy')), ('get', 'put', 'patch', 'delete')),
    (r'^dorm-types/$', 'dorm-type-list', 'DormTypeViewSet', (('get', 'list'), ('post', 'create')), ('get', 'post')),
    (r'^dorm-types/(?P<pk>[^/.]+)/$', 'dorm-type-detail', 'DormTypeViewSet', (('get', 'retrieve'), ('put', 'update'), ('patch', 'partial_update'), ('delete', 'destroy')), ('get', 'put', 'patch', 'delete')),
    (r'^buildings/$', 'building-list', 'BuildingViewSet', (('get', 'list'), ('post', 'create')), ('get', 'post')),
    (r'^buildings/(?P<pk>[^/.]+)/$', 'building-detail', 'BuildingViewSet', (('get', 'retrieve'), ('put', 'update'), ('patch', 'partial_update'), ('delete', 'destroy')), ('get', 'patch')),
    (r'^buildings/(?P<pk>[^/.]+)/apartments/$', 'building-apartments', 'BuildingViewSet', (('get', 'apartments'),), ('get',)),
    (r'^buildings/(?P<pk>[^/.]+)/bulk-create-inventory/$', 'building-bulk-create-inventory', 'BuildingViewSet', (('post', 'bulk_create_inventory'),), ('post',)),
    (r'^buildings/(?P<pk>[^/.]+)/rooms/$', 'building-rooms', 'BuildingViewSet', (('get', 'rooms'),), ('get',)),
    (r'^apartments/$', 'apartment-list', 'ApartmentViewSet', (('get', 'list'), ('post', 'create')), ('get', 'post')),
    (r'^apartments/(?P<pk>[^/.]+)/$', 'apartment-detail', 'ApartmentViewSet', (('get', 'retrieve'), ('put', 'update'), ('patch', 'partial_update'), ('delete', 'destroy')), ('get', 'patch')),
    (r'^rooms/$', 'room-list', 'RoomViewSet', (('get', 'list'), ('post', 'create')), ('get', 'post')),
    (r'^rooms/(?P<pk>[^/.]+)/$', 'room-detail', 'RoomViewSet', (('get', 'retrieve'), ('put', 'update'), ('patch', 'partial_update'), ('delete', 'destroy')), ('get', 'patch')),
    (r'^beds/$', 'bed-list', 'BedViewSet', (('get', 'list'), ('post', 'create')), ('get',)),
    (r'^beds/(?P<pk>[^/.]+)/$', 'bed-detail', 'BedViewSet', (('get', 'retrieve'), ('put', 'update'), ('patch', 'partial_update'), ('delete', 'destroy')), ('get', 'patch')),
    (r'^students/$', 'student-list', 'StudentViewSet', (('get', 'list'), ('post', 'create')), ('get', 'post')),
    (r'^students/counts/$', 'student-counts', 'StudentViewSet', (('get', 'counts'),), ('get',)),
    (r'^students/filter-options/$', 'student-filter-options', 'StudentViewSet', (('get', 'filter_options'),), ('get',)),
    (r'^students/(?P<pk>[^/.]+)/$', 'student-detail', 'StudentViewSet', (('get', 'retrieve'), ('put', 'update'), ('patch', 'partial_update'), ('delete', 'destroy')), ('get', 'patch')),
    (r'^transfers/$', 'transfer-list', 'TransferViewSet', (('get', 'list'), ('post', 'create')), ('get', 'post')),
    (r'^transfers/(?P<pk>[^/.]+)/$', 'transfer-detail', 'TransferViewSet', (('get', 'retrieve'), ('put', 'update'), ('patch', 'partial_update'), ('delete', 'destroy')), ('get', 'put', 'patch')),
    (r'^transfers/(?P<pk>[^/.]+)/approve/$', 'transfer-approve', 'TransferViewSet', (('put', 'approve'),), ('put',)),
    (r'^transfers/(?P<pk>[^/.]+)/reject/$', 'transfer-reject', 'TransferViewSet', (('put', 'reject'),), ('put',)),
    (r'^requests/$', 'student-request-list', 'StudentRequestViewSet', (('get', 'list'), ('post', 'create')), ('get', 'post')),
    (r'^requests/match-options/$', 'student-request-match-options', 'StudentRequestViewSet', (('post', 'match_options'),), ('post',)),
    (r'^requests/transfer-target-regions/$', 'student-request-transfer-target-regions', 'StudentRequestViewSet', (('get', 'transfer_target_regions'),), ('get',)),
    (r'^requests/(?P<pk>[^/.]+)/$', 'student-request-detail', 'StudentRequestViewSet', (('get', 'retrieve'), ('put', 'update'), ('patch', 'partial_update'), ('delete', 'destroy')), ('get', 'put', 'patch')),
    (r'^requests/(?P<pk>[^/.]+)/approve/$', 'student-request-approve', 'StudentRequestViewSet', (('put', 'approve'),), ('put',)),
    (r'^requests/(?P<pk>[^/.]+)/cancel/$', 'student-request-cancel', 'StudentRequestViewSet', (('put', 'cancel'),), ('put',)),
    (r'^requests/(?P<pk>[^/.]+)/feasibility/$', 'student-request-feasibility', 'StudentRequestViewSet', (('get', 'feasibility'),), ('get',)),
    (r'^requests/(?P<pk>[^/.]+)/reject/$', 'student-request-reject', 'StudentRequestViewSet', (('put', 'reject'),), ('put',)),
)

# path, URL name, api.views symbol, allowed methods, permissions, throttles
EXPLICIT_ROUTES = (
    ('auth/login/', 'login', 'login_view', ('post',), ('AllowAny',), ('LoginRateThrottle',)),
    ('auth/refresh/', 'token-refresh', 'refresh_view', ('post',), ('AllowAny',), ('TokenRefreshRateThrottle',)),
    ('auth/logout/', 'logout', 'logout_view', ('post',), ('AllowAny',), ('LogoutRateThrottle',)),
    ('auth/me/', 'me', 'me_view', ('get',), ('IsAuthenticated',), ()),
    ('auth/change-password/', 'change-password', 'change_password_view', ('post', 'put'), ('IsAuthenticated',), ('SensitiveAccountActionRateThrottle',)),
    ('auth/change-email/', 'change-email', 'change_email_view', ('post', 'put'), ('IsAuthenticated',), ('SensitiveAccountActionRateThrottle',)),
    ('statistics/', 'statistics', 'statistics', ('get',), ('IsAuthenticated',), ()),
    ('home/', 'home-dashboard', 'home_dashboard', ('get',), ('IsAuthenticated',), ()),
    ('upload/excel/', 'upload-excel', 'upload_excel', ('post',), ('IsAuthenticated',), ()),
    ('upload/additions-excel/', 'upload-additions-excel', 'upload_additions_excel', ('post',), ('IsAuthenticated',), ()),
    ('batches/', 'list-batches', 'list_batches', ('get',), ('IsAuthenticated',), ()),
    ('upload/batches/init/', 'init-import-batch', 'init_import_batch', ('post',), ('IsAuthenticated',), ()),
    ('upload/batches/<int:batch_id>/status/', 'import-batch-status', 'get_import_batch_status', ('get',), ('IsAuthenticated',), ()),
    ('upload/batches/<int:batch_id>/stop/', 'import-batch-stop', 'stop_import_batch', ('post',), ('IsAuthenticated',), ()),
    ('upload/batches/<int:batch_id>/stop-and-delete/', 'import-batch-stop-and-delete', 'stop_and_delete_import_batch', ('post',), ('IsAuthenticated',), ()),
    ('upload/batches/<int:batch_id>/delete/', 'import-batch-delete', 'delete_import_batch', ('post',), ('IsAuthenticated',), ()),
    ('inbox/', 'region-inbox', 'region_inbox', ('get',), ('IsAuthenticated',), ()),
    ('inbox/latest/', 'region-inbox-latest', 'region_inbox_latest', ('get',), ('IsAuthenticated',), ()),
    ('inbox/<int:inbox_id>/viewed/', 'mark-inbox-viewed', 'mark_inbox_viewed', ('put',), ('IsAuthenticated',), ()),
    ('inbox/<int:inbox_id>/processed/', 'mark-inbox-processed', 'mark_inbox_processed', ('put',), ('IsAuthenticated',), ()),
    ('allocation/run/', 'run-allocation', 'run_allocation', ('post',), ('IsAuthenticated',), ()),
    ('allocation/history/', 'allocation-history', 'allocation_history', ('get',), ('IsAuthenticated',), ()),
    ('allocation/summary/', 'allocation-summary', 'allocation_summary', ('get',), ('IsAuthenticated',), ()),
    ('allocation/results/', 'allocation-results', 'allocation_results', ('get',), ('IsAuthenticated',), ()),
    ('allocation/start/', 'allocation-start', 'start_allocation_run', ('post',), ('IsAuthenticated',), ()),
    ('allocation/runs/active/', 'allocation-active-run', 'get_active_allocation_run', ('get',), ('IsAuthenticated',), ()),
    ('allocation/runs/<int:run_id>/', 'allocation-run-detail', 'get_allocation_run_detail', ('get',), ('IsAuthenticated',), ()),
    ('allocation/runs/<int:run_id>/preview/', 'allocation-run-preview', 'get_allocation_run_preview', ('get',), ('IsAuthenticated',), ()),
    ('allocation/runs/<int:run_id>/stop/', 'allocation-run-stop', 'stop_allocation_run', ('post',), ('IsAuthenticated',), ()),
    ('allocation/runs/<int:run_id>/stop-and-save/', 'allocation-run-stop-and-save', 'stop_and_save_allocation_run', ('post',), ('IsAuthenticated',), ()),
    ('allocation/runs/<int:run_id>/delete/', 'allocation-run-delete', 'delete_allocation_run', ('delete',), ('IsAuthenticated',), ()),
    ('allocation/runs/<int:run_id>/retry-unassigned/', 'allocation-run-retry-unassigned', 'retry_unassigned_allocation_run', ('post',), ('IsAuthenticated',), ()),
    ('analysis/', 'analysis', 'analysis_data', ('get',), ('IsAuthenticated',), ()),
    ('what-if/building-inactivation/simulate/', 'what-if-building-inactivation-simulate', 'what_if_building_inactivation_simulate', ('post',), ('IsAuthenticated',), ()),
    ('what-if/building-inactivation/confirm/', 'what-if-building-inactivation-confirm', 'what_if_building_inactivation_confirm', ('post',), ('IsAuthenticated',), ()),
    ('what-if/availability/simulate/', 'what-if-availability-simulate', 'what_if_availability_simulate', ('post',), ('IsAuthenticated',), ()),
    ('what-if/availability/confirm/', 'what-if-availability-confirm', 'what_if_availability_confirm', ('post',), ('IsAuthenticated',), ()),
    ('room-assignments/assign/', 'assign-student-room', 'assign_student_room', ('post',), ('IsAuthenticated',), ()),
    ('room-assignments/move/', 'move-student-room', 'move_student_room', ('post',), ('IsAuthenticated',), ()),
    ('room-assignments/unassign/', 'unassign-student-room', 'unassign_student_room', ('post',), ('IsAuthenticated',), ()),
    ('room-assignments/swap/', 'swap-students-rooms', 'swap_students_rooms', ('post',), ('IsAuthenticated',), ()),
    ('assisted-allocation/queue/', 'assisted-allocation-queue', 'assisted_allocation_queue', ('get',), ('IsAuthenticated',), ()),
    ('assisted-allocation/students/<int:pk>/detail/', 'assisted-allocation-student-detail', 'assisted_allocation_student_detail', ('get',), ('IsAuthenticated',), ()),
    ('assisted-allocation/students/<int:pk>/recommendations/', 'assisted-allocation-recommendations', 'assisted_allocation_recommendations', ('get',), ('IsAuthenticated',), ()),
    ('assisted-allocation/students/<int:pk>/override-check/', 'assisted-allocation-override-check', 'assisted_allocation_override_check', ('get',), ('IsAuthenticated',), ()),
    ('assisted-allocation/students/<int:pk>/assign/', 'assisted-allocation-assign', 'assisted_allocation_assign', ('post',), ('IsAuthenticated',), ()),
    ('assisted-allocation/students/<int:pk>/override/', 'assisted-allocation-override', 'assisted_allocation_override', ('post',), ('IsAuthenticated',), ()),
    ('reports/dormify-report/', 'dormify-report', 'dormify_report', ('get',), ('IsAuthenticated', 'IsCentralAdmin'), ()),
    ('reports/student-allocation-report/', 'student-allocation-report', 'student_allocation_report', ('get',), ('IsAuthenticated',), ()),
    ('reports/student-actions-report/', 'student-actions-report', 'student_actions_report', ('get',), ('IsAuthenticated',), ()),
    ('reports/capacity-report/', 'capacity-report', 'capacity_report', ('get',), ('IsAuthenticated',), ()),
    ('reports/manual-review-report/', 'manual-review-report', 'manual_review_report', ('get',), ('IsAuthenticated',), ()),
)

URL_REQUIRED_VIEW_NAMES = tuple(item[2] for item in ROUTER_REGISTRY) + tuple(
    item[2] for item in EXPLICIT_ROUTES
)

DIRECT_TEST_IMPORT_NAMES = (
    'build_student_payload_from_row',
    'validate_apartment_assignment',
    '_cleanup_run_assignments',
    '_population_summary_for_region',
    '_build_unassigned_analysis',
    'execute_allocation_run',
    'is_accessibility_priority',
    'get_free_bed',
    'StudentRequestViewSet',
    '_assignment_snapshot',
    '_student_current_region_id',
    '_user_can_cancel_request',
    '_user_can_review_request',
)

DIRECT_IMPORT_OWNER_BINDINGS = {
    'build_student_payload_from_row': 'api.domains.imports.parsing',
    'validate_apartment_assignment': 'api.domains.placement.rules',
    '_cleanup_run_assignments': 'api.domains.allocation.orchestration',
    '_population_summary_for_region': 'api.domains.allocation.orchestration',
    '_build_unassigned_analysis': 'api.domains.allocation.results',
    'execute_allocation_run': 'api.domains.allocation.orchestration',
    'is_accessibility_priority': 'api.domains.imports.parsing',
    'get_free_bed': 'api.domains.placement.beds',
    '_assignment_snapshot': 'api.domains.transfers.services',
    '_student_current_region_id': 'api.domains.transfers.services',
    '_user_can_cancel_request': 'api.domains.transfers.services',
    '_user_can_review_request': 'api.domains.transfers.services',
}

LOWER_LAYER_COMPATIBILITY_BINDINGS = {
    'api.permissions': (
        'IsCentralAdmin', 'IsBoss', 'filter_by_region', '_resolve_region',
        'resolve_scoped_region', '_region_scoped_inventory_queryset',
        '_inventory_create_permission_error',
    ),
    'api.pagination': ('StandardResultsPagination',),
    'api.domains.allocation.config': (
        'HARD_ALLOCATION_CONSTRAINTS', 'SOFT_ALLOCATION_CONSTRAINTS',
        'normalize_allocation_constraints', 'DEFAULT_CONDITIONS',
        '_CONDITIONS_STORE',
    ),
    'api.model_metadata': ('_get_model_field_names',),
    'api.domains.imports.parsing': (
        'EXCEL_DORM_NAME_TO_OFFICIAL_CODE', 'LEAVING_SHEET_NAMES',
        'COLUMN_ALIASES', 'is_blank', 'safe_str', 'safe_int', 'safe_decimal',
        'normalize_compact', 'get_row_value', 'get_alias_value',
        'normalize_phone', 'parse_yes_no_code', 'extract_roommate_flag',
        'STUDENT_HOUSING_CODE_MAP', 'normalize_student_housing_type',
        'parse_explicit_gender', '_housing_type_does_not_require_gender',
        '_gender_field_supports_empty_value',
        'validate_gender_model_for_housing_import',
        'gender_value_is_valid_for_import', 'parse_gender_from_housing_type',
        'parse_requested_religion', 'parse_placement_sector',
        'parse_religious', 'parse_category', 'get_decision_status',
        'is_positive_decision', 'get_decision_dorm_code',
        'get_decision_dorm_name', '_normalize_excel_area_code',
        '_find_dorm_type_by_code', 'get_or_create_dorm_type_from_excel',
        'read_accessibility_fields', 'is_accessibility_priority',
        '_normalize_allocation_group_value',
        'ALLOCATION_GROUP_EXCEL_COLUMN_NAME',
        'ALLOCATION_GROUP_VALUE_STAYING', 'ALLOCATION_GROUP_VALUES_NEW',
        'ALLOCATION_GROUP_VALUE_ACCESSIBILITY',
        '_ALLOCATION_GROUP_STAYING_NORMALIZED',
        '_ALLOCATION_GROUP_NEW_NORMALIZED',
        'ACCESSIBILITY_ALLOCATION_GROUP_VALUES',
        'allocation_group_indicates_accessibility',
        'allocation_group_category', 'classify_allocation_group_bucket',
        'priority_fields_from_special_statuses',
        'inject_special_status_marker', 'filter_payload_to_student_fields',
        'build_student_payload_from_row', 'get_additions_decision_status',
        'get_additions_decision_dorm_code',
        'is_additions_positive_decision',
    ),
    'api.domains.placement.beds': (
        'ensure_room_beds', '_MISSING_BED_RECORDS_MSG', 'get_free_bed',
        'get_specific_free_bed',
    ),
    'api.domains.placement.rules': (
        '_active_apartment_assignments', '_z_compatibility',
        'validate_apartment_assignment',
    ),
    'api.domains.placement.services': (
        'end_active_bed_assignments', 'assign_student_to_room',
        '_room_region', '_user_can_edit_room', '_execute_swap',
    ),
    'api.domains.matching.ranking': (
        '_infer_housing_type', 'find_matching_room_options',
    ),
    'api.domains.inventory.queries': (
        '_annotate_building_inventory_counts',
        '_annotate_apartment_inventory_counts',
        '_annotate_room_inventory_counts', '_annotate_bed_occupancy',
    ),
    'api.domains.analytics.queries': (
        '_annotate_analysis_building_occupancy', 'build_analysis_read_model',
        'build_home_dashboard_read_model', 'build_statistics_read_model',
    ),
    'api.domains.transfers.services': (
        'infer_movement_type', 'user_can_approve_transfer',
        '_user_can_review_request', '_user_can_cancel_request',
        '_student_current_region_id', '_assignment_snapshot',
        '_create_student_from_request_data',
        'finalize_student_request_creation', 'approve_student_request',
        'reject_student_request', 'cancel_student_request',
        'create_legacy_transfer', 'approve_legacy_transfer',
        'reject_legacy_transfer',
    ),
    'api.domains.allocation.orchestration': (
        '_run_diagnostics_payload', '_exclude_non_solver_students',
        '_population_summary_for_region', '_cleanup_run_assignments',
        'execute_allocation_run',
    ),
    'api.domains.allocation.results': ('_build_unassigned_analysis',),
}

INCIDENTAL_NOT_FUTURE_FACADE = (
    'Decimal', 'InvalidOperation', 're', 'Response', 'status',
    'permissions', 'transaction', 'timezone', 'pd', 'os',
    'PageNumberPagination', 'Sum', 'OuterRef', 'Subquery', 'IntegerField',
    'Case', 'When', 'Value', 'F', 'BooleanField', 'Exists', 'Coalesce',
    'Greatest', 'Office', 'StaffProfile', 'MovementRequest',
)

# The background run body is executed by the durable allocation worker
# (R8); the request-owned daemon thread and its patch targets are gone.
FUTURE_PATCH_TARGETS = {
    'api.views.StudentRequest.objects.create':
        'api.domains.whatif.services.StudentRequest.objects.create',
}

# The what-if deactivation request helper moved out of the view package in
# the R5 thin-view phase; the model-manager patch contract follows it.
WHATIF_SERVICES_MODULE = 'api.domains.whatif.services'

FUTURE_OWNER_GROUPS = {
    'auth': (
        '_set_refresh_cookie', '_clear_refresh_cookie', 'login_view',
        'refresh_view', 'logout_view', 'me_view', 'change_password_view',
        'change_email_view',
    ),
    'inventory': (
        'RegionViewSet', 'DormTypeViewSet', '_parse_is_active_filter',
        'BuildingViewSet', 'ApartmentViewSet', 'RoomViewSet', 'BedViewSet',
        'inventory_by_housing_type',
    ),
    'students': ('_latest_run_unassigned_student_ids', 'StudentViewSet'),
    'transfers': ('TransferViewSet', 'StudentRequestViewSet'),
    'allocation': (
        '_resolve_run_request_region', '_already_running_response',
        'run_allocation', 'retry_unassigned_allocation_run',
        'start_allocation_run', 'get_allocation_run_detail',
        'get_allocation_run_preview', '_user_may_stop_run',
        'stop_allocation_run', 'stop_and_save_allocation_run',
        'delete_allocation_run', 'get_active_allocation_run',
        'allocation_history', 'allocation_results', 'allocation_summary',
        'allocation_status', 'allocation_conditions',
    ),
    'assisted': (
        '_user_can_access_student_region', '_get_student_or_error',
        '_get_placement_bed_or_error', '_local_placement_blocker',
        '_placement_error_response', 'assisted_allocation_queue',
        'assisted_allocation_student_detail',
        'assisted_allocation_recommendations',
        'assisted_allocation_override_check', 'assisted_allocation_assign',
        'assisted_allocation_override',
    ),
    'analytics': ('allocation_summary', 'analysis_data', 'statistics'),
    'whatif': (
        '_what_if_get_buildings_from_request',
        '_what_if_user_can_access_buildings',
        '_what_if_get_targets_from_request',
        '_what_if_user_can_access_targets', '_what_if_error_response',
        'what_if_building_inactivation_simulate',
        'what_if_building_inactivation_confirm',
        'what_if_availability_simulate', 'what_if_availability_confirm',
    ),
    'dashboard': ('_home_action', 'home_dashboard'),
    'imports': (
        '_get_owned_batch_or_error', 'init_import_batch',
        'get_import_batch_status', 'stop_import_batch',
        'stop_and_delete_import_batch', 'delete_import_batch',
        '_validate_upload_file_or_error', '_claim_upload_batch_or_error',
        'upload_excel', 'upload_additions_excel', 'list_batches',
        'region_inbox', 'region_inbox_latest', 'mark_inbox_viewed',
        'mark_inbox_processed',
    ),
    'placement': (
        '_student_by_reference', '_get_student_from_request',
        '_get_room_from_request', 'assign_student_room', 'move_student_room',
        'unassign_student_room', 'swap_students_rooms',
    ),
    'reports': (
        '_excel_response', 'dormify_report', '_resolve_report_region',
        'student_allocation_report', 'student_actions_report',
        'capacity_report', 'manual_review_report',
    ),
}

# allocation_summary is an analytics endpoint and is intentionally listed in
# the allocation closure as well; its natural final owner is analytics.
NATURAL_FUTURE_OWNER = {
    name: owner
    for owner, names in FUTURE_OWNER_GROUPS.items()
    for name in names
}

VIEWSET_METADATA = {
    'RegionViewSet': {
        'http': ('get', 'post', 'put', 'patch', 'delete', 'head', 'options', 'trace'),
        'serializer': ('RegionSerializer', 'api.serializers.organization'),
        'pagination': None,
        'actions': (),
    },
    'DormTypeViewSet': {
        'http': ('get', 'post', 'put', 'patch', 'delete', 'head', 'options', 'trace'),
        'serializer': ('DormTypeSerializer', 'api.serializers.organization'),
        'pagination': None,
        'actions': (),
    },
    'BuildingViewSet': {
        'http': ('get', 'post', 'patch', 'head', 'options'),
        'serializer': ('BuildingSerializer', 'api.serializers.inventory'),
        'pagination': None,
        'actions': (
            ('apartments', True, (('get', 'apartments'),), 'apartments', 'apartments'),
            ('rooms', True, (('get', 'rooms'),), 'rooms', 'rooms'),
            ('bulk_create_inventory', True, (('post', 'bulk_create_inventory'),), 'bulk-create-inventory', 'bulk-create-inventory'),
        ),
    },
    'ApartmentViewSet': {
        'http': ('get', 'post', 'patch', 'head', 'options'),
        'serializer': ('ApartmentSerializer', 'api.serializers.inventory'),
        'pagination': None,
        'actions': (),
    },
    'RoomViewSet': {
        'http': ('get', 'post', 'patch', 'head', 'options'),
        'serializer': ('RoomSerializer', 'api.serializers.inventory'),
        'pagination': None,
        'actions': (),
    },
    'BedViewSet': {
        'http': ('get', 'patch', 'head', 'options'),
        'serializer': ('BedSerializer', 'api.serializers.inventory'),
        'pagination': None,
        'actions': (),
    },
    'StudentViewSet': {
        'http': ('get', 'post', 'patch', 'head', 'options'),
        'serializer': ('StudentSerializer', 'api.serializers.students'),
        'pagination': 'StandardResultsPagination',
        'actions': (
            ('counts', False, (('get', 'counts'),), 'counts', 'counts'),
            ('filter_options', False, (('get', 'filter_options'),), 'filter-options', 'filter-options'),
        ),
    },
    'TransferViewSet': {
        'http': ('get', 'post', 'put', 'patch', 'head', 'options'),
        'serializer': ('TransferSerializer', 'api.serializers.workflows'),
        'pagination': None,
        'actions': (
            ('approve', True, (('put', 'approve'),), 'approve', 'approve'),
            ('reject', True, (('put', 'reject'),), 'reject', 'reject'),
        ),
    },
    'StudentRequestViewSet': {
        'http': ('get', 'post', 'put', 'patch', 'head', 'options'),
        'serializer': ('StudentRequestSerializer', 'api.serializers.workflows'),
        'pagination': 'StandardResultsPagination',
        'actions': (
            ('transfer_target_regions', False, (('get', 'transfer_target_regions'),), 'transfer-target-regions', 'transfer-target-regions'),
            ('match_options', False, (('post', 'match_options'),), 'match-options', 'match-options'),
            ('feasibility', True, (('get', 'feasibility'),), 'feasibility', 'feasibility'),
            ('approve', True, (('put', 'approve'),), 'approve', 'approve'),
            ('reject', True, (('put', 'reject'),), 'reject', 'reject'),
            ('cancel', True, (('put', 'cancel'),), 'cancel', 'cancel'),
        ),
    },
}


def _expected_view_module(name):
    return f'api.views.{NATURAL_FUTURE_OWNER[name]}'


def _view_implementation_module(name):
    return importlib.import_module(_expected_view_module(name))


def _original_api_function(callback, expected_name):
    """Return the function wrapped by DRF's ``@api_view`` adapter."""
    expected_module = _expected_view_module(expected_name)
    method = next(
        method for method in callback.cls.http_method_names
        if method not in ('options', 'head') and hasattr(callback.cls, method)
    )
    handler = getattr(callback.cls, method)
    return next(
        cell.cell_contents for cell in (handler.__closure__ or ())
        if inspect.isfunction(cell.cell_contents)
        and cell.cell_contents.__module__ == expected_module
        and cell.cell_contents.__name__ == expected_name
    )


def _format_variant(regex):
    if regex == r'^$':
        return r'^\.(?P<format>[a-z0-9]+)/?$'
    return regex[:-2] + r'\.(?P<format>[a-z0-9]+)/?$'


def _declared_router_actions(callback):
    actions = tuple(callback.actions.items())
    action_map = dict(actions)
    if (
        'get' in action_map
        and 'head' in action_map
        and action_map['head'] == action_map['get']
    ):
        return tuple(item for item in actions if item[0] != 'head')
    return actions


def _effective_router_actions(callback):
    action_map = dict(callback.actions)
    if 'get' in action_map and 'head' not in action_map:
        action_map['head'] = action_map['get']
    return tuple(action_map.items())


def _flatten(patterns, namespaces=()):
    for pattern in patterns:
        if isinstance(pattern, URLPattern):
            yield pattern, namespaces
        elif isinstance(pattern, URLResolver):
            next_namespaces = namespaces + ((pattern.namespace,) if pattern.namespace else ())
            yield from _flatten(pattern.url_patterns, next_namespaces)


class URLTopologyTests(SimpleTestCase):
    def test_router_registry_is_exact(self):
        observed = tuple(
            (prefix, basename, viewset.__name__)
            for prefix, viewset, basename in urls.router.registry
        )
        self.assertEqual(observed, ROUTER_REGISTRY)
        for prefix, viewset, basename in urls.router.registry:
            expected_name = dict((p, n) for p, _b, n in ROUTER_REGISTRY)[prefix]
            self.assertIs(viewset, getattr(views, expected_name))

    def test_explicit_path_snapshot_is_exact(self):
        explicit = tuple(p for p in urls.urlpatterns if isinstance(p, URLPattern))
        self.assertEqual(len(explicit), 52)
        observed = tuple(
            (
                str(pattern.pattern), pattern.name,
                pattern.callback.cls.__name__,
                frozenset(m for m in pattern.callback.cls.http_method_names if m != 'options'),
                tuple(c.__name__ for c in pattern.callback.cls.permission_classes),
                tuple(
                    c.__name__ for c in pattern.callback.cls.throttle_classes
                ) if 'throttle_classes' in pattern.callback.cls.__dict__ else (),
            )
            for pattern in explicit
        )
        expected = tuple(
            (path, name, symbol, frozenset(methods), permissions, throttles)
            for path, name, symbol, methods, permissions, throttles in EXPLICIT_ROUTES
        )
        self.assertEqual(observed, expected)

    def test_router_logical_and_format_suffix_patterns_are_exact(self):
        expected = []
        for regex, name, class_name, actions, _effective in ROUTER_LOGICAL_ROUTES:
            expected.extend((
                (regex, name, class_name, actions),
                (_format_variant(regex), name, class_name, actions),
            ))
        expected.extend((
            ('', 'api-root', 'APIRootView', None),
            ('<drf_format_suffix:format>', 'api-root', 'APIRootView', None),
        ))
        observed = tuple(
            (
                str(pattern.pattern), pattern.name, pattern.callback.cls.__name__,
                _declared_router_actions(pattern.callback)
                if hasattr(pattern.callback, 'actions') else None,
            )
            for pattern in urls.router.urls
        )
        self.assertEqual(observed, tuple(expected))
        api_root_patterns = tuple(
            pattern for pattern in urls.router.urls if pattern.name == 'api-root'
        )
        self.assertEqual(
            tuple(pattern.pattern.regex.pattern for pattern in api_root_patterns),
            (r'^\Z', r'^(?P<format>\.[a-z0-9]+/?)\Z'),
        )

    def test_logical_and_concrete_route_counts_are_exact(self):
        list_detail = tuple(
            route for route in ROUTER_LOGICAL_ROUTES
            if route[1].endswith(('-list', '-detail'))
        )
        actions = tuple(
            route for route in ROUTER_LOGICAL_ROUTES
            if not route[1].endswith(('-list', '-detail'))
        )
        self.assertEqual(len(list_detail), 18)
        self.assertEqual(len(actions), 13)
        self.assertEqual(len(ROUTER_LOGICAL_ROUTES), 31)
        self.assertEqual(len(EXPLICIT_ROUTES) + len(ROUTER_LOGICAL_ROUTES), 83)
        self.assertEqual(len(EXPLICIT_ROUTES) + len(ROUTER_LOGICAL_ROUTES) + 1, 84)
        flattened = tuple(_flatten(urls.urlpatterns))
        self.assertEqual(len(flattened), 116)
        self.assertEqual(len(urls.router.urls), 64)
        self.assertTrue(any(pattern.name == 'api-root' for pattern, _ in flattened))
        self.assertTrue(all(namespaces == () for _pattern, namespaces in flattened))

    def test_router_raw_actions_and_effective_methods_are_exact(self):
        unsuffixed = {
            str(pattern.pattern): pattern
            for pattern in urls.router.urls
            if '<format>' not in str(pattern.pattern) and pattern.name != 'api-root'
        }
        for regex, _name, class_name, actions, effective in ROUTER_LOGICAL_ROUTES:
            with self.subTest(regex=regex):
                pattern = unsuffixed[regex]
                self.assertIs(pattern.callback.cls, getattr(views, class_name))
                self.assertEqual(_declared_router_actions(pattern.callback), actions)
                expected_runtime_actions = dict(actions)
                if 'get' in expected_runtime_actions:
                    expected_runtime_actions['head'] = expected_runtime_actions['get']
                self.assertEqual(
                    _effective_router_actions(pattern.callback),
                    tuple(expected_runtime_actions.items()),
                )
                allowed = set(pattern.callback.cls.http_method_names)
                observed_effective = tuple(method for method, _action in actions if method in allowed)
                self.assertEqual(observed_effective, effective)

    def test_dynamic_reverse_contracts_are_exact(self):
        self.assertEqual(reverse('building-detail', kwargs={'pk': 17}), '/api/buildings/17/')
        self.assertEqual(reverse('allocation-run-detail', kwargs={'run_id': 23}), '/api/allocation/runs/23/')
        self.assertEqual(reverse('import-batch-status', kwargs={'batch_id': 29}), '/api/upload/batches/29/status/')
        self.assertEqual(reverse('mark-inbox-viewed', kwargs={'inbox_id': 31}), '/api/inbox/31/viewed/')


class URLFacadeManifestTests(SimpleTestCase):
    def test_exact_ordered_61_name_manifest_exists(self):
        self.assertEqual(len(URL_REQUIRED_VIEW_NAMES), 61)
        self.assertEqual(len(set(URL_REQUIRED_VIEW_NAMES)), 61)
        for name in URL_REQUIRED_VIEW_NAMES:
            with self.subTest(name=name):
                self.assertTrue(hasattr(views, name))

    def test_every_url_callback_resolves_to_the_facade_object(self):
        for prefix, viewset, _basename in urls.router.registry:
            expected_name = next(name for item_prefix, _base, name in ROUTER_REGISTRY if item_prefix == prefix)
            self.assertIs(viewset, getattr(views, expected_name))
        explicit = tuple(p for p in urls.urlpatterns if isinstance(p, URLPattern))
        for pattern, expected in zip(explicit, EXPLICIT_ROUTES):
            with self.subTest(name=pattern.name):
                self.assertEqual(pattern.name, expected[1])
                self.assertIs(pattern.callback, getattr(views, expected[2]))


class CompatibilityManifestTests(SimpleTestCase):
    def test_13_direct_test_import_names_and_owner_identities(self):
        self.assertEqual(len(DIRECT_TEST_IMPORT_NAMES), 13)
        for name in DIRECT_TEST_IMPORT_NAMES:
            with self.subTest(name=name):
                self.assertTrue(hasattr(views, name))
                if name in DIRECT_IMPORT_OWNER_BINDINGS:
                    owner = importlib.import_module(DIRECT_IMPORT_OWNER_BINDINGS[name])
                    self.assertIs(getattr(views, name), getattr(owner, name))

    def test_serializer_manifest_is_reused_and_object_identical(self):
        self.assertEqual(len(VIEW_IMPORT_NAMES), 18)
        for name in VIEW_IMPORT_NAMES:
            with self.subTest(name=name):
                self.assertIs(getattr(views, name), getattr(serializers, name))

    def test_lower_layer_compatibility_bindings_are_object_identical(self):
        for module_name, names in LOWER_LAYER_COMPATIBILITY_BINDINGS.items():
            owner = importlib.import_module(module_name)
            for name in names:
                with self.subTest(owner=module_name, name=name):
                    self.assertIs(getattr(views, name), getattr(owner, name))

    def test_incidental_implementation_bindings_are_not_in_manifest(self):
        supported = (
            set(URL_REQUIRED_VIEW_NAMES)
            | set(DIRECT_TEST_IMPORT_NAMES)
            | set(VIEW_IMPORT_NAMES)
            | {
                name
                for names in LOWER_LAYER_COMPATIBILITY_BINDINGS.values()
                for name in names
            }
        )
        self.assertTrue(set(INCIDENTAL_NOT_FUTURE_FACADE).isdisjoint(supported))
        self.assertNotIn('threading', vars(views))
        self.assertIn('StudentRequest', vars(views))
        self.assertNotIn('StudentRequest', supported)


class ViewSetMetadataTests(SimpleTestCase):
    def test_all_nine_viewsets_have_exact_structural_metadata(self):
        self.assertEqual(tuple(VIEWSET_METADATA), tuple(item[2] for item in ROUTER_REGISTRY))
        for name, expected in VIEWSET_METADATA.items():
            with self.subTest(name=name):
                cls = getattr(views, name)
                self.assertEqual(cls.__name__, name)
                self.assertEqual(cls.__module__, _expected_view_module(name))
                self.assertEqual(tuple(cls.http_method_names), expected['http'])
                self.assertEqual(tuple(cls.permission_classes), (IsAuthenticated,))
                self.assertNotIn('authentication_classes', cls.__dict__)
                self.assertNotIn('throttle_classes', cls.__dict__)
                self.assertNotIn('parser_classes', cls.__dict__)
                self.assertIsNone(getattr(cls, 'queryset', None))
                serializer_class = cls.serializer_class
                self.assertEqual(
                    (serializer_class.__name__, serializer_class.__module__),
                    expected['serializer'],
                )
                pagination = getattr(cls, 'pagination_class', None)
                self.assertEqual(
                    pagination.__name__ if pagination else None,
                    expected['pagination'],
                )

    def test_action_decorator_metadata_is_exact(self):
        for class_name, expected in VIEWSET_METADATA.items():
            cls = getattr(views, class_name)
            observed = tuple(
                (
                    name, method.detail, tuple(method.mapping.items()),
                    method.url_path, method.url_name,
                )
                for name, method in cls.__dict__.items()
                if hasattr(method, 'mapping')
            )
            with self.subTest(class_name=class_name):
                self.assertEqual(observed, expected['actions'])

    def test_student_serializer_selection_is_exact(self):
        view = views.StudentViewSet()
        view.action = 'list'
        self.assertIs(view.get_serializer_class(), serializers.StudentListSerializer)
        for action_name in ('retrieve', 'create', 'partial_update', 'counts', 'filter_options'):
            with self.subTest(action=action_name):
                view.action = action_name
                self.assertIs(view.get_serializer_class(), serializers.StudentSerializer)

    def test_http_lockdown_metadata_is_exact(self):
        expected = {
            'BuildingViewSet': ('get', 'post', 'patch', 'head', 'options'),
            'ApartmentViewSet': ('get', 'post', 'patch', 'head', 'options'),
            'RoomViewSet': ('get', 'post', 'patch', 'head', 'options'),
            'BedViewSet': ('get', 'patch', 'head', 'options'),
            'StudentViewSet': ('get', 'post', 'patch', 'head', 'options'),
            'TransferViewSet': ('get', 'post', 'put', 'patch', 'head', 'options'),
            'StudentRequestViewSet': ('get', 'post', 'put', 'patch', 'head', 'options'),
        }
        for name, method_names in expected.items():
            with self.subTest(name=name):
                self.assertEqual(tuple(getattr(views, name).http_method_names), method_names)


class ExplicitViewMetadataTests(SimpleTestCase):
    def test_all_52_explicit_views_have_exact_decorator_metadata(self):
        explicit = tuple(p for p in urls.urlpatterns if isinstance(p, URLPattern))
        self.assertEqual(len(explicit), len(EXPLICIT_ROUTES))
        for pattern, expected in zip(explicit, EXPLICIT_ROUTES):
            path, name, symbol, methods, permissions, throttles = expected
            with self.subTest(name=name):
                callback = getattr(views, symbol)
                expected_module = _expected_view_module(symbol)
                self.assertEqual(str(pattern.pattern), path)
                self.assertEqual(pattern.name, name)
                self.assertIs(pattern.callback, callback)
                self.assertEqual(callback.__module__, expected_module)
                self.assertEqual(callback.cls.__module__, expected_module)
                self.assertEqual(callback.cls.__name__, symbol)
                self.assertEqual(
                    frozenset(m for m in callback.cls.http_method_names if m != 'options'),
                    frozenset(methods),
                )
                self.assertEqual(tuple(c.__name__ for c in callback.cls.permission_classes), permissions)
                observed_throttles = tuple(
                    c.__name__ for c in callback.cls.throttle_classes
                ) if 'throttle_classes' in callback.cls.__dict__ else ()
                self.assertEqual(observed_throttles, throttles)
                original = _original_api_function(callback, symbol)
                self.assertFalse(hasattr(original, 'authentication_classes'))
                self.assertFalse(hasattr(original, 'parser_classes'))

    def test_auth_metadata_contract_is_explicit(self):
        expected = {
            'login_view': (('post',), (AllowAny,), ('LoginRateThrottle',)),
            'refresh_view': (('post',), (AllowAny,), ('TokenRefreshRateThrottle',)),
            'logout_view': (('post',), (AllowAny,), ('LogoutRateThrottle',)),
            'me_view': (('get',), (IsAuthenticated,), ()),
            'change_password_view': (('post', 'put'), (IsAuthenticated,), ('SensitiveAccountActionRateThrottle',)),
            'change_email_view': (('post', 'put'), (IsAuthenticated,), ('SensitiveAccountActionRateThrottle',)),
        }
        for name, (methods, permissions, throttles) in expected.items():
            callback = getattr(views, name)
            with self.subTest(name=name):
                self.assertEqual(
                    frozenset(m for m in callback.cls.http_method_names if m != 'options'),
                    frozenset(methods),
                )
                self.assertEqual(tuple(callback.cls.permission_classes), permissions)
                observed = tuple(c.__name__ for c in callback.cls.throttle_classes) if 'throttle_classes' in callback.cls.__dict__ else ()
                self.assertEqual(observed, throttles)


class AuthCookieStructureTests(SimpleTestCase):
    def test_refresh_cookie_uses_the_configured_structural_contract(self):
        response = Response()
        with patch.object(response, 'set_cookie') as set_cookie:
            views._set_refresh_cookie(response, 'opaque-refresh-token')
        set_cookie.assert_called_once_with(
            settings.JWT_REFRESH_COOKIE_NAME,
            'opaque-refresh-token',
            max_age=int(api_settings.REFRESH_TOKEN_LIFETIME.total_seconds()),
            httponly=True,
            secure=settings.JWT_REFRESH_COOKIE_SECURE,
            samesite=settings.JWT_REFRESH_COOKIE_SAMESITE,
            path=settings.JWT_REFRESH_COOKIE_PATH,
            domain=settings.JWT_REFRESH_COOKIE_DOMAIN,
        )

    def test_refresh_cookie_clear_uses_configured_name_and_scope(self):
        response = Response()
        with patch.object(response, 'delete_cookie') as delete_cookie:
            views._clear_refresh_cookie(response)
        delete_cookie.assert_called_once_with(
            settings.JWT_REFRESH_COOKIE_NAME,
            path=settings.JWT_REFRESH_COOKIE_PATH,
            domain=settings.JWT_REFRESH_COOKIE_DOMAIN,
            samesite=settings.JWT_REFRESH_COOKIE_SAMESITE,
        )


class UnroutedCompatibilityEndpointTests(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.admin = User.objects.create_user(
            username='views-char-admin', email='views-char-admin@example.test',
            password='x', role=User.Role.CENTRAL_ADMIN,
        )
        self.saved_conditions = dict(views._CONDITIONS_STORE)
        views._CONDITIONS_STORE.clear()

    def tearDown(self):
        views._CONDITIONS_STORE.clear()
        views._CONDITIONS_STORE.update(self.saved_conditions)
        super().tearDown()

    def _get(self, callback):
        request = self.factory.get('/compatibility-only/')
        force_authenticate(request, user=self.admin)
        return callback(request)

    def test_unrouted_metadata_and_absence_from_urlconf(self):
        names = ('allocation_status', 'inventory_by_housing_type', 'allocation_conditions')
        routed = {item[2] for item in EXPLICIT_ROUTES}
        for name in names:
            with self.subTest(name=name):
                callback = getattr(views, name)
                expected_module = _expected_view_module(name)
                self.assertNotIn(name, routed)
                self.assertEqual(callback.__module__, expected_module)
                self.assertEqual(callback.cls.__module__, expected_module)
                self.assertEqual(tuple(callback.cls.permission_classes), (IsAuthenticated,))
                if name == 'inventory_by_housing_type':
                    implementation_module = _view_implementation_module(name)
                    self.assertIs(callback, getattr(implementation_module, name))
        self.assertEqual(
            tuple(m for m in views.allocation_status.cls.http_method_names if m != 'options'),
            ('get',),
        )
        self.assertEqual(
            tuple(m for m in views.inventory_by_housing_type.cls.http_method_names if m != 'options'),
            ('get',),
        )
        self.assertEqual(
            frozenset(m for m in views.allocation_conditions.cls.http_method_names if m != 'options'),
            frozenset(('get', 'put')),
        )

    def test_unrouted_minimal_responses_are_exact(self):
        allocation = self._get(views.allocation_status)
        self.assertEqual(allocation.status_code, 200)
        self.assertEqual(allocation.data, {'status': 'not_started', 'run': None, 'region': None})

        inventory = self._get(views.inventory_by_housing_type)
        self.assertEqual(inventory.status_code, 200)
        self.assertEqual(inventory.data, {'region': None, 'inventory': []})

        conditions = self._get(views.allocation_conditions)
        self.assertEqual(conditions.status_code, 200)
        self.assertEqual(conditions.data, {'region': None, 'conditions': views.DEFAULT_CONDITIONS})


class PatchTransparencyTests(TestCase):
    def setUp(self):
        self.region = Region.objects.create(id='views_char', name='Views Characterization')
        self.boss = User.objects.create_user(
            username='views-char-boss', email='views-char-boss@example.test',
            password='x', role=User.Role.REGION_BOSS, region=self.region,
        )
        self.factory = APIRequestFactory()

    def test_start_allocation_queues_a_durable_run_without_executing(self):
        # Since R8 the request creates the durable QUEUED run and returns;
        # the allocation worker executes it in its own process, so neither
        # a thread nor the run body may be invoked here.
        request = self.factory.post('/api/allocation/start/', {'max_solver_seconds': 45}, format='json')
        force_authenticate(request, user=self.boss)
        with patch('api.views.allocation.refresh_db_connection'), \
                patch('threading.Thread') as thread, \
                patch('api.domains.allocation.orchestration.execute_allocation_run') as execute:
            response = views.start_allocation_run(request)
        self.assertEqual(response.status_code, 202)
        thread.assert_not_called()
        execute.assert_not_called()
        run = AllocationRun.objects.get(pk=response.data['run_id'])
        self.assertEqual(run.region_id, self.region.id)
        self.assertEqual(run.status, AllocationRun.Status.QUEUED)
        self.assertEqual(run.claimed_by, '')
        self.assertIsNone(run.lease_expires_at)
        self.assertEqual(run.job_parameters, {
            'constraints_config': views.DEFAULT_CONDITIONS,
            'include_assigned': False,
            'allocation_scope': None,
            'max_seconds': 45.0,
        })

    def test_facade_run_body_is_the_orchestration_object(self):
        orchestration = importlib.import_module('api.domains.allocation.orchestration')
        self.assertIs(views.execute_allocation_run, orchestration.execute_allocation_run)
        self.assertFalse(hasattr(orchestration, 'threading'))

    def test_facade_model_manager_patch_intercepts_whatif_helper_lookup(self):
        student = SimpleNamespace(id=901)
        assignment = SimpleNamespace(student=student)
        created = MagicMock(id=42)
        implementation_module = importlib.import_module(WHATIF_SERVICES_MODULE)
        with patch.object(
            implementation_module.StudentRequest.objects, 'filter'
        ) as filter_mock, patch(
            f'{implementation_module.__name__}.StudentRequest.objects.create',
            return_value=created,
        ) as create, patch.object(
            implementation_module, '_student_current_region_id',
            return_value='views_char',
        ), patch.object(
            implementation_module, '_assignment_snapshot', return_value={'bed': 7}
        ):
            filter_mock.return_value.exists.return_value = False
            result = implementation_module.create_deactivation_transfer_request(
                assignment, 'characterization', self.boss,
            )
        self.assertIs(result, created)
        create.assert_called_once()
        self.assertIs(create.call_args.kwargs['student'], student)
        created.save.assert_called_once_with(update_fields=['request_number'])
        self.assertEqual(created.request_number, 'REQ-000042')


class FutureOwnershipContractTests(SimpleTestCase):
    def test_approved_future_patch_target_map_is_data_only(self):
        self.assertEqual(FUTURE_PATCH_TARGETS, {
            'api.views.StudentRequest.objects.create': 'api.domains.whatif.services.StudentRequest.objects.create',
        })
        for future_target in FUTURE_PATCH_TARGETS.values():
            self.assertIsInstance(future_target, str)

    def test_final_owner_map_is_fully_extracted(self):
        definition_types = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
        implementation_types = definition_types + (ast.Assign, ast.AnnAssign)

        def top_level(module, node_types):
            tree = ast.parse(inspect.getsource(module))
            return [node for node in tree.body if isinstance(node, node_types)]

        owners = {
            'auth', 'students', 'inventory', 'whatif', 'placement',
            'transfers', 'imports', 'allocation', 'assisted', 'analytics',
            'dashboard', 'reports',
        }
        self.assertEqual(set(FUTURE_OWNER_GROUPS), owners)
        self.assertEqual(set(NATURAL_FUTURE_OWNER.values()), owners)
        self.assertEqual(NATURAL_FUTURE_OWNER['allocation_summary'], 'analytics')
        self.assertEqual(NATURAL_FUTURE_OWNER['statistics'], 'analytics')

        # The facade only re-exports: it defines no functions, classes or
        # module-level state of its own.
        self.assertEqual(
            [ast.unparse(node).splitlines()[0] for node in top_level(views, implementation_types)],
            [],
        )

        mapped_definitions = set(NATURAL_FUTURE_OWNER)
        supported_facade_names = (
            set(URL_REQUIRED_VIEW_NAMES)
            | set(DIRECT_TEST_IMPORT_NAMES)
            | set(VIEW_IMPORT_NAMES)
            | {
                name
                for names in LOWER_LAYER_COMPATIBILITY_BINDINGS.values()
                for name in names
            }
        )
        for owner in sorted(owners):
            with self.subTest(owner=owner):
                owner_module = importlib.import_module(f'api.views.{owner}')
                self.assertEqual(owner_module.__spec__.parent, 'api.views')
                expected_definitions = {
                    name for name in mapped_definitions
                    if NATURAL_FUTURE_OWNER[name] == owner
                }
                definitions = {
                    node.name for node in top_level(owner_module, definition_types)
                }
                self.assertEqual(definitions, expected_definitions)
                for name in expected_definitions:
                    implementation = getattr(owner_module, name)
                    self.assertEqual(implementation.__module__, f'api.views.{owner}')
                    if name in supported_facade_names:
                        self.assertIs(getattr(views, name), implementation)

    def test_current_global_ownership_is_patch_sensitive(self):
        start_module = _view_implementation_module('start_allocation_run')
        self.assertEqual(
            views.start_allocation_run.__module__,
            start_module.__name__,
        )
        start_original = _original_api_function(
            views.start_allocation_run,
            'start_allocation_run',
        )
        self.assertIs(start_original.__globals__, start_module.__dict__)
        runs_module = importlib.import_module('api.domains.allocation.runs')
        self.assertIs(
            start_original.__globals__['create_run_for_region'],
            runs_module.create_run_for_region,
        )
        implementation_module = importlib.import_module(WHATIF_SERVICES_MODULE)
        helper = implementation_module.create_deactivation_transfer_request
        self.assertEqual(helper.__module__, implementation_module.__name__)
        self.assertIs(helper.__globals__, implementation_module.__dict__)
        self.assertIs(
            helper.__globals__['StudentRequest'],
            implementation_module.StudentRequest,
        )
        self.assertIs(implementation_module.StudentRequest, StudentRequest)


class FreshImportTimingTests(SimpleTestCase):
    databases = set()

    def run_fresh_python(self, source):
        completed = subprocess.run(
            [sys.executable, '-c', textwrap.dedent(source)],
            cwd=str(settings.BASE_DIR),
            env=os.environ.copy(),
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(
            completed.returncode,
            0,
            msg=(
                f'fresh process failed\nstdout:\n{completed.stdout}\n'
                f'stderr:\n{completed.stderr}'
            ),
        )
        lines = [line for line in completed.stdout.splitlines() if line]
        self.assertTrue(lines, msg='fresh process produced no JSON output')
        return json.loads(lines[-1])

    def test_each_fresh_import_keeps_solver_stacks_unloaded(self):
        for target in ('api.views', 'api.urls', 'api.serializers'):
            with self.subTest(target=target):
                result = self.run_fresh_python(f"""
                    import importlib
                    import json
                    import os
                    import sys
                    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'dormify.settings')
                    import django
                    django.setup()
                    importlib.import_module({target!r})
                    blocked = sorted(
                        name for name in sys.modules
                        if name == 'allocation'
                        or name.startswith('allocation.')
                        or name.startswith('ortools')
                        or name.startswith('google.protobuf')
                    )
                    print(json.dumps({{'blocked': blocked}}))
                """)
                self.assertEqual(result['blocked'], [])

    def test_lazy_allocation_gateway_exports_remain_unresolved_at_import_time(self):
        result = self.run_fresh_python("""
            import importlib
            import json
            import os
            import sys
            os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'dormify.settings')
            import django
            django.setup()
            importlib.import_module('api.views')
            gateway = importlib.import_module('api.domains.allocation.gateway')
            unresolved = sorted(name for name in gateway.__all__ if name not in vars(gateway))
            blocked = sorted(
                name for name in sys.modules
                if name == 'allocation'
                or name.startswith('allocation.')
                or name.startswith('ortools')
                or name.startswith('google.protobuf')
            )
            print(json.dumps({
                'unresolved': unresolved,
                'declared': sorted(gateway.__all__),
                'blocked': blocked,
            }))
        """)
        self.assertEqual(result['unresolved'], result['declared'])
        self.assertEqual(result['blocked'], [])


class FilePackagePreconditionTests(SimpleTestCase):
    def test_current_views_is_a_package_and_file_does_not_exist(self):
        backend = Path(settings.BASE_DIR)
        forbidden_file = backend / 'api' / 'views.py'
        expected_package = backend / 'api' / 'views'
        expected_init = expected_package / '__init__.py'
        self.assertFalse(forbidden_file.exists())
        self.assertTrue(expected_package.is_dir())
        self.assertTrue(expected_init.is_file())
        self.assertEqual(Path(views.__file__).resolve(), expected_init.resolve())
