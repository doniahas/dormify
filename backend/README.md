# Dormify backend

Django 5.2 / Django REST Framework 3.17 API, the OR-Tools CP-SAT allocation engine and the durable allocation worker. Python 3.11 is the supported interpreter (backend image and CI); the runtime graph is pinned in `constraints.txt`.

Setup, environment variables and ports are documented in [../docs/DEVELOPMENT.md](../docs/DEVELOPMENT.md); the API in [../docs/API.md](../docs/API.md); the worker in [../docs/ALLOCATION_WORKER.md](../docs/ALLOCATION_WORKER.md); the test suites in [../docs/TESTING.md](../docs/TESTING.md).

## Layout

```text
backend/
  dormify/            settings.py, urls.py (admin + /api/), wsgi.py, db_safety.py (local-database guard)
  api/
    models.py         User (roles), Region, DormType, Building, Apartment, Room, Bed, Student,
                      BedAssignment, StudentRequest, Transfer, AllocationRun, ImportBatch,
                      RegionInbox, AssistedAllocationAudit, Office, StaffProfile, MovementRequest
    urls.py           every /api/ route (plus accounts/urls.py for /api/staff-users/)
    views/            thin HTTP views: auth, students, inventory, placement, transfers, imports,
                      allocation, assisted, analytics, dashboard, whatif, reports; __init__.py is a
                      re-export facade pinned by the characterization tests
    contracts/        request parsers and error-body builders
    serializers/      auth, organization, inventory, students, workflows, operations
    domains/          business logic: allocation (config, queries, inputs, engine, persistence,
                      orchestration, jobs, fencing, worker, results, runs, gateway), imports,
                      inventory, placement, matching, transfers, assisted, analytics, reports,
                      students, whatif
    permissions.py    IsCentralAdmin, IsBoss, region scoping helpers
    throttling.py     auth and staff-creation throttles
    management/commands/
                      allocation_worker, run_allocation_case, materialize_beds
    migrations/
    tests/            functional, characterization, allocation, assisted_allocation, security,
                      performance, concurrency, domains, contracts, support
  accounts/           staff-account list/create endpoint and its permission
  allocation/         solver.py (CP-SAT model and persistence), manual_placement.py (assisted rules),
                      live_registry.py (in-process live snapshots and stop fast path)
  canada_algorithm_tests/  controlled solver scenarios with expected results
  scripts/            generate_demo_students.py: synthetic student workbook for the Excel import
  seed.py             synthetic demo regions, dorm types, inventory and staff accounts
                      (requires DEBUG=True; random or env-supplied passwords)
  requirements.txt, constraints.txt, requirements-dev.txt, ruff.toml, Dockerfile
```

## Everyday commands

```bash
# from backend/, with the repository-root .env in place and the Compose db running
pip install -r requirements.txt -c constraints.txt
python manage.py migrate
python manage.py runserver                       # http://localhost:8000
python manage.py allocation_worker               # execute queued allocation runs (second terminal)
python manage.py allocation_worker --once        # one cycle, then exit
python seed.py                                   # synthetic demo regions, dorm types, inventory, staff accounts
python scripts/generate_demo_students.py         # synthetic student workbook -> demo-data/demo_students.xlsx (git-ignored)
python manage.py createsuperuser                 # admin at http://localhost:8000/admin/
python manage.py makemigrations                  # after model changes
python manage.py run_allocation_case case_01_full_integration_balanced --max-seconds 60
python manage.py materialize_beds [--apply]      # repair missing Bed rows (dry run by default)
```

## Tests

```bash
docker compose -p dormify-v3 --profile local-db up -d test_db      # from the repository root
ENV_FILE=.env.test python manage.py test                           # from backend/
ENV_FILE=.env.test python manage.py test api.tests.allocation      # one family
ruff check .
```

`.env.test` is a separate, git-ignored file in the repository root (recipe in `.env.example`) that targets the disposable test database on port 5435. Run tests on the host (or in a Python 3.11 container), not through `docker compose exec backend`, because the backend container cannot see the repository root.

## Allocation engine in one paragraph

`allocation/solver.py` turns the region's unassigned students and active beds into a CP-SAT model: one boolean per feasible student/apartment candidate, hard constraints that are never violated (gender, requested religious placement, capacity, inactive housing, reserved-apartment eligibility, priority-first when configured hard), and a weighted objective over soft preferences (roommate requests, same religion, sector, year mix, program preference). It respects the operator's time limit, publishes live snapshots while searching, honours cancel and stop-and-save requests through the database status, and persists the chosen assignments in one transaction. `api/domains/allocation/` owns everything around it: what the solver receives, how it is called, how its result is recorded, and (through the worker) when it runs.
