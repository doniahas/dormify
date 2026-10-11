# API reference

JSON REST API under `/api/`. The authoritative route list is `backend/api/urls.py` (plus `backend/accounts/urls.py`); the exact request acceptance rules, response keys and error bodies are pinned by `backend/api/tests/contracts/` and mirrored in the frontend's hand-written contracts under `frontend/src/shared/api/contracts/`. There is no OpenAPI schema.

## Conventions

- **Authentication**: every endpoint except login, refresh and logout requires `Authorization: Bearer <access token>`. The refresh token travels only in an HttpOnly cookie scoped to `/api/auth/`.
- **Region scope**: regional users are confined to their region on every endpoint; `?region=` is honoured only for central administrators (see [SECURITY.md](SECURITY.md)).
- **Errors**: hand-written error bodies come in two families, `{"error": "...", "errorEn"?: "..."}` for most views and `{"success": false, "error": "...", ...}` for the allocation and import workflows; DRF validation errors are field-keyed dictionaries; serializer errors on login arrive as `{"error": {...}, "errorHe": "..."}`. Status codes: 400 validation, 401 unauthenticated, 403 forbidden (including cross-region access), 404 unknown object, 409 state conflicts (an allocation already running, a request already decided, an approved run), 429 throttled, 500 unexpected failures (stack traces stay server-side).
- **Lists**: viewset list endpoints are paginated (`count`, `next`, `previous`, `results`) where `StandardResultsPagination` applies (students, requests); other lists return arrays. Messages are Hebrew with English twins where the UI needs them; `*_display` fields carry fixed Hebrew labels.

Legend for the "Status" column: **UI** = consumed by the current frontend; **Ops** = reachable, used operationally or by tests but not by the UI; **Legacy** = kept for compatibility, not routed or not consumed.

## Authentication and account

| Method | Route | Role | Purpose | Status |
|---|---|---|---|---|
| POST | `/api/auth/login/` | anyone (throttled) | `{email, password}` -> `{message, messageEn, user, access}` + refresh cookie | UI |
| POST | `/api/auth/refresh/` | cookie (throttled) | rotate the refresh cookie, return a new `access` | UI |
| POST | `/api/auth/logout/` | cookie (throttled) | blacklist the refresh token, clear the cookie | UI |
| GET | `/api/auth/me/` | any user | the current user (`UserSerializer`) | UI |
| PUT/POST | `/api/auth/change-password/` | any user (throttled) | `{current_password, new_password}` | UI |
| PUT/POST | `/api/auth/change-email/` | any user (throttled) | `{current_password, new_email}` | UI |

## Staff accounts

| Method | Route | Role | Purpose | Status |
|---|---|---|---|---|
| GET | `/api/staff-users/` | central or regional manager | list staff (regional managers see their region) | UI |
| POST | `/api/staff-users/` | central or regional manager (throttled) | create a staff account with role and region; the only account-creation path | UI |

## Students

`StudentViewSet` at `/api/students/`: `GET` list (paginated, filters and search), `POST` create, `GET /{id}/`, `PATCH /{id}/`. No `PUT` and no `DELETE` by design. Actions: `GET /api/students/counts/` (totals per category for the current scope) and `GET /api/students/filter-options/` (filter vocabularies). Writes to `assigned_room` are rejected; assignment changes go through room actions, allocation or requests. Status: UI.

## Inventory

Viewsets: `/api/regions/` and `/api/dorm-types/` (full CRUD; writes are reserved for `central_admin`), `/api/buildings/`, `/api/apartments/`, `/api/rooms/` (`GET`, `POST`, `PATCH`; writes require a manager, that is `region_boss` within their own region or `central_admin`; an `employee` may read only), `/api/beds/` (`GET`, `PATCH` of the label only). Building actions: `GET /api/buildings/{id}/apartments/`, `GET /api/buildings/{id}/rooms/`, `POST /api/buildings/{id}/bulk-create-inventory/` (manager; creates apartments, rooms and beds for one building under a lock on the building and its apartments). All lists are region-scoped. Status: UI.

## Imports and region inbox

| Method | Route | Role | Purpose | Status |
|---|---|---|---|---|
| POST | `/api/upload/batches/init/` | `central_admin` | create a PENDING `ImportBatch` before sending the file | UI |
| POST | `/api/upload/excel/` | `central_admin` | main population file (`file`, `batch_id`); validated before parsing; processed with progress | UI |
| POST | `/api/upload/additions-excel/` | `central_admin` | additions file | UI |
| GET | `/api/upload/batches/{id}/status/` | owner | progress, totals, terminal summary | UI |
| POST | `/api/upload/batches/{id}/stop/` | owner | request a stop of a processing batch (409 if not processing) | UI |
| POST | `/api/upload/batches/{id}/stop-and-delete/` | owner | stop and remove what the batch imported | UI |
| POST | `/api/upload/batches/{id}/delete/` | owner | delete a completed batch's students (409 while processing) | UI |
| GET | `/api/batches/` | any user | batches visible to the user (all for `central_admin`, otherwise the region's) | Ops |
| GET | `/api/inbox/`, `/api/inbox/latest/` | any user | the region's inbox entries (all regions for `central_admin`) | Ops |
| PUT | `/api/inbox/{id}/viewed/` | user of that region | mark an inbox entry as viewed | UI |
| PUT | `/api/inbox/{id}/processed/` | `region_boss` of that region or `central_admin` | mark an inbox entry as processed | UI |

## Allocation runs

| Method | Route | Role | Purpose | Status |
|---|---|---|---|---|
| POST | `/api/allocation/start/` | `region_boss` or `central_admin` | `{region, constraints?, include_assigned?, allocation_scope?, max_solver_seconds?}` -> 202 `{success, message, run_id, run}`; creates a QUEUED run for the worker; 409 `ALLOCATION_ALREADY_RUNNING` while a run is live | UI |
| GET | `/api/allocation/runs/active/` | regional scope | the live run, or the latest completed run while its assignments still exist | UI |
| GET | `/api/allocation/runs/{id}/` | region of the run | run status, counters, warnings, population summary, assignment rows once COMPLETED | UI |
| GET | `/api/allocation/runs/{id}/preview/` | region of the run | `{available, snapshot}` from the persisted live snapshot | UI |
| POST | `/api/allocation/runs/{id}/stop/` | `region_boss` or `central_admin` | request cancellation (idempotent; 409 if finished or a stop-and-save is pending) | UI |
| POST | `/api/allocation/runs/{id}/stop-and-save/` | same | request stop keeping the best feasible result (idempotent; 409 if a cancellation is pending) | UI |
| DELETE | `/api/allocation/runs/{id}/delete/` | same | cancel a COMPLETED run's draft assignments (409 if approved or not completed) | UI |
| POST | `/api/allocation/runs/{id}/retry-unassigned/` | same | re-solve the original run's still-unassigned students against current inventory (400 without the original population) | UI |
| GET | `/api/allocation/results/` | regional scope | current assignments, unassigned students with reasons, available beds | UI |
| GET | `/api/allocation/summary/` | regional scope | pre-run population breakdown and inventory summary | UI |
| GET | `/api/allocation/history/` | regional scope | past runs | Ops (adapter exists, no screen uses it) |
| POST | `/api/allocation/run/` | `region_boss` or `central_admin` | legacy synchronous solve inside the request; assignments are not tagged with the run | Legacy (routed, unconsumed; retirement is an owner decision) |

Allocation runs themselves are executed by the worker ([ALLOCATION_WORKER.md](ALLOCATION_WORKER.md)); the API only enqueues, reads and signals.

## Assisted allocation

| Method | Route | Role | Purpose | Status |
|---|---|---|---|---|
| GET | `/api/assisted-allocation/queue/` | regional scope | unassigned and accessibility-pending students | UI |
| GET | `/api/assisted-allocation/students/{id}/detail/` | regional scope | the student with placement context | UI |
| GET | `/api/assisted-allocation/students/{id}/recommendations/` | regional scope | ranked candidate rooms with explanations | UI |
| GET | `/api/assisted-allocation/students/{id}/override-check/` | regional scope | whether a chosen bed is blocked, and why | UI |
| POST | `/api/assisted-allocation/students/{id}/assign/` | `region_boss` or `central_admin` | assign to a compatible bed | UI |
| POST | `/api/assisted-allocation/students/{id}/override/` | `region_boss` or `central_admin` | assign despite a non-structural blocker, with an audited reason | UI |

## Room actions

`POST /api/room-assignments/assign/`, `/move/`, `/unassign/`, `/swap/` take student and room/bed references, validate occupancy and compatibility, and update assignments transactionally. Status: UI.

## Transfer and student requests

`StudentRequestViewSet` at `/api/requests/`: `GET` list (paginated, filterable by status and type), `POST` create (room change, apartment transfer, cross-region transfer, swap, add or remove student), `GET /{id}/`. Transitions are actions only: `PUT /{id}/approve/`, `PUT /{id}/reject/`, `PUT /{id}/cancel/` (a withdrawn request is a status change, never a deletion). Helpers: `GET /api/requests/transfer-target-regions/`, `POST /api/requests/match-options/` (candidate rooms for a request), `GET /api/requests/{id}/feasibility/`. Status: UI.

`TransferViewSet` at `/api/transfers/` is the older same-region transfer model: list, create, `PUT /{id}/approve/`, `PUT /{id}/reject/`; generic `PUT`/`PATCH` on a transfer returns 405. Status: Ops (approve/reject still reachable from the UI; the request workflow above is the primary path).

## What-if

`POST /api/what-if/availability/simulate/` and `/confirm/` (buildings, apartments or rooms to deactivate; simulate returns affected students and capacity, confirm applies the change and raises transfer requests atomically). `POST /api/what-if/building-inactivation/simulate/` and `/confirm/` are the building-only predecessors. Status: UI (availability), Ops (building-inactivation).

## Dashboard, analysis and statistics

| Method | Route | Purpose | Status |
|---|---|---|---|
| GET | `/api/home/` | role-aware home page data | UI |
| GET | `/api/analysis/` | occupancy and population aggregates for the analysis page and the map | UI |
| GET | `/api/statistics/` | summary statistics | Ops |

## Reports (Excel downloads)

`GET /api/reports/dormify-report/` (`central_admin` only, system-wide), `GET /api/reports/student-allocation-report/`, `/student-actions-report/`, `/capacity-report/`, `/manual-review-report/` (regional scope; `?region=` only for central administrators). Status: UI.

## Legacy and unrouted surfaces

These exist in the code base and are pinned by characterization tests, but are not reachable or not used:

| Surface | State |
|---|---|
| `allocation_status` view | not routed; superseded by `/api/allocation/runs/active/` |
| `allocation_conditions` view and the in-memory `_CONDITIONS_STORE` | not routed; soft-preference weights are sent per run instead |
| `inventory_by_housing_type` view | not routed |
| `POST /api/allocation/run/` | routed, unconsumed synchronous solve (see above) |
| frontend adapter methods `allocationAPI.run`, `history`, `getConditions`, `updateConditions`, and the inbox/assisted aliases on `allocationAPI`, `transfersAPI`, `inventoryAPI`, `apartmentsAPI`, `roomsAPI`, `debugAuthAPI` | present, unused by any screen |

Removing any of them is a product or owner decision; none affects the behaviour of the supported paths. The map page reads `GET /api/analysis/` directly; the historical `/api/analysis-data/` and `/api/analysis_data/` probes were removed.
