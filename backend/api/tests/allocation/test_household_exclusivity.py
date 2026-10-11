from unittest.mock import patch

from django.test import TestCase

from api.models import (
    Region, BedAssignment, Student, DormType, Building, Apartment, Room, Bed,
)


# ---------------------------------------------------------------------------
# Exclusive-apartment allocation (Z1/Z2 singles, Z3 couples, Z4 families, Z6
# single-in-apartment): each Z3/Z4/Z6 Student record represents one COMPLETE,
# independent application. Diagnostic + regression tests for the
# application-exclusivity constraint in allocation/solver.py.
# ---------------------------------------------------------------------------

def _print_household_capacity_report(test_name, result, students, rooms):
    """
    Reusable diagnostic printer for exclusive-apartment allocation tests.
    Prints, per applicant: housing type, dorm type, and — for assigned
    students — the actual building/apartment/room/bed they landed in plus
    that apartment's real inventory (rooms, room capacity, total beds,
    active occupants after this run), whether they were ever a candidate,
    whether they were assigned, and a rejection reason when available.
    Then prints aggregate inventory totals (physical beds, free beds,
    empty apartments, applications assigned/unassigned).
    """
    rooms = list(rooms)
    room_ids = [room.id for room in rooms]

    proposed = result.get('proposed_assignments', []) or []
    assignment_by_student_id = {item['student_db_id']: item for item in proposed}
    no_feasible_ids = set(result.get('students_with_no_feasible_beds') or [])

    print('\n' + '=' * 175)
    print(f'TEST: {test_name}')
    print(
        f"status={result.get('solver_status')} | students={len(students)} | "
        f"assigned={result.get('successful_assignments', 0)} | "
        f"conflicts={result.get('conflicts', 0)}"
    )
    warnings = result.get('warnings') or []
    if warnings:
        print('WARNINGS:')
        for warning in warnings:
            print(f'  - {warning}')
    print('=' * 175)

    print(
        f"{'HOUSING TYPE':<28} {'STUDENT':<10} {'DORM TYPE':<14} {'BUILDING':<9} "
        f"{'APARTMENT':<10} {'APT TYPE':<9} {'CATEGORY':<9} {'ROOMS':<6} "
        f"{'ROOM CAP':<9} {'BEDS':<6} {'ACTIVE OCC':<11} {'CANDIDATE':<10} "
        f"{'ASSIGNED':<9} {'REJECTION REASON':<28}"
    )
    print('-' * 175)

    for student in sorted(students, key=lambda item: item.student_id):
        assignment = assignment_by_student_id.get(student.id)
        dorm_type_name = student.accepted_dorm_type.name if student.accepted_dorm_type_id else '-'
        is_candidate = student.id not in no_feasible_ids
        is_assigned = assignment is not None

        if assignment:
            bed = Bed.objects.select_related(
                'room', 'room__apartment', 'room__apartment__building',
            ).get(id=assignment['bed_id'])
            room = bed.room
            apartment = room.apartment
            building = apartment.building
            building_label = str(building.number)
            apartment_label = str(apartment.number)
            apt_type_label = str(apartment.apartment_type)
            category_label = str(apartment.category)
            rooms_count = apartment.rooms.count()
            room_capacity = room.capacity
            beds_total = Bed.objects.filter(room__apartment_id=apartment.id).count()
            active_occupants = BedAssignment.objects.filter(
                bed__room__apartment_id=apartment.id,
                status=BedAssignment.Status.ACTIVE,
            ).count()
            reason = '-'
        else:
            building_label = apartment_label = apt_type_label = category_label = '-'
            rooms_count = room_capacity = beds_total = active_occupants = '-'
            reason = 'no feasible beds' if not is_candidate else 'capacity/household conflict'

        print(
            f"{str(student.housing_type):<28} "
            f"{student.student_id:<10} "
            f"{dorm_type_name:<14} "
            f"{building_label:<9} "
            f"{apartment_label:<10} "
            f"{apt_type_label:<9} "
            f"{category_label:<9} "
            f"{str(rooms_count):<6} "
            f"{str(room_capacity):<9} "
            f"{str(beds_total):<6} "
            f"{str(active_occupants):<11} "
            f"{('yes' if is_candidate else 'no'):<10} "
            f"{('yes' if is_assigned else 'no'):<9} "
            f"{reason:<28}"
        )

    apartment_ids = {room.apartment_id for room in rooms}
    physical_beds = Bed.objects.filter(room_id__in=room_ids).count()
    active_bed_ids = set(
        BedAssignment.objects.filter(
            bed__room_id__in=room_ids,
            status=BedAssignment.Status.ACTIVE,
        ).values_list('bed_id', flat=True)
    )
    free_beds = physical_beds - len(active_bed_ids)
    occupied_apartment_ids = set(
        BedAssignment.objects.filter(
            bed__room_id__in=room_ids,
            status=BedAssignment.Status.ACTIVE,
        ).values_list('bed__room__apartment_id', flat=True)
    )
    empty_apartments = len(apartment_ids - occupied_apartment_ids)

    print('-' * 175)
    print('INVENTORY TOTALS')
    print(f"  physical beds:              {physical_beds}")
    print(f"  free beds (after run):      {free_beds}")
    print(f"  empty apartments:           {empty_apartments}")
    print(f"  applications assigned:      {result.get('successful_assignments', 0)}")
    print(f"  applications unassigned:    {result.get('conflicts', 0)}")
    print('=' * 175 + '\n')


class HouseholdExclusivityTest(TestCase):
    """
    Authoritative data model (confirmed with the business owner): for
    exclusive housing types, ONE Student database record represents the
    ENTIRE application, not one household member.

      - Z3 / COUPLE: one Student row represents the student AND their
        partner. The partner is never stored as a separate Student record.
      - Z4 / FAMILY: one Student row represents the student AND their
        complete family. Family members are never stored as separate
        Student records.
      - Z6 / SINGLE_IN_APARTMENT: one Student row represents one single
        applicant requesting an entire apartment.

    Consequently:
      - two Z3 Student records are always two DIFFERENT couple
        applications;
      - two Z4 Student records are always two DIFFERENT family
        applications;
      - two Z6 Student records are always two DIFFERENT individual
        applications;
      - a mutual roommate request between any two exclusive-type records
        must NEVER combine them into one household — there is no such
        thing as "the applicant's spouse/family member inside the Student
        table" to find and merge with.

    Allocation semantics for Z3/Z4/Z6 are therefore APPLICATION-based, not
    bed-based: one Student record consumes an entire apartment, at most
    one Student record may ever be assigned to a given exclusive apartment
    regardless of remaining physical bed capacity (unused beds represent
    the untracked spouse/family), and any existing active assignment in
    the apartment makes it unavailable to every other applicant — a
    mutual roommate request never overrides this.

    An earlier version of this file (and of allocation/solver.py) treated
    two same-type Student rows linked by a mutual positive roommate
    request as verified members of ONE household allowed to co-occupy an
    apartment up to its bed capacity. That assumption was incorrect and
    has been reverted: `allocation.solver` no longer contains
    `_exclusive_household_groups`, `_verified_household_pairs`, or
    `_may_join_existing_exclusive_occupants`; the capacity constraint for
    exclusive apartments is the simple `sum(exclusive_vars) <= 1` below.
    Exclusive-type students are also excluded from the general
    roommate-pair machinery entirely (see the `roommate_pairs` filter in
    `run_improved_ortools_allocation`), so a stray mutual request between
    two unrelated Z3/Z4/Z6 applicants can never suppress either
    assignment.
    """

    def setUp(self):
        patcher = patch('allocation.solver.close_old_connections')
        patcher.start()
        self.addCleanup(patcher.stop)

        self.region = Region.objects.create(id='household_region', name='Household Region')
        self.dorm_type = DormType.objects.create(name='HouseholdDorm', region=self.region)
        self.other_dorm_type = DormType.objects.create(name='OtherHouseholdDorm', region=self.region)
        self.building = Building.objects.create(number=501, dorm_type=self.dorm_type)

    # ------------------------------------------------------------------
    # Infrastructure helpers
    # ------------------------------------------------------------------

    def _make_apartment(self, number, apartment_type, category, room_specs, building=None):
        """room_specs: list of (room_name, capacity) tuples. Beds are
        created explicitly (not relying on solver auto-repair) unless a
        test deliberately wants to exercise that self-healing path."""
        building = building or self.building

        apartment = Apartment.objects.create(
            building=building,
            number=str(number),
            category=category,
            apartment_type=apartment_type,
            room_count=len(room_specs),
        )
        rooms = []
        for room_name, capacity in room_specs:
            room = Room.objects.create(apartment=apartment, name=room_name, capacity=capacity)
            for index in range(capacity):
                Bed.objects.create(room=room, label=str(index + 1))
            rooms.append(room)
        return apartment, rooms

    def _make_student(self, student_id, housing_type, *, gender=None, accepted_dorm_type=None):
        if gender is None:
            gender = (
                Student.Gender.MALE
                if housing_type == Student.HousingType.SINGLE_MALE
                else Student.Gender.FEMALE
            )
        return Student.objects.create(
            student_id=student_id,
            first_name='Test',
            last_name=student_id,
            gender=gender,
            housing_type=housing_type,
            accepted_dorm_type=accepted_dorm_type,
        )

    def _make_mutual_positive_roommate_pair(self, student_1, student_2):
        self._add_positive_roommate_link(student_1, student_2, index=1)
        self._add_positive_roommate_link(student_2, student_1, index=1)

    def _add_positive_roommate_link(self, from_student, to_student, index):
        """
        Add a one-directional positive roommate request in a specific
        request slot (1-5), without disturbing any other slot already set
        on `from_student` — needed to build a multi-link chain (e.g. A-B
        and B-C) for the transitive-merging tests below.
        """
        id_field = f'roommate_request_student_id_{index}'
        flag_field = f'roommate_request_flag_{index}'
        setattr(from_student, id_field, to_student.student_id)
        setattr(from_student, flag_field, True)
        from_student.save(update_fields=[id_field, flag_field])

    CONFIG = {
        'sameGender': {'enabled': True, 'strict': True, 'critical': True, 'weight': 0},
        'roommatePositiveOnly': {'enabled': True, 'strict': True, 'critical': True, 'weight': 0},
        'priorityFirst': {'enabled': False},
        'ReligiousTogether': {'enabled': False},
        'sameReligion': {'enabled': False},
        'roommateMatch': {'enabled': False},
        'sectorMatching': {'enabled': False},
        'avoidYearMix_1_with_3_4': {'enabled': False},
        'avoidAtudaimWithHasmaha': {'enabled': False},
    }

    def _run(self, students, rooms):
        import inspect
        from allocation.solver import run_improved_ortools_allocation

        test_name = inspect.stack()[1].function
        students = list(students)
        rooms = list(rooms)

        result = run_improved_ortools_allocation(students, rooms, self.CONFIG)

        _print_household_capacity_report(test_name, result, students, rooms)
        return result

    def _apartment_of(self, result, student):
        for assignment in result.get('proposed_assignments', []):
            if assignment['student_db_id'] == student.id:
                return Bed.objects.select_related('room__apartment').get(
                    id=assignment['bed_id']
                ).room.apartment
        return None

    # ------------------------------------------------------------------
    # 1. One Z3 application occupies one whole couple apartment.
    # ------------------------------------------------------------------

    def test_single_couple_application_occupies_whole_apartment(self):
        """One Z3 Student record represents an entire couple application.
        It is assigned into the empty 2-bed couple apartment, consuming
        one bed; the apartment is then unavailable to anyone else."""
        apartment, rooms = self._make_apartment(
            1, Apartment.ApartmentType.COUPLE, Apartment.Category.MIXED,
            [('A', 2)],
        )
        s1 = self._make_student('C1A', Student.HousingType.COUPLE)

        result = self._run([s1], rooms)
        self.assertEqual(result['successful_assignments'], 1, result['proposed_assignments'])
        self.assertEqual(self._apartment_of(result, s1).id, apartment.id)

    # ------------------------------------------------------------------
    # 2. Two Z3 applications cannot share, even with a mutual roommate
    #    request between them.
    # ------------------------------------------------------------------

    def test_two_couple_applications_cannot_share_even_with_mutual_request(self):
        """Two Z3 Student records are always two DIFFERENT couple
        applications, never two members of one household. Even with a
        mutual positive roommate request between them, only one of the
        two records may ever be assigned to the single available couple
        apartment; the request must have no effect on this exclusivity."""
        apartment, rooms = self._make_apartment(
            1, Apartment.ApartmentType.COUPLE, Apartment.Category.MIXED,
            [('A', 2)],
        )
        s1 = self._make_student('C1A', Student.HousingType.COUPLE)
        s2 = self._make_student('C1B', Student.HousingType.COUPLE)
        self._make_mutual_positive_roommate_pair(s1, s2)

        result = self._run([s1, s2], rooms)
        self.assertEqual(result['successful_assignments'], 1, result['proposed_assignments'])

        assigned_ids = {a['student_db_id'] for a in result['proposed_assignments']}
        self.assertEqual(len(assigned_ids & {s1.id, s2.id}), 1)

    # ------------------------------------------------------------------
    # 3. One Z4 application occupies one whole family apartment.
    # ------------------------------------------------------------------

    def test_single_family_application_occupies_whole_apartment(self):
        """One Z4 Student record represents an entire family application
        (the student and their complete family, not stored as separate
        records). It is assigned into the empty family apartment,
        consuming one bed; the apartment is then unavailable to anyone
        else, regardless of remaining physical beds."""
        apartment, rooms = self._make_apartment(
            2, Apartment.ApartmentType.FAMILY, Apartment.Category.MIXED,
            [('A', 2)],
        )
        s1 = self._make_student('F1A', Student.HousingType.FAMILY)

        result = self._run([s1], rooms)
        self.assertEqual(result['successful_assignments'], 1, result['proposed_assignments'])
        self.assertEqual(self._apartment_of(result, s1).id, apartment.id)

    # ------------------------------------------------------------------
    # 4. Two Z4 applications cannot share, even with a mutual roommate
    #    request between them.
    # ------------------------------------------------------------------

    def test_two_family_applications_cannot_share_even_with_mutual_request(self):
        """Two Z4 Student records are always two DIFFERENT family
        applications. A mutual positive roommate request between them
        must not combine them into one household — only one of the two
        may ever be assigned to the single available family apartment."""
        apartment, rooms = self._make_apartment(
            2, Apartment.ApartmentType.FAMILY, Apartment.Category.MIXED,
            [('A', 2)],
        )
        s1 = self._make_student('F1A', Student.HousingType.FAMILY)
        s2 = self._make_student('F1B', Student.HousingType.FAMILY)
        self._make_mutual_positive_roommate_pair(s1, s2)

        result = self._run([s1, s2], rooms)
        self.assertEqual(result['successful_assignments'], 1, result['proposed_assignments'])

        assigned_ids = {a['student_db_id'] for a in result['proposed_assignments']}
        self.assertEqual(len(assigned_ids & {s1.id, s2.id}), 1)

    # ------------------------------------------------------------------
    # 4b. A mutual roommate request between two INDEPENDENT exclusive
    #     applications must never suppress either assignment when they
    #     have separate apartments available.
    # ------------------------------------------------------------------

    def test_mutual_request_between_independent_couples_does_not_block_assignment(self):
        """Two Z3 Student records with a mutual positive roommate request
        between them are two independent applications. When two separate
        couple apartments are available, BOTH are assigned — one to each
        apartment. The stray roommate request must never be treated as
        household linkage and must never cap them at a single combined
        assignment."""
        apartment_1, rooms_1 = self._make_apartment(
            1, Apartment.ApartmentType.COUPLE, Apartment.Category.MIXED, [('A', 2)],
        )
        apartment_2, rooms_2 = self._make_apartment(
            2, Apartment.ApartmentType.COUPLE, Apartment.Category.MIXED, [('A', 2)],
        )
        s1 = self._make_student('IND1', Student.HousingType.COUPLE)
        s2 = self._make_student('IND2', Student.HousingType.COUPLE)
        self._make_mutual_positive_roommate_pair(s1, s2)

        result = self._run([s1, s2], rooms_1 + rooms_2)
        self.assertEqual(result['successful_assignments'], 2, result['proposed_assignments'])

        assigned_apartment_ids = {
            self._apartment_of(result, s1).id,
            self._apartment_of(result, s2).id,
        }
        self.assertEqual(assigned_apartment_ids, {apartment_1.id, apartment_2.id})

    # ------------------------------------------------------------------
    # 3. Z6 assigned exclusively to a couple-layout apartment.
    # ------------------------------------------------------------------

    def test_z6_assigned_exclusively_to_couple_layout_apartment(self):
        """A single Z6 (single student receiving a couple-layout
        apartment) applicant is assigned into a COUPLE-type apartment on
        their own, reserving the whole apartment for their household."""
        apartment, rooms = self._make_apartment(
            3, Apartment.ApartmentType.COUPLE, Apartment.Category.MIXED,
            [('A', 2)],
        )
        z6_student = self._make_student('Z6A', Student.HousingType.SINGLE_IN_APARTMENT)

        result = self._run([z6_student], rooms)
        self.assertEqual(result['successful_assignments'], 1, result['proposed_assignments'])
        self.assertEqual(self._apartment_of(result, z6_student).id, apartment.id)

    # ------------------------------------------------------------------
    # 4. Two exclusive applicants cannot share one apartment.
    # ------------------------------------------------------------------

    def test_two_unrelated_exclusive_applicants_cannot_share_apartment(self):
        """Two UNRELATED couple applicants (no mutual roommate request
        between them) compete for the same single couple apartment: only
        one household may be assigned there — never both."""
        apartment, rooms = self._make_apartment(
            4, Apartment.ApartmentType.COUPLE, Apartment.Category.MIXED,
            [('A', 2)],
        )
        s1 = self._make_student('U1', Student.HousingType.COUPLE)
        s2 = self._make_student('U2', Student.HousingType.COUPLE)

        result = self._run([s1, s2], rooms)
        self.assertEqual(result['successful_assignments'], 1, result['proposed_assignments'])

        assigned_ids = {a['student_db_id'] for a in result['proposed_assignments']}
        self.assertEqual(len(assigned_ids & {s1.id, s2.id}), 1)

    # ------------------------------------------------------------------
    # 5. A partially occupied apartment rejects a new exclusive applicant.
    # ------------------------------------------------------------------

    def test_partially_occupied_apartment_rejects_new_exclusive_applicant(self):
        """A couple apartment already has one ACTIVE existing occupant
        (from a prior run). A new, unrelated couple-type applicant must be
        rejected — the existing assignment is preserved unchanged."""
        apartment, rooms = self._make_apartment(
            5, Apartment.ApartmentType.COUPLE, Apartment.Category.MIXED,
            [('A', 2)],
        )
        existing_occupant = self._make_student('EXIST_C', Student.HousingType.COUPLE)
        existing_bed = rooms[0].beds.first()
        BedAssignment.objects.create(
            student=existing_occupant,
            bed=existing_bed,
            status=BedAssignment.Status.ACTIVE,
            assignment_type=BedAssignment.AssignmentType.MANUAL,
        )

        new_applicant = self._make_student('NEW_C', Student.HousingType.COUPLE)

        result = self._run([new_applicant], rooms)
        self.assertEqual(result['successful_assignments'], 0, result['proposed_assignments'])

        existing_assignment = BedAssignment.objects.get(student=existing_occupant)
        self.assertEqual(existing_assignment.status, BedAssignment.Status.ACTIVE)
        self.assertEqual(existing_assignment.bed_id, existing_bed.id)

    # ------------------------------------------------------------------
    # 6. Wrong apartment type/category is rejected.
    # ------------------------------------------------------------------

    def test_wrong_apartment_type_or_category_is_rejected(self):
        """A couple-type apartment mistakenly marked category=FEMALE
        (instead of MIXED) is correctly rejected for a couple applicant,
        even though physical beds exist there."""
        mislabeled_apartment, rooms = self._make_apartment(
            6, Apartment.ApartmentType.COUPLE, Apartment.Category.FEMALE,
            [('A', 2)],
        )
        s1 = self._make_student('WRONG1', Student.HousingType.COUPLE)

        result = self._run([s1], rooms)
        self.assertEqual(result['successful_assignments'], 0, result['proposed_assignments'])

    # ------------------------------------------------------------------
    # 7. Accepted dorm type filtering works correctly.
    # ------------------------------------------------------------------

    def test_accepted_dorm_type_filtering(self):
        """A couple applicant whose accepted_dorm_type does not match the
        only available couple apartment's dorm type is rejected; the same
        applicant with a matching accepted_dorm_type is assigned."""
        apartment, rooms = self._make_apartment(
            7, Apartment.ApartmentType.COUPLE, Apartment.Category.MIXED,
            [('A', 2)],
        )

        mismatched_student = self._make_student(
            'DORM_MISMATCH', Student.HousingType.COUPLE, accepted_dorm_type=self.other_dorm_type,
        )
        result_mismatch = self._run([mismatched_student], rooms)
        self.assertEqual(
            result_mismatch['successful_assignments'], 0, result_mismatch['proposed_assignments'],
        )

        matched_student = self._make_student(
            'DORM_MATCH', Student.HousingType.COUPLE, accepted_dorm_type=self.dorm_type,
        )
        result_match = self._run([matched_student], rooms)
        self.assertEqual(
            result_match['successful_assignments'], 1, result_match['proposed_assignments'],
        )

    # ------------------------------------------------------------------
    # 8. Available apartment with missing beds is detected/repaired.
    # ------------------------------------------------------------------

    def test_missing_bed_records_are_detected_and_repaired(self):
        """A Room is recorded with capacity=2, but only ONE Bed row was
        actually created (a data-entry gap). The solver's existing
        bed-auto-repair (_ensure_beds_for_room) detects and creates the
        missing bed. A single Z3 application is still assigned exactly
        once, occupying one bed — the repaired second bed does not admit
        a second Student record."""
        apartment = Apartment.objects.create(
            building=self.building, number='8', category=Apartment.Category.MIXED,
            apartment_type=Apartment.ApartmentType.COUPLE, room_count=1,
        )
        room = Room.objects.create(apartment=apartment, name='A', capacity=2)
        Bed.objects.create(room=room, label='1')  # only one of two beds created

        self.assertEqual(room.beds.count(), 1, 'Test setup should start with a missing bed.')

        s1 = self._make_student('REPAIR1', Student.HousingType.COUPLE)

        result = self._run([s1], [room])

        self.assertEqual(room.beds.count(), 2, 'The missing bed should have been auto-created.')
        self.assertEqual(result['successful_assignments'], 1, result['proposed_assignments'])

    # ------------------------------------------------------------------
    # 9. Multiple available couple/family apartments maximize assignments.
    # ------------------------------------------------------------------

    def test_multiple_apartments_maximize_assigned_applications(self):
        """Two couple apartments (2 beds each) but THREE independent Z3
        applications compete for them: exactly two are assigned — one
        Student record per apartment — and the third remains entirely
        unassigned. A spurious mutual roommate request between two of the
        applicants must have no effect on this outcome."""
        apartment_1, rooms_1 = self._make_apartment(
            9, Apartment.ApartmentType.COUPLE, Apartment.Category.MIXED, [('A', 2)],
        )
        apartment_2, rooms_2 = self._make_apartment(
            10, Apartment.ApartmentType.COUPLE, Apartment.Category.MIXED, [('A', 2)],
        )

        s1 = self._make_student('MC1', Student.HousingType.COUPLE)
        s2 = self._make_student('MC2', Student.HousingType.COUPLE)
        s3 = self._make_student('MC3', Student.HousingType.COUPLE)
        self._make_mutual_positive_roommate_pair(s1, s2)

        result = self._run([s1, s2, s3], rooms_1 + rooms_2)

        self.assertEqual(result['successful_assignments'], 2, result['proposed_assignments'])

        assigned_ids = {a['student_db_id'] for a in result['proposed_assignments']}
        self.assertEqual(len(assigned_ids), 2, 'Exactly two of the three applications should be assigned.')

        assigned_apartment_ids = [
            self._apartment_of(result, student).id
            for student in (s1, s2, s3)
            if student.id in assigned_ids
        ]
        self.assertEqual(
            len(set(assigned_apartment_ids)), 2,
            'The two assigned applications must occupy two different apartments '
            '— one Student record per apartment, never two in one.',
        )

    # ------------------------------------------------------------------
    # 10. Ordinary single allocation remains unchanged.
    # ------------------------------------------------------------------

    def test_ordinary_single_allocation_unchanged(self):
        """Z1/Z2 ordinary single students are unaffected by the household-
        exclusivity fix: each single apartment still holds independent,
        unrelated single students up to its own bed capacity."""
        female_apartment, female_rooms = self._make_apartment(
            11, Apartment.ApartmentType.SINGLE, Apartment.Category.FEMALE, [('A', 2)],
        )
        male_apartment, male_rooms = self._make_apartment(
            12, Apartment.ApartmentType.SINGLE, Apartment.Category.MALE, [('A', 2)],
        )

        sf1 = self._make_student('SF1', Student.HousingType.SINGLE_FEMALE)
        sf2 = self._make_student('SF2', Student.HousingType.SINGLE_FEMALE)
        sm1 = self._make_student('SM1', Student.HousingType.SINGLE_MALE)

        result = self._run([sf1, sf2, sm1], female_rooms + male_rooms)
        self.assertEqual(result['successful_assignments'], 3, result['proposed_assignments'])

        self.assertEqual(self._apartment_of(result, sf1).id, female_apartment.id)
        self.assertEqual(self._apartment_of(result, sf2).id, female_apartment.id)
        self.assertEqual(self._apartment_of(result, sm1).id, male_apartment.id)

    # ------------------------------------------------------------------
    # 11. Z6 is NEVER grouped, even given a mutual roommate request.
    # ------------------------------------------------------------------

    def test_z6_never_groups_even_with_mutual_roommate_request(self):
        """
        Two Z6 Student records are always two DIFFERENT individual
        applications, each requiring exclusive use of an entire apartment.
        A mutual roommate request between them has no effect. With only
        one couple-layout apartment available, only ONE of them is
        assigned; the other remains unassigned rather than sharing.
        """
        apartment, rooms = self._make_apartment(
            14, Apartment.ApartmentType.COUPLE, Apartment.Category.MIXED, [('A', 2)],
        )
        z6_a = self._make_student('Z6PAIR_A', Student.HousingType.SINGLE_IN_APARTMENT)
        z6_b = self._make_student('Z6PAIR_B', Student.HousingType.SINGLE_IN_APARTMENT)
        self._make_mutual_positive_roommate_pair(z6_a, z6_b)

        result = self._run([z6_a, z6_b], rooms)
        self.assertEqual(result['successful_assignments'], 1, result['proposed_assignments'])

        assigned_ids = {a['student_db_id'] for a in result['proposed_assignments']}
        self.assertEqual(
            len(assigned_ids & {z6_a.id, z6_b.id}),
            1,
            'Z6 must never share an apartment, even with a mutually '
            'requested partner.',
        )
        self.assertEqual(self._apartment_of(result, z6_a) or self._apartment_of(result, z6_b), apartment)

    # ------------------------------------------------------------------
    # 12. Household grouping must never combine different housing types.
    # ------------------------------------------------------------------

    def test_cross_housing_type_mutual_request_has_no_effect(self):
        """
        A Z3 (couple) and a Z4 (family) applicant mutually request each
        other as roommates. There is no household concept linking them —
        the request is simply irrelevant to allocation. Each is
        independently assigned into its own type-matching apartment; the
        mutual request neither merges them nor blocks either assignment.
        """
        couple_apartment, couple_rooms = self._make_apartment(
            12, Apartment.ApartmentType.COUPLE, Apartment.Category.MIXED, [('A', 2)],
        )
        family_apartment, family_rooms = self._make_apartment(
            13, Apartment.ApartmentType.FAMILY, Apartment.Category.MIXED, [('A', 2)],
        )
        couple_student = self._make_student('CROSS_Z3', Student.HousingType.COUPLE)
        family_student = self._make_student('CROSS_Z4', Student.HousingType.FAMILY)
        self._make_mutual_positive_roommate_pair(couple_student, family_student)

        result = self._run([couple_student, family_student], couple_rooms + family_rooms)

        self.assertEqual(result['successful_assignments'], 2, result['proposed_assignments'])
        self.assertEqual(self._apartment_of(result, couple_student).id, couple_apartment.id)
        self.assertEqual(self._apartment_of(result, family_student).id, family_apartment.id)

    # ------------------------------------------------------------------
    # 14. Existing assignment: verified partner may join; unrelated may not.
    # ------------------------------------------------------------------

    def test_mutual_request_does_not_admit_second_record_into_occupied_apartment(self):
        """
        One Z3 application already occupies the apartment (a pre-existing
        active assignment, e.g. from a previous run or manual entry). A
        second, independent Z3 application with a mutual positive
        roommate request to the existing occupant must still be REJECTED
        — a mutual request is never grounds to admit a second Student
        record into an apartment that already has any active assignment.
        The existing assignment is preserved unchanged.
        """
        apartment, rooms = self._make_apartment(
            16, Apartment.ApartmentType.COUPLE, Apartment.Category.MIXED, [('A', 2)],
        )
        existing_member = self._make_student('EXIST_V1', Student.HousingType.COUPLE)
        other_applicant = self._make_student('PARTNER_V2', Student.HousingType.COUPLE)
        self._make_mutual_positive_roommate_pair(existing_member, other_applicant)

        existing_bed = rooms[0].beds.first()
        BedAssignment.objects.create(
            student=existing_member,
            bed=existing_bed,
            status=BedAssignment.Status.ACTIVE,
            assignment_type=BedAssignment.AssignmentType.MANUAL,
        )

        result = self._run([other_applicant], rooms)
        self.assertEqual(result['successful_assignments'], 0, result['proposed_assignments'])

        existing_assignment = BedAssignment.objects.get(student=existing_member)
        self.assertEqual(existing_assignment.status, BedAssignment.Status.ACTIVE)
        self.assertEqual(existing_assignment.bed_id, existing_bed.id)

    def test_unrelated_applicant_still_rejected_when_existing_occupant_present(self):
        """
        Same setup as above (one existing couple occupant), but the new
        candidate is a couple-type applicant with NO roommate link to the
        existing occupant. They must still be rejected — any existing
        active assignment makes the exclusive apartment unavailable to
        every other applicant, unconditionally.
        """
        apartment, rooms = self._make_apartment(
            17, Apartment.ApartmentType.COUPLE, Apartment.Category.MIXED, [('A', 2)],
        )
        existing_member = self._make_student('EXIST_V3', Student.HousingType.COUPLE)
        existing_bed = rooms[0].beds.first()
        BedAssignment.objects.create(
            student=existing_member,
            bed=existing_bed,
            status=BedAssignment.Status.ACTIVE,
            assignment_type=BedAssignment.AssignmentType.MANUAL,
        )

        unrelated_applicant = self._make_student('UNRELATED_V4', Student.HousingType.COUPLE)

        result = self._run([unrelated_applicant], rooms)
        self.assertEqual(result['successful_assignments'], 0, result['proposed_assignments'])

        existing_assignment = BedAssignment.objects.get(student=existing_member)
        self.assertEqual(existing_assignment.status, BedAssignment.Status.ACTIVE)
        self.assertEqual(existing_assignment.bed_id, existing_bed.id)

    # ------------------------------------------------------------------
    # 15. Manual assignment/transfer validation enforces the same rules.
    # ------------------------------------------------------------------

    def test_manual_assignment_validation_blocks_unrelated_couple(self):
        """api.views.validate_apartment_assignment (used by manual
        assign/move/swap and Transfer approval) must reject a second
        couple-type Student record from an apartment that already has an
        existing active assignment."""
        from api.views import validate_apartment_assignment

        apartment, rooms = self._make_apartment(
            18, Apartment.ApartmentType.COUPLE, Apartment.Category.MIXED, [('A', 2)],
        )
        existing_member = self._make_student('MANUAL_EXIST', Student.HousingType.COUPLE)
        BedAssignment.objects.create(
            student=existing_member,
            bed=rooms[0].beds.first(),
            status=BedAssignment.Status.ACTIVE,
            assignment_type=BedAssignment.AssignmentType.MANUAL,
        )

        unrelated_applicant = self._make_student('MANUAL_UNRELATED', Student.HousingType.COUPLE)

        with self.assertRaises(ValueError):
            validate_apartment_assignment(unrelated_applicant, rooms[0])

    def test_manual_assignment_validation_blocks_second_record_even_with_mutual_request(self):
        """The same manual-assignment validation must REJECT a second Z3
        Student record even when it carries a mutual positive roommate
        request to the existing occupant — a roommate request is never
        grounds to admit a second application into an occupied exclusive
        apartment."""
        from api.views import validate_apartment_assignment

        apartment, rooms = self._make_apartment(
            19, Apartment.ApartmentType.COUPLE, Apartment.Category.MIXED, [('A', 2)],
        )
        existing_member = self._make_student('MANUAL_EXIST2', Student.HousingType.COUPLE)
        other_applicant = self._make_student('MANUAL_PARTNER2', Student.HousingType.COUPLE)
        self._make_mutual_positive_roommate_pair(existing_member, other_applicant)

        BedAssignment.objects.create(
            student=existing_member,
            bed=rooms[0].beds.first(),
            status=BedAssignment.Status.ACTIVE,
            assignment_type=BedAssignment.AssignmentType.MANUAL,
        )

        with self.assertRaises(ValueError):
            validate_apartment_assignment(other_applicant, rooms[0])

    def test_manual_assignment_validation_blocks_second_z6_record(self):
        """api.views.validate_apartment_assignment must reject a second Z6
        Student record from an apartment that already has an active Z6
        assignment — Z6 always requires exclusive use of the complete
        apartment, with no exception for any roommate request."""
        from api.views import validate_apartment_assignment

        apartment, rooms = self._make_apartment(
            20, Apartment.ApartmentType.COUPLE, Apartment.Category.MIXED, [('A', 2)],
        )
        existing_z6 = self._make_student('MANUAL_Z6_EXIST', Student.HousingType.SINGLE_IN_APARTMENT)
        other_z6 = self._make_student('MANUAL_Z6_OTHER', Student.HousingType.SINGLE_IN_APARTMENT)
        self._make_mutual_positive_roommate_pair(existing_z6, other_z6)

        BedAssignment.objects.create(
            student=existing_z6,
            bed=rooms[0].beds.first(),
            status=BedAssignment.Status.ACTIVE,
            assignment_type=BedAssignment.AssignmentType.MANUAL,
        )

        with self.assertRaises(ValueError):
            validate_apartment_assignment(other_z6, rooms[0])
