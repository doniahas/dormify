"""Step 12A characterization tests for the legacy api.serializers module."""

import json
import os
import subprocess
import sys
import textwrap
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import PropertyMock, patch

from django.test import SimpleTestCase, TestCase
from django.utils import timezone
from rest_framework.exceptions import ErrorDetail, PermissionDenied, ValidationError
from rest_framework.fields import empty
from rest_framework.relations import ManyRelatedField

from api import serializers as serializer_module
from api import views
from api.models import (
    AllocationRun, Apartment, Bed, BedAssignment, Building, DormType,
    ImportBatch, MovementRequest, Office, Region, RegionInbox, Room,
    StaffProfile, Student, StudentRequest, Transfer, User,
)


SERIALIZER_NAMES = (
    'UserSerializer', 'LoginSerializer', 'RegionSerializer',
    'DormTypeSerializer', 'OfficeSerializer', 'StaffProfileSerializer',
    'BuildingSerializer', 'ApartmentSerializer', 'RoomSerializer',
    'BedSerializer', 'StudentListSerializer', 'StudentSerializer',
    'BedAssignmentSerializer', 'MovementRequestSerializer',
    'TransferSerializer', 'StudentRequestSerializer',
    'AllocationRunSerializer', 'ImportBatchSerializer',
    'RegionInboxSerializer',
)

PUBLIC_HELPER_NAMES = (
    'check_building_write_conflict',
    'check_apartment_write_conflict',
    'check_room_write_conflict',
)

# Module dictionary insertion order reflects the legacy source order. The
# first DormTypeSerializer establishes its slot and the second replaces it.
LEGACY_SOURCE_EXPORT_MANIFEST = (
    'UserSerializer', 'LoginSerializer', 'RegionSerializer',
    'OfficeSerializer', 'StaffProfileSerializer', 'DormTypeSerializer',
    'check_building_write_conflict',
    'check_apartment_write_conflict',
    'check_room_write_conflict',
    'BuildingSerializer', 'ApartmentSerializer', 'RoomSerializer',
    'BedSerializer', 'StudentListSerializer', 'StudentSerializer',
    'BedAssignmentSerializer', 'MovementRequestSerializer',
    'TransferSerializer', 'StudentRequestSerializer',
    'AllocationRunSerializer', 'ImportBatchSerializer',
    'RegionInboxSerializer',
)

VIEW_IMPORT_NAMES = (
    'UserSerializer', 'LoginSerializer', 'RegionSerializer',
    'DormTypeSerializer', 'BuildingSerializer', 'ApartmentSerializer',
    'RoomSerializer', 'BedSerializer', 'StudentSerializer',
    'StudentListSerializer', 'TransferSerializer',
    'StudentRequestSerializer', 'AllocationRunSerializer',
    'ImportBatchSerializer', 'RegionInboxSerializer',
) + PUBLIC_HELPER_NAMES

EXPECTED_FIELDS = {
    'UserSerializer': (
        'id', 'email', 'username', 'first_name', 'last_name', 'full_name',
        'role', 'role_display', 'region', 'region_name', 'phone', 'is_active',
        'date_joined', 'is_central_admin', 'is_boss',
    ),
    'LoginSerializer': ('email', 'password'),
    'RegionSerializer': ('id', 'name'),
    'DormTypeSerializer': ('id', 'code', 'name', 'region', 'region_name'),
    'OfficeSerializer': (
        'id', 'name', 'office_type', 'office_type_display', 'region',
        'region_name',
    ),
    'StaffProfileSerializer': (
        'id', 'user', 'user_email', 'user_full_name', 'role', 'role_display',
        'office', 'office_name',
    ),
    'BuildingSerializer': (
        'id', 'number', 'dorm_type', 'dorm_type_name', 'dorm_type_code',
        'region', 'region_name', 'is_active', 'gender_restriction',
        'gender_restriction_display', 'apartment_count', 'room_count',
        'bed_count', 'occupied_beds', 'free_beds',
    ),
    'ApartmentSerializer': (
        'id', 'building', 'building_number', 'number', 'category',
        'category_display', 'apartment_type', 'apartment_type_display',
        'room_count', 'actual_room_count', 'apartment_capacity', 'bed_count',
        'occupied_beds', 'free_beds', 'is_active', 'inactive_reason',
        'inactive_reason_display', 'region', 'region_name', 'dorm_type',
    ),
    'RoomSerializer': (
        'id', 'apartment', 'apartment_number', 'building_number', 'region',
        'region_name', 'name', 'number', 'capacity', 'bed_count',
        'current_occupancy', 'available_beds', 'is_full', 'is_active',
        'has_missing_bed_records',
    ),
    'BedSerializer': (
        'id', 'label', 'room', 'room_name', 'apartment_number',
        'building_number', 'is_occupied',
    ),
    'StudentListSerializer': (
        'id', 'student_id', 'business_partner_id', 'first_name', 'last_name',
        'full_name', 'email', 'phone', 'gender', 'gender_display',
        'requested_religion', 'requested_religion_display', 'category',
        'category_display', 'housing_type', 'accepted_dorm_type',
        'accepted_dorm_type_name', 'accepted_dorm_type_code', 'is_priority',
        'priority_reason', 'assigned_room', 'is_assigned', 'current_building',
        'current_apartment', 'current_room', 'current_bed',
    ),
    'StudentSerializer': (
        'id', 'student_id', 'business_partner_id', 'first_name', 'last_name',
        'full_name', 'email', 'email_secondary', 'phone', 'phone_secondary',
        'city', 'gender', 'gender_display', 'requested_religion',
        'requested_religion_display', 'religious', 'religious_display',
        'category', 'category_display', 'housing_type', 'housing_gender',
        'allocation_group', 'accepted_dorm_type', 'accepted_dorm_type_name',
        'accepted_dorm_type_code', 'region_id', 'region_name', 'batch',
        'batch_id', 'roommate_request_1', 'roommate_request_2',
        'roommate_request_3', 'roommate_request_4', 'roommate_request_5',
        'roommate_request_flag_1', 'roommate_request_flag_2',
        'roommate_request_flag_3', 'roommate_request_flag_4',
        'roommate_request_flag_5', 'special_status_1', 'special_status_2',
        'special_status_3', 'special_status_4', 'is_priority',
        'priority_reason', 'accessibility_flag', 'disability_percent',
        'medical_reason', 'study_points', 'current_address',
        'current_dorm_type', 'move_in_date', 'move_out_date', 'assigned_room',
        'assigned_room_id', 'assigned_room_name', 'assigned_building_number',
        'assigned_apartment_number', 'is_assigned', 'current_bed_id',
        'current_bed_label', 'created_at', 'updated_at',
    ),
    'BedAssignmentSerializer': (
        'id', 'student', 'student_name', 'student_id_number', 'bed',
        'bed_label', 'room_name', 'apartment_number', 'building_number',
        'status', 'status_display', 'assignment_type',
        'assignment_type_display', 'assigned_by', 'assigned_by_name',
        'assigned_at', 'ended_at',
    ),
    'MovementRequestSerializer': (
        'id', 'student', 'student_name', 'from_assignment',
        'from_assignment_id', 'from_bed_label', 'to_bed', 'to_bed_label',
        'movement_type', 'movement_type_display', 'status', 'status_display',
        'reason', 'requested_by', 'requested_by_name', 'approved_by',
        'approved_by_name', 'created_at', 'reviewed_at', 'completed_at',
    ),
    'TransferSerializer': (
        'id', 'student', 'student_name', 'student_id_number', 'from_room',
        'from_room_name', 'from_building_number', 'from_apartment_number',
        'to_room', 'to_room_name', 'to_building_number',
        'to_apartment_number', 'reason', 'status', 'status_display',
        'requested_by', 'requested_by_name', 'requested_by_region_name',
        'reviewed_by', 'reviewed_by_name', 'reviewed_at', 'rejection_reason',
        'movement_request', 'created_at', 'updated_at',
    ),
    'StudentRequestSerializer': (
        'id', 'request_number', 'request_type', 'request_type_display',
        'reason', 'status', 'status_display', 'priority', 'priority_display',
        'other_description', 'same_apartment', 'removal_notes',
        'removal_reason', 'student', 'student_name', 'student_id_number',
        'student_phone', 'student_data', 'target_room', 'target_room_name',
        'target_building_number', 'target_apartment_number',
        'swap_with_student', 'swap_with_student_name',
        'swap_with_student_id_number', 'target_region', 'target_region_name',
        'transfer_scope', 'transfer_scope_display', 'source_region',
        'source_region_name', 'destination_regions',
        'destination_region_names', 'current_assignment_snapshot',
        'final_assignment', 'final_bed_label', 'current_region',
        'current_building', 'current_apartment', 'current_room', 'current_bed',
        'placement_history', 'requested_by', 'requested_by_name',
        'reviewed_by', 'reviewed_by_name', 'reviewed_at', 'rejection_reason',
        'created_at', 'updated_at',
    ),
    'AllocationRunSerializer': (
        'id', 'region', 'region_name', 'run_by', 'run_by_name', 'status',
        'status_display', 'students_processed', 'successful_assignments',
        'roommate_matches', 'conflicts', 'max_search_seconds',
        'search_started_at', 'elapsed_search_seconds',
        'remaining_search_seconds', 'started_at', 'completed_at',
        'error_message',
    ),
    'ImportBatchSerializer': (
        'id', 'uploaded_by', 'uploaded_by_name', 'kind', 'filename',
        'total_students', 'status', 'status_display', 'error_message',
        'created_at', 'started_at', 'finished_at', 'total_rows',
        'processed_rows', 'result', 'region_breakdown',
    ),
    'RegionInboxSerializer': (
        'id', 'region', 'region_name', 'batch', 'batch_filename',
        'batch_created_at', 'students_count', 'status', 'status_display',
        'message', 'created_at', 'viewed_at', 'processed_at',
    ),
}

EXPECTED_READ_ONLY_FIELDS = {
    'UserSerializer': (
        'id', 'date_joined', 'full_name', 'is_central_admin', 'is_boss',
    ),
    'BedSerializer': ('room',),
    'StudentSerializer': (
        'id', 'full_name', 'housing_gender', 'is_assigned',
        'current_bed_id', 'current_bed_label', 'created_at', 'updated_at',
        'assigned_room',
    ),
    'BedAssignmentSerializer': ('id', 'assigned_at'),
    'MovementRequestSerializer': ('id', 'created_at'),
    'TransferSerializer': (
        'id', 'created_at', 'updated_at', 'status', 'reviewed_by',
        'reviewed_at', 'rejection_reason', 'requested_by',
        'movement_request',
    ),
    'StudentRequestSerializer': (
        'id', 'request_number', 'status', 'source_region',
        'current_assignment_snapshot', 'final_assignment', 'requested_by',
        'reviewed_by', 'reviewed_at', 'rejection_reason', 'created_at',
        'updated_at',
    ),
    'AllocationRunSerializer': ('id', 'started_at'),
    'ImportBatchSerializer': ('id', 'created_at'),
    'RegionInboxSerializer': ('id', 'created_at'),
}

EXPECTED_DECLARED_FIELDS = {
    'UserSerializer': (
        'role_display', 'region_name', 'full_name', 'is_central_admin',
        'is_boss',
    ),
    'LoginSerializer': ('email', 'password'),
    'RegionSerializer': (),
    'DormTypeSerializer': ('region_name',),
    'OfficeSerializer': ('office_type_display', 'region_name'),
    'StaffProfileSerializer': (
        'user_email', 'user_full_name', 'role_display', 'office_name',
    ),
    'BuildingSerializer': (
        'dorm_type_name', 'dorm_type_code', 'region', 'region_name',
        'gender_restriction_display', 'apartment_count', 'room_count',
        'bed_count', 'occupied_beds', 'free_beds',
    ),
    'ApartmentSerializer': (
        'building_number', 'category_display', 'apartment_type_display',
        'inactive_reason_display', 'region', 'region_name', 'dorm_type',
        'actual_room_count', 'bed_count', 'occupied_beds', 'free_beds',
    ),
    'RoomSerializer': (
        'apartment_number', 'building_number', 'region', 'region_name',
        'number', 'current_occupancy', 'available_beds', 'is_full',
        'bed_count', 'has_missing_bed_records',
    ),
    'BedSerializer': (
        'room_name', 'apartment_number', 'building_number', 'is_occupied',
    ),
    'StudentListSerializer': (
        'full_name', 'gender_display', 'requested_religion_display',
        'category_display', 'accepted_dorm_type_name',
        'accepted_dorm_type_code', 'is_assigned', 'current_building',
        'current_apartment', 'current_room', 'current_bed',
    ),
    'StudentSerializer': (
        'full_name', 'gender_display', 'requested_religion_display',
        'religious_display', 'category_display', 'accepted_dorm_type_name',
        'accepted_dorm_type_code', 'region_id', 'region_name',
        'assigned_room_name', 'assigned_room_id',
        'assigned_building_number', 'assigned_apartment_number',
        'housing_gender', 'is_assigned', 'current_bed_id',
        'current_bed_label', 'batch_id',
    ),
    'BedAssignmentSerializer': (
        'student_name', 'student_id_number', 'bed_label', 'room_name',
        'apartment_number', 'building_number', 'status_display',
        'assignment_type_display', 'assigned_by_name',
    ),
    'MovementRequestSerializer': (
        'student_name', 'from_assignment_id', 'from_bed_label',
        'to_bed_label', 'movement_type_display', 'status_display',
        'requested_by_name', 'approved_by_name',
    ),
    'TransferSerializer': (
        'student_name', 'student_id_number', 'from_room_name', 'to_room_name',
        'status_display', 'requested_by_region_name',
        'from_building_number', 'from_apartment_number',
        'to_building_number', 'to_apartment_number', 'requested_by_name',
        'reviewed_by_name',
    ),
    'StudentRequestSerializer': (
        'request_type_display', 'status_display', 'priority_display',
        'student_name', 'student_id_number', 'student_phone',
        'requested_by_name', 'reviewed_by_name', 'target_room_name',
        'target_building_number', 'target_apartment_number',
        'swap_with_student_name', 'swap_with_student_id_number',
        'target_region_name', 'transfer_scope_display', 'source_region_name',
        'destination_regions', 'destination_region_names', 'final_bed_label',
        'current_region', 'current_building', 'current_apartment',
        'current_room', 'current_bed', 'placement_history',
    ),
    'AllocationRunSerializer': (
        'region_name', 'run_by_name', 'status_display',
        'elapsed_search_seconds', 'remaining_search_seconds',
    ),
    'ImportBatchSerializer': (
        'uploaded_by_name', 'status_display', 'region_breakdown',
    ),
    'RegionInboxSerializer': (
        'region_name', 'batch_filename', 'batch_created_at', 'status_display',
    ),
}

METHOD_FIELD_NAMES = {
    'UserSerializer': ('full_name',),
    'StaffProfileSerializer': ('user_full_name',),
    'BuildingSerializer': (
        'apartment_count', 'room_count', 'bed_count', 'occupied_beds',
        'free_beds',
    ),
    'ApartmentSerializer': (
        'actual_room_count', 'bed_count', 'occupied_beds', 'free_beds',
    ),
    'RoomSerializer': (
        'current_occupancy', 'available_beds', 'is_full', 'bed_count',
        'has_missing_bed_records',
    ),
    'BedSerializer': ('is_occupied',),
    'StudentListSerializer': (
        'current_building', 'current_apartment', 'current_room', 'current_bed',
    ),
    'StudentSerializer': ('current_bed_id', 'current_bed_label'),
    'BedAssignmentSerializer': ('assigned_by_name',),
    'MovementRequestSerializer': ('requested_by_name', 'approved_by_name'),
    'TransferSerializer': ('requested_by_name', 'reviewed_by_name'),
    'StudentRequestSerializer': (
        'student_name', 'requested_by_name', 'reviewed_by_name',
        'destination_region_names', 'current_region', 'current_building',
        'current_apartment', 'current_room', 'current_bed',
        'placement_history',
    ),
    'AllocationRunSerializer': (
        'run_by_name', 'elapsed_search_seconds', 'remaining_search_seconds',
    ),
    'ImportBatchSerializer': ('uploaded_by_name', 'region_breakdown'),
}

INTEGER_FIELD_NAMES = {
    'BuildingSerializer': ('dorm_type_code',),
    'ApartmentSerializer': ('building_number',),
    'RoomSerializer': ('building_number',),
    'BedSerializer': ('building_number',),
    'StudentListSerializer': ('accepted_dorm_type_code',),
    'StudentSerializer': (
        'accepted_dorm_type_code', 'assigned_room_id',
        'assigned_building_number', 'batch_id',
    ),
    'BedAssignmentSerializer': ('building_number',),
    'MovementRequestSerializer': ('from_assignment_id',),
    'TransferSerializer': ('from_building_number', 'to_building_number'),
    'StudentRequestSerializer': ('target_building_number',),
}

BOOLEAN_FIELD_NAMES = {
    'UserSerializer': ('is_central_admin', 'is_boss'),
    'StudentListSerializer': ('is_assigned',),
    'StudentSerializer': ('is_assigned',),
}

DATETIME_FIELD_NAMES = {'RegionInboxSerializer': ('batch_created_at',)}
EMAIL_FIELD_NAMES = {'LoginSerializer': ('email',)}

EXPLICIT_SOURCES = {
    'UserSerializer': {
        'role_display': 'get_role_display', 'region_name': 'region.name',
    },
    'DormTypeSerializer': {'region_name': 'region.name'},
    'OfficeSerializer': {
        'office_type_display': 'get_office_type_display',
        'region_name': 'region.name',
    },
    'StaffProfileSerializer': {
        'user_email': 'user.email', 'role_display': 'get_role_display',
        'office_name': 'office.name',
    },
    'BuildingSerializer': {
        'dorm_type_name': 'dorm_type.name',
        'dorm_type_code': 'dorm_type.code',
        'region': 'dorm_type.region.id',
        'region_name': 'dorm_type.region.name',
        'gender_restriction_display': 'get_gender_restriction_display',
    },
    'ApartmentSerializer': {
        'building_number': 'building.number',
        'category_display': 'get_category_display',
        'apartment_type_display': 'get_apartment_type_display',
        'inactive_reason_display': 'get_inactive_reason_display',
        'region': 'region.id', 'region_name': 'region.name',
        'dorm_type': 'dorm_type.name',
    },
    'RoomSerializer': {
        'apartment_number': 'apartment.number',
        'building_number': 'building.number', 'region': 'region.id',
        'region_name': 'region.name',
    },
    'BedSerializer': {
        'room_name': 'room.name',
        'apartment_number': 'room.apartment.number',
        'building_number': 'room.apartment.building.number',
    },
    'StudentListSerializer': {
        'gender_display': 'get_gender_display',
        'requested_religion_display': 'get_requested_religion_display',
        'category_display': 'get_category_display',
        'accepted_dorm_type_name': 'accepted_dorm_type.name',
        'accepted_dorm_type_code': 'accepted_dorm_type.code',
    },
    'StudentSerializer': {
        'gender_display': 'get_gender_display',
        'requested_religion_display': 'get_requested_religion_display',
        'religious_display': 'get_religious_display',
        'category_display': 'get_category_display',
        'accepted_dorm_type_name': 'accepted_dorm_type.name',
        'accepted_dorm_type_code': 'accepted_dorm_type.code',
        'region_id': 'accepted_dorm_type.region_id',
        'region_name': 'accepted_dorm_type.region.name',
        'assigned_room_name': 'assigned_room.name',
        'assigned_room_id': 'assigned_room.id',
        'assigned_building_number': 'assigned_room.apartment.building.number',
        'assigned_apartment_number': 'assigned_room.apartment.number',
        'batch_id': 'batch.id',
    },
    'BedAssignmentSerializer': {
        'student_name': 'student.full_name',
        'student_id_number': 'student.student_id',
        'bed_label': 'bed.label', 'room_name': 'bed.room.name',
        'apartment_number': 'bed.room.apartment.number',
        'building_number': 'bed.room.apartment.building.number',
        'status_display': 'get_status_display',
        'assignment_type_display': 'get_assignment_type_display',
    },
    'MovementRequestSerializer': {
        'student_name': 'student.full_name',
        'from_assignment_id': 'from_assignment.id',
        'from_bed_label': 'from_assignment.bed.label',
        'to_bed_label': 'to_bed.label',
        'movement_type_display': 'get_movement_type_display',
        'status_display': 'get_status_display',
    },
    'TransferSerializer': {
        'student_name': 'student.full_name',
        'student_id_number': 'student.student_id',
        'from_room_name': 'from_room.name', 'to_room_name': 'to_room.name',
        'status_display': 'get_status_display',
        'requested_by_region_name': 'requested_by.region.name',
        'from_building_number': 'from_room.apartment.building.number',
        'from_apartment_number': 'from_room.apartment.number',
        'to_building_number': 'to_room.apartment.building.number',
        'to_apartment_number': 'to_room.apartment.number',
    },
    'StudentRequestSerializer': {
        'request_type_display': 'get_request_type_display',
        'status_display': 'get_status_display',
        'priority_display': 'get_priority_display',
        'student_id_number': 'student.student_id',
        'student_phone': 'student.phone',
        'target_room_name': 'target_room.name',
        'target_building_number': 'target_room.apartment.building.number',
        'target_apartment_number': 'target_room.apartment.number',
        'swap_with_student_name': 'swap_with_student.full_name',
        'swap_with_student_id_number': 'swap_with_student.student_id',
        'target_region_name': 'target_region.name',
        'transfer_scope_display': 'get_transfer_scope_display',
        'source_region_name': 'source_region.name',
        'final_bed_label': 'final_assignment.bed.label',
    },
    'AllocationRunSerializer': {
        'region_name': 'region.name', 'status_display': 'get_status_display',
    },
    'ImportBatchSerializer': {'status_display': 'get_status_display'},
    'RegionInboxSerializer': {
        'region_name': 'region.name', 'batch_filename': 'batch.filename',
        'batch_created_at': 'batch.created_at',
        'status_display': 'get_status_display',
    },
}

NONE_DEFAULT_FIELDS = {
    'StudentSerializer': ('region_id', 'region_name'),
    'StudentRequestSerializer': (
        'student_id_number', 'student_phone', 'target_room_name',
        'target_building_number', 'target_apartment_number',
        'swap_with_student_name', 'swap_with_student_id_number',
        'target_region_name', 'transfer_scope_display', 'source_region_name',
        'final_bed_label',
    ),
}


def plain_detail(value):
    if isinstance(value, dict):
        return {key: plain_detail(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain_detail(item) for item in value]
    return str(value)


def assert_validation_error(testcase, serializer, attrs, expected):
    with testcase.assertRaises(ValidationError) as caught:
        serializer.validate(attrs)
    testcase.assertEqual(plain_detail(caught.exception.detail), expected)


class SerializerPublicSurfaceTests(SimpleTestCase):
    def test_effective_public_names_are_importable(self):
        for name in SERIALIZER_NAMES + PUBLIC_HELPER_NAMES:
            with self.subTest(name=name):
                self.assertTrue(hasattr(serializer_module, name))

    def test_exact_legacy_source_export_manifest(self):
        supported = set(SERIALIZER_NAMES + PUBLIC_HELPER_NAMES)
        observed = tuple(
            name for name in vars(serializer_module) if name in supported
        )
        self.assertEqual(observed, LEGACY_SOURCE_EXPORT_MANIFEST)

    def test_views_bindings_are_object_identical(self):
        for name in VIEW_IMPORT_NAMES:
            with self.subTest(name=name):
                self.assertIs(
                    getattr(views, name), getattr(serializer_module, name),
                )

    def test_effective_dorm_type_serializer_contract(self):
        serializer_class = serializer_module.DormTypeSerializer
        self.assertEqual(serializer_class.__name__, 'DormTypeSerializer')
        self.assertEqual(serializer_class.__module__, 'api.serializers.organization')
        self.assertEqual(serializer_class.__doc__, 'Serialize dorm type data')
        self.assertIs(serializer_class.Meta.model, DormType)
        self.assertEqual(
            tuple(serializer_class().fields),
            ('id', 'code', 'name', 'region', 'region_name'),
        )


class SerializerFieldContractTests(SimpleTestCase):
    def test_exact_field_order_for_all_effective_serializers(self):
        self.assertEqual(tuple(EXPECTED_FIELDS), SERIALIZER_NAMES)
        for name, expected in EXPECTED_FIELDS.items():
            with self.subTest(serializer=name):
                self.assertEqual(
                    tuple(getattr(serializer_module, name)().fields),
                    expected,
                )

    def test_exact_explicit_declared_field_names(self):
        for name, expected in EXPECTED_DECLARED_FIELDS.items():
            with self.subTest(serializer=name):
                serializer_class = getattr(serializer_module, name)
                self.assertEqual(tuple(serializer_class._declared_fields), expected)

    def test_explicit_declared_field_metadata(self):
        for serializer_name, declared_names in EXPECTED_DECLARED_FIELDS.items():
            serializer = getattr(serializer_module, serializer_name)()
            method_names = set(METHOD_FIELD_NAMES.get(serializer_name, ()))
            integer_names = set(INTEGER_FIELD_NAMES.get(serializer_name, ()))
            boolean_names = set(BOOLEAN_FIELD_NAMES.get(serializer_name, ()))
            datetime_names = set(DATETIME_FIELD_NAMES.get(serializer_name, ()))
            email_names = set(EMAIL_FIELD_NAMES.get(serializer_name, ()))
            none_defaults = set(NONE_DEFAULT_FIELDS.get(serializer_name, ()))
            explicit_sources = EXPLICIT_SOURCES.get(serializer_name, {})

            for field_name in declared_names:
                with self.subTest(serializer=serializer_name, field=field_name):
                    field = serializer.fields[field_name]
                    if field_name == 'destination_regions':
                        expected_class = 'ManyRelatedField'
                    elif field_name in method_names:
                        expected_class = 'SerializerMethodField'
                    elif field_name in integer_names:
                        expected_class = 'IntegerField'
                    elif field_name in boolean_names:
                        expected_class = 'BooleanField'
                    elif field_name in datetime_names:
                        expected_class = 'DateTimeField'
                    elif field_name in email_names:
                        expected_class = 'EmailField'
                    else:
                        expected_class = 'CharField'
                    self.assertEqual(type(field).__name__, expected_class)

                    expected_source = (
                        '*' if field_name in method_names
                        else explicit_sources.get(field_name, field_name)
                    )
                    self.assertEqual(field.source, expected_source)
                    writable = (
                        serializer_name == 'LoginSerializer'
                        or (
                            serializer_name == 'StudentRequestSerializer'
                            and field_name == 'destination_regions'
                        )
                    )
                    self.assertEqual(field.read_only, not writable)
                    self.assertEqual(
                        field.write_only,
                        serializer_name == 'LoginSerializer'
                        and field_name == 'password',
                    )
                    self.assertEqual(
                        field.required,
                        serializer_name == 'LoginSerializer',
                    )
                    self.assertEqual(
                        field.allow_null,
                        serializer_name == 'StudentSerializer'
                        and field_name == 'batch_id',
                    )
                    if field_name in none_defaults:
                        self.assertIsNone(field.default)
                    else:
                        self.assertIs(field.default, empty)
                    if field_name == 'destination_regions':
                        self.assertIsInstance(field, ManyRelatedField)
                        self.assertFalse(field.required)
                        self.assertIs(
                            field.child_relation.queryset.model, Region,
                        )

    def test_explicit_meta_read_only_and_login_write_only_contracts(self):
        for serializer_name, expected in EXPECTED_READ_ONLY_FIELDS.items():
            with self.subTest(serializer=serializer_name):
                serializer_class = getattr(serializer_module, serializer_name)
                self.assertEqual(
                    tuple(serializer_class.Meta.read_only_fields), expected,
                )
                serializer = serializer_class()
                for field_name in expected:
                    self.assertTrue(serializer.fields[field_name].read_only)
        login = serializer_module.LoginSerializer()
        self.assertTrue(login.fields['password'].write_only)
        self.assertFalse(login.fields['email'].write_only)


class SerializerFixtureMixin:
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.region = Region.objects.create(
            id='serializer-char', name='Serializer Region',
        )
        cls.other_region = Region.objects.create(
            id='serializer-char-other', name='Other Serializer Region',
        )
        cls.dorm_type = DormType.objects.create(
            code=8121, name='Serializer Dorm', region=cls.region,
        )
        cls.other_dorm_type = DormType.objects.create(
            code=8122, name='Other Serializer Dorm', region=cls.other_region,
        )
        cls.building = Building.objects.create(
            number=41, dorm_type=cls.dorm_type,
        )
        cls.other_building = Building.objects.create(
            number=42, dorm_type=cls.dorm_type,
        )
        cls.apartment = Apartment.objects.create(
            building=cls.building,
            number='A-1',
            category=Apartment.Category.MALE,
            apartment_type=Apartment.ApartmentType.SINGLE,
            room_count=2,
            apartment_capacity=3,
        )
        cls.other_apartment = Apartment.objects.create(
            building=cls.other_building,
            number='B-1',
            category=Apartment.Category.MALE,
            apartment_type=Apartment.ApartmentType.SINGLE,
            room_count=1,
            apartment_capacity=2,
        )
        cls.room = Room.objects.create(
            apartment=cls.apartment, name='101', capacity=2,
        )
        cls.other_room = Room.objects.create(
            apartment=cls.other_apartment, name='201', capacity=2,
        )
        cls.bed = Bed.objects.create(room=cls.room, label='Bed 1')
        cls.spare_bed = Bed.objects.create(room=cls.room, label='Bed 2')
        cls.other_bed = Bed.objects.create(
            room=cls.other_room, label='Bed 1',
        )
        cls.user = User.objects.create_user(
            username='serializer-admin',
            email='serializer-admin@example.com',
            password='characterization-password',
            first_name='Admin',
            last_name='Characterizer',
            role=User.Role.CENTRAL_ADMIN,
            region=cls.region,
        )
        cls.employee = User.objects.create_user(
            username='serializer-employee',
            email='serializer-employee@example.com',
            password='characterization-password',
            first_name='Regional',
            last_name='Employee',
            role=User.Role.EMPLOYEE,
            region=cls.region,
        )
        cls.office = Office.objects.create(
            name='Serializer Office',
            office_type=Office.OfficeType.REGIONAL,
            region=cls.region,
        )
        cls.staff_profile = StaffProfile.objects.create(
            user=cls.employee,
            role=StaffProfile.StaffRole.EMPLOYEE,
            office=cls.office,
        )
        cls.student = Student.objects.create(
            student_id='SER-1001',
            first_name='Student',
            last_name='Character',
            email='student@example.com',
            phone='0501234567',
            gender=Student.Gender.MALE,
            requested_religion=Student.Religion.Jewish,
            religious=Student.Religious.RELIGIOUS,
            category=Student.StudentCategory.NEW,
            housing_type=Student.HousingType.SINGLE_MALE,
            accepted_dorm_type=cls.dorm_type,
            assigned_room=cls.room,
        )
        cls.other_student = Student.objects.create(
            student_id='SER-1002',
            first_name='Other',
            last_name='Student',
            gender=Student.Gender.MALE,
            category=Student.StudentCategory.NEW,
            housing_type=Student.HousingType.SINGLE_MALE,
            accepted_dorm_type=cls.dorm_type,
        )
        cls.assignment = BedAssignment.objects.create(
            student=cls.student,
            bed=cls.bed,
            status=BedAssignment.Status.ACTIVE,
            assignment_type=BedAssignment.AssignmentType.MANUAL,
            assigned_by=cls.user,
        )
        cls.movement = MovementRequest.objects.create(
            student=cls.student,
            from_assignment=cls.assignment,
            to_bed=cls.other_bed,
            movement_type=MovementRequest.MovementType.INTERNAL,
            status=MovementRequest.Status.PENDING,
            reason='Characterization move',
            requested_by=cls.employee,
        )
        cls.transfer = Transfer.objects.create(
            student=cls.student,
            from_room=cls.room,
            to_room=cls.other_room,
            reason='Characterization transfer',
            requested_by=cls.employee,
            movement_request=cls.movement,
        )
        cls.allocation_run = AllocationRun.objects.create(
            region=cls.region,
            run_by=cls.user,
            status=AllocationRun.Status.QUEUED,
            max_search_seconds=30,
        )
        cls.import_batch = ImportBatch.objects.create(
            uploaded_by=cls.user,
            kind=ImportBatch.Kind.MAIN,
            filename='students.xlsx',
            total_students=3,
            status=ImportBatch.Status.PENDING,
            total_rows=3,
            processed_rows=0,
            result={'created': 0},
        )
        cls.inbox = RegionInbox.objects.create(
            region=cls.region,
            batch=cls.import_batch,
            students_count=3,
            status=RegionInbox.Status.PENDING,
            message='Ready',
        )
        cls.student_request = StudentRequest.objects.create(
            request_type=StudentRequest.RequestType.OTHER,
            reason='Characterization request',
            student=cls.student,
            requested_by=cls.employee,
            target_room=cls.other_room,
            swap_with_student=cls.other_student,
            target_region=cls.other_region,
            transfer_scope=StudentRequest.TransferScope.SAME_REGION,
            source_region=cls.region,
            current_assignment_snapshot={'bed': cls.bed.label},
            final_assignment=cls.assignment,
            request_number='REQ-SERIALIZER-1',
        )
        cls.student_request.destination_regions.add(cls.other_region)


class LoginAndOfficeValidationTests(SerializerFixtureMixin, TestCase):
    def assert_office_direct_and_public_errors(
        self,
        *,
        direct_serializer,
        direct_attrs,
        public_serializer,
        message,
    ):
        with self.assertRaises(ValidationError) as caught:
            direct_serializer.validate(direct_attrs)
        self.assertEqual(tuple(caught.exception.detail), ('region',))
        direct_detail = caught.exception.detail['region']
        self.assertIsInstance(direct_detail, ErrorDetail)
        self.assertEqual(str(direct_detail), message)
        self.assertEqual(direct_detail.code, 'invalid')

        self.assertFalse(public_serializer.is_valid())
        self.assertEqual(tuple(public_serializer.errors), ('region',))
        public_details = public_serializer.errors['region']
        self.assertIsInstance(public_details, list)
        self.assertEqual(len(public_details), 1)
        self.assertIsInstance(public_details[0], ErrorDetail)
        self.assertEqual(str(public_details[0]), message)
        self.assertEqual(public_details[0].code, 'invalid')

    def test_login_missing_credentials_branch_has_exact_non_field_error(self):
        serializer = serializer_module.LoginSerializer()
        assert_validation_error(
            self,
            serializer,
            {},
            ['נדרש אימייל וסיסמה'],
        )

    def test_login_failed_authentication_has_exact_non_field_error(self):
        serializer = serializer_module.LoginSerializer()
        with patch('api.serializers.auth.authenticate', return_value=None):
            assert_validation_error(
                self,
                serializer,
                {'email': 'nobody@example.com', 'password': 'wrong'},
                ['אימייל או סיסמה שגויים'],
            )

    def test_login_inactive_user_has_exact_non_field_error(self):
        inactive = SimpleNamespace(is_active=False)
        serializer = serializer_module.LoginSerializer()
        with patch('api.serializers.auth.authenticate', return_value=inactive):
            assert_validation_error(
                self,
                serializer,
                {'email': 'inactive@example.com', 'password': 'password'},
                ['המשתמש אינו פעיל'],
            )

    def test_login_success_places_user_in_validated_data(self):
        serializer = serializer_module.LoginSerializer()
        payload = {
            'email': self.user.email,
            'password': 'characterization-password',
        }
        with patch('api.serializers.auth.authenticate', return_value=self.user):
            validated = serializer.validate(payload.copy())
        self.assertEqual(validated['email'], self.user.email)
        self.assertIs(validated['user'], self.user)

    def test_office_rejects_regional_without_region(self):
        self.assert_office_direct_and_public_errors(
            direct_serializer=serializer_module.OfficeSerializer(),
            direct_attrs={
                'office_type': Office.OfficeType.REGIONAL,
                'region': None,
            },
            public_serializer=serializer_module.OfficeSerializer(data={
                'name': 'Invalid regional office',
                'office_type': Office.OfficeType.REGIONAL,
                'region': None,
            }),
            message='Regional office must have a region.',
        )

    def test_office_rejects_central_with_region(self):
        self.assert_office_direct_and_public_errors(
            direct_serializer=serializer_module.OfficeSerializer(),
            direct_attrs={
                'office_type': Office.OfficeType.CENTRAL,
                'region': self.region,
            },
            public_serializer=serializer_module.OfficeSerializer(data={
                'name': 'Invalid central office',
                'office_type': Office.OfficeType.CENTRAL,
                'region': self.region.pk,
            }),
            message='Central office should not be linked to a region.',
        )

    def test_office_accepts_valid_combinations(self):
        serializer = serializer_module.OfficeSerializer()
        regional = {
            'office_type': Office.OfficeType.REGIONAL,
            'region': self.region,
        }
        central = {
            'office_type': Office.OfficeType.CENTRAL,
            'region': None,
        }
        self.assertEqual(serializer.validate(regional.copy()), regional)
        self.assertEqual(serializer.validate(central.copy()), central)

    def test_office_partial_update_uses_instance_fallback(self):
        serializer = serializer_module.OfficeSerializer(
            instance=self.office,
            partial=True,
        )
        self.assertEqual(serializer.validate({'name': 'Renamed'}), {
            'name': 'Renamed',
        })
        self.assert_office_direct_and_public_errors(
            direct_serializer=serializer,
            direct_attrs={'region': None},
            public_serializer=serializer_module.OfficeSerializer(
                instance=self.office,
                data={'region': None},
                partial=True,
            ),
            message='Regional office must have a region.',
        )


class InventoryFlatErrorHelperTests(SerializerFixtureMixin, TestCase):
    availability_message = (
        'שינוי סטטוס פעיל/לא פעיל מתבצע רק דרך תהליך "שינוי זמינות" '
        '(/api/what-if/availability/), הכולל אזהרת השפעה על דיירים קיימים.'
    )

    def assert_flat_error(self, observed, field, code, message):
        self.assertEqual(tuple(observed), ('field', 'code', 'message'))
        self.assertEqual(observed, {
            'field': field,
            'code': code,
            'message': message,
        })

    def test_is_active_changes_return_exact_flat_workflow_error(self):
        cases = (
            (serializer_module.check_building_write_conflict, self.building),
            (serializer_module.check_apartment_write_conflict, self.apartment),
            (serializer_module.check_room_write_conflict, self.room),
        )
        for helper, instance in cases:
            with self.subTest(helper=helper.__name__):
                self.assert_flat_error(
                    helper(instance, {'is_active': False}),
                    'is_active',
                    'USE_AVAILABILITY_WORKFLOW',
                    self.availability_message,
                )

    def test_duplicate_building_number_returns_exact_flat_error(self):
        observed = serializer_module.check_building_write_conflict(
            None,
            {'dorm_type': self.dorm_type.pk, 'number': self.building.number},
        )
        self.assert_flat_error(
            observed,
            'number',
            'DUPLICATE_BUILDING_NUMBER',
            'כבר קיים בניין עם מספר זה עבור סוג המעונות הנבחר.',
        )

    def test_building_gender_restriction_conflict_is_exact(self):
        observed = serializer_module.check_building_write_conflict(
            self.building,
            {'gender_restriction': Building.GenderRestriction.FEMALE},
        )
        self.assert_flat_error(
            observed,
            'gender_restriction',
            'ACTIVE_OCCUPANT_CONFLICT',
            'לא ניתן להגביל את הבניין למגדר זה — קיימים דיירים פעילים '
            'שאינם תואמים להגבלה החדשה.',
        )

    def test_apartment_category_conflict_uses_lazy_matcher_result(self):
        from api.domains.allocation import gateway

        with patch.dict(
            gateway.__dict__,
            {'_housing_matches_apartment': lambda student, apartment: False},
        ):
            observed = serializer_module.check_apartment_write_conflict(
                self.apartment,
                {'category': Apartment.Category.FEMALE},
            )
        self.assert_flat_error(
            observed,
            'category',
            'ACTIVE_OCCUPANT_CONFLICT',
            'לא ניתן לשנות את סיווג הדירה — 1 דיירים פעילים אינם תואמים '
            'לקטגוריה/סוג הדיור החדשים. יש לפנות את הדירה תחילה.',
        )

    def test_apartment_type_conflict_uses_apartment_type_field(self):
        from api.domains.allocation import gateway

        with patch.dict(
            gateway.__dict__,
            {'_housing_matches_apartment': lambda student, apartment: False},
        ):
            observed = serializer_module.check_apartment_write_conflict(
                self.apartment,
                {'apartment_type': Apartment.ApartmentType.FAMILY},
            )
        self.assertEqual(observed['field'], 'apartment_type')
        self.assertEqual(observed['code'], 'ACTIVE_OCCUPANT_CONFLICT')

    def test_apartment_capacity_below_occupancy_is_exact(self):
        observed = serializer_module.check_apartment_write_conflict(
            self.apartment,
            {'apartment_capacity': 0},
        )
        self.assert_flat_error(
            observed,
            'apartment_capacity',
            'CAPACITY_BELOW_OCCUPANCY',
            'לא ניתן להגדיר קיבולת (0) נמוכה ממספר הדיירים הפעילים '
            'הנוכחי (1).',
        )

    def test_room_capacity_below_occupancy_is_exact(self):
        observed = serializer_module.check_room_write_conflict(
            self.room,
            {'capacity': 0},
        )
        self.assert_flat_error(
            observed,
            'capacity',
            'CAPACITY_BELOW_OCCUPANCY',
            'לא ניתן להגדיר קיבולת (0) נמוכה ממספר הדיירים הפעילים '
            'הנוכחי (1).',
        )

    def test_create_calls_preserve_current_none_behavior(self):
        self.assertIsNone(serializer_module.check_building_write_conflict(
            None,
            {'dorm_type': self.other_dorm_type.pk, 'number': 999},
        ))
        self.assertIsNone(serializer_module.check_apartment_write_conflict(
            None,
            {'is_active': False, 'apartment_capacity': 0},
        ))
        self.assertIsNone(serializer_module.check_room_write_conflict(
            None,
            {'is_active': False, 'capacity': 0},
        ))


class StudentValidationTests(SerializerFixtureMixin, TestCase):
    def test_assignment_eligible_category_requires_housing_type(self):
        assert_validation_error(
            self,
            serializer_module.StudentSerializer(),
            {
                'category': Student.StudentCategory.NEW,
                'accepted_dorm_type': self.dorm_type,
            },
            {'housing_type': ['יש לבחור סוג דיור לפני שניתן לבצע שיבוץ.']},
        )

    def test_assignment_eligible_category_requires_accepted_dorm_type(self):
        assert_validation_error(
            self,
            serializer_module.StudentSerializer(),
            {
                'category': Student.StudentCategory.NEW,
                'housing_type': Student.HousingType.SINGLE_MALE,
            },
            {
                'accepted_dorm_type': [
                    'יש לבחור אזור/סוג מעונות לפני שניתן לבצע שיבוץ.'
                ],
            },
        )

    def test_leaving_category_is_exempt(self):
        attrs = {'category': Student.StudentCategory.LEAVING}
        self.assertEqual(
            serializer_module.StudentSerializer().validate(attrs.copy()),
            attrs,
        )

    def test_patch_uses_attrs_before_instance_fallback(self):
        serializer = serializer_module.StudentSerializer(
            instance=self.student,
            partial=True,
        )
        self.assertEqual(serializer.validate({}), {})
        assert_validation_error(
            self,
            serializer,
            {'housing_type': ''},
            {'housing_type': ['יש לבחור סוג דיור לפני שניתן לבצע שיבוץ.']},
        )

    def test_patch_uses_instance_housing_before_attrs_accepted_dorm_override(self):
        serializer = serializer_module.StudentSerializer(
            instance=self.student,
            partial=True,
        )
        assert_validation_error(
            self,
            serializer,
            {'accepted_dorm_type': None},
            {
                'accepted_dorm_type': [
                    'יש לבחור אזור/סוג מעונות לפני שניתן לבצע שיבוץ.'
                ],
            },
        )


class BedAssignmentValidationTests(SerializerFixtureMixin, TestCase):
    def assert_bed_assignment_direct_and_public_errors(
        self,
        *,
        direct_attrs,
        public_data,
        field,
        message,
    ):
        with self.assertRaises(ValidationError) as caught:
            serializer_module.BedAssignmentSerializer().validate(direct_attrs)
        self.assertEqual(tuple(caught.exception.detail), (field,))
        direct_detail = caught.exception.detail[field]
        self.assertIsInstance(direct_detail, ErrorDetail)
        self.assertEqual(str(direct_detail), message)
        self.assertEqual(direct_detail.code, 'invalid')

        public_serializer = serializer_module.BedAssignmentSerializer(
            data=public_data,
        )
        self.assertFalse(public_serializer.is_valid())
        self.assertEqual(tuple(public_serializer.errors), (field,))
        public_details = public_serializer.errors[field]
        self.assertIsInstance(public_details, list)
        self.assertEqual(len(public_details), 1)
        self.assertIsInstance(public_details[0], ErrorDetail)
        self.assertEqual(str(public_details[0]), message)
        self.assertEqual(public_details[0].code, 'invalid')

    def test_active_forbids_ended_at(self):
        ended_at = timezone.now()
        self.assert_bed_assignment_direct_and_public_errors(
            direct_attrs={
                'status': BedAssignment.Status.ACTIVE,
                'ended_at': ended_at,
            },
            public_data={
                'student': self.other_student.pk,
                'bed': self.spare_bed.pk,
                'status': BedAssignment.Status.ACTIVE,
                'ended_at': ended_at.isoformat(),
            },
            field='ended_at',
            message='Active assignment cannot have an ended_at value.',
        )

    def test_ended_requires_ended_at(self):
        self.assert_bed_assignment_direct_and_public_errors(
            direct_attrs={
                'status': BedAssignment.Status.ENDED,
                'ended_at': None,
            },
            public_data={
                'student': self.other_student.pk,
                'bed': self.spare_bed.pk,
                'status': BedAssignment.Status.ENDED,
                'ended_at': None,
            },
            field='ended_at',
            message='Ended or cancelled assignment must have ended_at.',
        )

    def test_cancelled_requires_ended_at(self):
        self.assert_bed_assignment_direct_and_public_errors(
            direct_attrs={
                'status': BedAssignment.Status.CANCELLED,
                'ended_at': None,
            },
            public_data={
                'student': self.other_student.pk,
                'bed': self.spare_bed.pk,
                'status': BedAssignment.Status.CANCELLED,
                'ended_at': None,
            },
            field='ended_at',
            message='Ended or cancelled assignment must have ended_at.',
        )

    def test_another_active_assignment_for_same_bed_is_rejected(self):
        self.assert_bed_assignment_direct_and_public_errors(
            direct_attrs={
                'student': self.other_student,
                'bed': self.bed,
                'status': BedAssignment.Status.ACTIVE,
                'ended_at': None,
            },
            public_data={
                'student': self.other_student.pk,
                'bed': self.bed.pk,
                'status': BedAssignment.Status.ACTIVE,
                'ended_at': None,
            },
            field='bed',
            message='This bed already has an active assignment.',
        )

    def test_another_active_assignment_for_same_student_is_rejected(self):
        self.assert_bed_assignment_direct_and_public_errors(
            direct_attrs={
                'student': self.student,
                'bed': self.spare_bed,
                'status': BedAssignment.Status.ACTIVE,
                'ended_at': None,
            },
            public_data={
                'student': self.student.pk,
                'bed': self.spare_bed.pk,
                'status': BedAssignment.Status.ACTIVE,
                'ended_at': None,
            },
            field='student',
            message='This student already has an active bed assignment.',
        )

    def test_update_excludes_current_instance_row(self):
        serializer = serializer_module.BedAssignmentSerializer(
            instance=self.assignment,
        )
        attrs = {
            'student': self.student,
            'bed': self.bed,
            'status': BedAssignment.Status.ACTIVE,
            'ended_at': None,
        }
        self.assertEqual(serializer.validate(attrs.copy()), attrs)


class MovementRequestValidationTests(SerializerFixtureMixin, TestCase):
    def assert_target_bed_direct_and_public_error(
        self,
        *,
        direct_attrs,
        public_data,
    ):
        message = 'Approved or completed request must have target bed.'
        with self.assertRaises(ValidationError) as caught:
            serializer_module.MovementRequestSerializer().validate(
                direct_attrs,
            )
        self.assertEqual(tuple(caught.exception.detail), ('to_bed',))
        direct_detail = caught.exception.detail['to_bed']
        self.assertIsInstance(direct_detail, ErrorDetail)
        self.assertEqual(str(direct_detail), message)
        self.assertEqual(direct_detail.code, 'invalid')

        public_serializer = serializer_module.MovementRequestSerializer(
            data=public_data,
        )
        self.assertFalse(public_serializer.is_valid())
        self.assertEqual(tuple(public_serializer.errors), ('to_bed',))
        public_details = public_serializer.errors['to_bed']
        self.assertIsInstance(public_details, list)
        self.assertEqual(len(public_details), 1)
        self.assertIsInstance(public_details[0], ErrorDetail)
        self.assertEqual(str(public_details[0]), message)
        self.assertEqual(public_details[0].code, 'invalid')

    def test_pending_forbids_approval_or_completion_data(self):
        assert_validation_error(
            self,
            serializer_module.MovementRequestSerializer(),
            {
                'status': MovementRequest.Status.PENDING,
                'approved_by': self.user,
            },
            ['Pending request cannot have approval/completion data.'],
        )

    def test_approved_requires_approval_metadata(self):
        assert_validation_error(
            self,
            serializer_module.MovementRequestSerializer(),
            {'status': MovementRequest.Status.APPROVED},
            ['Approved request must have approved_by and reviewed_at.'],
        )

    def test_approved_requires_target_bed_after_metadata(self):
        now = timezone.now()
        self.assert_target_bed_direct_and_public_error(
            direct_attrs={
                'status': MovementRequest.Status.APPROVED,
                'approved_by': self.user,
                'reviewed_at': now,
                'to_bed': None,
            },
            public_data={
                'student': self.other_student.pk,
                'status': MovementRequest.Status.APPROVED,
                'approved_by': self.user.pk,
                'reviewed_at': now.isoformat(),
                'to_bed': None,
            },
        )

    def test_rejected_requires_approval_metadata(self):
        assert_validation_error(
            self,
            serializer_module.MovementRequestSerializer(),
            {'status': MovementRequest.Status.REJECTED},
            ['Rejected request must have approved_by and reviewed_at.'],
        )

    def test_completed_requires_all_metadata(self):
        assert_validation_error(
            self,
            serializer_module.MovementRequestSerializer(),
            {
                'status': MovementRequest.Status.COMPLETED,
                'approved_by': self.user,
                'reviewed_at': timezone.now(),
            },
            [
                'Completed request must have approval and completion '
                'timestamps.'
            ],
        )

    def test_completed_requires_target_bed_after_all_metadata(self):
        now = timezone.now()
        self.assert_target_bed_direct_and_public_error(
            direct_attrs={
                'status': MovementRequest.Status.COMPLETED,
                'approved_by': self.user,
                'reviewed_at': now,
                'completed_at': now,
                'to_bed': None,
            },
            public_data={
                'student': self.other_student.pk,
                'status': MovementRequest.Status.COMPLETED,
                'approved_by': self.user.pk,
                'reviewed_at': now.isoformat(),
                'completed_at': now.isoformat(),
                'to_bed': None,
            },
        )


class TransferValidationTests(SerializerFixtureMixin, TestCase):
    def test_identical_source_and_target_room_is_rejected(self):
        message = 'Source room and target room cannot be the same.'
        with self.assertRaises(ValidationError) as caught:
            serializer_module.TransferSerializer().validate({
                'from_room': self.room,
                'to_room': self.room,
            })
        self.assertEqual(tuple(caught.exception.detail), ('to_room',))
        direct_detail = caught.exception.detail['to_room']
        self.assertIsInstance(direct_detail, ErrorDetail)
        self.assertEqual(str(direct_detail), message)
        self.assertEqual(direct_detail.code, 'invalid')

        public_serializer = serializer_module.TransferSerializer(data={
            'student': self.other_student.pk,
            'from_room': self.room.pk,
            'to_room': self.room.pk,
        })
        self.assertFalse(public_serializer.is_valid())
        self.assertEqual(tuple(public_serializer.errors), ('to_room',))
        public_details = public_serializer.errors['to_room']
        self.assertIsInstance(public_details, list)
        self.assertEqual(len(public_details), 1)
        self.assertIsInstance(public_details[0], ErrorDetail)
        self.assertEqual(str(public_details[0]), message)
        self.assertEqual(public_details[0].code, 'invalid')

    def test_pending_forbids_review_data(self):
        assert_validation_error(
            self,
            serializer_module.TransferSerializer(),
            {
                'status': Transfer.Status.PENDING,
                'reviewed_by': self.user,
            },
            ['Pending transfer cannot have review data.'],
        )

    def test_pending_forbids_rejection_reason(self):
        assert_validation_error(
            self,
            serializer_module.TransferSerializer(),
            {
                'status': Transfer.Status.PENDING,
                'rejection_reason': 'No',
            },
            ['Pending transfer cannot have rejection_reason.'],
        )

    def test_approved_requires_review_metadata(self):
        assert_validation_error(
            self,
            serializer_module.TransferSerializer(),
            {'status': Transfer.Status.APPROVED},
            ['Approved transfer must have reviewed_by and reviewed_at.'],
        )

    def test_approved_forbids_rejection_reason(self):
        assert_validation_error(
            self,
            serializer_module.TransferSerializer(),
            {
                'status': Transfer.Status.APPROVED,
                'reviewed_by': self.user,
                'reviewed_at': timezone.now(),
                'rejection_reason': 'No',
            },
            ['Approved transfer cannot have rejection_reason.'],
        )

    def test_rejected_requires_review_metadata(self):
        assert_validation_error(
            self,
            serializer_module.TransferSerializer(),
            {'status': Transfer.Status.REJECTED},
            ['Rejected transfer must have reviewed_by and reviewed_at.'],
        )

    def test_workflow_owned_fields_are_read_only(self):
        serializer = serializer_module.TransferSerializer()
        expected = EXPECTED_READ_ONLY_FIELDS['TransferSerializer']
        for field_name in expected:
            with self.subTest(field=field_name):
                self.assertTrue(serializer.fields[field_name].read_only)


class StudentRequestValidationTests(SerializerFixtureMixin, TestCase):
    def assert_student_request_direct_and_public_error(
        self,
        *,
        direct_serializer,
        direct_attrs,
        public_serializer,
        field,
        message,
    ):
        with self.assertRaises(ValidationError) as caught:
            direct_serializer.validate(direct_attrs)
        self.assertEqual(tuple(caught.exception.detail), (field,))
        direct_detail = caught.exception.detail[field]
        self.assertIsInstance(direct_detail, ErrorDetail)
        self.assertEqual(str(direct_detail), message)
        self.assertEqual(direct_detail.code, 'invalid')

        self.assertFalse(public_serializer.is_valid())
        self.assertEqual(tuple(public_serializer.errors), (field,))
        public_details = public_serializer.errors[field]
        self.assertIsInstance(public_details, list)
        self.assertEqual(len(public_details), 1)
        self.assertIsInstance(public_details[0], ErrorDetail)
        self.assertEqual(str(public_details[0]), message)
        self.assertEqual(public_details[0].code, 'invalid')

    def test_existing_student_request_types_require_student(self):
        request_types = (
            StudentRequest.RequestType.ROOM,
            StudentRequest.RequestType.APARTMENT,
            StudentRequest.RequestType.REMOVE_STUDENT,
            StudentRequest.RequestType.SWAP,
            StudentRequest.RequestType.REGION_TRANSFER,
        )
        for request_type in request_types:
            with self.subTest(request_type=request_type):
                message = (
                    'This request type requires selecting an existing '
                    'student.'
                )
                self.assert_student_request_direct_and_public_error(
                    direct_serializer=(
                        serializer_module.StudentRequestSerializer()
                    ),
                    direct_attrs={'request_type': request_type},
                    public_serializer=(
                        serializer_module.StudentRequestSerializer(
                            data={'request_type': request_type},
                        )
                    ),
                    field='student',
                    message=message,
                )

    def test_swap_requires_other_student(self):
        self.assert_student_request_direct_and_public_error(
            direct_serializer=serializer_module.StudentRequestSerializer(),
            direct_attrs={
                'request_type': StudentRequest.RequestType.SWAP,
                'student': self.student,
            },
            public_serializer=serializer_module.StudentRequestSerializer(
                data={
                    'request_type': StudentRequest.RequestType.SWAP,
                    'student': self.student.pk,
                },
            ),
            field='swap_with_student',
            message='A swap request requires selecting the other student.',
        )

    def test_swap_rejects_self_swap(self):
        self.assert_student_request_direct_and_public_error(
            direct_serializer=serializer_module.StudentRequestSerializer(),
            direct_attrs={
                'request_type': StudentRequest.RequestType.SWAP,
                'student': self.student,
                'swap_with_student': self.student,
            },
            public_serializer=serializer_module.StudentRequestSerializer(
                data={
                    'request_type': StudentRequest.RequestType.SWAP,
                    'student': self.student.pk,
                    'swap_with_student': self.student.pk,
                },
            ),
            field='swap_with_student',
            message='A student cannot swap with themselves.',
        )

    def test_region_transfer_requires_target_region(self):
        message = (
            'A region transfer request requires a destination region.'
        )
        self.assert_student_request_direct_and_public_error(
            direct_serializer=serializer_module.StudentRequestSerializer(),
            direct_attrs={
                'request_type': StudentRequest.RequestType.REGION_TRANSFER,
                'student': self.student,
            },
            public_serializer=serializer_module.StudentRequestSerializer(
                data={
                    'request_type': (
                        StudentRequest.RequestType.REGION_TRANSFER
                    ),
                    'student': self.student.pk,
                },
            ),
            field='target_region',
            message=message,
        )

    def test_add_student_missing_fields_preserve_declaration_order(self):
        message = (
            'Missing required new-student fields: student_id, first_name, '
            'gender'
        )
        self.assert_student_request_direct_and_public_error(
            direct_serializer=serializer_module.StudentRequestSerializer(),
            direct_attrs={
                'request_type': StudentRequest.RequestType.ADD_STUDENT,
                'student_data': {'last_name': 'Only'},
            },
            public_serializer=serializer_module.StudentRequestSerializer(
                data={
                    'request_type': StudentRequest.RequestType.ADD_STUDENT,
                    'student_data': {'last_name': 'Only'},
                },
            ),
            field='student_data',
            message=message,
        )

    def test_non_central_cross_region_raises_exact_permission_denied(self):
        request = SimpleNamespace(user=self.employee)
        serializer = serializer_module.StudentRequestSerializer(
            context={'request': request},
        )
        with self.assertRaises(PermissionDenied) as caught:
            serializer.validate({
                'request_type': StudentRequest.RequestType.ROOM,
                'student': self.student,
                'transfer_scope': StudentRequest.TransferScope.CROSS_REGION,
                'destination_regions': [self.other_region],
            })
        self.assertEqual(str(caught.exception.detail), (
            'אין לך הרשאה לבצע מעבר לאזור אחר.'
        ))
        self.assertEqual(caught.exception.get_codes(), 'permission_denied')

    def test_cross_region_requires_destination_region(self):
        request = SimpleNamespace(user=self.user)
        message = 'יש לבחור לפחות אזור יעד אחד עבור מעבר לאזור אחר.'
        self.assert_student_request_direct_and_public_error(
            direct_serializer=serializer_module.StudentRequestSerializer(
                context={'request': request},
            ),
            direct_attrs={
                'request_type': StudentRequest.RequestType.APARTMENT,
                'student': self.student,
                'transfer_scope': StudentRequest.TransferScope.CROSS_REGION,
                'destination_regions': [],
            },
            public_serializer=serializer_module.StudentRequestSerializer(
                data={
                    'request_type': StudentRequest.RequestType.APARTMENT,
                    'student': self.student.pk,
                    'transfer_scope': (
                        StudentRequest.TransferScope.CROSS_REGION
                    ),
                    'destination_regions': [],
                },
                context={'request': request},
            ),
            field='destination_regions',
            message=message,
        )

    def test_same_region_mutates_destination_regions_to_empty_list(self):
        request = SimpleNamespace(user=self.user)
        serializer = serializer_module.StudentRequestSerializer(
            context={'request': request},
        )
        attrs = {
            'request_type': StudentRequest.RequestType.ROOM,
            'student': self.student,
            'transfer_scope': StudentRequest.TransferScope.SAME_REGION,
            'destination_regions': [self.other_region],
        }
        validated = serializer.validate(attrs)
        self.assertIs(validated, attrs)
        self.assertEqual(validated['destination_regions'], [])


class LifecycleSerializerValidationTests(SerializerFixtureMixin, TestCase):
    def assert_lifecycle_direct_and_public_error(
        self,
        *,
        serializer_class,
        direct_attrs,
        public_data,
        field,
        message,
    ):
        with self.assertRaises(ValidationError) as caught:
            serializer_class().validate(direct_attrs)
        self.assertEqual(tuple(caught.exception.detail), (field,))
        direct_detail = caught.exception.detail[field]
        self.assertIsInstance(direct_detail, ErrorDetail)
        self.assertEqual(str(direct_detail), message)
        self.assertEqual(direct_detail.code, 'invalid')

        public_serializer = serializer_class(data=public_data)
        self.assertFalse(public_serializer.is_valid())
        self.assertEqual(tuple(public_serializer.errors), (field,))
        public_details = public_serializer.errors[field]
        self.assertIsInstance(public_details, list)
        self.assertEqual(len(public_details), 1)
        self.assertIsInstance(public_details[0], ErrorDetail)
        self.assertEqual(str(public_details[0]), message)
        self.assertEqual(public_details[0].code, 'invalid')

    def allocation_public_data(self, **overrides):
        data = {
            'region': self.region.pk,
            'run_by': self.user.pk,
        }
        data.update(overrides)
        return data

    def import_batch_public_data(self, **overrides):
        data = {
            'uploaded_by': self.user.pk,
            'kind': ImportBatch.Kind.MAIN,
            'filename': 'characterization.xlsx',
        }
        data.update(overrides)
        return data

    def inbox_public_data(self, **overrides):
        data = {
            'region': self.region.pk,
            'batch': self.import_batch.pk,
        }
        data.update(overrides)
        return data

    def test_running_allocation_forbids_completed_at(self):
        completed_at = timezone.now()
        self.assert_lifecycle_direct_and_public_error(
            serializer_class=serializer_module.AllocationRunSerializer,
            direct_attrs={
                'status': AllocationRun.Status.RUNNING,
                'completed_at': completed_at,
                'error_message': '',
            },
            public_data=self.allocation_public_data(
                status=AllocationRun.Status.RUNNING,
                completed_at=completed_at.isoformat(),
                error_message='',
            ),
            field='completed_at',
            message='Running allocation cannot have completed_at.',
        )

    def test_running_allocation_forbids_error_message(self):
        self.assert_lifecycle_direct_and_public_error(
            serializer_class=serializer_module.AllocationRunSerializer,
            direct_attrs={
                'status': AllocationRun.Status.RUNNING,
                'completed_at': None,
                'error_message': 'boom',
            },
            public_data=self.allocation_public_data(
                status=AllocationRun.Status.RUNNING,
                completed_at=None,
                error_message='boom',
            ),
            field='error_message',
            message='Running allocation cannot have error_message.',
        )

    def test_completed_allocation_requires_completed_at(self):
        self.assert_lifecycle_direct_and_public_error(
            serializer_class=serializer_module.AllocationRunSerializer,
            direct_attrs={
                'status': AllocationRun.Status.COMPLETED,
                'completed_at': None,
                'error_message': '',
            },
            public_data=self.allocation_public_data(
                status=AllocationRun.Status.COMPLETED,
                completed_at=None,
                error_message='',
            ),
            field='completed_at',
            message='Completed allocation must have completed_at.',
        )

    def test_completed_allocation_forbids_error_message(self):
        completed_at = timezone.now()
        self.assert_lifecycle_direct_and_public_error(
            serializer_class=serializer_module.AllocationRunSerializer,
            direct_attrs={
                'status': AllocationRun.Status.COMPLETED,
                'completed_at': completed_at,
                'error_message': 'boom',
            },
            public_data=self.allocation_public_data(
                status=AllocationRun.Status.COMPLETED,
                completed_at=completed_at.isoformat(),
                error_message='boom',
            ),
            field='error_message',
            message='Completed allocation should not have error_message.',
        )

    def test_failed_allocation_requires_completed_at(self):
        self.assert_lifecycle_direct_and_public_error(
            serializer_class=serializer_module.AllocationRunSerializer,
            direct_attrs={
                'status': AllocationRun.Status.FAILED,
                'completed_at': None,
                'error_message': 'boom',
            },
            public_data=self.allocation_public_data(
                status=AllocationRun.Status.FAILED,
                completed_at=None,
                error_message='boom',
            ),
            field='completed_at',
            message='Failed allocation must have completed_at.',
        )

    def test_failed_allocation_requires_error_message(self):
        completed_at = timezone.now()
        self.assert_lifecycle_direct_and_public_error(
            serializer_class=serializer_module.AllocationRunSerializer,
            direct_attrs={
                'status': AllocationRun.Status.FAILED,
                'completed_at': completed_at,
                'error_message': '',
            },
            public_data=self.allocation_public_data(
                status=AllocationRun.Status.FAILED,
                completed_at=completed_at.isoformat(),
                error_message='',
            ),
            field='error_message',
            message='Failed allocation should include error_message.',
        )

    def test_allocation_elapsed_and_remaining_time_are_deterministic(self):
        fixed_now = timezone.now().replace(microsecond=0)
        run = SimpleNamespace(
            search_started_at=fixed_now - timedelta(seconds=12),
            completed_at=None,
            max_search_seconds=30,
        )
        serializer = serializer_module.AllocationRunSerializer()
        with patch('api.serializers.operations.timezone.now', return_value=fixed_now):
            self.assertEqual(serializer.get_elapsed_search_seconds(run), 12)
            self.assertEqual(serializer.get_remaining_search_seconds(run), 18)

        run.completed_at = fixed_now - timedelta(seconds=2)
        with patch(
            'api.serializers.operations.timezone.now',
            side_effect=AssertionError('terminal run must not read now'),
        ):
            self.assertEqual(serializer.get_elapsed_search_seconds(run), 10)
            self.assertEqual(serializer.get_remaining_search_seconds(run), 20)

    def test_allocation_time_defaults_before_search_or_without_limit(self):
        serializer = serializer_module.AllocationRunSerializer()
        run = SimpleNamespace(
            search_started_at=None,
            completed_at=None,
            max_search_seconds=None,
        )
        self.assertEqual(serializer.get_elapsed_search_seconds(run), 0)
        self.assertIsNone(serializer.get_remaining_search_seconds(run))

    def test_failed_import_batch_requires_error_message(self):
        self.assert_lifecycle_direct_and_public_error(
            serializer_class=serializer_module.ImportBatchSerializer,
            direct_attrs={
                'status': ImportBatch.Status.FAILED,
                'error_message': '',
            },
            public_data=self.import_batch_public_data(
                status=ImportBatch.Status.FAILED,
                error_message='',
            ),
            field='error_message',
            message='Failed batch should include error_message.',
        )

    def test_nonfailed_import_statuses_interpolate_raw_status(self):
        statuses = (
            ImportBatch.Status.PENDING,
            ImportBatch.Status.PROCESSING,
            ImportBatch.Status.CANCELLATION_REQUESTED,
            ImportBatch.Status.STOP_AND_DELETE_REQUESTED,
            ImportBatch.Status.STOPPED,
            ImportBatch.Status.COMPLETED,
        )
        for status in statuses:
            with self.subTest(status=status):
                message = f'{status} batch cannot have error_message.'
                self.assert_lifecycle_direct_and_public_error(
                    serializer_class=serializer_module.ImportBatchSerializer,
                    direct_attrs={
                        'status': status,
                        'error_message': 'boom',
                    },
                    public_data=self.import_batch_public_data(
                        status=status,
                        error_message='boom',
                    ),
                    field='error_message',
                    message=message,
                )

    def test_pending_inbox_forbids_viewed_or_processed_timestamp(self):
        assert_validation_error(
            self,
            serializer_module.RegionInboxSerializer(),
            {
                'status': RegionInbox.Status.PENDING,
                'viewed_at': timezone.now(),
            },
            ['Pending inbox item cannot have viewed_at or processed_at.'],
        )

    def test_viewed_inbox_requires_viewed_at(self):
        self.assert_lifecycle_direct_and_public_error(
            serializer_class=serializer_module.RegionInboxSerializer,
            direct_attrs={
                'status': RegionInbox.Status.VIEWED,
                'viewed_at': None,
            },
            public_data=self.inbox_public_data(
                status=RegionInbox.Status.VIEWED,
                viewed_at=None,
            ),
            field='viewed_at',
            message='Viewed inbox item must have viewed_at.',
        )

    def test_processed_inbox_requires_processed_at(self):
        self.assert_lifecycle_direct_and_public_error(
            serializer_class=serializer_module.RegionInboxSerializer,
            direct_attrs={
                'status': RegionInbox.Status.PROCESSED,
                'processed_at': None,
            },
            public_data=self.inbox_public_data(
                status=RegionInbox.Status.PROCESSED,
                processed_at=None,
            ),
            field='processed_at',
            message='Processed inbox item must have processed_at.',
        )


class SerializerRepresentationTests(SerializerFixtureMixin, TestCase):
    def test_every_model_serializer_emits_exact_ordered_keys(self):
        self.student.prefetched_active_assignments = [self.assignment]
        instances = {
            'UserSerializer': self.user,
            'RegionSerializer': self.region,
            'DormTypeSerializer': self.dorm_type,
            'OfficeSerializer': self.office,
            'StaffProfileSerializer': self.staff_profile,
            'BuildingSerializer': self.building,
            'ApartmentSerializer': self.apartment,
            'RoomSerializer': self.room,
            'BedSerializer': self.bed,
            'StudentListSerializer': self.student,
            'StudentSerializer': self.student,
            'BedAssignmentSerializer': self.assignment,
            'MovementRequestSerializer': self.movement,
            'TransferSerializer': self.transfer,
            'StudentRequestSerializer': self.student_request,
            'AllocationRunSerializer': self.allocation_run,
            'ImportBatchSerializer': self.import_batch,
            'RegionInboxSerializer': self.inbox,
        }
        self.assertEqual(set(instances), set(SERIALIZER_NAMES) - {
            'LoginSerializer',
        })
        for serializer_name, instance in instances.items():
            with self.subTest(serializer=serializer_name):
                serializer_class = getattr(serializer_module, serializer_name)
                data = serializer_class(instance).data
                self.assertEqual(
                    tuple(data.keys()), EXPECTED_FIELDS[serializer_name],
                )

    def test_representative_values_and_zero_consumer_serializers(self):
        self.student.prefetched_active_assignments = [self.assignment]

        user = serializer_module.UserSerializer(self.user).data
        self.assertEqual(user['full_name'], 'Admin Characterizer')
        self.assertEqual(user['role_display'], self.user.get_role_display())
        self.assertEqual(user['region_name'], self.region.name)
        self.assertTrue(user['is_central_admin'])

        dorm = serializer_module.DormTypeSerializer(self.dorm_type).data
        self.assertEqual(dorm['code'], 8121)
        self.assertEqual(dorm['region'], self.region.pk)
        self.assertEqual(dorm['region_name'], self.region.name)

        office = serializer_module.OfficeSerializer(self.office).data
        self.assertEqual(
            office['office_type_display'],
            self.office.get_office_type_display(),
        )
        self.assertEqual(office['region_name'], self.region.name)

        staff = serializer_module.StaffProfileSerializer(
            self.staff_profile,
        ).data
        self.assertEqual(staff['user_email'], self.employee.email)
        self.assertEqual(staff['user_full_name'], 'Regional Employee')
        self.assertEqual(staff['office_name'], self.office.name)

        building = serializer_module.BuildingSerializer(self.building).data
        self.assertEqual(building['dorm_type_name'], self.dorm_type.name)
        self.assertEqual(building['region_name'], self.region.name)
        self.assertEqual(
            {
                key: building[key]
                for key in (
                    'apartment_count', 'room_count', 'bed_count',
                    'occupied_beds', 'free_beds',
                )
            },
            {
                'apartment_count': 1,
                'room_count': 1,
                'bed_count': 2,
                'occupied_beds': 1,
                'free_beds': 1,
            },
        )

        apartment = serializer_module.ApartmentSerializer(
            self.apartment,
        ).data
        self.assertEqual(apartment['building_number'], self.building.number)
        self.assertEqual(apartment['region_name'], self.region.name)
        self.assertEqual(apartment['dorm_type'], self.dorm_type.name)
        self.assertEqual(apartment['actual_room_count'], 1)
        self.assertEqual(apartment['bed_count'], 2)
        self.assertEqual(apartment['occupied_beds'], 1)
        self.assertEqual(apartment['free_beds'], 1)

        room = serializer_module.RoomSerializer(self.room).data
        self.assertEqual(room['number'], self.room.name)
        self.assertEqual(room['building_number'], self.building.number)
        self.assertEqual(room['current_occupancy'], 1)
        self.assertEqual(room['available_beds'], 1)
        self.assertFalse(room['is_full'])
        self.assertFalse(room['has_missing_bed_records'])

        bed = serializer_module.BedSerializer(self.bed).data
        self.assertEqual(bed['room_name'], self.room.name)
        self.assertEqual(bed['apartment_number'], self.apartment.number)
        self.assertTrue(bed['is_occupied'])

        student_list = serializer_module.StudentListSerializer(
            self.student,
        ).data
        self.assertEqual(student_list['full_name'], 'Student Character')
        self.assertEqual(student_list['current_building'], 41)
        self.assertEqual(student_list['current_apartment'], 'A-1')
        self.assertEqual(student_list['current_room'], '101')
        self.assertEqual(student_list['current_bed'], 'Bed 1')

        student = serializer_module.StudentSerializer(self.student).data
        self.assertEqual(student['region_id'], self.region.pk)
        self.assertEqual(student['region_name'], self.region.name)
        self.assertEqual(student['assigned_room_id'], self.room.pk)
        self.assertEqual(student['current_bed_id'], self.bed.pk)
        self.assertEqual(student['current_bed_label'], self.bed.label)
        self.assertIsNone(student['batch_id'])

        assignment = serializer_module.BedAssignmentSerializer(
            self.assignment,
        ).data
        self.assertEqual(assignment['student_name'], self.student.full_name)
        self.assertEqual(assignment['bed_label'], self.bed.label)
        self.assertEqual(
            assignment['status_display'],
            self.assignment.get_status_display(),
        )
        self.assertEqual(
            assignment['assigned_by_name'],
            self.user.get_full_name(),
        )

        movement = serializer_module.MovementRequestSerializer(
            self.movement,
        ).data
        self.assertEqual(movement['from_assignment_id'], self.assignment.pk)
        self.assertEqual(movement['from_bed_label'], self.bed.label)
        self.assertEqual(movement['to_bed_label'], self.other_bed.label)
        self.assertEqual(
            movement['requested_by_name'],
            self.employee.get_full_name(),
        )
        self.assertIsNone(movement['approved_by_name'])

        transfer = serializer_module.TransferSerializer(self.transfer).data
        self.assertEqual(transfer['from_room_name'], self.room.name)
        self.assertEqual(transfer['to_room_name'], self.other_room.name)
        self.assertEqual(
            transfer['requested_by_region_name'], self.region.name,
        )
        self.assertIsNone(transfer['reviewed_by_name'])

        request = serializer_module.StudentRequestSerializer(
            self.student_request,
        ).data
        self.assertEqual(request['student_name'], self.student.full_name)
        self.assertEqual(request['target_room_name'], self.other_room.name)
        self.assertEqual(
            request['destination_region_names'],
            [self.other_region.name],
        )
        self.assertEqual(request['final_bed_label'], self.bed.label)
        self.assertEqual(request['current_region'], self.region.name)
        self.assertEqual(request['current_building'], self.building.number)
        self.assertEqual(request['current_apartment'], self.apartment.number)
        self.assertEqual(request['current_room'], self.room.name)
        self.assertEqual(request['current_bed'], self.bed.label)

        allocation = serializer_module.AllocationRunSerializer(
            self.allocation_run,
        ).data
        self.assertEqual(allocation['region_name'], self.region.name)
        self.assertEqual(allocation['run_by_name'], self.user.get_full_name())
        self.assertEqual(
            allocation['status_display'],
            self.allocation_run.get_status_display(),
        )
        self.assertEqual(allocation['elapsed_search_seconds'], 0)
        self.assertEqual(allocation['remaining_search_seconds'], 30)

        batch = serializer_module.ImportBatchSerializer(
            self.import_batch,
        ).data
        self.assertEqual(batch['uploaded_by_name'], self.user.get_full_name())
        self.assertEqual(batch['status_display'], (
            self.import_batch.get_status_display()
        ))
        self.assertEqual(batch['result'], {'created': 0})
        self.assertEqual(batch['region_breakdown'], [{
            'region_id': self.region.pk,
            'region_name': self.region.name,
            'count': 3,
            'status': RegionInbox.Status.PENDING,
        }])

        inbox = serializer_module.RegionInboxSerializer(self.inbox).data
        self.assertEqual(inbox['region_name'], self.region.name)
        self.assertEqual(inbox['batch_filename'], self.import_batch.filename)
        batch_created_at = inbox['batch_created_at']
        expected_batch_created_at = timezone.localtime(
            self.import_batch.created_at,
        ).isoformat()
        self.assertIsInstance(batch_created_at, str)
        self.assertEqual(
            batch_created_at, expected_batch_created_at,
        )
        self.assertTrue(batch_created_at.endswith('+03:00'))
        self.assertEqual(inbox['status_display'], self.inbox.get_status_display())

    def test_none_defaults_and_student_data_name_fallback(self):
        dorm_without_region = DormType.objects.create(
            code=8123, name='Serializer Dorm Without Region',
        )
        dorm_serializer = serializer_module.DormTypeSerializer(
            dorm_without_region,
        )
        self.assertIn('region_name', dorm_serializer.fields)
        dorm_data = dorm_serializer.data
        self.assertIsNone(dorm_data['region'])
        self.assertNotIn('region_name', dorm_data)

        leaving = Student.objects.create(
            student_id='SER-NONE',
            first_name='No',
            last_name='Placement',
            category=Student.StudentCategory.LEAVING,
        )
        leaving_data = serializer_module.StudentSerializer(leaving).data
        self.assertIsNone(leaving_data['region_id'])
        self.assertIsNone(leaving_data['region_name'])
        self.assertIsNone(leaving_data['assigned_room'])
        self.assertIsNone(leaving_data['current_bed_id'])
        self.assertIsNone(leaving_data['current_bed_label'])

        add_request = StudentRequest.objects.create(
            request_type=StudentRequest.RequestType.ADD_STUDENT,
            requested_by=self.user,
            student_data={'first_name': 'Data', 'last_name': 'Only'},
        )
        request_data = serializer_module.StudentRequestSerializer(
            add_request,
        ).data
        self.assertEqual(request_data['student_name'], 'Data Only')
        self.assertIsNone(request_data['student_id_number'])
        self.assertIsNone(request_data['target_room_name'])
        self.assertIsNone(request_data['final_bed_label'])
        self.assertEqual(request_data['placement_history'], [])


class PlacementHistoryContractTests(SerializerFixtureMixin, TestCase):
    def test_fallback_history_is_newest_first_bounded_to_ten_and_key_ordered(self):
        history_student = Student.objects.create(
            student_id='SER-HISTORY',
            first_name='History',
            last_name='Student',
            gender=Student.Gender.MALE,
            category=Student.StudentCategory.NEW,
            housing_type=Student.HousingType.SINGLE_MALE,
            accepted_dorm_type=self.dorm_type,
        )
        request = StudentRequest.objects.create(
            request_type=StudentRequest.RequestType.OTHER,
            requested_by=self.user,
            student=history_student,
        )
        base_time = timezone.now().replace(microsecond=0)
        expected_room_names = []
        for index in range(11):
            room = Room.objects.create(
                apartment=self.apartment,
                name=f'H-{index:02d}',
                capacity=1,
            )
            bed = Bed.objects.create(room=room, label='Bed 1')
            assignment = BedAssignment.objects.create(
                student=history_student,
                bed=bed,
                status=BedAssignment.Status.ENDED,
                ended_at=base_time + timedelta(minutes=index),
            )
            assigned_at = base_time + timedelta(minutes=index)
            BedAssignment.objects.filter(pk=assignment.pk).update(
                assigned_at=assigned_at,
            )
            expected_room_names.append(room.name)

        history = serializer_module.StudentRequestSerializer().get_placement_history(
            request,
        )
        self.assertEqual(len(history), 10)
        self.assertEqual(
            [row['room'] for row in history],
            list(reversed(expected_room_names))[0:10],
        )
        expected_keys = (
            'region', 'building', 'apartment', 'room', 'status',
            'assigned_at', 'ended_at',
        )
        for row in history:
            self.assertEqual(tuple(row), expected_keys)


class SerializerFastPathTests(SerializerFixtureMixin, TestCase):
    def test_building_annotations_avoid_fallback_queries(self):
        self.building.dorm_type.region
        self.building._apartment_count = 7
        self.building._room_count = 8
        self.building._bed_count = 9
        self.building._occupied_beds = 4
        with self.assertNumQueries(0):
            data = serializer_module.BuildingSerializer(self.building).data
        self.assertEqual(
            (
                data['apartment_count'], data['room_count'], data['bed_count'],
                data['occupied_beds'], data['free_beds'],
            ),
            (7, 8, 9, 4, 5),
        )

    def test_apartment_annotations_avoid_fallback_queries(self):
        self.apartment.building.dorm_type.region
        self.apartment._actual_room_count = 6
        self.apartment._bed_count = 10
        self.apartment._occupied_beds = 3
        with self.assertNumQueries(0):
            data = serializer_module.ApartmentSerializer(self.apartment).data
        self.assertEqual(
            (
                data['actual_room_count'], data['bed_count'],
                data['occupied_beds'], data['free_beds'],
            ),
            (6, 10, 3, 7),
        )

    def test_room_annotations_avoid_fallback_queries(self):
        self.room.apartment.building.dorm_type.region
        self.room._current_occupancy = 1
        self.room._available_beds = 4
        self.room._is_full = False
        self.room._bed_count = 5
        self.room._has_missing_bed_records = True
        with self.assertNumQueries(0):
            data = serializer_module.RoomSerializer(self.room).data
        self.assertEqual(
            (
                data['current_occupancy'], data['available_beds'],
                data['is_full'], data['bed_count'],
                data['has_missing_bed_records'],
            ),
            (1, 4, False, 5, True),
        )

    def test_bed_annotation_avoids_fallback_query(self):
        self.bed.room.apartment.building
        self.bed._is_occupied = False
        with self.assertNumQueries(0):
            data = serializer_module.BedSerializer(self.bed).data
        self.assertFalse(data['is_occupied'])

    def test_student_list_prefetched_active_assignment_avoids_fallback(self):
        self.student.assigned_room.apartment.building
        self.student.accepted_dorm_type
        self.student.prefetched_active_assignments = [self.assignment]
        with patch.object(
            Student,
            'current_bed',
            new_callable=PropertyMock,
            side_effect=AssertionError('fallback current_bed was used'),
        ):
            with self.assertNumQueries(0):
                data = serializer_module.StudentListSerializer(
                    self.student,
                ).data
        self.assertEqual(data['current_bed'], self.bed.label)

    def test_student_detail_caches_current_bed_for_both_fields(self):
        self.student.assigned_room.apartment.building
        self.student.accepted_dorm_type.region
        with patch.object(
            Student,
            'current_bed',
            new_callable=PropertyMock,
            return_value=self.bed,
        ) as current_bed:
            data = serializer_module.StudentSerializer(self.student).data
        self.assertEqual(current_bed.call_count, 1)
        self.assertEqual(data['current_bed_id'], self.bed.pk)
        self.assertEqual(data['current_bed_label'], self.bed.label)

    def test_student_request_prefetched_placement_paths_avoid_fallback(self):
        self.student.assigned_room.apartment.building.dorm_type.region
        self.assignment.bed.room.apartment.building.dorm_type.region
        self.student.prefetched_current_assignment_list = [self.assignment]
        self.student.prefetched_placement_history_all = [self.assignment]
        serializer = serializer_module.StudentRequestSerializer()
        with patch.object(
            Student,
            'current_bed',
            new_callable=PropertyMock,
            side_effect=AssertionError('fallback current_bed was used'),
        ):
            with self.assertNumQueries(0):
                current_bed = serializer.get_current_bed(
                    self.student_request,
                )
                history = serializer.get_placement_history(
                    self.student_request,
                )
        self.assertEqual(current_bed, self.bed.label)
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]['room'], self.room.name)


class SerializerImportTimingTests(SimpleTestCase):
    databases = set()

    def run_fresh_python(self, source):
        completed = subprocess.run(
            [sys.executable, '-c', textwrap.dedent(source)],
            cwd=os.getcwd(),
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

    def test_each_fresh_import_keeps_allocation_and_solver_stacks_unloaded(self):
        for target in ('api.serializers', 'api.views', 'api.urls'):
            with self.subTest(target=target):
                result = self.run_fresh_python(f"""
                    import importlib
                    import json
                    import os
                    import sys
                    os.environ.setdefault(
                        'DJANGO_SETTINGS_MODULE', 'dormify.settings'
                    )
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

    def test_apartment_conflict_resolves_gateway_only_at_call_time(self):
        result = self.run_fresh_python("""
            import importlib
            import json
            import os
            import sys
            from types import SimpleNamespace
            from unittest.mock import MagicMock, patch

            os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'dormify.settings')
            import django
            django.setup()

            serializers = importlib.import_module('api.serializers')
            gateway = importlib.import_module(
                'api.domains.allocation.gateway'
            )

            def blocked_modules():
                return sorted(
                    name for name in sys.modules
                    if name == 'allocation'
                    or name.startswith('allocation.')
                    or name.startswith('ortools')
                    or name.startswith('google.protobuf')
                )

            calls = []
            def gateway_getattr(name):
                calls.append(name)
                if name == '_housing_matches_apartment':
                    return lambda student, apartment: False
                raise AttributeError(name)

            manager = MagicMock()
            queryset = MagicMock()
            queryset.select_related.return_value = [
                SimpleNamespace(student=object())
            ]
            manager.filter.return_value = queryset
            instance = SimpleNamespace(
                is_active=True,
                category='male',
                apartment_type='single',
                apartment_capacity=2,
            )

            early = serializers.check_apartment_write_conflict(
                None, {'category': 'female'}
            )
            before = blocked_modules()
            calls_before = list(calls)
            with patch.object(
                serializers.inventory.BedAssignment, 'objects', manager
            ), patch.object(gateway, '__getattr__', gateway_getattr):
                conflict = serializers.check_apartment_write_conflict(
                    instance, {'category': 'female'}
                )
            after = blocked_modules()
            print(json.dumps({
                'early': early,
                'before': before,
                'calls_before': calls_before,
                'calls_after': calls,
                'after': after,
                'conflict': conflict,
            }, ensure_ascii=False))
        """)
        self.assertIsNone(result['early'])
        self.assertEqual(result['before'], [])
        self.assertEqual(result['calls_before'], [])
        self.assertIn('_housing_matches_apartment', result['calls_after'])
        self.assertEqual(result['after'], [])
        self.assertEqual(result['conflict']['field'], 'category')
        self.assertEqual(
            result['conflict']['code'], 'ACTIVE_OCCUPANT_CONFLICT',
        )
