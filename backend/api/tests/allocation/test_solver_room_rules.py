from unittest.mock import patch

from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework import status

from api.models import (
    Region, BedAssignment, Student, DormType, Building, Apartment, Room, Bed,
)

from ._support import (
    _make_region,
    _make_central_admin,
    _make_region_boss,
    _make_employee,
)


# ---------------------------------------------------------------------------
# Reusable printing helper shared by SolverSharedFacilityRoomTest and
# SolverBuildingGenderRestrictionTest — module-level so both TestCase
# classes can call it without any inheritance relationship between them.
# Printing only; it never touches assertions or solver behavior.
# ---------------------------------------------------------------------------

def _print_gender_allocation_report(test_name, result, students, rooms):
    """
    Print a readable allocation report for building/room gender tests:
      - header: test name, solver status, totals, warnings;
      - allocation table (BUILDING | BUILDING GENDER | APARTMENT |
        APARTMENT CATEGORY | ROOM | BED | STUDENT | GENDER | RELIGION |
        SECTOR | PRIORITY), including pre-existing active occupants,
        clearly marked EXISTING versus newly persisted NEW rows;
      - a separate UNASSIGNED table (student id, gender, religion, reason
        when available).
    """
    rooms = list(rooms)
    room_ids = [room.id for room in rooms]

    proposed = result.get('proposed_assignments', []) or []
    new_bed_ids = {item['bed_id'] for item in proposed}
    assigned_student_ids = {item['student_db_id'] for item in proposed}

    active_assignments = list(
        BedAssignment.objects.filter(
            bed__room_id__in=room_ids,
            status=BedAssignment.Status.ACTIVE,
        ).select_related(
            'student',
            'bed',
            'bed__room',
            'bed__room__apartment',
            'bed__room__apartment__building',
        )
    )

    rows = []
    for assignment in active_assignments:
        bed = assignment.bed
        room = bed.room
        apartment = room.apartment
        building = apartment.building
        student = assignment.student
        row_status = 'NEW' if bed.id in new_bed_ids else 'EXISTING'
        rows.append((row_status, building, apartment, room, bed, student))

    rows.sort(
        key=lambda row: (
            str(row[1].number),
            str(row[2].number),
            str(row[3].name),
            str(row[4].label),
        )
    )

    print('\n' + '=' * 160)
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
    else:
        print('WARNINGS: none')
    print('=' * 160)

    if rows:
        print(
            f"{'STATUS':<9} {'BUILDING':<9} {'BLD.GENDER':<11} {'APARTMENT':<10} "
            f"{'APT.CAT':<8} {'ROOM':<6} {'BED':<5} {'STUDENT':<12} {'GENDER':<7} "
            f"{'RELIGION':<12} {'SECTOR':<9} {'PRIORITY':<9}"
        )
        print('-' * 160)
        for row_status, building, apartment, room, bed, student in rows:
            print(
                f"{row_status:<9} "
                f"{str(building.number):<9} "
                f"{(building.gender_restriction or '-'):<11} "
                f"{str(apartment.number):<10} "
                f"{str(apartment.category):<8} "
                f"{str(room.name):<6} "
                f"{str(bed.label):<5} "
                f"{student.student_id:<12} "
                f"{str(student.gender):<7} "
                f"{student.requested_religion:<12} "
                f"{student.placement_sector:<9} "
                f"{str(bool(student.is_priority)):<9}"
            )
    else:
        print('No assignments (new or existing).')

    no_feasible_ids = set(result.get('students_with_no_feasible_beds') or [])
    unassigned = [student for student in students if student.id not in assigned_student_ids]
    if unassigned:
        print('\nUNASSIGNED')
        print(f"{'STUDENT':<12} {'GENDER':<7} {'RELIGION':<12} {'REASON':<30}")
        print('-' * 70)
        for student in sorted(unassigned, key=lambda item: item.student_id):
            reason = 'no feasible beds' if student.id in no_feasible_ids else '-'
            print(
                f"{student.student_id:<12} {str(student.gender):<7} "
                f"{student.requested_religion:<12} {reason:<30}"
            )

    print('=' * 160 + '\n')


# ---------------------------------------------------------------------------
# Shared-facility dorm buildings: rooms with capacity 2 (two students per
# room), apartments that may contain several such rooms.
# ---------------------------------------------------------------------------

class SolverSharedFacilityRoomTest(TestCase):
    """
    Focused tests for shared-facility dorm buildings where each physical
    room holds two students (Room.capacity=2, two distinct Bed records),
    and an apartment may contain several such rooms sharing one apartment/
    kitchen (see allocation/solver.py: _apartment_uses_room_pairing,
    _build_candidate_rooms, and the room_assignment_vars layer in
    run_improved_ortools_allocation).

    Gender/building designation is read dynamically from the existing
    Apartment.category field (MALE/FEMALE/MIXED) — there is no separate
    Building-level gender field in this codebase — via the existing
    _housing_matches_apartment check; nothing here hard-codes a building
    number for that purpose.

    For apartments containing exactly one room, or several 1-bed rooms,
    behavior is completely unchanged (that is the existing, unmodified
    apartment-level architecture already covered by every other test class
    in this module) — see test 9 below.
    """

    def setUp(self):
        patcher = patch('allocation.solver.close_old_connections')
        patcher.start()
        self.addCleanup(patcher.stop)

        self.region = Region.objects.create(id='shared_facility_region', name='Shared Facility Region')
        self.dorm_type = DormType.objects.create(name='SharedFacilityDorm', region=self.region)
        self.building = Building.objects.create(number=201, dorm_type=self.dorm_type)

    # ------------------------------------------------------------------
    # Infrastructure helpers
    # ------------------------------------------------------------------

    def _make_apartment(self, number, category=Apartment.Category.FEMALE, building=None):
        return Apartment.objects.create(
            building=building or self.building,
            number=number,
            category=category,
            apartment_type=Apartment.ApartmentType.SINGLE,
            room_count=0,
            is_active=True,
        )

    def _make_room(self, apartment, name, capacity=2):
        room = Room.objects.create(apartment=apartment, name=name, capacity=capacity)
        for index in range(capacity):
            Bed.objects.create(room=room, label=str(index + 1))
        return room

    def _make_student(
        self,
        student_id,
        *,
        gender=Student.Gender.FEMALE,
        religion=Student.Religion.NOT_SPECIFIED,
        religious=Student.Religious.NOT_SPECIFIED,
    ):
        housing_type = (
            Student.HousingType.SINGLE_MALE
            if gender == Student.Gender.MALE
            else Student.HousingType.SINGLE_FEMALE
        )
        return Student.objects.create(
            student_id=student_id,
            first_name='Test',
            last_name=student_id,
            gender=gender,
            housing_type=housing_type,
            requested_religion=religion,
            religious=religious,
        )

    def _fill_room_with_existing_occupants(self, room, count=None):
        """Occupy `count` (default: room.capacity) beds with unrelated existing students."""
        count = room.capacity if count is None else count
        beds = list(room.beds.all())[:count]
        for index, bed in enumerate(beds):
            occupant = self._make_student(f'EXIST_{room.id}_{index}')
            BedAssignment.objects.create(
                student=occupant,
                bed=bed,
                status=BedAssignment.Status.ACTIVE,
                assignment_type=BedAssignment.AssignmentType.MANUAL,
            )

    def _make_mutual_positive_roommate_pair(self, student_1, student_2):
        student_1.roommate_request_student_id_1 = student_2.student_id
        student_1.roommate_request_flag_1 = True
        student_1.save(update_fields=['roommate_request_student_id_1', 'roommate_request_flag_1'])

        student_2.roommate_request_student_id_1 = student_1.student_id
        student_2.roommate_request_flag_1 = True
        student_2.save(update_fields=['roommate_request_student_id_1', 'roommate_request_flag_1'])

    HARD_CONFIG = {
        'sameGender': {'enabled': True, 'strict': True, 'critical': True, 'weight': 0},
        'ReligiousTogether': {'enabled': True, 'strict': True, 'critical': True, 'weight': 0},
        'roommatePositiveOnly': {'enabled': True, 'strict': True, 'critical': True, 'weight': 0},
        'priorityFirst': {'enabled': False},
        'sameReligion': {'enabled': False},
        'roommateMatch': {'enabled': False},
        'sectorMatching': {'enabled': False},
        'avoidYearMix_1_with_3_4': {'enabled': False},
        'avoidAtudaimWithHasmaha': {'enabled': False},
    }

    def _resolve_assignment_location(self, assignment):
        bed = Bed.objects.select_related(
            'room', 'room__apartment', 'room__apartment__building',
        ).get(id=assignment['bed_id'])
        return bed.room.apartment, bed.room, bed

    def _run(self, students, rooms, config=None):
        import inspect
        from allocation.solver import run_improved_ortools_allocation

        test_name = inspect.stack()[1].function
        students = list(students)
        rooms = list(rooms)

        result = run_improved_ortools_allocation(
            students,
            rooms,
            config or self.HARD_CONFIG,
        )

        _print_gender_allocation_report(test_name, result, students, rooms)
        return result

    def _room_of(self, result, student):
        for assignment in result.get('proposed_assignments', []):
            if assignment['student_db_id'] == student.id:
                _, room, _ = self._resolve_assignment_location(assignment)
                return room
        return None

    # ------------------------------------------------------------------
    # 1. Two compatible students share one room.
    # ------------------------------------------------------------------

    def test_two_compatible_students_share_one_room(self):
        """
        Two mutually-compatible students are both assigned into the same
        2-bed room of a shared-facility apartment, using two distinct beds.
        """
        apartment = self._make_apartment('SF1')
        room_a = self._make_room(apartment, 'A', capacity=2)
        room_b = self._make_room(apartment, 'B', capacity=2)
        self._fill_room_with_existing_occupants(room_b)  # only room A has space

        s1 = self._make_student('RM1')
        s2 = self._make_student('RM2')

        result = self._run([s1, s2], [room_a, room_b])
        self.assertEqual(result['successful_assignments'], 2, result['proposed_assignments'])

        room_1 = self._room_of(result, s1)
        room_2 = self._room_of(result, s2)
        self.assertEqual(room_1.id, room_a.id)
        self.assertEqual(room_2.id, room_a.id)

        beds = {a['bed_id'] for a in result['proposed_assignments']}
        self.assertEqual(len(beds), 2, 'Each student must use a distinct bed.')

    # ------------------------------------------------------------------
    # 2. A third student is rejected from the full room.
    # ------------------------------------------------------------------

    def test_third_student_rejected_from_full_room(self):
        """
        With only one 2-bed room available (the apartment's other room is
        already full), a third compatible student cannot be squeezed in
        and must remain unassigned rather than exceed room capacity.
        """
        apartment = self._make_apartment('SF2')
        room_a = self._make_room(apartment, 'A', capacity=2)
        room_b = self._make_room(apartment, 'B', capacity=2)
        self._fill_room_with_existing_occupants(room_b)

        s1 = self._make_student('TH1')
        s2 = self._make_student('TH2')
        s3 = self._make_student('TH3')

        result = self._run([s1, s2, s3], [room_a, room_b])
        self.assertEqual(result['successful_assignments'], 2, result['proposed_assignments'])

        assigned_ids = {a['student_db_id'] for a in result['proposed_assignments']}
        self.assertEqual(len(assigned_ids & {s1.id, s2.id, s3.id}), 2)
        unassigned_id = ({s1.id, s2.id, s3.id} - assigned_ids).pop()
        self.assertNotIn(unassigned_id, assigned_ids)

    # ------------------------------------------------------------------
    # 3. An existing Religious-Jewish occupant restricts the whole
    #    shared-facility apartment.
    # ------------------------------------------------------------------

    def test_existing_rj_occupant_restricts_whole_shared_facility_apartment(self):
        """
        Room A already has one Religious-Jewish occupant (one free bed);
        Room B is completely empty (two free beds) in the same apartment.
        Religious compatibility applies to the WHOLE shared-facility
        apartment, because its bedrooms share a kitchen and common space:
        a new Religious-Jewish candidate may join the apartment, but a new
        Muslim (no-preference) candidate may not enter it at all — not even
        the empty Room B — and remains unassigned with no feasible beds.
        """
        apartment = self._make_apartment('SF3')
        room_a = self._make_room(apartment, 'A', capacity=2)
        room_b = self._make_room(apartment, 'B', capacity=2)

        existing_rj = self._make_student(
            'EXRJ', religion=Student.Religion.Jewish, religious=Student.Religious.RELIGIOUS,
        )
        BedAssignment.objects.create(
            student=existing_rj,
            bed=room_a.beds.first(),
            status=BedAssignment.Status.ACTIVE,
            assignment_type=BedAssignment.AssignmentType.MANUAL,
        )

        new_rj = self._make_student(
            'NEWRJ', religion=Student.Religion.Jewish, religious=Student.Religious.RELIGIOUS,
        )
        new_muslim = self._make_student(
            'NEWMU', religion=Student.Religion.Muslim, religious=Student.Religious.NO_PREFERENCE,
        )

        result = self._run([new_rj, new_muslim], [room_a, room_b])
        self.assertEqual(result['successful_assignments'], 1, result['proposed_assignments'])

        # HARD_CONFIG's objective does not distinguish Room A from Room B
        # for the new RJ student; Room A is the solver's stable choice.
        self.assertEqual(self._room_of(result, new_rj).id, room_a.id)
        self.assertIsNone(self._room_of(result, new_muslim))
        self.assertIn(new_muslim.id, result['students_with_no_feasible_beds'])

    # ------------------------------------------------------------------
    # 4. Incompatible students do not share a room.
    # ------------------------------------------------------------------

    def test_incompatible_students_do_not_share_room(self):
        """
        A Religious-Jewish and a Religious-Muslim student cannot both be
        placed when the only capacity available is two beds in the SAME
        room: the hard ReligiousTogether rule must block them from sharing
        it, so at most one of them is assigned — never both, in violation
        of the rule.
        """
        apartment = self._make_apartment('SF4')
        room_a = self._make_room(apartment, 'A', capacity=2)
        room_b = self._make_room(apartment, 'B', capacity=2)
        self._fill_room_with_existing_occupants(room_b)  # only room A has space

        rj = self._make_student(
            'INCRJ', religion=Student.Religion.Jewish, religious=Student.Religious.RELIGIOUS,
        )
        muslim = self._make_student(
            'INCMU', religion=Student.Religion.Muslim, religious=Student.Religious.RELIGIOUS,
        )

        result = self._run([rj, muslim], [room_a, room_b])
        self.assertEqual(
            result['successful_assignments'], 1, result['proposed_assignments'],
        )

        assigned_ids = {a['student_db_id'] for a in result['proposed_assignments']}
        self.assertEqual(len(assigned_ids & {rj.id, muslim.id}), 1)

    # ------------------------------------------------------------------
    # 5. Mutual roommate requests produce the same room.
    # ------------------------------------------------------------------

    def test_mutual_roommate_request_produces_same_room(self):
        """Two students with a hard mutual positive roommate request end up
        in the SAME physical room, not merely the same apartment."""
        apartment = self._make_apartment('SF5')
        room_a = self._make_room(apartment, 'A', capacity=2)
        room_b = self._make_room(apartment, 'B', capacity=2)

        s1 = self._make_student('MR1')
        s2 = self._make_student('MR2')
        self._make_mutual_positive_roommate_pair(s1, s2)

        result = self._run([s1, s2], [room_a, room_b])
        self.assertEqual(result['successful_assignments'], 2, result['proposed_assignments'])

        room_1 = self._room_of(result, s1)
        room_2 = self._room_of(result, s2)
        self.assertEqual(room_1.id, room_2.id)

    # ------------------------------------------------------------------
    # 6. Female/male building (apartment) restriction.
    # ------------------------------------------------------------------

    def test_female_male_apartment_restriction(self):
        """A female student and a male student are each restricted to the
        gender-matching apartment, read dynamically from Apartment.category
        — no building number is hard-coded for this."""
        female_apartment = self._make_apartment('SFF', category=Apartment.Category.FEMALE)
        male_apartment = self._make_apartment('SFM', category=Apartment.Category.MALE)
        female_room = self._make_room(female_apartment, 'A', capacity=2)
        male_room = self._make_room(male_apartment, 'A', capacity=2)

        female_student = self._make_student('GF1', gender=Student.Gender.FEMALE)
        male_student = self._make_student('GM1', gender=Student.Gender.MALE)

        result = self._run([female_student, male_student], [female_room, male_room])
        self.assertEqual(result['successful_assignments'], 2, result['proposed_assignments'])

        self.assertEqual(
            self._resolve_assignment_location(
                next(a for a in result['proposed_assignments'] if a['student_db_id'] == female_student.id)
            )[0].id,
            female_apartment.id,
        )
        self.assertEqual(
            self._resolve_assignment_location(
                next(a for a in result['proposed_assignments'] if a['student_db_id'] == male_student.id)
            )[0].id,
            male_apartment.id,
        )

    # ------------------------------------------------------------------
    # 7. Changing the building/apartment designation later.
    # ------------------------------------------------------------------

    def test_changing_apartment_gender_designation_takes_effect(self):
        """
        A male student cannot enter a FEMALE-designated apartment. After
        staff change that apartment's category to MALE in the database, a
        fresh solver run for the same male student succeeds — proving the
        designation is read fresh from the database every run, not cached
        or hard-coded by building number.
        """
        apartment = self._make_apartment('SF7', category=Apartment.Category.FEMALE)
        room = self._make_room(apartment, 'A', capacity=2)
        second_room = self._make_room(apartment, 'B', capacity=2)

        male_student = self._make_student('DESG1', gender=Student.Gender.MALE)

        result_before = self._run([male_student], [room, second_room])
        self.assertEqual(result_before['successful_assignments'], 0, result_before['proposed_assignments'])

        apartment.category = Apartment.Category.MALE
        apartment.save(update_fields=['category'])

        result_after = self._run([male_student], [room, second_room])
        self.assertEqual(result_after['successful_assignments'], 1, result_after['proposed_assignments'])

    # ------------------------------------------------------------------
    # 8. Unique-bed persistence.
    # ------------------------------------------------------------------

    def test_unique_bed_persistence(self):
        """Four students filling a 2-room/4-bed shared-facility apartment
        each persist to a distinct, real Bed row — no bed is reused."""
        apartment = self._make_apartment('SF8')
        room_a = self._make_room(apartment, 'A', capacity=2)
        room_b = self._make_room(apartment, 'B', capacity=2)

        students = [self._make_student(f'UB{i}') for i in range(1, 5)]

        result = self._run(students, [room_a, room_b])
        self.assertEqual(result['successful_assignments'], 4, result['proposed_assignments'])

        bed_ids = [a['bed_id'] for a in result['proposed_assignments']]
        self.assertEqual(len(bed_ids), len(set(bed_ids)), 'Every bed must be used at most once.')

        for student in students:
            assignment = BedAssignment.objects.get(student=student, status=BedAssignment.Status.ACTIVE)
            self.assertIn(assignment.bed_id, bed_ids)

    # ------------------------------------------------------------------
    # 9. Existing one-student-per-room dorms remain unaffected.
    # ------------------------------------------------------------------

    def test_existing_one_per_room_dorm_unaffected(self):
        """
        An ordinary apartment built from several 1-bed rooms (the existing,
        already-tested architecture) is NOT treated as room-pairing: an
        existing Religious-Jewish occupant in one of its 1-bed rooms still
        blocks an incompatible newcomer from the WHOLE apartment (the
        apartment-level ReligiousTogether behavior, which shared-facility
        apartments share — see test 3 above).
        """
        from allocation.solver import _apartment_uses_room_pairing, _rooms_by_apartment_id

        apartment = self._make_apartment('SF9')
        rooms = [self._make_room(apartment, f'R{i}', capacity=1) for i in range(1, 4)]

        existing_rj = self._make_student(
            'OLDRJ', religion=Student.Religion.Jewish, religious=Student.Religious.RELIGIOUS,
        )
        BedAssignment.objects.create(
            student=existing_rj,
            bed=rooms[0].beds.first(),
            status=BedAssignment.Status.ACTIVE,
            assignment_type=BedAssignment.AssignmentType.MANUAL,
        )

        rooms_by_apartment = _rooms_by_apartment_id(rooms)
        self.assertFalse(
            _apartment_uses_room_pairing(apartment.id, rooms_by_apartment),
            'A 1-bed-room-per-room apartment must not be treated as room-pairing.',
        )

        new_rj = self._make_student(
            'NEWOLDRJ', religion=Student.Religion.Jewish, religious=Student.Religious.RELIGIOUS,
        )
        new_muslim = self._make_student(
            'NEWOLDMU', religion=Student.Religion.Muslim, religious=Student.Religious.NO_PREFERENCE,
        )

        result = self._run([new_rj, new_muslim], rooms)
        self.assertEqual(result['successful_assignments'], 1, result['proposed_assignments'])

        assigned_ids = {a['student_db_id'] for a in result['proposed_assignments']}
        self.assertIn(new_rj.id, assigned_ids)
        self.assertNotIn(
            new_muslim.id, assigned_ids,
            'The pre-existing apartment-level ReligiousTogether rule must '
            'still block the whole apartment for 1-bed-room dorms.',
        )


# ---------------------------------------------------------------------------
# Building-level gender restriction (shared-facility buildings with shared
# bathrooms: the whole building must be single-gender, not just individual
# apartments).
# ---------------------------------------------------------------------------

class SolverBuildingGenderRestrictionTest(TestCase):
    """
    Focused tests for Building.gender_restriction.

    Apartment.category (male/female/mixed) remains an apartment-level
    attribute and is NOT itself a building-level gender designation — a
    building can, by data error or a genuine mixed-apartment layout,
    contain apartments with conflicting categories. For shared-facility
    buildings (shared bathrooms), the whole BUILDING must still be
    restricted to one gender regardless of what any individual apartment's
    category says. Building.gender_restriction ('male'/'female'/blank) is
    the hard, building-wide override; blank preserves today's existing
    apartment-category-only behavior for ordinary buildings.
    """

    def setUp(self):
        patcher = patch('allocation.solver.close_old_connections')
        patcher.start()
        self.addCleanup(patcher.stop)

        self.region = Region.objects.create(id='gender_bldg_region', name='Gender Building Region')
        self.dorm_type = DormType.objects.create(name='GenderBuildingDorm', region=self.region)

    def _make_room(self, apartment, name, capacity=2):
        room = Room.objects.create(apartment=apartment, name=name, capacity=capacity)
        for index in range(capacity):
            Bed.objects.create(room=room, label=str(index + 1))
        return room

    def _make_student(self, student_id, gender):
        housing_type = (
            Student.HousingType.SINGLE_MALE
            if gender == Student.Gender.MALE
            else Student.HousingType.SINGLE_FEMALE
        )
        return Student.objects.create(
            student_id=student_id,
            first_name='Test',
            last_name=student_id,
            gender=gender,
            housing_type=housing_type,
        )

    CONFIG = {
        'sameGender': {'enabled': True, 'strict': True, 'critical': True, 'weight': 0},
        'priorityFirst': {'enabled': False},
        'ReligiousTogether': {'enabled': False},
        'roommatePositiveOnly': {'enabled': False},
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

        _print_gender_allocation_report(test_name, result, students, rooms)
        return result

    # ------------------------------------------------------------------
    # 1. Building-level restriction overrides conflicting apartment
    #    categories: male and female students can never be allocated
    #    anywhere in the same restricted building.
    # ------------------------------------------------------------------

    def test_building_restriction_overrides_conflicting_apartment_categories(self):
        """
        One shared-facility building holds two apartments with CONFLICTING
        categories (one FEMALE, one MALE), but the building itself is
        restricted to female only. A male student must be rejected from
        BOTH apartments — even the one nominally marked MALE — because the
        building-level restriction is authoritative for shared-facility
        buildings. A female student is still assigned normally.
        """
        building = Building.objects.create(
            number=301,
            dorm_type=self.dorm_type,
            gender_restriction=Building.GenderRestriction.FEMALE,
        )
        female_apartment = Apartment.objects.create(
            building=building, number='F1', category=Apartment.Category.FEMALE,
            apartment_type=Apartment.ApartmentType.SINGLE, room_count=1,
        )
        # Mislabeled/conflicting apartment: category says MALE, but the
        # building as a whole is female-only.
        conflicting_apartment = Apartment.objects.create(
            building=building, number='M1', category=Apartment.Category.MALE,
            apartment_type=Apartment.ApartmentType.SINGLE, room_count=1,
        )
        room_f = self._make_room(female_apartment, 'A', capacity=2)
        room_m = self._make_room(conflicting_apartment, 'A', capacity=2)

        male_student = self._make_student('BGM1', Student.Gender.MALE)
        female_student = self._make_student('BGF1', Student.Gender.FEMALE)

        result = self._run([male_student, female_student], [room_f, room_m])

        assigned_ids = {a['student_db_id'] for a in result['proposed_assignments']}
        self.assertIn(female_student.id, assigned_ids)
        self.assertNotIn(
            male_student.id,
            assigned_ids,
            'A male student must never be assigned anywhere in a '
            'female-restricted building, even an apartment marked MALE.',
        )

        # Confirm across every room actually persisted in this building —
        # not merely the one apartment a naive apartment-only check might
        # have looked at.
        for assignment in result['proposed_assignments']:
            bed = Bed.objects.select_related(
                'room__apartment__building',
            ).get(id=assignment['bed_id'])
            self.assertEqual(bed.room.apartment.building_id, building.id)
            student = Student.objects.get(id=assignment['student_db_id'])
            self.assertEqual(student.gender, Student.Gender.FEMALE)

    # ------------------------------------------------------------------
    # 2. Ordinary buildings without a restriction keep the existing
    #    apartment-category-only behavior.
    # ------------------------------------------------------------------

    def test_ordinary_building_without_restriction_uses_apartment_category(self):
        """
        A building with NO gender_restriction (blank, the default) behaves
        exactly as before: each student follows their own apartment's
        category, and a mixed building (one FEMALE apartment, one MALE
        apartment) still allocates both genders successfully.
        """
        building = Building.objects.create(number=302, dorm_type=self.dorm_type)
        self.assertEqual(building.gender_restriction, '')

        female_apartment = Apartment.objects.create(
            building=building, number='F1', category=Apartment.Category.FEMALE,
            apartment_type=Apartment.ApartmentType.SINGLE, room_count=1,
        )
        male_apartment = Apartment.objects.create(
            building=building, number='M1', category=Apartment.Category.MALE,
            apartment_type=Apartment.ApartmentType.SINGLE, room_count=1,
        )
        room_f = self._make_room(female_apartment, 'A', capacity=2)
        room_m = self._make_room(male_apartment, 'A', capacity=2)

        male_student = self._make_student('OGM1', Student.Gender.MALE)
        female_student = self._make_student('OGF1', Student.Gender.FEMALE)

        result = self._run([male_student, female_student], [room_f, room_m])
        self.assertEqual(result['successful_assignments'], 2, result['proposed_assignments'])

        assignments_by_student = {
            a['student_db_id']: a for a in result['proposed_assignments']
        }
        male_bed = Bed.objects.select_related('room__apartment').get(
            id=assignments_by_student[male_student.id]['bed_id']
        )
        female_bed = Bed.objects.select_related('room__apartment').get(
            id=assignments_by_student[female_student.id]['bed_id']
        )
        self.assertEqual(male_bed.room.apartment_id, male_apartment.id)
        self.assertEqual(female_bed.room.apartment_id, female_apartment.id)

    # ------------------------------------------------------------------
    # 3. A building's ONLY apartment is mislabeled (wrong category); the
    #    building restriction must still correct it.
    # ------------------------------------------------------------------

    def test_single_mislabeled_apartment_building_restriction_overrides_category(self):
        """
        A female-restricted building has only one apartment, incorrectly
        marked MALE. A female student must still be assigned there (the
        building-level restriction corrects the wrong apartment category),
        while a male student is rejected.
        """
        building = Building.objects.create(
            number=303,
            dorm_type=self.dorm_type,
            gender_restriction=Building.GenderRestriction.FEMALE,
        )
        mislabeled_apartment = Apartment.objects.create(
            building=building, number='1', category=Apartment.Category.MALE,
            apartment_type=Apartment.ApartmentType.SINGLE, room_count=1,
        )
        room = self._make_room(mislabeled_apartment, 'A', capacity=2)

        female_student = self._make_student('SOLO_F', Student.Gender.FEMALE)
        male_student = self._make_student('SOLO_M', Student.Gender.MALE)

        result = self._run([female_student, male_student], [room])

        assigned_ids = {a['student_db_id'] for a in result['proposed_assignments']}
        self.assertIn(
            female_student.id, assigned_ids,
            'A female student must be assigned even though the only '
            "apartment's own category says MALE.",
        )
        self.assertNotIn(male_student.id, assigned_ids)

    # ------------------------------------------------------------------
    # 4. Existing occupants: preserved unchanged, block new opposite-
    #    gender students, and surface a clear warning.
    # ------------------------------------------------------------------

    def test_conflicting_existing_occupant_freezes_building_female_restriction(self):
        """
        A building already has an active MALE occupant from before any
        restriction existed. After the building becomes FEMALE-restricted:
          - the existing male occupant's active assignment is preserved
            exactly as-is (never modified);
          - a new MALE candidate is NOT added;
          - a new FEMALE candidate is ALSO not added — a matching-gender
            addition would not fix an already-mixed building, so the whole
            building is frozen for new assignments until staff resolve
            the inconsistency manually;
          - a clear warning about the conflicting existing occupant/frozen
            building is returned.
        """
        building = Building.objects.create(number=304, dorm_type=self.dorm_type)
        apartment = Apartment.objects.create(
            building=building, number='1', category=Apartment.Category.MALE,
            apartment_type=Apartment.ApartmentType.SINGLE, room_count=1,
        )
        room = self._make_room(apartment, 'A', capacity=2)

        legacy_male = self._make_student('LEGACY_M', Student.Gender.MALE)
        legacy_bed = room.beds.first()
        BedAssignment.objects.create(
            student=legacy_male,
            bed=legacy_bed,
            status=BedAssignment.Status.ACTIVE,
            assignment_type=BedAssignment.AssignmentType.MANUAL,
        )

        # The building becomes female-restricted after the fact.
        building.gender_restriction = Building.GenderRestriction.FEMALE
        building.save(update_fields=['gender_restriction'])

        new_male = self._make_student('NEW_M', Student.Gender.MALE)
        new_female = self._make_student('NEW_F', Student.Gender.FEMALE)

        result = self._run([new_male, new_female], [room])

        legacy_assignment = BedAssignment.objects.get(student=legacy_male)
        self.assertEqual(legacy_assignment.status, BedAssignment.Status.ACTIVE)
        self.assertEqual(legacy_assignment.bed_id, legacy_bed.id)

        assigned_ids = {a['student_db_id'] for a in result['proposed_assignments']}
        self.assertNotIn(
            new_male.id, assigned_ids,
            'No new opposite-gender student may be added once the '
            'building is restricted, even though a legacy occupant of '
            'that gender is already grandfathered in.',
        )
        self.assertNotIn(
            new_female.id, assigned_ids,
            'A conflicting existing occupant must freeze the WHOLE '
            'building for new assignments, including matching-gender '
            'candidates — adding them would not fix an already-mixed '
            'building.',
        )

        self.assertTrue(
            any(
                'restricted to' in warning and 'LEGACY_M' in warning and 'frozen' in warning
                for warning in result['warnings']
            ),
            f"Expected a conflicting-existing-occupant/frozen-building warning, got: {result['warnings']}",
        )

    def test_conflicting_existing_occupant_freezes_building_male_restriction(self):
        """
        Symmetric case: a building already has an active FEMALE occupant.
        After the building becomes MALE-restricted:
          - the existing female occupant's active assignment is preserved
            exactly as-is (never modified);
          - a new MALE candidate (matching the restriction) is NOT added —
            the building is frozen entirely because of the conflict;
          - a clear warning is returned.
        """
        building = Building.objects.create(number=306, dorm_type=self.dorm_type)
        apartment = Apartment.objects.create(
            building=building, number='1', category=Apartment.Category.FEMALE,
            apartment_type=Apartment.ApartmentType.SINGLE, room_count=1,
        )
        room = self._make_room(apartment, 'A', capacity=2)

        legacy_female = self._make_student('LEGACY_F', Student.Gender.FEMALE)
        legacy_bed = room.beds.first()
        BedAssignment.objects.create(
            student=legacy_female,
            bed=legacy_bed,
            status=BedAssignment.Status.ACTIVE,
            assignment_type=BedAssignment.AssignmentType.MANUAL,
        )

        # The building becomes male-restricted after the fact.
        building.gender_restriction = Building.GenderRestriction.MALE
        building.save(update_fields=['gender_restriction'])

        new_male = self._make_student('NEW_M2', Student.Gender.MALE)

        result = self._run([new_male], [room])

        legacy_assignment = BedAssignment.objects.get(student=legacy_female)
        self.assertEqual(legacy_assignment.status, BedAssignment.Status.ACTIVE)
        self.assertEqual(legacy_assignment.bed_id, legacy_bed.id)

        assigned_ids = {a['student_db_id'] for a in result['proposed_assignments']}
        self.assertNotIn(
            new_male.id, assigned_ids,
            'A male candidate must not be added to a male-restricted '
            'building that already has a conflicting existing female '
            'occupant — that would create a mixed-gender shared-facility '
            'building.',
        )

        self.assertTrue(
            any(
                'restricted to' in warning and 'LEGACY_F' in warning and 'frozen' in warning
                for warning in result['warnings']
            ),
            f"Expected a conflicting-existing-occupant/frozen-building warning, got: {result['warnings']}",
        )

    # ------------------------------------------------------------------
    # 5. Changing gender_restriction affects the very next solver run.
    # ------------------------------------------------------------------

    def test_changing_gender_restriction_affects_next_run(self):
        """Changing Building.gender_restriction takes effect immediately
        on the next solver run — read fresh from the database, never
        cached or hard-coded by building number."""
        building = Building.objects.create(number=305, dorm_type=self.dorm_type)
        apartment = Apartment.objects.create(
            building=building, number='1', category=Apartment.Category.MALE,
            apartment_type=Apartment.ApartmentType.SINGLE, room_count=1,
        )
        room = self._make_room(apartment, 'A', capacity=2)

        female_student = self._make_student('DYN_F', Student.Gender.FEMALE)

        result_before = self._run([female_student], [room])
        self.assertEqual(
            result_before['successful_assignments'], 0, result_before['proposed_assignments'],
        )

        building.gender_restriction = Building.GenderRestriction.FEMALE
        building.save(update_fields=['gender_restriction'])

        result_after = self._run([female_student], [room])
        self.assertEqual(
            result_after['successful_assignments'], 1, result_after['proposed_assignments'],
        )


# ---------------------------------------------------------------------------
# API permissions for editing Building.gender_restriction.
# ---------------------------------------------------------------------------

def _print_permission_check_row(test_name, user, requested_value, response, building):
    """Reusable printing helper for building-permission API tests: prints
    TEST | USER ROLE | REGION | REQUESTED VALUE | HTTP STATUS | SAVED VALUE."""
    building.refresh_from_db()
    print('\n' + '-' * 115)
    print(
        f"{'TEST':<50} {'USER ROLE':<14} {'REGION':<14} "
        f"{'REQUESTED':<12} {'HTTP STATUS':<12} {'SAVED VALUE':<12}"
    )
    print('-' * 115)
    print(
        f"{test_name:<50} {user.role:<14} {(user.region_id or '-'):<14} "
        f"{str(requested_value):<12} {response.status_code:<12} "
        f"{(building.gender_restriction or '-'):<12}"
    )
    print('-' * 115 + '\n')


class BuildingGenderRestrictionPermissionTest(TestCase):
    """
    Editing a building (e.g. gender_restriction) via BuildingViewSet is a
    boss-level action (see BuildingViewSet.update in api/views.py):
      - an ordinary employee -> 403, regardless of region;
      - a region_boss of the SAME region as the building -> allowed;
      - a region_boss of a DIFFERENT region -> 403 or 404 (the building
        is outside their scoped queryset, so DRF's get_object() 404s);
      - a central_admin -> allowed, regardless of region.
    """

    def setUp(self):
        self.region = _make_region('Perm Region A')
        self.other_region = _make_region('Perm Region B')
        self.dorm_type = DormType.objects.create(name='PermDorm', region=self.region)
        self.building = Building.objects.create(number=401, dorm_type=self.dorm_type)

        self.employee = _make_employee(self.region, email='perm_emp@test.com')
        self.boss = _make_region_boss(self.region, email='perm_boss@test.com')
        self.other_boss = _make_region_boss(self.other_region, email='perm_other_boss@test.com')
        self.admin = _make_central_admin(email='perm_admin@test.com')

    def _patch_gender_restriction(self, user):
        import inspect

        test_name = inspect.stack()[1].function
        requested_value = Building.GenderRestriction.FEMALE

        client = APIClient()
        client.force_authenticate(user=user)
        response = client.patch(
            f'/api/buildings/{self.building.id}/',
            {'gender_restriction': requested_value},
            format='json',
        )

        _print_permission_check_row(test_name, user, requested_value, response, self.building)
        return response

    def test_employee_forbidden(self):
        """An ordinary employee cannot change gender_restriction."""
        response = self._patch_gender_restriction(self.employee)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_region_boss_own_region_allowed(self):
        """A region_boss may change gender_restriction for a building in
        their own region."""
        response = self._patch_gender_restriction(self.boss)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.building.refresh_from_db()
        self.assertEqual(self.building.gender_restriction, Building.GenderRestriction.FEMALE)

    def test_region_boss_other_region_forbidden_or_not_found(self):
        """A region_boss from a different region cannot change this
        building's gender_restriction."""
        response = self._patch_gender_restriction(self.other_boss)
        self.assertIn(
            response.status_code,
            (status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND),
        )
        self.building.refresh_from_db()
        self.assertEqual(self.building.gender_restriction, '')

    def test_central_admin_allowed(self):
        """A central_admin may change gender_restriction for any building,
        regardless of region."""
        response = self._patch_gender_restriction(self.admin)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.building.refresh_from_db()
        self.assertEqual(self.building.gender_restriction, Building.GenderRestriction.FEMALE)
