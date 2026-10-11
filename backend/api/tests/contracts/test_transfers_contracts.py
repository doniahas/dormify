"""Contracts of the student-request workflow endpoints (/api/requests/)."""

from api.models import StudentRequest
from api.serializers import StudentRequestSerializer

from ._support import ContractTestCase, assign, make_full_stack, make_region, make_student, serializer_keys

REQUEST_KEYS = serializer_keys(StudentRequestSerializer)
PAGE_KEYS = ['count', 'next', 'previous', 'results']


class StudentRequestContractTests(ContractTestCase):
    def setUp(self):
        super().setUp()
        self.dorm, self.building, self.apartment, self.room = make_full_stack(self.region)
        self.student = make_student(self.dorm, 'RQ-1')
        assign(self.student, self.room)

    def _create(self, client, **overrides):
        payload = {'request_type': 'room', 'student': self.student.id, 'reason': 'noise'}
        payload.update(overrides)
        return client.post('/api/requests/', payload, format='json')

    def test_create_and_list_bodies(self):
        employee = self.client_for(self.employee)
        response = self._create(employee)
        self.assertEqual(response.status_code, 201, response.data)
        self.assertKeys(response.data, REQUEST_KEYS)
        self.assertEqual(response.data['status'], 'pending')
        self.assertEqual(response.data['transfer_scope'], 'same_region')
        self.assertEqual(response.data['source_region'], self.region.id)
        self.assertTrue(response.data['request_number'].startswith('REQ-'))
        self.assertEqual(response.data['current_building'], self.building.number)
        self.assertEqual(len(response.data['placement_history']), 1)
        self.assertKeys(response.data['placement_history'][0], ['region', 'building', 'apartment', 'room', 'status', 'assigned_at', 'ended_at'])

        response = employee.get('/api/requests/')
        self.assertKeys(response.data, PAGE_KEYS)
        self.assertEqual(response.data['count'], 1)
        self.assertKeys(response.data['results'][0], REQUEST_KEYS)
        self.assertEqual(employee.get('/api/requests/?status=approved').data['count'], 0)
        self.assertEqual(employee.get(f'/api/requests/?student={self.student.id}').data['count'], 1)

    def test_create_validation_bodies(self):
        employee = self.client_for(self.employee)
        response = self._create(employee, student=None)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data, {'student': ['This request type requires selecting an existing student.']})
        response = self._create(employee, transfer_scope='cross_region')
        self.assertDetailBody(response, 403)
        response = self._create(self.client_for(self.admin), transfer_scope='cross_region')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data, {'destination_regions': ['יש לבחור לפחות אזור יעד אחד עבור מעבר לאזור אחר.']})

    def test_review_action_bodies(self):
        employee = self.client_for(self.employee)
        boss = self.client_for(self.boss)
        request_id = self._create(employee).data['id']
        self.assertErrorBody(employee.put(f'/api/requests/{request_id}/approve/', {}, format='json'), 403, 'רק מנהל יכול לאשר בקשות')
        self.assertErrorBody(employee.put(f'/api/requests/{request_id}/reject/', {}, format='json'), 403, 'רק מנהל יכול לדחות בקשות')
        self.assertErrorBody(boss.put(f'/api/requests/{request_id}/approve/', {'target_room': 999999}, format='json'), 404, 'החדר שנבחר לא נמצא')
        self.assertErrorBody(boss.put(f'/api/requests/{request_id}/approve/', {}, format='json'), 400, 'יש לבחור חדר יעד לפני האישור')

        response = boss.put(f'/api/requests/{request_id}/reject/', {'reason': 'no'}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertKeys(response.data, ['message', 'request'])
        self.assertEqual(response.data['message'], 'הבקשה נדחתה')
        self.assertKeys(response.data['request'], REQUEST_KEYS)
        self.assertEqual((response.data['request']['status'], response.data['request']['rejection_reason']), ('rejected', 'no'))
        self.assertErrorBody(boss.put(f'/api/requests/{request_id}/reject/', {}, format='json'), 400, 'הבקשה כבר טופלה')
        self.assertErrorBody(boss.put(f'/api/requests/{request_id}/cancel/', {}, format='json'), 400, 'ניתן לבטל רק בקשה הממתינה לאישור')

    def test_cancel_and_delete_bodies(self):
        employee = self.client_for(self.employee)
        request_id = self._create(employee).data['id']
        response = employee.put(f'/api/requests/{request_id}/cancel/', {}, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertKeys(response.data, ['message', 'request'])
        self.assertEqual((response.data['message'], response.data['request']['status']), ('בקשת ההעברה בוטלה', 'cancelled'))
        self.assertDetailBody(employee.delete(f'/api/requests/{request_id}/'), 405)
        # Generic PUT/PATCH stay routed; a PUT without the required fields is
        # a field-keyed serializer rejection.
        response = employee.put(f'/api/requests/{request_id}/', {'reason': 'x'}, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertKeys(response.data, ['request_type'])

    def test_feasibility_and_target_regions_bodies(self):
        employee = self.client_for(self.employee)
        request_id = self._create(employee).data['id']
        response = employee.get(f'/api/requests/{request_id}/feasibility/?limit=5')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['limit'], 5)
        self.assertEqual(response.data['transfer_scope'], 'same_region')
        self.assertEqual(response.data['search_regions'], [{'id': self.region.id, 'name': self.region.name}])
        self.assertIn('buildings', response.data)
        other = make_region('Contract Target Region')
        response = employee.get('/api/requests/transfer-target-regions/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(sorted(r['id'] for r in response.data), sorted([self.region.id, other.id]))
        self.assertKeys(response.data[0], ['id', 'name'])

    def test_region_transfer_visibility_contract(self):
        other = make_region('Contract Destination')
        request = StudentRequest.objects.create(
            student=self.student, request_type=StudentRequest.RequestType.REGION_TRANSFER,
            status=StudentRequest.Status.PENDING, requested_by=self.employee, target_region=other,
        )
        row = self.client_for(self.employee).get('/api/requests/').data['results'][0]
        self.assertEqual((row['id'], row['target_region'], row['destination_regions']), (request.id, other.id, []))
        self.assertErrorBody(self.client_for(self.boss).put(f'/api/requests/{request.id}/approve/', {}, format='json'), 403, 'אין הרשאה לאשר בקשה זו')
