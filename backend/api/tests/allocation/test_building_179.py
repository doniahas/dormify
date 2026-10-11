from unittest.mock import patch

from django.test import TestCase
from rest_framework.test import APIClient

from api.models import (
    Region, BedAssignment, Student, DormType, Building, Apartment, Room, Bed,
)

from ._support import _make_region, _make_central_admin


# ---------------------------------------------------------------------------
# Building 179 / כפר הסמכה (DormType.code == 15) automatic-allocation
# preference: a one-way reservation with overflow, not hard bidirectional
# exclusivity.
#
# Confirmed business rules under test:
#   - Building 179 belongs to DormType.code == 15 (כפר הסמכה). DormType.code
#     == 11 (עליון עמים) is a separate, unrelated dorm type.
#   - An eligible Hasmaha ANIR student (אנייר marker AND
#     accepted_dorm_type.code == 15) prefers Building 179 but is not locked
#     to it — they may overflow to any other active, compatible apartment
#     within DormType 15.
#   - Students who are not eligible Hasmaha ANIR students (ordinary,
#     generic-priority, or ANIR-but-wrong-dorm-type) may never
#     automatically consume Building-179 inventory.
#   - This policy governs automatic allocation only; authorized staff may
#     still manually assign/move any student into or out of Building 179
#     (see ManualBuilding179OverrideTest below).
#
# Replaces the historical SolverBuilding179PriorityTest, which tested a
# now-confirmed-incorrect rule (region-based detection via a nonexistent
# UPPER_DORM_OFFICE_REGION_IDS constant, a 4-condition eligibility
# requirement, and hard bidirectional exclusivity with no overflow).
# ---------------------------------------------------------------------------

class Building179AutomaticAllocationTest(TestCase):
    """
    Confirmed business rules under test (audit sections 4, 9A):

      Case A — an eligible Hasmaha ANIR student (carries the אנייר special-
      status marker AND accepted_dorm_type.code == 15):
        - Building 179 is their preferred automatic-allocation destination.
        - Ordinary and generic-priority (non-eligible) students may never
          automatically consume Building-179 inventory.
        - They are NOT hard-locked to Building 179 — when it lacks a
          compatible bed, they automatically overflow to any other active,
          compatible apartment within DormType 15, found via ordinary
          accepted-dorm-type matching (never a hard-coded building-number
          list, so a future building added to DormType 15 works with no
          code change).
        - All normal hard constraints (gender, religion, capacity, housing
          type, existing occupants, roommate rules) still apply.

      Case B — an ANIR student whose accepted_dorm_type.code != 15:
        - Must never be redirected to Building 179.
        - Must remain restricted to their own accepted dorm type/region,
          exactly like any other non-priority student — the אנייר marker
          alone must never waive that restriction (this directly tests the
          confirmed fix to _should_enforce_accepted_dorm_type).

      Case C — an ANIR student in a region with no כפר הסמכה inventory at
      all: assigned normally, as an ordinary priority student; a dedicated
      ANIR building is not required outside גוש עליון.

    This policy is automatic-allocation only; manual staff overrides
    (explicitly permitted) are covered separately in
    ManualBuilding179OverrideTest below.
    """

    DEFAULT_CONFIG = {
        "sameGender": {"enabled": True, "strict": True, "critical": True, "weight": 0},
        "priorityFirst": {"enabled": True, "strict": True, "critical": True, "weight": 0},
        "roommatePositiveOnly": {"enabled": True, "strict": True, "critical": True, "weight": 0},
        "ReligiousTogether": {"enabled": True, "strict": True, "critical": True, "weight": 0},
        "sameReligion": {"enabled": False},
        "roommateMatch": {"enabled": False},
        "sectorMatching": {"enabled": False},
        "avoidYearMix_1_with_3_4": {"enabled": False},
        "avoidAtudaimWithHasmaha": {"enabled": False},
    }

    def setUp(self):
        patcher = patch("allocation.solver.close_old_connections")
        patcher.start()
        self.addCleanup(patcher.stop)

        # כפר הסמכה (DormType.code == 15) in its confirmed region גוש עליון,
        # with Building 179 (the preferred destination) plus one additional
        # building (176) representing ordinary overflow inventory of the
        # SAME dorm type — deliberately not a hard-coded {176,177,178,179}
        # list; any other/future building under code 15 must behave the
        # same way (see test_overflow_not_restricted_to_hardcoded_building_list).
        self.upper_region = Region.objects.create(id="gush_elyon", name="גוש עליון")
        self.hasmaha_dorm_type = DormType.objects.create(
            name="כפר הסמכה", code=15, region=self.upper_region,
        )
        self.building_179 = Building.objects.create(number=179, dorm_type=self.hasmaha_dorm_type)
        self.building_176 = Building.objects.create(number=176, dorm_type=self.hasmaha_dorm_type)

        # A second, real, unrelated dorm type in the SAME region (code 11 =
        # עליון עמים, confirmed unrelated to this policy) — used for Case B.
        self.other_upper_dorm_type = DormType.objects.create(
            name="עליון עמים", code=11, region=self.upper_region,
        )
        self.other_upper_building = Building.objects.create(
            number=201, dorm_type=self.other_upper_dorm_type,
        )

        # A building numbered 179 under a completely unrelated dorm
        # type/region — must remain an entirely ordinary building.
        self.other_region = Region.objects.create(id="other_region", name="אזור אחר")
        self.other_region_dorm_type = DormType.objects.create(
            name="OtherRegionDorm", region=self.other_region,
        )
        self.other_region_building_179 = Building.objects.create(
            number=179, dorm_type=self.other_region_dorm_type,
        )

    # ------------------------------------------------------------------
    # Infrastructure helpers
    # ------------------------------------------------------------------

    def _make_room(
        self,
        building,
        apt_number,
        category=Apartment.Category.FEMALE,
        apartment_type=Apartment.ApartmentType.SINGLE,
        bed_count=2,
        room_name="A",
        is_active=True,
    ):
        apartment = Apartment.objects.create(
            building=building,
            number=apt_number,
            category=category,
            apartment_type=apartment_type,
            room_count=1,
            apartment_capacity=bed_count,
            is_active=is_active,
        )
        room = Room.objects.create(
            apartment=apartment, name=room_name, capacity=bed_count, is_active=is_active,
        )
        for index in range(bed_count):
            Bed.objects.create(room=room, label=str(index + 1))
        return room

    def _make_student(
        self,
        student_id,
        *,
        gender=Student.Gender.FEMALE,
        housing_type=None,
        priority=False,
        anier=False,
        accepted_dorm_type=None,
        religion=Student.Religion.NOT_SPECIFIED,
        religious=Student.Religious.NOT_SPECIFIED,
    ):
        if housing_type is None:
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
            is_priority=priority,
            special_status_1="אנייר" if anier else "",
            accepted_dorm_type=accepted_dorm_type,
            requested_religion=religion,
            religious=religious,
        )

    def _resolve_assignment_location(self, assignment):
        bed = Bed.objects.select_related(
            "room", "room__apartment", "room__apartment__building",
            "room__apartment__building__dorm_type",
        ).get(id=assignment["bed_id"])
        return bed.room.apartment, bed.room, bed

    def _assigned_building_number(self, result, student):
        for assignment in result["proposed_assignments"]:
            if assignment["student_db_id"] == student.id:
                apartment, _, _ = self._resolve_assignment_location(assignment)
                return apartment.building.number
        return None

    def _run(self, students, rooms, config=None):
        from allocation.solver import run_improved_ortools_allocation
        return run_improved_ortools_allocation(
            list(students), list(rooms), config or self.DEFAULT_CONFIG,
        )

    # ------------------------------------------------------------------
    # 1. Eligible Hasmaha ANIR student gets Building 179 when space exists.
    # ------------------------------------------------------------------

    def test_hasmaha_anier_student_gets_building_179_when_space_exists(self):
        room179 = self._make_room(self.building_179, "1", bed_count=2)
        student = self._make_student(
            "H1", anier=True, accepted_dorm_type=self.hasmaha_dorm_type,
        )

        result = self._run([student], [room179])
        self.assertEqual(result["successful_assignments"], 1, result["proposed_assignments"])
        self.assertEqual(self._assigned_building_number(result, student), 179)

    # ------------------------------------------------------------------
    # 2/3. Overflow within DormType 15 when 179 is full — driven by
    #      accepted-dorm-type matching, not a hard-coded building list.
    # ------------------------------------------------------------------

    def test_hasmaha_anier_student_overflows_within_dormtype_when_179_full(self):
        """When Building 179 has no free bed, an eligible Hasmaha ANIR
        student must be assigned elsewhere in DormType 15 (Building 176)
        rather than left unassigned."""
        room179 = self._make_room(self.building_179, "1", bed_count=1)
        room176 = self._make_room(self.building_176, "1", bed_count=1)

        existing_occupant = self._make_student(
            "H_EXIST", anier=True, accepted_dorm_type=self.hasmaha_dorm_type,
        )
        BedAssignment.objects.create(
            student=existing_occupant, bed=room179.beds.first(),
            status=BedAssignment.Status.ACTIVE,
            assignment_type=BedAssignment.AssignmentType.MANUAL,
        )

        new_student = self._make_student(
            "H2", anier=True, accepted_dorm_type=self.hasmaha_dorm_type,
        )

        result = self._run([new_student], [room179, room176])
        self.assertEqual(result["successful_assignments"], 1, result["proposed_assignments"])
        self.assertEqual(self._assigned_building_number(result, new_student), 176)

        # The pre-existing occupant of 179 must remain untouched.
        existing_assignment = BedAssignment.objects.get(student=existing_occupant)
        self.assertEqual(existing_assignment.status, BedAssignment.Status.ACTIVE)
        self.assertEqual(existing_assignment.bed_id, room179.beds.first().id)

    def test_overflow_not_restricted_to_hardcoded_building_list(self):
        """Overflow must work through accepted DormType code 15, not a
        hard-coded {176,177,178,179} list — a brand-new building number
        (999) added to the SAME dorm type must be usable automatically
        with no code change, while Building 179 itself is full."""
        room179 = self._make_room(self.building_179, "1", bed_count=1)
        future_building = Building.objects.create(number=999, dorm_type=self.hasmaha_dorm_type)
        room_future = self._make_room(future_building, "1", bed_count=1)

        existing_occupant = self._make_student(
            "H_EXIST2", anier=True, accepted_dorm_type=self.hasmaha_dorm_type,
        )
        BedAssignment.objects.create(
            student=existing_occupant, bed=room179.beds.first(),
            status=BedAssignment.Status.ACTIVE,
            assignment_type=BedAssignment.AssignmentType.MANUAL,
        )

        new_student = self._make_student(
            "H3", anier=True, accepted_dorm_type=self.hasmaha_dorm_type,
        )

        result = self._run([new_student], [room179, room_future])
        self.assertEqual(result["successful_assignments"], 1, result["proposed_assignments"])
        self.assertEqual(self._assigned_building_number(result, new_student), 999)

    # ------------------------------------------------------------------
    # Regression test for a real production defect found by a production
    # validation run: an eligible Hasmaha ANIR student who also happens to
    # be is_priority (the common case — the Excel import pipeline sets
    # is_priority=True as a side effect of populating special_status_1..4,
    # so most ANIR students are also generic-priority students) was being
    # offered candidates in completely unrelated dorm types, because the
    # pre-existing generic is_priority bypass in
    # _should_enforce_accepted_dorm_type was firing for them too — a
    # subset of the eligible ANIR students in that run leaked into
    # unrelated DormType codes. This test reproduces the exact shape of that bug:
    # Building 179 unavailable, a compatible bed available in DormType 15
    # (valid overflow) AND a compatible bed available in an unrelated
    # DormType (the leak this test must prove no longer happens), all in
    # the same solver call.
    # ------------------------------------------------------------------

    def test_hasmaha_anier_priority_student_overflows_within_dormtype_not_to_unrelated_dorm_type(self):
        room179 = self._make_room(self.building_179, "1", bed_count=1)
        room176 = self._make_room(self.building_176, "1", bed_count=1)
        unrelated_room = self._make_room(self.other_upper_building, "1", bed_count=1)

        existing_occupant = self._make_student(
            "REG_EXIST", anier=True, accepted_dorm_type=self.hasmaha_dorm_type,
        )
        BedAssignment.objects.create(
            student=existing_occupant, bed=room179.beds.first(),
            status=BedAssignment.Status.ACTIVE,
            assignment_type=BedAssignment.AssignmentType.MANUAL,
        )

        student = self._make_student(
            "REG1", anier=True, priority=True, accepted_dorm_type=self.hasmaha_dorm_type,
        )

        result = self._run([student], [room179, room176, unrelated_room])
        self.assertEqual(result["successful_assignments"], 1, result["proposed_assignments"])
        self.assertEqual(
            self._assigned_building_number(result, student),
            self.building_176.number,
            "An eligible Hasmaha ANIR student who is also is_priority must "
            "overflow within DormType 15, never leak into an unrelated "
            "dorm type merely because a compatible bed exists there.",
        )

    def test_hasmaha_anier_priority_student_prefers_179_when_available(self):
        """The is_priority side effect must not disturb the ordinary
        Building-179 preference when 179 is actually available."""
        room179 = self._make_room(self.building_179, "1", bed_count=2)
        unrelated_room = self._make_room(self.other_upper_building, "1", bed_count=2)

        student = self._make_student(
            "REG2", anier=True, priority=True, accepted_dorm_type=self.hasmaha_dorm_type,
        )

        result = self._run([student], [room179, unrelated_room])
        self.assertEqual(result["successful_assignments"], 1, result["proposed_assignments"])
        self.assertEqual(self._assigned_building_number(result, student), 179)

    # ------------------------------------------------------------------
    # 4/5. Ordinary and generic-priority (non-eligible) students cannot
    #      automatically enter Building 179.
    # ------------------------------------------------------------------

    def test_ordinary_student_cannot_enter_building_179_automatically(self):
        room179 = self._make_room(self.building_179, "1", bed_count=2)
        student = self._make_student("O1", priority=False, anier=False)

        result = self._run([student], [room179])
        self.assertEqual(result["successful_assignments"], 0, result["proposed_assignments"])
        self.assertIn(student.id, result["students_with_no_feasible_beds"])

    def test_generic_priority_non_anier_student_cannot_enter_building_179_automatically(self):
        """is_priority=True alone (no אנייר marker) must never be
        sufficient to enter Building 179 automatically."""
        room179 = self._make_room(self.building_179, "1", bed_count=2)
        student = self._make_student("O2", priority=True, anier=False)

        result = self._run([student], [room179])
        self.assertEqual(result["successful_assignments"], 0, result["proposed_assignments"])
        self.assertIn(student.id, result["students_with_no_feasible_beds"])

    # ------------------------------------------------------------------
    # Regression guard: the pre-existing generic is_priority bypass in
    # _should_enforce_accepted_dorm_type is unrelated to the ANIR fix
    # above and must keep working exactly as before for non-ANIR
    # students — the accepted-dorm-type fix only tightens enforcement for
    # אנייר-marked students, it must not affect anyone else.
    # ------------------------------------------------------------------

    def test_generic_priority_non_anier_student_still_bypasses_accepted_dorm_type(self):
        """A non-ANIR priority student may still be placed outside their
        imported accepted_dorm_type — this pre-existing, unrelated
        behavior must be untouched by the ANIR accepted-dorm-type fix."""
        other_room = self._make_room(self.other_upper_building, "1", bed_count=2)

        student = self._make_student(
            "GEN_PRI1", priority=True, anier=False,
            accepted_dorm_type=self.hasmaha_dorm_type,
        )

        result = self._run([student], [other_room])
        self.assertEqual(result["successful_assignments"], 1, result["proposed_assignments"])
        self.assertEqual(
            self._assigned_building_number(result, student),
            self.other_upper_building.number,
        )

    def test_non_priority_non_anier_student_respects_accepted_dorm_type(self):
        """An ordinary non-priority, non-ANIR student is only assignable
        within their imported accepted_dorm_type — unrelated to, and
        unaffected by, the ANIR accepted-dorm-type fix."""
        room179 = self._make_room(self.building_179, "1", bed_count=2)
        other_room = self._make_room(self.other_upper_building, "1", bed_count=2)

        student = self._make_student(
            "GEN_STRICT1", priority=False, anier=False,
            accepted_dorm_type=self.other_upper_dorm_type,
        )

        result = self._run([student], [room179, other_room])
        self.assertEqual(result["successful_assignments"], 1, result["proposed_assignments"])
        self.assertEqual(
            self._assigned_building_number(result, student),
            self.other_upper_building.number,
        )

    # ------------------------------------------------------------------
    # 6/8. Case B: an ANIR student whose accepted dorm type is not code 15
    #      stays in that dorm type — never redirected to 179, and the אנייר
    #      marker never waives accepted-dorm-type enforcement by itself.
    # ------------------------------------------------------------------

    def test_anier_student_in_other_upper_region_dorm_type_stays_in_accepted_dorm_type(self):
        """An ANIR-marked student accepted into a DIFFERENT dorm type
        (still inside גוש עליון, the same region as כפר הסמכה) must be
        assigned within that accepted dorm type, never redirected to
        Building 179."""
        room179 = self._make_room(self.building_179, "1", bed_count=2)
        other_room = self._make_room(self.other_upper_building, "1", bed_count=2)

        student = self._make_student(
            "B1", anier=True, accepted_dorm_type=self.other_upper_dorm_type,
        )

        result = self._run([student], [room179, other_room])
        self.assertEqual(result["successful_assignments"], 1, result["proposed_assignments"])
        self.assertEqual(
            self._assigned_building_number(result, student),
            self.other_upper_building.number,
        )

    def test_anier_student_not_allowed_to_cross_accepted_dorm_types_merely_because_of_marker(self):
        """Confirms the accepted-dorm-type fix directly: the אנייר marker
        by itself must not waive accepted_dorm_type enforcement. A non-
        priority ANIR student accepted into the OTHER dorm type, with only
        a Building-179 bed available, must remain unassigned rather than
        being admitted into Building 179."""
        room179 = self._make_room(self.building_179, "1", bed_count=2)

        student = self._make_student(
            "B2", priority=False, anier=True, accepted_dorm_type=self.other_upper_dorm_type,
        )

        result = self._run([student], [room179])
        self.assertEqual(result["successful_assignments"], 0, result["proposed_assignments"])
        self.assertIn(student.id, result["students_with_no_feasible_beds"])

    def test_anier_priority_student_not_allowed_to_cross_accepted_dorm_types_merely_because_of_marker(self):
        """Same as above, but with is_priority=True — the exact
        combination that reproduced the production regression:
        an ANIR student accepted into a different dorm type, who also
        carries is_priority=True, must still be confined to their own
        accepted dorm type. A compatible bed in Building 179 AND a
        compatible bed in a third, unrelated dorm type are both available;
        neither may be used — only their own accepted dorm type."""
        room179 = self._make_room(self.building_179, "1", bed_count=2)
        third_dorm_type = DormType.objects.create(
            name="ThirdUnrelatedDorm", region=self.upper_region,
        )
        third_building = Building.objects.create(number=301, dorm_type=third_dorm_type)
        third_room = self._make_room(third_building, "1", bed_count=2)
        own_room = self._make_room(self.other_upper_building, "1", bed_count=2)

        student = self._make_student(
            "B2_PRI", priority=True, anier=True, accepted_dorm_type=self.other_upper_dorm_type,
        )

        result = self._run([student], [room179, third_room, own_room])
        self.assertEqual(result["successful_assignments"], 1, result["proposed_assignments"])
        self.assertEqual(
            self._assigned_building_number(result, student),
            self.other_upper_building.number,
            "A priority ANIR student accepted into a different dorm type "
            "must stay confined to that accepted dorm type, never "
            "Building 179 and never a third unrelated dorm type.",
        )

    # ------------------------------------------------------------------
    # 7. Case C: an ANIR student in another region (no כפר הסמכה inventory
    #    in this run at all) is assigned normally, without needing a
    #    dedicated ANIR building.
    # ------------------------------------------------------------------

    def test_anier_student_in_other_region_can_be_assigned_without_dedicated_building(self):
        """An ANIR-marked student accepted into a dorm type in an entirely
        different region (no כפר הסמכה inventory anywhere in this run) must
        still be assigned normally, as an ordinary priority student — a
        dedicated ANIR building is not required outside גוש עליון."""
        ordinary_dorm_type = DormType.objects.create(
            name="OtherRegionOrdinary", region=self.other_region,
        )
        ordinary_building = Building.objects.create(number=301, dorm_type=ordinary_dorm_type)
        other_room = self._make_room(ordinary_building, "1", bed_count=2)

        student = self._make_student(
            "C1", anier=True, priority=True, accepted_dorm_type=ordinary_dorm_type,
        )

        result = self._run([student], [other_room])
        self.assertEqual(result["successful_assignments"], 1, result["proposed_assignments"])
        self.assertEqual(self._assigned_building_number(result, student), 301)

    def test_building_179_in_other_region_is_not_exclusive(self):
        """A building numbered 179 belonging to an unrelated (non-Hasmaha)
        dorm type behaves like any ordinary building — an ordinary student
        may freely enter it."""
        other_room179 = self._make_room(self.other_region_building_179, "1", bed_count=2)
        student = self._make_student("SCOPE1", priority=False)

        result = self._run([student], [other_room179])
        self.assertEqual(result["successful_assignments"], 1, result["proposed_assignments"])

    # ------------------------------------------------------------------
    # 9/10/11. Hard constraints always override the Building-179 preference.
    # ------------------------------------------------------------------

    def test_building_179_preference_never_overrides_gender(self):
        room179_male = self._make_room(
            self.building_179, "1", category=Apartment.Category.MALE, bed_count=2,
        )
        female_student = self._make_student(
            "G1", gender=Student.Gender.FEMALE, anier=True,
            accepted_dorm_type=self.hasmaha_dorm_type,
        )

        result = self._run([female_student], [room179_male])
        self.assertEqual(result["successful_assignments"], 0, result["proposed_assignments"])

    def test_building_179_preference_never_overrides_religion(self):
        """A Religious Jewish and a Religious Muslim eligible Hasmaha ANIR
        student cannot share the one Building-179 apartment under hard
        ReligiousTogether; both must still be assigned, split across
        Building 179 and the overflow building instead."""
        room179 = self._make_room(self.building_179, "1", bed_count=2)
        room176 = self._make_room(self.building_176, "1", bed_count=2)

        rj_student = self._make_student(
            "RJ1", anier=True, accepted_dorm_type=self.hasmaha_dorm_type,
            religion=Student.Religion.Jewish, religious=Student.Religious.RELIGIOUS,
        )
        muslim_student = self._make_student(
            "RM1", anier=True, accepted_dorm_type=self.hasmaha_dorm_type,
            religion=Student.Religion.Muslim, religious=Student.Religious.RELIGIOUS,
        )

        result = self._run([rj_student, muslim_student], [room179, room176])
        self.assertEqual(result["successful_assignments"], 2, result["proposed_assignments"])
        self.assertNotEqual(
            self._assigned_building_number(result, rj_student),
            self._assigned_building_number(result, muslim_student),
        )

    def test_building_179_preference_never_overrides_housing_type(self):
        """An eligible Hasmaha ANIR COUPLE-housing student cannot be forced
        into a SINGLE-only Building-179 apartment; with no compatible
        apartment type available anywhere, they remain unassigned rather
        than being placed incompatibly."""
        room179_single = self._make_room(
            self.building_179, "1",
            category=Apartment.Category.FEMALE,
            apartment_type=Apartment.ApartmentType.SINGLE,
            bed_count=2,
        )
        couple_student = self._make_student(
            "HT1", anier=True, accepted_dorm_type=self.hasmaha_dorm_type,
            housing_type=Student.HousingType.COUPLE,
        )

        result = self._run([couple_student], [room179_single])
        self.assertEqual(result["successful_assignments"], 0, result["proposed_assignments"])

    # ------------------------------------------------------------------
    # 12/13. Couples/families use the correct apartment type within
    #        Hasmaha inventory (Excel-confirmed: Building 179 spans both
    #        "רווקים/רווקות" and "זוגות" sections).
    # ------------------------------------------------------------------

    def test_couples_anier_student_uses_appropriate_couples_apartment(self):
        room179_couple = self._make_room(
            self.building_179, "1",
            category=Apartment.Category.MIXED,
            apartment_type=Apartment.ApartmentType.COUPLE,
            bed_count=2,
        )
        couple_student = self._make_student(
            "CP1", anier=True, accepted_dorm_type=self.hasmaha_dorm_type,
            housing_type=Student.HousingType.COUPLE,
        )

        result = self._run([couple_student], [room179_couple])
        self.assertEqual(result["successful_assignments"], 1, result["proposed_assignments"])
        self.assertEqual(self._assigned_building_number(result, couple_student), 179)

    def test_family_anier_student_uses_appropriate_family_apartment(self):
        room176_family = self._make_room(
            self.building_176, "1",
            category=Apartment.Category.MIXED,
            apartment_type=Apartment.ApartmentType.FAMILY,
            bed_count=3,
        )
        family_student = self._make_student(
            "FM1", anier=True, accepted_dorm_type=self.hasmaha_dorm_type,
            housing_type=Student.HousingType.FAMILY,
        )

        result = self._run([family_student], [room176_family])
        self.assertEqual(result["successful_assignments"], 1, result["proposed_assignments"])
        self.assertEqual(self._assigned_building_number(result, family_student), 176)

    # ------------------------------------------------------------------
    # 14. Inactive Building-179 inventory is never counted as usable
    #     capacity — the student must overflow instead.
    # ------------------------------------------------------------------

    def test_inactive_179_inventory_not_counted(self):
        inactive_room179 = self._make_room(
            self.building_179, "1", bed_count=2, is_active=False,
        )
        active_room176 = self._make_room(self.building_176, "1", bed_count=2)

        student = self._make_student(
            "IA1", anier=True, accepted_dorm_type=self.hasmaha_dorm_type,
        )

        result = self._run([student], [inactive_room179, active_room176])
        self.assertEqual(result["successful_assignments"], 1, result["proposed_assignments"])
        self.assertEqual(self._assigned_building_number(result, student), 176)

    # ------------------------------------------------------------------
    # 15. Existing occupants of Building 179 are never modified.
    # ------------------------------------------------------------------

    def test_existing_occupants_of_179_remain_untouched(self):
        room179 = self._make_room(self.building_179, "1", bed_count=2)

        legacy_occupant = self._make_student("LEGACY1", priority=False)
        legacy_bed = room179.beds.first()
        BedAssignment.objects.create(
            student=legacy_occupant, bed=legacy_bed,
            status=BedAssignment.Status.ACTIVE,
            assignment_type=BedAssignment.AssignmentType.MANUAL,
        )

        other_student = self._make_student("OTHER1", priority=False)
        room176 = self._make_room(self.building_176, "1", bed_count=2)

        result = self._run([other_student], [room179, room176])

        legacy_assignment = BedAssignment.objects.get(student=legacy_occupant)
        self.assertEqual(legacy_assignment.status, BedAssignment.Status.ACTIVE)
        self.assertEqual(legacy_assignment.bed_id, legacy_bed.id)

        self.assertTrue(
            any(
                "179" in warning and "eligible Hasmaha ANIR" in warning
                for warning in result["warnings"]
            ),
            f"Expected a building-179 existing-occupant warning, got: {result['warnings']}",
        )

    # ------------------------------------------------------------------
    # 16. Persistence records the actual overflow destination correctly.
    # ------------------------------------------------------------------

    def test_persistence_records_actual_overflow_destination(self):
        room179 = self._make_room(self.building_179, "1", bed_count=1)
        room176 = self._make_room(self.building_176, "1", bed_count=1)

        existing_occupant = self._make_student(
            "P_EXIST", anier=True, accepted_dorm_type=self.hasmaha_dorm_type,
        )
        BedAssignment.objects.create(
            student=existing_occupant, bed=room179.beds.first(),
            status=BedAssignment.Status.ACTIVE,
            assignment_type=BedAssignment.AssignmentType.MANUAL,
        )

        student = self._make_student(
            "P1", anier=True, accepted_dorm_type=self.hasmaha_dorm_type,
        )

        result = self._run([student], [room179, room176])
        self.assertTrue(result["solution_persisted"])

        persisted = BedAssignment.objects.get(student=student, status=BedAssignment.Status.ACTIVE)
        self.assertEqual(persisted.bed.room.apartment.building.number, 176)

        student.refresh_from_db()
        self.assertEqual(student.assigned_room_id, persisted.bed.room_id)

    # ------------------------------------------------------------------
    # Diagnostics: reflect the new eligibility/overflow/unassigned counts.
    # ------------------------------------------------------------------

    def test_anier_building_179_diagnostics_report_overflow_and_unassigned(self):
        room179 = self._make_room(self.building_179, "1", bed_count=1)
        room176 = self._make_room(self.building_176, "1", bed_count=1)

        overflowed = self._make_student(
            "DIAG_OVER", anier=True, accepted_dorm_type=self.hasmaha_dorm_type,
        )
        in_179 = self._make_student(
            "DIAG_179", anier=True, accepted_dorm_type=self.hasmaha_dorm_type,
        )
        unplaceable = self._make_student(
            "DIAG_UNPLACED", anier=True, accepted_dorm_type=self.hasmaha_dorm_type,
            gender=Student.Gender.MALE,
        )
        not_hasmaha_accepted = self._make_student(
            "DIAG_NOTHASMAHA", anier=True, accepted_dorm_type=self.other_upper_dorm_type,
        )

        result = self._run(
            [overflowed, in_179, unplaceable, not_hasmaha_accepted], [room179, room176],
        )

        diagnostics = result["anier_building_179_diagnostics"]
        self.assertEqual(diagnostics["imported_anier_students"], 4)
        self.assertEqual(diagnostics["eligible_hasmaha_anier_students"], 3)
        self.assertTrue(diagnostics["reserved_building_found"])
        self.assertEqual(diagnostics["assigned_to_building_179"], 1)
        self.assertEqual(diagnostics["assigned_via_overflow_in_dorm_type"], 1)
        self.assertEqual(diagnostics["unassigned_eligible_hasmaha_anier"], 1)
        # Defensive counter: must be 0 for a valid run — see
        # test_anier_building_179_diagnostics_never_counts_cross_dorm_type_leak_as_overflow
        # for the case that specifically stresses this counter with a
        # tempting unrelated-dorm-type bed present.
        self.assertEqual(diagnostics["assigned_outside_hasmaha_dorm_type"], 0)
        self.assertFalse(
            any("assigned outside DormType 15" in warning for warning in result["warnings"]),
        )

    def test_anier_building_179_diagnostics_never_counts_cross_dorm_type_leak_as_overflow(self):
        """Regression coverage for the diagnostics-side half of the run-113
        bug: an eligible Hasmaha ANIR student who is also is_priority, with
        a tempting compatible bed available in an unrelated dorm type
        alongside genuine DormType-15 overflow capacity, must be counted
        under assigned_via_overflow_in_dorm_type (not
        assigned_outside_hasmaha_dorm_type) precisely because the
        accepted-dorm-type fix keeps them out of the unrelated dorm type
        in the first place — the defensive counter stays at 0."""
        room179 = self._make_room(self.building_179, "1", bed_count=1)
        room176 = self._make_room(self.building_176, "1", bed_count=1)
        unrelated_room = self._make_room(self.other_upper_building, "1", bed_count=1)

        existing_occupant = self._make_student(
            "DIAG_LEAK_EXIST", anier=True, accepted_dorm_type=self.hasmaha_dorm_type,
        )
        BedAssignment.objects.create(
            student=existing_occupant, bed=room179.beds.first(),
            status=BedAssignment.Status.ACTIVE,
            assignment_type=BedAssignment.AssignmentType.MANUAL,
        )

        student = self._make_student(
            "DIAG_LEAK1", anier=True, priority=True, accepted_dorm_type=self.hasmaha_dorm_type,
        )

        result = self._run([student], [room179, room176, unrelated_room])

        diagnostics = result["anier_building_179_diagnostics"]
        self.assertEqual(diagnostics["assigned_via_overflow_in_dorm_type"], 1)
        self.assertEqual(diagnostics["assigned_outside_hasmaha_dorm_type"], 0)
        self.assertEqual(
            self._assigned_building_number(result, student), self.building_176.number,
        )

    def test_anier_building_179_diagnostics_when_building_missing(self):
        """When Building 179 itself is not part of this run's inventory
        (e.g. room data not yet imported for it), diagnostics must report
        reserved_building_found=False, and the eligible student must still
        be actually assigned normally within their accepted dorm type —
        not merely silently excluded."""
        room176 = self._make_room(self.building_176, "1", bed_count=1)

        eligible_anier = self._make_student(
            "DIAG_MISSING1", anier=True, accepted_dorm_type=self.hasmaha_dorm_type,
        )

        # Deliberately omit any Building-179 room from this run's inventory.
        result = self._run([eligible_anier], [room176])

        diagnostics = result["anier_building_179_diagnostics"]
        self.assertEqual(diagnostics["eligible_hasmaha_anier_students"], 1)
        self.assertFalse(diagnostics["reserved_building_found"])
        self.assertEqual(diagnostics["reserved_building_available_beds"], 0)

        assigned_ids = {item["student_db_id"] for item in result["proposed_assignments"]}
        self.assertIn(eligible_anier.id, assigned_ids)
        self.assertEqual(self._assigned_building_number(result, eligible_anier), 176)


# ---------------------------------------------------------------------------
# Manual staff override of the Building-179 automatic-allocation policy.
#
# Confirmed business rule: the ANIR/Building-179 preference is an
# automatic-allocation rule only. Authorized staff may still manually
# assign any student into Building 179, or move an eligible ANIR student
# out of it, via the ordinary manual assignment endpoints. These endpoints
# (assign_student_room / move_student_room, backed by
# validate_apartment_assignment) deliberately never call
# _may_use_building_179_automatically or any other ANIR-specific helper —
# these tests are a positive-path regression guard against a future,
# incorrect hard block being added there.
# ---------------------------------------------------------------------------

class ManualBuilding179OverrideTest(TestCase):
    def setUp(self):
        self.region = _make_region("ManualOverrideRegion")
        self.admin = _make_central_admin()
        self.dorm_type = DormType.objects.create(
            name="כפר הסמכה", code=15, region=self.region,
        )
        self.building_179 = Building.objects.create(number=179, dorm_type=self.dorm_type)

        self.apartment = Apartment.objects.create(
            building=self.building_179, number="1",
            category=Apartment.Category.FEMALE,
            apartment_type=Apartment.ApartmentType.SINGLE,
            room_count=1,
        )
        self.room = Room.objects.create(apartment=self.apartment, name="A", capacity=2)
        self.bed_1 = Bed.objects.create(room=self.room, label="1")
        self.bed_2 = Bed.objects.create(room=self.room, label="2")

        self.client = APIClient()
        self.client.force_authenticate(user=self.admin)

    def test_staff_can_manually_assign_non_anier_student_into_building_179(self):
        """A non-ANIR student may be manually assigned into Building 179 —
        the manual endpoint must not enforce the automatic-allocation-only
        ANIR eligibility rule."""
        student = Student.objects.create(
            student_id="MANUAL_NONANIER1", first_name="T", last_name="S",
            gender=Student.Gender.FEMALE, housing_type=Student.HousingType.SINGLE_FEMALE,
            accepted_dorm_type=self.dorm_type,
        )

        response = self.client.post(
            "/api/room-assignments/assign/",
            {"student_id": student.id, "room_id": self.room.id},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)

        student.refresh_from_db()
        self.assertEqual(student.assigned_room_id, self.room.id)

    def test_staff_can_manually_move_eligible_anier_student_out_of_building_179(self):
        """An eligible Hasmaha ANIR student already in Building 179 may be
        manually moved to an ordinary building — the manual endpoint must
        not lock them into 179."""
        anier_student = Student.objects.create(
            student_id="MANUAL_ANIER1", first_name="T", last_name="S",
            gender=Student.Gender.FEMALE, housing_type=Student.HousingType.SINGLE_FEMALE,
            accepted_dorm_type=self.dorm_type, special_status_1="אנייר",
        )
        BedAssignment.objects.create(
            student=anier_student, bed=self.bed_1,
            status=BedAssignment.Status.ACTIVE,
            assignment_type=BedAssignment.AssignmentType.MANUAL,
        )
        anier_student.assigned_room = self.room
        anier_student.save(update_fields=["assigned_room"])

        other_building = Building.objects.create(number=176, dorm_type=self.dorm_type)
        other_apartment = Apartment.objects.create(
            building=other_building, number="1",
            category=Apartment.Category.FEMALE,
            apartment_type=Apartment.ApartmentType.SINGLE,
            room_count=1,
        )
        other_room = Room.objects.create(apartment=other_apartment, name="A", capacity=1)
        Bed.objects.create(room=other_room, label="1")

        response = self.client.post(
            "/api/room-assignments/move/",
            {"student_id": anier_student.id, "room_id": other_room.id},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)

        anier_student.refresh_from_db()
        self.assertEqual(anier_student.assigned_room_id, other_room.id)

        old_assignment = BedAssignment.objects.get(student=anier_student, bed=self.bed_1)
        self.assertEqual(old_assignment.status, BedAssignment.Status.ENDED)
