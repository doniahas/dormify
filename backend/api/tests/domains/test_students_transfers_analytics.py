"""Direct tests for the students, transfers, matching-feasibility, placement and analytics domain additions."""

from django.test import TestCase
from django.utils import timezone

from api.domains.analytics.queries import build_allocation_summary_read_model
from api.domains.matching import feasibility
from api.domains.placement.services import unassign_student
from api.domains.students import queries as student_queries
from api.domains.transfers.queries import student_request_base_queryset, top10_bed_assignment_history_qs
from api.models import AllocationRun, BedAssignment, ImportBatch, RegionInbox, Student, StudentRequest

from ._fixtures import (
    assign,
    make_boss,
    make_full_stack,
    make_region,
    make_run,
    make_student,
)


class StudentQueriesTests(TestCase):
    def setUp(self):
        self.region = make_region('Students Region')
        self.boss = make_boss(self.region)
        self.dorm, self.building, self.apartment, self.room = make_full_stack(self.region)
        self.assigned = make_student(self.dorm, 'ST-ASSIGNED', category=Student.StudentCategory.CONTINUING)
        assign(self.assigned, self.room)
        self.unassigned = make_student(self.dorm, 'ST-UNASSIGNED', is_priority=True, roommate_request_1='Pal')
        self.leaving = make_student(self.dorm, 'ST-LEAVING', category=Student.StudentCategory.LEAVING)

    def test_unassigned_ids_from_latest_completed_run(self):
        self.assertEqual(student_queries.unassigned_student_ids_from_latest_completed_run(self.region.id), [])
        make_run(self.region, self.boss, diagnostics={'population_summary': {
            'sent_to_solver_student_ids': [self.assigned.id, self.unassigned.id, self.leaving.id],
        }})
        self.assertEqual(
            student_queries.unassigned_student_ids_from_latest_completed_run(self.region.id),
            [self.unassigned.id],
        )
        make_run(self.region, self.boss, diagnostics={})
        self.assertEqual(student_queries.unassigned_student_ids_from_latest_completed_run(self.region.id), [])

    def test_filters(self):
        base = Student.objects.all()

        def ids(**overrides):
            filters = student_queries.StudentFilters(**overrides)
            return sorted(student_queries.filter_students(base, filters).values_list('student_id', flat=True))

        self.assertEqual(ids(), ['ST-ASSIGNED', 'ST-LEAVING', 'ST-UNASSIGNED'])
        self.assertEqual(ids(status='assigned'), ['ST-ASSIGNED'])
        self.assertEqual(ids(status='priority'), ['ST-UNASSIGNED'])
        self.assertEqual(ids(status='unassigned', unassigned_student_ids=[self.unassigned.id]), ['ST-UNASSIGNED'])
        self.assertEqual(ids(status='unassigned'), [])
        self.assertEqual(ids(has_roommate_request='yes'), ['ST-UNASSIGNED'])
        self.assertEqual(ids(has_roommate_request='no'), ['ST-ASSIGNED', 'ST-LEAVING'])
        self.assertEqual(ids(category=Student.StudentCategory.LEAVING), ['ST-LEAVING'])
        self.assertEqual(ids(category='all'), ['ST-ASSIGNED', 'ST-LEAVING', 'ST-UNASSIGNED'])
        self.assertEqual(ids(search='leav'), ['ST-LEAVING'])
        self.assertEqual(ids(building_ids=[self.building.id]), ['ST-ASSIGNED'])
        self.assertEqual(ids(room_ids=[self.room.id]), ['ST-ASSIGNED'])
        self.assertEqual(ids(region_ids=['nope']), [])
        self.assertEqual(ids(genders=['male'], religious='all', placement_sector='all'), ['ST-ASSIGNED', 'ST-LEAVING', 'ST-UNASSIGNED'])

    def test_filter_options_scoping(self):
        other = make_region('Students Other')
        make_full_stack(other)

        everything = student_queries.build_student_filter_options(None)
        self.assertEqual(len(everything['regions']), 2)
        self.assertEqual(len(everything['buildings']), 2)
        self.assertEqual(len(everything['housing_types']), 5)
        self.assertEqual({r['id'] for r in everything['religions']}, set(Student.Religion.values))

        scoped = student_queries.build_student_filter_options(self.region.id)
        self.assertEqual(scoped['regions'], [{'id': self.region.id, 'name': self.region.name}])
        self.assertEqual(scoped['dorm_types'], [{
            'id': self.dorm.id, 'name': self.dorm.name, 'region_id': self.region.id, 'region_name': self.region.name,
        }])
        self.assertEqual(scoped['rooms'], [{'id': self.room.id, 'name': self.room.name}])


class TransfersQueriesAndFeasibilityTests(TestCase):
    def setUp(self):
        self.region = make_region('Transfers Region')
        self.boss = make_boss(self.region)
        self.dorm, _b, _a, self.room = make_full_stack(self.region)
        self.student = make_student(self.dorm, 'TR-1')

    def test_history_prefetch_is_bounded_to_ten_rows_per_student(self):
        bed = self.room.beds.first()
        for _ in range(12):
            BedAssignment.objects.create(
                student=self.student, bed=bed, status=BedAssignment.Status.ENDED,
                ended_at=timezone.now(), assignment_type=BedAssignment.AssignmentType.INITIAL,
            )
        self.assertEqual(top10_bed_assignment_history_qs().filter(student=self.student).count(), 10)

    def test_base_queryset_carries_the_prefetched_slices(self):
        assign(self.student, self.room)
        request = StudentRequest.objects.create(
            student=self.student, request_type=StudentRequest.RequestType.ROOM,
            status=StudentRequest.Status.PENDING, requested_by=self.boss,
        )
        row = student_request_base_queryset().get(pk=request.pk)
        self.assertEqual(len(row.student.prefetched_current_assignment_list), 1)
        self.assertEqual(len(row.student.prefetched_placement_history_all), 1)

    def test_student_assignment_blocker(self):
        self.assertIsNone(feasibility.student_assignment_blocker(self.student))
        leaving = make_student(self.dorm, 'TR-LEAVING', category=Student.StudentCategory.LEAVING)
        self.assertEqual(feasibility.student_assignment_blocker(leaving)[0], 'category')
        no_housing = make_student(self.dorm, 'TR-NOHOUSING', housing_type='')
        self.assertEqual(feasibility.student_assignment_blocker(no_housing)[0], 'housing_type')
        no_region = Student.objects.create(
            student_id='TR-NOREGION', first_name='N', last_name='R',
            gender=Student.Gender.MALE, housing_type=Student.HousingType.SINGLE_MALE,
        )
        self.assertEqual(feasibility.student_assignment_blocker(no_region)[0], 'region')

    def test_empty_payload_and_reason(self):
        payload = feasibility.empty_match_payload(10, 20)
        self.assertEqual((payload['limit'], payload['offset'], payload['total_valid_beds']), (10, 20, 0))
        self.assertEqual(feasibility.match_infeasibility_reason({'total_valid_beds': 1}, 'x'), '')
        self.assertEqual(feasibility.match_infeasibility_reason({'total_valid_beds': 0}, 'none'), 'none')
        with_integrity = feasibility.match_infeasibility_reason(
            {'total_valid_beds': 0, 'data_integrity': {'missing_bed_records': True}}, 'none',
        )
        self.assertTrue(with_integrity.startswith('none '))
        self.assertIn('materialize_beds', with_integrity)


class PlacementUnassignTests(TestCase):
    def test_unassign_ends_the_assignment_and_clears_the_room(self):
        region = make_region('Unassign Region')
        dorm, _b, _a, room = make_full_stack(region)
        student = make_student(dorm, 'UN-1')
        assignment = assign(student, room)

        unassign_student(student, assignment)

        assignment.refresh_from_db()
        student.refresh_from_db()
        self.assertEqual(assignment.status, BedAssignment.Status.ENDED)
        self.assertIsNotNone(assignment.ended_at)
        self.assertIsNone(student.assigned_room_id)


class AllocationSummaryReadModelTests(TestCase):
    def test_summary_counts_and_latest_objects(self):
        region = make_region('Summary Region')
        boss = make_boss(region)
        dorm, _b, _a, room = make_full_stack(region)
        assigned = make_student(dorm, 'SUM-ASSIGNED')
        assign(assigned, room)
        make_student(dorm, 'SUM-UNASSIGNED', is_priority=True)
        make_student(dorm, 'SUM-LEAVING', category=Student.StudentCategory.LEAVING)
        make_student(dorm, 'SUM-ACC', accessibility_flag=True)
        make_student(dorm, 'SUM-COUPLE', housing_type=Student.HousingType.COUPLE, gender=None)
        run = make_run(region, boss, status=AllocationRun.Status.COMPLETED)
        batch = ImportBatch.objects.create(uploaded_by=boss, status=ImportBatch.Status.COMPLETED)
        inbox = RegionInbox.objects.create(
            region=region, batch=batch, students_count=3, status=RegionInbox.Status.PENDING,
        )

        summary = build_allocation_summary_read_model(region)

        self.assertEqual(summary['total_students'], 3)
        self.assertEqual(summary['assigned_students'], 1)
        self.assertEqual(summary['unassigned_students'], 2)
        self.assertEqual(summary['priority_students'], 1)
        self.assertEqual(summary['students_by_category'], {'new': 4, 'continuing': 0, 'transfer': 0, 'leaving': 1})
        self.assertEqual(summary['students_by_housing_type']['single_male'], 1)
        self.assertEqual(summary['students_by_housing_type']['couple'], 1)
        self.assertEqual(summary['total_capacity'], 2)
        self.assertEqual(summary['available_beds'], 1)
        self.assertEqual(summary['occupancy_rate'], 50.0)
        self.assertEqual(summary['inventory_by_type']['single']['occupied_beds'], 1)
        self.assertEqual(summary['population_summary']['imported_students'], 5)
        self.assertEqual(summary['latest_inbox'], inbox)
        self.assertEqual(summary['latest_run'], run)
