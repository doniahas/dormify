from django.conf import settings as django_settings
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.exceptions import AuthenticationFailed as DRFAuthenticationFailed
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from rest_framework_simplejwt.settings import api_settings
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken

from ..models import User
from ..serializers import LoginSerializer, UserSerializer
from ..throttling import (
    LoginRateThrottle, LogoutRateThrottle, SensitiveAccountActionRateThrottle,
    TokenRefreshRateThrottle,
)
from ..contracts.errors import error_response, failure_response

def _set_refresh_cookie(response, refresh_token_str):
    """
    G3-14/G3-16/G3-17: the refresh token lives ONLY in an HttpOnly cookie -
    it is never present in a JSON response body, so frontend JS can never
    read or persist it (closing G3-17's localStorage exposure for the
    refresh token specifically). Secure/SameSite/Path/Domain all come from
    dormify.settings (see the JWT_REFRESH_COOKIE_* block there for the
    DEBUG-gated rationale).
    """
    response.set_cookie(
        django_settings.JWT_REFRESH_COOKIE_NAME,
        refresh_token_str,
        max_age=int(api_settings.REFRESH_TOKEN_LIFETIME.total_seconds()),
        httponly=True,
        secure=django_settings.JWT_REFRESH_COOKIE_SECURE,
        samesite=django_settings.JWT_REFRESH_COOKIE_SAMESITE,
        path=django_settings.JWT_REFRESH_COOKIE_PATH,
        domain=django_settings.JWT_REFRESH_COOKIE_DOMAIN,
    )


def _clear_refresh_cookie(response):
    response.delete_cookie(
        django_settings.JWT_REFRESH_COOKIE_NAME,
        path=django_settings.JWT_REFRESH_COOKIE_PATH,
        domain=django_settings.JWT_REFRESH_COOKIE_DOMAIN,
        samesite=django_settings.JWT_REFRESH_COOKIE_SAMESITE,
    )


@api_view(['POST'])
@permission_classes([AllowAny])
@throttle_classes([LoginRateThrottle])
def login_view(request):
    serializer = LoginSerializer(data=request.data)

    if serializer.is_valid():
        user = serializer.validated_data['user']
        refresh = RefreshToken.for_user(user)

        response = Response({
            'message': 'התחברות בוצעה בהצלחה',
            'messageEn': 'Login successful',
            'user': UserSerializer(user).data,
            # Access token only - the refresh token goes out as an
            # HttpOnly cookie below, never in the body (G3-17).
            'access': str(refresh.access_token),
        })
        _set_refresh_cookie(response, str(refresh))
        return response

    return error_response(status.HTTP_401_UNAUTHORIZED, serializer.errors, errorHe='אימייל או סיסמה שגויים')


@api_view(['POST'])
@permission_classes([AllowAny])
@throttle_classes([TokenRefreshRateThrottle])
def refresh_view(request):
    """
    G3-14/G3-16: reads the refresh token from the HttpOnly cookie (never
    from the request body - frontend JS never has access to the raw
    token), rotates it via SimpleJWT's own TokenRefreshSerializer (which
    respects ROTATE_REFRESH_TOKENS/BLACKLIST_AFTER_ROTATION - the old
    refresh token is blacklisted the moment a new one is issued), and
    returns a fresh short-lived access token. Also returns the caller's
    profile so the frontend can restore a full session (access token +
    user) from this single call on page reload, without a second request
    to /api/auth/me/.
    """
    raw_refresh = request.COOKIES.get(django_settings.JWT_REFRESH_COOKIE_NAME)
    if not raw_refresh:
        return error_response(status.HTTP_401_UNAUTHORIZED, 'לא נמצא טוקן רענון')

    serializer = TokenRefreshSerializer(data={'refresh': raw_refresh})
    try:
        serializer.is_valid(raise_exception=True)
    # SimpleJWT 5.5.1 re-checks the account behind the token before rotating
    # it, which adds two failure modes that are not TokenError: DRF's
    # AuthenticationFailed for a deactivated user, and an unguarded user
    # lookup that surfaces a deleted account as User.DoesNotExist. Both mean
    # what an expired or malformed token means here - this cookie can no
    # longer buy a session - so both take the same 401-and-clear path, rather
    # than escaping as an unhandled 500 (deletion) or returning DRF's own 401
    # body without clearing the dead cookie (deactivation).
    except (TokenError, DRFValidationError, DRFAuthenticationFailed, User.DoesNotExist):
        response = error_response(status.HTTP_401_UNAUTHORIZED, 'טוקן רענון לא תקין או פג תוקף')
        _clear_refresh_cookie(response)
        return response

    data = serializer.validated_data
    new_access = data['access']

    try:
        user_id = AccessToken(new_access)['user_id']
        user = User.objects.get(pk=user_id)
        user_data = UserSerializer(user).data
    except (TokenError, User.DoesNotExist):
        user_data = None

    response = Response({'access': new_access, 'user': user_data})

    new_refresh = data.get('refresh')
    if new_refresh:
        _set_refresh_cookie(response, new_refresh)

    return response


@api_view(['POST'])
@permission_classes([AllowAny])
@throttle_classes([LogoutRateThrottle])
def logout_view(request):
    """
    G3-14: actually revokes the refresh token server-side (blacklists it,
    now that rest_framework_simplejwt.token_blacklist is installed) instead
    of only clearing client-side storage. Deliberately AllowAny rather than
    IsAuthenticated: the whole point is to be able to kill a long-lived
    refresh cookie even if the short-lived access token has already
    expired - requiring a currently-valid access token to log out would
    leave exactly that case unable to revoke anything. A missing/already-
    invalid refresh cookie still returns success; logout is idempotent.
    """
    raw_refresh = request.COOKIES.get(django_settings.JWT_REFRESH_COOKIE_NAME)
    if raw_refresh:
        try:
            RefreshToken(raw_refresh).blacklist()
        except TokenError:
            pass

    response = Response({'success': True, 'message': 'התנתקת בהצלחה'})
    _clear_refresh_cookie(response)
    return response


# G3-01: unrestricted public staff self-registration removed. Dormify is an
# internal staff-management system - the only authorized way to create a
# staff account is the role/region-validated accounts.views.
# StaffUserListCreateView (/api/staff-users/), which enforces business rules
# 2-4 (central admin manages anyone, a regional manager may only create
# employees in their own region, an employee cannot create staff at all).
# No frontend code called /auth/register/ (verified: no "register" reference
# anywhere under src/), so removing it is safe. The route below intentionally
# does not exist any more; see tests in api/tests/security/test_registration.py.


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def me_view(request):
    return Response({
        'user': UserSerializer(request.user).data
    })

@api_view(['PUT', 'POST'])
@permission_classes([IsAuthenticated])
@throttle_classes([SensitiveAccountActionRateThrottle])
def change_password_view(request):
    user = request.user

    current_password = request.data.get('current_password')
    new_password = request.data.get('new_password')
    confirm_password = request.data.get('confirm_password')

    if not current_password or not new_password or not confirm_password:
        return failure_response(status.HTTP_400_BAD_REQUEST, 'יש למלא את כל השדות')

    if not user.check_password(current_password):
        return failure_response(status.HTTP_400_BAD_REQUEST, 'הסיסמה הנוכחית אינה נכונה')

    if new_password != confirm_password:
        return failure_response(status.HTTP_400_BAD_REQUEST, 'הסיסמאות החדשות אינן תואמות')

    if len(new_password) < 8:
        return failure_response(status.HTTP_400_BAD_REQUEST, 'הסיסמה החדשה חייבת להכיל לפחות 8 תווים')

    user.set_password(new_password)
    user.save()

    return Response({
        'success': True,
        'message': 'הסיסמה עודכנה בהצלחה'
    }, status=status.HTTP_200_OK)

@api_view(['PUT', 'POST'])
@permission_classes([IsAuthenticated])
@throttle_classes([SensitiveAccountActionRateThrottle])
def change_email_view(request):
    user = request.user

    current_email = request.data.get('current_email')
    new_email = request.data.get('new_email')
    confirm_email = request.data.get('confirm_email')
    # G3-18: email is not a secret - matching it alone (as this endpoint
    # used to require) proves nothing an attacker with a hijacked session
    # doesn't already know. Reuses the exact same check_password() call
    # change_password_view already uses above, so changing account email
    # requires the same proof of identity changing the password does.
    password = request.data.get('password')

    if not current_email or not new_email or not confirm_email or not password:
        return failure_response(status.HTTP_400_BAD_REQUEST, 'יש למלא את כל השדות')

    if not user.check_password(password):
        return failure_response(status.HTTP_400_BAD_REQUEST, 'הסיסמה שגויה')

    if not user.email or user.email.lower() != current_email.lower():
        return failure_response(status.HTTP_400_BAD_REQUEST, 'האימייל הנוכחי אינו תואם לחשבון')

    if new_email.lower() != confirm_email.lower():
        return failure_response(status.HTTP_400_BAD_REQUEST, 'כתובות האימייל אינן תואמות')

    try:
        validate_email(new_email)
    except ValidationError:
        return failure_response(status.HTTP_400_BAD_REQUEST, 'כתובת האימייל החדשה אינה תקינה')

    if User.objects.filter(email__iexact=new_email).exclude(id=user.id).exists():
        return failure_response(status.HTTP_400_BAD_REQUEST, 'כתובת האימייל כבר קיימת במערכת')

    user.email = new_email

    # אצלכם לפי הנתונים שראינו קודם, username הוא בדרך כלל האימייל.
    # לכן נעדכן גם אותו כדי שהתחברות עם האימייל החדש תמשיך לעבוד.
    if hasattr(user, 'username'):
        user.username = new_email

    user.save()

    return Response({
        'success': True,
        'message': 'האימייל עודכן בהצלחה',
        'user': UserSerializer(user).data
    }, status=status.HTTP_200_OK)
