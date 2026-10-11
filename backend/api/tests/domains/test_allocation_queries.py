"""Direct tests for api.domains.allocation.queries and .results."""

from django.test import TestCase

from api.domains.allocation import queries, results
from api.models import AllocationRun, Apartment, Student

from ._fixtures import (
    assign,
    make_boss,
    make_full_stack,
    make_region,
    make_run,
    make_student,
)


class SolverPopulationQueryTests(TestCase):
    def setUp(self):
        self.region = make_region('Pop Query Region')
        self.dorm, _b, _a, self.room = make_full_stack(self.region)
        self.new = make_student(self.dorm, 'NEW-1', category=Student.StudentCategory.NEW)
        self.continuing = make_student(self.dorm, 'CONT-1', category=Student.StudentCategory.CONTINUING)
        self.leaving = make_student(self.dorm, 'LEAVE-1', category=Student.StudentCategory.LEAVING)
        self.accessibility = make_student(self.dorm, 'ACC-1', accessibility_flag=True)
        self.assigned = make_student(self.dorm, 'ASSIGNED-1')
        assign(self.assigned, self.room)

    def test_default_population_excludes_assigned_leaving_and_accessibility(self):
        base, students = queries.solver_students_for_region(self.region)
        self.assertEqual(
            sorted(base.values_list('student_id', flat=True)),
            ['ASSIGNED-1', 'CONT-1', 'NEW-1'],
        )
        self.assertEqual(sorted(students.values_list('student_id', flat=True)), ['CONT-1', 'NEW-1'])

    def test_include_assigned_and_scope_narrowing(self):
        _base, with_assigned = queries.solver_students_for_region(self.region, include_assigned=True)
        self.assertIn('ASSIGNED-1', with_assigned.values_list('student_id', flat=True))

        _base, scoped = queries.solver_students_for_region(self.region, allocation_scope='new_transfer_only')
        self.assertEqual(list(scoped.values_list('student_id', flat=True)), ['NEW-1'])

    def test_unassigned_and_accessibility_queues_are_disjoint_and_ordered(self):
        priority = make_student(self.dorm, 'PRIO-1', is_priority=True)
        unassigned = list(queries.unassigned_students_queryset(self.region))
        self.assertEqual(unassigned[0], priority)
        self.assertEqual({s.student_id for s in unassigned}, {'PRIO-1', 'NEW-1', 'CONT-1'})
        self.assertEqual(
            [s.student_id for s in queries.accessibility_pending_queryset(self.region)],
            ['ACC-1'],
        )

    def test_retry_population_keeps_only_still_unassigned_eligible_students(self):
        ids = [self.new.id, self.assigned.id, self.leaving.id, self.accessibility.id]
        retry = queries.retry_population_queryset(ids)
        self.assertEqual(list(retry.values_list('student_id', flat=True)), ['NEW-1'])


class CurrentRunForRegionTests(TestCase):
    def setUp(self):
        self.region = make_region('Current Run Region')
        self.boss = make_boss(self.region)

    def test_no_runs_means_none(self):
        self.assertIsNone(queries.current_run_for_region(self.region))

    def test_active_run_wins(self):
        make_run(self.region, self.boss, status=AllocationRun.Status.COMPLETED)
        queued = make_run(self.region, self.boss, status=AllocationRun.Status.QUEUED, completed=False)
        self.assertEqual(queries.current_run_for_region(self.region), queued)

    def test_completed_run_only_while_its_assignments_still_exist(self):
        dorm, _b, _a, room = make_full_stack(self.region)
        run = make_run(self.region, self.boss, status=AllocationRun.Status.COMPLETED)
        self.assertIsNone(queries.current_run_for_region(self.region))

        assignment = assign(make_student(dorm, 'CUR-1'), room, run=run)
        self.assertEqual(queries.current_run_for_region(self.region), run)

        room.is_active = False
        room.save()
        self.assertIsNone(queries.current_run_for_region(self.region))
        self.assertTrue(assignment.pk)

    def test_latest_run_lookups(self):
        older = make_run(self.region, self.boss, status=AllocationRun.Status.FAILED, error_message='x')
        newer = make_run(self.region, self.boss, status=AllocationRun.Status.COMPLETED)
        self.assertEqual(queries.latest_run_for_region(self.region), newer)
        self.assertEqual(queries.latest_run_in_statuses(self.region, (AllocationRun.Status.FAILED,)), older)
        self.assertIsNone(queries.latest_run_in_statuses(self.region, queries.ACTIVE_RUN_STATUSES))


class ResultsReadModelTests(TestCase):
    def setUp(self):
        self.region = make_region('Results Region')
        self.boss = make_boss(self.region)
        self.dorm, self.building, self.apartment, self.room = make_full_stack(self.region)
        self.run = make_run(self.region, self.boss, status=AllocationRun.Status.COMPLETED)
        self.assigned = make_student(self.dorm, 'RES-ASSIGNED')
        self.assignment = assign(self.assigned, self.room, run=self.run)
        self.unassigned = make_student(self.dorm, 'RES-UNASSIGNED')
        make_student(self.dorm, 'RES-ACC', accessibility_flag=True)

    def test_assignment_rows_for_run_have_the_table_shape(self):
        rows = results.build_assignment_rows_for_run(self.run)
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row['student_id'], 'RES-ASSIGNED')
        self.assertEqual(row['building'], self.building.number)
        self.assertEqual(row['bed'], self.assignment.bed.label)
        self.assertEqual(row['region_id'], self.region.id)
        self.assertEqual(row['assignment_type'], self.assignment.assignment_type)
        self.assertEqual(
            list(row)[-3:], ['assignment_type', 'assignment_status', 'assigned_at'],
        )

    def test_assignment_rows_for_students_are_scoped_to_the_given_population(self):
        other = make_student(self.dorm, 'RES-OTHER')
        assign(other, self.room)
        rows = results.build_assignment_rows_for_students(self.region, [self.assigned.id])
        self.assertEqual([r['student_id'] for r in rows], ['RES-ASSIGNED'])

    def test_allocation_results_partition_assigned_unassigned_and_free_beds(self):
        payload = results.build_allocation_results(self.region)
        self.assertEqual([r['student_id'] for r in payload['assignments']], ['RES-ASSIGNED'])
        self.assertEqual([r['student_id'] for r in payload['unassigned_students']], ['RES-UNASSIGNED'])
        self.assertEqual(len(payload['available_beds']), 1)
        self.assertEqual(payload['available_beds'][0]['room_id'], self.room.id)
        self.assertFalse(payload['available_beds'][0]['is_reserved'])
        self.assertEqual(len(payload['unassigned_analysis']), 1)
        self.assertEqual(payload['unassigned_analysis'][0]['student_count'], 1)

    def test_unassigned_analysis_groups_and_sorts_by_group_size(self):
        make_student(self.dorm, 'RES-F1', gender=Student.Gender.FEMALE, housing_type=Student.HousingType.SINGLE_FEMALE)
        make_student(self.dorm, 'RES-F2', gender=Student.Gender.FEMALE, housing_type=Student.HousingType.SINGLE_FEMALE)
        no_dorm = Student.objects.create(
            student_id='RES-NODORM', first_name='N', last_name='D',
            gender=Student.Gender.MALE, housing_type=Student.HousingType.SINGLE_MALE,
        )
        students = list(queries.unassigned_students_queryset(self.region)) + [no_dorm]

        analysis = results._build_unassigned_analysis(students)

        self.assertEqual([row['student_count'] for row in analysis], [2, 1, 1])
        self.assertEqual(analysis[0]['gender'], Student.Gender.FEMALE)
        self.assertIn('NO_ACCEPTED_DORM_TYPE', {row['reason_code'] for row in analysis})
        self.assertEqual(results._build_unassigned_analysis([]), [])

    def test_inventory_breakdown_rows_add_display_labels(self):
        rows = results.inventory_breakdown_rows([
            {'category': 'male', 'apartment_type': 'single', 'free_beds': 2},
            {'category': '', 'apartment_type': None, 'free_beds': 0},
        ])
        self.assertEqual(rows[0]['category_display'], str(Apartment.Category.MALE.label))
        self.assertEqual(rows[0]['apartment_type_display'], str(Apartment.ApartmentType.SINGLE.label))
        self.assertEqual(rows[1]['category_display'], '')
        self.assertEqual(rows[1]['apartment_type_display'], '')
