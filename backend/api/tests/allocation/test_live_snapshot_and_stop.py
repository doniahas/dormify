import threading
import time
from unittest.mock import patch, MagicMock

from django.test import TestCase, TransactionTestCase
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework import status

from api.models import AllocationRun, BedAssignment
from allocation.solver import (
    run_improved_ortools_allocation,
    _run_stop_watcher,
    _STOP_WATCHER_POLL_INTERVAL_SECONDS,
    _LiveSolutionCallback,
    _SnapshotMirrorState,
)
from allocation import live_registry

from ._support import (
    _make_region,
    _make_region_boss,
    _make_employee,
    _make_run,
    _make_minimal_infra,
    _make_minimal_student,
    MINIMAL_SOLVER_CONFIG,
)


# ---------------------------------------------------------------------------

class LiveSnapshotCallbackTest(TransactionTestCase):
    """Requirement: the FIRST feasible solution is captured immediately,
    not delayed by the memory/DB throttle windows; the registry is cleared
    once the solve finishes; callers without allocation_run_id see zero
    behavior change. Needs TransactionTestCase so the fixtures are
    committed: CP-SAT invokes the solution callback on its own thread,
    whose separate DB connection cannot see rows written by an
    uncommitted transaction."""

    def setUp(self):
        patcher = patch('allocation.solver.close_old_connections')
        patcher.start()
        self.addCleanup(patcher.stop)
        self.region = _make_region('LiveSnapshotRegion')
        self.boss = _make_region_boss(self.region)
        self.dorm_type, self.rooms = _make_minimal_infra(self.region)
        self.student = _make_minimal_student('LS1', self.dorm_type)

    def tearDown(self):
        live_registry._snapshots.clear()
        live_registry._active_solvers.clear()

    def test_first_feasible_snapshot_captured_immediately(self):
        run = _make_run(self.region, self.boss, status_val=AllocationRun.Status.RUNNING, completed=False)

        result = run_improved_ortools_allocation(
            [self.student], self.rooms, MINIMAL_SOLVER_CONFIG,
            allocation_run_id=run.id, max_seconds=5,
        )

        self.assertIn(result['solver_status'], ('OPTIMAL', 'FEASIBLE'))
        run.refresh_from_db()
        self.assertIsNotNone(
            run.live_snapshot,
            "the first feasible solution must be captured immediately, "
            "not delayed by the throttle window",
        )
        self.assertEqual(run.live_snapshot['assigned_count'], 1)
        self.assertEqual(run.live_snapshot['unassigned_count'], 0)

    def test_live_registry_cleared_after_solve_completes(self):
        run = _make_run(self.region, self.boss, status_val=AllocationRun.Status.RUNNING, completed=False)
        run_improved_ortools_allocation(
            [self.student], self.rooms, MINIMAL_SOLVER_CONFIG,
            allocation_run_id=run.id, max_seconds=5,
        )
        self.assertIsNone(live_registry.get(run.id))
        self.assertIsNone(live_registry._active_solvers.get(run.id))

    def test_no_allocation_run_id_skips_live_callback_entirely(self):
        """Callers that omit allocation_run_id (sync legacy endpoint, most
        existing solver tests) must see zero behavior change: no registry
        writes, no watcher thread, no live_snapshot write attempted."""
        result = run_improved_ortools_allocation(
            [self.student], self.rooms, MINIMAL_SOLVER_CONFIG, max_seconds=5,
        )
        self.assertEqual(result['solver_status'], 'OPTIMAL')
        self.assertEqual(len(live_registry._snapshots), 0)
        self.assertEqual(len(live_registry._active_solvers), 0)

    def test_snapshot_persisted_when_watcher_never_completes_a_poll(self):
        """A solve can finish long before the stop watcher completes even
        one poll interval, so snapshot persistence must not depend on the
        watcher having run: the caller-thread final flush covers it."""
        run = _make_run(self.region, self.boss, status_val=AllocationRun.Status.RUNNING, completed=False)
        completed_polls = []

        def counting_watcher(allocation_run_id, solver, stop_event, mirror_state=None):
            class _CountingEvent:
                """Records every poll interval that elapses without the
                solve finishing, so the test can assert there were none."""

                def wait(self, timeout=None):
                    fired = stop_event.wait(timeout)
                    if not fired:
                        completed_polls.append(timeout)
                    return fired

                def __getattr__(self, name):
                    return getattr(stop_event, name)

            return _run_stop_watcher(
                allocation_run_id, solver, _CountingEvent(), mirror_state,
            )

        with patch('allocation.solver._STOP_WATCHER_POLL_INTERVAL_SECONDS', 300.0), \
                patch('allocation.solver._run_stop_watcher', counting_watcher):
            result = run_improved_ortools_allocation(
                [self.student], self.rooms, MINIMAL_SOLVER_CONFIG,
                allocation_run_id=run.id, max_seconds=5,
            )

        self.assertIn(result['solver_status'], ('OPTIMAL', 'FEASIBLE'))
        self.assertEqual(
            completed_polls, [],
            'the watcher must not have completed a poll interval for this test to mean anything',
        )
        run.refresh_from_db()
        self.assertIsNotNone(
            run.live_snapshot,
            'the newest snapshot must be persisted even when the watcher never polled',
        )
        self.assertEqual(run.live_snapshot['assigned_count'], 1)

    def test_solution_callback_performs_no_database_queries(self):
        """CP-SAT may invoke the solution callback on a thread it owns,
        whose Django connection nothing in this process would close. The
        callback must therefore issue no SQL at all - asserted by marking
        the callback's own execution context rather than by thread name,
        so the check holds wherever CP-SAT chooses to run it."""
        from django.db.backends.utils import CursorWrapper

        run = _make_run(self.region, self.boss, status_val=AllocationRun.Status.RUNNING, completed=False)
        inside_callback = threading.local()
        callback_calls = []
        queries_during_callback = []
        real_callback = _LiveSolutionCallback.on_solution_callback
        real_execute = CursorWrapper.execute
        real_executemany = CursorWrapper.executemany

        def marked_callback(callback_self):
            callback_calls.append(1)
            inside_callback.active = True
            try:
                return real_callback(callback_self)
            finally:
                inside_callback.active = False

        def guarded_execute(cursor_self, sql, params=None):
            if getattr(inside_callback, 'active', False):
                queries_during_callback.append(str(sql))
            return real_execute(cursor_self, sql, params)

        def guarded_executemany(cursor_self, sql, param_list):
            if getattr(inside_callback, 'active', False):
                queries_during_callback.append(str(sql))
            return real_executemany(cursor_self, sql, param_list)

        with patch.object(_LiveSolutionCallback, 'on_solution_callback', marked_callback), \
                patch.object(CursorWrapper, 'execute', guarded_execute), \
                patch.object(CursorWrapper, 'executemany', guarded_executemany):
            result = run_improved_ortools_allocation(
                [self.student], self.rooms, MINIMAL_SOLVER_CONFIG,
                allocation_run_id=run.id, max_seconds=5,
            )

        self.assertIn(result['solver_status'], ('OPTIMAL', 'FEASIBLE'))
        self.assertGreater(
            len(callback_calls), 0,
            'the solution callback never ran, so this test proved nothing',
        )
        self.assertEqual(
            queries_during_callback, [],
            'the solution callback must not issue any database query',
        )

    def test_solve_leaves_no_new_database_session(self):
        """The whole point of keeping the callback database-free: a solve
        must not leave a connection behind on a thread nothing closes.
        Compares sessions before and after rather than assuming the
        database has no other sessions at all."""
        from django.db import connection

        if connection.vendor != 'postgresql':
            self.skipTest('session inspection is PostgreSQL-specific')

        def other_session_pids():
            with connection.cursor() as cursor:
                cursor.execute(
                    'SELECT pid FROM pg_stat_activity '
                    'WHERE datname = current_database() AND pid <> pg_backend_pid()'
                )
                return {row[0] for row in cursor.fetchall()}

        run = _make_run(self.region, self.boss, status_val=AllocationRun.Status.RUNNING, completed=False)
        sessions_before = other_session_pids()

        # A poll interval the solve cannot outlast keeps the watcher from
        # opening a connection of its own, so any new session could only
        # have come from the solution callback.
        with patch('allocation.solver._STOP_WATCHER_POLL_INTERVAL_SECONDS', 300.0):
            result = run_improved_ortools_allocation(
                [self.student], self.rooms, MINIMAL_SOLVER_CONFIG,
                allocation_run_id=run.id, max_seconds=5,
            )

        self.assertIn(result['solver_status'], ('OPTIMAL', 'FEASIBLE'))
        self.assertEqual(
            other_session_pids() - sessions_before, set(),
            'the solve must not leave a database session behind',
        )

    def test_snapshot_is_persisted_before_the_registry_is_cleared(self):
        """The final flush reads the registry, so it has to happen while
        the entry is still there."""
        run = _make_run(self.region, self.boss, status_val=AllocationRun.Status.RUNNING, completed=False)
        observed = {}
        real_clear = live_registry.clear

        def observing_clear(run_id):
            observed['snapshot_at_clear'] = (
                AllocationRun.objects.filter(pk=run_id)
                .values_list('live_snapshot', flat=True)
                .first()
            )
            return real_clear(run_id)

        with patch.object(live_registry, 'clear', observing_clear):
            run_improved_ortools_allocation(
                [self.student], self.rooms, MINIMAL_SOLVER_CONFIG,
                allocation_run_id=run.id, max_seconds=5,
            )

        self.assertIsNotNone(
            observed.get('snapshot_at_clear'),
            'live_snapshot must already be persisted when the registry entry is dropped',
        )
        self.assertIsNone(live_registry.get(run.id))

    def test_final_flush_does_not_block_on_a_stalled_mirror_write(self):
        """The snapshot mirror lock is held across database I/O, so a write
        that stalls past the watcher join timeout would otherwise leave the
        caller-thread final flush waiting for it indefinitely. The flush
        must wait only a bounded time, then let finalization proceed - and
        the allocation result itself must be unaffected."""
        run = _make_run(self.region, self.boss, status_val=AllocationRun.Status.RUNNING, completed=False)
        lock_held = threading.Event()
        release_lock = threading.Event()
        holders = []
        solver_threads = []

        def unblock_and_join():
            """Release the simulated stall and reap both threads, so a
            failing regression cannot leave a daemon solver thread running
            on into later tests. Idempotent and bounded."""
            release_lock.set()
            for thread in holders + solver_threads:
                thread.join(timeout=10)

        self.addCleanup(unblock_and_join)

        class _StalledMirrorState(_SnapshotMirrorState):
            """Stands in for a mirror whose database write never returns:
            the coordination lock stays held for the whole solve."""

            def __init__(self):
                super().__init__()
                holder = threading.Thread(target=self._hold_lock, daemon=True)
                holders.append(holder)
                holder.start()
                lock_held.wait(timeout=5)

            def _hold_lock(self):
                self._lock.acquire()
                lock_held.set()
                release_lock.wait(timeout=60)
                self._lock.release()

        solve = {}

        def do_solve():
            from django.db import connection as solve_connection
            try:
                solve['result'] = run_improved_ortools_allocation(
                    [self.student], self.rooms, MINIMAL_SOLVER_CONFIG,
                    allocation_run_id=run.id, max_seconds=5,
                )
            except BaseException as exc:
                solve['error'] = exc
            finally:
                solve_connection.close()

        with patch('allocation.solver._SnapshotMirrorState', _StalledMirrorState):
            solver_thread = threading.Thread(target=do_solve, daemon=True)
            solver_threads.append(solver_thread)
            solver_thread.start()
            # Comfortably above the watcher join timeout plus the bounded
            # lock wait, and low enough that a regression fails quickly
            # instead of hanging the suite.
            solver_thread.join(timeout=30)
            finished = not solver_thread.is_alive()
            # Releasing the lock also unblocks a solver thread that was
            # stuck on it, so both are joined before the test returns.
            unblock_and_join()

        self.assertTrue(
            finished,
            'solver finalization blocked waiting for the snapshot mirror lock',
        )
        self.assertNotIn('error', solve, solve.get('error'))
        self.assertIn(solve['result']['solver_status'], ('OPTIMAL', 'FEASIBLE'))
        self.assertEqual(
            solve['result']['successful_assignments'], 1,
            'a snapshot that could not be mirrored must not affect the allocation result',
        )
        # Registry cleanup ran even though the flush had to give up.
        self.assertIsNone(live_registry.get(run.id))
        self.assertIsNone(live_registry._active_solvers.get(run.id))

    def test_late_mirror_cannot_resurrect_a_finalized_snapshot(self):
        """A mirror write that only reaches the database after the run was
        finalized must not restore a preview on a finished run, and a stale
        sequence must never replace a newer one."""
        run = _make_run(self.region, self.boss, status_val=AllocationRun.Status.RUNNING, completed=False)
        mirror_state = _SnapshotMirrorState()

        def _snapshot(sequence):
            return {
                'sequence': sequence,
                'assignments': [],
                'assigned_count': 0,
                'unassigned_count': 0,
                'solver_status': 'FEASIBLE',
            }

        self.assertTrue(mirror_state.mirror(run.id, _snapshot(2)))
        run.refresh_from_db()
        self.assertEqual(run.live_snapshot['sequence'], 2)

        self.assertFalse(
            mirror_state.mirror(run.id, _snapshot(1)),
            'an older snapshot must never replace a newer one',
        )
        self.assertFalse(
            mirror_state.mirror(run.id, _snapshot(2)),
            'the same sequence must not be written twice',
        )
        run.refresh_from_db()
        self.assertEqual(run.live_snapshot['sequence'], 2)

        # Terminal cleanup, exactly as the background runner performs it.
        AllocationRun.objects.filter(pk=run.id).update(
            status=AllocationRun.Status.COMPLETED,
            live_snapshot=None,
        )

        self.assertFalse(
            mirror_state.mirror(run.id, _snapshot(3)),
            'a write landing after finalization must not update the run',
        )
        run.refresh_from_db()
        self.assertIsNone(
            run.live_snapshot,
            'a late mirror write must not resurrect a preview on a finished run',
        )

    def test_snapshot_persisted_for_each_search_worker_count(self):
        """Which thread CP-SAT uses for the callback depends on the search
        worker count, so persistence must not vary with it."""
        for workers in (1, 2):
            with self.subTest(search_workers=workers):
                region = _make_region(f'LiveSnapshotWorkers{workers}')
                boss = _make_region_boss(region, email=f'boss-workers{workers}@test.com')
                dorm_type, rooms = _make_minimal_infra(region)
                student = _make_minimal_student(f'LSW{workers}', dorm_type)
                run = _make_run(region, boss, status_val=AllocationRun.Status.RUNNING, completed=False)

                with patch('allocation.solver.NUM_SEARCH_WORKERS', workers):
                    result = run_improved_ortools_allocation(
                        [student], rooms, MINIMAL_SOLVER_CONFIG,
                        allocation_run_id=run.id, max_seconds=5,
                    )

                self.assertIn(result['solver_status'], ('OPTIMAL', 'FEASIBLE'))
                run.refresh_from_db()
                self.assertIsNotNone(run.live_snapshot)
                self.assertEqual(run.live_snapshot['assigned_count'], 1)


# ---------------------------------------------------------------------------
# Tests: GET /api/allocation/runs/<id>/preview/ ("צפה בתוצאה הנוכחית")
# ---------------------------------------------------------------------------

class PreviewEndpointTest(TestCase):
    """Requirements 5/6/7: preview never stops the solver, never creates
    BedAssignment rows, and reports unavailable (not an error) before any
    feasible solution exists."""

    def setUp(self):
        self.client = APIClient()
        self.region = _make_region('PreviewRegion')
        self.boss = _make_region_boss(self.region)

    def tearDown(self):
        live_registry._snapshots.clear()
        live_registry._active_solvers.clear()

    def test_preview_unavailable_before_any_snapshot(self):
        run = _make_run(self.region, self.boss, status_val=AllocationRun.Status.RUNNING, completed=False)
        self.client.force_authenticate(user=self.boss)
        resp = self.client.get(f'/api/allocation/runs/{run.id}/preview/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertFalse(resp.data['available'])
        self.assertIsNone(resp.data['snapshot'])

    def test_preview_returns_snapshot_without_touching_solver_or_db(self):
        run = _make_run(self.region, self.boss, status_val=AllocationRun.Status.RUNNING, completed=False)
        fake_solver = MagicMock()
        live_registry.register_solver(run.id, fake_solver)
        snapshot = {
            'sequence': 1,
            'assignments': [{'student_db_id': 1, 'student_name': 'X'}],
            'assigned_count': 1,
            'unassigned_count': 0,
            'objective_value': 10.0,
            'wall_time_seconds': 0.2,
            'solver_status': 'FEASIBLE',
            'captured_at': timezone.now().isoformat(),
        }
        # The solve mirrors its snapshots to AllocationRun.live_snapshot;
        # since R8 that persisted copy is the only one the preview reads.
        AllocationRun.objects.filter(pk=run.id).update(live_snapshot=snapshot)

        self.client.force_authenticate(user=self.boss)
        resp = self.client.get(f'/api/allocation/runs/{run.id}/preview/')

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertTrue(resp.data['available'])
        self.assertEqual(resp.data['snapshot']['sequence'], 1)

        # Preview must never touch the solver control surface or create
        # any DB assignment - it is a pure read of already-computed data.
        fake_solver.StopSearch.assert_not_called()
        run.refresh_from_db()
        self.assertEqual(run.status, AllocationRun.Status.RUNNING)
        self.assertEqual(BedAssignment.objects.filter(allocation_run=run).count(), 0)

    def test_preview_reads_the_persisted_snapshot_when_nothing_is_registered_in_process(self):
        run = _make_run(self.region, self.boss, status_val=AllocationRun.Status.RUNNING, completed=False)
        AllocationRun.objects.filter(pk=run.id).update(live_snapshot={
            'sequence': 3, 'assignments': [], 'assigned_count': 0,
            'unassigned_count': 5, 'objective_value': 1.0,
            'wall_time_seconds': 4.0, 'solver_status': 'FEASIBLE',
            'captured_at': timezone.now().isoformat(),
        })
        self.client.force_authenticate(user=self.boss)
        resp = self.client.get(f'/api/allocation/runs/{run.id}/preview/')
        self.assertTrue(resp.data['available'])
        self.assertEqual(resp.data['snapshot']['sequence'], 3)

    def test_preview_forbidden_for_other_region_user(self):
        run = _make_run(self.region, self.boss, status_val=AllocationRun.Status.RUNNING, completed=False)
        other_region = _make_region('OtherPreviewRegion')
        other_employee = _make_employee(other_region, email='other-preview@test.com')
        self.client.force_authenticate(user=other_employee)
        resp = self.client.get(f'/api/allocation/runs/{run.id}/preview/')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)


# ---------------------------------------------------------------------------
# Tests: POST /api/allocation/runs/<id>/stop-and-save/ ("עצור ושמור תוצאה")
# ---------------------------------------------------------------------------

class StopAndSaveSameProcessFastPathTest(TestCase):
    """Requirement 8 (same-process path): the view calls
    live_registry.request_stop_search, which invokes StopSearch() directly
    on whatever solver object is registered for this run - proven here with
    a stand-in solver, independent of real CP-SAT timing."""

    def setUp(self):
        self.client = APIClient()
        self.region = _make_region('StopSaveFastPathRegion')
        self.boss = _make_region_boss(self.region)

    def tearDown(self):
        live_registry._active_solvers.clear()

    def test_stop_and_save_calls_stopsearch_when_solver_registered_in_process(self):
        run = _make_run(self.region, self.boss, status_val=AllocationRun.Status.RUNNING, completed=False)
        fake_solver = MagicMock()
        live_registry.register_solver(run.id, fake_solver)

        self.client.force_authenticate(user=self.boss)
        resp = self.client.post(f'/api/allocation/runs/{run.id}/stop-and-save/')

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        run.refresh_from_db()
        self.assertEqual(run.status, AllocationRun.Status.STOP_AND_SAVE_REQUESTED)
        fake_solver.StopSearch.assert_called_once()

    def test_stop_and_save_unauthorized(self):
        run = _make_run(self.region, self.boss, status_val=AllocationRun.Status.RUNNING, completed=False)
        employee = _make_employee(self.region, email='emp-stopsave@test.com')
        self.client.force_authenticate(user=employee)
        resp = self.client.post(f'/api/allocation/runs/{run.id}/stop-and-save/')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_stop_and_save_completed_run_returns_409(self):
        run = _make_run(self.region, self.boss, status_val=AllocationRun.Status.COMPLETED)
        self.client.force_authenticate(user=self.boss)
        resp = self.client.post(f'/api/allocation/runs/{run.id}/stop-and-save/')
        self.assertEqual(resp.status_code, status.HTTP_409_CONFLICT)

    def test_repeated_stop_and_save_is_idempotent(self):
        run = _make_run(self.region, self.boss, status_val=AllocationRun.Status.RUNNING, completed=False)
        self.client.force_authenticate(user=self.boss)
        resp1 = self.client.post(f'/api/allocation/runs/{run.id}/stop-and-save/')
        self.assertEqual(resp1.status_code, status.HTTP_200_OK)
        resp2 = self.client.post(f'/api/allocation/runs/{run.id}/stop-and-save/')
        self.assertEqual(resp2.status_code, status.HTTP_200_OK)
        run.refresh_from_db()
        self.assertEqual(run.status, AllocationRun.Status.STOP_AND_SAVE_REQUESTED)


class StopWatcherThreadTest(TransactionTestCase):
    """Requirement 8 (process-agnostic path): _run_stop_watcher polls the DB
    on its own fixed timer, independent of CP-SAT's solution callback, and
    calls StopSearch() once it observes a stop request written by a
    completely separate thread/connection - exactly the cross-process-style
    scenario a same-process shortcut cannot cover. Needs TransactionTestCase
    so the watcher's own DB connection actually sees the committed update."""

    def test_watcher_thread_calls_stopsearch_when_status_changes(self):
        region = _make_region('WatcherRegion')
        boss = _make_region_boss(region)
        run = _make_run(region, boss, status_val=AllocationRun.Status.RUNNING, completed=False)
        fake_solver = MagicMock()
        stop_event = threading.Event()

        watcher_thread = threading.Thread(
            target=_run_stop_watcher,
            args=(run.id, fake_solver, stop_event),
            daemon=True,
        )
        watcher_thread.start()

        # Give the watcher a moment to start polling, then request a stop -
        # from the watcher's perspective this is indistinguishable from a
        # stop requested by a different process entirely, since it only
        # ever learns about it through the DB.
        time.sleep(0.2)
        AllocationRun.objects.filter(pk=run.id).update(
            status=AllocationRun.Status.STOP_AND_SAVE_REQUESTED,
        )

        watcher_thread.join(timeout=_STOP_WATCHER_POLL_INTERVAL_SECONDS + 3.0)
        stop_event.set()

        fake_solver.StopSearch.assert_called_once()
        self.assertFalse(watcher_thread.is_alive())

    def test_stop_request_is_acted_on_before_snapshot_mirroring(self):
        """Snapshot mirroring is best-effort state and must never sit
        between observing a stop request and interrupting the search - a
        mirror write that blocks would otherwise delay StopSearch for as
        long as the database takes. The newest snapshot is persisted after
        Solve() returns by the calling thread's final flush instead."""
        region = _make_region('WatcherStopOrderRegion')
        boss = _make_region_boss(region)
        run = _make_run(
            region, boss,
            status_val=AllocationRun.Status.STOP_AND_SAVE_REQUESTED,
            completed=False,
        )
        fake_solver = MagicMock()
        stop_event = threading.Event()
        mirror_entered = threading.Event()
        release_mirror = threading.Event()

        class _BlockingMirrorState:
            """Stands in for a mirror whose database write never returns,
            and records whether it was entered at all."""

            def mirror(self, *args, **kwargs):
                mirror_entered.set()
                release_mirror.wait(timeout=30)
                return False

        watcher_thread = threading.Thread(
            target=_run_stop_watcher,
            args=(run.id, fake_solver, stop_event, _BlockingMirrorState()),
            daemon=True,
        )

        def unblock_and_join():
            """Bounded and idempotent, so a failing regression cannot leave
            the watcher blocked in the stand-in mirror."""
            release_mirror.set()
            stop_event.set()
            watcher_thread.join(timeout=10)

        self.addCleanup(unblock_and_join)

        watcher_thread.start()
        watcher_thread.join(timeout=_STOP_WATCHER_POLL_INTERVAL_SECONDS + 3.0)

        self.assertFalse(
            watcher_thread.is_alive(),
            'the watcher must exit after acting on the stop request',
        )
        fake_solver.StopSearch.assert_called_once()
        self.assertFalse(
            mirror_entered.is_set(),
            'snapshot mirroring must not run on a tick that observed a stop request',
        )

    def test_continuing_poll_mirrors_the_registry_snapshot_to_the_database(self):
        """The periodic cross-process copy, exercised through the watcher
        itself: on a poll where the run is still RUNNING, whatever
        live_registry holds must reach AllocationRun.live_snapshot. The
        caller-thread final flush would otherwise mask a periodic mirror
        that had stopped working."""
        region = _make_region('WatcherMirrorRegion')
        boss = _make_region_boss(region)
        run = _make_run(region, boss, status_val=AllocationRun.Status.RUNNING, completed=False)
        self.addCleanup(live_registry.clear, run.id)

        snapshot = {
            'sequence': 7,
            'assignments': [],
            'assigned_count': 3,
            'unassigned_count': 1,
            'objective_value': 42.0,
            'wall_time_seconds': 1.5,
            'solver_status': 'FEASIBLE',
            'captured_at': timezone.now().isoformat(),
        }
        live_registry.set(run.id, snapshot)

        class _SinglePollStopEvent:
            """Lets the watcher complete exactly one continuing poll and
            then ends it, so the periodic path runs to completion without
            depending on any elapsed wall-clock time."""

            def __init__(self):
                self._wait_calls = 0

            @property
            def completed_polls(self):
                return max(0, self._wait_calls - 1)

            def wait(self, timeout=None):
                self._wait_calls += 1
                return self._wait_calls > 1

        fake_solver = MagicMock()
        stop_event = _SinglePollStopEvent()
        watcher_thread = threading.Thread(
            target=_run_stop_watcher,
            args=(run.id, fake_solver, stop_event, _SnapshotMirrorState()),
            daemon=True,
        )
        watcher_thread.start()
        self.addCleanup(watcher_thread.join, 10)
        watcher_thread.join(timeout=10)

        self.assertFalse(watcher_thread.is_alive(), 'the watcher must exit after its last poll')
        self.assertEqual(
            stop_event.completed_polls, 1,
            'exactly one continuing poll must have run',
        )

        run.refresh_from_db()
        self.assertIsNotNone(
            run.live_snapshot,
            'a continuing poll must mirror the registry snapshot to the database',
        )
        self.assertEqual(run.live_snapshot['sequence'], 7)
        self.assertEqual(run.live_snapshot['assigned_count'], 3)
        self.assertEqual(run.live_snapshot['unassigned_count'], 1)

        # No stop was requested, so the search must have been left alone.
        fake_solver.StopSearch.assert_not_called()


class StopAndSaveBranchLogicTest(TestCase):
    """Requirements 9/10/11: how execute_allocation_run (the run body the
    durable worker executes) finalizes a run depends on (a) whether Cancel
    or Stop & Save was requested and (b) whether the (possibly
    early-stopped) solve actually persisted a result. Tested
    deterministically by faking the solver's return value - the real
    persistence transaction itself is unchanged, existing code."""

    def setUp(self):
        self.region = _make_region('StopSaveBranchRegion')
        self.boss = _make_region_boss(self.region)
        self.dorm_type, self.rooms = _make_minimal_infra(self.region)
        self.student = _make_minimal_student('SSB1', self.dorm_type)

    def _run_background_sync(self, run, fabricated_result, set_status_before_return=None):
        def _fake_solve(*args, **kwargs):
            if set_status_before_return:
                AllocationRun.objects.filter(pk=run.id).update(status=set_status_before_return)
            return fabricated_result

        # The run body owns its database connection in production (the
        # worker process) and closes it in its own finally block. Here it
        # runs inline on the test's own thread, so that same close() call
        # would kill the connection TestCase's wrapping transaction depends
        # on for every assertion after this call (and cascade into later
        # tests). Patch both connection-closing calls out, exactly like
        # DeleteAllocationRunTest already does for close_old_connections.
        with patch('allocation.solver.run_improved_ortools_allocation', side_effect=_fake_solve), \
                patch('django.db.close_old_connections'), \
                patch('django.db.connection.close'):
            from api.views import execute_allocation_run
            execute_allocation_run(
                allocation_run_id=run.id,
                region_id=self.region.id,
                constraints_config={},
                include_assigned=False,
                allocation_scope=None,
                max_seconds=30,
            )

    def test_stop_and_save_with_no_feasible_solution_persists_nothing(self):
        """Requirement 10."""
        run = _make_run(self.region, self.boss, status_val=AllocationRun.Status.RUNNING, completed=False)
        fabricated_result = {
            'solver_status': 'UNKNOWN',
            'solution_persisted': False,
            'successful_assignments': 0,
            'conflicts': 1,
            'students_processed': 1,
            'warnings': [],
            'anier_building_179_diagnostics': {},
        }
        self._run_background_sync(
            run, fabricated_result,
            set_status_before_return=AllocationRun.Status.STOP_AND_SAVE_REQUESTED,
        )

        run.refresh_from_db()
        self.assertEqual(run.status, AllocationRun.Status.STOPPED)
        self.assertEqual(BedAssignment.objects.filter(allocation_run=run).count(), 0)

    def test_stop_and_save_persists_feasible_result_and_marks_completed(self):
        """Requirement 9."""
        run = _make_run(self.region, self.boss, status_val=AllocationRun.Status.RUNNING, completed=False)
        fabricated_result = {
            'solver_status': 'FEASIBLE',
            'optimality_proven': False,
            'solution_persisted': True,
            'successful_assignments': 1,
            'conflicts': 0,
            'students_processed': 1,
            'roommate_matches': 0,
            'warnings': [],
            'anier_building_179_diagnostics': {},
        }
        self._run_background_sync(
            run, fabricated_result,
            set_status_before_return=AllocationRun.Status.STOP_AND_SAVE_REQUESTED,
        )

        run.refresh_from_db()
        self.assertEqual(run.status, AllocationRun.Status.COMPLETED)
        self.assertTrue(run.diagnostics.get('stopped_early_by_user'))
        self.assertEqual(run.diagnostics.get('solver_status'), 'FEASIBLE')
        self.assertFalse(run.diagnostics.get('optimality_proven'))

    def test_cancellation_still_discards_result(self):
        """Requirement 11 (regression): Cancel (בטל הרצה) keeps discarding
        results exactly as before, distinct from Stop & Save."""
        run = _make_run(self.region, self.boss, status_val=AllocationRun.Status.RUNNING, completed=False)
        fabricated_result = {
            'solver_status': 'FEASIBLE',
            'optimality_proven': False,
            'solution_persisted': True,
            'successful_assignments': 1,
            'conflicts': 0,
            'students_processed': 1,
            'roommate_matches': 0,
            'warnings': [],
            'anier_building_179_diagnostics': {},
        }
        self._run_background_sync(
            run, fabricated_result,
            set_status_before_return=AllocationRun.Status.CANCELLATION_REQUESTED,
        )

        run.refresh_from_db()
        self.assertEqual(run.status, AllocationRun.Status.STOPPED)


class StopAndSaveRealInterruptionTest(TransactionTestCase):
    """End-to-end smoke test: a Stop & Save request already sitting in the
    DB before the solve starts is picked up by the real watcher thread
    spawned inside run_improved_ortools_allocation itself, and the existing
    best-effort persistence path still produces a valid, safely-persisted
    result. Uses TransactionTestCase because the watcher runs in its own
    thread/connection and must see this test's committed writes."""

    def test_stop_and_save_requested_before_solve_still_yields_valid_result(self):
        region = _make_region('StopSaveRealRegion')
        boss = _make_region_boss(region)
        dorm_type, rooms = _make_minimal_infra(region)
        student = _make_minimal_student('SSR1', dorm_type)
        run = _make_run(region, boss, status_val=AllocationRun.Status.RUNNING, completed=False)

        AllocationRun.objects.filter(pk=run.id).update(
            status=AllocationRun.Status.STOP_AND_SAVE_REQUESTED,
        )

        result = run_improved_ortools_allocation(
            [student], rooms, MINIMAL_SOLVER_CONFIG,
            allocation_run_id=run.id, max_seconds=30,
        )

        self.assertIn(result['solver_status'], ('OPTIMAL', 'FEASIBLE'))
        self.assertTrue(result['solution_persisted'])
        self.assertEqual(result['successful_assignments'], 1)
        live_registry.unregister_solver(run.id)
        live_registry.clear(run.id)


# ---------------------------------------------------------------------------
# Tests: Stop & Save vs Cancel race protection
# ---------------------------------------------------------------------------

class StopSaveVsCancelRaceTest(TestCase):
    """Requirement 12: whichever of Stop & Save / Cancel is requested first
    wins the row lock and "claims" the stop; the other gets 409, not a
    silent double-apply."""

    def setUp(self):
        self.client = APIClient()
        self.region = _make_region('RaceRegion')
        self.boss = _make_region_boss(self.region)
        self.client.force_authenticate(user=self.boss)

    def test_stop_and_save_then_cancel_returns_409(self):
        run = _make_run(self.region, self.boss, status_val=AllocationRun.Status.RUNNING, completed=False)
        resp1 = self.client.post(f'/api/allocation/runs/{run.id}/stop-and-save/')
        self.assertEqual(resp1.status_code, status.HTTP_200_OK)

        resp2 = self.client.post(f'/api/allocation/runs/{run.id}/stop/')
        self.assertEqual(resp2.status_code, status.HTTP_409_CONFLICT)

        run.refresh_from_db()
        self.assertEqual(run.status, AllocationRun.Status.STOP_AND_SAVE_REQUESTED)

    def test_cancel_then_stop_and_save_returns_409(self):
        run = _make_run(self.region, self.boss, status_val=AllocationRun.Status.RUNNING, completed=False)
        resp1 = self.client.post(f'/api/allocation/runs/{run.id}/stop/')
        self.assertEqual(resp1.status_code, status.HTTP_200_OK)

        resp2 = self.client.post(f'/api/allocation/runs/{run.id}/stop-and-save/')
        self.assertEqual(resp2.status_code, status.HTTP_409_CONFLICT)

        run.refresh_from_db()
        self.assertEqual(run.status, AllocationRun.Status.CANCELLATION_REQUESTED)
