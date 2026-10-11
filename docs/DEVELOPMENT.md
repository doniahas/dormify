# Development guide

How to run Dormify on a workstation, what each environment variable does, and how the pieces find each other. The source of truth for every value here is `docker-compose.yml`, `.env.example` and `backend/dormify/settings.py`.

## Ports and services

| Service | Where | Port | Notes |
|---|---|---|---|
| PostgreSQL (development) | Compose `db` | `127.0.0.1:5434` | database `dormify_v3_dev`; data in the named volume `dormify-v3-dev-pgdata` |
| PostgreSQL (tests) | Compose `test_db` (profile `local-db`) | `127.0.0.1:5435` | database `dormify_test`; disposable; started only on demand |
| Django API | Compose `backend` | `http://localhost:8001` | container port 8000; development server |
| Django API | host `manage.py runserver` | `http://localhost:8000` | |
| Allocation worker | Compose `allocation_worker` or host `manage.py allocation_worker` | none | same image and configuration as the API |
| Frontend | Compose `frontend` or host `npm start` | `http://localhost:3001` | Vite dev server; fails if the port is taken |

Compose containers receive their configuration as literal values in `docker-compose.yml` (shared between `backend` and `allocation_worker` through one YAML anchor); they do not read `.env`. Host processes read the repository-root `.env`.

## Environment files

`.env.example` is the only committed template and documents every variable. Copy it to `.env` (git-ignored) for host-side work:

```bash
cp .env.example .env
```

Essentials:

| Variable | Purpose |
|---|---|
| `DEBUG` | `True` for development. Defaults to `False` when absent; with `DEBUG=False` the application refuses to start without a real `SECRET_KEY` and enables HTTPS redirect, HSTS and secure cookies. |
| `SECRET_KEY` | Django secret. The template value is a placeholder for local use only. |
| `DORMIFY_LOCAL_DB_ONLY` | Fail-closed guard: when enabled (the default when unset, blank or unrecognised), Django refuses any `DB_HOST` that is not an explicitly recognised local host (`localhost`, `db`, `test_db`, `host.docker.internal`, loopback addresses). Only an explicit `False`/`0`/`no`/`off` disables it, for deployments with a managed database. |
| `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT`, `DB_SSLMODE` | PostgreSQL connection. `DB_SSLMODE` defaults to `require`; the local containers need `disable`. |
| `CORS_ALLOWED_ORIGINS` | The frontend origin(s), `http://localhost:3001` locally. |
| `VITE_API_URL` | The API root the frontend calls, including `/api`: `http://localhost:8000/api` for a host-run backend, `http://localhost:8001/api` for the Compose backend. Read at Vite start/build time. |
| `ALLOCATION_WORKER_*` | Worker tunables (see [ALLOCATION_WORKER.md](ALLOCATION_WORKER.md)). |
| `ALLOCATION_NUM_SEARCH_WORKERS` | CP-SAT search workers (default 2; tests use 1 for reproducibility). |
| `JWT_*`, `THROTTLE_*`, `SECURE_*` | Authentication lifetimes, cookie settings, rate limits and hardening; safe defaults in code. |

Precedence: `settings.py` loads `.env` with python-dotenv without `override`, so a variable already exported in the shell wins silently. If the application connects somewhere unexpected, check for stale `DB_*` or `DORMIFY_LOCAL_DB_ONLY` values in the shell first.

`ENV_FILE` selects a different file: host-side tests use `ENV_FILE=.env.test` (recipe in `.env.example`), which points at the test database on port 5435.

## Full stack in Docker

First run, on a blank database:

```bash
docker compose -p dormify-v3 up -d db                                            # 1. database only (waits for its healthcheck)
docker compose -p dormify-v3 run --rm --build backend python manage.py migrate   # 2. apply the schema before any worker polls
docker compose -p dormify-v3 up --build                                          # 3. db, backend, allocation_worker, frontend
docker compose -p dormify-v3 exec backend python seed.py                         # 4. synthetic demo inventory and accounts; requires DEBUG=True (set in Compose)
docker compose -p dormify-v3 exec backend python scripts/generate_demo_students.py   # 5. synthetic student workbook, see "Synthetic demo data"
docker compose -p dormify-v3 logs -f allocation_worker                           # worker events
docker compose -p dormify-v3 down                                                # keeps the data volume
```

Migrate before starting the worker. `allocation_worker` begins polling `api_allocationrun` as soon as the database is healthy; on a database that has never been migrated it logs `relation "api_allocationrun" does not exist` (or a missing-column error) on every poll until the migrations are applied, then recovers on its own. Nothing is damaged, but a first-time user should not have to read those errors. After the first run, `docker compose -p dormify-v3 up` is enough; run `migrate` again (step 2, or `exec backend python manage.py migrate` while the stack is up) whenever you pull new migrations.

Both application containers bind-mount `./backend`, so code edits are live. The frontend container mounts `./frontend` and keeps its own `node_modules`.

### The development database volume

The development database is stored in the named Docker volume `dormify-v3-dev-pgdata`. Its name is fixed by `docker-compose.yml`, not derived from the project name or the checkout directory, so:

- it is intentionally persistent: `down`, rebuilds and restarts keep the data, and only an explicit volume removal deletes it;
- it is shared by every checkout of Dormify v3 on the same host. A fresh clone of the source code is therefore not automatically a blank database; if the volume already exists, the new checkout starts with whatever migrations, seed data and imports the previous checkout left there;
- do not delete it casually. Local data that is not reproducible from `seed.py` and the generator is lost with it.

A reviewer who needs a clean-room database has two options. Preferred: run against an isolated volume name through a Compose override file kept outside the repository (or untracked), which leaves the regular development data untouched:

```yaml
# clean-room.yml
volumes:
  dev_pgdata:
    name: dormify-v3-clean-room-pgdata
```

```bash
docker compose -p dormify-v3 -f docker-compose.yml -f clean-room.yml up -d db
docker compose -p dormify-v3 -f docker-compose.yml -f clean-room.yml run --rm --build backend python manage.py migrate
docker compose -p dormify-v3 -f docker-compose.yml -f clean-room.yml up
```

Alternatively, reset the regular development volume deliberately, knowing that its data is gone:

```bash
docker compose -p dormify-v3 down
docker volume rm dormify-v3-dev-pgdata
```

The automated test database uses its own volume (`dormify-v3-test-pgdata`) and is unaffected by either procedure.

## Host-side backend

```bash
docker compose -p dormify-v3 up -d db
cd backend
python -m venv .venv && . .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt -c constraints.txt    # pinned runtime graph
pip install -r requirements-dev.txt                   # ruff, pre-commit, pip-audit (optional)
python manage.py migrate
python manage.py runserver                            # terminal 1
python manage.py allocation_worker                    # terminal 2
```

The pinned graph (`constraints.txt`) is resolved for CPython 3.11, the version of the backend image and CI; `ortools==9.10.4067` has no wheel for newer interpreters.

## Host-side frontend

```bash
cd frontend
npm ci
npm start            # http://localhost:3001
npm run typecheck    # tsc, strict for .ts/.tsx
npm run lint         # ESLint, warnings are errors
npm test             # Vitest
npm run build        # lint + production bundle in frontend/build/
```

Vite reads `VITE_API_URL` from the repository root (`envDir`), not from `frontend/`.

## Accounts

There is no self-registration. Create the first account with `python manage.py createsuperuser` (central administrator through the Django admin at `/admin/`) or run `python seed.py`, which creates one synthetic staff account per role (`admin@example.edu`, `canada@example.edu`, `canada.emp@example.edu`, `hasmaha@example.edu`, `mizrah@example.edu`) and prints the generated passwords once (`SEED_ADMIN_PASSWORD` / `SEED_STAFF_PASSWORD` fix them if set). Further staff accounts are created from the Staff page or `POST /api/staff-users/` by a central or regional manager.

## Synthetic demo data

Two scripts produce a complete, synthetic data set for demos, manual testing, screenshots and fresh-clone evaluation. Nothing they create refers to a real person or to real inventory. The screenshots in `docs/images/` (see the README's product preview) were taken from this data set.

1. `python seed.py` (from `backend/`, `DEBUG=True` required, safe to re-run) creates six regions, seven dormitory types carrying the official dorm-office codes the importer resolves (2, 15, 12, 5, 1, 17, 13), buildings, apartments, rooms and beds for codes 2, 15, 12 and 5 (including an inactive apartment and a gender-restricted shared-facility building), and the staff accounts above. Codes 1, 13 and 17 deliberately have no inventory.
2. `python scripts/generate_demo_students.py` writes `backend/demo-data/demo_students.xlsx` (git-ignored) in the dorm-office import format: three sheets (continuing, new, leaving), the real column headers from `api/domains/imports/parsing.py`, 9-digit identifiers starting with `9`, `@example.edu` e-mails and `050-1xxxxxx` phone numbers. Options: `--count` (default 120), `--seed` (default 2026; the same seed and count always produce the same workbook), `--output`, `--help`. The population is skewed so a demo shows both outcomes: more single-female applicants than Canada has beds, household applications beyond the household apartments, students accepted to a dorm type without inventory, accessibility cases (left to the assisted workbench), ANIR and other priority students, religious-placement requests and mutual roommate requests.

Then, in the UI: sign in as `admin@example.edu`, upload the workbook on the Students import page (main population file), sign in as a regional manager (for example `canada@example.edu`), start an allocation from the Allocation page and watch the worker execute it (`docker compose -p dormify-v3 logs -f allocation_worker`). The generator is covered by `api.tests.domains.test_demo_student_generator`, which also runs its output through the real import path.

## Troubleshooting

- **"local-database-only mode" error at startup**: `DB_HOST` is not a recognised local host, or a stale shell variable overrides `.env`. Clear it or set `DORMIFY_LOCAL_DB_ONLY=False` deliberately for a managed database.
- **Frontend cannot reach the API**: `VITE_API_URL` must include `/api` and match where the backend runs (8000 host, 8001 Compose); restart Vite after changing it. CORS must list the frontend origin.
- **Allocation stays QUEUED**: no worker is running. Start `manage.py allocation_worker` (host) or check `docker compose -p dormify-v3 logs allocation_worker`.
- **Worker logs `relation "api_allocationrun" does not exist` or `column api_allocationrun.claimed_by does not exist`**: migrations are not applied yet, which is expected when the full stack was started on a blank database before `migrate` (see "Full stack in Docker"). Run `migrate`; the worker keeps polling and recovers by itself.
- **A fresh clone already contains data**: the named volume `dormify-v3-dev-pgdata` from an earlier checkout is being reused. See "The development database volume".
- **Tests fail with connection errors**: start the test database (`docker compose -p dormify-v3 --profile local-db up -d test_db`) and use `ENV_FILE=.env.test`.
