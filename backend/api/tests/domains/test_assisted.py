"""Direct tests for api.domains.assisted (queue, detail, recommendations, placement services)."""

from django.test import TestCase

from api.domains.assisted import queries, services
from api.models import AssistedAllocationAudit, BedAssignment, Student, StudentRequest

from ._fixtures import (
    assign,
    make_boss,
    make_central_admin,
    make_full_stack,
    make_region,
    make_student,
)


class AssistedFixtures(TestCase):
    def setUp(self):
        self.region = make_region('Assisted Region')
        self.boss = make_boss(self.region)
        self.dorm, self.building, self.apartment, self.room = make_full_stack(self.region)
        self.unassigned = make_student(self.dorm, 'AS-UNASSIGNED')
        self.accessibility = make_student(self.dorm, 'AS-ACC', accessibility_flag=True)
        self.transferring = make_student(self.dorm, 'AS-TRANSFER')
        self.target_region = make_region('Assisted Target')
        self.transfer_request = StudentRequest.objects.create(
            student=self.transferring, request_type=StudentRequest.RequestType.REGION_TRANSFER,
            status=StudentRequest.Status.PENDING, requested_by=self.boss, target_region=self.target_region,
        )


class AssistedQueueTests(AssistedFixtures):
    def test_buckets_keep_transfer_pending_students_out_of_local_tabs(self):
        queue = queries.build_assisted_queue(self.region)
        self.assertEqual([s.student_id for s in queue.unassigned_students], ['AS-UNASSIGNED'])
        self.assertEqual([s.student_id for s in queue.accessibility_students], ['AS-ACC'])
        self.assertEqual([s.student_id for s in queue.transfer_pending_students], ['AS-TRANSFER'])
        self.assertEqual(queue.transfer_requested_ids, {self.transferring.id})
        self.assertEqual(queue.counts, {
            'accessibility_pending': 1, 'unassigned': 1, 'resolved': 0,
            'transfer_requested': 1, 'needs_placement': 2,
        })

    def test_resolved_bucket_is_audit_based_and_deduplicated(self):
        resolved = make_student(self.dorm, 'AS-RESOLVED')
        assignment = assign(resolved, self.room)
        for _ in range(2):
            AssistedAllocationAudit.objects.create(
                action_type=AssistedAllocationAudit.ActionType.MANUAL_ASSIGNMENT, actor=self.boss,
                student=resolved, bed_assignment=assignment,
            )
        queue = queries.build_assisted_queue(self.region)
        self.assertEqual([s.student_id for s in queue.resolved_students], ['AS-RESOLVED'])
        students, group_of = queue.tab('resolved')
        self.assertEqual(group_of, {resolved.id: 'resolved'})
        self.assertEqual(students, [resolved])

    def test_tabs_and_groups(self):
        queue = queries.build_assisted_queue(self.region)
        students, group_of = queue.tab('needs_placement')
        self.assertEqual([s.student_id for s in students], ['AS-ACC', 'AS-UNASSIGNED'])
        self.assertEqual(group_of, {self.accessibility.id: 'accessibility', self.unassigned.id: 'unassigned'})
        students, group_of = queue.tab('transfer_pending')
        self.assertEqual(group_of, {self.transferring.id: 'transfer_pending'})
        students, _ = queue.tab('unknown-tab')
        self.assertEqual(len(students), 2)

    def test_filters(self):
        female = make_student(self.dorm, 'AS-FEMALE', gender=Student.Gender.FEMALE,
                              housing_type=Student.HousingType.SINGLE_FEMALE)
        students = [self.unassigned, female]
        self.assertEqual(queries.filter_queue_students(students, gender='female'), [female])
        self.assertEqual(queries.filter_queue_students(students, dorm_type_id=str(self.dorm.id)), students)
        self.assertEqual(queries.filter_queue_students(students, search='as-fem'), [female])
        self.assertEqual(queries.filter_queue_students(students, search='  '), students)

    def test_student_row_shape(self):
        row = queries.assisted_student_row(self.accessibility, group='accessibility', is_transfer_requested=False)
        self.assertEqual(row['student_id'], 'AS-ACC')
        self.assertTrue(row['accessibility_flag'])
        self.assertIsNone(row['disability_percent'])
        self.assertEqual(row['region_id'], self.region.id)
        self.assertEqual(row['group'], 'accessibility')
        self.assertFalse(row['is_transfer_requested'])


class AssistedDetailTests(AssistedFixtures):
    def test_student_group_priority(self):
        self.assertEqual(queries.student_group(self.unassigned, None), 'unassigned')
        self.assertEqual(queries.student_group(self.accessibility, None), 'accessibility')
        self.assertEqual(queries.student_group(self.transferring, self.transfer_request), 'transfer_pending')
        assign(self.accessibility, self.room)
        self.assertEqual(queries.student_group(self.accessibility, None), 'resolved')

    def test_detail_for_unassigned_student_includes_reason_and_placement(self):
        detail = queries.build_student_detail(self.unassigned)
        self.assertEqual(detail['student']['group'], 'unassigned')
        self.assertEqual(detail['roommate_requests'], [])
        self.assertIn('reason_code', detail['reason'])
        self.assertEqual(detail['history'], [])
        self.assertEqual(detail['current_placement'], {'assigned': False})
        self.assertIsNone(detail['pending_transfer_request'])

    def test_detail_for_transfer_pending_and_accessibility_students_has_no_reason(self):
        detail = queries.build_student_detail(self.transferring)
        self.assertEqual(detail['student']['group'], 'transfer_pending')
        self.assertIsNone(detail['reason'])
        self.assertEqual(detail['pending_transfer_request'], self.transfer_request)
        self.assertIsNone(queries.build_student_detail(self.accessibility)['reason'])

    def test_unassigned_reason_without_dorm_type(self):
        orphan = Student.objects.create(
            student_id='AS-ORPHAN', first_name='O', last_name='R',
            gender=Student.Gender.MALE, housing_type=Student.HousingType.SINGLE_MALE,
        )
        self.assertEqual(queries.unassigned_reason(orphan), {'reason_code': 'NO_ACCEPTED_DORM_TYPE', 'inventory_breakdown': []})

    def test_roommate_requests_and_history(self):
        self.unassigned.roommate_request_1 = 'Friend'
        self.unassigned.roommate_request_student_id_1 = 'F-1'
        self.unassigned.roommate_request_flag_1 = True
        self.unassigned.save()
        self.assertEqual(queries.roommate_requests(self.unassigned), [{'name': 'Friend', 'student_id': 'F-1', 'mutual': True}])

        AssistedAllocationAudit.objects.create(
            action_type=AssistedAllocationAudit.ActionType.MANUAL_OVERRIDE, actor=self.boss,
            student=self.unassigned, note='why', overridden_rules=[{'code': 'x'}],
        )
        history = queries.student_audit_history(self.unassigned)
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]['note'], 'why')
        self.assertEqual(history[0]['actor_name'], self.boss.get_full_name())

    def test_recommendations_short_circuit_for_non_local_students(self):
        payload = queries.build_recommendations(self.boss, self.transferring)
        self.assertFalse(payload['candidates']['feasible'])
        self.assertFalse(payload['already_assigned'])
        self.assertTrue(payload['transfer_pending'])

        assigned = make_student(self.dorm, 'AS-DONE')
        assign(assigned, self.room)
        payload = queries.build_recommendations(self.boss, assigned)
        self.assertTrue(payload['already_assigned'])

        orphan = Student.objects.create(
            student_id='AS-NODORM', first_name='O', last_name='R',
            gender=Student.Gender.MALE, housing_type=Student.HousingType.SINGLE_MALE,
        )
        payload = queries.build_recommendations(make_central_admin('rec-admin@domain.test'), orphan)
        self.assertIsNone(payload['accepted_dorm_type'])
        self.assertIn('reason', payload)

    def test_recommendations_for_a_local_student(self):
        payload = queries.build_recommendations(self.boss, self.unassigned)
        self.assertEqual(payload['accepted_dorm_type'], {'id': self.dorm.id, 'name': self.dorm.name})
        self.assertIn('config_opportunities', payload)
        self.assertIn('has_unsafe_config_candidates', payload)
        self.assertGreaterEqual(payload['candidates']['total_valid_beds'], 1)


class AssistedServiceTests(AssistedFixtures):
    def test_override_check_shape(self):
        check = services.override_check(self.unassigned, self.room)
        self.assertEqual(set(check), {'violations', 'blocked', 'requires_override'})
        self.assertFalse(check['blocked'])

    def test_manual_assignment_places_and_audits(self):
        bed = self.room.beds.order_by('label').first()
        assignment = services.record_manual_assignment(self.unassigned, self.room, bed, self.boss)

        self.assertEqual(assignment.bed, bed)
        self.assertEqual(assignment.assignment_type, BedAssignment.AssignmentType.MANUAL)
        audit = AssistedAllocationAudit.objects.get(student=self.unassigned)
        self.assertEqual(audit.action_type, AssistedAllocationAudit.ActionType.MANUAL_ASSIGNMENT)
        self.assertEqual(audit.previous_state, {'assigned': False})
        self.assertTrue(audit.new_state['assigned'])
        self.assertEqual(audit.building, self.building)

    def test_manual_override_records_waived_rules_and_note(self):
        bed = self.room.beds.order_by('label').first()
        violations = [{'code': 'religion', 'label': 'x', 'overridable': True}]
        assignment = services.record_manual_override(
            self.unassigned, self.room, bed, self.boss, violations=violations, note='approved by boss',
        )
        audit = AssistedAllocationAudit.objects.get(bed_assignment=assignment)
        self.assertEqual(audit.action_type, AssistedAllocationAudit.ActionType.MANUAL_OVERRIDE)
        self.assertEqual(audit.overridden_rules, violations)
        self.assertEqual(audit.note, 'approved by boss')

    def test_blocking_violations_filter(self):
        violations = [{'overridable': True}, {'overridable': False}]
        self.assertEqual(services.blocking_violations(violations), [{'overridable': False}])

    def test_pending_region_transfer_lookup(self):
        self.assertEqual(queries.pending_region_transfer(self.transferring), self.transfer_request)
        self.assertIsNone(queries.pending_region_transfer(self.unassigned))
        self.assertEqual(queries.transfer_requested_student_ids(), {self.transferring.id})
