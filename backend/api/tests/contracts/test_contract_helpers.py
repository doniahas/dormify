"""Direct tests for api.contracts.errors and api.contracts.requests."""

from django.test import SimpleTestCase
from rest_framework import status

from api.contracts import errors, requests


class ErrorBodyTests(SimpleTestCase):
    def test_error_body_shapes_and_key_order(self):
        self.assertEqual(errors.error_body('x'), {'error': 'x'})
        self.assertEqual(list(errors.error_body('x', error_en='y', status='s')), ['error', 'errorEn', 'status'])
        self.assertEqual(
            list(errors.error_body('x', run_id=4, status='running')),
            ['error', 'run_id', 'status'],
        )

    def test_failure_body_shapes_and_key_order(self):
        self.assertEqual(errors.failure_body('x'), {'success': False, 'error': 'x'})
        self.assertEqual(
            list(errors.failure_body('x', error_en='y', error_type='T')),
            ['success', 'error', 'errorEn', 'error_type'],
        )
        self.assertEqual(
            list(errors.failure_body('x', error_code='C', region='r', run_id=1, run={})),
            ['success', 'error', 'error_code', 'region', 'run_id', 'run'],
        )

    def test_responses_carry_the_status(self):
        response = errors.error_response(status.HTTP_404_NOT_FOUND, 'missing')
        self.assertEqual((response.status_code, response.data), (404, {'error': 'missing'}))
        response = errors.failure_response(status.HTTP_409_CONFLICT, 'busy', error_code='X')
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data, {'success': False, 'error': 'busy', 'error_code': 'X'})


class AllocationRunRequestTests(SimpleTestCase):
    def test_region_aliases_in_precedence_order(self):
        self.assertEqual(requests.parse_allocation_run_request({'region': 'a', 'region_id': 'b'}).region_value, 'a')
        self.assertEqual(requests.parse_allocation_run_request({'region_id': 'b', 'region_name': 'c'}).region_value, 'b')
        self.assertEqual(requests.parse_allocation_run_request({'region_name': 'c'}).region_value, 'c')
        self.assertIsNone(requests.parse_allocation_run_request({}).region_value)
        self.assertIsNone(requests.parse_allocation_run_request({'region': ''}).region_value)

    def test_include_assigned_requires_the_json_literal_true(self):
        self.assertIs(requests.parse_allocation_run_request({'include_assigned': True}).include_assigned, True)
        for loose in ('true', 1, 'yes', None, False):
            self.assertIs(requests.parse_allocation_run_request({'include_assigned': loose}).include_assigned, False, loose)

    def test_raw_fields_pass_through_unchanged(self):
        parsed = requests.parse_allocation_run_request({
            'constraints': 'not-a-dict', 'allocation_scope': 'new_transfer_only', 'max_solver_seconds': '90',
        })
        self.assertEqual(parsed.constraints, 'not-a-dict')
        self.assertEqual(parsed.allocation_scope, 'new_transfer_only')
        self.assertEqual(parsed.max_solver_seconds, '90')
        self.assertIsNone(requests.parse_allocation_run_request({}).max_solver_seconds)


class WhatIfRequestTests(SimpleTestCase):
    def test_building_ids_aliases_and_rejections(self):
        self.assertEqual(requests.parse_building_ids({'building_ids': [1, 2]}), [1, 2])
        self.assertEqual(requests.parse_building_ids({'buildings': [3]}), [3])
        for bad in ({}, {'building_ids': []}, {'building_ids': 'x'}, {'building_ids': None}):
            with self.assertRaises(ValueError) as raised:
                requests.parse_building_ids(bad)
            self.assertEqual(str(raised.exception), 'building_ids must be a non-empty list.')

    def test_target_selection_defaults_validates_and_deduplicates(self):
        target_type, ids = requests.parse_target_selection({'target_ids': [5, 5, 6]})
        self.assertEqual(target_type, 'building')
        self.assertEqual(sorted(ids), [5, 6])
        self.assertEqual(requests.parse_target_selection({'target_type': 'room', 'target_ids': [9]})[0], 'room')
        with self.assertRaises(ValueError) as raised:
            requests.parse_target_selection({'target_type': 'bed', 'target_ids': [1]})
        self.assertEqual(str(raised.exception), 'target_type must be one of: building, apartment, room.')
        with self.assertRaises(ValueError) as raised:
            requests.parse_target_selection({'target_type': 'room'})
        self.assertEqual(str(raised.exception), 'target_ids must be a non-empty list.')

    def test_availability_action(self):
        self.assertEqual(requests.parse_availability_action({}), 'inactivate')
        self.assertEqual(requests.parse_availability_action({'action': 'reactivate'}), 'reactivate')
        with self.assertRaises(ValueError) as raised:
            requests.parse_availability_action({'action': 'activate'})
        self.assertEqual(str(raised.exception), 'action must be inactivate or reactivate.')


class PlacementAndMatchRequestTests(SimpleTestCase):
    def test_student_and_room_references(self):
        self.assertEqual(requests.student_reference({'student_id': 7}), 7)
        self.assertEqual(requests.student_reference({'student': 'S-1'}), 'S-1')
        self.assertEqual(requests.student_reference({'student_a_id': 3, 'student': 9}, 'student_a_id'), 3)
        with self.assertRaises(ValueError) as raised:
            requests.student_reference({})
        self.assertEqual(str(raised.exception), 'Missing student_id')
        self.assertEqual(requests.room_reference({'room': 4}), 4)
        with self.assertRaises(ValueError) as raised:
            requests.room_reference({'room_id': ''})
        self.assertEqual(str(raised.exception), 'Missing room_id')

    def test_swap_pair_accepts_both_spellings(self):
        self.assertEqual(requests.swap_pair({'student_a_id': 1, 'studentBId': 2}), (1, 2))
        self.assertEqual(requests.swap_pair({}), (None, None))

    def test_match_pagination_defaults_and_clamps(self):
        self.assertEqual(requests.parse_match_pagination({}), (10, 0))
        self.assertEqual(requests.parse_match_pagination({'limit': '50', 'offset': '-3'}), (20, 0))
        self.assertEqual(requests.parse_match_pagination({'limit': 0, 'offset': 7}), (1, 7))
        self.assertEqual(requests.parse_match_pagination({'limit': 'x', 'offset': None}), (10, 0))

    def test_region_ids_normalization(self):
        self.assertEqual(requests.parse_region_ids(None), [])
        self.assertEqual(requests.parse_region_ids('north'), ['north'])
        self.assertEqual(requests.parse_region_ids(['north', '', None, 'south']), ['north', 'south'])

    def test_override_request(self):
        self.assertEqual(requests.parse_override_request({'bed_id': 3, 'note': '  why  '}), (3, 'why'))
        self.assertEqual(requests.parse_override_request({}), (None, ''))
