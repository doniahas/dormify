"""Behavioral characterization tests for GET /api/statistics/."""

from datetime import UTC, datetime

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from api.models import (
    Apartment,
    Bed,
    BedAssignment,
    Building,
    DormType,
    Region,
    Room,
    Student,
    Transfer,
    User,
)


STATISTICS_KEYS = [
    'total_students',
    'assigned_students',
    'unassigned_students',
    'priority_students',
    'total_buildings',
    'active_buildings',
    'inactive_buildings',
    'total_rooms',
    'total_capacity',
    'occupied_beds',
    'available_beds',
    'occupancy_rate',
    'pending_transfers',
]


def _make_user(email, role, region=None):
    return User.objects.create_user(
        email=email,
        username=email,
        password='testpass123',
        role=role,
        region=region,
    )


def _make_inventory(region, code, building_number, capacity, *, building_active=True):
    dorm_type = DormType.objects.create(
        region=region,
        code=code,
        name=f'Dorm {code}',
    )
    building = Building.objects.create(
        dorm_type=dorm_type,
        number=building_number,
        is_active=building_active,
    )
    apartment = Apartment.objects.create(
        building=building,
        number='1',
        category=Apartment.Category.MALE,
        apartment_type=Apartment.ApartmentType.SINGLE,
        room_count=1,
    )
    room = Room.objects.create(
        apartment=apartment,
        name='101',
        capacity=capacity,
    )
    beds = [
        Bed.objects.create(room=room, label=str(index))
        for index in range(1, capacity + 1)
    ]
    return dorm_type, building, apartment, room, beds


def _make_student(student_id, dorm_type, **extra):
    return Student.objects.create(
        student_id=student_id,
        first_name='Test',
        last_name='Student',
        gender=Student.Gender.MALE,
        housing_type=Student.HousingType.SINGLE_MALE,
        accepted_dorm_type=dorm_type,
        **extra,
    )


class StatisticsReadModelCharacterizationTests(TestCase):
    def setUp(self):
        self.region_a = Region.objects.create(id='region-a', name='Region A')
        self.region_b = Region.objects.create(id='region-b', name='Region B')
        self.admin = _make_user('admin@test.com', User.Role.CENTRAL_ADMIN)
        self.boss_a = _make_user(
            'boss-a@test.com', User.Role.REGION_BOSS, self.region_a,
        )
        self.client = APIClient()

    def _get_statistics(self, user, **params):
        self.client.force_authenticate(user)
        response = self.client.get('/api/statistics/', params)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.content)
        return response.json()

    def _create_populated_fixture(self):
        dorm_a, active_a, apartment_a, room_a, beds_a = _make_inventory(
            self.region_a, 101, 1, 3,
        )

        inactive_room_a = Room.objects.create(
            apartment=apartment_a,
            name='102',
            capacity=7,
            is_active=False,
        )

        _, inactive_a, _, inactive_building_room, _ = _make_inventory(
            self.region_a, 102, 2, 11, building_active=False,
        )

        dorm_b, active_b, _, room_b, beds_b = _make_inventory(
            self.region_b, 201, 1, 2,
        )

        priority_assigned = _make_student(
            'A-1', dorm_a, is_priority=True,
        )
        ended_student = _make_student('A-2', dorm_a)
        _make_student(
            'A-3', dorm_a,
            is_priority=True,
            category=Student.StudentCategory.LEAVING,
        )
        _make_student(
            'A-4', dorm_a,
            is_priority=True,
            accessibility_flag=True,
        )
        assigned_b = _make_student('B-1', dorm_b)

        BedAssignment.objects.create(
            student=priority_assigned,
            bed=beds_a[0],
            status=BedAssignment.Status.ACTIVE,
        )
        BedAssignment.objects.create(
            student=ended_student,
            bed=beds_a[1],
            status=BedAssignment.Status.ENDED,
            ended_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
        BedAssignment.objects.create(
            student=assigned_b,
            bed=beds_b[0],
            status=BedAssignment.Status.ACTIVE,
        )

        Transfer.objects.create(
            student=priority_assigned,
            from_room=room_a,
            to_room=inactive_room_a,
            requested_by=self.admin,
            status=Transfer.Status.PENDING,
        )
        Transfer.objects.create(
            student=ended_student,
            from_room=room_a,
            to_room=inactive_building_room,
            requested_by=self.admin,
            status=Transfer.Status.APPROVED,
            reviewed_by=self.admin,
            reviewed_at=datetime(2026, 1, 2, tzinfo=UTC),
        )

        return {
            'active_buildings': (active_a, active_b),
            'inactive_building': inactive_a,
            'active_rooms': (room_a, room_b),
            'inactive_room': inactive_room_a,
        }

    def test_empty_global_response_has_exact_order_types_and_zero_values(self):
        data = self._get_statistics(self.admin)

        self.assertEqual(list(data), STATISTICS_KEYS)
        self.assertEqual(data, {key: 0 for key in STATISTICS_KEYS})
        for value in data.values():
            self.assertIs(type(value), int)

    def test_populated_global_response_pins_complete_contract_and_filters(self):
        self._create_populated_fixture()

        data = self._get_statistics(self.admin)

        self.assertEqual(list(data), STATISTICS_KEYS)
        self.assertEqual(data, {
            'total_students': 5,
            'assigned_students': 2,
            'unassigned_students': 3,
            'priority_students': 1,
            'total_buildings': 3,
            'active_buildings': 2,
            'inactive_buildings': 1,
            'total_rooms': 2,
            'total_capacity': 5,
            'occupied_beds': 2,
            'available_beds': 3,
            'occupancy_rate': 40,
            'pending_transfers': 1,
        })
        for value in data.values():
            self.assertIs(type(value), int)

    def test_occupancy_rate_uses_integer_rounding(self):
        dorm_type, _, _, _, beds = _make_inventory(
            self.region_a, 101, 1, 3,
        )
        student = _make_student('A-1', dorm_type)
        BedAssignment.objects.create(
            student=student,
            bed=beds[0],
            status=BedAssignment.Status.ACTIVE,
        )

        data = self._get_statistics(self.admin)

        self.assertEqual(data['occupied_beds'], 1)
        self.assertEqual(data['total_capacity'], 3)
        self.assertEqual(data['occupancy_rate'], 33)
        self.assertIs(type(data['occupancy_rate']), int)

    def test_active_and_ended_assignments_have_distinct_effects(self):
        dorm_type, _, _, _, beds = _make_inventory(
            self.region_a, 101, 1, 3,
        )
        active_student = _make_student('A-1', dorm_type)
        ended_student = _make_student('A-2', dorm_type)
        BedAssignment.objects.create(
            student=active_student,
            bed=beds[0],
            status=BedAssignment.Status.ACTIVE,
        )
        BedAssignment.objects.create(
            student=ended_student,
            bed=beds[1],
            status=BedAssignment.Status.ENDED,
            ended_at=datetime(2026, 1, 1, tzinfo=UTC),
        )

        data = self._get_statistics(self.admin)

        self.assertEqual(data['total_students'], 2)
        self.assertEqual(data['assigned_students'], 1)
        self.assertEqual(data['unassigned_students'], 1)
        self.assertEqual(data['occupied_beds'], 1)
        self.assertEqual(data['available_beds'], 2)
        self.assertEqual(data['occupancy_rate'], 33)

    def test_global_and_regional_responses_use_their_respective_scopes(self):
        self._create_populated_fixture()

        global_data = self._get_statistics(self.admin)
        boss_a_data = self._get_statistics(self.boss_a)
        admin_a_data = self._get_statistics(self.admin, region=self.region_a.id)

        self.assertEqual(boss_a_data, admin_a_data)
        self.assertEqual(global_data['total_students'], 5)
        self.assertEqual(global_data['total_capacity'], 5)
        self.assertEqual(global_data['occupied_beds'], 2)
        self.assertEqual(boss_a_data, {
            'total_students': 4,
            'assigned_students': 1,
            'unassigned_students': 3,
            'priority_students': 1,
            'total_buildings': 2,
            'active_buildings': 1,
            'inactive_buildings': 1,
            'total_rooms': 1,
            'total_capacity': 3,
            'occupied_beds': 1,
            'available_beds': 2,
            'occupancy_rate': 33,
            'pending_transfers': 1,
        })
