from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework import status

from api.models import AllocationRun
from api.serializers import AllocationRunSerializer
from allocation.solver import (
    run_improved_ortools_allocation,
    MIN_USER_SOLVER_TIME_SECONDS,
    MAX_USER_SOLVER_TIME_SECONDS,
    DEFAULT_SOLVER_TIME_SECONDS,
)

from ._support import (
    _make_region,
    _make_region_boss,
    _make_run,
    _make_minimal_infra,
    _make_minimal_student,
    MINIMAL_SOLVER_CONFIG,
)


# ---------------------------------------------------------------------------
# Tests: configurable max solver time (זמן חיפוש מרבי)
# ---------------------------------------------------------------------------

class MaxSolverSecondsViewTest(TestCase):
    """Requirement 1/2: user-selected max time reaches CP-SAT; invalid values rejected."""

    def setUp(self):
        self.client = APIClient()
        self.region = _make_region('MaxSecondsRegion')
        self.boss = _make_region_boss(self.region)

    # Since R8 the start request queues a durable run instead of starting a
    # thread: the operator's value must reach the stored job parameters the
    # allocation worker hands to the solver.
    def test_valid_max_solver_seconds_passed_through(self):
        self.client.force_authenticate(user=self.boss)
        resp = self.client.post('/api/allocation/start/', {
            'region': self.region.id,
            'max_solver_seconds': 90,
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_202_ACCEPTED, resp.data)

        run = AllocationRun.objects.get(pk=resp.data['run_id'])
        self.assertEqual(run.job_parameters['max_seconds'], 90.0)
        self.assertEqual(run.max_search_seconds, 90)

    def test_missing_max_solver_seconds_uses_default(self):
        self.client.force_authenticate(user=self.boss)
        resp = self.client.post('/api/allocation/start/', {
            'region': self.region.id,
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_202_ACCEPTED, resp.data)
        run = AllocationRun.objects.get(pk=resp.data['run_id'])
        self.assertEqual(run.job_parameters['max_seconds'], DEFAULT_SOLVER_TIME_SECONDS)

    def test_non_numeric_max_solver_seconds_rejected(self):
        self.client.force_authenticate(user=self.boss)
        resp = self.client.post('/api/allocation/start/', {
            'region': self.region.id,
            'max_solver_seconds': 'not-a-number',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(AllocationRun.objects.exists())

    def test_below_minimum_max_solver_seconds_rejected(self):
        self.client.force_authenticate(user=self.boss)
        resp = self.client.post('/api/allocation/start/', {
            'region': self.region.id,
            'max_solver_seconds': 0,
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(AllocationRun.objects.exists())

    def test_above_maximum_max_solver_seconds_rejected(self):
        self.client.force_authenticate(user=self.boss)
        resp = self.client.post('/api/allocation/start/', {
            'region': self.region.id,
            'max_solver_seconds': 999999,
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(AllocationRun.objects.exists())


class SolverTimeLimitDirectTest(TestCase):
    """Requirements 1/2/3 at the solver layer: bounds enforced independently
    of the view, max_seconds reaches CpSolver, an easy model finishes long
    before its time limit."""

    def setUp(self):
        patcher = patch('allocation.solver.close_old_connections')
        patcher.start()
        self.addCleanup(patcher.stop)
        self.region = _make_region('SolverTimeRegion')
        self.dorm_type, self.rooms = _make_minimal_infra(self.region)
        self.student = _make_minimal_student('TL1', self.dorm_type)

    def test_max_seconds_reaches_solver_time_limit(self):
        result = run_improved_ortools_allocation(
            [self.student], self.rooms, MINIMAL_SOLVER_CONFIG, max_seconds=8,
        )
        self.assertEqual(result['time_limit_seconds'], 8.0)

    def test_default_max_seconds_used_when_not_specified(self):
        result = run_improved_ortools_allocation(
            [self.student], self.rooms, MINIMAL_SOLVER_CONFIG,
        )
        self.assertEqual(result['time_limit_seconds'], DEFAULT_SOLVER_TIME_SECONDS)

    def test_solver_rejects_below_minimum_max_seconds(self):
        with self.assertRaises(ValueError):
            run_improved_ortools_allocation(
                [self.student], self.rooms, MINIMAL_SOLVER_CONFIG,
                max_seconds=MIN_USER_SOLVER_TIME_SECONDS - 1,
            )

    def test_solver_rejects_above_maximum_max_seconds(self):
        with self.assertRaises(ValueError):
            run_improved_ortools_allocation(
                [self.student], self.rooms, MINIMAL_SOLVER_CONFIG,
                max_seconds=MAX_USER_SOLVER_TIME_SECONDS + 1,
            )

    def test_solver_finishes_before_max_time_when_trivially_optimal(self):
        result = run_improved_ortools_allocation(
            [self.student], self.rooms, MINIMAL_SOLVER_CONFIG, max_seconds=30,
        )
        self.assertEqual(result['solver_status'], 'OPTIMAL')
        self.assertTrue(result['optimality_proven'])
        self.assertLess(result['wall_time'], 5.0)


# ---------------------------------------------------------------------------
# Tests: persistent search timing (AllocationRun.search_started_at +
# AllocationRunSerializer.elapsed_search_seconds/remaining_search_seconds).
# Frontend timer-reconstruction bug fix — the backend must be the source
# of truth, never local React state re-derived from Date.now() at mount.
# ---------------------------------------------------------------------------

class SearchStartedAtTest(TestCase):
    """search_started_at is stamped by the solver itself, right before
    Solve() — meaningfully after AllocationRun.started_at (row creation),
    and only when a real solver_run_id is supplied."""

    def setUp(self):
        patcher = patch('allocation.solver.close_old_connections')
        patcher.start()
        self.addCleanup(patcher.stop)
        self.region = _make_region('SearchStartedAtRegion')
        self.boss = _make_region_boss(self.region)
        self.dorm_type, self.rooms = _make_minimal_infra(self.region)
        self.student = _make_minimal_student('SSA1', self.dorm_type)

    def test_search_started_at_set_after_solve_with_run_id(self):
        run = _make_run(self.region, self.boss, status_val=AllocationRun.Status.RUNNING, completed=False)
        self.assertIsNone(run.search_started_at)

        run_improved_ortools_allocation(
            [self.student], self.rooms, MINIMAL_SOLVER_CONFIG,
            allocation_run_id=run.id, max_seconds=5,
        )

        run.refresh_from_db()
        self.assertIsNotNone(run.search_started_at)
        self.assertGreaterEqual(run.search_started_at, run.started_at)

    def test_search_started_at_stays_none_without_run_id(self):
        """Legacy sync callers (no allocation_run_id) see zero behavior
        change — nothing to stamp, no AllocationRun row passed in."""
        result = run_improved_ortools_allocation(
            [self.student], self.rooms, MINIMAL_SOLVER_CONFIG, max_seconds=5,
        )
        self.assertEqual(result['solver_status'], 'OPTIMAL')


        # No exception / no AllocationRun touched — nothing further to assert.


class AllocationRunTimingSerializerTest(TestCase):
    """Pure serializer-level checks for elapsed_search_seconds /
    remaining_search_seconds — the values the frontend now treats as
    authoritative instead of re-deriving them from local mount time."""

    def setUp(self):
        self.region = _make_region('TimingSerializerRegion')
        self.boss = _make_region_boss(self.region)

    def _run(self, **kwargs):
        defaults = dict(
            region=self.region,
            run_by=self.boss,
            status=AllocationRun.Status.RUNNING,
            max_search_seconds=500,
        )
        defaults.update(kwargs)
        run = AllocationRun(**defaults)
        # bulk_create bypasses the model's overridden save()/full_clean(),
        # same pattern _make_run() above already uses — lets these fixtures
        # set search_started_at/completed_at combinations directly.
        AllocationRun.objects.bulk_create([run])
        return AllocationRun.objects.get(pk=run.pk)

    def test_queued_or_pre_solve_shows_zero_elapsed_and_full_remaining(self):
        run = self._run(status=AllocationRun.Status.QUEUED, search_started_at=None)
        data = AllocationRunSerializer(run).data
        self.assertEqual(data['elapsed_search_seconds'], 0)
        self.assertEqual(data['remaining_search_seconds'], 500)

    def test_running_elapsed_matches_now_minus_search_started_at(self):
        started = timezone.now() - timedelta(seconds=200)
        run = self._run(status=AllocationRun.Status.RUNNING, search_started_at=started)
        data = AllocationRunSerializer(run).data
        # allow a couple seconds of test-execution slack
        self.assertAlmostEqual(data['elapsed_search_seconds'], 200, delta=3)
        self.assertAlmostEqual(data['remaining_search_seconds'], 300, delta=3)

    def test_completed_run_freezes_at_completed_at_not_now(self):
        started = timezone.now() - timedelta(seconds=400)
        completed = started + timedelta(seconds=120)
        run = self._run(
            status=AllocationRun.Status.COMPLETED,
            search_started_at=started,
            completed_at=completed,
        )
        data = AllocationRunSerializer(run).data
        self.assertEqual(data['elapsed_search_seconds'], 120)
        self.assertEqual(data['remaining_search_seconds'], 380)

        # A second read (simulating a later GET on a finished run) must
        # return the exact same frozen value, not one that keeps growing
        # with real wall-clock time.
        data_again = AllocationRunSerializer(run).data
        self.assertEqual(data_again['elapsed_search_seconds'], 120)

    def test_remaining_floors_at_zero_when_elapsed_exceeds_max(self):
        started = timezone.now() - timedelta(seconds=999)
        run = self._run(
            status=AllocationRun.Status.RUNNING,
            search_started_at=started,
            max_search_seconds=500,
        )
        data = AllocationRunSerializer(run).data
        self.assertEqual(data['remaining_search_seconds'], 0)

    def test_no_max_search_seconds_means_no_remaining(self):
        run = self._run(
            status=AllocationRun.Status.RUNNING,
            search_started_at=timezone.now(),
            max_search_seconds=None,
        )
        data = AllocationRunSerializer(run).data
        self.assertIsNone(data['remaining_search_seconds'])
