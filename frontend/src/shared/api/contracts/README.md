# API contracts

Hand-maintained TypeScript descriptions of the JSON the Dormify backend
serializes. They are **wire types, not ORM types**: the field list, the field
names and the nullability come from `backend/api/serializers/*.py` and from the
explicit `Response({...})` dicts in `backend/api/views/*.py`. There is no
OpenAPI schema and no generator; when a serializer changes, the matching type
changes with it in the same change.

## What lives here

Shapes that more than one feature reads:

| File | Source of truth |
|---|---|
| `common.ts` | DRF pagination envelope, id/date aliases, bilingual text, action envelopes |
| `errors.ts` | Error body shapes, one per backend origin (`detail`, `error`/`errorEn`, the `success: false` failure envelope, field errors, structured rule violations, the login wrapper) |
| `operations.ts` | `AllocationRunSerializer`, `RegionInboxSerializer`, `ImportBatchSerializer` (with the region breakdown and the deletion record) |
| `organization.ts` | `RegionSerializer`, `DormTypeSerializer` |
| `inventory.ts` | `BuildingSerializer`, `ApartmentSerializer`, `RoomSerializer`, `BedSerializer` |
| `students.ts` | `StudentListSerializer` (summary), `StudentSerializer` (detail) |
| `auth.ts` | `UserSerializer`, the login/refresh/me response bodies, the restored session |

## What stays feature-owned

Payloads only one feature reads live next to that feature's adapter in
`src/features/<feature>/types.ts` (allocation runs and results, the assisted
allocation workbench, import batches, student requests and transfers, what-if
scenarios, reports, dashboard, analytics). They import the shared types above
rather than redeclaring them.

## Errors at runtime

`shared/api/client.ts` flattens any error body into the one message adapters
throw today. `shared/api/errors.ts` (`normalizeApiError`) adds typed access
next to that message: the HTTP status, the backend's bare sentence
(`serverMessage`), its English twin (`messageEn`), the error code, the
conflicting status of a 409, the field-keyed validation dict and the
structured inventory violation. The message text is unchanged, so a screen can
adopt the normalizer without changing what the user reads.

## Row shapes

Rows the pages read from view builders (allocation results, run assignments,
live snapshots, the assisted queue, the match tree, dashboard sections,
analysis aggregates) are declared as `type` aliases, not interfaces: an
object-literal type keeps an implicit index signature, so a typed row still
satisfies the `Record<string, unknown>` parameters of the defensive page
helpers. `contracts.test.ts` pins the field types that matter against the
backend contract tests in `backend/api/tests/contracts/`.

## Conventions

- Field names are the backend's snake_case names, verbatim.
- `*_display` fields are the backend's fixed Hebrew labels; the UI localizes
  from the raw value instead (see `shared/lib/genderLabels.ts`).
- Lists are typed `ListResponse<T>` where a view may answer either paginated
  or as a plain array; `shared/api/normalize.ts` turns either into `T[]`.
- Payloads whose full shape is not modelled yet carry the keys the frontend
  reads plus an index signature, so new fields can be read without a type
  change but known fields stay checked.
- Do not add runtime code here: contracts are `type`/`interface` only.
