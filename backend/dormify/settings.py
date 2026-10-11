"""
DORMIFY - Django Settings
"""

import os
from pathlib import Path
from datetime import timedelta
from dotenv import load_dotenv
from corsheaders.defaults import default_headers
from django.core.exceptions import ImproperlyConfigured

from dormify.db_safety import check_database_host, local_db_only_enabled

# Build paths
BASE_DIR = Path(__file__).resolve().parent.parent

# Load environment variables.
# Default: .env
# For tests: run with ENV_FILE=.env.test.
# `.env.test` is intentionally local/untracked and should be created
# according to the test-environment instructions in the repository README,
# including DEBUG=True for the isolated local test environment.
ENV_FILE = os.getenv("ENV_FILE", ".env")
load_dotenv(BASE_DIR.parent / ENV_FILE)

# Security
#
# Default to production-safe behavior unless development mode is enabled
# explicitly: a deployment that never sets DEBUG runs with hardening on.
# Every hardening rule below is gated on this same value.
#
# Local development must therefore set DEBUG=True explicitly:
#   - the `backend` service in docker-compose.yml sets it directly. That
#     container mounts only ./backend, not the repository root, so the
#     load_dotenv() call above finds no .env file inside it.
#   - a backend started directly on the host reads it from ENV_FILE
#     (.env / .env.test) through load_dotenv() above.
#
# A production deployment needs DEBUG unset (or False) and a real
# SECRET_KEY supplied through the environment.
DEBUG = os.getenv("DEBUG", "False") == "True"

# No insecure hardcoded fallback once DEBUG is off. A DEBUG=True
# (development) run may still fall back to a fixed placeholder key purely
# for local convenience - it never leaves this process and there is nothing
# session-worthy to protect on a throwaway dev database. Once DEBUG=False,
# the app refuses to start without an operator-supplied SECRET_KEY rather
# than silently running on a public, guessable one.
SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    if DEBUG:
        SECRET_KEY = "django-insecure-local-dev-only-do-not-use-in-production"
    else:
        raise ImproperlyConfigured(
            "SECRET_KEY environment variable must be set when DEBUG is not "
            "enabled. Refusing to start with no secret key configured."
        )

ALLOWED_HOSTS = [
    h.strip() for h in os.getenv(
        "DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1"
    ).split(",") if h.strip()
]

# Application definition
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",

    # Third party
    "rest_framework",
    "rest_framework_simplejwt",
    # Required for server-side refresh-token revocation. Without this app
    # installed, BLACKLIST_AFTER_ROTATION below has no effect.
    "rest_framework_simplejwt.token_blacklist",
    "corsheaders",

    # Local apps
    "api",
    "accounts.apps.AccountsConfig",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",  # Must be first!
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "dormify.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "dormify.wsgi.application"

DB_SSLMODE = os.getenv("DB_SSLMODE", "require")

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.getenv("DB_NAME"),
        "USER": os.getenv("DB_USER"),
        "PASSWORD": os.getenv("DB_PASSWORD"),
        "HOST": os.getenv("DB_HOST"),
        "PORT": os.getenv("DB_PORT", "5432"),
        "OPTIONS": {
            "connect_timeout": 30,
        },
        "CONN_MAX_AGE": 0,
    }
}

if DB_SSLMODE:
    DATABASES["default"]["OPTIONS"]["sslmode"] = DB_SSLMODE

# ===========================================
# Local-database-only safety guard
# ===========================================
# Fails fast when local-only database mode is enabled and DB_HOST is not a
# recognised local host, so development and test runs cannot reach a
# remote database by accident.
#
# The deciding boundary is DORMIFY_LOCAL_DB_ONLY, not DEBUG. DEBUG
# controls error reporting; deriving database safety from it would mean
# the protection disappears whenever DEBUG is changed for an unrelated
# reason, and would leave a misconfigured DEBUG=False run unprotected. The
# guarantee holds either way:
#
#     local-only mode enabled + remote DB host = startup blocked
#
# Local-only mode is ON unless explicitly and recognisably disabled, so a
# missing or misspelled value fails closed. A deployment that uses a
# managed database sets DORMIFY_LOCAL_DB_ONLY=False deliberately. The rule
# itself lives in dormify/db_safety.py (standard library only, no Django
# imports) and is documented there, including why configuration alone
# cannot provide this guarantee.
LOCAL_DB_ONLY = local_db_only_enabled(os.getenv("DORMIFY_LOCAL_DB_ONLY"))

_db_config_error = check_database_host(
    host=DATABASES["default"]["HOST"],
    name=DATABASES["default"]["NAME"],
    local_db_only=LOCAL_DB_ONLY,
)
if _db_config_error:
    raise ImproperlyConfigured(_db_config_error)

# ===========================================
# Durable allocation worker
# ===========================================
# Background allocation runs are executed by a dedicated worker process
# (python manage.py allocation_worker) that claims QUEUED AllocationRun rows
# from PostgreSQL. The lease is renewed by the worker's heartbeat while a run
# executes; a run whose lease has expired belongs to a worker that is gone
# and is recovered by any live worker (see api.domains.allocation.jobs).
ALLOCATION_WORKER_POLL_INTERVAL_SECONDS = float(
    os.getenv("ALLOCATION_WORKER_POLL_INTERVAL_SECONDS", "2")
)
ALLOCATION_WORKER_LEASE_SECONDS = int(os.getenv("ALLOCATION_WORKER_LEASE_SECONDS", "300"))
ALLOCATION_WORKER_HEARTBEAT_SECONDS = float(
    os.getenv("ALLOCATION_WORKER_HEARTBEAT_SECONDS", "30")
)
ALLOCATION_WORKER_MAX_ATTEMPTS = int(os.getenv("ALLOCATION_WORKER_MAX_ATTEMPTS", "3"))

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# Custom User Model
AUTH_USER_MODEL = "api.User"

# Internationalization
LANGUAGE_CODE = "he"
TIME_ZONE = "Asia/Jerusalem"
USE_I18N = True
USE_TZ = True

# Static files
STATIC_URL = "static/"

# Default primary key
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ===========================================
# REST Framework Configuration
# ===========================================
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    # Rates for the fixed-scope throttle classes in api/throttling.py.
    # DEFAULT_THROTTLE_CLASSES is intentionally not set globally:
    # throttling is applied per view, only on security-sensitive
    # endpoints, so ordinary authenticated API traffic (allocation
    # polling, list views, and similar) is never throttled.
    "DEFAULT_THROTTLE_RATES": {
        "auth_login": os.getenv("THROTTLE_AUTH_LOGIN", "10/min"),
        "auth_sensitive": os.getenv("THROTTLE_AUTH_SENSITIVE", "10/min"),
        "staff_create": os.getenv("THROTTLE_STAFF_CREATE", "20/min"),
        "auth_refresh": os.getenv("THROTTLE_AUTH_REFRESH", "30/min"),
        "auth_logout": os.getenv("THROTTLE_AUTH_LOGOUT", "30/min"),
    },
}

# ===========================================
# JWT Configuration
# ===========================================
SIMPLE_JWT = {
    # Access tokens are deliberately short-lived. Clients stay signed in
    # through the refresh-cookie flow instead (see api/views/auth.py
    # refresh_view and the JWT_REFRESH_COOKIE_* settings below).
    "ACCESS_TOKEN_LIFETIME": timedelta(
        minutes=int(os.getenv("JWT_ACCESS_TOKEN_LIFETIME", 20))
    ),
    "REFRESH_TOKEN_LIFETIME": timedelta(
        minutes=int(os.getenv("JWT_REFRESH_TOKEN_LIFETIME", 10080))
    ),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "AUTH_HEADER_TYPES": ("Bearer",),
}

# ===========================================
# Refresh-token cookie
# ===========================================
# The refresh token is never sent to frontend JS: /api/auth/login/ and
# /api/auth/refresh/ set it as an HttpOnly cookie, and only the backend
# auth endpoints (refresh/logout) ever read it. The access token stays a
# normal Bearer token in the Authorization header, kept in frontend memory
# only - see src/services/api.js. Path is scoped to /api/auth/ so the
# browser doesn't attach this cookie to every unrelated API request.
JWT_REFRESH_COOKIE_NAME = os.getenv("JWT_REFRESH_COOKIE_NAME", "dormify_refresh")
JWT_REFRESH_COOKIE_PATH = os.getenv("JWT_REFRESH_COOKIE_PATH", "/api/auth/")
JWT_REFRESH_COOKIE_SAMESITE = os.getenv("JWT_REFRESH_COOKIE_SAMESITE", "Lax")
# Never Secure on local plain-HTTP dev (the browser would silently refuse to
# ever send it); Secure by default once DEBUG=False, still overridable.
JWT_REFRESH_COOKIE_SECURE = os.getenv(
    "JWT_REFRESH_COOKIE_SECURE", "False" if DEBUG else "True"
) == "True"
JWT_REFRESH_COOKIE_DOMAIN = os.getenv("JWT_REFRESH_COOKIE_DOMAIN") or None

CORS_ALLOWED_ORIGINS = os.getenv(
    "CORS_ALLOWED_ORIGINS",
    "http://localhost:3000,http://127.0.0.1:3000",
).split(",")

CORS_ALLOW_HEADERS = list(default_headers) + [
    "authorization",
]

# Required for the browser to send/accept the HttpOnly refresh cookie
# cross-origin (frontend :3000 -> backend :8000) - already relied on the
# explicit CORS_ALLOWED_ORIGINS list above (never "*", which is invalid
# together with credentials anyway).
CORS_ALLOW_CREDENTIALS = True

# ===========================================
# Production hardening
# ===========================================
# Inert while DEBUG=True, so local development over plain HTTP is never
# redirected or otherwise broken (SECURE_SSL_REDIRECT=True on plain HTTP
# would just be a permanent redirect loop). A deployment that sets
# DEBUG=False gets all of this automatically. SECURE_PROXY_SSL_HEADER is
# only enabled when DJANGO_BEHIND_HTTPS_PROXY explicitly says the
# deployment sits behind a proxy that terminates TLS and sets that header -
# never turned on by guesswork, since trusting it incorrectly lets a client
# spoof "https" and defeat SECURE_SSL_REDIRECT.
if not DEBUG:
    SECURE_SSL_REDIRECT = os.getenv("SECURE_SSL_REDIRECT", "True") == "True"
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = int(os.getenv("SECURE_HSTS_SECONDS", 31536000))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = os.getenv("SECURE_HSTS_INCLUDE_SUBDOMAINS", "True") == "True"
    SECURE_HSTS_PRELOAD = os.getenv("SECURE_HSTS_PRELOAD", "True") == "True"
    if os.getenv("DJANGO_BEHIND_HTTPS_PROXY", "False") == "True":
        SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
else:
    SECURE_SSL_REDIRECT = False
    SESSION_COOKIE_SECURE = False
    CSRF_COOKIE_SECURE = False