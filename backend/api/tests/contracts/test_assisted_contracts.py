"""Contracts of the assisted-allocation workbench endpoints."""

from api.models import StudentRequest
from api.serializers import StudentRequestSerializer

from ._support import ContractTestCase, assign, make_full_stack, make_region, make_student, serializer_keys

QUEUE_ROW_KEYS = [
    'student_db_id', 'student_id', 'full_name', 'first_name', 'last_name',
    'gender', 'gender_display', 'accepted_dorm_type_id', 'accepted_dorm_type',
    'housing_type', 'housing_type_display', 'requested_religion', 'religion_display',
    'region_id', 'region', 'is_priority', 'priority_reason',
    'accessibility_flag', 'disability_percent', 'medical_reason', 'special_statuses',
    'group', 'is_transfer_requested',
]
COUNT_KEYS = ['accessibility_pending', 'unassigned', 'resolved', 'transfer_requested', 'needs_placement']
EMPTY_CANDIDATES = {'buildings': [], 'total_valid_beds': 0, 'has_more': False, 'next_offset': None, 'feasible': False}


class AssistedQueueContractTests(ContractTestCase):
    def setUp(self):
        super().setUp()
        self.dorm, _b, _a, self.room = make_full_stack(self.region)
        self.unassigned = make_student(self.dorm, 'AQ-1')
        self.accessibility = make_student(self.dorm, 'AQ-ACC', accessibility_flag=True)

    def test_queue_body_and_row_shape(self):
        response = self.client_for(self.employee).get('/api/assisted-allocation/queue/')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertKeys(response.data, ['counts', 'students', 'region_id', 'region_name'])
        self.assertKeys(response.data['counts'], COUNT_KEYS)
        self.assertEqual(response.data['counts']['needs_placement'], 2)
        self.assertEqual(response.data['region_id'], self.region.id)
        self.assertEqual(len(response.data['students']), 2)
        row = response.data['students'][0]
        self.assertKeys(row, QUEUE_ROW_KEYS)
        self.assertIn(row['group'], ('accessibility', 'unassigned'))
        self.assertIsNone(row['disability_percent'])

    def test_queue_tab_filters_and_scoping(self):
        client = self.client_for(self.employee)
        self.assertEqual([r['student_id'] for r in client.get('/api/assisted-allocation/queue/?tab=unassigned').data['students']], ['AQ-1'])
        self.assertEqual(client.get('/api/assisted-allocation/queue/?tab=resolved').data['students'], [])
        self.assertEqual(client.get('/api/assisted-allocation/queue/?search=aq-acc').data['students'][0]['student_id'], 'AQ-ACC')
        other = make_region('Contract Other Queue')
        self.assertErrorBody(client.get(f'/api/assisted-allocation/queue/?region={other.id}'), 403, 'אין הרשאה לאזור זה')
        admin = self.client_for(self.admin).get('/api/assisted-allocation/queue/')
        self.assertEqual((admin.data['region_id'], admin.data['region_name']), (None, None))


class AssistedStudentContractTests(ContractTestCase):
    def setUp(self):
        super().setUp()
        self.dorm, _b, _a, self.room = make_full_stack(self.region)
        self.student = make_student(self.dorm, 'AS-1')
        self.bed = self.room.beds.order_by('label').first()

    def test_detail_body(self):
        response = self.client_for(self.employee).get(f'/api/assisted-allocation/students/{self.student.id}/detail/')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertKeys(response.data, ['student', 'roommate_requests', 'reason', 'history', 'current_placement', 'pending_transfer_request'])
        self.assertKeys(response.data['student'], QUEUE_ROW_KEYS)
        self.assertEqual(response.data['student']['group'], 'unassigned')
        self.assertKeys(response.data['reason'], ['reason_code', 'physically_free_beds_in_accepted_dorm', 'compatible_free_beds', 'inventory_breakdown'])
        self.assertEqual(response.data['history'], [])
        self.assertEqual(response.data['current_placement'], {'assigned': False})
        self.assertIsNone(response.data['pending_transfer_request'])

    def test_detail_with_pending_transfer_serializes_the_request(self):
        target = make_region('Contract Transfer Target')
        request = StudentRequest.objects.create(
            student=self.student, request_type=StudentRequest.RequestType.REGION_TRANSFER,
            status=StudentRequest.Status.PENDING, requested_by=self.boss, target_region=target,
        )
        response = self.client_for(self.employee).get(f'/api/assisted-allocation/students/{self.student.id}/detail/')
        self.assertEqual(response.data['student']['group'], 'transfer_pending')
        self.assertIsNone(response.data['reason'])
        self.assertKeys(response.data['pending_transfer_request'], serializer_keys(StudentRequestSerializer))
        self.assertEqual(response.data['pending_transfer_request']['id'], request.id)

    def test_detail_errors(self):
        self.assertErrorBody(self.client_for(self.employee).get('/api/assisted-allocation/students/999999/detail/'), 404, 'הסטודנט לא נמצא')
        other = make_region('Contract Other Detail')
        foreign_dorm, _b, _a, _r = make_full_stack(other)
        foreign = make_student(foreign_dorm, 'AS-F')
        self.assertErrorBody(self.client_for(self.employee).get(f'/api/assisted-allocation/students/{foreign.id}/detail/'), 403, 'אין הרשאה לאזור זה')

    def test_recommendations_bodies(self):
        client = self.client_for(self.employee)
        response = client.get(f'/api/assisted-allocation/students/{self.student.id}/recommendations/')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertKeys(response.data, ['candidates', 'config_opportunities', 'has_unsafe_config_candidates', 'accepted_dorm_type'])
        self.assertEqual(response.data['accepted_dorm_type'], {'id': self.dorm.id, 'name': self.dorm.name})
        self.assertIn('buildings', response.data['candidates'])
        self.assertIn('total_valid_beds', response.data['candidates'])

        assign(self.student, self.room)
        response = client.get(f'/api/assisted-allocation/students/{self.student.id}/recommendations/')
        self.assertKeys(response.data, ['candidates', 'config_opportunities', 'has_unsafe_config_candidates', 'accepted_dorm_type', 'already_assigned', 'transfer_pending'])
        self.assertEqual(response.data['candidates'], EMPTY_CANDIDATES)
        self.assertIs(response.data['already_assigned'], True)
        self.assertIs(response.data['transfer_pending'], False)

    def test_override_check_body_and_errors(self):
        client = self.client_for(self.employee)
        self.assertErrorBody(client.get(f'/api/assisted-allocation/students/{self.student.id}/override-check/'), 400, 'יש לבחור מיטה')
        self.assertErrorBody(client.get(f'/api/assisted-allocation/students/{self.student.id}/override-check/?bed_id=999999'), 404, 'המיטה לא נמצאה')
        response = client.get(f'/api/assisted-allocation/students/{self.student.id}/override-check/?bed_id={self.bed.id}')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertKeys(response.data, ['violations', 'blocked', 'requires_override'])
        self.assertIsInstance(response.data['violations'], list)

    def test_assign_and_override_bodies(self):
        client = self.client_for(self.employee)
        self.assertErrorBody(client.post(f'/api/assisted-allocation/students/{self.student.id}/assign/', {}, format='json'), 400, 'יש לבחור מיטה')
        self.assertErrorBody(client.post(f'/api/assisted-allocation/students/{self.student.id}/override/', {'bed_id': self.bed.id}, format='json'),
                             403, 'רק מנהל אזור או מנהל מרכזי יכול לבצע שיבוץ בחריגה')
        boss = self.client_for(self.boss)
        self.assertErrorBody(boss.post(f'/api/assisted-allocation/students/{self.student.id}/override/', {'bed_id': self.bed.id}, format='json'),
                             400, 'יש להזין סיבה לחריגה')
        response = client.post(f'/api/assisted-allocation/students/{self.student.id}/assign/', {'bed_id': self.bed.id}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertKeys(response.data, ['message', 'assignment_id'])
        self.assertEqual(response.data['message'], 'הסטודנט שובץ בהצלחה')
        response = client.post(f'/api/assisted-allocation/students/{self.student.id}/assign/', {'bed_id': self.bed.id}, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertKeys(response.data, ['error'])
        self.assertIn('כבר משובץ', response.data['error'])
