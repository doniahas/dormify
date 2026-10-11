"""
G3-14 / G3-16 / G3-17: login/refresh/logout/blacklist/session-restoration
lifecycle. The refresh token must live only in an HttpOnly cookie (never
the JSON body), refresh must actually work end-to-end, rotation must
blacklist the previous refresh token, and logout must revoke it
server-side (not just clear client state).
"""

from django.conf import settings
from django.core.cache import cache
from rest_framework.test import APIClient
from rest_framework_simplejwt.token_blacklist.models import (
    BlacklistedToken, OutstandingToken,
)
from rest_framework_simplejwt.tokens import RefreshToken

from .base import SecurityTestCase, TEST_PASSWORD


class JwtLifecycleTests(SecurityTestCase):
    def setUp(self):
        super().setUp()
        # Throttle counters live in the process-wide cache rather than the
        # DB, so they accumulate across tests in a run. The logins this
        # module makes now exactly fill the auth_login budget (10/min per
        # IP), leaving no headroom for the next test added here or for a
        # change in suite ordering - clear the cache so each test starts on
        # a fresh window, as LoginThrottlingTests in test_throttling does.
        cache.clear()

    def test_login_returns_access_only_never_refresh_in_body(self):
        client = APIClient()
        resp = client.post('/api/auth/login/', {
            'email': self.emp_a.email, 'password': TEST_PASSWORD,
        }, format='json')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('access', resp.data)
        self.assertNotIn('refresh', resp.data)
        self.assertNotIn('tokens', str(resp.data.keys()))

    def test_refresh_cookie_is_httponly(self):
        client = APIClient()
        resp = client.post('/api/auth/login/', {
            'email': self.emp_a.email, 'password': TEST_PASSWORD,
        }, format='json')
        cookie = resp.cookies.get(settings.JWT_REFRESH_COOKIE_NAME)
        self.assertIsNotNone(cookie)
        self.assertTrue(cookie['httponly'])

    def test_access_token_authorizes_api_calls(self):
        client = APIClient()
        login = client.post('/api/auth/login/', {
            'email': self.emp_a.email, 'password': TEST_PASSWORD,
        }, format='json')
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")
        me = client.get('/api/auth/me/')
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.data['user']['email'], self.emp_a.email)

    def test_refresh_endpoint_issues_new_access_token_from_cookie_only(self):
        client = APIClient()
        login = client.post('/api/auth/login/', {
            'email': self.emp_a.email, 'password': TEST_PASSWORD,
        }, format='json')
        cookie = login.cookies.get(settings.JWT_REFRESH_COOKIE_NAME)

        # Fresh client, as if the page was reloaded: only the cookie
        # carries the session forward, nothing read from JS-visible storage.
        fresh_client = APIClient()
        fresh_client.cookies[settings.JWT_REFRESH_COOKIE_NAME] = cookie.value
        refreshed = fresh_client.post('/api/auth/refresh/')
        self.assertEqual(refreshed.status_code, 200, refreshed.content)
        self.assertIn('access', refreshed.data)
        self.assertEqual(refreshed.data['user']['email'], self.emp_a.email)

    def test_refresh_without_cookie_is_rejected(self):
        client = APIClient()
        resp = client.post('/api/auth/refresh/')
        self.assertEqual(resp.status_code, 401)

    def test_rotated_refresh_token_cannot_be_reused(self):
        client = APIClient()
        login = client.post('/api/auth/login/', {
            'email': self.emp_a.email, 'password': TEST_PASSWORD,
        }, format='json')
        old_cookie = login.cookies.get(settings.JWT_REFRESH_COOKIE_NAME)

        first_refresh_client = APIClient()
        first_refresh_client.cookies[settings.JWT_REFRESH_COOKIE_NAME] = old_cookie.value
        first = first_refresh_client.post('/api/auth/refresh/')
        self.assertEqual(first.status_code, 200)

        # The OLD refresh token was rotated away and blacklisted - reusing
        # it must fail even though it hasn't naturally expired.
        replay_client = APIClient()
        replay_client.cookies[settings.JWT_REFRESH_COOKIE_NAME] = old_cookie.value
        replay = replay_client.post('/api/auth/refresh/')
        self.assertEqual(replay.status_code, 401)

    def test_logout_blacklists_refresh_token(self):
        client = APIClient()
        login = client.post('/api/auth/login/', {
            'email': self.emp_a.email, 'password': TEST_PASSWORD,
        }, format='json')
        cookie = login.cookies.get(settings.JWT_REFRESH_COOKIE_NAME)

        logout_client = APIClient()
        logout_client.cookies[settings.JWT_REFRESH_COOKIE_NAME] = cookie.value
        logout_resp = logout_client.post('/api/auth/logout/')
        self.assertEqual(logout_resp.status_code, 200)

        reuse_client = APIClient()
        reuse_client.cookies[settings.JWT_REFRESH_COOKIE_NAME] = cookie.value
        after_logout = reuse_client.post('/api/auth/refresh/')
        self.assertEqual(after_logout.status_code, 401)

    def test_logout_succeeds_even_without_a_valid_access_token(self):
        # Logout must be able to revoke a still-valid refresh cookie even
        # when the short-lived access token has already expired/is absent -
        # requiring IsAuthenticated here would create exactly the gap this
        # test guards against.
        client = APIClient()
        login = client.post('/api/auth/login/', {
            'email': self.emp_a.email, 'password': TEST_PASSWORD,
        }, format='json')
        cookie = login.cookies.get(settings.JWT_REFRESH_COOKIE_NAME)

        anon_client = APIClient()  # no Authorization header at all
        anon_client.cookies[settings.JWT_REFRESH_COOKIE_NAME] = cookie.value
        resp = anon_client.post('/api/auth/logout/')
        self.assertEqual(resp.status_code, 200)

    def test_access_token_lifetime_is_short(self):
        # G3-16: no more 24h (1440 minute) default.
        self.assertLessEqual(
            settings.SIMPLE_JWT['ACCESS_TOKEN_LIFETIME'].total_seconds(), 30 * 60
        )

    def test_blacklist_app_installed(self):
        # G3-14: BLACKLIST_AFTER_ROTATION being True is a no-op without
        # this app - guard against that regressing silently.
        self.assertIn('rest_framework_simplejwt.token_blacklist', settings.INSTALLED_APPS)
        self.assertTrue(settings.SIMPLE_JWT.get('BLACKLIST_AFTER_ROTATION'))

    def test_refresh_is_rejected_once_the_account_is_deactivated(self):
        # SimpleJWT 5.5.1 re-checks the account behind the refresh token
        # before rotating it, closing a real gap: under 5.3.1 a user
        # deactivated mid-session kept trading their refresh cookie for new
        # access tokens for the rest of the 7-day refresh lifetime. The
        # rejection has to come back through refresh_view's own path, so the
        # dead cookie is cleared rather than left on the client.
        client = APIClient()
        login = client.post('/api/auth/login/', {
            'email': self.emp_a.email, 'password': TEST_PASSWORD,
        }, format='json')
        cookie = login.cookies.get(settings.JWT_REFRESH_COOKIE_NAME)

        self.emp_a.is_active = False
        self.emp_a.save(update_fields=['is_active'])

        deactivated_client = APIClient()
        deactivated_client.cookies[settings.JWT_REFRESH_COOKIE_NAME] = cookie.value
        resp = deactivated_client.post('/api/auth/refresh/')

        self.assertEqual(resp.status_code, 401)
        self.assertNotIn('access', resp.data)
        cleared = resp.cookies.get(settings.JWT_REFRESH_COOKIE_NAME)
        self.assertEqual(cleared.value, '')
        self.assertEqual(str(cleared['max-age']), '0')

    def test_refresh_is_rejected_once_the_account_is_deleted(self):
        # That same 5.5.1 account check looks the user up without guarding
        # for a missing row, so a deleted account raises User.DoesNotExist
        # out of the serializer. Left alone that escapes refresh_view as an
        # unhandled 500 (and this test would error, not fail); it belongs on
        # the same 401-and-clear path as any other unusable refresh cookie.
        client = APIClient()
        login = client.post('/api/auth/login/', {
            'email': self.emp_a.email, 'password': TEST_PASSWORD,
        }, format='json')
        cookie = login.cookies.get(settings.JWT_REFRESH_COOKIE_NAME)

        self.emp_a.delete()

        deleted_client = APIClient()
        deleted_client.cookies[settings.JWT_REFRESH_COOKIE_NAME] = cookie.value
        resp = deleted_client.post('/api/auth/refresh/')

        self.assertEqual(resp.status_code, 401)
        self.assertNotIn('access', resp.data)
        cleared = resp.cookies.get(settings.JWT_REFRESH_COOKIE_NAME)
        self.assertEqual(cleared.value, '')
        self.assertEqual(str(cleared['max-age']), '0')

    def test_rotation_records_the_new_refresh_token_against_its_user(self):
        # 5.5.1 adds the rotated refresh token to the outstanding list (5.3.1
        # recorded only the one minted at login) and fills in the user FK that
        # older versions left NULL - which is what makes these tables usable
        # as a per-user revocation trail rather than a bag of orphan rows.
        client = APIClient()
        login = client.post('/api/auth/login/', {
            'email': self.emp_a.email, 'password': TEST_PASSWORD,
        }, format='json')
        old_cookie = login.cookies.get(settings.JWT_REFRESH_COOKIE_NAME)
        # Read the outgoing jti before rotating: afterwards this token is
        # blacklisted and constructing it raises.
        old_jti = RefreshToken(old_cookie.value)['jti']

        refresh_client = APIClient()
        refresh_client.cookies[settings.JWT_REFRESH_COOKIE_NAME] = old_cookie.value
        rotated = refresh_client.post('/api/auth/refresh/')
        self.assertEqual(rotated.status_code, 200, rotated.content)

        new_cookie = rotated.cookies.get(settings.JWT_REFRESH_COOKIE_NAME)
        self.assertNotEqual(new_cookie.value, old_cookie.value)
        new_jti = RefreshToken(new_cookie.value)['jti']

        self.assertTrue(
            OutstandingToken.objects.filter(jti=new_jti, user=self.emp_a).exists()
        )
        # Nothing this flow writes may land in the list unattributed.
        self.assertFalse(OutstandingToken.objects.filter(user__isnull=True).exists())
        # And the token it replaced is still revoked.
        self.assertTrue(BlacklistedToken.objects.filter(token__jti=old_jti).exists())
