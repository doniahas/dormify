# Security, roles and regional isolation

What the backend enforces and how. Everything here is covered by `backend/api/tests/security/` (88 tests) and the contract suite; claims beyond those tests are not made. Implementation: `backend/api/permissions.py`, `backend/api/views/auth.py`, `backend/accounts/`, `backend/dormify/settings.py`.

## Roles

| Role | Scope | Typical actions |
|---|---|---|
| `central_admin` | all regions | imports, staff management for every region, system-wide reports, inventory structure (regions, dorm types), any region's data by explicit selection |
| `region_boss` | one region | start, stop and delete allocation runs, review and decide transfer requests, assisted-allocation assignments and overrides, manage the region's staff |
| `employee` | one region | operate the region's students, inventory and requests within the limits above |

A single `region_boss` per region is enforced by a database constraint. Roles are fixed at account creation by a central or regional manager (`POST /api/staff-users/`); there is no public registration endpoint.

## Regional data isolation

Region scope is derived from the authenticated user, not from the request:

- a `region_boss` or `employee` sees only rows of their own region in every list, detail and action; a `?region=` parameter naming another region returns 403 rather than silently substituting their own region, so a response can never be mistaken for data about a different region;
- a `central_admin` may select any region explicitly or omit it to work system-wide, where the endpoint supports that;
- object-level checks repeat the test on writes: approving a request, assigning a bed, deleting run results or stopping a run all re-check the target's region against the user under the row lock that serializes the operation;
- mutable system state is only reachable through the workflows that validate it: students cannot be deleted or replaced wholesale, `Student.assigned_room` is not writable through the student API, transfer status changes go through approve/reject/cancel actions only, and bed records expose only their label to edits.

## Authentication

- `POST /api/auth/login/` returns a short-lived JWT access token (20 minutes by default) in the response body and sets the refresh token as an HttpOnly cookie scoped to `/api/auth/` (`SameSite=Lax`; `Secure` once `DEBUG=False`).
- The frontend keeps the access token in memory only and sends it as `Authorization: Bearer ...`; it never sees the refresh token.
- `POST /api/auth/refresh/` rotates the refresh token (old tokens are blacklisted) and returns a new access token; `POST /api/auth/logout/` blacklists the refresh token and clears the cookie.
- Login, refresh, logout, password/email change and staff creation are rate-limited (`THROTTLE_*` settings); ordinary API traffic is not throttled.
- Changing the account email requires the current password.

## Configuration hardening

- `DEBUG` defaults to `False`. With `DEBUG=False` the application refuses to start without a real `SECRET_KEY`, redirects to HTTPS, sends HSTS, and marks session, CSRF and refresh cookies `Secure`. `SECURE_PROXY_SSL_HEADER` is enabled only when `DJANGO_BEHIND_HTTPS_PROXY=True` is set deliberately.
- The local-database-only guard (`DORMIFY_LOCAL_DB_ONLY`, fail-closed) stops development and test processes from reaching a non-local database by accident.
- CORS is an explicit origin allowlist with credentials; it is never `*`.
- Uploaded files are validated (type, size via `MAX_UPLOAD_FILE_SIZE_MB`) before any parsing; parser stack traces stay server-side.
- `seed.py` contains no fixed passwords and refuses to run unless `DEBUG=True`.

## What is not covered

- Audit logging exists for assisted-allocation overrides (`AssistedAllocationAudit`); other write paths rely on database state and request history, not a general audit trail.
- Dependency vulnerabilities are reported by the audit workflow but do not yet block CI (advisory mode; see [TESTING.md](TESTING.md)).
- Transport security, secret storage and backups are deployment concerns outside this repository.
