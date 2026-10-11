# Testing

## Backend

The backend suites live under `backend/api/tests/`, one package per kind of guarantee, and run against an isolated PostgreSQL database that the test runner creates and destroys. Counts are those of the current checkpoint.

| Label | Tests | Protects |
|---|---|---|
| `api.tests.functional` | 168 | End-to-end API behaviour per area: students, imports, inventory, requests, transfers, analysis, dashboard, reports |
| `api.tests.characterization` | 200 | Pinned behaviour of the views package (routes, decorators, facade bindings) and of the allocation run body (exact UPDATE statements, connection lifecycle); these make refactors verifiable |
| `api.tests.allocation` | 210 | Solver scenarios with expected assignments (real OR-Tools), run lifecycle, live preview, stop and cancel, retry, accessibility exclusion |
| `api.tests.assisted_allocation` | 63 | The assisted workbench: queue, recommendations, blockers, overrides, audit |
| `api.tests.security` | 88 | Role and region authorization, JWT lifecycle, throttles, lockdowns, production-safe settings |
| `api.tests.performance` | 65 | Query counts and N+1 growth on list and detail endpoints, with a generous wall-clock guard |
| `api.tests.concurrency` | 24 | Request-transition races, placement races and a load test with real concurrent connections |
| `api.tests.domains` | 177 | Domain modules directly: allocation engine boundary, durable jobs (claiming, leases, heartbeat, recovery, fencing with real OR-Tools), imports, inventory, what-if, transfers, and the synthetic student generator run through the real import path |
| `api.tests.contracts` | 86 | HTTP contracts of every frontend-consumed endpoint: status codes, response keys and order, error bodies, permissions, omitted-vs-null fields |
| default discovery | 1081 | everything above |

`backend/canada_algorithm_tests/` holds 13 controlled solver scenarios with written expected results, run on demand with `python manage.py run_allocation_case <case> --max-seconds 60`.

### Running

Start the isolated test database and create `.env.test` in the repository root from the recipe in `.env.example` (eight variables: `DEBUG=True`, `DORMIFY_LOCAL_DB_ONLY=True`, `DB_NAME=dormify_test`, `DB_USER=dormify_user`, `DB_PASSWORD=dormify_password`, `DB_HOST=localhost`, `DB_PORT=5435`, `DB_SSLMODE=disable`):

```bash
docker compose -p dormify-v3 --profile local-db up -d test_db
cd backend
ENV_FILE=.env.test python manage.py test                              # full discovery
ENV_FILE=.env.test python manage.py test api.tests.domains            # one family
ENV_FILE=.env.test python manage.py test api.tests.domains.test_allocation_jobs   # worker and fencing tests
```

PowerShell: `$env:ENV_FILE=".env.test"; python manage.py test ...`.

Run the tests on the host, not through `docker compose exec backend`: that container mounts only `backend/` and cannot see `.env.test` or `docker-compose.yml`, which some tests read. Use Python 3.11 with the pinned dependencies (`pip install -r requirements.txt -c constraints.txt`); when the host interpreter differs, a `python:3.11-slim` container with the repository mounted and `DB_HOST=test_db` on the Compose network is equivalent to CI.

`ALLOCATION_NUM_SEARCH_WORKERS=1` keeps solver results reproducible. The performance and concurrency suites assert on wall-clock ratios; run them with the host otherwise idle, and treat a failure that disappears on an idle host as contention, not as a product regression.

The concurrency and performance suites can write human-readable evidence files, but only when `DORMIFY_CONCURRENCY_EVIDENCE_DIR` or `DORMIFY_PERF_EVIDENCE_DIR` is set to a directory outside the repository; CI leaves both unset.

### Static checks and audits

```bash
cd backend && pip install -r requirements-dev.txt
ruff check .                                           # correctness-only rule set, backend/ruff.toml
python manage.py check
python manage.py makemigrations --check --dry-run
cd .. && pre-commit run --all-files                    # ruff, YAML, frontend lint and typecheck, whitespace
python scripts/ci/dependency_audit.py python --fail-on any    # pip-audit over backend/constraints.txt, as the CI gate runs it
python scripts/ci/dependency_audit.py npm --fail-on high      # npm audit over frontend/package-lock.json, as the CI gate runs it
bash scripts/ci/run_allocation_suite.sh                       # allocation suite exactly as CI runs it
```

Without `--fail-on` the dependency audits only report (the mode the weekly scheduled run uses); with it they exit non-zero on findings at or above the given severity, which is what the push and pull-request gate does.

## Frontend

```bash
cd frontend
npm ci
npm run typecheck      # tsc -p tsconfig.json
npm run lint           # eslint src --max-warnings 0
npm test               # vitest run: 33 files, 321 tests
npm run build          # lint + vite build
```

Tests render pages through `src/shared/test/render.tsx` (real auth provider and router, mocked Axios adapter) and pin adapter requests and contract types. Transient states are asserted by holding the mocked request open with `src/shared/test/deferred.ts` and resolving it explicitly, never by timing, so the suite is deterministic under parallel workers and host load.

## Manual verification of the synthetic-data workflow

The automated suites above are the regression gate. In addition, a manual walkthrough of the end-user workflow was completed on the v3 tree (October 2026) from a fresh private clone against an isolated, blank PostgreSQL database, using only the synthetic data the repository can generate. It verified:

- all migrations through `api.0020` on a blank database, then `seed.py` on the empty schema: 6 regions, 7 dormitory types, 7 buildings, 56 apartments, 105 rooms, 207 beds and 5 synthetic staff accounts;
- the generated 120-student workbook imported as the main population file: 120 created, 0 skipped;
- the central-administrator dashboard, and the student list and detail pages;
- regional isolation: the Canada regional manager saw the 50 students of that region, not all 120;
- a complete Canada allocation through the worker: 50 regional students, 47 sent to the solver (3 excluded before the solve), 35 assigned, 12 unassigned, 39 beds remaining;
- the allocation results tree, the assisted-allocation workflow and the recommendations for an accessibility case.

The product-preview screenshots in `docs/images/` were taken during this run. It covered the allocation cycle described above, not every page or action of the product; transfers, what-if planning, reports, staff management and the inventory editor remain covered by the automated suites only.

## Continuous integration

`.github/workflows/ci.yml` runs on pushes and pull requests to `main` and `refactor/**`:

| Job | Runs |
|---|---|
| static-checks | `ruff check .`, `manage.py check`, `makemigrations --check --dry-run` |
| backend-tests | functional + characterization, security, assisted_allocation, domains + contracts, against a PostgreSQL 16 service, then asserts the checkout is clean |
| allocation-regression | the complete allocation suite through `scripts/ci/run_allocation_suite.sh`: every discovered test must run and pass, any failure or error fails the job, and the full log is uploaded as an artifact |
| performance-tests | `api.tests.performance` |
| frontend-build | `npm ci`, typecheck, tests, production build |

`scheduled-backend-validation.yml` runs the performance and concurrency suites weekly and on demand. `dependency-audit.yml` runs both dependency audits on every push, pull request and weekly. On pushes and pull requests it is a blocking gate: any Python finding (`--fail-on any`) or any npm finding of high or critical severity (`--fail-on high`) fails the job. The weekly scheduled run and manual dispatches are advisory, so an advisory published without a code change is reported rather than turning the default branch red; in every mode a scanner that cannot run fails the job. Dependabot opens grouped weekly update pull requests, which run the blocking gate.
