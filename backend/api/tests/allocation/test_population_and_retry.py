from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from api.models import (
    AllocationRun, BedAssignment, Student, DormType, Building, Apartment, Room,
    Bed,
)

from ._support import (
    _make_region,
    _make_region_boss,
    _make_employee,
    _make_run,
)


# ---------------------------------------------------------------------------
# Population summary ("קלטנו X / Y הוחרגו / Z נשלחו לשיבוץ"): why the number
# of students imported into a region is greater than the number actually
# sent to the OR-Tools solver. Covers api.views._population_summary_for_region
# directly, plus its wiring into run_allocation and allocation_summary.
# ---------------------------------------------------------------------------
class PopulationSummaryTest(TestCase):

    def _make_population(self, region, dorm_type, suffix=''):
        """
        9 students total, deliberately covering every distinct-count case:
          - 3 ordinary, unassigned  -> eligible, sent to solver
          - 2 accessibility only
          - 2 leaving only
          - 1 both accessibility AND leaving (the overlap case)
          - 1 ordinary but ALREADY ASSIGNED -> imported, not accessibility/
            leaving, but still not sent to solver (demonstrates that
            excluded_total alone does not explain imported - sent_to_solver).
        """
        def make(sid, **kw):
            return Student.objects.create(
                student_id=f'{sid}{suffix}', first_name='T', last_name='S',
                gender=Student.Gender.FEMALE, housing_type=Student.HousingType.SINGLE_FEMALE,
                accepted_dorm_type=dorm_type, **kw,
            )

        ordinary = [make(f'POP_ORD{i}') for i in range(1, 4)]
        accessibility = [
            make(f'POP_ACC{i}', accessibility_flag=True) for i in range(1, 3)
        ]
        leaving = [
            make(f'POP_LEAVE{i}', category=Student.StudentCategory.LEAVING) for i in range(1, 3)
        ]
        both = make('POP_BOTH1', accessibility_flag=True, category=Student.StudentCategory.LEAVING)

        building = Building.objects.create(number=500, dorm_type=dorm_type)
        apartment = Apartment.objects.create(
            building=building, number='1', category=Apartment.Category.FEMALE,
            apartment_type=Apartment.ApartmentType.SINGLE, room_count=1,
        )
        room = Room.objects.create(apartment=apartment, name='A', capacity=1)
        bed = Bed.objects.create(room=room, label='1')
        already_assigned = make('POP_ASSIGNED1', assigned_room=room)
        BedAssignment.objects.create(
            student=already_assigned, bed=bed, status=BedAssignment.Status.ACTIVE,
            assignment_type=BedAssignment.AssignmentType.INITIAL,
        )

        return {
            'ordinary': ordinary, 'accessibility': accessibility,
            'leaving': leaving, 'both': both, 'already_assigned': already_assigned,
        }

    def test_population_summary_counts(self):
        """Direct unit coverage of the distinct-count math: excluded_overlap
        counts the accessibility+leaving student once, excluded_total is the
        union (not a naive sum), and sent_to_solver additionally accounts
        for students who are eligible but already assigned."""
        from api.views import _population_summary_for_region

        region = _make_region('PopSummaryRegion')
        dorm_type = DormType.objects.create(name='PopDorm', region=region)
        self._make_population(region, dorm_type)

        summary = _population_summary_for_region(region)

        self.assertEqual(summary['imported_students'], 9)
        self.assertEqual(summary['excluded_accessibility'], 3)  # 2 + the overlap student
        self.assertEqual(summary['excluded_leaving'], 3)        # 2 + the overlap student
        self.assertEqual(summary['excluded_overlap'], 1)
        self.assertEqual(summary['excluded_total'], 5)          # union, not 3+3=6
        self.assertEqual(summary['sent_to_solver'], 3)          # 9 - 5 excluded - 1 already assigned
        self.assertEqual(len(summary['sent_to_solver_student_ids']), 3)

    def test_population_summary_scope_isolation(self):
        """A student imported into an unrelated region/upload must never be
        counted in this region's population summary — scoped strictly to
        Student rows whose accepted_dorm_type belongs to this region."""
        from api.views import _population_summary_for_region

        region = _make_region('PopScopeRegion')
        dorm_type = DormType.objects.create(name='PopScopeDorm', region=region)
        self._make_population(region, dorm_type)

        other_region = _make_region('PopScopeOtherRegion')
        other_dorm_type = DormType.objects.create(name='PopScopeOtherDorm', region=other_region)
        self._make_population(other_region, other_dorm_type, suffix='_OTHER')

        summary = _population_summary_for_region(region)
        self.assertEqual(summary['imported_students'], 9)

        other_summary = _population_summary_for_region(other_region)
        self.assertEqual(other_summary['imported_students'], 9)

    def test_run_allocation_response_includes_population_summary(self):
        """/api/allocation/run/ must return a population_summary whose
        sent_to_solver_student_ids exactly matches the real solver-input
        queryset, and after completion assigned + unassigned == sent_to_solver."""
        region = _make_region('PopRunRegion')
        boss = _make_region_boss(region)
        dorm_type = DormType.objects.create(name='PopRunDorm', region=region)
        self._make_population(region, dorm_type)

        # No rooms available beyond the one already fully occupied above ->
        # every eligible student stays unassigned, which is fine: this test
        # is about the population_summary shape, not solver outcomes.
        patcher = patch('allocation.solver.close_old_connections')
        patcher.start()
        self.addCleanup(patcher.stop)

        client = APIClient()
        client.force_authenticate(user=boss)
        response = client.post('/api/allocation/run/', {'region': region.id}, format='json')
        self.assertEqual(response.status_code, 200, response.data)

        summary = response.data['result']['population_summary']
        self.assertEqual(summary['imported_students'], 9)
        self.assertEqual(summary['excluded_total'], 5)
        self.assertEqual(summary['sent_to_solver'], 3)
        self.assertEqual(summary['assigned'] + summary['unassigned'], summary['sent_to_solver'])

    def test_allocation_summary_preview_includes_population_summary(self):
        """GET /api/allocation/summary/ (pre-run preview) must also expose
        population_summary, scoped to the same region, before any
        AllocationRun exists."""
        region = _make_region('PopPreviewRegion')
        boss = _make_region_boss(region)
        dorm_type = DormType.objects.create(name='PopPreviewDorm', region=region)
        self._make_population(region, dorm_type)

        client = APIClient()
        client.force_authenticate(user=boss)
        response = client.get('/api/allocation/summary/', {'region': region.id})
        self.assertEqual(response.status_code, 200, response.data)

        summary = response.data['population_summary']
        self.assertEqual(summary['imported_students'], 9)
        self.assertEqual(summary['sent_to_solver'], 3)


# ---------------------------------------------------------------------------
# Unassigned-analysis ("למה חלק מהסטודנטים לא שובצו?"): grouped, staged
# hard-constraint explanation for why unassigned students remain unassigned,
# reusing allocation.solver.analyze_unassigned_group so the reported reason
# can never diverge from the solver's own eligibility rules.
# ---------------------------------------------------------------------------
class UnassignedAnalysisTest(TestCase):

    def test_female_single_blocked_by_male_only_inventory_reports_gender_mismatch(self):
        """Models the validated run-115 example: an unassigned female,
        single-housing student whose accepted dorm type has plenty of
        PHYSICALLY free beds, but none of them are compatible (all free
        inventory is male-single/couple). Must report
        HOUSING_TYPE_OR_GENDER_MISMATCH with compatible_free_beds == 0,
        never a generic "no free beds" reason."""
        region = _make_region('UnassignedGenderRegion')
        boss = _make_region_boss(region)
        dorm_type = DormType.objects.create(name='Dorm15Like', code=15, region=region)
        building = Building.objects.create(number=179, dorm_type=dorm_type)

        male_single_apt = Apartment.objects.create(
            building=building, number='1', category=Apartment.Category.MALE,
            apartment_type=Apartment.ApartmentType.SINGLE, room_count=1,
        )
        male_room = Room.objects.create(apartment=male_single_apt, name='M1', capacity=2)
        Bed.objects.create(room=male_room, label='1')
        Bed.objects.create(room=male_room, label='2')

        couple_apt = Apartment.objects.create(
            building=building, number='2', category=Apartment.Category.MIXED,
            apartment_type=Apartment.ApartmentType.COUPLE, room_count=1,
        )
        couple_room = Room.objects.create(apartment=couple_apt, name='C1', capacity=2)
        Bed.objects.create(room=couple_room, label='1')
        Bed.objects.create(room=couple_room, label='2')

        Student.objects.create(
            student_id='UNASSIGNED_F1', first_name='F', last_name='Student',
            gender=Student.Gender.FEMALE, housing_type=Student.HousingType.SINGLE_FEMALE,
            accepted_dorm_type=dorm_type,
        )

        client = APIClient()
        client.force_authenticate(user=boss)
        response = client.get('/api/allocation/results/', {'region': region.id})
        self.assertEqual(response.status_code, 200, response.data)

        analysis = response.data['unassigned_analysis']
        self.assertEqual(len(analysis), 1)
        group = analysis[0]
        self.assertEqual(group['accepted_dorm_type_id'], dorm_type.id)
        self.assertEqual(group['accepted_dorm_type_code'], 15)
        self.assertEqual(group['gender'], Student.Gender.FEMALE)
        self.assertEqual(group['housing_type'], Student.HousingType.SINGLE_FEMALE)
        self.assertEqual(group['student_count'], 1)
        self.assertEqual(group['physically_free_beds_in_accepted_dorm'], 4)
        self.assertEqual(group['compatible_free_beds'], 0)
        self.assertEqual(group['reason_code'], 'HOUSING_TYPE_OR_GENDER_MISMATCH')

        breakdown_categories = {
            (row['category'], row['apartment_type']) for row in group['inventory_breakdown']
        }
        self.assertIn((Apartment.Category.MALE, Apartment.ApartmentType.SINGLE), breakdown_categories)
        self.assertIn((Apartment.Category.MIXED, Apartment.ApartmentType.COUPLE), breakdown_categories)

        # Still keeps the existing free-beds report/table intact alongside
        # the new analysis (Part 2 requires not removing it).
        self.assertIn('available_beds', response.data)

    def test_no_physical_free_beds_reports_that_reason_not_gender_mismatch(self):
        """When the accepted dorm type has zero physically free beds at
        all, the reason must be NO_PHYSICAL_FREE_BEDS_IN_ACCEPTED_DORM, not
        a gender/housing mismatch — the two must stay distinguishable."""
        region = _make_region('UnassignedNoFreeRegion')
        boss = _make_region_boss(region)
        dorm_type = DormType.objects.create(name='FullDorm', region=region)
        building = Building.objects.create(number=300, dorm_type=dorm_type)
        apartment = Apartment.objects.create(
            building=building, number='1', category=Apartment.Category.FEMALE,
            apartment_type=Apartment.ApartmentType.SINGLE, room_count=1,
        )
        room = Room.objects.create(apartment=apartment, name='A', capacity=1)
        bed = Bed.objects.create(room=room, label='1')

        occupant = Student.objects.create(
            student_id='FULL_OCC1', first_name='Occ', last_name='Student',
            gender=Student.Gender.FEMALE, housing_type=Student.HousingType.SINGLE_FEMALE,
            accepted_dorm_type=dorm_type, assigned_room=room,
        )
        BedAssignment.objects.create(
            student=occupant, bed=bed, status=BedAssignment.Status.ACTIVE,
            assignment_type=BedAssignment.AssignmentType.INITIAL,
        )

        Student.objects.create(
            student_id='FULL_UNASSIGNED1', first_name='U', last_name='Student',
            gender=Student.Gender.FEMALE, housing_type=Student.HousingType.SINGLE_FEMALE,
            accepted_dorm_type=dorm_type,
        )

        client = APIClient()
        client.force_authenticate(user=boss)
        response = client.get('/api/allocation/results/', {'region': region.id})
        self.assertEqual(response.status_code, 200, response.data)

        analysis = response.data['unassigned_analysis']
        self.assertEqual(len(analysis), 1)
        self.assertEqual(analysis[0]['reason_code'], 'NO_PHYSICAL_FREE_BEDS_IN_ACCEPTED_DORM')
        self.assertEqual(analysis[0]['physically_free_beds_in_accepted_dorm'], 0)
        self.assertEqual(analysis[0]['compatible_free_beds'], 0)

    def test_no_accepted_dorm_type_grouped_separately(self):
        """A student with no accepted_dorm_type at all must be grouped
        under NO_ACCEPTED_DORM_TYPE with accepted_dorm_type_id/code None,
        never crash the grouping/analysis pipeline. Tested directly against
        the helper since the region-scoped allocation_results endpoint
        cannot itself resolve a region for a student with no dorm type."""
        from api.views import _build_unassigned_analysis

        student = Student.objects.create(
            student_id='NO_DORM1', first_name='N', last_name='D',
            gender=Student.Gender.FEMALE, housing_type=Student.HousingType.SINGLE_FEMALE,
            accepted_dorm_type=None,
        )
        analysis = _build_unassigned_analysis([student])
        self.assertEqual(len(analysis), 1)
        self.assertIsNone(analysis[0]['accepted_dorm_type_id'])
        self.assertIsNone(analysis[0]['accepted_dorm_type_code'])
        self.assertEqual(analysis[0]['reason_code'], 'NO_ACCEPTED_DORM_TYPE')


# ---------------------------------------------------------------------------
# Retry-unassigned-students ("נסה לשבץ שוב את הסטודנטים שלא שובצו"): a
# narrowly-scoped retry that must never touch previously-successful
# assignments, must only re-solve for the original run's unassigned
# population, and must be safely re-runnable without creating duplicates.
# ---------------------------------------------------------------------------
class RetryUnassignedAllocationTest(TestCase):

    def _make_scenario(self):
        region = _make_region('RetryRegion')
        boss = _make_region_boss(region)
        dorm_type = DormType.objects.create(name='RetryDorm', region=region)
        building = Building.objects.create(number=700, dorm_type=dorm_type)
        apartment = Apartment.objects.create(
            building=building, number='1', category=Apartment.Category.FEMALE,
            apartment_type=Apartment.ApartmentType.SINGLE, room_count=1,
        )
        room = Room.objects.create(apartment=apartment, name='A', capacity=1)
        bed = Bed.objects.create(room=room, label='1')

        assigned_student = Student.objects.create(
            student_id='RETRY_ASSIGNED1', first_name='A', last_name='S',
            gender=Student.Gender.FEMALE, housing_type=Student.HousingType.SINGLE_FEMALE,
            accepted_dorm_type=dorm_type, assigned_room=room,
        )
        unassigned_student = Student.objects.create(
            student_id='RETRY_UNASSIGNED1', first_name='U', last_name='S',
            gender=Student.Gender.FEMALE, housing_type=Student.HousingType.SINGLE_FEMALE,
            accepted_dorm_type=dorm_type,
        )

        original_run = AllocationRun.objects.create(
            region=region, run_by=boss, status=AllocationRun.Status.COMPLETED,
            students_processed=2, successful_assignments=1, conflicts=1,
            completed_at=timezone.now(),
            diagnostics={
                'warnings': [], 'anier_building_179_diagnostics': {},
                'population_summary': {
                    'imported_students': 2, 'excluded_accessibility': 0,
                    'excluded_leaving': 0, 'excluded_overlap': 0, 'excluded_total': 0,
                    'sent_to_solver': 2,
                    'sent_to_solver_student_ids': [assigned_student.id, unassigned_student.id],
                    'assigned': 1, 'unassigned': 1,
                },
            },
        )
        assignment = BedAssignment.objects.create(
            student=assigned_student, bed=bed, status=BedAssignment.Status.ACTIVE,
            assignment_type=BedAssignment.AssignmentType.INITIAL, allocation_run=original_run,
        )

        return region, boss, dorm_type, building, apartment, room, bed, \
            assigned_student, unassigned_student, original_run, assignment

    def test_retry_with_no_new_inventory_preserves_prior_assignment_and_retries_only_unassigned(self):
        (region, boss, dorm_type, building, apartment, room, bed,
         assigned_student, unassigned_student, original_run, assignment) = self._make_scenario()

        patcher = patch('allocation.solver.close_old_connections')
        patcher.start()
        self.addCleanup(patcher.stop)

        client = APIClient()
        client.force_authenticate(user=boss)
        response = client.post(f'/api/allocation/runs/{original_run.id}/retry-unassigned/', {}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['result']['retried_student_count'], 1)
        self.assertEqual(response.data['result']['successful_assignments'], 0)

        # The previously-successful assignment is completely untouched.
        assignment.refresh_from_db()
        self.assertEqual(assignment.status, BedAssignment.Status.ACTIVE)
        self.assertEqual(assignment.bed_id, bed.id)
        assigned_student.refresh_from_db()
        self.assertEqual(assigned_student.assigned_room_id, room.id)

        # Still unassigned since no new inventory was added.
        unassigned_student.refresh_from_db()
        self.assertIsNone(unassigned_student.assigned_room_id)

        # A new, separate AllocationRun was created and linked back.
        retry_run_id = response.data['result']['run']['id']
        self.assertNotEqual(retry_run_id, original_run.id)
        retry_run = AllocationRun.objects.get(pk=retry_run_id)
        self.assertEqual(retry_run.diagnostics['retry_of_run_id'], original_run.id)

        # Only one active assignment total exists for this bed — no
        # duplicate was created.
        self.assertEqual(
            BedAssignment.objects.filter(bed=bed, status=BedAssignment.Status.ACTIVE).count(), 1,
        )

    def test_retry_after_new_inventory_added_assigns_previously_unassigned_student(self):
        """Once staff add a genuinely new free bed, retrying the same run
        must be able to assign the previously-unassigned student, without
        disturbing the original assignment."""
        (region, boss, dorm_type, building, apartment, room, bed,
         assigned_student, unassigned_student, original_run, assignment) = self._make_scenario()

        # Staff adds capacity: a second bed in a new room of the same
        # accepted dorm type / matching category+type.
        new_room = Room.objects.create(apartment=apartment, name='B', capacity=1)
        Bed.objects.create(room=new_room, label='1')

        patcher = patch('allocation.solver.close_old_connections')
        patcher.start()
        self.addCleanup(patcher.stop)

        client = APIClient()
        client.force_authenticate(user=boss)
        response = client.post(f'/api/allocation/runs/{original_run.id}/retry-unassigned/', {}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['result']['retried_student_count'], 1)
        self.assertEqual(response.data['result']['successful_assignments'], 1)

        unassigned_student.refresh_from_db()
        self.assertIsNotNone(unassigned_student.assigned_room_id)
        self.assertEqual(unassigned_student.assigned_room_id, new_room.id)

        # Original assignment still completely untouched.
        assignment.refresh_from_db()
        self.assertEqual(assignment.status, BedAssignment.Status.ACTIVE)
        assigned_student.refresh_from_db()
        self.assertEqual(assigned_student.assigned_room_id, room.id)

    def test_retry_twice_after_success_reports_nothing_left_to_retry(self):
        """Retrying again after everyone from the original population is
        assigned must not error or create duplicates — it should report
        that there is nothing left to retry."""
        (region, boss, dorm_type, building, apartment, room, bed,
         assigned_student, unassigned_student, original_run, assignment) = self._make_scenario()

        new_room = Room.objects.create(apartment=apartment, name='B', capacity=1)
        Bed.objects.create(room=new_room, label='1')

        patcher = patch('allocation.solver.close_old_connections')
        patcher.start()
        self.addCleanup(patcher.stop)

        client = APIClient()
        client.force_authenticate(user=boss)
        first = client.post(f'/api/allocation/runs/{original_run.id}/retry-unassigned/', {}, format='json')
        self.assertEqual(first.status_code, 200, first.data)
        self.assertEqual(first.data['result']['successful_assignments'], 1)

        second = client.post(f'/api/allocation/runs/{original_run.id}/retry-unassigned/', {}, format='json')
        self.assertEqual(second.status_code, 200, second.data)
        self.assertEqual(second.data['result']['retried_student_count'], 0)

        self.assertEqual(
            BedAssignment.objects.filter(status=BedAssignment.Status.ACTIVE).count(), 2,
        )

    def test_retry_requires_completed_run(self):
        (region, boss, dorm_type, building, apartment, room, bed,
         assigned_student, unassigned_student, original_run, assignment) = self._make_scenario()
        original_run.status = AllocationRun.Status.RUNNING
        original_run.completed_at = None
        original_run.save()

        client = APIClient()
        client.force_authenticate(user=boss)
        response = client.post(f'/api/allocation/runs/{original_run.id}/retry-unassigned/', {}, format='json')
        self.assertEqual(response.status_code, 400, response.data)
        self.assertEqual(response.data['error_code'], 'RUN_NOT_COMPLETED')

    def test_retry_requires_saved_original_population(self):
        """An older run created before this feature existed has no
        sent_to_solver_student_ids saved — retry must refuse rather than
        silently guessing the population."""
        region = _make_region('RetryOldRunRegion')
        boss = _make_region_boss(region)
        old_run = _make_run(region, boss, status_val=AllocationRun.Status.COMPLETED)

        client = APIClient()
        client.force_authenticate(user=boss)
        response = client.post(f'/api/allocation/runs/{old_run.id}/retry-unassigned/', {}, format='json')
        self.assertEqual(response.status_code, 400, response.data)
        self.assertEqual(response.data['error_code'], 'MISSING_ORIGINAL_POPULATION')

    def test_retry_forbidden_for_employee(self):
        (region, boss, dorm_type, building, apartment, room, bed,
         assigned_student, unassigned_student, original_run, assignment) = self._make_scenario()
        employee = _make_employee(region)

        client = APIClient()
        client.force_authenticate(user=employee)
        response = client.post(f'/api/allocation/runs/{original_run.id}/retry-unassigned/', {}, format='json')
        self.assertEqual(response.status_code, 403, response.data)
