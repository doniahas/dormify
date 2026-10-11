"""
Local-database-only safety guard.

Purpose
-------
Restricts the application to explicitly approved local database hosts, so
a development or test run cannot reach a remote database by accident.

Configuration alone cannot provide that guarantee, because of how
settings.py loads the environment:

    load_dotenv(BASE_DIR.parent / ENV_FILE)

python-dotenv's `override` parameter defaults to False, so a variable
that is ALREADY set in the process environment takes precedence over the
value in the .env file. A DB_HOST exported earlier in a shell session
therefore applies to every subsequent `manage.py` command in that
session, regardless of what the .env file says - silently, with no
warning. This module turns that silent condition into a startup failure.

Containerised runs are covered separately: docker-compose.yml sets the
DB_* values as literals, which cannot be overridden from outside the
container. This module covers processes started directly on the host,
which configuration cannot protect.

The safety boundary is DORMIFY_LOCAL_DB_ONLY, not DEBUG
-------------------------------------------------------
DEBUG controls error reporting. Deriving database safety from it would
mean the protection disappears whenever DEBUG is changed for an unrelated
reason, and would leave a misconfigured DEBUG=False run unprotected. The
guarantee is therefore:

    DORMIFY_LOCAL_DB_ONLY enabled  +  remote DB host  =  startup blocked

independently of DEBUG, which is not consulted anywhere in this module.

Fail-closed by design
---------------------
- Local-only mode is ON unless something explicitly and recognisably
  disables it. An unset variable, a blank value or a typo all leave the
  protection ON (see `local_db_only_enabled`). Only a deliberate, valid
  false value ("False"/"0"/"no"/"off") turns it off, which is what a
  deployment using a managed database does explicitly.
- There is deliberately no secondary bypass flag. A single explicit
  switch is auditable; an additional convenience escape hatch is how such
  guarantees erode over time.
- Host matching is an explicit allowlist rather than a heuristic. Pattern
  based rules (for example, treating any undotted name as local) wrongly
  accept names such as `prod-db` or `company-db`. Anything not listed
  below, including every non-loopback IP address, is treated as remote.
- An empty or missing DB_HOST fails in local-only mode rather than
  passing silently: an unspecified host is an unverified host, and the
  PostgreSQL client would fall back to its own default rather than to a
  host this project selected.

Design constraints
------------------
Standard library only - no Django imports, no settings access and no
database access - so this module can be imported and unit-tested in
isolation, without configuring Django or connecting to anything.
"""

import ipaddress

# The complete set of non-IP hostnames accepted as local. This is an
# allowlist, not a pattern: adding a host requires a deliberate edit here.
#
#   localhost / localhost.localdomain
#       processes started directly on the host, including the test suite.
#   db / test_db
#       the Compose service names, resolvable only inside this project's
#       Docker network (see docker-compose.yml).
#   host.docker.internal
#       Docker Desktop's alias for the host machine. It is dotted but
#       never remote - it always resolves back to the host - and it is the
#       only supported way for a container to reach a PostgreSQL instance
#       installed directly on the host.
ALLOWED_LOCAL_DB_HOSTNAMES = frozenset({
    "localhost",
    "localhost.localdomain",
    "db",
    "test_db",
    "host.docker.internal",
})

# Values that explicitly turn local-only mode OFF. Anything else - including
# an unset variable, a blank string, or a misspelling such as "flase" -
# leaves it ON.
EXPLICIT_FALSE_VALUES = frozenset({"false", "0", "no", "off"})


def local_db_only_enabled(raw_value):
    """
    Resolve the DORMIFY_LOCAL_DB_ONLY setting, failing closed.

    Returns True (protection ON) unless `raw_value` is one of the
    explicitly recognised false values. This asymmetry is deliberate: a
    typo must never silently disable the guarantee.
    """
    if raw_value is None:
        return True
    return raw_value.strip().lower() not in EXPLICIT_FALSE_VALUES


def is_local_db_host(host):
    """
    True only for hosts that are provably local.

    An IP literal is local only if it is loopback (127.0.0.0/8, ::1).
    Any other name is local only if it appears in
    ALLOWED_LOCAL_DB_HOSTNAMES. There is no undotted-name heuristic:
    `prod-db` and `company-db` are remote.
    """
    normalized = (host or "").strip().lower()

    # Accept a bracketed IPv6 literal such as "[::1]" as well as "::1".
    if normalized.startswith("[") and normalized.endswith("]"):
        normalized = normalized[1:-1]

    if not normalized:
        return False

    try:
        # Any IP literal must be loopback. This rejects LAN and public
        # addresses (10.x, 192.168.x, and anything routable) as well as
        # 0.0.0.0, which is not a valid destination anyway.
        return ipaddress.ip_address(normalized).is_loopback
    except ValueError:
        # Not an IP literal - fall through to the hostname allowlist.
        pass

    return normalized in ALLOWED_LOCAL_DB_HOSTNAMES


def check_database_host(host, name, local_db_only):
    """
    Return an error message if this database configuration must not be
    used, or None if it is acceptable.

    Returning a message rather than raising keeps this function free of
    any Django dependency; settings.py turns the message into an
    ImproperlyConfigured exception.
    """
    # Explicitly disabled: a deliberate, visible operator decision, such as
    # a deployment using a managed database. Not this guard's concern.
    if not local_db_only:
        return None

    normalized = (host or "").strip()

    if not normalized:
        return (
            "Refusing to start: DORMIFY_LOCAL_DB_ONLY is enabled but "
            "DB_HOST is empty or unset.\n"
            "In local-database-only mode the database host must be stated "
            "explicitly - an unspecified host is an unverified host, and "
            "the PostgreSQL client would fall back to its own default "
            "rather than to anything this repository chose.\n"
            "Set DB_HOST to one of:\n"
            "  - db        (v3 Docker development database, see docker-compose.yml)\n"
            "  - localhost (host-run development on port 5434, or the test "
            "database on port 5435 - see .env.example)\n"
            "Copy .env.example to .env if you have not configured this "
            "checkout yet."
        )

    if is_local_db_host(normalized):
        return None

    return (
        "Refusing to start: DORMIFY_LOCAL_DB_ONLY is enabled but DB_HOST "
        "is not a recognised LOCAL database host.\n"
        f"    DB_HOST = {host!r}\n"
        f"    DB_NAME = {name!r}\n"
        "Dormify v3 accepts only these database hosts in local-only mode:\n"
        "  - db, test_db            (v3 Compose service names)\n"
        "  - localhost              (host-run development and tests)\n"
        "  - 127.0.0.0/8, ::1       (loopback addresses)\n"
        "  - host.docker.internal   (this machine, from inside a container)\n"
        "Everything else - including bare names such as 'prod-db' and every "
        "non-loopback IP address - is treated as remote and rejected.\n"
        "\n"
        "A stale DB_HOST left over in your shell environment is the usual "
        "cause: python-dotenv does NOT override variables that are already "
        "set, so that value silently beats your .env file. Check with "
        "`echo $env:DB_HOST` (PowerShell) and clear it with "
        "`Remove-Item Env:DB_HOST`.\n"
        "\n"
        "A real deployment that genuinely must use a managed/remote "
        "database sets DORMIFY_LOCAL_DB_ONLY=False explicitly in its own "
        "environment. Never set that in a development checkout - it "
        "disables this protection entirely."
    )
