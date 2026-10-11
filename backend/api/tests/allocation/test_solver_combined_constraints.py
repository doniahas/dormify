from collections import defaultdict
from unittest.mock import patch

from django.test import TestCase

from api.models import Student, DormType, Building, Apartment, Room, Bed


# ---------------------------------------------------------------------------
# Strong combined solver tests: capacity-5 apartments
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Strong combined solver tests:
# 4 apartments × 5 separate one-bed rooms = 20 students
# ---------------------------------------------------------------------------

class SolverCombinedAllConstraintsTest(TestCase):
    """
    End-to-end solver tests using realistic apartment structure:

        4 apartments
        5 separate rooms per apartment
        1 bed per room
        total capacity = 20 students

    The tests cover both categories of allocation rules:

    CRITICAL / HARD
    ----------------
    - sameGender
    - priorityFirst / reserved apartments
    - roommatePositiveOnly
    - ReligiousTogether
    - apartment capacity and one student per room

    FLEXIBLE / SOFT
    ---------------
    - sameReligion
    - roommateMatch
    - sectorMatching
    - avoidYearMix_1_with_3_4
    - avoidAtudaimWithHasmaha

    Every solver run prints a readable allocation table, including the actual
    apartment, room and bed loaded from the test database.
    """

    ALL_CRITICAL_AND_FLEXIBLE = {
        "sameGender": {
            "enabled": True,
            "strict": True,
            "critical": True,
            "weight": 0,
        },
        "priorityFirst": {
            "enabled": True,
            "strict": True,
            "critical": True,
            "weight": 0,
        },
        "roommatePositiveOnly": {
            "enabled": True,
            "strict": True,
            "critical": True,
            "weight": 0,
        },
        "ReligiousTogether": {
            "enabled": True,
            "strict": True,
            "critical": True,
            "weight": 0,
        },
        "sameReligion": {
            "enabled": True,
            "strict": False,
            "critical": False,
            "weight": 6,
        },
        "roommateMatch": {
            "enabled": True,
            "strict": False,
            "critical": False,
            "weight": 10,
        },
        "sectorMatching": {
            "enabled": True,
            "strict": False,
            "critical": False,
            "weight": 7,
        },
        "avoidYearMix_1_with_3_4": {
            "enabled": True,
            "strict": False,
            "critical": False,
            "weight": 8,
        },
        "avoidAtudaimWithHasmaha": {
            "enabled": True,
            "strict": False,
            "critical": False,
            "weight": 8,
        },
    }

    FLEXIBLE_ROOMMATE_CONFIG = {
        **ALL_CRITICAL_AND_FLEXIBLE,
        "roommatePositiveOnly": {
            "enabled": False,
            "strict": False,
            "critical": False,
            "weight": 0,
        },
    }

    def setUp(self):
        patcher = patch("allocation.solver.close_old_connections")
        patcher.start()
        self.addCleanup(patcher.stop)

        self.dorm = DormType.objects.create(name="CombinedStrongDorm")
        self.building = Building.objects.create(
            number=1,
            dorm_type=self.dorm,
        )

    # ------------------------------------------------------------------
    # Infrastructure and data helpers
    # ------------------------------------------------------------------

    def _make_four_apartments(
        self,
        categories=None,
        reserved_indexes=None,
    ):
        """
        Build exactly four apartments.

        Each apartment contains five separate rooms, and every room contains
        one bed. This is deliberately different from one room with five beds.
        """

        categories = categories or [
            Apartment.Category.FEMALE,
            Apartment.Category.FEMALE,
            Apartment.Category.FEMALE,
            Apartment.Category.FEMALE,
        ]
        reserved_indexes = set(reserved_indexes or [])

        self.assertEqual(len(categories), 4)

        rooms = []

        for apartment_index in range(4):
            apartment = Apartment.objects.create(
                building=self.building,
                number=str(apartment_index + 1),
                category=categories[apartment_index],
                apartment_type=Apartment.ApartmentType.SINGLE,
                room_count=5,
                apartment_capacity=5,
                is_active=True,
                inactive_reason=(
                    Apartment.InactiveReason.RESERVED
                    if apartment_index in reserved_indexes
                    else ""
                ),
            )

            for room_index in range(5):
                room = Room.objects.create(
                    apartment=apartment,
                    name=f"R{room_index + 1}",
                    capacity=1,
                    is_active=True,
                )
                Bed.objects.create(
                    room=room,
                    label="Bed 1",
                )
                rooms.append(room)

        self.assertEqual(len(rooms), 20)
        return rooms

    def _student(
        self,
        student_id,
        religion,
        religious,
        *,
        gender=Student.Gender.FEMALE,
        priority=False,
        sector=Student.PlacementSector.UNKNOWN,
        points=45,
        special_status="",
    ):
        housing_type = (
            Student.HousingType.SINGLE_MALE
            if gender == Student.Gender.MALE
            else Student.HousingType.SINGLE_FEMALE
        )

        return Student.objects.create(
            student_id=student_id,
            first_name="Test",
            last_name=student_id,
            gender=gender,
            housing_type=housing_type,
            requested_religion=religion,
            religious=religious,
            placement_sector=sector,
            study_points=points,
            special_status_1=special_status,
            is_priority=priority,
        )

    def _make_mutual_positive_roommate_pair(self, student_1, student_2):
        """
        Store a real mutual positive roommate request using the current model
        fields consumed by the solver.
        """

        student_1.roommate_request_student_id_1 = student_2.student_id
        student_1.roommate_request_flag_1 = True
        student_1.save(
            update_fields=[
                "roommate_request_student_id_1",
                "roommate_request_flag_1",
            ]
        )

        student_2.roommate_request_student_id_1 = student_1.student_id
        student_2.roommate_request_flag_1 = True
        student_2.save(
            update_fields=[
                "roommate_request_student_id_1",
                "roommate_request_flag_1",
            ]
        )

    def _assignment_maps(self, result):
        assignments = result.get("proposed_assignments", [])
        student_to_apartment = {}
        by_apartment = defaultdict(list)
        by_room = defaultdict(list)

        for assignment in assignments:
            student_id = assignment["student_db_id"]
            apartment_id = assignment["apartment_id"]

            student_to_apartment[student_id] = apartment_id
            by_apartment[apartment_id].append(student_id)

            room_id = assignment.get("room_id")
            if room_id is not None:
                by_room[room_id].append(student_id)

        return student_to_apartment, by_apartment, by_room

    def _assert_capacity_and_single_occupancy(self, result):
        _, by_apartment, by_room = self._assignment_maps(result)

        for apartment_id, student_ids in by_apartment.items():
            self.assertLessEqual(
                len(student_ids),
                5,
                f"Apartment {apartment_id} exceeds capacity 5.",
            )

        for room_id, student_ids in by_room.items():
            self.assertEqual(
                len(student_ids),
                1,
                f"Room {room_id} contains more than one student.",
            )

    def _assert_religious_rules(self, result):
        """
        Validate the corrected hard rule directly from the produced allocation.

        - Religious Jewish: only Religious Jewish.
        - Religious Muslim/Christian/Druze: everyone in the apartment must have
          that same religion, while observance may differ.
        - Unrestricted students impose no restriction.
        """

        from allocation.solver import (
            _is_religious_jewish,
            _student_religious_state,
            _religion_key,
        )

        _, by_apartment, _ = self._assignment_maps(result)

        for apartment_id, student_ids in by_apartment.items():
            occupants = list(Student.objects.filter(id__in=student_ids))

            if any(_is_religious_jewish(student) for student in occupants):
                self.assertTrue(
                    all(_is_religious_jewish(student) for student in occupants),
                    f"Apartment {apartment_id} mixes Religious Jewish "
                    f"with an incompatible student.",
                )
                continue

            restricted_religions = {
                state[1]
                for student in occupants
                if (
                    (state := _student_religious_state(student)) is not None
                    and state[0] == "religion"
                )
            }

            self.assertLessEqual(
                len(restricted_religions),
                1,
                f"Apartment {apartment_id} contains different hard "
                f"religious restrictions: {restricted_religions}",
            )

            if restricted_religions:
                required_religion = next(iter(restricted_religions))
                self.assertTrue(
                    all(
                        _religion_key(student) == required_religion
                        for student in occupants
                    ),
                    f"Apartment {apartment_id} is restricted to "
                    f"{required_religion}, but contains another religion.",
                )

    def _assert_pairs_together(self, result, pairs):
        student_to_apartment, _, _ = self._assignment_maps(result)

        for student_1, student_2 in pairs:
            self.assertIn(
                student_1.id,
                student_to_apartment,
                f"{student_1.student_id} was not assigned.",
            )
            self.assertIn(
                student_2.id,
                student_to_apartment,
                f"{student_2.student_id} was not assigned.",
            )
            self.assertEqual(
                student_to_apartment[student_1.id],
                student_to_apartment[student_2.id],
                f"Mutual roommates {student_1.student_id} and "
                f"{student_2.student_id} were separated.",
            )

    def _resolve_assignment_location(self, assignment):
        """
        Resolve actual DB objects so the printed ROOM column never appears blank
        merely because a solver result omitted room_name.
        """

        bed = None

        for key in ("bed_id", "bed_db_id"):
            value = assignment.get(key)
            if value is not None:
                bed = (
                    Bed.objects.select_related("room", "room__apartment")
                    .filter(id=value)
                    .first()
                )
                if bed is not None:
                    break

        if bed is not None:
            return bed.room.apartment, bed.room, bed

        room = None
        room_id = assignment.get("room_id")
        if room_id is not None:
            room = (
                Room.objects.select_related("apartment")
                .filter(id=room_id)
                .first()
            )

        if room is not None:
            return room.apartment, room, None

        apartment = Apartment.objects.get(id=assignment["apartment_id"])
        return apartment, None, None

    def _run(self, students, rooms, config=None):
        import inspect
        from allocation.solver import run_improved_ortools_allocation

        test_name = inspect.stack()[1].function
        students = list(students)
        rooms = list(rooms)

        result = run_improved_ortools_allocation(
            students,
            rooms,
            config or self.ALL_CRITICAL_AND_FLEXIBLE,
        )

        assignments = result.get("proposed_assignments", [])
        assigned_ids = {
            assignment["student_db_id"]
            for assignment in assignments
        }

        printable_rows = []

        for assignment in assignments:
            student = Student.objects.get(
                id=assignment["student_db_id"]
            )
            apartment, room, bed = self._resolve_assignment_location(
                assignment
            )

            printable_rows.append(
                (
                    str(apartment.number),
                    str(room.name if room else assignment.get("room_name", "")),
                    str(bed.label if bed else assignment.get("bed_label", "")),
                    student,
                )
            )

        printable_rows.sort(
            key=lambda row: (
                row[0],
                row[1],
                row[2],
                row[3].student_id,
            )
        )

        print("\n" + "=" * 150)
        print(f"STRONG COMBINED TEST: {test_name}")
        print(
            f"status={result.get('solver_status')} | "
            f"students={len(students)} | "
            f"assigned={result.get('successful_assignments', 0)} | "
            f"conflicts={result.get('conflicts', 0)} | "
            f"mutual_roommate_matches="
            f"{result.get('mutual_roommate_matches', 0)} | "
            f"one_sided_roommate_matches="
            f"{result.get('one_sided_roommate_matches', 0)}"
        )
        print("=" * 150)

        if printable_rows:
            print(
                f"{'APT':<6} {'ROOM':<7} {'BED':<8} {'STUDENT':<10} "
                f"{'GENDER':<8} {'RELIGION':<14} {'RELIGIOUS':<15} "
                f"{'SECTOR':<9} {'POINTS':<8} {'STATUS':<12} "
                f"{'PRIORITY':<8} {'ROOMMATE REQUEST':<20}"
            )
            print("-" * 150)

            for apartment_number, room_name, bed_label, student in printable_rows:
                requests = [
                    student.roommate_request_student_id_1,
                    student.roommate_request_student_id_2,
                    student.roommate_request_student_id_3,
                    student.roommate_request_student_id_4,
                    student.roommate_request_student_id_5,
                ]
                request_text = ",".join(
                    request for request in requests if request
                ) or "-"

                print(
                    f"{apartment_number:<6} "
                    f"{room_name:<7} "
                    f"{bed_label:<8} "
                    f"{student.student_id:<10} "
                    f"{str(student.gender):<8} "
                    f"{student.requested_religion:<14} "
                    f"{student.religious:<15} "
                    f"{student.placement_sector:<9} "
                    f"{str(student.study_points):<8} "
                    f"{student.special_status_1:<12} "
                    f"{str(bool(student.is_priority)):<8} "
                    f"{request_text:<20}"
                )
        else:
            print("No assignments.")

        unassigned = [
            student
            for student in students
            if student.id not in assigned_ids
        ]

        if unassigned:
            print("\nUNASSIGNED")
            print(
                f"{'STUDENT':<10} {'GENDER':<8} {'RELIGION':<14} "
                f"{'RELIGIOUS':<15} {'SECTOR':<9} {'PRIORITY':<8}"
            )
            print("-" * 80)

            for student in sorted(
                unassigned,
                key=lambda item: item.student_id,
            ):
                print(
                    f"{student.student_id:<10} "
                    f"{str(student.gender):<8} "
                    f"{student.requested_religion:<14} "
                    f"{student.religious:<15} "
                    f"{student.placement_sector:<9} "
                    f"{str(bool(student.is_priority)):<8}"
                )

        print("=" * 150 + "\n")
        return result

    # ------------------------------------------------------------------
    # Test 1: all critical constraints together
    # ------------------------------------------------------------------

    def test_all_critical_constraints_together_with_20_students(self):
        """
        WHAT THIS TEST CHECKS
        ---------------------
        1. Exactly 20 students fit into 4 apartments × 5 separate rooms.
        2. Apartment 1 is reserved, so only the five priority students enter it.
        3. Female students enter female apartments and male students enter male
           apartments (sameGender + housing-type compatibility).
        4. Ten mutual positive roommate pairs remain in the same apartment
           (roommatePositiveOnly is critical).
        5. Religious Jewish students share only with Religious Jewish students.
        6. Religious Muslim, Christian and Druze students share only with their
           own religion, but may share with same-religion NO_PREFERENCE students.
        7. All flexible constraints are simultaneously enabled.
        """

        rooms = self._make_four_apartments(
            categories=[
                Apartment.Category.FEMALE,
                Apartment.Category.FEMALE,
                Apartment.Category.MALE,
                Apartment.Category.MALE,
            ],
            reserved_indexes={0},
        )

        groups = []

        # Reserved female apartment: 5 priority Religious Jewish students.
        groups.append([
            self._student(
                f"FRJ{i}",
                Student.Religion.Jewish,
                Student.Religious.RELIGIOUS,
                gender=Student.Gender.FEMALE,
                priority=True,
                sector=Student.PlacementSector.JEWISH,
                points=20,
                special_status="עתודאי",
            )
            for i in range(1, 6)
        ])

        # Female Muslim apartment.
        groups.append([
            self._student(
                "FRM1",
                Student.Religion.Muslim,
                Student.Religious.RELIGIOUS,
                gender=Student.Gender.FEMALE,
                sector=Student.PlacementSector.ARAB,
                points=80,
                special_status="הסמכה",
            ),
            *[
                self._student(
                    f"FMU{i}",
                    Student.Religion.Muslim,
                    Student.Religious.NO_PREFERENCE,
                    gender=Student.Gender.FEMALE,
                    sector=Student.PlacementSector.ARAB,
                    points=80,
                    special_status="הסמכה",
                )
                for i in range(1, 5)
            ],
        ])

        # Male Christian apartment.
        groups.append([
            self._student(
                "MRC1",
                Student.Religion.Christian,
                Student.Religious.RELIGIOUS,
                gender=Student.Gender.MALE,
                sector=Student.PlacementSector.ARAB,
                points=20,
                special_status="עתודאי",
            ),
            *[
                self._student(
                    f"MCU{i}",
                    Student.Religion.Christian,
                    Student.Religious.NO_PREFERENCE,
                    gender=Student.Gender.MALE,
                    sector=Student.PlacementSector.ARAB,
                    points=20,
                    special_status="עתודאי",
                )
                for i in range(1, 5)
            ],
        ])

        # Male Druze apartment.
        groups.append([
            self._student(
                "MRD1",
                Student.Religion.Druze,
                Student.Religious.RELIGIOUS,
                gender=Student.Gender.MALE,
                sector=Student.PlacementSector.ARAB,
                points=80,
                special_status="הסמכה",
            ),
            *[
                self._student(
                    f"MDU{i}",
                    Student.Religion.Druze,
                    Student.Religious.NO_PREFERENCE,
                    gender=Student.Gender.MALE,
                    sector=Student.PlacementSector.ARAB,
                    points=80,
                    special_status="הסמכה",
                )
                for i in range(1, 5)
            ],
        ])

        students = [
            student
            for group in groups
            for student in group
        ]

        roommate_pairs = []

        # Two hard mutual pairs in every five-person group.
        for group in groups:
            for first_index, second_index in ((0, 1), (2, 3)):
                first = group[first_index]
                second = group[second_index]
                self._make_mutual_positive_roommate_pair(first, second)
                roommate_pairs.append((first, second))

        result = self._run(students, rooms)

        self.assertEqual(
            result["successful_assignments"],
            20,
            result.get("proposed_assignments"),
        )
        self.assertEqual(result["conflicts"], 0)

        self._assert_capacity_and_single_occupancy(result)
        self._assert_religious_rules(result)
        self._assert_pairs_together(result, roommate_pairs)

        student_to_apartment, by_apartment, _ = self._assignment_maps(result)

        reserved_apartment = Apartment.objects.get(
            building=self.building,
            number="1",
        )

        reserved_student_ids = set(
            by_apartment.get(reserved_apartment.id, [])
        )

        expected_priority_ids = {
            student.id
            for student in groups[0]
        }

        self.assertEqual(
            reserved_student_ids,
            expected_priority_ids,
            "The reserved apartment must contain exactly the five "
            "priority students.",
        )

        for apartment_id, student_ids in by_apartment.items():
            occupants = list(Student.objects.filter(id__in=student_ids))
            genders = {student.gender for student in occupants}
            self.assertEqual(
                len(genders),
                1,
                f"Apartment {apartment_id} mixes genders: {genders}",
            )

    # ------------------------------------------------------------------
    # Test 2: two critical constraints conflict
    # ------------------------------------------------------------------

    def test_critical_roommate_request_cannot_break_critical_religion(self):
        """
        WHAT THIS TEST CHECKS
        ---------------------
        A Religious Jewish student and a Muslim NO_PREFERENCE student request
        each other as critical positive roommates.

        Hard roommate logic says they must share an apartment if both are placed.
        Hard religion logic says they may never share.

        Therefore the solver must not assign both students. It must preserve both
        hard constraints instead of silently violating either one.
        """

        rooms = self._make_four_apartments()

        religious_jewish = self._student(
            "CRJ",
            Student.Religion.Jewish,
            Student.Religious.RELIGIOUS,
            sector=Student.PlacementSector.JEWISH,
        )
        muslim = self._student(
            "CMU",
            Student.Religion.Muslim,
            Student.Religious.NO_PREFERENCE,
            sector=Student.PlacementSector.ARAB,
        )

        self._make_mutual_positive_roommate_pair(
            religious_jewish,
            muslim,
        )

        fillers = [
            self._student(
                f"CF{i:02}",
                [
                    Student.Religion.Jewish,
                    Student.Religion.Muslim,
                    Student.Religion.Christian,
                    Student.Religion.Druze,
                ][i % 4],
                Student.Religious.NO_PREFERENCE,
                sector=(
                    Student.PlacementSector.JEWISH
                    if i % 4 == 0
                    else Student.PlacementSector.ARAB
                ),
            )
            for i in range(18)
        ]

        students = [
            religious_jewish,
            muslim,
            *fillers,
        ]

        result = self._run(students, rooms)

        assigned_ids = {
            assignment["student_db_id"]
            for assignment in result["proposed_assignments"]
        }

        self.assertFalse(
            religious_jewish.id in assigned_ids
            and muslim.id in assigned_ids,
            "The incompatible critical roommate pair was assigned together.",
        )

        self.assertGreaterEqual(result["conflicts"], 1)
        self._assert_capacity_and_single_occupancy(result)
        self._assert_religious_rules(result)

    # ------------------------------------------------------------------
    # Test 3: flexible roommate preference never overrides a hard rule
    # ------------------------------------------------------------------

    def test_flexible_roommate_preference_does_not_override_religion(self):
        """
        WHAT THIS TEST CHECKS
        ---------------------
        The same incompatible pair is now a FLEXIBLE roommate preference:
        roommateMatch is enabled, but roommatePositiveOnly is disabled.

        Because religion is critical and roommate matching is flexible:
        - both students may still be assigned,
        - but they must be assigned to different apartments,
        - and all 20 students should fit.
        """

        rooms = self._make_four_apartments()

        religious_jewish = self._student(
            "SRJ",
            Student.Religion.Jewish,
            Student.Religious.RELIGIOUS,
            sector=Student.PlacementSector.JEWISH,
        )
        muslim = self._student(
            "SMU",
            Student.Religion.Muslim,
            Student.Religious.NO_PREFERENCE,
            sector=Student.PlacementSector.ARAB,
        )

        self._make_mutual_positive_roommate_pair(
            religious_jewish,
            muslim,
        )

        # Four more RJ students allow a valid RJ-only apartment.
        rj_fillers = [
            self._student(
                f"SRJF{i}",
                Student.Religion.Jewish,
                Student.Religious.RELIGIOUS,
                sector=Student.PlacementSector.JEWISH,
            )
            for i in range(1, 5)
        ]

        unrestricted_fillers = [
            self._student(
                f"SU{i:02}",
                [
                    Student.Religion.Muslim,
                    Student.Religion.Christian,
                    Student.Religion.Druze,
                ][i % 3],
                Student.Religious.NO_PREFERENCE,
                sector=Student.PlacementSector.ARAB,
            )
            for i in range(14)
        ]

        students = [
            religious_jewish,
            muslim,
            *rj_fillers,
            *unrestricted_fillers,
        ]

        self.assertEqual(len(students), 20)

        result = self._run(
            students,
            rooms,
            config=self.FLEXIBLE_ROOMMATE_CONFIG,
        )

        self.assertEqual(
            result["successful_assignments"],
            20,
            result["proposed_assignments"],
        )
        self.assertEqual(result["conflicts"], 0)

        student_to_apartment, _, _ = self._assignment_maps(result)

        self.assertNotEqual(
            student_to_apartment[religious_jewish.id],
            student_to_apartment[muslim.id],
            "A flexible roommate preference overrode critical religion.",
        )

        self._assert_capacity_and_single_occupancy(result)
        self._assert_religious_rules(result)

    # ------------------------------------------------------------------
    # Test 4: all flexible preferences guide the optimizer together
    # ------------------------------------------------------------------

    def test_all_flexible_preferences_organize_20_students(self):
        """
        WHAT THIS TEST CHECKS
        ---------------------
        There are no religious students, so hard ReligiousTogether imposes no
        grouping restriction. All 20 students remain feasible.

        The 20 students form four natural five-person groups distinguished by:
        - religion,
        - placement sector,
        - study-year group,
        - Atudai versus Hasmaha status,
        - mutual roommate requests.

        With all flexible weights enabled, the optimal result should keep every
        apartment internally homogeneous for those soft attributes and keep the
        requested roommate pairs together.

        This directly exercises:
        - sameReligion,
        - roommateMatch,
        - sectorMatching,
        - avoidYearMix_1_with_3_4,
        - avoidAtudaimWithHasmaha.
        """

        rooms = self._make_four_apartments()

        group_specs = [
            (
                "A",
                Student.Religion.Jewish,
                Student.PlacementSector.JEWISH,
                20,
                "עתודאי",
            ),
            (
                "B",
                Student.Religion.Muslim,
                Student.PlacementSector.ARAB,
                80,
                "הסמכה",
            ),
            (
                "C",
                Student.Religion.Christian,
                Student.PlacementSector.ARAB,
                20,
                "עתודאי",
            ),
            (
                "D",
                Student.Religion.Druze,
                Student.PlacementSector.ARAB,
                80,
                "הסמכה",
            ),
        ]

        groups = []
        roommate_pairs = []

        for prefix, religion, sector, points, special_status in group_specs:
            group = [
                self._student(
                    f"{prefix}{index}",
                    religion,
                    Student.Religious.NO_PREFERENCE,
                    sector=sector,
                    points=points,
                    special_status=special_status,
                )
                for index in range(1, 6)
            ]
            groups.append(group)

            self._make_mutual_positive_roommate_pair(
                group[0],
                group[1],
            )
            self._make_mutual_positive_roommate_pair(
                group[2],
                group[3],
            )

            roommate_pairs.extend([
                (group[0], group[1]),
                (group[2], group[3]),
            ])

        students = [
            student
            for group in groups
            for student in group
        ]

        result = self._run(
            students,
            rooms,
            config=self.FLEXIBLE_ROOMMATE_CONFIG,
        )

        self.assertEqual(
            result["successful_assignments"],
            20,
            result["proposed_assignments"],
        )
        self.assertEqual(result["conflicts"], 0)

        self._assert_capacity_and_single_occupancy(result)
        self._assert_pairs_together(result, roommate_pairs)

        _, by_apartment, _ = self._assignment_maps(result)

        self.assertEqual(
            len(by_apartment),
            4,
            "All four apartments should be used.",
        )

        for apartment_id, student_ids in by_apartment.items():
            occupants = list(Student.objects.filter(id__in=student_ids))

            self.assertEqual(
                len(occupants),
                5,
                f"Apartment {apartment_id} should contain exactly 5 students.",
            )

            religions = {
                student.requested_religion
                for student in occupants
            }
            sectors = {
                student.placement_sector
                for student in occupants
            }
            year_groups = {
                "year1"
                if float(student.study_points or 0) <= 40
                else "year3_4"
                if float(student.study_points or 0) >= 60
                else "other"
                for student in occupants
            }
            statuses = {
                "atudai"
                if "עתודאי" in student.special_status_1
                else "hasmaha"
                if "הסמכה" in student.special_status_1
                else "other"
                for student in occupants
            }

            self.assertEqual(
                len(religions),
                1,
                f"sameReligion did not keep apartment {apartment_id} homogeneous.",
            )
            self.assertEqual(
                len(sectors),
                1,
                f"sectorMatching did not keep apartment {apartment_id} homogeneous.",
            )
            self.assertEqual(
                len(year_groups),
                1,
                f"Year-mix preference was violated in apartment {apartment_id}.",
            )
            self.assertEqual(
                len(statuses),
                1,
                f"Atudai/Hasmaha preference was violated in apartment {apartment_id}.",
            )
