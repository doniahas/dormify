"""Direct tests for api.domains.allocation.runs (run lifecycle services)."""

from unittest.mock import patch

from django.test import TestCase

from api.domains.allocation import runs
from api.domains.allocation.gateway import (
    DEFAULT_SOLVER_TIME_SECONDS,
    MAX_USER_SOLVER_TIME_SECONDS,
)
from api.models import AllocationRun, BedAssignment

from ._fixtures import (
    assign,
    make_boss,
    make_full_stack,
    make_region,
    make_run,
    make_student,
)


class CreateRunForRegionTests(TestCase):
    def setUp(self):
        self.region = make_region('Runs Region')
        self.boss = make_boss(self.region)

    def test_blocking_run_raises_without_creating(self):
        running = make_run(self.region, self.boss, status=AllocationRun.Status.RUNNING, completed=False)

        with self.assertRaises(runs.AllocationAlreadyRunning) as raised:
            runs.create_run_for_region(
                self.region, self.boss,
                status=AllocationRun.Status.RUNNING,
                blocking_statuses=(AllocationRun.Status.RUNNING,),
            )

        self.assertEqual(raised.exception.active_run, running)
        self.assertEqual(AllocationRun.objects.count(), 1)

    def test_non_blocking_statuses_do_not_block_and_fields_are_stored(self):
        make_run(self.region, self.boss, status=AllocationRun.Status.COMPLETED)

        run = runs.create_run_for_region(
            self.region, self.boss,
            status=AllocationRun.Status.QUEUED,
            blocking_statuses=runs.STOP_REQUEST_STATUSES + (AllocationRun.Status.RUNNING,),
            max_search_seconds=42,
        )

        self.assertEqual(run.status, AllocationRun.Status.QUEUED)
        self.assertEqual(run.max_search_seconds, 42)
        self.assertEqual(run.run_by, self.boss)

    def test_other_region_run_does_not_block(self):
        other = make_region('Other Runs Region')
        make_run(other, make_boss(other), status=AllocationRun.Status.RUNNING, completed=False)

        run = runs.create_run_for_region(
            self.region, self.boss,
            status=AllocationRun.Status.RUNNING,
            blocking_statuses=(AllocationRun.Status.RUNNING,),
        )
        self.assertEqual(run.region, self.region)


class ParseMaxSolverSecondsTests(TestCase):
    def test_absent_value_returns_the_solver_default_unchanged(self):
        for raw in (None, ''):
            value = runs.parse_max_solver_seconds(raw)
            self.assertEqual(value, DEFAULT_SOLVER_TIME_SECONDS)
            self.assertIs(type(value), type(DEFAULT_SOLVER_TIME_SECONDS))

    def test_numeric_string_becomes_float(self):
        value = runs.parse_max_solver_seconds('90')
        self.assertEqual(value, 90.0)
        self.assertIs(type(value), float)

    def test_non_numeric_value_raises_user_message(self):
        with self.assertRaises(ValueError) as raised:
            runs.parse_max_solver_seconds('abc')
        self.assertEqual(str(raised.exception), 'זמן חיפוש מרבי חייב להיות מספר')

    def test_out_of_range_value_raises_range_message(self):
        with self.assertRaises(ValueError) as raised:
            runs.parse_max_solver_seconds(MAX_USER_SOLVER_TIME_SECONDS + 1)
        self.assertIn('זמן חיפוש מרבי חייב להיות בין', str(raised.exception))


class RequestRunStopTests(TestCase):
    def setUp(self):
        self.region = make_region('Stop Region')
        self.boss = make_boss(self.region)

    def _stop(self, run, requested=AllocationRun.Status.CANCELLATION_REQUESTED, allowed=True):
        with patch('allocation.live_registry.request_stop_search') as stop_search:
            outcome = runs.request_run_stop(run.id, requested, authorize=lambda locked: allowed)
        return outcome, stop_search

    def test_unknown_run_raises_does_not_exist(self):
        with self.assertRaises(AllocationRun.DoesNotExist):
            runs.request_run_stop(999999, AllocationRun.Status.CANCELLATION_REQUESTED, authorize=lambda r: True)

    def test_authorize_callback_sees_the_locked_run_and_can_refuse(self):
        run = make_run(self.region, self.boss, status=AllocationRun.Status.RUNNING, completed=False)
        seen = []

        def authorize(locked):
            seen.append(locked.pk)
            return False

        with patch('allocation.live_registry.request_stop_search') as stop_search:
            outcome = runs.request_run_stop(run.id, AllocationRun.Status.CANCELLATION_REQUESTED, authorize=authorize)

        self.assertEqual(seen, [run.pk])
        self.assertEqual(outcome, runs.StopRequestOutcome('forbidden', AllocationRun.Status.RUNNING))
        run.refresh_from_db()
        self.assertEqual(run.status, AllocationRun.Status.RUNNING)
        stop_search.assert_not_called()

    def test_terminal_run_is_reported_with_its_status(self):
        run = make_run(self.region, self.boss, status=AllocationRun.Status.COMPLETED)
        outcome, stop_search = self._stop(run)
        self.assertEqual(outcome, runs.StopRequestOutcome('terminal', AllocationRun.Status.COMPLETED))
        stop_search.assert_not_called()

    def test_repeated_request_is_idempotent(self):
        run = make_run(self.region, self.boss, status=AllocationRun.Status.CANCELLATION_REQUESTED, completed=False)
        outcome, stop_search = self._stop(run)
        self.assertEqual(outcome.outcome, 'already_requested')
        stop_search.assert_not_called()

    def test_competing_request_of_the_other_kind_is_never_overridden(self):
        run = make_run(self.region, self.boss, status=AllocationRun.Status.STOP_AND_SAVE_REQUESTED, completed=False)
        outcome, _ = self._stop(run, requested=AllocationRun.Status.CANCELLATION_REQUESTED)
        self.assertEqual(outcome, runs.StopRequestOutcome('conflicting_request', AllocationRun.Status.STOP_AND_SAVE_REQUESTED))
        run.refresh_from_db()
        self.assertEqual(run.status, AllocationRun.Status.STOP_AND_SAVE_REQUESTED)

    def test_live_run_is_flagged_and_same_process_solver_interrupted(self):
        run = make_run(self.region, self.boss, status=AllocationRun.Status.RUNNING, completed=False)
        outcome, stop_search = self._stop(run, requested=AllocationRun.Status.STOP_AND_SAVE_REQUESTED)
        self.assertEqual(outcome, runs.StopRequestOutcome('requested', AllocationRun.Status.STOP_AND_SAVE_REQUESTED))
        run.refresh_from_db()
        self.assertEqual(run.status, AllocationRun.Status.STOP_AND_SAVE_REQUESTED)
        stop_search.assert_called_once_with(run.id)


class DeleteCompletedRunResultsTests(TestCase):
    def setUp(self):
        self.region = make_region('Delete Region')
        self.boss = make_boss(self.region)
        patcher = patch('django.db.close_old_connections')
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_approved_run_is_refused(self):
        run = make_run(self.region, self.boss, status=AllocationRun.Status.APPROVED)
        with self.assertRaises(runs.RunNotDeletable) as raised:
            runs.delete_completed_run_results(run)
        self.assertEqual(raised.exception.reason, 'approved')
        self.assertEqual(raised.exception.run_status, AllocationRun.Status.APPROVED)

    def test_non_completed_run_is_refused(self):
        run = make_run(self.region, self.boss, status=AllocationRun.Status.RUNNING, completed=False)
        with self.assertRaises(runs.RunNotDeletable) as raised:
            runs.delete_completed_run_results(run)
        self.assertEqual(raised.exception.reason, 'not_completed')

    def test_completed_run_assignments_are_cancelled_and_run_marked_deleted(self):
        dorm, _building, _apartment, room = make_full_stack(self.region)
        run = make_run(self.region, self.boss, status=AllocationRun.Status.COMPLETED)
        student = make_student(dorm, 'DEL-1')
        assignment = assign(student, room, run=run)

        deleted = runs.delete_completed_run_results(run)

        self.assertEqual(deleted, 1)
        run.refresh_from_db()
        assignment.refresh_from_db()
        student.refresh_from_db()
        self.assertEqual(run.status, AllocationRun.Status.DELETED)
        self.assertEqual(assignment.status, BedAssignment.Status.CANCELLED)
        self.assertIsNone(student.assigned_room_id)


class MarkRunFailedAndPopulationTests(TestCase):
    def setUp(self):
        self.region = make_region('Failed Region')
        self.boss = make_boss(self.region)

    def test_mark_run_failed_persists_message_and_completion(self):
        run = make_run(self.region, self.boss, status=AllocationRun.Status.RUNNING, completed=False)
        runs.mark_run_failed(run, 'boom')
        run.refresh_from_db()
        self.assertEqual(run.status, AllocationRun.Status.FAILED)
        self.assertEqual(run.error_message, 'boom')
        self.assertIsNotNone(run.completed_at)

    def test_original_population_ids_read_from_diagnostics(self):
        with_ids = make_run(
            self.region, self.boss,
            diagnostics={'population_summary': {'sent_to_solver_student_ids': [3, 5]}},
        )
        without = make_run(self.region, self.boss, diagnostics={})
        self.assertEqual(runs.original_solver_population_ids(with_ids), [3, 5])
        self.assertIsNone(runs.original_solver_population_ids(without))
