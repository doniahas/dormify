"""Shared base class for the contract tests."""

from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient

from api.tests.domains._fixtures import (  # noqa: F401 - re-exported for the contract modules
    assign,
    make_apartment,
    make_boss,
    make_building,
    make_central_admin,
    make_dorm,
    make_employee,
    make_full_stack,
    make_region,
    make_room,
    make_run,
    make_student,
)


def serializer_keys(serializer_class):
    """The exact output keys of a ModelSerializer (its Meta.fields)."""
    return list(serializer_class.Meta.fields)


class ContractTestCase(TestCase):
    """A region with one boss, one employee and a central admin, plus client helpers."""

    def setUp(self):
        # Throttle counters (auth_sensitive etc.) live in the process cache.
        cache.clear()
        self.region = make_region(f'Contract {self.__class__.__name__}'[:40])
        self.admin = make_central_admin(email=f'admin-{self.region.id}@contract.test')
        self.boss = make_boss(self.region, email=f'boss-{self.region.id}@contract.test')
        self.employee = make_employee(self.region, email=f'emp-{self.region.id}@contract.test')

    def client_for(self, user):
        client = APIClient()
        client.force_authenticate(user=user)
        return client

    def assertKeys(self, payload, expected, msg=None):
        """The payload carries exactly ``expected`` keys, in that order."""
        self.assertEqual(list(payload), list(expected), msg or payload)

    def assertKeySet(self, payload, expected, msg=None):
        self.assertEqual(set(payload), set(expected), msg or payload)

    def assertErrorBody(self, response, status_code, error=None, error_en=None, **extra):
        """A hand-written error body: {'error'[, 'errorEn'][, extra]} with the given status."""
        self.assertEqual(response.status_code, status_code, response.data)
        expected = ['error'] + (['errorEn'] if error_en is not None else []) + list(extra)
        self.assertKeys(response.data, expected)
        if error is not None:
            self.assertEqual(response.data['error'], error)
        if error_en is not None:
            self.assertEqual(response.data['errorEn'], error_en)
        for key, value in extra.items():
            self.assertEqual(response.data[key], value)

    def assertFailureBody(self, response, status_code, error=None, **extra):
        """A {'success': False, 'error'[, extra]} body with the given status."""
        self.assertEqual(response.status_code, status_code, response.data)
        self.assertKeys(response.data, ['success', 'error'] + list(extra))
        self.assertIs(response.data['success'], False)
        if error is not None:
            self.assertEqual(response.data['error'], error)
        for key, value in extra.items():
            self.assertEqual(response.data[key], value)

    def assertDetailBody(self, response, status_code):
        """A DRF-generated {'detail': ...} body (permission / 404 / throttle)."""
        self.assertEqual(response.status_code, status_code, response.data)
        self.assertKeys(response.data, ['detail'])
