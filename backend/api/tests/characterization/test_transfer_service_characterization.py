from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APIClient

from api.models import (
    Apartment,
    Bed,
    BedAssignment,
    Building,
    DormType,
    Region,
    Student,
    StudentRequest,
    Transfer,
    User,
)
from api.views import (
    _assignment_snapshot,
    _student_current_region_id,
    _user_can_cancel_request,
    _user_can_review_request,
)


class TransferServiceCharacterizationFixtures(TestCase):
    def setUp(self):
        self.region_a = Region.objects.create(id="A", name="Region A")
        self.region_b = Region.objects.create(id="B", name="Region B")
        self.region_c = Region.objects.create(id="C", name="Region C")
        self.dorm_a = DormType.objects.create(code=101, name="Dorm A", region=self.region_a)
        self.dorm_b = DormType.objects.create(code=102, name="Dorm B", region=self.region_b)
        self.dorm_c = DormType.objects.create(code=103, name="Dorm C", region=self.region_c)

        self.central = self._user("central", User.Role.CENTRAL_ADMIN)
        self.boss_a = self._user("boss-a", User.Role.REGION_BOSS, self.region_a)
        self.boss_b = self._user("boss-b", User.Role.REGION_BOSS, self.region_b)
        self.boss_c = self._user("boss-c", User.Role.REGION_BOSS, self.region_c)
        self.employee_a = self._user("employee-a", User.Role.EMPLOYEE, self.region_a)
        self.employee_b = self._user("employee-b", User.Role.EMPLOYEE, self.region_b)
        self.no_region_boss = self._user("boss-none", User.Role.REGION_BOSS)

        self.room_a1 = self._room(self.dorm_a, "A1", capacity=2)
        self.room_a2 = self._room(self.dorm_a, "A2", capacity=2)
        self.room_b1 = self._room(self.dorm_b, "B1", capacity=2)
        self.room_c1 = self._room(self.dorm_c, "C1", capacity=2)

    def _user(self, username, role, region=None):
        return User.objects.create_user(
            username=username,
            email=f"{username}@example.test",
            password="test-pass",
            role=role,
            region=region,
        )

    def _client(self, user):
        client = APIClient()
        client.force_authenticate(user=user)
        return client

    def _room(self, dorm_type, suffix, capacity=2):
        building_number = Building.objects.count() + 1
        building = Building.objects.create(
            number=building_number, dorm_type=dorm_type, is_active=True
        )
        apartment = Apartment.objects.create(
            building=building,
            number=f"APT-{suffix}",
            category=Apartment.Category.MALE,
            apartment_type=Apartment.ApartmentType.SINGLE,
            room_count=1,
            apartment_capacity=capacity,
        )
        room = apartment.rooms.create(
            name=f"Room {suffix}",
            capacity=capacity,
            is_active=True,
        )
        for position in range(1, capacity + 1):
            Bed.objects.create(room=room, label=str(position))
        return room

    def _student(self, student_id, accepted_dorm=None, assigned_room=None):
        return Student.objects.create(
            student_id=student_id,
            first_name=f"First-{student_id}",
            last_name="Student",
            gender=Student.Gender.MALE,
            housing_type=Student.HousingType.SINGLE_MALE,
            accepted_dorm_type=accepted_dorm,
            assigned_room=assigned_room,
        )

    def _place(self, student, room, status=BedAssignment.Status.ACTIVE):
        used = BedAssignment.objects.filter(
            bed__room=room, status=BedAssignment.Status.ACTIVE
        ).values_list("bed_id", flat=True)
        bed = room.beds.exclude(id__in=used).order_by("label").first()
        assignment = BedAssignment.objects.create(
            student=student,
            bed=bed,
            status=status,
            assigned_by=self.central,
            assignment_type=BedAssignment.AssignmentType.MANUAL,
            ended_at=timezone.now() if status == BedAssignment.Status.ENDED else None,
        )
        student.assigned_room = room
        student.save(update_fields=["assigned_room"])
        return assignment

    def _request(self, request_type, **overrides):
        sequence = StudentRequest.objects.count() + 1
        values = {
            "request_number": f"REQ-CHAR-{sequence:03d}",
            "request_type": request_type,
            "reason": "characterization",
            "requested_by": self.boss_a,
            "status": StudentRequest.Status.PENDING,
        }
        values.update(overrides)
        return StudentRequest.objects.create(**values)

    def _approve(self, req, user=None, data=None):
        return self._client(user or self.boss_a).put(
            f"/api/requests/{req.pk}/approve/", data or {}, format="json"
        )

    def _assert_approved(self, req, reviewer):
        req.refresh_from_db()
        self.assertEqual(req.status, StudentRequest.Status.APPROVED)
        self.assertEqual(req.reviewed_by_id, reviewer.id)
        self.assertIsNotNone(req.reviewed_at)


class AssignmentAndRegionHelperCharacterizationTests(
    TransferServiceCharacterizationFixtures
):
    def test_assignment_snapshot_none_and_unassigned_exact_output(self):
        student = self._student("SNAP-NONE", self.dorm_a)

        self.assertEqual(_assignment_snapshot(None), {"assigned": False})
        self.assertEqual(_assignment_snapshot(student), {"assigned": False})

    def test_assignment_snapshot_active_exact_order_values_types_and_two_active_reads(self):
        student = self._student("SNAP-ACTIVE", self.dorm_a)
        assignment = self._place(student, self.room_a1)
        student.refresh_from_db()

        with CaptureQueriesContext(connection) as captured:
            snapshot = _assignment_snapshot(student)

        self.assertEqual(
            list(snapshot),
            [
                "assigned",
                "assignment_id",
                "region_id",
                "region_name",
                "building_id",
                "building_number",
                "apartment_id",
                "apartment_number",
                "room_id",
                "room_name",
                "bed_id",
                "bed_label",
            ],
        )
        self.assertEqual(
            snapshot,
            {
                "assigned": True,
                "assignment_id": assignment.id,
                "region_id": self.region_a.id,
                "region_name": self.region_a.name,
                "building_id": self.room_a1.apartment.building_id,
                "building_number": self.room_a1.apartment.building.number,
                "apartment_id": self.room_a1.apartment_id,
                "apartment_number": self.room_a1.apartment.number,
                "room_id": self.room_a1.id,
                "room_name": self.room_a1.name,
                "bed_id": assignment.bed_id,
                "bed_label": assignment.bed.label,
            },
        )
        self.assertIs(snapshot["assigned"], True)
        for key in (
            "assignment_id",
            "building_id",
            "apartment_id",
            "room_id",
            "bed_id",
        ):
            self.assertIsInstance(snapshot[key], int)
        bed_assignment_queries = [
            query["sql"]
            for query in captured.captured_queries
            if "api_bedassignment" in query["sql"].replace('"', "").lower()
        ]
        self.assertEqual(len(bed_assignment_queries), 2)
        for sql in bed_assignment_queries:
            self.assertIn("active", sql.lower())

    def test_assignment_snapshot_assigned_room_with_ended_only_history(self):
        student = self._student("SNAP-ENDED", self.dorm_a)
        assignment = self._place(student, self.room_a1, BedAssignment.Status.ENDED)
        student.refresh_from_db()

        snapshot = _assignment_snapshot(student)

        self.assertEqual(snapshot["assigned"], True)
        self.assertIsNone(snapshot["assignment_id"])
        self.assertEqual(snapshot["region_id"], self.region_a.id)
        self.assertEqual(snapshot["building_id"], self.room_a1.apartment.building_id)
        self.assertEqual(snapshot["apartment_id"], self.room_a1.apartment_id)
        self.assertEqual(snapshot["room_id"], self.room_a1.id)
        self.assertIsNone(snapshot["bed_id"])
        self.assertIsNone(snapshot["bed_label"])
        self.assertEqual(assignment.status, BedAssignment.Status.ENDED)

    def test_student_current_region_id_all_fallback_branches(self):
        assigned = self._student("REGION-ASSIGNED", self.dorm_b)
        self._place(assigned, self.room_a1)
        assigned.refresh_from_db()
        accepted_only = self._student("REGION-ACCEPTED", self.dorm_b)
        unanchored = self._student("REGION-NONE")

        orphan_building = Building.objects.create(number=999, dorm_type=None, is_active=True)
        orphan_apartment = Apartment.objects.create(
            building=orphan_building,
            number="APT-ORPHAN",
            category=Apartment.Category.MALE,
            apartment_type=Apartment.ApartmentType.SINGLE,
            room_count=1,
            apartment_capacity=1,
        )
        orphan_room = orphan_apartment.rooms.create(
            name="Orphan Room",
            capacity=1,
            is_active=True,
        )
        fallback = self._student("REGION-FALLBACK", self.dorm_c, orphan_room)

        self.assertIsNone(_student_current_region_id(None))
        self.assertEqual(_student_current_region_id(assigned), self.region_a.id)
        self.assertEqual(_student_current_region_id(accepted_only), self.region_b.id)
        self.assertIsNone(_student_current_region_id(unanchored))
        self.assertEqual(_student_current_region_id(fallback), self.region_c.id)


class RequestPolicyCharacterizationTests(TransferServiceCharacterizationFixtures):
    def test_review_policy_central_employee_and_no_region_boss(self):
        req = self._request(StudentRequest.RequestType.OTHER)

        self.assertTrue(_user_can_review_request(self.central, req))
        self.assertFalse(_user_can_review_request(self.employee_a, req))
        self.assertFalse(_user_can_review_request(self.no_region_boss, req))

    def test_review_policy_region_transfer_destination_only(self):
        student = self._student("REVIEW-REGION", self.dorm_a)
        req = self._request(
            StudentRequest.RequestType.REGION_TRANSFER,
            student=student,
            source_region=self.region_a,
            target_region=self.region_b,
        )

        self.assertTrue(_user_can_review_request(self.boss_b, req))
        self.assertFalse(_user_can_review_request(self.boss_a, req))
        self.assertFalse(_user_can_review_request(self.boss_c, req))

    def test_review_policy_student_accepted_region(self):
        student = self._student("REVIEW-ACCEPTED", self.dorm_a)
        req = self._request(StudentRequest.RequestType.OTHER, student=student)

        self.assertTrue(_user_can_review_request(self.boss_a, req))
        self.assertFalse(_user_can_review_request(self.boss_b, req))

    def test_review_policy_target_room_without_accepted_region(self):
        student = self._student("REVIEW-TARGET")
        req = self._request(
            StudentRequest.RequestType.ROOM,
            student=student,
            target_room=self.room_b1,
        )

        self.assertTrue(_user_can_review_request(self.boss_b, req))
        self.assertFalse(_user_can_review_request(self.boss_a, req))

    def test_review_policy_unanchored_add_student_allows_regional_boss(self):
        req = self._request(StudentRequest.RequestType.ADD_STUDENT)

        self.assertTrue(_user_can_review_request(self.boss_a, req))
        self.assertTrue(_user_can_review_request(self.boss_b, req))

    def test_cancel_action_requester_employee_short_circuit(self):
        req = self._request(
            StudentRequest.RequestType.OTHER, requested_by=self.employee_a
        )

        response = self._client(self.employee_a).put(
            f"/api/requests/{req.pk}/cancel/", {}, format="json"
        )

        self.assertEqual(response.status_code, 200)
        req.refresh_from_db()
        self.assertEqual(req.status, StudentRequest.Status.CANCELLED)

    def test_cancel_policy_central_employee_and_no_region_boss(self):
        req = self._request(StudentRequest.RequestType.OTHER)

        self.assertTrue(_user_can_cancel_request(self.central, req))
        self.assertFalse(_user_can_cancel_request(self.employee_a, req))
        self.assertFalse(_user_can_cancel_request(self.no_region_boss, req))

    def test_cancel_policy_region_transfer_source_destination_and_unrelated(self):
        student = self._student("CANCEL-REGION", self.dorm_a)
        req = self._request(
            StudentRequest.RequestType.REGION_TRANSFER,
            student=student,
            source_region=self.region_a,
            target_region=self.region_b,
        )

        self.assertTrue(_user_can_cancel_request(self.boss_a, req))
        self.assertFalse(_user_can_cancel_request(self.boss_b, req))
        self.assertFalse(_user_can_cancel_request(self.boss_c, req))

    def test_cancel_policy_missing_source_uses_current_region_and_non_region_delegates(self):
        student = self._student("CANCEL-FALLBACK", self.dorm_b)
        self._place(student, self.room_a1)
        student.refresh_from_db()
        region_req = self._request(
            StudentRequest.RequestType.REGION_TRANSFER,
            student=student,
            target_region=self.region_b,
            source_region=None,
        )
        ordinary_req = self._request(
            StudentRequest.RequestType.OTHER, student=student
        )

        self.assertTrue(_user_can_cancel_request(self.boss_a, region_req))
        self.assertFalse(_user_can_cancel_request(self.boss_b, region_req))
        self.assertEqual(
            _user_can_cancel_request(self.boss_b, ordinary_req),
            _user_can_review_request(self.boss_b, ordinary_req),
        )


class StudentRequestApprovalCharacterizationTests(
    TransferServiceCharacterizationFixtures
):
    def test_room_request_approval_moves_student_and_records_audit(self):
        student = self._student("APPROVE-ROOM", self.dorm_a)
        old_assignment = self._place(student, self.room_a1)
        req = self._request(
            StudentRequest.RequestType.ROOM,
            student=student,
            target_room=self.room_a2,
            current_assignment_snapshot={"assigned": True},
        )
        request_number = req.request_number

        response = self._approve(req)

        self.assertEqual(response.status_code, 200)
        self._assert_approved(req, self.boss_a)
        student.refresh_from_db()
        old_assignment.refresh_from_db()
        self.assertEqual(student.assigned_room_id, self.room_a2.id)
        self.assertEqual(old_assignment.status, BedAssignment.Status.ENDED)
        active = BedAssignment.objects.get(student=student, status="active")
        self.assertEqual(active.bed.room_id, self.room_a2.id)
        self.assertEqual(req.target_room_id, self.room_a2.id)
        self.assertEqual(req.final_assignment_id, active.id)
        self.assertEqual(req.request_number, request_number)

    def test_apartment_request_approval_moves_student_and_records_audit(self):
        student = self._student("APPROVE-APARTMENT", self.dorm_a)
        old_assignment = self._place(student, self.room_a1)
        req = self._request(
            StudentRequest.RequestType.APARTMENT,
            student=student,
            target_room=self.room_a2,
        )

        response = self._approve(req)

        self.assertEqual(response.status_code, 200)
        self._assert_approved(req, self.boss_a)
        student.refresh_from_db()
        old_assignment.refresh_from_db()
        self.assertEqual(student.assigned_room_id, self.room_a2.id)
        self.assertEqual(old_assignment.status, BedAssignment.Status.ENDED)
        self.assertEqual(req.final_assignment.bed.room_id, self.room_a2.id)

    def test_add_student_approval_without_and_with_target_room(self):
        no_room = self._request(
            StudentRequest.RequestType.ADD_STUDENT,
            student_data={
                "student_id": "NEW-NO-ROOM",
                "first_name": "New",
                "last_name": "NoRoom",
                "gender": Student.Gender.MALE,
                "housing_type": Student.HousingType.SINGLE_MALE,
            },
        )
        with_room = self._request(
            StudentRequest.RequestType.ADD_STUDENT,
            student_data={
                "student_id": "NEW-WITH-ROOM",
                "first_name": "New",
                "last_name": "WithRoom",
                "gender": Student.Gender.MALE,
                "housing_type": Student.HousingType.SINGLE_MALE,
            },
        )

        response_no_room = self._approve(no_room)
        response_with_room = self._approve(
            with_room, data={"target_room": self.room_a1.id}
        )

        self.assertEqual(response_no_room.status_code, 200)
        self.assertEqual(response_with_room.status_code, 200)
        self._assert_approved(no_room, self.boss_a)
        self._assert_approved(with_room, self.boss_a)
        created_no_room = Student.objects.get(student_id="NEW-NO-ROOM")
        created_with_room = Student.objects.get(student_id="NEW-WITH-ROOM")
        self.assertIsNone(created_no_room.assigned_room_id)
        self.assertEqual(created_with_room.assigned_room_id, self.room_a1.id)
        self.assertIsNone(no_room.final_assignment_id)
        self.assertEqual(with_room.target_room_id, self.room_a1.id)
        self.assertEqual(with_room.final_assignment.student_id, created_with_room.id)

    def test_remove_student_approval_with_and_without_active_assignment(self):
        assigned = self._student("REMOVE-ACTIVE", self.dorm_a)
        assignment = self._place(assigned, self.room_a1)
        unassigned = self._student("REMOVE-NONE", self.dorm_a)
        active_req = self._request(
            StudentRequest.RequestType.REMOVE_STUDENT, student=assigned
        )
        empty_req = self._request(
            StudentRequest.RequestType.REMOVE_STUDENT, student=unassigned
        )

        active_response = self._approve(active_req)
        empty_response = self._approve(empty_req)

        self.assertEqual(active_response.status_code, 200)
        self.assertEqual(empty_response.status_code, 200)
        self._assert_approved(active_req, self.boss_a)
        self._assert_approved(empty_req, self.boss_a)
        assigned.refresh_from_db()
        unassigned.refresh_from_db()
        assignment.refresh_from_db()
        self.assertIsNone(assigned.assigned_room_id)
        self.assertIsNone(unassigned.assigned_room_id)
        self.assertEqual(assignment.status, BedAssignment.Status.ENDED)
        self.assertFalse(
            BedAssignment.objects.filter(student=assigned, status="active").exists()
        )

    def test_swap_request_approval_swaps_both_students(self):
        first = self._student("SWAP-FIRST", self.dorm_a)
        second = self._student("SWAP-SECOND", self.dorm_a)
        first_assignment = self._place(first, self.room_a1)
        second_assignment = self._place(second, self.room_a2)
        first_original_room_id = first_assignment.bed.room_id
        second_original_room_id = second_assignment.bed.room_id
        req = self._request(
            StudentRequest.RequestType.SWAP,
            student=first,
            swap_with_student=second,
        )

        response = self._approve(req)

        self.assertEqual(response.status_code, 200)
        self._assert_approved(req, self.boss_a)
        first.refresh_from_db()
        second.refresh_from_db()
        first_assignment.refresh_from_db()
        second_assignment.refresh_from_db()
        self.assertIsNone(req.final_assignment_id)
        self.assertEqual(first.assigned_room_id, second_original_room_id)
        self.assertEqual(second.assigned_room_id, first_original_room_id)
        self.assertEqual(first_assignment.status, BedAssignment.Status.ENDED)
        self.assertEqual(second_assignment.status, BedAssignment.Status.ENDED)

        first_active_assignments = list(
            BedAssignment.objects.filter(
                student=first, status=BedAssignment.Status.ACTIVE
            ).select_related("bed")
        )
        second_active_assignments = list(
            BedAssignment.objects.filter(
                student=second, status=BedAssignment.Status.ACTIVE
            ).select_related("bed")
        )
        self.assertEqual(len(first_active_assignments), 1)
        self.assertEqual(len(second_active_assignments), 1)
        self.assertEqual(
            first_active_assignments[0].bed.room_id, second_original_room_id
        )
        self.assertEqual(
            second_active_assignments[0].bed.room_id, first_original_room_id
        )
        self.assertEqual(
            first_active_assignments[0].assignment_type,
            BedAssignment.AssignmentType.TRANSFER,
        )
        self.assertEqual(
            second_active_assignments[0].assignment_type,
            BedAssignment.AssignmentType.TRANSFER,
        )

    def test_region_transfer_approval_places_student_in_destination(self):
        student = self._student("APPROVE-REGION", self.dorm_a)
        old_assignment = self._place(student, self.room_a1)
        req = self._request(
            StudentRequest.RequestType.REGION_TRANSFER,
            student=student,
            source_region=self.region_a,
            target_region=self.region_b,
            target_room=self.room_b1,
        )

        response = self._approve(req, self.boss_b)

        self.assertEqual(response.status_code, 200)
        self._assert_approved(req, self.boss_b)
        student.refresh_from_db()
        old_assignment.refresh_from_db()
        self.assertEqual(student.assigned_room_id, self.room_b1.id)
        self.assertEqual(old_assignment.status, BedAssignment.Status.ENDED)
        self.assertEqual(req.final_assignment.bed.room_id, self.room_b1.id)

    def test_other_request_approval_is_audited_no_op(self):
        student = self._student("APPROVE-OTHER", self.dorm_a)
        req = self._request(StudentRequest.RequestType.OTHER, student=student)
        assignment_count = BedAssignment.objects.count()

        response = self._approve(req)

        self.assertEqual(response.status_code, 200)
        self._assert_approved(req, self.boss_a)
        student.refresh_from_db()
        self.assertIsNone(student.assigned_room_id)
        self.assertIsNone(req.final_assignment_id)
        self.assertEqual(BedAssignment.objects.count(), assignment_count)


class StudentRequestErrorAndGenericUpdateCharacterizationTests(
    TransferServiceCharacterizationFixtures
):
    def test_stale_non_pending_approval_returns_400(self):
        req = self._request(
            StudentRequest.RequestType.OTHER,
            status=StudentRequest.Status.CANCELLED,
        )

        response = self._approve(req)

        self.assertEqual(response.status_code, 400)
        req.refresh_from_db()
        self.assertEqual(req.status, StudentRequest.Status.CANCELLED)

    def test_unauthorized_review_returns_403(self):
        student = self._student("ERROR-AUTH", self.dorm_a)
        req = self._request(
            StudentRequest.RequestType.OTHER,
            student=student,
            requested_by=self.boss_b,
        )

        response = self._approve(req, self.boss_b)

        self.assertEqual(response.status_code, 403)
        req.refresh_from_db()
        self.assertEqual(req.status, StudentRequest.Status.PENDING)

    def test_missing_and_invalid_target_room_return_current_errors(self):
        missing = self._request(
            StudentRequest.RequestType.ROOM,
            student=self._student("ERROR-MISSING", self.dorm_a),
        )
        invalid = self._request(
            StudentRequest.RequestType.ROOM,
            student=self._student("ERROR-INVALID", self.dorm_a),
        )

        missing_response = self._approve(missing)
        invalid_response = self._approve(invalid, data={"target_room": 999999})

        self.assertEqual(missing_response.status_code, 400)
        self.assertEqual(invalid_response.status_code, 404)
        missing.refresh_from_db()
        invalid.refresh_from_db()
        self.assertEqual(missing.status, StudentRequest.Status.PENDING)
        self.assertEqual(invalid.status, StudentRequest.Status.PENDING)

    def test_failed_destination_placement_rolls_back_request_and_assignment(self):
        student = self._student("ERROR-ROLLBACK", self.dorm_a)
        source_assignment = self._place(student, self.room_a1)
        self._place(self._student("FILL-1", self.dorm_a), self.room_a2)
        self._place(self._student("FILL-2", self.dorm_a), self.room_a2)
        req = self._request(
            StudentRequest.RequestType.ROOM,
            student=student,
            target_room=self.room_a2,
        )

        response = self._approve(req)

        self.assertEqual(response.status_code, 400)
        req.refresh_from_db()
        student.refresh_from_db()
        source_assignment.refresh_from_db()
        self.assertEqual(req.status, StudentRequest.Status.PENDING)
        self.assertIsNone(req.final_assignment_id)
        self.assertEqual(student.assigned_room_id, self.room_a1.id)
        self.assertEqual(source_assignment.status, BedAssignment.Status.ACTIVE)
        self.assertEqual(
            BedAssignment.objects.filter(student=student, status="active").count(), 1
        )

    def test_duplicate_add_student_conflict_leaves_request_pending(self):
        self._student("DUPLICATE-ID", self.dorm_a)
        req = self._request(
            StudentRequest.RequestType.ADD_STUDENT,
            student_data={
                "student_id": "DUPLICATE-ID",
                "first_name": "Duplicate",
                "last_name": "Student",
                "gender": Student.Gender.MALE,
                "housing_type": Student.HousingType.SINGLE_MALE,
            },
        )

        response = self._approve(req)

        self.assertEqual(response.status_code, 400)
        req.refresh_from_db()
        self.assertEqual(req.status, StudentRequest.Status.PENDING)
        self.assertIsNone(req.reviewed_by_id)
        self.assertIsNone(req.reviewed_at)
        self.assertIsNone(req.final_assignment_id)
        self.assertEqual(Student.objects.filter(student_id="DUPLICATE-ID").count(), 1)

    def test_patch_updates_reason_but_ignores_workflow_and_audit_fields(self):
        req = self._request(
            StudentRequest.RequestType.OTHER,
            current_assignment_snapshot={"assigned": False},
        )
        original_number = req.request_number

        response = self._client(self.boss_a).patch(
            f"/api/requests/{req.pk}/",
            {
                "reason": "patched reason",
                "status": StudentRequest.Status.APPROVED,
                "reviewed_by": self.central.id,
                "reviewed_at": timezone.now().isoformat(),
                "rejection_reason": "ignored",
                "request_number": "REPLACED",
                "current_assignment_snapshot": {"assigned": True},
                "final_assignment": 999999,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        req.refresh_from_db()
        self.assertEqual(req.reason, "patched reason")
        self.assertEqual(req.status, StudentRequest.Status.PENDING)
        self.assertIsNone(req.reviewed_by_id)
        self.assertIsNone(req.reviewed_at)
        self.assertEqual(req.rejection_reason, "")
        self.assertEqual(req.request_number, original_number)
        self.assertEqual(req.current_assignment_snapshot, {"assigned": False})
        self.assertIsNone(req.final_assignment_id)

    def test_put_updates_writable_fields_but_ignores_workflow_and_audit_fields(self):
        req = self._request(
            StudentRequest.RequestType.OTHER,
            current_assignment_snapshot={"assigned": False},
        )
        original_number = req.request_number

        response = self._client(self.boss_a).put(
            f"/api/requests/{req.pk}/",
            {
                "request_type": StudentRequest.RequestType.OTHER,
                "reason": "put reason",
                "priority": StudentRequest.Priority.HIGH,
                "status": StudentRequest.Status.REJECTED,
                "reviewed_by": self.central.id,
                "reviewed_at": timezone.now().isoformat(),
                "rejection_reason": "ignored",
                "request_number": "REPLACED",
                "current_assignment_snapshot": {"assigned": True},
                "final_assignment": 999999,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        req.refresh_from_db()
        self.assertEqual(req.reason, "put reason")
        self.assertEqual(req.priority, StudentRequest.Priority.HIGH)
        self.assertEqual(req.status, StudentRequest.Status.PENDING)
        self.assertIsNone(req.reviewed_by_id)
        self.assertIsNone(req.reviewed_at)
        self.assertEqual(req.rejection_reason, "")
        self.assertEqual(req.request_number, original_number)
        self.assertEqual(req.current_assignment_snapshot, {"assigned": False})
        self.assertIsNone(req.final_assignment_id)

    def test_student_request_delete_is_method_not_allowed(self):
        req = self._request(StudentRequest.RequestType.OTHER)

        response = self._client(self.boss_a).delete(
            f"/api/requests/{req.pk}/"
        )

        self.assertEqual(response.status_code, 405)
        self.assertTrue(StudentRequest.objects.filter(pk=req.pk).exists())


class LegacyTransferCharacterizationTests(TransferServiceCharacterizationFixtures):
    def _transfer(self, student_id, **overrides):
        student = self._student(student_id, self.dorm_a)
        values = {
            "student": student,
            "from_room": self.room_a1,
            "to_room": self.room_a2,
            "reason": "legacy characterization",
            "requested_by": self.boss_a,
            "status": Transfer.Status.PENDING,
        }
        values.update(overrides)
        return Transfer.objects.create(**values)

    def test_legacy_approve_and_reject_non_pending_return_400(self):
        approved = self._transfer("LEGACY-STALE-A")
        approved.status = Transfer.Status.APPROVED
        approved.reviewed_by = self.central
        approved.reviewed_at = timezone.now()
        approved.save(update_fields=["status", "reviewed_by", "reviewed_at"])
        rejected = self._transfer("LEGACY-STALE-R")
        rejected.status = Transfer.Status.REJECTED
        rejected.reviewed_by = self.central
        rejected.reviewed_at = timezone.now()
        rejected.save(update_fields=["status", "reviewed_by", "reviewed_at"])
        client = self._client(self.boss_a)

        approve_response = client.put(
            f"/api/transfers/{approved.pk}/approve/", {}, format="json"
        )
        reject_response = client.put(
            f"/api/transfers/{rejected.pk}/reject/",
            {"reason": "still rejected"},
            format="json",
        )

        self.assertEqual(approve_response.status_code, 400)
        self.assertEqual(reject_response.status_code, 400)

    def test_legacy_boss_room_authorization_and_no_region_denial(self):
        transfer = self._transfer(
            "LEGACY-AUTH", from_room=self.room_a1, to_room=self.room_b1
        )

        unauthorized = self._client(self.boss_b).put(
            f"/api/transfers/{transfer.pk}/approve/", {}, format="json"
        )
        no_region = self._client(self.no_region_boss).put(
            f"/api/transfers/{transfer.pk}/approve/", {}, format="json"
        )

        self.assertEqual(unauthorized.status_code, 403)
        self.assertEqual(no_region.status_code, 404)
        transfer.refresh_from_db()
        self.assertEqual(transfer.status, Transfer.Status.PENDING)

    def test_legacy_full_destination_prelock_check_returns_400(self):
        self._place(self._student("LEGACY-FILL-1", self.dorm_a), self.room_a2)
        self._place(self._student("LEGACY-FILL-2", self.dorm_a), self.room_a2)
        transfer = self._transfer("LEGACY-FULL")

        response = self._client(self.boss_a).put(
            f"/api/transfers/{transfer.pk}/approve/", {}, format="json"
        )

        self.assertEqual(response.status_code, 400)
        transfer.refresh_from_db()
        self.assertEqual(transfer.status, Transfer.Status.PENDING)

    def test_legacy_generic_put_patch_and_delete_are_method_not_allowed(self):
        transfer = self._transfer("LEGACY-METHODS")
        client = self._client(self.boss_a)
        url = f"/api/transfers/{transfer.pk}/"

        self.assertEqual(client.put(url, {"reason": "put"}, format="json").status_code, 405)
        self.assertEqual(
            client.patch(url, {"reason": "patch"}, format="json").status_code,
            405,
        )
        self.assertEqual(client.delete(url).status_code, 405)
        self.assertTrue(Transfer.objects.filter(pk=transfer.pk).exists())
