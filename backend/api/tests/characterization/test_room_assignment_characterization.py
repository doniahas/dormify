"""
Characterization tests for the manual room-assignment write paths:
/api/room-assignments/assign/, /move/, /unassign/ and /swap/, StudentRequest
swap approval, and the bed checks that still apply to an Assisted Allocation
override.

These tests pin the CURRENT observable behaviour - status codes, response
bodies, error text and the resulting BedAssignment / Student.assigned_room
state - so that relocating the placement code cannot silently change it.
Pinning a behaviour here is not a statement that it is the desired policy.

Run against Django's disposable TEST database (created/destroyed as
test_<DB_NAME> - never touches the real `dormify` database):

    python manage.py test api.tests.characterization.test_room_assignment_characterization
"""

from django.test import TestCase
from rest_framework.test import APIClient

from api.models import (
    User, Region, DormType, Building, Apartment, Room,
    Student, BedAssignment, StudentRequest, AssistedAllocationAudit,
)
from api.tests.support.matching_test_utils import create_beds_for_room


ASSIGN_URL = '/api/room-assignments/assign/'
MOVE_URL = '/api/room-assignments/move/'
UNASSIGN_URL = '/api/room-assignments/unassign/'
SWAP_URL = '/api/room-assignments/swap/'


class RoomAssignmentFixtures(TestCase):
    """Local fixture helpers only - defines no tests of its own."""

    def setUp(self):
        self._building_seq = 0

    def _region(self, key):
        return Region.objects.create(id=f'char-{key}', name=f'Char {key}')

    def _dorm_type(self, region):
        return DormType.objects.create(name=f'Char DT {region.id}', region=region)

    def _user(self, email, role, region=None):
        return User.objects.create_user(
            username=email, email=email, password='testpass123',
            role=role, region=region, first_name='T', last_name='User',
        )

    def _boss(self, region):
        # Exactly one region_boss per region (DB constraint and business rule).
        return self._user(f'boss-{region.id}@test.com', User.Role.REGION_BOSS, region)

    def _client(self, user):
        client = APIClient()
        client.force_authenticate(user=user)
        return client

    def _apartment(self, dorm_type, *, category, apartment_type, rooms, number='1'):
        """rooms: iterable of (room_name, capacity); Bed rows are created to capacity."""
        self._building_seq += 1
        building = Building.objects.create(number=self._building_seq, dorm_type=dorm_type)
        apartment = Apartment.objects.create(
            building=building, number=number, category=category,
            apartment_type=apartment_type, room_count=len(rooms),
        )
        created = []
        for name, capacity in rooms:
            room = Room.objects.create(apartment=apartment, name=name, capacity=capacity)
            create_beds_for_room(room)
            created.append(room)
        return building, apartment, created

    def _student(self, student_id, dorm_type, *, housing_type=Student.HousingType.SINGLE_MALE,
                 gender=Student.Gender.MALE, **extra):
        return Student.objects.create(
            student_id=student_id, first_name='F', last_name=student_id,
            gender=gender, housing_type=housing_type, accepted_dorm_type=dorm_type,
            **extra,
        )

    def _place(self, student, bed):
        """Existing active placement, as left by an earlier assignment."""
        assignment = BedAssignment.objects.create(
            student=student, bed=bed, status=BedAssignment.Status.ACTIVE,
            assignment_type=BedAssignment.AssignmentType.INITIAL,
        )
        student.assigned_room = bed.room
        student.save(update_fields=['assigned_room'])
        return assignment

    def _first_bed(self, room):
        return room.beds.order_by('id').first()

    def _state(self):
        return (
            list(BedAssignment.objects.order_by('id').values_list(
                'id', 'student_id', 'bed_id', 'status', 'ended_at', 'assignment_type',
            )),
            dict(Student.objects.values_list('id', 'assigned_room_id')),
        )


class UnassignCharacterizationTests(RoomAssignmentFixtures):
    """POST /api/room-assignments/unassign/"""

    def setUp(self):
        super().setUp()
        self.region = self._region('u1')
        self.dorm_type = self._dorm_type(self.region)
        self.boss = self._boss(self.region)
        _, _, (self.room,) = self._apartment(
            self.dorm_type, category=Apartment.Category.MALE,
            apartment_type=Apartment.ApartmentType.SINGLE, rooms=[('101', 1)],
        )

    def test_unassign_ends_active_assignment_and_clears_room(self):
        student = self._student('U1-S', self.dorm_type)
        client = self._client(self.boss)
        resp = client.post(ASSIGN_URL, {'student_id': student.id, 'room_id': self.room.id}, format='json')
        self.assertEqual(resp.status_code, 200, resp.data)
        assignment = BedAssignment.objects.get(student=student, status=BedAssignment.Status.ACTIVE)

        resp = client.post(UNASSIGN_URL, {'student_id': student.id}, format='json')

        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertEqual(resp.data, {
            'success': True,
            'message': 'Student unassigned successfully',
            'student_id': student.id,
        })
        assignment.refresh_from_db()
        self.assertEqual(assignment.status, BedAssignment.Status.ENDED)
        self.assertIsNotNone(assignment.ended_at)
        self.assertFalse(
            BedAssignment.objects.filter(student=student, status=BedAssignment.Status.ACTIVE).exists()
        )
        student.refresh_from_db()
        self.assertIsNone(student.assigned_room_id)
        self.assertEqual(BedAssignment.objects.count(), 1)

        # The bed is free again.
        other = self._student('U1-T', self.dorm_type)
        resp = client.post(
            ASSIGN_URL,
            {'student_id': other.id, 'room_id': self.room.id, 'bed_id': assignment.bed_id},
            format='json',
        )
        self.assertEqual(resp.status_code, 200, resp.data)

    def test_unassign_without_active_assignment_reports_already_unassigned(self):
        student = self._student('U2-S', self.dorm_type)
        Student.objects.filter(pk=student.pk).update(assigned_room=self.room)  # drifted pointer

        resp = self._client(self.boss).post(UNASSIGN_URL, {'student_id': student.id}, format='json')

        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertEqual(resp.data, {'success': True, 'message': 'Student was already unassigned'})
        self.assertEqual(BedAssignment.objects.count(), 0)
        student.refresh_from_db()
        self.assertIsNone(student.assigned_room_id)

    def test_unassign_missing_identifier_returns_400(self):
        self._place(self._student('U3-S', self.dorm_type), self._first_bed(self.room))
        before = self._state()

        resp = self._client(self.boss).post(UNASSIGN_URL, {}, format='json')

        self.assertEqual(resp.status_code, 400, resp.data)
        self.assertEqual(resp.data, {'error': 'Missing student_id'})
        self.assertEqual(self._state(), before)

    def test_unassign_unknown_student_returns_404(self):
        self._place(self._student('U4-S', self.dorm_type), self._first_bed(self.room))
        before = self._state()

        resp = self._client(self.boss).post(UNASSIGN_URL, {'student_id': 999999}, format='json')

        self.assertEqual(resp.status_code, 404, resp.data)
        self.assertEqual(resp.data, {'error': 'Student not found'})
        self.assertEqual(self._state(), before)

    def test_unassign_accepts_university_student_id(self):
        student = self._student('U-5', self.dorm_type)
        assignment = self._place(student, self._first_bed(self.room))

        resp = self._client(self.boss).post(UNASSIGN_URL, {'student_id': 'U-5'}, format='json')

        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertEqual(resp.data, {
            'success': True,
            'message': 'Student unassigned successfully',
            'student_id': student.id,
        })
        assignment.refresh_from_db()
        self.assertEqual(assignment.status, BedAssignment.Status.ENDED)
        self.assertIsNotNone(assignment.ended_at)
        student.refresh_from_db()
        self.assertIsNone(student.assigned_room_id)

    def test_unassign_foreign_region_user_is_forbidden_and_state_unchanged(self):
        student = self._student('U6-S', self.dorm_type)
        self._place(student, self._first_bed(self.room))
        other_boss = self._boss(self._region('u6-other'))
        before = self._state()

        resp = self._client(other_boss).post(UNASSIGN_URL, {'student_id': student.id}, format='json')

        self.assertEqual(resp.status_code, 403, resp.data)
        self.assertEqual(resp.data, {'error': 'אין הרשאה לערוך חדר באזור זה'})
        self.assertEqual(self._state(), before)

    def test_unassign_without_active_assignment_skips_region_check(self):
        """
        Characterizes current behaviour, not desired policy: when the student
        has no active assignment, the endpoint clears assigned_room and answers
        200 without checking the caller's region.
        """
        student = self._student('U7-S', self.dorm_type)
        Student.objects.filter(pk=student.pk).update(assigned_room=self.room)  # drifted pointer
        other_boss = self._boss(self._region('u7-other'))

        resp = self._client(other_boss).post(UNASSIGN_URL, {'student_id': student.id}, format='json')

        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertEqual(resp.data, {'success': True, 'message': 'Student was already unassigned'})
        student.refresh_from_db()
        self.assertIsNone(student.assigned_room_id)


class SwapCharacterizationTests(RoomAssignmentFixtures):
    """POST /api/room-assignments/swap/ and StudentRequest swap approval."""

    def setUp(self):
        super().setUp()
        self.region = self._region('s1')
        self.dorm_type = self._dorm_type(self.region)
        self.boss = self._boss(self.region)

    def _two_single_rooms(self, category_a=Apartment.Category.MALE, category_b=Apartment.Category.MALE,
                          apartment_type=Apartment.ApartmentType.SINGLE, dorm_type_b=None):
        _, _, (room_a,) = self._apartment(
            self.dorm_type, category=category_a, apartment_type=apartment_type, rooms=[('101', 1)],
        )
        _, _, (room_b,) = self._apartment(
            dorm_type_b or self.dorm_type, category=category_b, apartment_type=apartment_type,
            rooms=[('101', 1)],
        )
        return room_a, room_b

    def _placed_pair(self):
        room_a, room_b = self._two_single_rooms()
        student_a = self._student('S-A', self.dorm_type)
        student_b = self._student('S-B', self.dorm_type)
        old_a = self._place(student_a, self._first_bed(room_a))
        old_b = self._place(student_b, self._first_bed(room_b))
        return room_a, room_b, student_a, student_b, old_a, old_b

    def _assert_swapped(self, room_a, room_b, student_a, student_b, old_a, old_b):
        old_a.refresh_from_db()
        old_b.refresh_from_db()
        self.assertEqual(old_a.status, BedAssignment.Status.ENDED)
        self.assertEqual(old_b.status, BedAssignment.Status.ENDED)
        self.assertIsNotNone(old_a.ended_at)
        self.assertEqual(old_a.ended_at, old_b.ended_at)

        new_a = BedAssignment.objects.get(student=student_a, status=BedAssignment.Status.ACTIVE)
        new_b = BedAssignment.objects.get(student=student_b, status=BedAssignment.Status.ACTIVE)
        self.assertEqual(new_a.bed_id, self._first_bed(room_b).id)
        self.assertEqual(new_b.bed_id, self._first_bed(room_a).id)
        self.assertEqual(new_a.assignment_type, BedAssignment.AssignmentType.TRANSFER)
        self.assertEqual(new_b.assignment_type, BedAssignment.AssignmentType.TRANSFER)
        self.assertEqual(new_a.assigned_by_id, self.boss.id)
        self.assertEqual(new_b.assigned_by_id, self.boss.id)

        student_a.refresh_from_db()
        student_b.refresh_from_db()
        self.assertEqual(student_a.assigned_room_id, room_b.id)
        self.assertEqual(student_b.assigned_room_id, room_a.id)
        self.assertEqual(BedAssignment.objects.count(), 4)
        return new_a, new_b

    def test_swap_exchanges_rooms_of_two_single_students(self):
        room_a, room_b, student_a, student_b, old_a, old_b = self._placed_pair()

        resp = self._client(self.boss).post(
            SWAP_URL, {'student_a_id': student_a.id, 'student_b_id': student_b.id}, format='json',
        )

        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertEqual(resp.data, {
            'success': True,
            'message': 'Students swapped successfully',
            'student_a': {
                'student_id': student_a.id, 'room_id': room_b.id, 'bed_id': self._first_bed(room_b).id,
            },
            'student_b': {
                'student_id': student_b.id, 'room_id': room_a.id, 'bed_id': self._first_bed(room_a).id,
            },
        })
        self._assert_swapped(room_a, room_b, student_a, student_b, old_a, old_b)

    def test_swap_missing_identifier_returns_400(self):
        _, _, student_a, _, _, _ = self._placed_pair()
        before = self._state()

        resp = self._client(self.boss).post(SWAP_URL, {'student_a_id': student_a.id}, format='json')

        self.assertEqual(resp.status_code, 400, resp.data)
        self.assertEqual(resp.data, {'error': 'Missing student_a_id or student_b_id'})
        self.assertEqual(self._state(), before)

    def test_swap_unknown_student_returns_404(self):
        _, _, student_a, _, _, _ = self._placed_pair()
        before = self._state()

        resp = self._client(self.boss).post(
            SWAP_URL, {'student_a_id': student_a.id, 'student_b_id': 999999}, format='json',
        )

        self.assertEqual(resp.status_code, 404, resp.data)
        self.assertEqual(resp.data, {'error': 'Student not found'})
        self.assertEqual(self._state(), before)

    def test_swap_requires_both_students_to_have_active_assignments(self):
        room_a, _ = self._two_single_rooms()
        student_a = self._student('S4-A', self.dorm_type)
        student_b = self._student('S4-B', self.dorm_type)
        self._place(student_a, self._first_bed(room_a))
        before = self._state()

        resp = self._client(self.boss).post(
            SWAP_URL, {'student_a_id': student_a.id, 'student_b_id': student_b.id}, format='json',
        )

        self.assertEqual(resp.status_code, 400, resp.data)
        self.assertEqual(resp.data, {'error': 'Both students must have active assignments before swapping'})
        self.assertEqual(self._state(), before)

    def test_swap_students_in_same_room_rejected(self):
        _, _, (room,) = self._apartment(
            self.dorm_type, category=Apartment.Category.MALE,
            apartment_type=Apartment.ApartmentType.SINGLE, rooms=[('101', 2)],
        )
        beds = list(room.beds.order_by('id'))
        student_a = self._student('S5-A', self.dorm_type)
        student_b = self._student('S5-B', self.dorm_type)
        self._place(student_a, beds[0])
        self._place(student_b, beds[1])
        before = self._state()

        resp = self._client(self.boss).post(
            SWAP_URL, {'student_a_id': student_a.id, 'student_b_id': student_b.id}, format='json',
        )

        self.assertEqual(resp.status_code, 400, resp.data)
        self.assertEqual(resp.data, {'error': 'שני הסטודנטים כבר נמצאים באותו חדר'})
        self.assertEqual(self._state(), before)

    def test_swap_across_regions_by_regional_user_forbidden_and_unchanged(self):
        other_region = self._region('s6-other')
        other_dorm_type = self._dorm_type(other_region)
        room_a, room_b = self._two_single_rooms(dorm_type_b=other_dorm_type)
        student_a = self._student('S6-A', self.dorm_type)
        student_b = self._student('S6-B', other_dorm_type)
        self._place(student_a, self._first_bed(room_a))
        self._place(student_b, self._first_bed(room_b))
        before = self._state()

        resp = self._client(self.boss).post(
            SWAP_URL, {'student_a_id': student_a.id, 'student_b_id': student_b.id}, format='json',
        )

        self.assertEqual(resp.status_code, 403, resp.data)
        self.assertEqual(resp.data, {'error': 'אין הרשאה לערוך אחד מהחדרים'})
        self.assertEqual(self._state(), before)

    def test_swap_with_incompatible_housing_rejected_and_unchanged(self):
        room_a, room_b = self._two_single_rooms(
            category_a=Apartment.Category.MALE, category_b=Apartment.Category.FEMALE,
        )
        student_a = self._student('S7-A', self.dorm_type)
        student_b = self._student(
            'S7-B', self.dorm_type,
            housing_type=Student.HousingType.SINGLE_FEMALE, gender=Student.Gender.FEMALE,
        )
        self._place(student_a, self._first_bed(room_a))
        self._place(student_b, self._first_bed(room_b))
        before = self._state()

        resp = self._client(self.boss).post(
            SWAP_URL, {'student_a_id': student_a.id, 'student_b_id': student_b.id}, format='json',
        )

        self.assertEqual(resp.status_code, 400, resp.data)
        self.assertEqual(resp.data, {
            'error': 'Housing category mismatch: student requires category=male, '
                     'but apartment has category=female.',
        })
        self.assertEqual(self._state(), before)

    def test_swap_of_couple_records_rejected_by_exclusivity_prevalidation(self):
        """
        Characterizes current behaviour, not desired policy: both directions
        are validated while the partner's assignment is still active, so two
        couple (Z3) records can never be swapped - the exclusivity rule
        rejects the swap before anything is written.
        """
        room_a, room_b = self._two_single_rooms(
            category_a=Apartment.Category.MIXED, category_b=Apartment.Category.MIXED,
            apartment_type=Apartment.ApartmentType.COUPLE,
        )
        student_a = self._student('S8-A', self.dorm_type, housing_type=Student.HousingType.COUPLE)
        student_b = self._student('S8-B', self.dorm_type, housing_type=Student.HousingType.COUPLE)
        self._place(student_a, self._first_bed(room_a))
        self._place(student_b, self._first_bed(room_b))
        before = self._state()

        resp = self._client(self.boss).post(
            SWAP_URL, {'student_a_id': student_a.id, 'student_b_id': student_b.id}, format='json',
        )

        self.assertEqual(resp.status_code, 400, resp.data)
        self.assertEqual(resp.data, {
            'error': 'This apartment already has an active assignment. Exclusive '
                     'couple/family apartments may only be assigned to one Student record.',
        })
        self.assertEqual(self._state(), before)

    def test_swap_request_approval_swaps_rooms(self):
        room_a, room_b, student_a, student_b, old_a, old_b = self._placed_pair()
        request = StudentRequest.objects.create(
            request_type=StudentRequest.RequestType.SWAP, reason='swap',
            requested_by=self.boss, student=student_a, swap_with_student=student_b,
            request_number='REQ-CHAR-S9',
        )

        resp = self._client(self.boss).put(f'/api/requests/{request.id}/approve/', {}, format='json')

        self.assertEqual(resp.status_code, 200, resp.data)
        request.refresh_from_db()
        self.assertEqual(request.status, StudentRequest.Status.APPROVED)
        self._assert_swapped(room_a, room_b, student_a, student_b, old_a, old_b)


class MoveCharacterizationTests(RoomAssignmentFixtures):
    """POST /api/room-assignments/move/"""

    def test_move_from_foreign_region_room_forbidden_and_unchanged(self):
        source_region = self._region('m1-source')
        target_region = self._region('m1-target')
        source_dorm_type = self._dorm_type(source_region)
        target_dorm_type = self._dorm_type(target_region)
        _, _, (source_room,) = self._apartment(
            source_dorm_type, category=Apartment.Category.MALE,
            apartment_type=Apartment.ApartmentType.SINGLE, rooms=[('101', 1)],
        )
        _, _, (target_room,) = self._apartment(
            target_dorm_type, category=Apartment.Category.MALE,
            apartment_type=Apartment.ApartmentType.SINGLE, rooms=[('101', 1)],
        )
        student = self._student('M1-S', source_dorm_type)
        self._place(student, self._first_bed(source_room))
        target_boss = self._boss(target_region)
        before = self._state()

        resp = self._client(target_boss).post(
            MOVE_URL, {'student_id': student.id, 'room_id': target_room.id}, format='json',
        )

        self.assertEqual(resp.status_code, 403, resp.data)
        self.assertEqual(resp.data, {'error': 'אין הרשאה להעביר סטודנט מאזור זה'})
        self.assertEqual(self._state(), before)


class AssignValidationCharacterizationTests(RoomAssignmentFixtures):
    """Validation and bed-check branches reached through POST /api/room-assignments/assign/."""

    def setUp(self):
        super().setUp()
        self.region = self._region('v1')
        self.dorm_type = self._dorm_type(self.region)
        self.boss = self._boss(self.region)
        self.client = self._client(self.boss)

    def _assert_rejected(self, student, room, expected_error, bed_id=None):
        payload = {'student_id': student.id, 'room_id': room.id}
        if bed_id is not None:
            payload['bed_id'] = bed_id
        resp = self.client.post(ASSIGN_URL, payload, format='json')
        self.assertEqual(resp.status_code, 400, resp.data)
        self.assertEqual(resp.data, {'error': expected_error})
        self.assertFalse(BedAssignment.objects.filter(student=student).exists())
        student.refresh_from_db()
        self.assertIsNone(student.assigned_room_id)

    def _male_single_room(self):
        return self._apartment(
            self.dorm_type, category=Apartment.Category.MALE,
            apartment_type=Apartment.ApartmentType.SINGLE, rooms=[('101', 1)],
        )

    def test_assign_rejects_inactive_room_apartment_and_building(self):
        with self.subTest('inactive room'):
            _, _, (room,) = self._male_single_room()
            Room.objects.filter(pk=room.pk).update(is_active=False)
            self._assert_rejected(self._student('V1-ROOM', self.dorm_type), room,
                                  'The selected room is inactive.')

        with self.subTest('inactive apartment'):
            _, apartment, (room,) = self._male_single_room()
            Apartment.objects.filter(pk=apartment.pk).update(
                is_active=False, inactive_reason=Apartment.InactiveReason.MAINTENANCE,
            )
            self._assert_rejected(self._student('V1-APT', self.dorm_type), room,
                                  'Apartment is inactive: תחזוקה')

        with self.subTest('inactive building'):
            building, _, (room,) = self._male_single_room()
            Building.objects.filter(pk=building.pk).update(is_active=False)
            self._assert_rejected(self._student('V1-BLD', self.dorm_type), room,
                                  'The selected building is inactive.')

    def test_assign_rejects_category_and_type_mismatch(self):
        with self.subTest('category mismatch'):
            _, _, (room,) = self._male_single_room()
            student = self._student(
                'V2-CAT', self.dorm_type,
                housing_type=Student.HousingType.SINGLE_FEMALE, gender=Student.Gender.FEMALE,
            )
            self._assert_rejected(
                student, room,
                'Housing category mismatch: student requires category=female, '
                'but apartment has category=male.',
            )

        with self.subTest('type mismatch'):
            _, _, (room,) = self._apartment(
                self.dorm_type, category=Apartment.Category.MIXED,
                apartment_type=Apartment.ApartmentType.COUPLE, rooms=[('101', 1)],
            )
            self._assert_rejected(
                self._student('V2-TYPE', self.dorm_type), room,
                'Housing type mismatch: student requires apartment_type=single, '
                'but apartment has apartment_type=couple.',
            )

    def test_assign_z6_requires_couple_layout_and_blocks_non_z6_entrants(self):
        with self.subTest('Z6 into a single-layout apartment'):
            _, _, (room,) = self._male_single_room()
            student = self._student('V3-Z6', self.dorm_type,
                                    housing_type=Student.HousingType.SINGLE_IN_APARTMENT)
            self._assert_rejected(student, room, 'Z6 requires a couple-layout apartment.')

        with self.subTest('non-Z6 into an apartment reserved by a Z6 resident'):
            _, _, (resident_room, free_room) = self._apartment(
                self.dorm_type, category=Apartment.Category.MIXED,
                apartment_type=Apartment.ApartmentType.COUPLE, rooms=[('101', 1), ('102', 1)],
            )
            resident = self._student('V3-RES', self.dorm_type,
                                     housing_type=Student.HousingType.SINGLE_IN_APARTMENT)
            self._place(resident, self._first_bed(resident_room))
            self._assert_rejected(
                self._student('V3-Z1', self.dorm_type), free_room,
                'This apartment is reserved exclusively for a Z6 resident.',
            )

    def test_assign_specific_bed_from_another_room_rejected(self):
        _, _, (room, other_room) = self._apartment(
            self.dorm_type, category=Apartment.Category.MALE,
            apartment_type=Apartment.ApartmentType.SINGLE, rooms=[('101', 1), ('102', 1)],
        )
        self._assert_rejected(
            self._student('V4-S', self.dorm_type), room,
            'המיטה שנבחרה אינה שייכת לחדר זה',
            bed_id=self._first_bed(other_room).id,
        )


class OverrideBedCheckCharacterizationTests(RoomAssignmentFixtures):
    """POST /api/assisted-allocation/students/<pk>/override/ (skip_validation=True path)."""

    def test_override_into_inactive_room_still_rejected(self):
        region = self._region('o1')
        dorm_type = self._dorm_type(region)
        boss = self._boss(region)
        _, _, (room,) = self._apartment(
            dorm_type, category=Apartment.Category.FEMALE,
            apartment_type=Apartment.ApartmentType.SINGLE, rooms=[('101', 2)],
        )
        beds = list(room.beds.order_by('id'))
        # A religion-only (overridable) violation, as in ManualOverrideTests.
        resident = self._student(
            'O1-RES', dorm_type,
            housing_type=Student.HousingType.SINGLE_FEMALE, gender=Student.Gender.FEMALE,
            requested_religion=Student.Religion.Jewish, religious=Student.Religious.RELIGIOUS,
        )
        resident_assignment = self._place(resident, beds[0])
        student = self._student(
            'O1-S', dorm_type,
            housing_type=Student.HousingType.SINGLE_FEMALE, gender=Student.Gender.FEMALE,
            requested_religion=Student.Religion.Muslim,
        )
        Room.objects.filter(pk=room.pk).update(is_active=False)

        resp = self._client(boss).post(
            f'/api/assisted-allocation/students/{student.id}/override/',
            {'bed_id': beds[1].id, 'note': 'characterization'},
            format='json',
        )

        self.assertEqual(resp.status_code, 400, resp.data)
        self.assertEqual(resp.data, {'error': 'החדר אינו פעיל'})
        self.assertFalse(BedAssignment.objects.filter(student=student).exists())
        self.assertFalse(AssistedAllocationAudit.objects.filter(student=student).exists())
        resident_assignment.refresh_from_db()
        self.assertEqual(resident_assignment.status, BedAssignment.Status.ACTIVE)
        student.refresh_from_db()
        self.assertIsNone(student.assigned_room_id)
