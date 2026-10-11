from unittest.mock import patch

from django.test import TestCase

from api.models import (
    BedAssignment, Student, DormType, Building, Apartment, Room, Bed,
)


# ---------------------------------------------------------------------------
# Solver regression tests — religious-Jewish isolation rule + accessibility
# ---------------------------------------------------------------------------

class SolverReligiousJewishRuleTest(TestCase):
    """
    Regression tests for the hard ReligiousTogether rule.

    The rule is per-religion and bidirectional:

    1. A RELIGIOUS student of religion R restricts their apartment to students of
       religion R only — with one extra condition for Jewish:
         • Religious Jewish (RJ): only Jewish+RELIGIOUS students may share.
         • Religious Muslim/Christian/Druze: any student of the same religion
           (any observance level) may share.

    2. Non-RELIGIOUS students have no restriction of their own but must comply
       with any RELIGIOUS occupant's restriction.

    3. An apartment with only non-RELIGIOUS students has no religion restriction.
       Any mix of unrestricted students may share.

    4. Two RELIGIOUS students of different religions are always incompatible.
    """

    HARD_RELIGIOUS_CONFIG = {
        "ReligiousTogether": {"enabled": True, "strict": True},
        "sameReligion": {"enabled": False},
        "sectorMatching": {"enabled": False},
        "roommateMatch": {"enabled": False},
        "roommatePositiveOnly": {"enabled": False},
        "avoidYearMix_1_with_3_4": {"enabled": False},
        "avoidAtudaimWithHasmaha": {"enabled": False},
        "priorityFirst": {"enabled": False},
    }

    def setUp(self):
        patcher = patch('allocation.solver.close_old_connections')
        patcher.start()
        self.addCleanup(patcher.stop)

    def _make_infra(self, beds_per_apt=2, num_apts=1):
        dorm = DormType.objects.create(name='TestDorm')
        building = Building.objects.create(number=1, dorm_type=dorm)
        rooms = []
        for i in range(num_apts):
            apt = Apartment.objects.create(
                building=building,
                number=str(i + 1),
                category=Apartment.Category.FEMALE,
                apartment_type=Apartment.ApartmentType.SINGLE,
                room_count=1,
            )
            room = Room.objects.create(apartment=apt, name='A', capacity=beds_per_apt)
            for j in range(beds_per_apt):
                Bed.objects.create(room=room, label=str(j + 1))
            rooms.append(room)
        return rooms

    def _make_student(self, student_id, religion, religious):
        return Student.objects.create(
            student_id=student_id,
            first_name='Test',
            last_name=student_id,
            housing_type=Student.HousingType.SINGLE_FEMALE,
            requested_religion=religion,
            religious=religious,
        )

    def _run(self, students, rooms, config=None):
        import inspect
        from collections import defaultdict
        from allocation.solver import run_improved_ortools_allocation

        test_name = inspect.stack()[1].function
        students = list(students)
        rooms = list(rooms)

        result = run_improved_ortools_allocation(
            students,
            rooms,
            config or self.HARD_RELIGIOUS_CONFIG,
        )

        assignments = result.get("proposed_assignments", [])
        assigned_ids = {item["student_db_id"] for item in assignments}
        by_apartment = defaultdict(list)
        for item in assignments:
            by_apartment[item["apartment_id"]].append(item)

        print("\n" + "=" * 110)
        print(f"TEST: {test_name}")
        print(
            f"status={result.get('solver_status')} | "
            f"students={len(students)} | "
            f"assigned={result.get('successful_assignments', 0)} | "
            f"conflicts={result.get('conflicts', 0)}"
        )
        print("=" * 110)

        if assignments:
            print(
                f"{'APT':<8} {'ROOM':<8} {'BED':<8} {'STUDENT':<12} "
                f"{'RELIGION':<15} {'RELIGIOUS':<16} {'PRIORITY':<9}"
            )
            print("-" * 110)

            for apartment_id in sorted(by_apartment):
                apartment = Apartment.objects.get(id=apartment_id)
                apartment_rows = sorted(
                    by_apartment[apartment_id],
                    key=lambda row: (
                        str(row.get("room_name", "")),
                        str(row.get("bed_label", "")),
                        row["student_db_id"],
                    ),
                )

                for row in apartment_rows:
                    student = Student.objects.get(id=row["student_db_id"])
                    print(
                        f"{apartment.number:<8} "
                        f"{str(row.get('room_name', '')):<8} "
                        f"{str(row.get('bed_label', '')):<8} "
                        f"{student.student_id:<12} "
                        f"{student.requested_religion:<15} "
                        f"{student.religious:<16} "
                        f"{str(bool(student.is_priority)):<9}"
                    )
        else:
            print("No assignments.")

        unassigned = [student for student in students if student.id not in assigned_ids]
        if unassigned:
            print("\nUNASSIGNED")
            print(f"{'STUDENT':<12} {'RELIGION':<15} {'RELIGIOUS':<16} {'PRIORITY':<9}")
            print("-" * 60)
            for student in sorted(unassigned, key=lambda s: s.student_id):
                print(
                    f"{student.student_id:<12} "
                    f"{student.requested_religion:<15} "
                    f"{student.religious:<16} "
                    f"{str(bool(student.is_priority)):<9}"
                )

        print("=" * 110 + "\n")
        return result

    # ------------------------------------------------------------------
    # Case 1: RJ + RJ — allowed
    # ------------------------------------------------------------------
    def test_rj_plus_rj_can_share(self):
        rooms = self._make_infra(beds_per_apt=2)
        s1 = self._make_student('RJ1', Student.Religion.Jewish, Student.Religious.RELIGIOUS)
        s2 = self._make_student('RJ2', Student.Religion.Jewish, Student.Religious.RELIGIOUS)
        result = self._run([s1, s2], rooms)
        self.assertEqual(result['successful_assignments'], 2, result['proposed_assignments'])

    # ------------------------------------------------------------------
    # Case 2: RJ + Jewish NO_PREFERENCE — forbidden
    # ------------------------------------------------------------------
    def test_rj_plus_jewish_no_preference_cannot_share(self):
        rooms = self._make_infra(beds_per_apt=2)
        s1 = self._make_student('RJ1', Student.Religion.Jewish, Student.Religious.RELIGIOUS)
        s2 = self._make_student('JNP', Student.Religion.Jewish, Student.Religious.NO_PREFERENCE)
        result = self._run([s1, s2], rooms)
        self.assertLessEqual(result['successful_assignments'], 1, result['proposed_assignments'])

    # ------------------------------------------------------------------
    # Case 3: RJ + Muslim NO_PREFERENCE — forbidden
    # ------------------------------------------------------------------
    def test_rj_plus_muslim_no_preference_cannot_share(self):
        rooms = self._make_infra(beds_per_apt=2)
        s1 = self._make_student('RJ1', Student.Religion.Jewish, Student.Religious.RELIGIOUS)
        s2 = self._make_student('MNP', Student.Religion.Muslim, Student.Religious.NO_PREFERENCE)
        result = self._run([s1, s2], rooms)
        self.assertLessEqual(result['successful_assignments'], 1, result['proposed_assignments'])

    # ------------------------------------------------------------------
    # Case 4: Religious Muslim + Muslim NO_PREFERENCE — allowed
    # ------------------------------------------------------------------
    def test_religious_muslim_plus_muslim_no_preference_allowed(self):
        rooms = self._make_infra(beds_per_apt=2)
        s1 = self._make_student('RM1', Student.Religion.Muslim, Student.Religious.RELIGIOUS)
        s2 = self._make_student('MNP', Student.Religion.Muslim, Student.Religious.NO_PREFERENCE)
        result = self._run([s1, s2], rooms)
        self.assertEqual(result['successful_assignments'], 2, result['proposed_assignments'])

    # ------------------------------------------------------------------
    # Case 5: Religious Muslim + Muslim NOT_SPECIFIED — allowed
    # ------------------------------------------------------------------
    def test_religious_muslim_plus_muslim_not_specified_allowed(self):
        rooms = self._make_infra(beds_per_apt=2)
        s1 = self._make_student('RM1', Student.Religion.Muslim, Student.Religious.RELIGIOUS)
        s2 = self._make_student('MNS', Student.Religion.Muslim, Student.Religious.NOT_SPECIFIED)
        result = self._run([s1, s2], rooms)
        self.assertEqual(result['successful_assignments'], 2, result['proposed_assignments'])

    # ------------------------------------------------------------------
    # Case 6: Religious Muslim + Christian NO_PREFERENCE — forbidden
    # ------------------------------------------------------------------
    def test_religious_muslim_plus_christian_no_preference_forbidden(self):
        rooms = self._make_infra(beds_per_apt=2)
        s1 = self._make_student('RM1', Student.Religion.Muslim, Student.Religious.RELIGIOUS)
        s2 = self._make_student('CNP', Student.Religion.Christian, Student.Religious.NO_PREFERENCE)
        result = self._run([s1, s2], rooms)
        self.assertLessEqual(result['successful_assignments'], 1, result['proposed_assignments'])

    # ------------------------------------------------------------------
    # Case 7: Religious Christian + Christian NO_PREFERENCE — allowed
    # ------------------------------------------------------------------
    def test_religious_christian_plus_christian_no_preference_allowed(self):
        rooms = self._make_infra(beds_per_apt=2)
        s1 = self._make_student('RC1', Student.Religion.Christian, Student.Religious.RELIGIOUS)
        s2 = self._make_student('CNP', Student.Religion.Christian, Student.Religious.NO_PREFERENCE)
        result = self._run([s1, s2], rooms)
        self.assertEqual(result['successful_assignments'], 2, result['proposed_assignments'])

    # ------------------------------------------------------------------
    # Case 8: Religious Druze + Druze NO_PREFERENCE — allowed
    # ------------------------------------------------------------------
    def test_religious_druze_plus_druze_no_preference_allowed(self):
        rooms = self._make_infra(beds_per_apt=2)
        s1 = self._make_student('RD1', Student.Religion.Druze, Student.Religious.RELIGIOUS)
        s2 = self._make_student('DNP', Student.Religion.Druze, Student.Religious.NO_PREFERENCE)
        result = self._run([s1, s2], rooms)
        self.assertEqual(result['successful_assignments'], 2, result['proposed_assignments'])

    # ------------------------------------------------------------------
    # Case 9: Religious Muslim + Religious Christian — forbidden
    # ------------------------------------------------------------------
    def test_religious_muslim_plus_religious_christian_forbidden(self):
        rooms = self._make_infra(beds_per_apt=2)
        s1 = self._make_student('RM1', Student.Religion.Muslim, Student.Religious.RELIGIOUS)
        s2 = self._make_student('RC1', Student.Religion.Christian, Student.Religious.RELIGIOUS)
        result = self._run([s1, s2], rooms)
        self.assertLessEqual(result['successful_assignments'], 1, result['proposed_assignments'])

    # ------------------------------------------------------------------
    # Case 10: Religious Christian + Religious Druze — forbidden
    # ------------------------------------------------------------------
    def test_religious_christian_plus_religious_druze_forbidden(self):
        rooms = self._make_infra(beds_per_apt=2)
        s1 = self._make_student('RC1', Student.Religion.Christian, Student.Religious.RELIGIOUS)
        s2 = self._make_student('RD1', Student.Religion.Druze, Student.Religious.RELIGIOUS)
        result = self._run([s1, s2], rooms)
        self.assertLessEqual(result['successful_assignments'], 1, result['proposed_assignments'])

    # ------------------------------------------------------------------
    # Case 11: Jewish NO_PREFERENCE + Muslim NO_PREFERENCE — allowed
    # ------------------------------------------------------------------
    def test_jewish_no_preference_plus_muslim_no_preference_allowed(self):
        rooms = self._make_infra(beds_per_apt=2)
        s1 = self._make_student('JNP', Student.Religion.Jewish, Student.Religious.NO_PREFERENCE)
        s2 = self._make_student('MNP', Student.Religion.Muslim, Student.Religious.NO_PREFERENCE)
        result = self._run([s1, s2], rooms)
        self.assertEqual(result['successful_assignments'], 2, result['proposed_assignments'])

    # ------------------------------------------------------------------
    # Case 12: Muslim NO_PREFERENCE + Christian NO_PREFERENCE — allowed
    # ------------------------------------------------------------------
    def test_muslim_no_preference_plus_christian_no_preference_allowed(self):
        rooms = self._make_infra(beds_per_apt=2)
        s1 = self._make_student('MNP', Student.Religion.Muslim, Student.Religious.NO_PREFERENCE)
        s2 = self._make_student('CNP', Student.Religion.Christian, Student.Religious.NO_PREFERENCE)
        result = self._run([s1, s2], rooms)
        self.assertEqual(result['successful_assignments'], 2, result['proposed_assignments'])

    # ------------------------------------------------------------------
    # Case 13: Christian NO_PREFERENCE + Druze NO_PREFERENCE — allowed
    # ------------------------------------------------------------------
    def test_christian_no_preference_plus_druze_no_preference_allowed(self):
        rooms = self._make_infra(beds_per_apt=2)
        s1 = self._make_student('CNP', Student.Religion.Christian, Student.Religious.NO_PREFERENCE)
        s2 = self._make_student('DNP', Student.Religion.Druze, Student.Religious.NO_PREFERENCE)
        result = self._run([s1, s2], rooms)
        self.assertEqual(result['successful_assignments'], 2, result['proposed_assignments'])

    # ------------------------------------------------------------------
    # Case 14: Existing RELIGIOUS occupant blocks incompatible candidates
    # ------------------------------------------------------------------
    def test_existing_rj_blocks_non_rj_candidate(self):
        """Existing RJ occupant: a new non-RJ student cannot enter."""
        rooms = self._make_infra(beds_per_apt=2)
        room = rooms[0]
        bed = room.beds.first()
        rj = self._make_student('RJ0', Student.Religion.Jewish, Student.Religious.RELIGIOUS)
        BedAssignment.objects.create(
            student=rj, bed=bed,
            status=BedAssignment.Status.ACTIVE,
            assignment_type=BedAssignment.AssignmentType.MANUAL,
        )
        non_rj = self._make_student('MNP', Student.Religion.Muslim, Student.Religious.NO_PREFERENCE)
        result = self._run([non_rj], rooms)
        self.assertEqual(result['successful_assignments'], 0, result['proposed_assignments'])

    def test_existing_religious_muslim_blocks_christian_candidate(self):
        """Existing Religious Muslim occupant: a Christian (any level) cannot enter."""
        rooms = self._make_infra(beds_per_apt=2)
        room = rooms[0]
        bed = room.beds.first()
        rm = self._make_student('RM0', Student.Religion.Muslim, Student.Religious.RELIGIOUS)
        BedAssignment.objects.create(
            student=rm, bed=bed,
            status=BedAssignment.Status.ACTIVE,
            assignment_type=BedAssignment.AssignmentType.MANUAL,
        )
        christian = self._make_student('CNP', Student.Religion.Christian, Student.Religious.NO_PREFERENCE)
        result = self._run([christian], rooms)
        self.assertEqual(result['successful_assignments'], 0, result['proposed_assignments'])

    def test_existing_religious_muslim_allows_muslim_candidate(self):
        """Existing Religious Muslim occupant: a Muslim (no-preference) may enter."""
        rooms = self._make_infra(beds_per_apt=2)
        room = rooms[0]
        bed = room.beds.first()
        rm = self._make_student('RM0', Student.Religion.Muslim, Student.Religious.RELIGIOUS)
        BedAssignment.objects.create(
            student=rm, bed=bed,
            status=BedAssignment.Status.ACTIVE,
            assignment_type=BedAssignment.AssignmentType.MANUAL,
        )
        muslim = self._make_student('MNP', Student.Religion.Muslim, Student.Religious.NO_PREFERENCE)
        result = self._run([muslim], rooms)
        self.assertEqual(result['successful_assignments'], 1, result['proposed_assignments'])

    # ------------------------------------------------------------------
    # Case 15: Existing unrestricted occupants do not block mixed unrestricted candidates
    # ------------------------------------------------------------------
    def test_existing_unrestricted_do_not_block_mixed_unrestricted(self):
        """No-pref Muslim already in apt: a no-pref Jewish student may enter."""
        rooms = self._make_infra(beds_per_apt=2)
        room = rooms[0]
        bed = room.beds.first()
        muslim_np = self._make_student('MNP0', Student.Religion.Muslim, Student.Religious.NO_PREFERENCE)
        BedAssignment.objects.create(
            student=muslim_np, bed=bed,
            status=BedAssignment.Status.ACTIVE,
            assignment_type=BedAssignment.AssignmentType.MANUAL,
        )
        jewish_np = self._make_student('JNP1', Student.Religion.Jewish, Student.Religious.NO_PREFERENCE)
        result = self._run([jewish_np], rooms)
        self.assertEqual(result['successful_assignments'], 1, result['proposed_assignments'])

    # ------------------------------------------------------------------
    # Case 16: Accessibility removal — no student is filtered for accessibility
    # ------------------------------------------------------------------
    def test_accessibility_attributes_not_filtered(self):
        """After removing accessibility from the solver, no student is filtered for it."""
        rooms = self._make_infra(beds_per_apt=2)
        s = Student.objects.create(
            student_id='ACC1',
            first_name='Test',
            last_name='ACC1',
            housing_type=Student.HousingType.SINGLE_FEMALE,
            requested_religion=Student.Religion.Jewish,
            religious=Student.Religious.NO_PREFERENCE,
            is_priority=True,
            priority_reason='נגיש - accessibility needed',
        )
        result = self._run([s], rooms)
        self.assertEqual(result['successful_assignments'], 1, result['proposed_assignments'])

    # ------------------------------------------------------------------
    # Case 17: Priority and reserved-apartment behavior still works
    # ------------------------------------------------------------------
    def test_priority_can_enter_reserved_apartment(self):
        """
        Generic Apartment.InactiveReason.RESERVED behavior (any building,
        any is_priority=True student) — unrelated to, and not to be
        confused with, the Building-179 / כפר הסמכה automatic-allocation
        preference, which has its own dedicated tests in
        Building179AutomaticAllocationTest and is keyed on the אנייר
        marker plus accepted_dorm_type.code == 15, not is_priority=True.
        """
        dorm = DormType.objects.create(name='TestDorm')
        building = Building.objects.create(number=1, dorm_type=dorm)
        apt = Apartment.objects.create(
            building=building,
            number='R1',
            category=Apartment.Category.FEMALE,
            apartment_type=Apartment.ApartmentType.SINGLE,
            room_count=1,
            is_active=True,
            inactive_reason=Apartment.InactiveReason.RESERVED,
        )
        room = Room.objects.create(apartment=apt, name='A', capacity=2)
        Bed.objects.create(room=room, label='1')
        Bed.objects.create(room=room, label='2')

        priority_s = Student.objects.create(
            student_id='PRI1',
            first_name='Priority',
            last_name='Student',
            housing_type=Student.HousingType.SINGLE_FEMALE,
            requested_religion=Student.Religion.NOT_SPECIFIED,
            religious=Student.Religious.NOT_SPECIFIED,
            is_priority=True,
        )
        non_priority_s = Student.objects.create(
            student_id='NP1',
            first_name='NonPriority',
            last_name='Student',
            housing_type=Student.HousingType.SINGLE_FEMALE,
            requested_religion=Student.Religion.NOT_SPECIFIED,
            religious=Student.Religious.NOT_SPECIFIED,
            is_priority=False,
        )

        result = self._run([priority_s, non_priority_s], [room])
        self.assertEqual(result['successful_assignments'], 1, result['proposed_assignments'])
        assigned_ids = {a['student_db_id'] for a in result['proposed_assignments']}
        self.assertIn(priority_s.id, assigned_ids)
        self.assertNotIn(non_priority_s.id, assigned_ids)

    # ------------------------------------------------------------------
    # Multi-student run: solver separates all groups correctly
    # ------------------------------------------------------------------
    def test_hard_rule_multiple_students_same_run(self):
        """4 RJ + 4 Muslim NO_PREFERENCE in 2 apts of 4 beds: no mixing allowed."""
        from allocation.solver import _is_religious_jewish
        rooms = self._make_infra(beds_per_apt=4, num_apts=2)
        rj_students = [
            self._make_student(f'RJ{i}', Student.Religion.Jewish, Student.Religious.RELIGIOUS)
            for i in range(4)
        ]
        non_rj_students = [
            self._make_student(f'NRJ{i}', Student.Religion.Muslim, Student.Religious.NO_PREFERENCE)
            for i in range(4)
        ]
        result = self._run(rj_students + non_rj_students, rooms)
        self.assertEqual(result['successful_assignments'], 8, result['proposed_assignments'])

        apt_classification = {}
        for a in result['proposed_assignments']:
            apt_id = a['apartment_id']
            student = Student.objects.get(id=a['student_db_id'])
            is_rj = _is_religious_jewish(student)
            if apt_id in apt_classification:
                self.assertEqual(
                    apt_classification[apt_id], is_rj,
                    f"Apartment {apt_id} has mixed RJ/non-RJ occupants",
                )
            else:
                apt_classification[apt_id] = is_rj
