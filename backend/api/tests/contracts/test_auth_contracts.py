"""Contracts of /api/auth/* (login, refresh, me, logout, change-password, change-email)."""

from django.conf import settings
from rest_framework.test import APIClient

from api.serializers import UserSerializer

from ._support import ContractTestCase, serializer_keys

USER_KEYS = serializer_keys(UserSerializer)


class AuthContractTests(ContractTestCase):
    def test_login_success_body_and_refresh_cookie(self):
        response = APIClient().post('/api/auth/login/', {'email': self.boss.email, 'password': 'x'}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertKeys(response.data, ['message', 'messageEn', 'user', 'access'])
        self.assertKeys(response.data['user'], USER_KEYS)
        self.assertEqual(response.data['user']['region'], self.region.id)
        self.assertIsInstance(response.data['access'], str)
        self.assertIn(settings.JWT_REFRESH_COOKIE_NAME, response.cookies)
        self.assertNotIn('refresh', response.data)

    def test_login_failure_wraps_serializer_errors_under_error(self):
        response = APIClient().post('/api/auth/login/', {'email': self.boss.email, 'password': 'wrong'}, format='json')
        self.assertEqual(response.status_code, 401)
        self.assertKeys(response.data, ['error', 'errorHe'])
        self.assertIn('non_field_errors', response.data['error'])
        self.assertEqual(response.data['errorHe'], 'אימייל או סיסמה שגויים')

    def test_refresh_without_cookie_and_me(self):
        self.assertErrorBody(APIClient().post('/api/auth/refresh/'), 401, 'לא נמצא טוקן רענון')
        response = self.client_for(self.employee).get('/api/auth/me/')
        self.assertEqual(response.status_code, 200)
        self.assertKeys(response.data, ['user'])
        self.assertKeys(response.data['user'], USER_KEYS)
        self.assertEqual(response.data['user']['role'], 'employee')

    def test_unauthenticated_requests_get_drf_detail_bodies(self):
        self.assertDetailBody(APIClient().get('/api/auth/me/'), 401)
        self.assertDetailBody(APIClient().get('/api/students/'), 401)

    def test_logout_is_idempotent(self):
        response = APIClient().post('/api/auth/logout/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, {'success': True, 'message': 'התנתקת בהצלחה'})

    def test_change_password_validation_and_success(self):
        client = self.client_for(self.employee)
        self.assertFailureBody(client.put('/api/auth/change-password/', {}, format='json'), 400, 'יש למלא את כל השדות')
        self.assertFailureBody(
            client.put('/api/auth/change-password/', {
                'current_password': 'nope', 'new_password': 'longenough', 'confirm_password': 'longenough',
            }, format='json'),
            400, 'הסיסמה הנוכחית אינה נכונה',
        )
        self.assertFailureBody(
            client.put('/api/auth/change-password/', {
                'current_password': 'x', 'new_password': 'short', 'confirm_password': 'short',
            }, format='json'),
            400, 'הסיסמה החדשה חייבת להכיל לפחות 8 תווים',
        )
        response = client.post('/api/auth/change-password/', {
            'current_password': 'x', 'new_password': 'longenough', 'confirm_password': 'longenough',
        }, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, {'success': True, 'message': 'הסיסמה עודכנה בהצלחה'})

    def test_change_email_validation_and_success(self):
        client = self.client_for(self.employee)
        self.assertFailureBody(
            client.put('/api/auth/change-email/', {'new_email': 'a@b.c'}, format='json'),
            400, 'יש למלא את כל השדות',
        )
        self.assertFailureBody(
            client.put('/api/auth/change-email/', {
                'current_email': self.employee.email, 'new_email': 'new@contract.test',
                'confirm_email': 'new@contract.test', 'password': 'wrong',
            }, format='json'),
            400, 'הסיסמה שגויה',
        )
        response = client.put('/api/auth/change-email/', {
            'current_email': self.employee.email, 'new_email': 'new@contract.test',
            'confirm_email': 'new@contract.test', 'password': 'x',
        }, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertKeys(response.data, ['success', 'message', 'user'])
        self.assertKeys(response.data['user'], USER_KEYS)
        self.assertEqual(response.data['user']['email'], 'new@contract.test')
