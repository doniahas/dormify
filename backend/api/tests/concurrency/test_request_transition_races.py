"""Concurrency characterization for StudentRequest transitions and SWAP approval."""

import threading
import time
from unittest.mock import patch

from django.db import connection, connections
from django.db.models.query import QuerySet
from django.test import TransactionTestCase
from rest_framework.test import APIClient

from api.models import (
    Apartment,
    Bed,
    BedAssignment,
    Building,
    DormType,
    Region,
    Room,
    Student,
    StudentRequest,
    User,
)


def _client_for(user):
    client = APIClient()
    client.force_authenticate(user=user)
    client.raise_request_exception = False
    return client


def _run_concurrently(callables, timeout=20):
    """Run independent requests together without permitting an unbounded join."""
    start_barrier = threading.Barrier(len(callables))
    results = [None] * len(callables)
    errors = [None] * len(callables)

    def _worker(index, call):
        connections.close_all()
        try:
            with connection.cursor() as cursor:
                cursor.execute("SET lock_timeout = '8s'")
                cursor.execute("SET statement_timeout = '15s'")
            start_barrier.wait(timeout=10)
            results[index] = call()
        except BaseException as exc:  # surfaced in the main test thread below
            errors[index] = repr(exc)
        finally:
            connections.close_all()

    threads = [
        threading.Thread(target=_worker, args=(index, call), daemon=True)
        for index, call in enumerate(callables)
    ]
    for thread in threads:
        thread.start()

    deadline = time.monotonic() + timeout
    for thread in threads:
        thread.join(timeout=max(0, deadline - time.monotonic()))

    alive = [index for index, thread in enumerate(threads) if thread.is_alive()]
    if alive:
        raise AssertionError(f"concurrent request threads exceeded {timeout}s: {alive}")
    if any(errors):
        raise AssertionError(f"concurrent worker errors: {errors}")
    return results


class StudentRequestTransitionRaceTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.region = Region.objects.create(id="transition-race", name="Transition Race")
        self.dorm = DormType.objects.create(
            code=9910, name="Transition Race Dorm", region=self.region
        )
        self.admin = User.objects.create_user(
            username="transition-race-admin",
            email="transition-race-admin@example.test",
            password="test-pass",
            role=User.Role.CENTRAL_ADMIN,
        )

    def _other_request(self):
        return StudentRequest.objects.create(
            request_type=StudentRequest.RequestType.OTHER,
            reason="transition race",
            requested_by=self.admin,
        )

    def _action(self, req, action):
        def _call():
            data = {"reason": "race rejection"} if action == "reject" else {}
            response = _client_for(self.admin).put(
                f"/api/requests/{req.pk}/{action}/", data, format="json"
            )
            return action, response.status_code, response.content[:500]

        return _call

    def _assert_two_way_transition(self, req, actions, allowed_statuses):
        results = _run_concurrently([self._action(req, action) for action in actions])
        self.assertEqual(sorted(result[1] for result in results), [200, 400], results)
        winner = next(result[0] for result in results if result[1] == 200)
        req.refresh_from_db()
        self.assertEqual(req.status, allowed_statuses[winner])
        self.assertEqual(req.reviewed_by_id, self.admin.id)
        self.assertIsNotNone(req.reviewed_at)
        self.assertIsNone(req.final_assignment_id)

    def test_approve_vs_cancel(self):
        self._assert_two_way_transition(
            self._other_request(),
            ("approve", "cancel"),
            {
                "approve": StudentRequest.Status.APPROVED,
                "cancel": StudentRequest.Status.CANCELLED,
            },
        )

    def test_reject_vs_cancel(self):
        self._assert_two_way_transition(
            self._other_request(),
            ("reject", "cancel"),
            {
                "reject": StudentRequest.Status.REJECTED,
                "cancel": StudentRequest.Status.CANCELLED,
            },
        )

    def test_cancel_vs_cancel(self):
        req = self._other_request()
        results = _run_concurrently(
            [self._action(req, "cancel"), self._action(req, "cancel")]
        )
        self.assertEqual(sorted(result[1] for result in results), [200, 400], results)
        req.refresh_from_db()
        self.assertEqual(req.status, StudentRequest.Status.CANCELLED)
        self.assertEqual(req.reviewed_by_id, self.admin.id)
        self.assertIsNotNone(req.reviewed_at)
        self.assertIsNone(req.final_assignment_id)


class StudentRequestSwapRaceTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.region = Region.objects.create(id="swap-race", name="Swap Race")
        self.dorm = DormType.objects.create(code=9920, name="Swap Race Dorm", region=self.region)
        self.admin = User.objects.create_user(
            username="swap-race-admin",
            email="swap-race-admin@example.test",
            password="test-pass",
            role=User.Role.CENTRAL_ADMIN,
        )
        self.room_a = self._room(1, "A")
        self.room_b = self._room(2, "B")
        self.student_a = self._student("SWAP-RACE-A")
        self.student_b = self._student("SWAP-RACE-B")
        self.original_a = self._place(self.student_a, self.room_a)
        self.original_b = self._place(self.student_b, self.room_b)

    def _room(self, number, suffix):
        building = Building.objects.create(number=number, dorm_type=self.dorm)
        apartment = Apartment.objects.create(
            building=building,
            number=f"APT-{suffix}",
            category=Apartment.Category.MALE,
            apartment_type=Apartment.ApartmentType.SINGLE,
            room_count=1,
            apartment_capacity=2,
        )
        room = Room.objects.create(
            apartment=apartment, name=f"Room {suffix}", capacity=2, is_active=True
        )
        Bed.objects.create(room=room, label="1")
        Bed.objects.create(room=room, label="2")
        return room

    def _student(self, student_id):
        return Student.objects.create(
            student_id=student_id,
            first_name="Race",
            last_name="Student",
            gender=Student.Gender.MALE,
            housing_type=Student.HousingType.SINGLE_MALE,
            accepted_dorm_type=self.dorm,
        )

    def _place(self, student, room):
        assignment = BedAssignment.objects.create(
            student=student,
            bed=room.beds.order_by("label").first(),
            status=BedAssignment.Status.ACTIVE,
            assigned_by=self.admin,
            assignment_type=BedAssignment.AssignmentType.MANUAL,
        )
        student.assigned_room = room
        student.save(update_fields=["assigned_room"])
        return assignment

    def _swap_request(self, first, second, suffix):
        return StudentRequest.objects.create(
            request_number=f"REQ-SWAP-RACE-{suffix}",
            request_type=StudentRequest.RequestType.SWAP,
            reason="swap race",
            requested_by=self.admin,
            student=first,
            swap_with_student=second,
        )

    def _approve(self, req):
        def _call():
            response = _client_for(self.admin).put(
                f"/api/requests/{req.pk}/approve/", {}, format="json"
            )
            return req.pk, response.status_code, response.content[:500]

        return _call

    def _active_assignments(self, student):
        return list(
            BedAssignment.objects.filter(
                student=student, status=BedAssignment.Status.ACTIVE
            ).select_related("bed")
        )

    def test_concurrent_approval_of_same_swap_request(self):
        req = self._swap_request(self.student_a, self.student_b, "SAME")
        results = _run_concurrently([self._approve(req), self._approve(req)])

        self.assertEqual(sorted(result[1] for result in results), [200, 400], results)
        req.refresh_from_db()
        self.student_a.refresh_from_db()
        self.student_b.refresh_from_db()
        self.original_a.refresh_from_db()
        self.original_b.refresh_from_db()
        active_a = self._active_assignments(self.student_a)
        active_b = self._active_assignments(self.student_b)

        self.assertEqual(req.status, StudentRequest.Status.APPROVED)
        self.assertIsNone(req.final_assignment_id)
        self.assertEqual(self.student_a.assigned_room_id, self.room_b.id)
        self.assertEqual(self.student_b.assigned_room_id, self.room_a.id)
        self.assertEqual(self.original_a.status, BedAssignment.Status.ENDED)
        self.assertEqual(self.original_b.status, BedAssignment.Status.ENDED)
        self.assertEqual(len(active_a), 1)
        self.assertEqual(len(active_b), 1)
        self.assertEqual(active_a[0].bed.room_id, self.room_b.id)
        self.assertEqual(active_b[0].bed.room_id, self.room_a.id)
        self.assertEqual(active_a[0].assignment_type, BedAssignment.AssignmentType.TRANSFER)
        self.assertEqual(active_b[0].assignment_type, BedAssignment.AssignmentType.TRANSFER)

    def test_reversed_student_swap_ordering(self):
        req_ab = self._swap_request(self.student_a, self.student_b, "AB")
        req_ba = self._swap_request(self.student_b, self.student_a, "BA")
        canonical_lock_query_ready = threading.Barrier(2)
        original_fetch_all = QuerySet._fetch_all
        thread_state = threading.local()
        query_observations = []
        observations_lock = threading.Lock()

        def _coordinated_fetch_all(queryset):
            is_canonical_lock_query = (
                queryset.model is BedAssignment
                and queryset.query.select_for_update
                and queryset._result_cache is None
            )
            if not is_canonical_lock_query:
                return original_fetch_all(queryset)

            query_number = getattr(thread_state, "canonical_lock_query_count", 0) + 1
            thread_state.canonical_lock_query_count = query_number
            if query_number == 1:
                canonical_lock_query_ready.wait(timeout=10)

            result = original_fetch_all(queryset)
            rows = [
                (assignment.student_id, assignment.status, assignment.assignment_type)
                for assignment in queryset._result_cache
            ]
            with observations_lock:
                query_observations.append(
                    (threading.get_ident(), query_number, rows)
                )
            return result

        with patch.object(QuerySet, "_fetch_all", new=_coordinated_fetch_all):
            results = _run_concurrently([self._approve(req_ab), self._approve(req_ba)])

        req_ab.refresh_from_db()
        req_ba.refresh_from_db()
        self.student_a.refresh_from_db()
        self.student_b.refresh_from_db()
        self.original_a.refresh_from_db()
        self.original_b.refresh_from_db()
        active_a = self._active_assignments(self.student_a)
        active_b = self._active_assignments(self.student_b)
        history_a = list(BedAssignment.objects.filter(student=self.student_a).select_related("bed"))
        history_b = list(BedAssignment.objects.filter(student=self.student_b).select_related("bed"))
        database_state = {
            "request_statuses": (req_ab.status, req_ba.status),
            "assigned_rooms": (
                self.student_a.assigned_room_id,
                self.student_b.assigned_room_id,
            ),
            "active_counts": (len(active_a), len(active_b)),
            "active_rooms": (
                [assignment.bed.room_id for assignment in active_a],
                [assignment.bed.room_id for assignment in active_b],
            ),
            "final_assignment_ids": (
                req_ab.final_assignment_id,
                req_ba.final_assignment_id,
            ),
        }
        observations_by_thread = {}
        for thread_id, query_number, rows in query_observations:
            observations_by_thread.setdefault(thread_id, []).append((query_number, rows))
        observation_sequences = sorted(
            [
                [rows for _, rows in sorted(observations)]
                for observations in observations_by_thread.values()
            ],
            key=lambda sequence: [len(rows) for rows in sequence],
        )
        database_state["canonical_query_observations"] = observation_sequences
        context = {"responses": results, "database_state": database_state}

        self.assertNotIn(500, [result[1] for result in results], context)
        self.assertEqual(sorted(result[1] for result in results), [200, 200], context)
        self.assertEqual(
            [[len(rows) for rows in sequence] for sequence in observation_sequences],
            [[0, 2], [2]],
            context,
        )
        fresh_rows = observation_sequences[0][1]
        self.assertEqual(
            [student_id for student_id, _, _ in fresh_rows],
            sorted([self.student_a.id, self.student_b.id]),
            context,
        )
        self.assertTrue(
            all(status_value == BedAssignment.Status.ACTIVE for _, status_value, _ in fresh_rows),
            context,
        )
        self.assertTrue(
            all(
                assignment_type == BedAssignment.AssignmentType.TRANSFER
                for _, _, assignment_type in fresh_rows
            ),
            context,
        )
        for _, _, body in results:
            body_lower = body.lower()
            self.assertNotIn(b"deadlock", body_lower, context)
            self.assertNotIn(b"database", body_lower, context)
            self.assertNotIn(b"operationalerror", body_lower, context)
            self.assertNotIn(b"40p01", body_lower, context)
        self.assertEqual(
            (req_ab.status, req_ba.status),
            (StudentRequest.Status.APPROVED, StudentRequest.Status.APPROVED),
            context,
        )
        self.assertEqual(req_ab.reviewed_by_id, self.admin.id, context)
        self.assertEqual(req_ba.reviewed_by_id, self.admin.id, context)
        self.assertIsNotNone(req_ab.reviewed_at, context)
        self.assertIsNotNone(req_ba.reviewed_at, context)
        self.assertEqual(len(active_a), 1, context)
        self.assertEqual(len(active_b), 1, context)
        self.assertEqual(self.student_a.assigned_room_id, self.room_a.id, context)
        self.assertEqual(self.student_b.assigned_room_id, self.room_b.id, context)
        self.assertEqual(active_a[0].assignment_type, BedAssignment.AssignmentType.TRANSFER, context)
        self.assertEqual(active_b[0].assignment_type, BedAssignment.AssignmentType.TRANSFER, context)
        self.assertIsNone(req_ab.final_assignment_id, context)
        self.assertIsNone(req_ba.final_assignment_id, context)
        self.assertEqual(self.original_a.status, BedAssignment.Status.ENDED, context)
        self.assertEqual(self.original_b.status, BedAssignment.Status.ENDED, context)
        self.assertIsNotNone(self.original_a.ended_at, context)
        self.assertIsNotNone(self.original_b.ended_at, context)
        self.assertEqual(len(history_a), 3, context)
        self.assertEqual(len(history_b), 3, context)
        intermediate_a = [
            assignment
            for assignment in history_a
            if assignment.pk not in (self.original_a.pk, active_a[0].pk)
        ]
        intermediate_b = [
            assignment
            for assignment in history_b
            if assignment.pk not in (self.original_b.pk, active_b[0].pk)
        ]
        self.assertEqual(len(intermediate_a), 1, context)
        self.assertEqual(len(intermediate_b), 1, context)
        self.assertEqual(intermediate_a[0].status, BedAssignment.Status.ENDED, context)
        self.assertEqual(intermediate_b[0].status, BedAssignment.Status.ENDED, context)
        self.assertEqual(
            intermediate_a[0].assignment_type, BedAssignment.AssignmentType.TRANSFER, context
        )
        self.assertEqual(
            intermediate_b[0].assignment_type, BedAssignment.AssignmentType.TRANSFER, context
        )
        self.assertEqual(intermediate_a[0].bed.room_id, self.room_b.id, context)
        self.assertEqual(intermediate_b[0].bed.room_id, self.room_a.id, context)
        self.assertIsNotNone(intermediate_a[0].ended_at, context)
        self.assertIsNotNone(intermediate_b[0].ended_at, context)
