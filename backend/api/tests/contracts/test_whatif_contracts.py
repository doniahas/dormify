"""Contracts of the what-if simulation and confirm endpoints."""

from api.models import StudentRequest

from ._support import ContractTestCase, assign, make_full_stack, make_region, make_student

SNAPSHOT_KEYS = [
    'total_students', 'assigned_students', 'unassigned_students', 'total_buildings', 'total_rooms',
    'total_capacity', 'total_beds', 'occupied_beds', 'assigned_beds', 'available_beds', 'occupancy_rate',
]
BREAKDOWN_KEYS = ['gender', 'requested_religion', 'religious', 'placement_sector', 'category', 'housing_type']
AFFECTED_STUDENT_KEYS = [
    'assignment_id', 'student_db_id', 'student_id', 'business_partner_id', 'full_name', 'first_name', 'last_name',
    'gender', 'requested_religion', 'religious', 'placement_sector', 'category', 'housing_type',
    'gender_display', 'requested_religion_display', 'religious_display', 'is_priority', 'priority_reason',
    'accepted_dorm_type_id', 'accepted_dorm_type_name',
    'current_building_id', 'current_building_number', 'current_apartment_id', 'current_apartment_number',
    'current_room_id', 'current_room_name', 'current_bed_id', 'current_bed_label',
    'dorm_type_id', 'dorm_type_name', 'region_id', 'region_name', 'status',
]
SUMMARY_KEYS = [
    'affected_students_count', 'students_without_valid_placement', 'male_count', 'female_count',
    'lost_apartments', 'lost_rooms', 'lost_capacity', 'lost_beds',
]


class WhatIfContractTests(ContractTestCase):
    def setUp(self):
        super().setUp()
        self.dorm, self.building, self.apartment, self.room = make_full_stack(self.region)
        assign(make_student(self.dorm, 'WI-1'), self.room)

    def test_building_simulation_body(self):
        response = self.client_for(self.employee).post(
            '/api/what-if/building-inactivation/simulate/', {'building_ids': [self.building.id]}, format='json',
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertKeys(response.data, [
            'success', 'scenario', 'selected_buildings', 'summary', 'breakdowns', 'analysis_before', 'analysis_after', 'affected_students',
        ])
        self.assertEqual(response.data['scenario'], 'building_inactivation')
        self.assertKeys(response.data['selected_buildings'][0], ['id', 'number', 'dorm_type_id', 'dorm_type_name', 'region_id', 'region_name', 'is_active'])
        self.assertKeys(response.data['summary'], SUMMARY_KEYS)
        self.assertKeys(response.data['breakdowns'], BREAKDOWN_KEYS)
        self.assertEqual(response.data['breakdowns']['gender'], [{'value': 'male', 'count': 1}])
        self.assertKeys(response.data['analysis_before'], SNAPSHOT_KEYS)
        self.assertKeys(response.data['analysis_after'], SNAPSHOT_KEYS)
        self.assertKeys(response.data['affected_students'][0], AFFECTED_STUDENT_KEYS)
        self.assertEqual(response.data['affected_students'][0]['status'], 'needs_transfer')

    def test_availability_simulation_body(self):
        response = self.client_for(self.employee).post(
            '/api/what-if/availability/simulate/', {'target_type': 'room', 'target_ids': [self.room.id]}, format='json',
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertKeys(response.data, [
            'success', 'scenario', 'target_type', 'target_ids', 'selected_targets', 'summary', 'breakdowns',
            'analysis_before', 'analysis_after', 'affected_students',
        ])
        self.assertEqual(response.data['scenario'], 'room_availability_change')
        self.assertEqual(response.data['target_ids'], [self.room.id])
        self.assertKeys(response.data['selected_targets'][0], [
            'id', 'target_type', 'label', 'room_id', 'room_name', 'apartment_id', 'apartment_number',
            'building_id', 'building_number', 'dorm_type_id', 'dorm_type_name', 'region_id', 'region_name',
            'capacity', 'is_active',
        ])
        self.assertKeys(response.data['summary'], SUMMARY_KEYS)

    def test_request_validation_bodies(self):
        client = self.client_for(self.employee)
        self.assertFailureBody(client.post('/api/what-if/building-inactivation/simulate/', {}, format='json'), 400,
                               'building_ids must be a non-empty list.')
        self.assertFailureBody(client.post('/api/what-if/building-inactivation/simulate/', {'building_ids': [999999]}, format='json'), 400,
                               'One or more selected buildings were not found.')
        self.assertFailureBody(client.post('/api/what-if/availability/simulate/', {'target_type': 'bed', 'target_ids': [1]}, format='json'), 400,
                               'target_type must be one of: building, apartment, room.')
        self.assertFailureBody(client.post('/api/what-if/availability/simulate/', {'target_type': 'room'}, format='json'), 400,
                               'target_ids must be a non-empty list.')
        self.assertFailureBody(client.post('/api/what-if/availability/simulate/', {'target_type': 'room', 'target_ids': [999999]}, format='json'), 400,
                               'One or more selected targets were not found.')
        boss = self.client_for(self.boss)
        self.assertFailureBody(boss.post('/api/what-if/availability/confirm/', {
            'target_type': 'room', 'target_ids': [self.room.id], 'action': 'activate',
        }, format='json'), 400, 'action must be inactivate or reactivate.')

    def test_permission_bodies(self):
        other = make_region('Contract Other WhatIf')
        _d, foreign_building, _a, foreign_room = make_full_stack(other)
        employee = self.client_for(self.employee)
        self.assertFailureBody(employee.post('/api/what-if/building-inactivation/simulate/', {'building_ids': [foreign_building.id]}, format='json'), 403,
                               'אין הרשאה לבצע סימולציה עבור אחד או יותר מהבניינים שנבחרו.')
        self.assertFailureBody(employee.post('/api/what-if/availability/simulate/', {'target_type': 'room', 'target_ids': [foreign_room.id]}, format='json'), 403,
                               'אין הרשאה לבצע סימולציה עבור אחד או יותר מהפריטים שנבחרו.')
        self.assertFailureBody(employee.post('/api/what-if/availability/confirm/', {'target_type': 'room', 'target_ids': [self.room.id]}, format='json'), 403,
                               'רק מנהל יכול לאשר שינוי זמינות ויצירת בקשות העברה.')
        self.assertFailureBody(employee.post('/api/what-if/building-inactivation/confirm/', {'building_ids': [self.building.id]}, format='json'), 403,
                               'רק מנהל יכול לאשר השבתת בניינים ויצירת בקשות העברה.')
        self.assertFailureBody(self.client_for(self.boss).post('/api/what-if/availability/confirm/', {'target_type': 'room', 'target_ids': [foreign_room.id]}, format='json'), 403,
                               'אין הרשאה לשנות זמינות עבור אחד או יותר מהפריטים שנבחרו.')

    def test_confirm_bodies(self):
        boss = self.client_for(self.boss)
        response = boss.post('/api/what-if/availability/confirm/', {
            'target_type': 'room', 'target_ids': [self.room.id], 'reason': 'works',
        }, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertKeys(response.data, [
            'success', 'message', 'target_type', 'target_ids', 'action', 'affected_students_count',
            'created_requests', 'skipped_existing_requests', 'created_request_ids',
        ])
        self.assertEqual(response.data['message'], 'Availability change confirmed.')
        self.assertEqual((response.data['action'], response.data['created_requests'], response.data['skipped_existing_requests']), ('inactivate', 1, 0))
        self.assertEqual(StudentRequest.objects.filter(pk__in=response.data['created_request_ids']).count(), 1)

        response = boss.post('/api/what-if/building-inactivation/confirm/', {'building_ids': [self.building.id]}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertKeys(response.data, [
            'success', 'message', 'inactivated_buildings', 'selected_building_ids', 'affected_students_count',
            'created_requests', 'skipped_existing_requests', 'created_request_ids',
        ])
        self.assertIs(response.data['inactivated_buildings'], True)
        self.assertEqual(response.data['selected_building_ids'], [self.building.id])
        self.assertEqual((response.data['created_requests'], response.data['skipped_existing_requests']), (0, 1))
