"""
Placement race tests: apartment-level serialization of manual assignments.

assign_student_to_room() locks the target Apartment row (select_for_update)
before it validates the placement and re-verifies the chosen bed. Two
invariants depend on that lock alone - no database constraint covers them:

* apartment-level exclusivity (a Z6 resident needs the whole apartment), and
* room capacity when a room has more Bed rows than its capacity.

(A race for one and the same bed is caught by the partial unique index
`unique_active_assignment_per_bed` even without the lock, so it cannot
prove the lock exists - both tests below deliberately race for DIFFERENT
beds.)

WHY TransactionTestCase: every worker thread needs its own committed,
visible data and its own database connection, exactly like two real
concurrent HTTP requests; a plain TestCase's wrapping transaction would hide
one thread's writes from the other or deadlock on the lock.

Both workers authenticate as the same central_admin (one user acting in two
tabs); no scenario places two managers in one region. This module writes no
evidence files.

Run against Django's disposable TEST database:

    python manage.py test api.tests.concurrency.test_placement_races
"""

import threading
from concurrent.futures import ThreadPoolExecutor

from django.db import connections
from django.test import TransactionTestCase
from rest_framework.test import APIClient

from api.models import User, Region, DormType, Building, Apartment, Room, Bed, Student, BedAssignment


ASSIGN_URL = '/api/room-assignments/assign/'


def _run_concurrently(callables):
    """
    Release all callables at (as close as possible to) the same instant, each
    on its own worker thread and therefore its own Django DB connection, which
    is closed explicitly when the worker finishes.
    """
    barrier = threading.Barrier(len(callables))
    results = [None] * len(callables)

    def _wrapped(i, fn):
        try:
            barrier.wait(timeout=10)
            results[i] = fn()
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=len(callables)) as pool:
        futures = [pool.submit(_wrapped, i, fn) for i, fn in enumerate(callables)]
        for future in futures:
            future.result(timeout=30)
    return results


def _client_for(user):
    """A fresh APIClient per worker; an unhandled view error comes back as a real 500."""
    client = APIClient()
    client.force_authenticate(user)
    client.raise_request_exception = False
    return client


class PlacementRaceTests(TransactionTestCase):

    def setUp(self):
        self.region = Region.objects.create(id='placement-race-region', name='Placement Race Region')
        self.dorm_type = DormType.objects.create(name='Placement Race DormType', region=self.region)
        self.admin = User(
            email='placement-race-admin@test.com', username='placement-race-admin@test.com',
            role=User.Role.CENTRAL_ADMIN, first_name='T', last_name='User',
        )
        self.admin.set_password('testpass123')
        self.admin.save()

    def _apartment(self, *, category, apartment_type, rooms):
        """rooms: iterable of (room_name, capacity, bed_count)."""
        building = Building.objects.create(number=1, dorm_type=self.dorm_type)
        apartment = Apartment.objects.create(
            building=building, number='1', category=category,
            apartment_type=apartment_type, room_count=len(rooms),
        )
        created = []
        for name, capacity, bed_count in rooms:
            room = Room.objects.create(apartment=apartment, name=name, capacity=capacity)
            beds = [Bed.objects.create(room=room, label=f'B{i}') for i in range(1, bed_count + 1)]
            created.append((room, beds))
        return apartment, created

    def _student(self, student_id, housing_type):
        return Student.objects.create(
            student_id=student_id, first_name='F', last_name='L', gender=Student.Gender.MALE,
            housing_type=housing_type, accepted_dorm_type=self.dorm_type,
        )

    def _assign(self, payload):
        def _call():
            resp = _client_for(self.admin).post(ASSIGN_URL, payload, format='json')
            body = getattr(resp, 'data', None)
            return resp.status_code, (body if body is not None else resp.content[:300])
        return _call

    def test_concurrent_z6_assignments_into_one_apartment_admit_exactly_one(self):
        apartment, ((room_1, _), (room_2, _)) = self._apartment(
            category=Apartment.Category.MIXED, apartment_type=Apartment.ApartmentType.COUPLE,
            rooms=[('101', 1, 1), ('102', 1, 1)],
        )
        student_a = self._student('RACE-Z6-A', Student.HousingType.SINGLE_IN_APARTMENT)
        student_b = self._student('RACE-Z6-B', Student.HousingType.SINGLE_IN_APARTMENT)

        results = _run_concurrently([
            self._assign({'student_id': student_a.id, 'room_id': room_1.id}),
            self._assign({'student_id': student_b.id, 'room_id': room_2.id}),
        ])

        status_codes = sorted(code for code, _ in results)
        self.assertNotIn(500, status_codes, results)
        self.assertEqual(status_codes, [200, 400], results)
        loser_body = next(body for code, body in results if code == 400)
        self.assertEqual(loser_body, {'error': 'Z6 requires exclusive use of the complete apartment.'})
        self.assertEqual(
            BedAssignment.objects.filter(
                bed__room__apartment=apartment, status=BedAssignment.Status.ACTIVE,
            ).count(),
            1,
        )
        winner_index = 0 if results[0][0] == 200 else 1
        winner, loser = (student_a, student_b) if winner_index == 0 else (student_b, student_a)
        winner_room = room_1 if winner_index == 0 else room_2
        winner.refresh_from_db()
        loser.refresh_from_db()
        self.assertEqual(winner.assigned_room_id, winner_room.id)
        self.assertIsNone(loser.assigned_room_id)

    def test_concurrent_assignments_cannot_exceed_capacity_with_surplus_bed_rows(self):
        _, ((room, beds),) = self._apartment(
            category=Apartment.Category.MALE, apartment_type=Apartment.ApartmentType.SINGLE,
            rooms=[('101', 1, 2)],  # capacity 1, but two Bed rows (data anomaly)
        )
        student_a = self._student('RACE-CAP-A', Student.HousingType.SINGLE_MALE)
        student_b = self._student('RACE-CAP-B', Student.HousingType.SINGLE_MALE)

        results = _run_concurrently([
            self._assign({'student_id': student_a.id, 'room_id': room.id, 'bed_id': beds[0].id}),
            self._assign({'student_id': student_b.id, 'room_id': room.id, 'bed_id': beds[1].id}),
        ])

        status_codes = sorted(code for code, _ in results)
        self.assertNotIn(500, status_codes, results)
        self.assertEqual(status_codes, [200, 400], results)
        loser_body = next(body for code, body in results if code == 400)
        self.assertEqual(loser_body, {'error': 'החדר בתפוסה מלאה - לא ניתן לחרוג מקיבולת החדר'})
        self.assertEqual(
            BedAssignment.objects.filter(bed__room=room, status=BedAssignment.Status.ACTIVE).count(),
            1,
        )
        winner, loser = (student_a, student_b) if results[0][0] == 200 else (student_b, student_a)
        winner.refresh_from_db()
        loser.refresh_from_db()
        self.assertEqual(winner.assigned_room_id, room.id)
        self.assertIsNone(loser.assigned_room_id)
