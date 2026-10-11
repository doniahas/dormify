"""Contracts of the summary, analysis, statistics and home-dashboard endpoints."""

from api.models import AllocationRun
from api.serializers import AllocationRunSerializer

from ._support import ContractTestCase, assign, make_full_stack, make_region, make_run, make_student, serializer_keys

SUMMARY_KEYS = [
    'region', 'total_students', 'unassigned_students', 'assigned_students', 'available_beds',
    'priority_students', 'total_capacity', 'occupancy_rate', 'students_by_category',
    'students_by_housing_type', 'inventory_by_type', 'population_summary', 'latest_inbox', 'latest_run',
]
ANALYSIS_KEYS = [
    'region', 'summary', 'students_by_gender', 'students_by_religion', 'students_by_religious',
    'students_by_category', 'students_by_housing', 'students_by_region', 'unassigned_by_region',
    'occupancy_data', 'transfers_by_status', 'transfers_by_type', 'pending_requests_by_type',
    'latest_run', 'latest_batch',
]
ANALYSIS_SUMMARY_KEYS = [
    'total_students', 'assigned_students', 'unassigned_students', 'priority_students', 'total_buildings',
    'active_buildings', 'inactive_buildings', 'total_rooms', 'total_capacity', 'total_beds', 'assigned_beds',
    'occupied_beds', 'available_beds', 'occupancy_rate', 'total_transfers', 'pending_transfers',
    'pending_requests', 'priority_unassigned_students',
]
STATISTICS_KEYS = [
    'total_students', 'assigned_students', 'unassigned_students', 'priority_students', 'total_buildings',
    'active_buildings', 'inactive_buildings', 'total_rooms', 'total_capacity', 'occupied_beds',
    'available_beds', 'occupancy_rate', 'pending_transfers',
]
HOME_KEYS = [
    'user', 'scope', 'metrics', 'process', 'workflow', 'situation_he', 'situation_en',
    'primary_action', 'attention_items', 'recent_activity',
]


class AnalyticsContractTests(ContractTestCase):
    def setUp(self):
        super().setUp()
        self.dorm, self.building, self.apartment, self.room = make_full_stack(self.region)
        assign(make_student(self.dorm, 'AN-1'), self.room)
        make_student(self.dorm, 'AN-2', is_priority=True)
        self.run = make_run(self.region, self.boss, status=AllocationRun.Status.COMPLETED)

    def test_allocation_summary_bodies(self):
        response = self.client_for(self.boss).get('/api/allocation/summary/')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertKeys(response.data, SUMMARY_KEYS)
        self.assertEqual(response.data['region'], {'id': self.region.id, 'name': self.region.name})
        self.assertEqual((response.data['total_students'], response.data['assigned_students'], response.data['unassigned_students'], response.data['priority_students']), (2, 1, 1, 1))
        self.assertKeys(response.data['students_by_category'], ['new', 'continuing', 'transfer', 'leaving'])
        self.assertKeys(response.data['students_by_housing_type'], ['single_male', 'single_female', 'single_mixed', 'couple', 'family', 'unknown'])
        self.assertKeys(response.data['inventory_by_type'], ['single', 'couple', 'family'])
        self.assertKeys(response.data['inventory_by_type']['single'], ['apartments', 'rooms', 'total_beds', 'occupied_beds', 'available_beds'])
        self.assertKeys(response.data['population_summary'], [
            'imported_students', 'excluded_accessibility', 'excluded_leaving', 'excluded_overlap',
            'excluded_total', 'sent_to_solver', 'sent_to_solver_student_ids',
        ])
        self.assertIsNone(response.data['latest_inbox'])
        self.assertKeys(response.data['latest_run'], serializer_keys(AllocationRunSerializer))

        admin = self.client_for(self.admin).get('/api/allocation/summary/')
        self.assertKeys(admin.data, SUMMARY_KEYS)
        self.assertIsNone(admin.data['region'])
        self.assertEqual(admin.data['total_students'], 0)
        self.assertEqual(admin.data['population_summary']['sent_to_solver_student_ids'], [])
        other = make_region('Contract Other Summary')
        self.assertErrorBody(self.client_for(self.boss).get(f'/api/allocation/summary/?region={other.id}'), 403, 'אין הרשאה לאזור זה')

    def test_analysis_bodies(self):
        response = self.client_for(self.boss).get('/api/analysis/')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertKeys(response.data, ANALYSIS_KEYS)
        self.assertEqual(response.data['region'], {'id': self.region.id, 'name': self.region.name})
        self.assertKeys(response.data['summary'], ANALYSIS_SUMMARY_KEYS)
        self.assertKeys(response.data['occupancy_data'][0], [
            'building_id', 'building', 'building_number', 'dorm_type', 'region', 'region_id',
            'rooms_count', 'total_beds', 'assigned', 'available_beds', 'occupancy_rate',
        ])
        self.assertKeys(response.data['latest_run'], serializer_keys(AllocationRunSerializer))
        self.assertIsNone(response.data['latest_batch'])
        admin = self.client_for(self.admin).get('/api/analysis/')
        self.assertIsNone(admin.data['region'])
        self.assertErrorBody(self.client_for(self.admin).get('/api/analysis/?region=nope'), 404, 'אזור לא נמצא')

    def test_statistics_body(self):
        response = self.client_for(self.employee).get('/api/statistics/')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertKeys(response.data, STATISTICS_KEYS)
        self.assertEqual((response.data['total_students'], response.data['occupied_beds'], response.data['available_beds']), (2, 1, 1))
        self.assertKeys(self.client_for(self.admin).get('/api/statistics/').data, STATISTICS_KEYS)

    def test_home_dashboard_bodies(self):
        response = self.client_for(self.boss).get('/api/home/')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertKeys(response.data, HOME_KEYS)
        self.assertKeys(response.data['user'], ['name', 'role', 'role_display', 'region_id', 'region_name'])
        self.assertEqual(response.data['scope'], 'region')
        self.assertKeys(response.data['metrics'], ['assigned_students', 'unassigned_students', 'occupancy_rate', 'available_beds', 'pending_requests'])
        self.assertKeys(response.data['process'], ['latest_batch', 'latest_inbox', 'active_run', 'latest_run', 'has_completed_run'])
        self.assertKeys(response.data['process']['latest_run'], serializer_keys(AllocationRunSerializer))
        self.assertEqual([w['key'] for w in response.data['workflow']], ['upload', 'data_review', 'regional_processing', 'allocation', 'results_review'])
        self.assertKeys(response.data['workflow'][0], ['key', 'label_he', 'label_en', 'status'])
        if response.data['primary_action'] is not None:
            self.assertKeys(response.data['primary_action'], ['key', 'label_he', 'label_en', 'route'])
        for item in response.data['attention_items']:
            self.assertKeys(item, ['id', 'severity', 'icon', 'count', 'title_he', 'title_en', 'description_he', 'description_en', 'route'])
        run_activity = next(a for a in response.data['recent_activity'] if a['type'] == 'allocation')
        self.assertKeys(run_activity, ['id', 'type', 'icon', 'status', 'title_he', 'title_en', 'subtitle_he', 'subtitle_en', 'timestamp', 'route'])

        admin = self.client_for(self.admin).get('/api/home/')
        self.assertEqual(admin.data['scope'], 'system')
        self.assertIsNone(admin.data['user']['region_id'])
