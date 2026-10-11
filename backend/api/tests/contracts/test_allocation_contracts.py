"""Contracts of the allocation run lifecycle and results endpoints."""

from unittest.mock import patch

from api.domains.allocation.gateway import MAX_USER_SOLVER_TIME_SECONDS
from api.models import AllocationRun, BedAssignment, Student
from api.serializers import AllocationRunSerializer

from ._support import (
    ContractTestCase,
    assign,
    make_boss,
    make_full_stack,
    make_region,
    make_run,
    make_student,
    serializer_keys,
)

RUN_KEYS = serializer_keys(AllocationRunSerializer)

RUN_ASSIGNMENT_ROW_KEYS = [
    'student_id', 'student_name', 'full_name', 'first_name', 'last_name',
    'gender', 'requested_religion', 'religion', 'religious', 'placement_sector', 'sector',
    'building', 'building_number', 'apartment', 'apartment_number', 'room', 'room_name',
    'bed', 'bed_label', 'dorm_type', 'region', 'region_id',
    'assignment_type', 'assignment_status', 'assigned_at',
]

RESULTS_ASSIGNMENT_ROW_KEYS = [
    'student_id', 'student_name', 'full_name', 'first_name', 'last_name',
    'gender', 'housing_type', 'housing_type_display',
    'requested_religion', 'religion', 'religion_display',
    'religious', 'placement_sector', 'sector', 'is_priority',
    'building', 'building_number', 'apartment', 'apartment_number',
    'apartment_type', 'apartment_type_display', 'apartment_category', 'apartment_category_display',
    'room', 'room_name', 'bed', 'bed_label',
    'dorm_type', 'dorm_type_id', 'region', 'region_id',
    'assignment_type', 'assignment_status', 'assigned_at',
]

UNASSIGNED_ROW_KEYS = [
    'student_db_id', 'student_id', 'business_partner_id',
    'student_name', 'full_name', 'first_name', 'last_name',
    'gender', 'gender_display', 'housing_type', 'housing_type_display',
    'requested_religion', 'religion', 'religion_display',
    'religious', 'placement_sector', 'placement_sector_display',
    'is_priority', 'priority_reason', 'category', 'category_display',
    'accepted_dorm_type_id', 'accepted_dorm_type', 'region_id', 'region',
    'special_statuses', 'unassigned_reason',
]

AVAILABLE_BED_ROW_KEYS = [
    'bed_id', 'bed', 'bed_label', 'room_id', 'room', 'room_name', 'room_capacity',
    'apartment_id', 'apartment', 'apartment_number', 'apartment_type', 'apartment_type_display',
    'apartment_category', 'apartment_category_display', 'is_reserved',
    'building_id', 'building', 'building_number', 'building_gender_restriction',
    'dorm_type_id', 'dorm_type', 'region_id', 'region',
]

ANALYSIS_GROUP_KEYS = [
    'accepted_dorm_type_id', 'accepted_dorm_type_code', 'accepted_dorm_type_name',
    'gender', 'housing_type', 'housing_type_display', 'student_count',
    'physically_free_beds_in_accepted_dorm', 'compatible_free_beds', 'reason_code',
    'inventory_breakdown',
]

POPULATION_KEYS = [
    'imported_students', 'excluded_accessibility', 'excluded_leaving', 'excluded_overlap',
    'excluded_total', 'sent_to_solver', 'sent_to_solver_student_ids', 'assigned', 'unassigned',
]

ALREADY_RUNNING = 'כבר רץ שיבוץ עבור אזור זה. נא להמתין לסיום ההרצה הקיימת.'


class StartRunContractTests(ContractTestCase):
    def setUp(self):
        super().setUp()
        self.dorm, _b, _a, self.room = make_full_stack(self.region)

    def _start(self, user, payload):
        # Since R8 the request only queues a durable run for the allocation
        # worker; it must start no thread of its own.
        with patch('threading.Thread') as thread:
            response = self.client_for(user).post('/api/allocation/start/', payload, format='json')
        return response, thread

    def test_202_body_and_run_shape(self):
        response, thread = self._start(self.boss, {'region': self.region.id, 'max_solver_seconds': 30})
        self.assertEqual(response.status_code, 202, response.data)
        self.assertKeys(response.data, ['success', 'message', 'run_id', 'run'])
        self.assertIs(response.data['success'], True)
        self.assertKeys(response.data['run'], RUN_KEYS)
        self.assertEqual(response.data['run']['status'], 'queued')
        self.assertEqual(response.data['run']['max_search_seconds'], 30)
        self.assertEqual(response.data['run_id'], response.data['run']['id'])
        thread.assert_not_called()
        run = AllocationRun.objects.get(pk=response.data['run_id'])
        self.assertEqual(run.job_parameters['max_seconds'], 30.0)
        self.assertEqual(run.claimed_by, '')

    def test_request_validation_bodies(self):
        self.assertErrorBody(self._start(self.employee, {'region': self.region.id})[0], 403,
                             'רק מנהל אזור או מנהל מרכזי יכולים להריץ שיבוץ')
        self.assertErrorBody(self._start(self.admin, {})[0], 400, 'נדרש לבחור אזור')
        self.assertErrorBody(self._start(self.admin, {'region': 'nope'})[0], 404, 'אזור לא נמצא')
        other = make_region('Contract Other Start')
        self.assertErrorBody(self._start(self.boss, {'region': other.id})[0], 403,
                             'אין הרשאה להריץ שיבוץ עבור אזור זה')
        self.assertErrorBody(self._start(self.boss, {'region': self.region.id, 'max_solver_seconds': 'abc'})[0],
                             400, 'זמן חיפוש מרבי חייב להיות מספר')
        response, _ = self._start(self.boss, {'region': self.region.id, 'max_solver_seconds': MAX_USER_SOLVER_TIME_SECONDS + 1})
        self.assertEqual(response.status_code, 400)
        self.assertKeys(response.data, ['error'])
        self.assertIn('זמן חיפוש מרבי חייב להיות בין', response.data['error'])

    def test_409_when_a_run_is_live(self):
        live = make_run(self.region, self.boss, status=AllocationRun.Status.QUEUED, completed=False)
        response, thread = self._start(self.boss, {'region': self.region.id})
        self.assertFailureBody(
            response, 409, ALREADY_RUNNING,
            error_code='ALLOCATION_ALREADY_RUNNING', region=self.region.id, run_id=live.id,
            run=AllocationRunSerializer(live).data,
        )
        thread.assert_not_called()
        self.assertEqual(AllocationRun.objects.count(), 1)

    def test_sync_run_409_has_no_run_id_key(self):
        live = make_run(self.region, self.boss, status=AllocationRun.Status.RUNNING, completed=False)
        response = self.client_for(self.boss).post('/api/allocation/run/', {'region': self.region.id}, format='json')
        self.assertFailureBody(
            response, 409, ALREADY_RUNNING,
            error_code='ALLOCATION_ALREADY_RUNNING', region=self.region.id,
            run=AllocationRunSerializer(live).data,
        )

    def test_sync_run_no_students_body(self):
        response = self.client_for(self.boss).post('/api/allocation/run/', {'region': self.region.id}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertKeys(response.data, ['success', 'message', 'result'])
        self.assertKeys(response.data['result'], [
            'students_total_in_region', 'students_available_for_allocation', 'students_processed',
            'successful_assignments', 'roommate_matches', 'mutual_roommate_matches',
            'one_sided_roommate_matches', 'conflicts', 'solver_status', 'objective_value', 'wall_time',
            'warnings', 'students_with_no_feasible_beds', 'anier_building_179_diagnostics',
            'population_summary', 'assignments', 'run',
        ])
        self.assertEqual(response.data['result']['solver_status'], 'NO_STUDENTS')
        self.assertKeys(response.data['result']['population_summary'], POPULATION_KEYS)
        self.assertKeys(response.data['result']['run'], RUN_KEYS)
        self.assertEqual(response.data['result']['run']['status'], 'completed')


class RunLifecycleContractTests(ContractTestCase):
    def setUp(self):
        super().setUp()
        self.dorm, _b, _a, self.room = make_full_stack(self.region)

    def test_run_detail_body_with_assignment_rows(self):
        run = make_run(self.region, self.boss, status=AllocationRun.Status.COMPLETED,
                       diagnostics={'warnings': ['w'], 'solver_status': 'OPTIMAL', 'population_summary': {'sent_to_solver': 1}})
        assign(make_student(self.dorm, 'RD-1'), self.room, run=run)
        response = self.client_for(self.boss).get(f'/api/allocation/runs/{run.id}/')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertKeys(response.data, [
            'run', 'assignments', 'successful_assignments', 'roommate_matches', 'conflicts', 'warnings',
            'anier_building_179_diagnostics', 'population_summary', 'solver_status', 'optimality_proven',
            'stopped_early_by_user',
        ])
        self.assertKeys(response.data['run'], RUN_KEYS)
        self.assertKeys(response.data['assignments'][0], RUN_ASSIGNMENT_ROW_KEYS)
        self.assertEqual(response.data['warnings'], ['w'])
        self.assertIs(response.data['optimality_proven'], False)
        self.assertIs(response.data['stopped_early_by_user'], False)
        self.assertIsInstance(response.data['anier_building_179_diagnostics'], dict)

    def test_run_detail_not_found_and_foreign_region(self):
        self.assertErrorBody(self.client_for(self.boss).get('/api/allocation/runs/999999/'), 404, 'הרצה לא נמצאה')
        other = make_region('Contract Other Detail')
        run = make_run(other, make_boss(other, email='ob@contract.test'))
        self.assertErrorBody(self.client_for(self.boss).get(f'/api/allocation/runs/{run.id}/'), 403, 'אין גישה להרצה זו')
        self.assertErrorBody(self.client_for(self.boss).get(f'/api/allocation/runs/{run.id}/preview/'), 403, 'אין גישה להרצה זו')

    def test_preview_bodies(self):
        run = make_run(self.region, self.boss, status=AllocationRun.Status.RUNNING, completed=False)
        response = self.client_for(self.employee).get(f'/api/allocation/runs/{run.id}/preview/')
        self.assertEqual(response.data, {'available': False, 'snapshot': None})
        AllocationRun.objects.filter(pk=run.pk).update(live_snapshot={'sequence': 2, 'assignments': []})
        response = self.client_for(self.employee).get(f'/api/allocation/runs/{run.id}/preview/')
        self.assertEqual(response.data, {'available': True, 'snapshot': {'sequence': 2, 'assignments': []}})

    def test_stop_and_stop_and_save_outcome_bodies(self):
        client = self.client_for(self.boss)
        self.assertErrorBody(self.client_for(self.employee).post('/api/allocation/runs/1/stop/'), 403, 'אין הרשאה לעצור שיבוץ')
        self.assertErrorBody(client.post('/api/allocation/runs/999999/stop/'), 404, 'הרצה לא נמצאה')

        done = make_run(self.region, self.boss, status=AllocationRun.Status.COMPLETED)
        self.assertErrorBody(client.post(f'/api/allocation/runs/{done.id}/stop/'), 409, 'הרצה זו כבר הסתיימה', status='completed')

        live = make_run(self.region, self.boss, status=AllocationRun.Status.RUNNING, completed=False)
        with patch('allocation.live_registry.request_stop_search'):
            response = client.post(f'/api/allocation/runs/{live.id}/stop-and-save/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, {
            'message': 'בקשת עצירה עם שמירת תוצאה נשלחה. הפתרון הטוב ביותר שנמצא יישמר.', 'run_id': live.id,
        })
        response = client.post(f'/api/allocation/runs/{live.id}/stop-and-save/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, {'message': 'בקשת עצירה ושמירה כבר נשלחה', 'run_id': live.id, 'status': 'stop_and_save_requested'})
        self.assertErrorBody(client.post(f'/api/allocation/runs/{live.id}/stop/'), 409,
                             'כבר התבקשה עצירה עם שמירת תוצאה עבור הרצה זו', run_id=live.id, status='stop_and_save_requested')

        other = make_region('Contract Other Stop')
        foreign = make_run(other, make_boss(other, email='os@contract.test'), status=AllocationRun.Status.RUNNING, completed=False)
        self.assertErrorBody(client.post(f'/api/allocation/runs/{foreign.id}/stop/'), 403, 'אין הרשאה לעצור הרצה זו')

    def test_delete_results_bodies(self):
        client = self.client_for(self.boss)
        self.assertErrorBody(self.client_for(self.employee).delete('/api/allocation/runs/1/delete/'), 403, 'אין הרשאה למחוק תוצאות שיבוץ')
        approved = make_run(self.region, self.boss, status=AllocationRun.Status.APPROVED)
        self.assertErrorBody(client.delete(f'/api/allocation/runs/{approved.id}/delete/'), 409, 'לא ניתן למחוק הקצאה שאושרה סופית')
        running = make_run(self.region, self.boss, status=AllocationRun.Status.RUNNING, completed=False)
        self.assertErrorBody(client.delete(f'/api/allocation/runs/{running.id}/delete/'), 409,
                             'לא ניתן למחוק הרצה עם סטטוס: running', status='running')
        done = make_run(self.region, self.boss, status=AllocationRun.Status.COMPLETED)
        assign(make_student(self.dorm, 'DEL-1'), self.room, run=done)
        with patch('django.db.close_old_connections'):
            response = client.delete(f'/api/allocation/runs/{done.id}/delete/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, {'message': 'תוצאות השיבוץ נמחקו בהצלחה', 'run_id': done.id, 'deleted_assignments': 1})

    def test_retry_unassigned_precondition_bodies(self):
        client = self.client_for(self.boss)
        self.assertErrorBody(client.post('/api/allocation/runs/999999/retry-unassigned/'), 404, 'הרצה לא נמצאה')
        running = make_run(self.region, self.boss, status=AllocationRun.Status.RUNNING, completed=False)
        self.assertFailureBody(client.post(f'/api/allocation/runs/{running.id}/retry-unassigned/'), 400,
                               'ניתן לנסות שוב רק הרצה שהושלמה', error_code='RUN_NOT_COMPLETED')
        legacy = make_run(self.region, self.boss, status=AllocationRun.Status.COMPLETED, diagnostics={})
        response = client.post(f'/api/allocation/runs/{legacy.id}/retry-unassigned/')
        self.assertEqual(response.status_code, 400)
        self.assertKeys(response.data, ['success', 'error', 'error_code'])
        self.assertEqual(response.data['error_code'], 'MISSING_ORIGINAL_POPULATION')
        placed = make_student(self.dorm, 'RT-1')
        done = make_run(self.region, self.boss, status=AllocationRun.Status.COMPLETED,
                        diagnostics={'population_summary': {'sent_to_solver_student_ids': [placed.id]}})
        assign(placed, self.room, run=done)
        response = client.post(f'/api/allocation/runs/{done.id}/retry-unassigned/')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data, {
            'success': True,
            'message': 'כל הסטודנטים מהרצה זו כבר משובצים — אין מה לנסות שוב',
            'result': {
                'retry_of_run_id': done.id, 'retried_student_count': 0,
                'successful_assignments': 0, 'conflicts': 0, 'assignments': [],
            },
        })

    def test_active_run_and_history_bodies(self):
        client = self.client_for(self.boss)
        self.assertEqual(client.get('/api/allocation/runs/active/').data, {'run': None})
        self.assertEqual(self.client_for(self.admin).get('/api/allocation/runs/active/').data, {'run': None})
        live = make_run(self.region, self.boss, status=AllocationRun.Status.QUEUED, completed=False)
        response = client.get('/api/allocation/runs/active/')
        self.assertKeys(response.data, ['run'])
        self.assertKeys(response.data['run'], RUN_KEYS)
        self.assertEqual(response.data['run']['id'], live.id)
        other = make_region('Contract Other Active')
        self.assertErrorBody(client.get(f'/api/allocation/runs/active/?region={other.id}'), 403, 'אין הרשאה לאזור זה')
        response = client.get('/api/allocation/history/')
        self.assertKeys(response.data, ['runs'])
        self.assertKeys(response.data['runs'][0], RUN_KEYS)


class AllocationResultsContractTests(ContractTestCase):
    def setUp(self):
        super().setUp()
        self.dorm, self.building, _a, self.room = make_full_stack(self.region)
        assign(make_student(self.dorm, 'RES-A'), self.room)
        make_student(self.dorm, 'RES-U')

    def test_results_body_and_row_shapes(self):
        response = self.client_for(self.boss).get('/api/allocation/results/')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertKeys(response.data, ['counts', 'count', 'assignments', 'unassigned_students', 'available_beds', 'unassigned_analysis'])
        self.assertEqual(response.data['counts'], {'assigned': 1, 'unassigned': 1, 'available_beds': 1})
        self.assertEqual(response.data['count'], 1)
        self.assertKeys(response.data['assignments'][0], RESULTS_ASSIGNMENT_ROW_KEYS)
        self.assertKeys(response.data['unassigned_students'][0], UNASSIGNED_ROW_KEYS)
        self.assertKeys(response.data['available_beds'][0], AVAILABLE_BED_ROW_KEYS)
        self.assertKeys(response.data['unassigned_analysis'][0], ANALYSIS_GROUP_KEYS)
        breakdown = response.data['unassigned_analysis'][0]['inventory_breakdown']
        self.assertIsInstance(breakdown, list)
        if breakdown:
            self.assertKeys(breakdown[0], ['category', 'category_display', 'apartment_type', 'apartment_type_display', 'free_beds'])
        self.assertEqual(response.data['available_beds'][0]['region_id'], self.region.id)
        self.assertIs(response.data['available_beds'][0]['is_reserved'], False)
        self.assertEqual(response.data['unassigned_students'][0]['special_statuses'], [])

    def test_results_region_scoping_bodies(self):
        other = make_region('Contract Other Results')
        self.assertErrorBody(self.client_for(self.boss).get(f'/api/allocation/results/?region={other.id}'), 403, 'אין הרשאה לאזור זה')
        self.assertErrorBody(self.client_for(self.admin).get('/api/allocation/results/?region=nope'), 404, 'אזור לא נמצא')
        self.assertEqual(self.client_for(self.admin).get('/api/allocation/results/').data['counts']['assigned'], 1)

    def test_assignment_rows_are_active_assignments_only(self):
        BedAssignment.objects.update(status=BedAssignment.Status.ENDED, ended_at='2026-01-01T00:00:00Z')
        Student.objects.update(assigned_room=None)
        response = self.client_for(self.boss).get('/api/allocation/results/')
        self.assertEqual(response.data['counts'], {'assigned': 0, 'unassigned': 2, 'available_beds': 2})
