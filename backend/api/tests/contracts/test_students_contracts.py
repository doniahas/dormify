"""Contracts of the students, placement and match-options endpoints."""

from api.models import Student
from api.serializers import StudentListSerializer, StudentSerializer

from ._support import ContractTestCase, assign, make_full_stack, make_region, make_student, serializer_keys

PAGE_KEYS = ['count', 'next', 'previous', 'results']
ABSENT_WHILE_UNASSIGNED = ['assigned_room_id', 'assigned_room_name', 'assigned_building_number', 'assigned_apartment_number']
MATCH_KEYS = [
    'feasible', 'reason', 'transfer_scope', 'search_regions', 'buildings', 'loaded_buildings',
    'total_buildings', 'total_apartments', 'total_rooms', 'total_valid_beds', 'total_valid',
    'limit', 'offset', 'has_more', 'next_offset', 'conflict_examples', 'counts', 'data_integrity',
]


class StudentListContractTests(ContractTestCase):
    def setUp(self):
        super().setUp()
        self.dorm, self.building, self.apartment, self.room = make_full_stack(self.region)
        self.assigned = make_student(self.dorm, 'ST-A')
        assign(self.assigned, self.room)
        self.unassigned = make_student(self.dorm, 'ST-U', category=Student.StudentCategory.CONTINUING)

    def test_list_is_paginated_with_summary_rows(self):
        response = self.client_for(self.employee).get('/api/students/')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertKeys(response.data, PAGE_KEYS)
        self.assertEqual(response.data['count'], 2)
        self.assertIsNone(response.data['next'])
        self.assertKeys(response.data['results'][0], serializer_keys(StudentListSerializer))
        row = next(r for r in response.data['results'] if r['student_id'] == 'ST-A')
        self.assertEqual((row['is_assigned'], row['current_building'], row['current_bed']), (True, self.building.number, '1'))
        self.assertEqual(row['accepted_dorm_type'], self.dorm.id)

    def test_filters_and_region_scoping(self):
        employee = self.client_for(self.employee)
        self.assertEqual(employee.get('/api/students/?status=assigned').data['count'], 1)
        self.assertEqual(employee.get('/api/students/?category=continuing').data['count'], 1)
        self.assertEqual(employee.get('/api/students/?search=ST-U').data['count'], 1)
        other = make_region('Contract Other Students')
        other_dorm, _b, _a, _r = make_full_stack(other)
        make_student(other_dorm, 'ST-F')
        self.assertEqual(employee.get('/api/students/').data['count'], 2)
        self.assertEqual(self.client_for(self.admin).get('/api/students/').data['count'], 3)
        self.assertEqual(self.client_for(self.admin).get(f'/api/students/?region={other.id}').data['count'], 1)

    def test_detail_create_and_update_bodies(self):
        employee = self.client_for(self.employee)
        response = employee.get(f'/api/students/{self.assigned.id}/')
        self.assertEqual(response.status_code, 200)
        self.assertKeys(response.data, serializer_keys(StudentSerializer))
        self.assertEqual((response.data['region_id'], response.data['assigned_room_id'], response.data['current_bed_label']), (self.region.id, self.room.id, '1'))
        self.assertDetailBody(employee.get('/api/students/999999/'), 404)

        response = employee.post('/api/students/', {
            'student_id': 'ST-NEW', 'first_name': 'N', 'last_name': 'S', 'gender': 'female',
            'housing_type': Student.HousingType.SINGLE_FEMALE, 'accepted_dorm_type': self.dorm.id,
        }, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        # Contract quirk: the four assigned_room-sourced fields are DRF
        # dotted-source fields without a default, so they are OMITTED (not
        # null) while the student has no assigned room.
        self.assertKeys(response.data, [k for k in serializer_keys(StudentSerializer) if k not in ABSENT_WHILE_UNASSIGNED])
        self.assertIsNone(response.data['current_bed_id'])
        response = employee.patch(f'/api/students/{self.unassigned.id}/', {'city': 'Haifa'}, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['city'], 'Haifa')
        for key in ABSENT_WHILE_UNASSIGNED:
            self.assertNotIn(key, response.data)
        row = next(r for r in employee.get('/api/students/').data['results'] if r['student_id'] == 'ST-U')
        self.assertIn('accepted_dorm_type_name', row)

    def test_validation_and_authorization_bodies(self):
        employee = self.client_for(self.employee)
        response = employee.post('/api/students/', {'student_id': 'ST-X', 'first_name': 'a', 'last_name': 'b', 'gender': 'male'}, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data, {'housing_type': ['יש לבחור סוג דיור לפני שניתן לבצע שיבוץ.']})
        response = employee.patch(f'/api/students/{self.assigned.id}/', {'assigned_room': None}, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['assigned_room'], self.room.id)
        other_dorm, _b, _a, _r = make_full_stack(make_region('Contract Other Student Write'))
        response = employee.post('/api/students/', {
            'student_id': 'ST-Y', 'first_name': 'a', 'last_name': 'b', 'gender': 'male',
            'housing_type': Student.HousingType.SINGLE_MALE, 'accepted_dorm_type': other_dorm.id,
        }, format='json')
        self.assertDetailBody(response, 403)
        self.assertEqual(response.data['detail'], 'אינך מורשה לשייך סטודנט לאזור זה')

    def test_counts_and_filter_options_bodies(self):
        response = self.client_for(self.employee).get('/api/students/counts/')
        self.assertEqual(response.data, {'all': 2, 'continuing': 1, 'new': 1, 'transfer': 0, 'leaving': 0, 'unassigned': 0})
        response = self.client_for(self.employee).get('/api/students/filter-options/')
        self.assertKeys(response.data, ['is_central_admin', 'regions', 'buildings', 'dorm_types', 'apartments', 'rooms', 'religions', 'housing_types'])
        self.assertIs(response.data['is_central_admin'], False)
        self.assertEqual(response.data['regions'], [{'id': self.region.id, 'name': self.region.name}])
        self.assertKeys(response.data['dorm_types'][0], ['id', 'name', 'region_id', 'region_name'])
        self.assertKeys(response.data['religions'][0], ['id', 'name'])
        self.assertEqual(len(response.data['housing_types']), 5)


class PlacementContractTests(ContractTestCase):
    def setUp(self):
        super().setUp()
        self.dorm, self.building, self.apartment, self.room = make_full_stack(self.region)
        self.student = make_student(self.dorm, 'PL-1')

    def test_assign_move_unassign_bodies(self):
        client = self.client_for(self.employee)
        response = client.post('/api/room-assignments/assign/', {'student_id': self.student.id, 'room_id': self.room.id}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertKeys(response.data, ['success', 'message', 'assignment_id', 'student_id', 'room_id', 'bed_id'])
        self.assertEqual(response.data['message'], 'Student assigned successfully')
        response = client.post('/api/room-assignments/unassign/', {'student': self.student.student_id}, format='json')
        self.assertEqual(response.data, {'success': True, 'message': 'Student unassigned successfully', 'student_id': self.student.id})
        response = client.post('/api/room-assignments/unassign/', {'student_id': self.student.id}, format='json')
        self.assertEqual(response.data, {'success': True, 'message': 'Student was already unassigned'})

    def test_placement_error_bodies(self):
        client = self.client_for(self.employee)
        self.assertErrorBody(client.post('/api/room-assignments/assign/', {}, format='json'), 400, 'Missing student_id')
        self.assertErrorBody(client.post('/api/room-assignments/assign/', {'student_id': self.student.id}, format='json'), 400, 'Missing room_id')
        self.assertErrorBody(client.post('/api/room-assignments/assign/', {'student_id': 999999, 'room_id': self.room.id}, format='json'), 404, 'Student or room not found')
        self.assertErrorBody(client.post('/api/room-assignments/unassign/', {'student_id': 999999}, format='json'), 404, 'Student not found')
        self.assertErrorBody(client.post('/api/room-assignments/swap/', {'student_a_id': self.student.id}, format='json'), 400, 'Missing student_a_id or student_b_id')
        other_dorm, _b, _a, foreign_room = make_full_stack(make_region('Contract Other Placement'))
        self.assertErrorBody(client.post('/api/room-assignments/assign/', {'student_id': self.student.id, 'room_id': foreign_room.id}, format='json'), 403, 'אין הרשאה לערוך חדר באזור זה')


class MatchOptionsContractTests(ContractTestCase):
    def setUp(self):
        super().setUp()
        self.dorm, self.building, self.apartment, self.room = make_full_stack(self.region)
        self.student = make_student(self.dorm, 'MO-1')

    def test_match_options_body(self):
        response = self.client_for(self.employee).post('/api/requests/match-options/', {'student_id': self.student.id}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertKeys(response.data, MATCH_KEYS)
        self.assertIs(response.data['feasible'], True)
        self.assertEqual(response.data['reason'], '')
        self.assertEqual(response.data['search_regions'], [{'id': self.region.id, 'name': self.region.name}])
        self.assertEqual((response.data['limit'], response.data['offset']), (10, 0))
        building = response.data['buildings'][0]
        for key in ('building_id', 'building_number', 'apartments', 'recommendation_level', 'available_bed_count'):
            self.assertIn(key, building)
        bed = building['apartments'][0]['rooms'][0]['beds'][0]
        self.assertKeys(bed, ['bed_id', 'bed_label', 'is_occupied', 'occupant_name', 'is_selectable'])

    def test_match_options_error_and_blocker_bodies(self):
        client = self.client_for(self.employee)
        response = client.post('/api/requests/match-options/', {'student_id': 999999}, format='json')
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.data, {'feasible': False, 'buildings': [], 'reason': 'הסטודנט לא נמצא'})
        leaving = make_student(self.dorm, 'MO-L', category=Student.StudentCategory.LEAVING)
        response = client.post('/api/requests/match-options/', {'student_id': leaving.id}, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['blocking_field'], 'category')
        self.assertIs(response.data['feasible'], False)
        self.assertKeys(response.data, ['feasible', 'reason', 'blocking_field', 'buildings', 'loaded_buildings', 'total_buildings', 'total_apartments', 'total_rooms', 'total_valid_beds', 'total_valid', 'limit', 'offset', 'has_more', 'next_offset', 'conflict_examples', 'counts', 'data_integrity'])
        response = client.post('/api/requests/match-options/', {'student_id': self.student.id, 'transfer_scope': 'cross_region'}, format='json')
        self.assertDetailBody(response, 403)
        self.assertEqual(response.data['detail'], 'אין לך הרשאה לבצע מעבר לאזור אחר.')
        response = self.client_for(self.admin).post('/api/requests/match-options/', {'student_id': self.student.id, 'transfer_scope': 'cross_region'}, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data['reason'], 'יש לבחור לפחות אזור יעד אחד עבור מעבר לאזור אחר.')
        self.assertIs(response.data['feasible'], False)
