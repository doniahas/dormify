"""
Tests for the best-match ranking service (roommate priority, hard
constraints, history) and the no-percentage response contract.

Run against Django's disposable TEST database (created/destroyed as
test_<DB_NAME> - never touches the real `dormify` database):

    docker exec dormify_backend python manage.py test api.tests.functional.test_matching_ranking
"""

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from api.models import (
    User, Region, DormType, Building, Apartment, Room, Student, BedAssignment, Transfer,
)
from api.tests.support.matching_test_utils import (
    create_beds_for_room, flatten_bed_options, assert_no_score_keys,
)


def _make_user(email, role, region=None):
    user = User(email=email, username=email, role=role, region=region,
                first_name='T', last_name='User')
    user.set_password('testpass123')
    user.save()
    return user


def _make_dorm_type(region, code, name=None):
    return DormType.objects.create(code=code, name=name or f'DT{code}', region=region)


def _make_room(dorm_type, building_number, apartment_number, category,
                apartment_type=Apartment.ApartmentType.SINGLE, room_capacity=2):
    building = Building.objects.create(number=building_number, dorm_type=dorm_type)
    apartment = Apartment.objects.create(
        building=building, number=apartment_number, category=category,
        apartment_type=apartment_type, room_count=1,
    )
    room = Room.objects.create(apartment=apartment, name='101', capacity=room_capacity)
    # Matching is read-only over real Bed rows - fixtures materialize them
    # explicitly, like a properly initialized production database.
    create_beds_for_room(room)
    return building, apartment, room


def _make_student(student_id, gender, housing_type, dorm_type, **extra):
    return Student.objects.create(
        student_id=student_id, first_name='F', last_name='L',
        gender=gender, housing_type=housing_type, accepted_dorm_type=dorm_type,
        **extra,
    )


class RoommateRankingTests(TestCase):
    def setUp(self):
        self.region = Region.objects.create(id='canada', name='Canada')
        self.dorm_type = _make_dorm_type(self.region, code=1)
        self.admin = _make_user('admin@test.com', User.Role.CENTRAL_ADMIN)
        self.client = APIClient()
        self.client.force_authenticate(self.admin)

    def _match(self, student, **extra):
        payload = {'student_id': student.id}
        payload.update(extra)
        resp = self.client.post('/api/requests/match-options/', payload, format='json')
        self.assertEqual(resp.status_code, 200, resp.content)
        return resp.data

    # 1/2. No percentage or raw score ever appears anywhere in the response.
    def test_no_percentage_or_score_fields(self):
        _make_room(self.dorm_type, 1, '1', Apartment.Category.MALE)
        student = _make_student('S1', Student.Gender.MALE, Student.HousingType.SINGLE_MALE, self.dorm_type)
        data = self._match(student)
        assert_no_score_keys(dict(data))
        for opt in flatten_bed_options(data):
            self.assertIn('recommendation_level', opt)
            self.assertIn('recommendation_label', opt)

    # 2. Best Match prioritizes mutual roommate requests, and 4. a one-sided
    # request ranks below a mutual one - both verified in one scenario:
    # apartment A has the mutual-roommate resident, apartment B has a
    # one-sided (student wants them, they didn't request back) resident.
    def test_mutual_roommate_ranks_above_one_sided(self):
        _, apt_mutual, room_mutual = _make_room(self.dorm_type, 1, 'Mutual', Apartment.Category.MALE, room_capacity=2)
        _, apt_one_sided, room_one_sided = _make_room(self.dorm_type, 2, 'OneSided', Apartment.Category.MALE, room_capacity=2)

        mutual_roommate = _make_student(
            'ROOMMATE-MUTUAL', Student.Gender.MALE, Student.HousingType.SINGLE_MALE, self.dorm_type,
            roommate_request_student_id_1='STUDENT1',
        )
        one_sided_roommate = _make_student(
            'ROOMMATE-ONESIDED', Student.Gender.MALE, Student.HousingType.SINGLE_MALE, self.dorm_type,
        )
        self.client.post('/api/room-assignments/assign/', {
            'student_id': mutual_roommate.id, 'room_id': room_mutual.id,
        }, format='json')
        self.client.post('/api/room-assignments/assign/', {
            'student_id': one_sided_roommate.id, 'room_id': room_one_sided.id,
        }, format='json')

        student = _make_student(
            'STUDENT1', Student.Gender.MALE, Student.HousingType.SINGLE_MALE, self.dorm_type,
            roommate_request_student_id_1='ROOMMATE-MUTUAL',
            roommate_request_student_id_2='ROOMMATE-ONESIDED',
        )
        data = self._match(student, limit=20)
        options = flatten_bed_options(data)
        options_by_apt = {o['apartment_id']: o for o in options}
        mutual_opt = options_by_apt[apt_mutual.id]
        one_sided_opt = options_by_apt[apt_one_sided.id]

        mutual_codes = {r['code'] for r in mutual_opt['matched_reasons']}
        one_sided_codes = {r['code'] for r in one_sided_opt['matched_reasons']}
        self.assertIn('mutual_roommate_request', mutual_codes)
        self.assertIn('roommate_already_here', mutual_codes)
        self.assertNotIn('mutual_roommate_request', one_sided_codes)
        self.assertIn('roommate_already_here', one_sided_codes)

        # Mutual must rank at or above one-sided in the actual returned order.
        mutual_index = next(i for i, o in enumerate(options) if o['apartment_id'] == apt_mutual.id)
        one_sided_index = next(i for i, o in enumerate(options) if o['apartment_id'] == apt_one_sided.id)
        self.assertLess(mutual_index, one_sided_index)
        self.assertEqual(mutual_opt['recommendation_level'], 'best')

    # 3. A requested roommate already assigned to an apartment increases
    # that apartment's ranking relative to a plain empty apartment.
    def test_roommate_already_assigned_ranks_above_plain_empty(self):
        _, apt_roommate, room_roommate = _make_room(self.dorm_type, 1, 'WithRoommate', Apartment.Category.MALE, room_capacity=2)
        _, apt_plain, _room_plain = _make_room(self.dorm_type, 2, 'PlainEmpty', Apartment.Category.MALE, room_capacity=2)

        roommate = _make_student('ROOMMATE', Student.Gender.MALE, Student.HousingType.SINGLE_MALE, self.dorm_type)
        self.client.post('/api/room-assignments/assign/', {
            'student_id': roommate.id, 'room_id': room_roommate.id,
        }, format='json')

        student = _make_student(
            'STUDENT2', Student.Gender.MALE, Student.HousingType.SINGLE_MALE, self.dorm_type,
            roommate_request_student_id_1='ROOMMATE',
        )
        data = self._match(student, limit=20)
        options = flatten_bed_options(data)
        roommate_index = next(i for i, o in enumerate(options) if o['apartment_id'] == apt_roommate.id)
        plain_index = next(i for i, o in enumerate(options) if o['apartment_id'] == apt_plain.id)
        self.assertLess(roommate_index, plain_index)

    # 5. A MUTUAL roommate request whose roommate is not yet assigned
    # anywhere prefers an apartment with capacity for both students over a
    # single-remaining-bed apartment.
    def test_future_roommate_capacity_preferred_when_roommate_unassigned(self):
        _, apt_two_beds, _room_two = _make_room(self.dorm_type, 1, 'TwoBeds', Apartment.Category.MALE, room_capacity=2)
        _, apt_one_bed, room_one = _make_room(self.dorm_type, 2, 'OneBed', Apartment.Category.MALE, room_capacity=2)
        # Fill one bed in apt_one_bed so only 1 remains - can't fit both
        # the student and their not-yet-assigned roommate.
        filler = _make_student('FILLER', Student.Gender.MALE, Student.HousingType.SINGLE_MALE, self.dorm_type)
        self.client.post('/api/room-assignments/assign/', {
            'student_id': filler.id, 'room_id': room_one.id,
        }, format='json')

        # The roommate exists, is unassigned, and requested STUDENT3 back -
        # a real mutual request (required by ranking case 3).
        _make_student(
            'ROOMMATE-NEW', Student.Gender.MALE, Student.HousingType.SINGLE_MALE, self.dorm_type,
            roommate_request_student_id_1='STUDENT3',
        )
        student = _make_student(
            'STUDENT3', Student.Gender.MALE, Student.HousingType.SINGLE_MALE, self.dorm_type,
            roommate_request_student_id_1='ROOMMATE-NEW',
        )
        data = self._match(student, limit=20)
        options = flatten_bed_options(data)
        options_by_apt = {o['apartment_id']: o for o in options}
        two_beds_opt = options_by_apt[apt_two_beds.id]
        two_beds_codes = {r['code'] for r in two_beds_opt['matched_reasons']}
        self.assertIn('roommate_future_capacity', two_beds_codes)

        two_index = next(i for i, o in enumerate(options) if o['apartment_id'] == apt_two_beds.id)
        one_index = next(i for i, o in enumerate(options) if o['apartment_id'] == apt_one_bed.id)
        self.assertLess(two_index, one_index)

    # 5b. A one-sided request (the other student never requested back) must
    # NOT receive the future-capacity boost - the tier is mutual-only.
    def test_future_roommate_capacity_requires_mutual_request(self):
        _, apt_two_beds, _ = _make_room(self.dorm_type, 1, 'TwoBeds', Apartment.Category.MALE, room_capacity=2)
        _make_student(
            'ROOMMATE-ONE-WAY', Student.Gender.MALE, Student.HousingType.SINGLE_MALE, self.dorm_type,
        )
        student = _make_student(
            'STUDENT3B', Student.Gender.MALE, Student.HousingType.SINGLE_MALE, self.dorm_type,
            roommate_request_student_id_1='ROOMMATE-ONE-WAY',
        )
        data = self._match(student, limit=20)
        options_by_apt = {o['apartment_id']: o for o in flatten_bed_options(data)}
        codes = {r['code'] for r in options_by_apt[apt_two_beds.id]['matched_reasons']}
        self.assertNotIn('roommate_future_capacity', codes)

    # 6. Hard constraints always override roommate preferences - a roommate
    # sitting in a wrong-gender apartment must never be recommended there.
    def test_hard_constraint_overrides_roommate_preference(self):
        _, female_apt, female_room = _make_room(self.dorm_type, 1, 'F1', Apartment.Category.FEMALE)
        roommate = _make_student('ROOMMATE-F', Student.Gender.FEMALE, Student.HousingType.SINGLE_FEMALE, self.dorm_type)
        self.client.post('/api/room-assignments/assign/', {
            'student_id': roommate.id, 'room_id': female_room.id,
        }, format='json')

        male_student = _make_student(
            'STUDENT4', Student.Gender.MALE, Student.HousingType.SINGLE_MALE, self.dorm_type,
            roommate_request_student_id_1='ROOMMATE-F',
        )
        data = self._match(male_student)
        returned_apartment_ids = {o['apartment_id'] for o in flatten_bed_options(data)}
        self.assertNotIn(female_apt.id, returned_apartment_ids)

        # And the conflict explanation (when nothing else is valid) names
        # the roommate-incompatibility explicitly rather than staying silent.
        if not data['buildings'] and data.get('conflict_examples'):
            all_conflicts = [c for ex in data['conflict_examples'] for c in ex['conflicts']]
            self.assertTrue(any('השותף המבוקש' in c for c in all_conflicts))

    # 7/8. Historical reasons are shown only when real Transfer history
    # exists, and are explainable (a fixed, non-invented code+label).
    def test_historical_reason_only_appears_with_real_transfer_record(self):
        # apt_b lives under a DIFFERENT dorm_type than apt_a/the transfer's
        # to_room, so the two are genuinely distinguishable - a shared
        # dorm_type would legitimately flag both (history is dormitory-level,
        # the coarsest concept the data actually supports).
        other_dorm_type = _make_dorm_type(self.region, code=2)
        _, apt_a, room_a = _make_room(self.dorm_type, 1, 'A', Apartment.Category.MALE)
        _, apt_b, _room_b = _make_room(other_dorm_type, 2, 'B', Apartment.Category.MALE)

        student = _make_student('STUDENT5', Student.Gender.MALE, Student.HousingType.SINGLE_MALE, self.dorm_type)

        # No transfer history yet - no historical_reasons anywhere.
        data_before = self._match(student, limit=20)
        for opt in flatten_bed_options(data_before):
            self.assertEqual(opt['historical_reasons'], [])

        # Give the student a real, stored transfer request that named
        # apt_a's building (a previous rejected request - still real
        # interest, must not be invented from nothing).
        requester = _make_user('req@test.com', User.Role.CENTRAL_ADMIN)
        other_room_for_from = _make_room(self.dorm_type, 3, 'From', Apartment.Category.MALE)[2]
        Transfer.objects.create(
            student=student, from_room=other_room_for_from, to_room=room_a,
            status=Transfer.Status.REJECTED,
            requested_by=requester, reviewed_by=requester,
            reviewed_at=timezone.now(),
        )

        data_after = self._match(student, limit=20)
        options_by_apt = {o['apartment_id']: o for o in flatten_bed_options(data_after)}
        opt_a = options_by_apt[apt_a.id]
        opt_b = options_by_apt[apt_b.id]
        self.assertTrue(any(r['code'] == 'previously_requested_dormitory' for r in opt_a['historical_reasons']))
        self.assertEqual(opt_b['historical_reasons'], [])


class MatchingCharacterizationGateTests(TestCase):
    """Pin reachable matching behavior before the ranking engine is moved."""

    def setUp(self):
        self.region = Region.objects.create(id='characterization', name='Characterization')
        self.dorm_type = _make_dorm_type(self.region, code=10)
        self.admin = _make_user('characterization@test.com', User.Role.CENTRAL_ADMIN)
        self.client = APIClient()
        self.client.force_authenticate(self.admin)

    def _match_student(self, student, **extra):
        payload = {'student_id': student.id, 'limit': 20}
        payload.update(extra)
        response = self.client.post('/api/requests/match-options/', payload, format='json')
        self.assertEqual(response.status_code, 200, response.content)
        return response.data

    def test_transient_student_data_infers_single_male_candidate_compatibility(self):
        _, male_apartment, _ = _make_room(
            self.dorm_type, 1, 'Male', Apartment.Category.MALE,
        )
        _, female_apartment, _ = _make_room(
            self.dorm_type, 2, 'Female', Apartment.Category.FEMALE,
        )

        response = self.client.post('/api/requests/match-options/', {
            'student_data': {'gender': Student.Gender.MALE, 'dorm_type': 'single'},
            'limit': 20,
        }, format='json')

        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(response.data['feasible'])
        apartment_ids = {option['apartment_id'] for option in flatten_bed_options(response.data)}
        self.assertIn(male_apartment.id, apartment_ids)
        self.assertNotIn(female_apartment.id, apartment_ids)

    def test_occupied_match_reports_year_mix_and_compatible_soft_reasons(self):
        _, apartment, room = _make_room(
            self.dorm_type, 1, 'Signals', Apartment.Category.MALE, room_capacity=2,
        )
        resident = _make_student(
            'SIGNAL-RESIDENT', Student.Gender.MALE, Student.HousingType.SINGLE_MALE,
            self.dorm_type, requested_religion=Student.Religion.Jewish,
            placement_sector=Student.PlacementSector.OTHER, city='Haifa', study_points=80,
        )
        assign_response = self.client.post('/api/room-assignments/assign/', {
            'student_id': resident.id, 'room_id': room.id,
        }, format='json')
        self.assertEqual(assign_response.status_code, 200, assign_response.content)

        student = _make_student(
            'SIGNAL-CANDIDATE', Student.Gender.MALE, Student.HousingType.SINGLE_MALE,
            self.dorm_type, requested_religion=Student.Religion.Jewish,
            placement_sector=Student.PlacementSector.OTHER, city=' haifa ', study_points=20,
            is_priority=True,
        )

        data = self._match_student(student)
        option = next(
            item for item in flatten_bed_options(data)
            if item['apartment_id'] == apartment.id and item['is_selectable']
        )
        matched = {reason['code']: reason['label'] for reason in option['matched_reasons']}
        warnings = {reason['code']: reason['label'] for reason in option['warnings']}

        self.assertEqual(matched['religion_match'], 'התאמה דתית/עדתית')
        self.assertEqual(matched['sector_match'], 'התאמת סקטור שיבוץ')
        self.assertEqual(matched['city_match'], 'התאמת עיר מגורים')
        self.assertEqual(matched['priority_student'], 'סטודנט/ית בעדיפות')
        self.assertEqual(
            warnings,
            {'year_mix_conflict': 'ערבוב שנתונים בדירה (שנה א׳ עם שנה ג׳-ד׳)'},
        )
        self.assertEqual(option['match_level'], 'warning')
        self.assertEqual(option['recommendation_level'], 'warning')

    def test_z6_accepts_empty_couple_layout_and_rejects_single_layout(self):
        _, valid_apartment, _ = _make_room(
            self.dorm_type, 1, 'Z6-valid', Apartment.Category.MIXED,
            apartment_type=Apartment.ApartmentType.COUPLE,
        )
        _, invalid_apartment, _ = _make_room(
            self.dorm_type, 2, 'Z6-invalid', Apartment.Category.MIXED,
            apartment_type=Apartment.ApartmentType.SINGLE,
        )
        student = _make_student(
            'Z6-CANDIDATE', Student.Gender.MALE, Student.HousingType.SINGLE_IN_APARTMENT,
            self.dorm_type,
        )

        apartment_ids = {
            option['apartment_id'] for option in flatten_bed_options(self._match_student(student))
        }

        self.assertEqual(apartment_ids, {valid_apartment.id})
        self.assertNotIn(invalid_apartment.id, apartment_ids)

    def test_non_z6_apartment_type_mismatch_reports_distinct_conflict(self):
        _make_room(
            self.dorm_type, 1, 'Wrong-layout', Apartment.Category.MALE,
            apartment_type=Apartment.ApartmentType.COUPLE,
        )
        student = _make_student(
            'TYPE-MISMATCH', Student.Gender.MALE, Student.HousingType.SINGLE_MALE,
            self.dorm_type,
        )

        data = self._match_student(student)

        self.assertFalse(data['feasible'])
        self.assertEqual(data['buildings'], [])
        conflicts = [
            reason for example in data['conflict_examples'] for reason in example['conflicts']
        ]
        self.assertIn('אי-התאמת סוג הדירה לסוג הדיור של הסטודנט', conflicts)
        self.assertNotIn('אי-התאמת מגדר/קטגוריית הדירה', conflicts)

    def test_existing_z6_resident_excludes_non_z6_candidate(self):
        _, _, room = _make_room(
            self.dorm_type, 1, 'Z6-resident', Apartment.Category.MALE, room_capacity=2,
        )
        z6_resident = _make_student(
            'Z6-RESIDENT', Student.Gender.MALE, Student.HousingType.SINGLE_IN_APARTMENT,
            self.dorm_type,
        )
        BedAssignment.objects.create(
            student=z6_resident,
            bed=room.beds.order_by('id').first(),
            status=BedAssignment.Status.ACTIVE,
        )
        student = _make_student(
            'NON-Z6-CANDIDATE', Student.Gender.MALE, Student.HousingType.SINGLE_MALE,
            self.dorm_type,
        )

        data = self._match_student(student)

        self.assertFalse(data['feasible'])
        conflicts = [
            reason for example in data['conflict_examples'] for reason in example['conflicts']
        ]
        self.assertIn(
            'הדירה שמורה בלעדית לדייר/ת בשיבוץ רווקים/ות בדירה',
            conflicts,
        )

    def test_same_apartment_filters_include_and_exclude_current_apartment(self):
        _, current_apartment, current_room = _make_room(
            self.dorm_type, 1, 'Current', Apartment.Category.MALE, room_capacity=1,
        )
        same_apartment_room = Room.objects.create(
            apartment=current_apartment, name='102', capacity=1,
        )
        create_beds_for_room(same_apartment_room)
        _, _, outside_room = _make_room(
            self.dorm_type, 2, 'Outside', Apartment.Category.MALE, room_capacity=1,
        )
        student = _make_student(
            'SAME-APARTMENT', Student.Gender.MALE, Student.HousingType.SINGLE_MALE,
            self.dorm_type,
        )
        assign_response = self.client.post('/api/room-assignments/assign/', {
            'student_id': student.id, 'room_id': current_room.id,
        }, format='json')
        self.assertEqual(assign_response.status_code, 200, assign_response.content)

        inside_ids = {
            option['room_id']
            for option in flatten_bed_options(self._match_student(student, same_apartment=True))
            if option['is_selectable']
        }
        outside_ids = {
            option['room_id']
            for option in flatten_bed_options(self._match_student(student, same_apartment=False))
            if option['is_selectable']
        }

        self.assertEqual(inside_ids, {same_apartment_room.id})
        self.assertEqual(outside_ids, {outside_room.id})
