"""
Direct tests for the durable allocation jobs (api.domains.allocation.jobs /
worker / the allocation_worker command): claiming, leases, recovery of lost
workers, execution of a claimed run through the R7 engine boundary, and
the web process's reduced responsibility (queue, read, stop - never execute).
"""

import contextlib
import io
import threading
import time
from datetime import timedelta
from unittest.mock import MagicMock, patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.test import SimpleTestCase, TestCase, TransactionTestCase
from django.utils import timezone
from rest_framework.test import APIClient

from allocation import live_registry
from allocation.solver import _STOP_WATCHER_POLL_INTERVAL_SECONDS, _run_stop_watcher
from api.domains.allocation import jobs
from api.domains.allocation.config import DEFAULT_CONDITIONS, normalize_allocation_constraints
from api.domains.allocation.fencing import ClaimFence, ClaimLost
from api.domains.allocation.jobs import (
    LOST_AFTER_PERSISTENCE_MESSAGE,
    LOST_BEFORE_SOLVE_MESSAGE,
    LOST_DURING_SOLVE_MESSAGE,
    ClaimedRun,
    LeaseHeartbeat,
    WorkerSettings,
    claim_next_run,
    execute_claimed_run,
    pack_job_parameters,
    recover_stale_runs,
    release_lease,
    renew_lease,
    unpack_job_parameters,
)
from api.domains.allocation.orchestration import execute_allocation_run
from api.domains.allocation.runs import request_run_stop
from api.domains.allocation.worker import AllocationWorker
from api.models import AllocationRun, BedAssignment, Student

from ._fixtures import (
    assign,
    make_boss,
    make_full_stack,
    make_region,
    make_run,
    make_student,
)

CANNED_RESULT = {
    'students_processed': 2, 'successful_assignments': 2, 'conflicts': 0,
    'mutual_roommate_matches': 0, 'one_sided_roommate_matches': 0,
    'solver_status': 'OPTIMAL', 'optimality_proven': True, 'objective_value': 4.0,
    'best_objective_bound': 4.0, 'absolute_gap': 0.0, 'relative_gap': 0.0,
    'warnings': [], 'anier_building_179_diagnostics': {}, 'solution_persisted': True,
    'wall_time': 0.1, 'students_with_no_feasible_beds': [], 'assignments': [],
}

TEST_SETTINGS = WorkerSettings(
    poll_interval_seconds=0.01, lease_seconds=60, heartbeat_seconds=0, max_attempts=3,
)
DEAD_WORKER = 'dead-host:1:deadbeef'
WORKER_A = 'host-a:100:aaaaaaaa'
WORKER_B = 'host-b:200:bbbbbbbb'


def _parameters(max_seconds=30.0, **extra):
    values = {
        'constraints_config': normalize_allocation_constraints(None),
        'include_assigned': False,
        'allocation_scope': None,
        'max_seconds': max_seconds,
    }
    values.update(extra)
    return pack_job_parameters(**values)


def _queued_run(region, user, **extra):
    extra.setdefault('status', AllocationRun.Status.QUEUED)
    extra.setdefault('job_parameters', _parameters())
    extra.setdefault('max_search_seconds', 30)
    return make_run(region, user, completed=False, **extra)


def _stale_run(region, user, status=AllocationRun.Status.RUNNING, *, started=False, attempts=1, **extra):
    """A run claimed by a worker whose lease expired a minute ago."""
    now = timezone.now()
    return make_run(
        region, user, status=status, completed=False,
        job_parameters=_parameters(), max_search_seconds=30,
        claimed_by=DEAD_WORKER, lease_expires_at=now - timedelta(seconds=60), attempts=attempts,
        search_started_at=(now - timedelta(seconds=120)) if started else None,
        **extra,
    )


@contextlib.contextmanager
def inline_connections():
    """
    The run body and the worker own their connections in production (they
    close them when done); inside a TestCase that would end the wrapping
    transaction, so the connection-closing calls are made no-ops.
    """
    with patch('django.db.close_old_connections'), patch('django.db.connection.close'), \
            patch('api.domains.allocation.jobs.close_old_connections'), \
            patch('api.domains.allocation.worker.close_old_connections'):
        yield


class _SolverRecorder:
    """
    A stand-in for the solver: records its calls, optionally acts mid-solve
    (``side_effect``), then - like the real solver's persistence transaction
    - invokes the ``persistence_guard`` it was given before ``persist``.
    """

    def __init__(self, result=None, side_effect=None, persist=None):
        self.result = result if result is not None else dict(CANNED_RESULT)
        self.side_effect = side_effect
        self.persist = persist
        self.calls = []
        self.guard_called = False
        self.guard_raised = False

    def __call__(self, *args, **kwargs):
        self.calls.append({
            'kwargs': kwargs,
            'student_ids': sorted(kwargs['students'].values_list('id', flat=True)),
        })
        if self.side_effect is not None:
            outcome = self.side_effect(kwargs)
            if outcome is not None:
                return outcome
        guard = kwargs.get('persistence_guard')
        if guard is not None:
            self.guard_called = True
            try:
                guard()
            except Exception:
                self.guard_raised = True
                raise
        if self.persist is not None:
            self.persist(kwargs)
        return dict(self.result)


# ---------------------------------------------------------------------------
# Job parameters and settings
# ---------------------------------------------------------------------------

class JobParameterTests(SimpleTestCase):
    def test_pack_and_unpack_round_trip(self):
        constraints = normalize_allocation_constraints({'sameReligion': {'enabled': False}})
        document = pack_job_parameters(
            constraints_config=constraints, include_assigned=1,
            allocation_scope='new_transfer_only', max_seconds=90.0,
        )
        self.assertEqual(list(document), ['constraints_config', 'include_assigned', 'allocation_scope', 'max_seconds'])
        self.assertIs(document['include_assigned'], True)
        parameters = unpack_job_parameters(document)
        self.assertEqual(parameters.constraints_config, constraints)
        self.assertIs(parameters.include_assigned, True)
        self.assertEqual(parameters.allocation_scope, 'new_transfer_only')
        self.assertEqual(parameters.max_seconds, 90.0)

    def test_legacy_run_without_parameters_is_rejected_and_missing_constraints_default(self):
        with self.assertRaises(ValueError):
            unpack_job_parameters(None)
        parameters = unpack_job_parameters({'max_seconds': None})
        self.assertEqual(parameters.constraints_config, DEFAULT_CONDITIONS)
        self.assertIs(parameters.include_assigned, False)
        self.assertIsNone(parameters.allocation_scope)
        self.assertIsNone(parameters.max_seconds)

    def test_worker_settings_defaults_overrides_and_validation(self):
        defaults = WorkerSettings.from_settings()
        self.assertEqual(
            (defaults.poll_interval_seconds, defaults.lease_seconds, defaults.heartbeat_seconds, defaults.max_attempts),
            (2.0, 300, 30.0, 3),
        )
        tuned = WorkerSettings.from_settings(lease_seconds=20, heartbeat_seconds=5, poll_interval_seconds=None)
        self.assertEqual((tuned.lease_seconds, tuned.heartbeat_seconds, tuned.poll_interval_seconds), (20, 5.0, 2.0))
        for invalid in (
            {'poll_interval_seconds': 0}, {'lease_seconds': 0}, {'heartbeat_seconds': -1},
            {'heartbeat_seconds': 300}, {'max_attempts': 0},
        ):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                WorkerSettings.from_settings(**invalid)
        self.assertRegex(jobs.build_worker_id(), r'^.+:\d+:[0-9a-f]{8}$')


# ---------------------------------------------------------------------------
# Claiming and leases
# ---------------------------------------------------------------------------

class ClaimTests(TestCase):
    def setUp(self):
        self.region = make_region('Jobs Region')
        self.other = make_region('Jobs Other Region')
        self.boss = make_boss(self.region)

    def test_queued_run_is_claimed_exactly_once(self):
        run = _queued_run(self.region, self.boss)
        claimed = claim_next_run(WORKER_A, lease_seconds=60)
        self.assertIsInstance(claimed, ClaimedRun)
        self.assertEqual((claimed.run_id, claimed.region_id, claimed.status, claimed.attempt),
                         (run.id, self.region.id, AllocationRun.Status.QUEUED, 1))
        self.assertEqual(claimed.parameters.max_seconds, 30.0)
        self.assertIsNone(claim_next_run(WORKER_B, lease_seconds=60))
        run.refresh_from_db()
        self.assertEqual((run.claimed_by, run.attempts), (WORKER_A, 1))
        self.assertGreater(run.lease_expires_at, timezone.now() + timedelta(seconds=50))
        # The claim is bookkeeping only: the run body makes it RUNNING.
        self.assertEqual(run.status, AllocationRun.Status.QUEUED)

    def test_two_workers_claim_different_runs_oldest_first(self):
        first = _queued_run(self.region, self.boss)
        AllocationRun.objects.filter(pk=first.pk).update(started_at=timezone.now() - timedelta(minutes=5))
        second = _queued_run(self.other, self.boss)
        self.assertEqual(claim_next_run(WORKER_A, lease_seconds=60).run_id, first.id)
        self.assertEqual(claim_next_run(WORKER_B, lease_seconds=60).run_id, second.id)
        self.assertIsNone(claim_next_run('host-c:3:cccccccc', lease_seconds=60))

    def test_legacy_and_in_request_runs_are_never_claimed(self):
        make_run(self.region, self.boss, status=AllocationRun.Status.QUEUED, completed=False)  # pre-R8 run
        make_run(self.other, self.boss, status=AllocationRun.Status.RUNNING, completed=False)  # sync/retry run
        self.assertIsNone(claim_next_run(WORKER_A, lease_seconds=60))

    def test_stop_requested_before_any_claim_is_claimable(self):
        run = _queued_run(self.region, self.boss, status=AllocationRun.Status.CANCELLATION_REQUESTED)
        claimed = claim_next_run(WORKER_A, lease_seconds=60)
        self.assertEqual((claimed.run_id, claimed.status), (run.id, AllocationRun.Status.CANCELLATION_REQUESTED))

    def test_renew_and_release_lease_belong_to_the_claiming_worker(self):
        run = _queued_run(self.region, self.boss)
        claimed = claim_next_run(WORKER_A, lease_seconds=60)
        self.assertFalse(renew_lease(run.id, WORKER_B, claimed.attempt, lease_seconds=60))
        self.assertFalse(renew_lease(run.id, WORKER_A, claimed.attempt + 1, lease_seconds=60),
                         'a renewal names its own claim generation')
        later = timezone.now() + timedelta(seconds=30)
        self.assertTrue(renew_lease(run.id, WORKER_A, claimed.attempt, lease_seconds=60, now=later))
        run.refresh_from_db()
        self.assertEqual(run.lease_expires_at, later + timedelta(seconds=60))
        self.assertGreater(run.lease_expires_at, claimed.lease_expires_at)
        self.assertTrue(release_lease(run.id, WORKER_A, claimed.attempt))
        run.refresh_from_db()
        self.assertIsNone(run.lease_expires_at)
        self.assertEqual(run.claimed_by, WORKER_A)
        AllocationRun.objects.filter(pk=run.pk).update(status=AllocationRun.Status.COMPLETED, completed_at=timezone.now())
        self.assertFalse(renew_lease(run.id, WORKER_A, claimed.attempt, lease_seconds=60), 'a finished run holds no lease')


# ---------------------------------------------------------------------------
# Executing a claimed run through the R7 boundary
# ---------------------------------------------------------------------------

class ExecutionFixture(TestCase):
    def setUp(self):
        self.region = make_region('Jobs Exec Region')
        self.boss = make_boss(self.region)
        self.dorm, self.building, self.apartment, self.room = make_full_stack(self.region)
        self.students = [make_student(self.dorm, 'JOB-1'), make_student(self.dorm, 'JOB-2')]

    def _execute(self, run, solver, worker_id=WORKER_A, claim=True):
        claimed = claim_next_run(worker_id, lease_seconds=60) if claim else run
        self.assertIsNotNone(claimed)
        with inline_connections(), patch('allocation.solver.run_improved_ortools_allocation', new=solver):
            outcome = execute_claimed_run(claimed, worker_id, worker_settings=TEST_SETTINGS)
        run.refresh_from_db()
        return outcome


class ExecuteClaimedRunTests(ExecutionFixture):
    def test_claimed_run_executes_through_the_engine_boundary_and_completes(self):
        constraints = normalize_allocation_constraints({'sameReligion': {'enabled': False}})
        run = _queued_run(
            self.region, self.boss,
            job_parameters=_parameters(max_seconds=45.0, constraints_config=constraints, allocation_scope='new_transfer_only'),
        )
        Student.objects.filter(pk=self.students[1].pk).update(category=Student.StudentCategory.CONTINUING)
        solver = _SolverRecorder()
        outcome = self._execute(run, solver)

        self.assertEqual(len(solver.calls), 1)
        kwargs = solver.calls[0]['kwargs']
        self.assertEqual(
            list(kwargs),
            ['students', 'rooms', 'constraints_config', 'allocation_run_id', 'max_seconds',
             'enable_group_capacity_cuts', 'persistence_guard', 'run_ownership_filter'],
        )
        self.assertTrue(callable(kwargs['persistence_guard']), 'the worker fences the solver persistence')
        self.assertEqual(kwargs['run_ownership_filter'], {'claimed_by': WORKER_A, 'attempts': 1},
                         "the solver's own run-row writes are scoped to the claim generation")
        self.assertTrue(solver.guard_called)
        self.assertEqual(kwargs['allocation_run_id'], run.id)
        self.assertEqual(kwargs['max_seconds'], 45.0)
        self.assertEqual(kwargs['constraints_config'], constraints)
        self.assertIs(kwargs['enable_group_capacity_cuts'], True)
        self.assertEqual(solver.calls[0]['student_ids'], [self.students[0].id], 'the stored scope narrows the population')

        self.assertEqual(run.status, AllocationRun.Status.COMPLETED)
        self.assertEqual((run.students_processed, run.successful_assignments, run.conflicts), (2, 2, 0))
        self.assertEqual(run.diagnostics['solver_status'], 'OPTIMAL')
        self.assertEqual(run.diagnostics['population_summary']['sent_to_solver_student_ids'], [self.students[0].id])
        self.assertEqual((run.claimed_by, run.attempts, run.lease_expires_at), (WORKER_A, 1, None))
        self.assertEqual((outcome.run_id, outcome.status, outcome.error_message, outcome.stopped_early_by_user, outcome.lease_lost),
                         (run.id, AllocationRun.Status.COMPLETED, '', False, False))
        self.assertFalse(outcome.fenced)

    def test_solver_failure_marks_the_run_failed_and_drops_the_lease(self):
        run = _queued_run(self.region, self.boss)

        def explode(kwargs):
            raise RuntimeError('solver exploded')

        outcome = self._execute(run, _SolverRecorder(side_effect=explode))
        self.assertEqual(run.status, AllocationRun.Status.FAILED)
        self.assertEqual(run.error_message, 'solver exploded')
        self.assertIsNotNone(run.completed_at)
        self.assertIsNone(run.lease_expires_at)
        self.assertEqual(outcome.status, AllocationRun.Status.FAILED)
        self.assertEqual(outcome.error_message, 'solver exploded')

    def test_cancellation_requested_during_the_solve_discards_the_persisted_result(self):
        run = _queued_run(self.region, self.boss)

        def persist_then_cancel(kwargs):
            assign(self.students[0], self.room, run=run)
            AllocationRun.objects.filter(pk=run.pk).update(status=AllocationRun.Status.CANCELLATION_REQUESTED)

        self._execute(run, _SolverRecorder(side_effect=persist_then_cancel))
        self.assertEqual(run.status, AllocationRun.Status.STOPPED)
        rows = BedAssignment.objects.filter(allocation_run=run)
        self.assertEqual(list(rows.values_list('status', flat=True)), [BedAssignment.Status.CANCELLED])
        self.students[0].refresh_from_db()
        self.assertIsNone(self.students[0].assigned_room_id)
        self.assertIsNone(run.live_snapshot)

    def test_stop_and_save_requested_during_the_solve_keeps_the_persisted_result(self):
        run = _queued_run(self.region, self.boss)
        result = {**CANNED_RESULT, 'solver_status': 'FEASIBLE', 'optimality_proven': False,
                  'successful_assignments': 1, 'conflicts': 1}

        def persist_then_stop(kwargs):
            assign(self.students[0], self.room, run=run)
            AllocationRun.objects.filter(pk=run.pk).update(status=AllocationRun.Status.STOP_AND_SAVE_REQUESTED)

        outcome = self._execute(run, _SolverRecorder(result=result, side_effect=persist_then_stop))
        self.assertEqual(run.status, AllocationRun.Status.COMPLETED)
        self.assertIs(run.diagnostics['stopped_early_by_user'], True)
        self.assertEqual(run.diagnostics['solver_status'], 'FEASIBLE')
        self.assertIs(outcome.stopped_early_by_user, True)
        self.assertEqual(
            list(BedAssignment.objects.filter(allocation_run=run).values_list('status', flat=True)),
            [BedAssignment.Status.ACTIVE],
        )

    def test_stop_requested_while_queued_is_finalized_without_a_solve(self):
        cancelled = _queued_run(self.region, self.boss, status=AllocationRun.Status.CANCELLATION_REQUESTED)
        solver = _SolverRecorder()
        self._execute(cancelled, solver)
        self.assertEqual(cancelled.status, AllocationRun.Status.STOPPED)
        self.assertIsNotNone(cancelled.completed_at)
        self.assertEqual(cancelled.diagnostics, {})

        other = make_region('Jobs Exec Other')
        stop_and_save = _queued_run(other, self.boss, status=AllocationRun.Status.STOP_AND_SAVE_REQUESTED)
        self._execute(stop_and_save, solver)
        self.assertEqual(stop_and_save.status, AllocationRun.Status.STOPPED)
        self.assertEqual(stop_and_save.diagnostics['stop_reason'], 'no_feasible_solution_before_stop')
        self.assertEqual(stop_and_save.diagnostics['warnings'], [])
        self.assertEqual(solver.calls, [], 'a run stopped before it started never reaches the solver')

    def test_stop_signal_from_a_process_without_the_solver_is_the_database_status(self):
        """
        The web process that handles a stop request holds no solver (the
        solve runs in the worker process), so live_registry.request_stop_search
        finds nothing there; the status it writes is what the worker side
        acts on. The stand-in solver plays the worker side: it observes the
        status in the database, exactly as the solver's stop watcher does,
        and the run body finalizes the stop-and-save from that signal alone.
        """
        run = _queued_run(self.region, self.boss)
        live_registry._active_solvers.clear()
        fast_path_results = []
        original_fast_path = live_registry.request_stop_search

        def recording_fast_path(run_id):
            result = original_fast_path(run_id)
            fast_path_results.append(result)
            return result

        def web_process_requests_stop(kwargs):
            with patch.object(live_registry, 'request_stop_search', recording_fast_path):
                decision = request_run_stop(
                    run.id, AllocationRun.Status.STOP_AND_SAVE_REQUESTED, authorize=lambda _run: True,
                )
            self.assertEqual(decision.outcome, 'requested')
            observed = AllocationRun.objects.filter(pk=run.pk).values_list('status', flat=True).first()
            self.assertEqual(observed, AllocationRun.Status.STOP_AND_SAVE_REQUESTED)
            assign(self.students[0], self.room, run=run)
            return {**CANNED_RESULT, 'solver_status': 'FEASIBLE', 'optimality_proven': False,
                    'successful_assignments': 1, 'conflicts': 1}

        outcome = self._execute(run, _SolverRecorder(side_effect=web_process_requests_stop))
        self.assertEqual(fast_path_results, [False], 'the web process held no solver to interrupt')
        self.assertEqual(run.status, AllocationRun.Status.COMPLETED)
        self.assertIs(outcome.stopped_early_by_user, True)
        self.assertEqual(BedAssignment.objects.filter(allocation_run=run, status=BedAssignment.Status.ACTIVE).count(), 1)


# ---------------------------------------------------------------------------
# Recovery of runs whose worker is gone
# ---------------------------------------------------------------------------

class RecoveryTests(ExecutionFixture):
    def _recover(self, worker_id=WORKER_B):
        with inline_connections():
            return recover_stale_runs(worker_id, worker_settings=TEST_SETTINGS)

    def test_a_live_lease_is_never_recovered(self):
        run = _queued_run(self.region, self.boss)
        claim_next_run(WORKER_A, lease_seconds=60)
        self.assertEqual(self._recover(), [])
        self.assertEqual(jobs.stale_run_ids(), [])
        run.refresh_from_db()
        self.assertEqual(run.claimed_by, WORKER_A)

    def test_lost_before_the_solver_started_is_requeued_until_attempts_are_exhausted(self):
        run = _stale_run(self.region, self.boss, started=False, attempts=1)
        actions = self._recover()
        self.assertEqual([(a.run_id, a.previous_status, a.action) for a in actions],
                         [(run.id, AllocationRun.Status.RUNNING, 'requeued')])
        run.refresh_from_db()
        self.assertEqual((run.status, run.claimed_by, run.lease_expires_at, run.attempts),
                         (AllocationRun.Status.QUEUED, '', None, 1))
        self.assertIsNone(run.completed_at)

        exhausted = _stale_run(make_region('Jobs Exhausted'), self.boss, started=False, attempts=3)
        actions = self._recover()
        self.assertEqual([(a.run_id, a.action) for a in actions], [(exhausted.id, 'failed')])
        exhausted.refresh_from_db()
        self.assertEqual(exhausted.status, AllocationRun.Status.FAILED)
        self.assertEqual(exhausted.claimed_by, WORKER_B)
        self.assertEqual(exhausted.error_message, LOST_BEFORE_SOLVE_MESSAGE.format(attempts=3))
        self.assertIsNotNone(exhausted.completed_at)
        self.assertIsNone(exhausted.lease_expires_at)

    def test_lost_during_the_solve_without_persistence_fails_explicitly_and_never_resolves(self):
        run = _stale_run(self.region, self.boss, started=True, live_snapshot={'sequence': 2})
        actions = self._recover()
        self.assertEqual([(a.run_id, a.action) for a in actions], [(run.id, 'failed')])
        run.refresh_from_db()
        self.assertEqual(run.status, AllocationRun.Status.FAILED)
        self.assertEqual(run.error_message, LOST_DURING_SOLVE_MESSAGE)
        self.assertIsNone(run.live_snapshot)
        self.assertIsNone(run.lease_expires_at)
        self.assertEqual(run.claimed_by, WORKER_B, 'recovery takes the row over from the lost worker')
        self.assertEqual(actions[0].lost_worker, DEAD_WORKER)
        self.assertIsNone(claim_next_run(WORKER_B, lease_seconds=60), 'a failed run is never claimed again')

    def test_lost_after_persistence_fails_and_cancels_the_tagged_assignments(self):
        run = _stale_run(self.region, self.boss, started=True)
        assign(self.students[0], self.room, run=run)
        assign(self.students[1], self.room, run=run)
        actions = self._recover()
        self.assertEqual([(a.run_id, a.action) for a in actions], [(run.id, 'failed')])
        run.refresh_from_db()
        self.assertEqual(run.status, AllocationRun.Status.FAILED)
        self.assertEqual(run.error_message, LOST_AFTER_PERSISTENCE_MESSAGE.format(count=2))
        self.assertIsNotNone(run.completed_at)
        self.assertIsNone(run.lease_expires_at)
        self.assertEqual(run.claimed_by, WORKER_B, 'the recovering worker took the run over for the cleanup')
        rows = BedAssignment.objects.filter(allocation_run=run)
        self.assertEqual(set(rows.values_list('status', flat=True)), {BedAssignment.Status.CANCELLED})
        for student in self.students:
            student.refresh_from_db()
            self.assertIsNone(student.assigned_room_id)

    def test_pending_cancellation_of_a_lost_worker_is_honoured(self):
        run = _stale_run(self.region, self.boss, status=AllocationRun.Status.CANCELLATION_REQUESTED, started=True,
                         live_snapshot={'sequence': 1})
        assign(self.students[0], self.room, run=run)
        actions = self._recover()
        self.assertEqual([(a.run_id, a.action) for a in actions], [(run.id, 'cancelled')])
        run.refresh_from_db()
        self.assertEqual(run.status, AllocationRun.Status.STOPPED)
        self.assertEqual(run.error_message, '')
        self.assertIsNone(run.live_snapshot)
        self.assertEqual(
            list(BedAssignment.objects.filter(allocation_run=run).values_list('status', flat=True)),
            [BedAssignment.Status.CANCELLED],
        )

    def test_pending_stop_and_save_without_a_solution_is_stopped(self):
        run = _stale_run(self.region, self.boss, status=AllocationRun.Status.STOP_AND_SAVE_REQUESTED, started=True)
        actions = self._recover()
        self.assertEqual([(a.run_id, a.action) for a in actions], [(run.id, 'stopped')])
        run.refresh_from_db()
        self.assertEqual(run.status, AllocationRun.Status.STOPPED)
        self.assertEqual(run.diagnostics['stop_reason'], 'no_feasible_solution_before_stop')
        self.assertIsNone(run.lease_expires_at)
        self.assertEqual(run.claimed_by, WORKER_B)

    def test_requeued_run_is_claimed_again_and_executed_exactly_once(self):
        run = _stale_run(self.region, self.boss, status=AllocationRun.Status.QUEUED, started=False, attempts=1)
        self.assertEqual([a.action for a in self._recover()], ['requeued'])
        solver = _SolverRecorder()
        self._execute(run, solver, worker_id=WORKER_B)
        self.assertEqual(len(solver.calls), 1)
        self.assertEqual(run.status, AllocationRun.Status.COMPLETED)
        self.assertEqual((run.claimed_by, run.attempts), (WORKER_B, 2))
        self.assertEqual(self._recover(), [], 'a finished run is never recovered')

    def test_recovery_is_skipped_for_runs_another_worker_already_handled(self):
        run = _stale_run(self.region, self.boss, started=False)
        with inline_connections():
            first = recover_stale_runs(WORKER_A, worker_settings=TEST_SETTINGS)
            second = recover_stale_runs(WORKER_B, worker_settings=TEST_SETTINGS)
        self.assertEqual([a.run_id for a in first], [run.id])
        self.assertEqual(second, [])


# ---------------------------------------------------------------------------
# The worker loop and the management command
# ---------------------------------------------------------------------------

class WorkerLoopTests(ExecutionFixture):
    def _worker(self, **overrides):
        return AllocationWorker(worker_id=WORKER_A, worker_settings=TEST_SETTINGS, **overrides)

    def test_run_once_recovers_then_claims_and_executes_one_run(self):
        stale = _stale_run(make_region('Jobs Loop Stale'), self.boss, started=True)
        queued = _queued_run(self.region, self.boss)
        solver = _SolverRecorder()
        with inline_connections(), patch('allocation.solver.run_improved_ortools_allocation', new=solver):
            cycle = self._worker().run_once()
        self.assertEqual([a.run_id for a in cycle.recovered], [stale.id])
        self.assertEqual(cycle.claimed.run_id, queued.id)
        self.assertEqual(cycle.outcome.status, AllocationRun.Status.COMPLETED)
        self.assertEqual(cycle.error, '')
        self.assertEqual(len(solver.calls), 1)
        queued.refresh_from_db()
        self.assertEqual(queued.status, AllocationRun.Status.COMPLETED)

    def test_run_once_is_idle_when_nothing_is_queued(self):
        with inline_connections():
            cycle = self._worker().run_once()
        self.assertTrue(cycle.idle)
        self.assertIsNone(cycle.claimed)

    def test_a_job_exception_does_not_kill_the_loop_and_the_run_is_recovered_later(self):
        """
        Worker restart simulation: worker A claims a run and dies before the
        run body wrote anything (the exception escapes with the lease held).
        Nothing else may touch the run while the lease is valid; once it
        expires, the next worker re-queues it and executes it once.
        """
        run = _queued_run(self.region, self.boss)

        def crash(*args, **kwargs):
            raise RuntimeError('worker process died')

        with inline_connections(), patch('api.domains.allocation.worker.execute_claimed_run', side_effect=crash):
            cycle = self._worker().run_once()
        self.assertEqual(cycle.claimed.run_id, run.id)
        self.assertIn('RuntimeError: worker process died', cycle.error)
        run.refresh_from_db()
        self.assertEqual((run.status, run.claimed_by), (AllocationRun.Status.QUEUED, WORKER_A))
        self.assertIsNotNone(run.lease_expires_at, 'the lease is kept so recovery, not a second claim, decides')

        solver = _SolverRecorder()
        with inline_connections(), patch('allocation.solver.run_improved_ortools_allocation', new=solver):
            untouched = AllocationWorker(worker_id=WORKER_B, worker_settings=TEST_SETTINGS).run_once()
        self.assertIsNone(untouched.claimed, 'a run with a live lease is not claimable')
        self.assertEqual(solver.calls, [])

        AllocationRun.objects.filter(pk=run.pk).update(lease_expires_at=timezone.now() - timedelta(seconds=1))
        with inline_connections(), patch('allocation.solver.run_improved_ortools_allocation', new=solver):
            recovered = AllocationWorker(worker_id=WORKER_B, worker_settings=TEST_SETTINGS).run_once()
        self.assertEqual([a.action for a in recovered.recovered], ['requeued'])
        self.assertEqual(recovered.claimed.run_id, run.id)
        self.assertEqual(len(solver.calls), 1)
        run.refresh_from_db()
        self.assertEqual((run.status, run.claimed_by, run.attempts), (AllocationRun.Status.COMPLETED, WORKER_B, 2))

    def test_recovery_errors_are_reported_without_stopping_the_cycle(self):
        queued = _queued_run(self.region, self.boss)
        solver = _SolverRecorder()
        with inline_connections(), patch('allocation.solver.run_improved_ortools_allocation', new=solver), \
                patch('api.domains.allocation.worker.recover_stale_runs', side_effect=RuntimeError('db hiccup')):
            cycle = self._worker().run_once()
        self.assertIn('recovery: RuntimeError: db hiccup', cycle.error)
        self.assertEqual(cycle.claimed.run_id, queued.id)
        self.assertEqual(cycle.outcome.status, AllocationRun.Status.COMPLETED)

    def test_run_forever_finishes_the_current_run_and_stops_on_request(self):
        run = _queued_run(self.region, self.boss)
        worker = self._worker()

        def stop_mid_solve(kwargs):
            worker.request_stop()

        solver = _SolverRecorder(side_effect=stop_mid_solve)
        with inline_connections(), patch('allocation.solver.run_improved_ortools_allocation', new=solver):
            cycles = worker.run_forever()
        self.assertEqual(cycles, 1)
        run.refresh_from_db()
        self.assertEqual(run.status, AllocationRun.Status.COMPLETED)

    def test_run_forever_waits_the_poll_interval_when_idle(self):
        worker = self._worker()
        waits = []
        original_wait = worker.stop_event.wait

        def counting_wait(timeout=None):
            waits.append(timeout)
            if len(waits) >= 3:
                worker.request_stop()
            return original_wait(timeout)

        with inline_connections(), patch.object(worker.stop_event, 'wait', counting_wait):
            cycles = worker.run_forever()
        self.assertEqual(cycles, 3)
        self.assertEqual(waits, [TEST_SETTINGS.poll_interval_seconds] * 3)

    def test_management_command_once_executes_a_queued_run(self):
        run = _queued_run(self.region, self.boss)
        solver = _SolverRecorder()
        out = io.StringIO()
        with inline_connections(), patch('allocation.solver.run_improved_ortools_allocation', new=solver):
            call_command(
                'allocation_worker', '--once', '--heartbeat-seconds', '0', '--lease-seconds', '60',
                '--worker-id', 'command-test', stdout=out,
            )
        run.refresh_from_db()
        self.assertEqual((run.status, run.claimed_by), (AllocationRun.Status.COMPLETED, 'command-test'))
        self.assertIn(f'claimed={run.id} status=completed', out.getvalue())

    def test_management_command_rejects_invalid_settings(self):
        with self.assertRaises(CommandError):
            call_command('allocation_worker', '--once', '--heartbeat-seconds', '500', '--lease-seconds', '10')
        with self.assertRaises(CommandError):
            call_command('allocation_worker', '--once', '--log-level', 'LOUD')


# ---------------------------------------------------------------------------
# The web process: queue, read, stop - never execute
# ---------------------------------------------------------------------------

class WebProcessContractTests(TestCase):
    def setUp(self):
        self.region = make_region('Jobs Web Region')
        self.boss = make_boss(self.region)
        make_full_stack(self.region)
        self.client = APIClient()
        self.client.force_authenticate(user=self.boss)

    def tearDown(self):
        live_registry._snapshots.clear()
        live_registry._active_solvers.clear()

    def test_start_endpoint_queues_a_durable_run_and_launches_nothing(self):
        with patch('threading.Thread') as thread, \
                patch('api.domains.allocation.orchestration.execute_allocation_run') as execute:
            response = self.client.post('/api/allocation/start/', {
                'region': self.region.id, 'max_solver_seconds': 45,
                'include_assigned': True, 'allocation_scope': 'new_transfer_only',
                'constraints': {'sameReligion': {'enabled': False}},
            }, format='json')
        self.assertEqual(response.status_code, 202, response.data)
        thread.assert_not_called()
        execute.assert_not_called()
        run = AllocationRun.objects.get(pk=response.data['run_id'])
        self.assertEqual(run.status, AllocationRun.Status.QUEUED)
        self.assertEqual(run.job_parameters, {
            'constraints_config': normalize_allocation_constraints({'sameReligion': {'enabled': False}}),
            'include_assigned': True,
            'allocation_scope': 'new_transfer_only',
            'max_seconds': 45.0,
        })
        self.assertEqual((run.claimed_by, run.lease_expires_at, run.attempts), ('', None, 0))
        self.assertEqual(run.max_search_seconds, 45)
        # The response contract is unchanged: no lease field leaks into it.
        self.assertNotIn('job_parameters', response.data['run'])
        self.assertNotIn('claimed_by', response.data['run'])

    def test_region_duplicate_run_protection_still_holds_for_queued_and_claimed_runs(self):
        first = self.client.post('/api/allocation/start/', {'region': self.region.id}, format='json')
        self.assertEqual(first.status_code, 202)
        second = self.client.post('/api/allocation/start/', {'region': self.region.id}, format='json')
        self.assertEqual(second.status_code, 409)
        self.assertEqual(second.data['run_id'], first.data['run_id'])
        claim_next_run(WORKER_A, lease_seconds=60)
        third = self.client.post('/api/allocation/start/', {'region': self.region.id}, format='json')
        self.assertEqual(third.status_code, 409)
        self.assertEqual(AllocationRun.objects.filter(region=self.region).count(), 1)

    def test_preview_serves_only_the_persisted_snapshot(self):
        run = make_run(self.region, self.boss, status=AllocationRun.Status.RUNNING, completed=False)
        # A snapshot that exists only in this process's registry (the way a
        # solving process holds it) is not what another process can see.
        live_registry.set(run.id, {'sequence': 9, 'assigned_count': 9})
        response = self.client.get(f'/api/allocation/runs/{run.id}/preview/')
        self.assertEqual(response.data, {'available': False, 'snapshot': None})

        AllocationRun.objects.filter(pk=run.pk).update(live_snapshot={'sequence': 2, 'assigned_count': 1})
        response = self.client.get(f'/api/allocation/runs/{run.id}/preview/')
        self.assertEqual(response.data, {'available': True, 'snapshot': {'sequence': 2, 'assigned_count': 1}})

    def test_status_and_stop_requests_depend_only_on_the_database(self):
        start = self.client.post('/api/allocation/start/', {'region': self.region.id}, format='json')
        run_id = start.data['run_id']
        claim_next_run(WORKER_A, lease_seconds=60)
        AllocationRun.objects.filter(pk=run_id).update(status=AllocationRun.Status.RUNNING)

        # Another replica: a fresh client, an empty registry.
        other_replica = APIClient()
        other_replica.force_authenticate(user=self.boss)
        detail = other_replica.get(f'/api/allocation/runs/{run_id}/')
        self.assertEqual((detail.status_code, detail.data['run']['status']), (200, 'running'))

        with patch.object(live_registry, 'request_stop_search', wraps=live_registry.request_stop_search) as fast_path:
            stop = other_replica.post(f'/api/allocation/runs/{run_id}/stop/')
        self.assertEqual(stop.status_code, 200)
        fast_path.assert_called_once_with(run_id)
        self.assertEqual(
            AllocationRun.objects.filter(pk=run_id).values_list('status', flat=True).first(),
            AllocationRun.Status.CANCELLATION_REQUESTED,
            'the database status is the authoritative stop signal',
        )


# ---------------------------------------------------------------------------
# Real connections and threads: process boundaries
# ---------------------------------------------------------------------------

class WorkerProcessBoundaryTests(TransactionTestCase):
    def setUp(self):
        self.region = make_region('Jobs Boundary Region')
        self.other = make_region('Jobs Boundary Other')
        self.boss = make_boss(self.region)

    def tearDown(self):
        live_registry._snapshots.clear()
        live_registry._active_solvers.clear()

    def _claim_in_threads(self, worker_ids):
        barrier = threading.Barrier(len(worker_ids))
        results = {}

        def claim(worker_id):
            try:
                barrier.wait(timeout=10)
                results[worker_id] = claim_next_run(worker_id, lease_seconds=60)
            finally:
                connection.close()

        threads = [threading.Thread(target=claim, args=(worker_id,)) for worker_id in worker_ids]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)
        return results

    def test_concurrent_workers_never_claim_the_same_run(self):
        run = _queued_run(self.region, self.boss)
        results = self._claim_in_threads([f'host:{n}:{n:08d}' for n in range(4)])
        claimed = [claimed for claimed in results.values() if claimed is not None]
        self.assertEqual(len(claimed), 1)
        self.assertEqual(claimed[0].run_id, run.id)
        run.refresh_from_db()
        self.assertEqual(run.attempts, 1)
        self.assertEqual(run.claimed_by, next(w for w, c in results.items() if c is not None))

    def test_concurrent_workers_claim_different_runs(self):
        first = _queued_run(self.region, self.boss)
        second = _queued_run(self.other, self.boss)
        results = self._claim_in_threads([WORKER_A, WORKER_B])
        claimed_ids = sorted(claimed.run_id for claimed in results.values() if claimed is not None)
        self.assertEqual(claimed_ids, sorted([first.id, second.id]))

    def test_heartbeat_thread_renews_the_lease_and_notices_losing_it(self):
        run = _queued_run(self.region, self.boss)
        claimed = claim_next_run(WORKER_A, lease_seconds=60)
        fence = claimed.fence(WORKER_A)
        heartbeat = LeaseHeartbeat(fence, interval_seconds=0.05, lease_seconds=60)
        heartbeat.start()
        deadline = time.monotonic() + 5
        while heartbeat.renewals < 2 and time.monotonic() < deadline:
            time.sleep(0.02)
        heartbeat.stop()
        self.assertGreaterEqual(heartbeat.renewals, 2)
        self.assertFalse(heartbeat.lost)
        run.refresh_from_db()
        self.assertGreater(run.lease_expires_at, claimed.lease_expires_at)

        # Another worker recovered the run (its claim replaced ours): the
        # next renewal fails and the heartbeat reports the lost lease.
        AllocationRun.objects.filter(pk=run.pk).update(claimed_by=WORKER_B)
        heartbeat = LeaseHeartbeat(fence, interval_seconds=0.05, lease_seconds=60)
        heartbeat.start()
        deadline = time.monotonic() + 5
        while not heartbeat.lost and time.monotonic() < deadline:
            time.sleep(0.02)
        heartbeat.stop()
        self.assertTrue(heartbeat.lost)
        self.assertTrue(fence.lost, 'the loss is observable to the execution through its fence')
        self.assertFalse(heartbeat.is_alive())

    def test_stop_requested_by_the_web_process_reaches_the_solver_watcher_in_the_worker(self):
        """
        Cross-process stop: the web side has no solver registered, so its
        fast path does nothing and only the database status changes; the
        solver's stop watcher - running in the worker process, here a
        separate thread with its own connection - observes that status and
        interrupts the search.
        """
        run = _queued_run(self.region, self.boss)
        claim_next_run(WORKER_A, lease_seconds=60)
        AllocationRun.objects.filter(pk=run.pk).update(status=AllocationRun.Status.RUNNING)

        class FakeSolver:
            def __init__(self):
                self.stopped = threading.Event()

            def StopSearch(self):
                self.stopped.set()

        worker_solver = FakeSolver()
        watcher_done = threading.Event()
        watcher = threading.Thread(
            target=_run_stop_watcher, args=(run.id, worker_solver, watcher_done), daemon=True,
        )
        watcher.start()
        self.addCleanup(watcher_done.set)
        time.sleep(0.2)

        live_registry._active_solvers.clear()
        with patch.object(live_registry, 'request_stop_search', wraps=live_registry.request_stop_search) as fast_path:
            decision = request_run_stop(
                run.id, AllocationRun.Status.CANCELLATION_REQUESTED, authorize=lambda _run: True,
            )
        self.assertEqual(decision.outcome, 'requested')
        fast_path.assert_called_once_with(run.id)
        self.assertFalse(
            any(live_registry._active_solvers), 'the web process never held the worker\'s solver',
        )

        self.assertTrue(
            worker_solver.stopped.wait(timeout=_STOP_WATCHER_POLL_INTERVAL_SECONDS + 5.0),
            'the watcher in the worker process must act on the database status',
        )
        watcher.join(timeout=5)
        self.assertFalse(watcher.is_alive())


# ---------------------------------------------------------------------------
# Claim fencing: a stale execution can neither persist nor finalize
# ---------------------------------------------------------------------------

def _expire_lease(run_id):
    AllocationRun.objects.filter(pk=run_id).update(lease_expires_at=timezone.now() - timedelta(seconds=1))


class ClaimFenceTests(ExecutionFixture):
    def test_fence_matches_only_the_current_claim_generation(self):
        run = _queued_run(self.region, self.boss)
        claimed = claim_next_run(WORKER_A, lease_seconds=60)
        fence = claimed.fence(WORKER_A)
        self.assertEqual((fence.run_id, fence.worker_id, fence.generation), (run.id, WORKER_A, 1))
        fence.check()
        self.assertEqual(fence.update(status=AllocationRun.Status.RUNNING), 1)
        self.assertFalse(fence.lost)

        # The run is re-queued (recovery) and claimed by another worker: a
        # new generation. The old fence is refused everywhere, and once it
        # has seen the refusal it refuses without touching the database.
        _expire_lease(run.id)
        with inline_connections():
            recover_stale_runs(WORKER_B, worker_settings=TEST_SETTINGS)
        new_claim = claim_next_run(WORKER_B, lease_seconds=60)
        self.assertEqual((new_claim.run_id, new_claim.attempt), (run.id, 2))
        with self.assertRaises(ClaimLost):
            fence.update(status=AllocationRun.Status.COMPLETED)
        self.assertTrue(fence.lost)
        with self.assertNumQueries(0), self.assertRaises(ClaimLost):
            fence.check()
        with self.assertNumQueries(0), self.assertRaises(ClaimLost):
            fence.persistence_guard()
        run.refresh_from_db()
        self.assertEqual((run.status, run.claimed_by, run.attempts), (AllocationRun.Status.QUEUED, WORKER_B, 2))
        self.assertTrue(new_claim.fence(WORKER_B).check() is None)

    def test_fence_refuses_after_a_recovery_takeover_even_with_the_same_generation(self):
        run = _queued_run(self.region, self.boss)
        claimed = claim_next_run(WORKER_A, lease_seconds=60)
        fence = claimed.fence(WORKER_A)
        AllocationRun.objects.filter(pk=run.pk).update(
            status=AllocationRun.Status.RUNNING, search_started_at=timezone.now(),
        )
        _expire_lease(run.id)
        with inline_connections():
            actions = recover_stale_runs(WORKER_B, worker_settings=TEST_SETTINGS)
        self.assertEqual([(a.action, a.lost_worker) for a in actions], [('failed', WORKER_A)])
        run.refresh_from_db()
        self.assertEqual((run.status, run.claimed_by, run.attempts), (AllocationRun.Status.FAILED, WORKER_B, 1))
        with self.assertRaises(ClaimLost):
            fence.update(status=AllocationRun.Status.COMPLETED, completed_at=timezone.now())
        self.assertFalse(renew_lease(run.id, WORKER_A, 1, lease_seconds=60))
        self.assertFalse(release_lease(run.id, WORKER_A, 1))
        run.refresh_from_db()
        self.assertEqual(run.status, AllocationRun.Status.FAILED, 'the recovered state is never overwritten')


class StaleWorkerFencingTests(ExecutionFixture):
    """The three crash windows, with worker A resuming after worker B's recovery."""

    def _run_body_as(self, claimed, worker_id, solver, *, fence=None):
        fence = fence or claimed.fence(worker_id)
        with inline_connections(), patch('allocation.solver.run_improved_ortools_allocation', new=solver):
            outcome = execute_claimed_run(claimed, worker_id, worker_settings=TEST_SETTINGS, fence=fence)
        return outcome, fence

    def test_worker_refused_before_the_solver_when_its_run_was_requeued_and_reclaimed(self):
        run = _queued_run(self.region, self.boss)
        # 1. A claims. 2. A's lease expires before the solver started.
        claimed_a = claim_next_run(WORKER_A, lease_seconds=60)
        _expire_lease(run.id)
        # 3. Recovery re-queues the run.
        with inline_connections():
            actions = recover_stale_runs(WORKER_B, worker_settings=TEST_SETTINGS)
        self.assertEqual([a.action for a in actions], ['requeued'])
        # 4. B claims the new generation.
        claimed_b = claim_next_run(WORKER_B, lease_seconds=60)
        self.assertEqual((claimed_b.run_id, claimed_b.attempt), (run.id, 2))
        # 5. A resumes with its stale claim. 6. A is refused before any solve.
        solver = _SolverRecorder()
        outcome, fence_a = self._run_body_as(claimed_a, WORKER_A, solver)
        self.assertTrue(outcome.fenced)
        self.assertTrue(fence_a.lost)
        self.assertEqual(solver.calls, [], 'the stale worker never reaches the solver')
        run.refresh_from_db()
        self.assertEqual((run.status, run.claimed_by, run.attempts), (AllocationRun.Status.QUEUED, WORKER_B, 2))
        self.assertIsNotNone(run.lease_expires_at, "B's lease is untouched by the stale worker")

        # B executes its generation normally.
        outcome_b, _ = self._run_body_as(claimed_b, WORKER_B, _SolverRecorder())
        self.assertFalse(outcome_b.fenced)
        run.refresh_from_db()
        self.assertEqual((run.status, run.claimed_by, run.attempts), (AllocationRun.Status.COMPLETED, WORKER_B, 2))

    def test_worker_cannot_persist_after_losing_its_lease_during_the_solve(self):
        run = _queued_run(self.region, self.boss)
        claimed_a = claim_next_run(WORKER_A, lease_seconds=60)
        recovery_actions = []

        def lease_expires_and_is_recovered_mid_solve(kwargs):
            # 1. A began the solve (the solver stamps search_started_at).
            AllocationRun.objects.filter(pk=run.pk).update(search_started_at=timezone.now())
            # 2. A loses the lease. 3. Recovery handles the run (window C).
            _expire_lease(run.id)
            recovery_actions.extend(recover_stale_runs(WORKER_B, worker_settings=TEST_SETTINGS))
            # 4. A's solver now returns and reaches its persistence transaction.

        def persist(kwargs):
            raise AssertionError('persistence must not be reached by the stale worker')

        solver = _SolverRecorder(side_effect=lease_expires_and_is_recovered_mid_solve, persist=persist)
        outcome, fence_a = self._run_body_as(claimed_a, WORKER_A, solver)
        self.assertEqual([(a.action, a.lost_worker) for a in recovery_actions], [('failed', WORKER_A)])
        self.assertTrue(outcome.fenced)
        self.assertEqual(len(solver.calls), 1)
        self.assertTrue(solver.guard_raised, 'the persistence guard refused inside the solver')
        # 5. Nothing was persisted and the recovered state stands.
        self.assertEqual(BedAssignment.objects.filter(allocation_run=run).count(), 0)
        run.refresh_from_db()
        self.assertEqual(run.status, AllocationRun.Status.FAILED)
        self.assertEqual(run.error_message, LOST_DURING_SOLVE_MESSAGE)
        self.assertEqual(run.claimed_by, WORKER_B)
        self.assertEqual(outcome.status, AllocationRun.Status.FAILED)

    def test_worker_cannot_overwrite_the_recovered_state_after_persisting(self):
        run = _queued_run(self.region, self.boss)
        claimed_a = claim_next_run(WORKER_A, lease_seconds=60)
        recovery_actions = []

        def persist(kwargs):
            # 1. A persists a tagged assignment (the guard passed: A still owned the run).
            AllocationRun.objects.filter(pk=run.pk).update(search_started_at=timezone.now())
            assign(self.students[0], self.room, run=run)
            # 2. A loses ownership before the final run-state update.
            _expire_lease(run.id)
            # 3. Recovery applies the window-D policy: FAILED, rows cancelled.
            recovery_actions.extend(recover_stale_runs(WORKER_B, worker_settings=TEST_SETTINGS))

        solver = _SolverRecorder(persist=persist)
        # 4. A resumes finalization (diagnostics, then COMPLETED).
        outcome, fence_a = self._run_body_as(claimed_a, WORKER_A, solver)
        self.assertEqual([(a.action, a.lost_worker) for a in recovery_actions], [('failed', WORKER_A)])
        self.assertTrue(outcome.fenced)
        # 5. A could not overwrite the recovered state.
        run.refresh_from_db()
        self.assertEqual(run.status, AllocationRun.Status.FAILED)
        self.assertEqual(run.error_message, LOST_AFTER_PERSISTENCE_MESSAGE.format(count=1))
        self.assertEqual(run.claimed_by, WORKER_B)
        self.assertNotIn('solver_status', run.diagnostics, "A's diagnostics write was refused")
        self.assertEqual(
            list(BedAssignment.objects.filter(allocation_run=run).values_list('status', flat=True)),
            [BedAssignment.Status.CANCELLED],
        )
        self.students[0].refresh_from_db()
        self.assertIsNone(self.students[0].assigned_room_id)

    def test_stale_cancellation_cleanup_is_rolled_back_by_the_fence(self):
        run = _queued_run(self.region, self.boss)
        claimed_a = claim_next_run(WORKER_A, lease_seconds=60)

        def persist(kwargs):
            AllocationRun.objects.filter(pk=run.pk).update(search_started_at=timezone.now())
            assign(self.students[0], self.room, run=run)
            # The operator cancels; the run is then recovered by B (E1:
            # cleanup -> STOPPED, B owns the row) before A reaches its own
            # cancel branch.
            AllocationRun.objects.filter(pk=run.pk).update(status=AllocationRun.Status.CANCELLATION_REQUESTED)
            _expire_lease(run.id)
            actions = recover_stale_runs(WORKER_B, worker_settings=TEST_SETTINGS)
            self.assertEqual([a.action for a in actions], ['cancelled'])
            # B's finished run is what A must not touch: give it a marker.
            AllocationRun.objects.filter(pk=run.pk).update(completed_at=timezone.now() - timedelta(days=1))

        outcome, _ = self._run_body_as(claimed_a, WORKER_A, _SolverRecorder(persist=persist))
        self.assertTrue(outcome.fenced)
        run.refresh_from_db()
        self.assertEqual((run.status, run.claimed_by), (AllocationRun.Status.STOPPED, WORKER_B))
        self.assertLess(run.completed_at, timezone.now() - timedelta(hours=23), "B's completion time stands")

    def test_heartbeat_loss_is_observed_and_stops_the_search_and_the_execution(self):
        run = _queued_run(self.region, self.boss)
        claimed_a = claim_next_run(WORKER_A, lease_seconds=60)
        fence = claimed_a.fence(WORKER_A)
        heartbeat = LeaseHeartbeat(fence, interval_seconds=60, lease_seconds=60)
        self.assertTrue(heartbeat.renew_once())
        self.assertEqual(heartbeat.renewals, 1)

        # Another worker took the run over; the next renewal matches no row.
        solver_in_this_process = MagicMock()
        live_registry.register_solver(run.id, solver_in_this_process)
        self.addCleanup(live_registry.unregister_solver, run.id)
        AllocationRun.objects.filter(pk=run.pk).update(claimed_by=WORKER_B)
        self.assertFalse(heartbeat.renew_once())
        self.assertTrue(fence.lost)
        self.assertTrue(heartbeat.lost)
        solver_in_this_process.StopSearch.assert_called_once_with()
        self.assertFalse(heartbeat.renew_once(), 'a lost fence is never renewed again')

        # The execution observes the loss: it is refused without a single
        # database write, before the solver is even called.
        solver = _SolverRecorder()
        with inline_connections(), patch('allocation.solver.run_improved_ortools_allocation', new=solver):
            outcome = execute_claimed_run(
                claimed_a, WORKER_A, worker_settings=TEST_SETTINGS, fence=fence, heartbeat=heartbeat,
            )
        self.assertTrue(outcome.fenced)
        self.assertTrue(outcome.lease_lost)
        self.assertEqual(solver.calls, [])
        run.refresh_from_db()
        self.assertEqual((run.status, run.claimed_by), (AllocationRun.Status.QUEUED, WORKER_B))

    def test_unfenced_callers_hand_the_solver_the_unchanged_six_key_call(self):
        run = _queued_run(self.region, self.boss)
        solver = _SolverRecorder()
        with inline_connections(), patch('allocation.solver.run_improved_ortools_allocation', new=solver):
            execute_allocation_run(
                allocation_run_id=run.id, region_id=self.region.id,
                constraints_config=normalize_allocation_constraints(None),
                include_assigned=False, allocation_scope=None, max_seconds=30.0,
            )
        self.assertEqual(
            list(solver.calls[0]['kwargs']),
            ['students', 'rooms', 'constraints_config', 'allocation_run_id', 'max_seconds', 'enable_group_capacity_cuts'],
        )
        self.assertFalse(solver.guard_called)
        run.refresh_from_db()
        self.assertEqual(run.status, AllocationRun.Status.COMPLETED)


class SolverPersistenceGuardTests(TransactionTestCase):
    """The real solver invokes the guard inside its persistence transaction and aborts on refusal."""

    def setUp(self):
        self.region = make_region('Jobs Guard Region')
        self.boss = make_boss(self.region)
        self.dorm, _b, _a, self.room = make_full_stack(self.region)
        self.students = [make_student(self.dorm, 'GUARD-1'), make_student(self.dorm, 'GUARD-2')]
        patcher = patch('allocation.solver.close_old_connections')
        patcher.start()
        self.addCleanup(patcher.stop)

    def tearDown(self):
        live_registry._snapshots.clear()
        live_registry._active_solvers.clear()

    def _solve(self, run, guard, ownership_filter=None):
        from allocation.solver import run_improved_ortools_allocation
        from api.domains.allocation.queries import solver_rooms_for_region, solver_students_for_region

        _base, students = solver_students_for_region(self.region)
        return run_improved_ortools_allocation(
            students, solver_rooms_for_region(self.region), normalize_allocation_constraints(None),
            allocation_run_id=run.id, max_seconds=10, enable_group_capacity_cuts=True,
            persistence_guard=guard, run_ownership_filter=ownership_filter,
        )

    def test_guard_runs_inside_the_persistence_transaction_and_a_refusal_persists_nothing(self):
        run = make_run(self.region, self.boss, status=AllocationRun.Status.RUNNING, completed=False,
                       job_parameters=_parameters(), claimed_by=WORKER_A, attempts=1)
        observed = {}

        def refusing_guard():
            observed['in_atomic_block'] = connection.in_atomic_block
            observed['beds_locked_yet'] = False
            raise ClaimLost('stale')

        with self.assertRaises(ClaimLost):
            self._solve(run, refusing_guard)
        self.assertIs(observed['in_atomic_block'], True)
        self.assertEqual(BedAssignment.objects.filter(allocation_run=run).count(), 0)
        for student in self.students:
            student.refresh_from_db()
            self.assertIsNone(student.assigned_room_id)

    def test_fence_guard_locks_the_run_row_and_lets_the_owner_persist(self):
        run = make_run(self.region, self.boss, status=AllocationRun.Status.RUNNING, completed=False,
                       job_parameters=_parameters(), claimed_by=WORKER_A, attempts=1)
        fence = ClaimFence(run_id=run.id, worker_id=WORKER_A, generation=1)
        calls = []

        def guard():
            calls.append(connection.in_atomic_block)
            fence.persistence_guard()

        result = self._solve(run, guard, fence.ownership_filter())
        self.assertEqual(calls, [True])
        self.assertIn(result['solver_status'], ('OPTIMAL', 'FEASIBLE'))
        self.assertTrue(result['solution_persisted'])
        self.assertEqual(BedAssignment.objects.filter(allocation_run=run, status=BedAssignment.Status.ACTIVE).count(), 2)
        # The owner's own solver writes still land under the ownership filter.
        run.refresh_from_db()
        self.assertIsNotNone(run.search_started_at)
        self.assertIsNotNone(run.live_snapshot)
        self.assertEqual(run.live_snapshot['assigned_count'], 2)

        # The same solve for a generation that is no longer the row's persists nothing.
        AllocationRun.objects.filter(pk=run.pk).update(claimed_by=WORKER_B, attempts=2)
        BedAssignment.objects.filter(allocation_run=run).update(status=BedAssignment.Status.CANCELLED)
        Student.objects.filter(pk__in=[s.pk for s in self.students]).update(assigned_room=None)
        with self.assertRaises(ClaimLost):
            self._solve(run, fence.persistence_guard)
        self.assertEqual(BedAssignment.objects.filter(allocation_run=run, status=BedAssignment.Status.ACTIVE).count(), 0)


class StaleSolverRunRowFencingTests(TransactionTestCase):
    """
    The solver writes to the run row itself - the search-start stamp and the
    live-snapshot mirror (watcher ticks and the final flush after Solve()).
    A worker whose run was re-queued and re-claimed while it was inside the
    solver (window B) must not touch the new owner's row through those
    writes either. End to end through the worker path with real OR-Tools.
    """

    def setUp(self):
        self.region = make_region('Jobs Stale Solver Region')
        self.boss = make_boss(self.region)
        self.dorm, _b, _a, self.room = make_full_stack(self.region)
        self.students = [make_student(self.dorm, 'STALE-1'), make_student(self.dorm, 'STALE-2')]
        patcher = patch('allocation.solver.close_old_connections')
        patcher.start()
        self.addCleanup(patcher.stop)

    def tearDown(self):
        live_registry._snapshots.clear()
        live_registry._active_solvers.clear()

    def test_stale_solver_cannot_touch_the_search_stamp_or_live_snapshot_of_the_new_owner(self):
        import allocation.solver as solver_module

        run = _queued_run(self.region, self.boss, job_parameters=_parameters(max_seconds=10.0))
        claimed_a = claim_next_run(WORKER_A, lease_seconds=60)
        b_search_started_at = timezone.now() - timedelta(minutes=3)
        b_snapshot = {'sequence': 99, 'assigned_count': 0, 'owner': 'worker-b'}
        original_prepare_inventory = solver_module._prepare_inventory
        takeover = {}

        def ownership_moves_while_a_is_inside_the_solver(rooms):
            # A passed its pre-solver check and is building the model when
            # its lease expires: recovery re-queues the run (the solver had
            # not stamped the search start yet) and B claims generation 2
            # and starts its own search.
            if not takeover:
                _expire_lease(run.id)
                takeover['actions'] = recover_stale_runs(WORKER_B, worker_settings=TEST_SETTINGS)
                takeover['claim'] = claim_next_run(WORKER_B, lease_seconds=60)
                AllocationRun.objects.filter(pk=run.pk).update(
                    status=AllocationRun.Status.RUNNING,
                    search_started_at=b_search_started_at,
                    live_snapshot=b_snapshot,
                )
            return original_prepare_inventory(rooms)

        with patch.object(solver_module, '_prepare_inventory', ownership_moves_while_a_is_inside_the_solver):
            outcome = execute_claimed_run(claimed_a, WORKER_A, worker_settings=TEST_SETTINGS)

        self.assertEqual([a.action for a in takeover['actions']], ['requeued'])
        self.assertEqual(takeover['claim'].attempt, 2)
        self.assertTrue(outcome.fenced)
        run.refresh_from_db()
        self.assertEqual((run.status, run.claimed_by, run.attempts), (AllocationRun.Status.RUNNING, WORKER_B, 2))
        self.assertEqual(run.search_started_at, b_search_started_at, "the stale search-start stamp must not land")
        self.assertEqual(run.live_snapshot, b_snapshot, "the stale live-snapshot mirror must not land")
        self.assertEqual(BedAssignment.objects.filter(allocation_run=run).count(), 0)


class StopWatcherOwnershipTests(TransactionTestCase):
    """The solver's stop watcher acts on the claim generation it is given (real thread and connection)."""

    class _PollEvent:
        """Lets the watcher run exactly ``polls`` ticks, then ends it - no wall-clock waits."""

        def __init__(self, polls=1):
            self.polls = polls
            self.calls = 0

        def wait(self, timeout=None):
            self.calls += 1
            return self.calls > self.polls

    class _RecordingMirror:
        def __init__(self):
            self.calls = 0

        def mirror(self, *args, **kwargs):
            self.calls += 1
            return False

    def setUp(self):
        self.region = make_region('Jobs Watcher Region')
        self.boss = make_boss(self.region)

    def tearDown(self):
        live_registry._snapshots.clear()
        live_registry._active_solvers.clear()

    def _watch(self, run, ownership_filter, mirror_state):
        solver = MagicMock()
        watcher = threading.Thread(
            target=_run_stop_watcher,
            args=(run.id, solver, self._PollEvent(polls=1), mirror_state),
            kwargs={'ownership_filter': ownership_filter},
            daemon=True,
        )
        watcher.start()
        watcher.join(timeout=10)
        self.assertFalse(watcher.is_alive())
        return solver

    def test_a_watcher_whose_generation_was_superseded_stops_the_search_without_mirroring(self):
        run = make_run(self.region, self.boss, status=AllocationRun.Status.RUNNING, completed=False,
                       job_parameters=_parameters(), claimed_by=WORKER_B, attempts=2)
        mirror = self._RecordingMirror()
        solver = self._watch(run, {'claimed_by': WORKER_A, 'attempts': 1}, mirror)
        solver.StopSearch.assert_called_once_with()
        self.assertEqual(mirror.calls, 0)

    def test_the_owning_generation_keeps_searching_and_mirrors_its_snapshot(self):
        from allocation.solver import _SnapshotMirrorState

        run = make_run(self.region, self.boss, status=AllocationRun.Status.RUNNING, completed=False,
                       job_parameters=_parameters(), claimed_by=WORKER_A, attempts=1)
        ownership = {'claimed_by': WORKER_A, 'attempts': 1}
        live_registry.set(run.id, {'sequence': 5, 'assigned_count': 3})
        solver = self._watch(run, ownership, _SnapshotMirrorState(ownership_filter=ownership))
        solver.StopSearch.assert_not_called()
        run.refresh_from_db()
        self.assertEqual(run.live_snapshot, {'sequence': 5, 'assigned_count': 3})

    def test_a_superseded_mirror_never_writes_the_new_owners_row(self):
        from allocation.solver import _SnapshotMirrorState

        run = make_run(self.region, self.boss, status=AllocationRun.Status.RUNNING, completed=False,
                       job_parameters=_parameters(), claimed_by=WORKER_B, attempts=2,
                       live_snapshot={'sequence': 9, 'owner': 'worker-b'})
        stale_mirror = _SnapshotMirrorState(ownership_filter={'claimed_by': WORKER_A, 'attempts': 1})
        self.assertFalse(stale_mirror.mirror(run.id, {'sequence': 10, 'owner': 'worker-a'}, lock_wait_seconds=1.0))
        run.refresh_from_db()
        self.assertEqual(run.live_snapshot, {'sequence': 9, 'owner': 'worker-b'})
        # Without a filter (every non-worker caller) the mirror behaves exactly as before.
        self.assertTrue(_SnapshotMirrorState().mirror(run.id, {'sequence': 11}, lock_wait_seconds=1.0))
        run.refresh_from_db()
        self.assertEqual(run.live_snapshot, {'sequence': 11})


class RecoveryConvergenceTests(ExecutionFixture):
    """A recovering worker that dies part-way through its own recovery leaves a run the next recovery finishes."""

    def test_recoverer_lost_before_its_cleanup_leaves_a_run_the_next_recovery_converges(self):
        run = _stale_run(self.region, self.boss, started=True)
        assign(self.students[0], self.room, run=run)

        with inline_connections(), \
                patch('api.domains.allocation.jobs._cleanup_run_assignments', side_effect=RuntimeError('recoverer died')), \
                self.assertRaises(RuntimeError):
            recover_stale_runs(WORKER_B, worker_settings=TEST_SETTINGS)

        # B took the run over (owner, lease, outcome message) but never
        # wrote a terminal status: the run is still in progress and leased.
        run.refresh_from_db()
        self.assertEqual((run.status, run.claimed_by), (AllocationRun.Status.RUNNING, WORKER_B))
        self.assertEqual(run.error_message, LOST_AFTER_PERSISTENCE_MESSAGE.format(count=1))
        self.assertGreater(run.lease_expires_at, timezone.now())
        self.assertEqual(jobs.stale_run_ids(), [], "B's takeover lease is respected while it lasts")

        # B's lease expires; the next recovery converges on the same outcome.
        _expire_lease(run.id)
        with inline_connections():
            actions = recover_stale_runs('host-c:300:cccccccc', worker_settings=TEST_SETTINGS)
        self.assertEqual([(a.action, a.lost_worker) for a in actions], [('failed', WORKER_B)])
        run.refresh_from_db()
        self.assertEqual(run.status, AllocationRun.Status.FAILED)
        self.assertEqual(run.error_message, LOST_AFTER_PERSISTENCE_MESSAGE.format(count=1))
        self.assertIsNotNone(run.completed_at)
        self.assertIsNone(run.lease_expires_at)
        self.assertEqual(run.claimed_by, 'host-c:300:cccccccc')
        self.assertEqual(
            list(BedAssignment.objects.filter(allocation_run=run).values_list('status', flat=True)),
            [BedAssignment.Status.CANCELLED],
        )

    def test_a_completed_recovery_never_leaves_a_terminal_run_without_its_message(self):
        run = _stale_run(self.region, self.boss, started=True)
        assign(self.students[0], self.room, run=run)
        with inline_connections():
            recover_stale_runs(WORKER_B, worker_settings=TEST_SETTINGS)
        run.refresh_from_db()
        self.assertEqual(run.status, AllocationRun.Status.FAILED)
        self.assertTrue(run.error_message)
        self.assertIsNone(run.live_snapshot)
        self.assertIsNone(run.lease_expires_at)
