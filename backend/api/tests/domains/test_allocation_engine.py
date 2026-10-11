"""
Direct tests for the allocation-engine boundary (api.domains.allocation
inputs / engine / persistence) and the sync / retry / background parity it
guarantees. The OR-Tools model itself is covered by api.tests.allocation.
"""

from unittest.mock import patch

from django.db import connection
from django.test import SimpleTestCase, TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

import api.views as api_views
from api.domains.allocation import engine, inputs, persistence, runs
from api.domains.allocation.config import (
    DEFAULT_CONDITIONS,
    HARD_ALLOCATION_CONSTRAINTS,
    SOFT_ALLOCATION_CONSTRAINTS,
    normalize_allocation_constraints,
)
from api.domains.allocation.gateway import EMPTY_ANIER_BUILDING_179_DIAGNOSTICS
from api.domains.allocation.results import (
    build_assignment_rows_for_run,
    build_assignment_rows_for_students,
)
from api.models import AllocationRun, BedAssignment, Student

from ._fixtures import (
    assign,
    make_apartment,
    make_boss,
    make_building,
    make_dorm,
    make_full_stack,
    make_region,
    make_room,
    make_run,
    make_student,
)

SOLVER_KWARGS = [
    'students', 'rooms', 'constraints_config', 'allocation_run_id', 'max_seconds',
    'enable_group_capacity_cuts',
]
POPULATION_KEYS = [
    'imported_students', 'excluded_accessibility', 'excluded_leaving', 'excluded_overlap',
    'excluded_total', 'sent_to_solver', 'sent_to_solver_student_ids',
]
CANNED_RESULT = {
    'students_processed': 3, 'successful_assignments': 2, 'conflicts': 1,
    'mutual_roommate_matches': 1, 'one_sided_roommate_matches': 1,
    'solver_status': 'OPTIMAL', 'optimality_proven': True, 'objective_value': 12.5,
    'best_objective_bound': 12.0, 'absolute_gap': 0.5, 'relative_gap': 0.04,
    'warnings': ['w1'], 'anier_building_179_diagnostics': {'imported_anier_students': 3},
    'solution_persisted': True, 'wall_time': 1.5, 'students_with_no_feasible_beds': [],
    'assignments': [],
}


def _query_kind(sql):
    if sql.startswith('SELECT COUNT(*)'):
        table = 'student' if 'FROM "api_student"' in sql else 'room' if 'FROM "api_room"' in sql else '?'
        return f'count:{table}'
    if sql.startswith('SELECT "api_student"."id" AS "id"'):
        return 'ids:student'
    return 'other'


class PopulationFixture(TestCase):
    """One region with every population / inventory variant the solver input filters."""

    def setUp(self):
        self.region = make_region('Engine Region')
        self.other = make_region('Engine Other Region')
        self.boss = make_boss(self.region)
        self.dorm, self.building, self.apartment, self.room_1 = make_full_stack(self.region)
        self.room_2 = make_room(make_apartment(self.building, number='2'), name='B')
        make_room(make_apartment(self.building, number='3'), name='RI', is_active=False)
        make_room(make_apartment(self.building, number='4', is_active=False), name='RA')
        make_room(make_apartment(make_building(self.dorm, is_active=False), number='5'), name='RB')
        other_dorm = make_dorm(self.other)
        make_room(make_apartment(make_building(other_dorm), number='6'), name='RO')

        self.new = make_student(self.dorm, 'E-NEW', category=Student.StudentCategory.NEW)
        self.transfer = make_student(self.dorm, 'E-TR', category=Student.StudentCategory.TRANSFER)
        self.continuing = make_student(self.dorm, 'E-CONT', category=Student.StudentCategory.CONTINUING)
        make_student(self.dorm, 'E-ACC', accessibility_flag=True)
        make_student(self.dorm, 'E-LEAVE', category=Student.StudentCategory.LEAVING)
        make_student(self.dorm, 'E-BOTH', accessibility_flag=True, category=Student.StudentCategory.LEAVING)
        self.assigned = make_student(self.dorm, 'E-ASSIGNED')
        assign(self.assigned, self.room_1)
        make_student(other_dorm, 'E-OTHER')

        self.default_ids = sorted([self.new.id, self.transfer.id, self.continuing.id])


class SolverPopulationTests(PopulationFixture):
    def test_load_is_lazy_and_composes_the_shared_querysets(self):
        with CaptureQueriesContext(connection) as queries:
            population = inputs.load_solver_population(self.region)
        self.assertEqual(len(queries.captured_queries), 0)
        self.assertEqual((population.region, population.include_assigned, population.allocation_scope),
                         (self.region, False, None))
        self.assertEqual(sorted(population.students.values_list('id', flat=True)), self.default_ids)
        self.assertEqual(sorted(population.students_base.values_list('id', flat=True)),
                         sorted(self.default_ids + [self.assigned.id]))
        self.assertEqual(sorted(population.rooms.values_list('name', flat=True)), ['A', 'B'])
        self.assertEqual(population.rooms._prefetch_related_lookups, ('beds',))
        self.assertEqual(population.students.query.select_related, {'accepted_dorm_type': {'region': {}}})

    def test_include_assigned_and_scope_narrowing(self):
        with_assigned = inputs.load_solver_population(self.region, include_assigned=True)
        self.assertEqual(sorted(with_assigned.students.values_list('id', flat=True)),
                         sorted(self.default_ids + [self.assigned.id]))
        scoped = inputs.load_solver_population(self.region, allocation_scope='new_transfer_only')
        self.assertEqual(sorted(scoped.students.values_list('id', flat=True)), sorted([self.new.id, self.transfer.id]))
        ignored = inputs.load_solver_population(self.region, allocation_scope='something_else')
        self.assertEqual(sorted(ignored.students.values_list('id', flat=True)), self.default_ids)

    def test_measure_population_reads_exactly_the_pre_solve_set_in_canonical_order(self):
        population = inputs.load_solver_population(self.region)
        with CaptureQueriesContext(connection) as queries:
            snapshot = inputs.measure_population(population)
        self.assertEqual(
            [_query_kind(q['sql']) for q in queries.captured_queries],
            ['count:student', 'ids:student', 'count:student', 'count:student', 'count:student',
             'count:student', 'count:student', 'count:room'],
        )
        self.assertEqual(snapshot.students_total_in_region, 4)
        self.assertEqual(sorted(snapshot.student_ids), self.default_ids)
        self.assertIs(type(snapshot.student_ids), list)
        self.assertEqual((snapshot.students_count, snapshot.rooms_count), (3, 2))
        self.assertEqual(list(snapshot.population_summary), POPULATION_KEYS)
        self.assertEqual(
            {k: v for k, v in snapshot.population_summary.items() if k != 'sent_to_solver_student_ids'},
            {'imported_students': 7, 'excluded_accessibility': 2, 'excluded_leaving': 2,
             'excluded_overlap': 1, 'excluded_total': 3, 'sent_to_solver': 3},
        )
        self.assertEqual(snapshot.population_summary['sent_to_solver_student_ids'], snapshot.student_ids)

    def test_retry_population_summary_counts_the_retried_students_only(self):
        summary = inputs.retry_population_summary((5, 9))
        self.assertEqual(list(summary), POPULATION_KEYS)
        self.assertEqual(summary, {
            'imported_students': 2, 'excluded_accessibility': 0, 'excluded_leaving': 0,
            'excluded_overlap': 0, 'excluded_total': 0, 'sent_to_solver': 2,
            'sent_to_solver_student_ids': [5, 9],
        })


class SolverInputTests(SimpleTestCase):
    def test_solver_kwargs_is_the_full_argument_set(self):
        constraints = {'marker': 'constraints'}
        solver_input = engine.SolverInput(students='S', rooms='R', constraints_config=constraints)
        kwargs = solver_input.solver_kwargs()
        self.assertEqual(list(kwargs), SOLVER_KWARGS)
        self.assertIs(kwargs['constraints_config'], constraints)
        self.assertEqual((kwargs['allocation_run_id'], kwargs['max_seconds'], kwargs['enable_group_capacity_cuts']),
                         (None, None, True))
        explicit = engine.SolverInput('S', 'R', constraints, allocation_run_id=7, max_seconds=45.0)
        self.assertEqual((explicit.solver_kwargs()['allocation_run_id'], explicit.solver_kwargs()['max_seconds']), (7, 45.0))

    def test_invoke_solver_calls_the_gateway_solver_with_the_kwargs_and_defaults_none_to_empty(self):
        solver_input = engine.SolverInput('S', 'R', {'k': 1}, allocation_run_id=3, max_seconds=9)
        with patch('allocation.solver.run_improved_ortools_allocation', return_value=None) as solve:
            self.assertEqual(engine.invoke_solver(solver_input), {})
        solve.assert_called_once_with(**solver_input.solver_kwargs())
        self.assertEqual(solve.call_args.args, ())
        with patch('allocation.solver.run_improved_ortools_allocation', return_value={'solver_status': 'OPTIMAL'}):
            self.assertEqual(engine.invoke_solver(solver_input), {'solver_status': 'OPTIMAL'})


class SolverOutcomeTests(SimpleTestCase):
    def test_defaults_for_a_missing_or_empty_result(self):
        outcome = engine.SolverOutcome.from_result(None)
        self.assertEqual(outcome.raw, {})
        self.assertEqual(outcome.students_processed(7), 7)
        self.assertEqual((outcome.successful_assignments, outcome.conflicts, outcome.roommate_matches), (0, 0, 0))
        self.assertIsNone(outcome.solver_status)
        self.assertIs(outcome.solution_persisted, False)
        self.assertEqual((outcome.warnings, outcome.anier_building_179_diagnostics), ([], {}))

    def test_roommate_total_prefers_the_explicit_value_even_when_zero(self):
        self.assertEqual(engine.SolverOutcome({'roommate_matches': 0, 'mutual_roommate_matches': 5,
                                               'one_sided_roommate_matches': 4}).roommate_matches, 0)
        self.assertEqual(engine.SolverOutcome({'mutual_roommate_matches': 5, 'one_sided_roommate_matches': 4}).roommate_matches, 9)
        self.assertEqual(engine.SolverOutcome({'roommate_matches': None, 'one_sided_roommate_matches': 2}).roommate_matches, 2)

    def test_accessors_read_the_raw_dict_without_copying(self):
        outcome = engine.SolverOutcome(dict(CANNED_RESULT))
        self.assertEqual(outcome.students_processed(0), 3)
        self.assertEqual((outcome.successful_assignments, outcome.conflicts, outcome.roommate_matches), (2, 1, 2))
        self.assertEqual(outcome.solver_status, 'OPTIMAL')
        self.assertIs(outcome.solution_persisted, True)
        self.assertIs(outcome.warnings, outcome.raw['warnings'])
        self.assertIs(outcome.anier_building_179_diagnostics, outcome.raw['anier_building_179_diagnostics'])

    def test_diagnostics_payload_keys_order_and_fallbacks(self):
        payload = engine.SolverOutcome(dict(CANNED_RESULT)).diagnostics_payload()
        self.assertEqual(list(payload), list(engine.RUN_DIAGNOSTICS_KEYS))
        self.assertEqual(payload, {
            'warnings': ['w1'], 'anier_building_179_diagnostics': {'imported_anier_students': 3},
            'solver_status': 'OPTIMAL', 'optimality_proven': True, 'objective_value': 12.5,
            'best_objective_bound': 12.0, 'absolute_gap': 0.5, 'relative_gap': 0.04,
        })
        empty = engine.run_diagnostics_payload('not a dict')
        self.assertEqual(list(empty), list(engine.RUN_DIAGNOSTICS_KEYS))
        self.assertEqual(empty, engine.run_diagnostics_payload({}) | {'anier_building_179_diagnostics': {}})
        self.assertIs(api_views._run_diagnostics_payload, engine.run_diagnostics_payload)


class RunPersistenceRecordTests(SimpleTestCase):
    def test_completed_run_fields_order_and_values(self):
        now = timezone.now()
        fields = persistence.completed_run_fields(engine.SolverOutcome(dict(CANNED_RESULT)), students_count=9, completed_at=now)
        self.assertEqual(fields, {
            'status': AllocationRun.Status.COMPLETED, 'students_processed': 3, 'successful_assignments': 2,
            'roommate_matches': 2, 'conflicts': 1, 'completed_at': now,
        })
        self.assertEqual(list(fields), ['status', 'students_processed', 'successful_assignments',
                                        'roommate_matches', 'conflicts', 'completed_at'])
        fallback = persistence.completed_run_fields(engine.SolverOutcome({}), students_count=9, completed_at=now)
        self.assertEqual((fallback['students_processed'], fallback['successful_assignments'], fallback['conflicts']), (9, 0, 0))

    def test_early_exit_fields(self):
        now = timezone.now()
        self.assertEqual(persistence.no_students_run_fields(now), {
            'status': AllocationRun.Status.COMPLETED, 'students_processed': 0, 'successful_assignments': 0,
            'roommate_matches': 0, 'conflicts': 0, 'completed_at': now,
        })
        self.assertEqual(persistence.no_rooms_run_fields(now), {
            'status': AllocationRun.Status.FAILED, 'error_message': 'לא נמצאו חדרים פעילים באזור זה', 'completed_at': now,
        })
        self.assertEqual(persistence.NO_ACTIVE_ROOMS_MESSAGE, 'לא נמצאו חדרים פעילים באזור זה')

    def test_diagnostics_documents(self):
        summary = {'imported_students': 1, 'sent_to_solver_student_ids': [4]}
        empty = persistence.empty_run_diagnostics(summary)
        self.assertEqual(list(empty), ['warnings', 'anier_building_179_diagnostics', 'population_summary'])
        self.assertEqual(empty['anier_building_179_diagnostics'], dict(EMPTY_ANIER_BUILDING_179_DIAGNOSTICS))
        self.assertIsNot(empty['anier_building_179_diagnostics'], EMPTY_ANIER_BUILDING_179_DIAGNOSTICS)
        self.assertEqual(empty['population_summary'], {**summary, 'assigned': 0, 'unassigned': 0})

        stopped = persistence.stopped_without_solution_diagnostics()
        self.assertEqual(stopped, {
            'warnings': [], 'anier_building_179_diagnostics': dict(EMPTY_ANIER_BUILDING_179_DIAGNOSTICS),
            'stop_reason': 'no_feasible_solution_before_stop',
        })

        outcome = engine.SolverOutcome(dict(CANNED_RESULT))
        merged = persistence.population_summary_with_outcome(summary, outcome)
        self.assertEqual(merged, {**summary, 'assigned': 2, 'unassigned': 1})
        solved = persistence.solved_run_diagnostics(outcome, merged, retry_of_run_id=11)
        self.assertEqual(list(solved), list(engine.RUN_DIAGNOSTICS_KEYS) + ['population_summary', 'retry_of_run_id'])
        self.assertIs(solved['population_summary'], merged)
        self.assertEqual(solved['retry_of_run_id'], 11)

    def test_apply_run_fields_sets_the_attributes(self):
        run = AllocationRun()
        persistence.apply_run_fields(run, {'status': AllocationRun.Status.FAILED, 'error_message': 'x'})
        self.assertEqual((run.status, run.error_message), (AllocationRun.Status.FAILED, 'x'))


class ConstraintConfigBoundaryTests(SimpleTestCase):
    """
    The configuration handover: normalize_allocation_constraints() produces
    the dict SolverInput.constraints_config carries by identity, and the
    solver reads it only through its three readers. Pins the defaults and
    the meaning of each key as the solver interprets them.
    """

    def test_default_configuration_is_the_documented_catalogue(self):
        self.assertEqual(normalize_allocation_constraints(None), DEFAULT_CONDITIONS)
        self.assertEqual(normalize_allocation_constraints({}), DEFAULT_CONDITIONS)
        self.assertEqual(normalize_allocation_constraints('not a dict'), DEFAULT_CONDITIONS)
        self.assertEqual(set(DEFAULT_CONDITIONS), HARD_ALLOCATION_CONSTRAINTS | set(SOFT_ALLOCATION_CONSTRAINTS))

    def test_solver_reads_hard_soft_and_weights_exactly_as_normalized(self):
        from allocation.solver import _constraint_weight, _is_constraint_hard, _is_constraint_soft

        config = normalize_allocation_constraints({
            'sameReligion': {'enabled': False, 'weight': 2},
            'roommateMatch': {'weight': 25},
            'sectorMatching': {'weight': 'abc'},
            'sameGender': {'enabled': False, 'weight': 9},
        })
        for key in HARD_ALLOCATION_CONSTRAINTS:
            with self.subTest(key=key):
                self.assertEqual(config[key], {'enabled': True, 'strict': True, 'critical': True, 'weight': 0})
                self.assertTrue(_is_constraint_hard(config, key))
                self.assertFalse(_is_constraint_soft(config, key))
                self.assertEqual(_constraint_weight(config, key, 5), 0)
        self.assertTrue(bool(config['priorityFirst'].get('enabled') or config['priorityFirst'].get('critical')))

        self.assertEqual(config['sameReligion'], {'enabled': False, 'strict': False, 'critical': False, 'weight': 2})
        self.assertFalse(_is_constraint_soft(config, 'sameReligion'))
        self.assertEqual(_constraint_weight(config, 'sameReligion', 6), 2)
        self.assertEqual(config['roommateMatch']['weight'], 10)
        self.assertTrue(_is_constraint_soft(config, 'roommateMatch'))
        self.assertEqual(_constraint_weight(config, 'roommateMatch', 8), 10)
        self.assertEqual(config['sectorMatching']['weight'], SOFT_ALLOCATION_CONSTRAINTS['sectorMatching'])
        for key, default_weight in SOFT_ALLOCATION_CONSTRAINTS.items():
            with self.subTest(key=key):
                self.assertFalse(_is_constraint_hard(config, key))
                self.assertEqual(_constraint_weight(DEFAULT_CONDITIONS, key, default_weight), default_weight)
                self.assertTrue(_is_constraint_soft(DEFAULT_CONDITIONS, key))

    def test_solver_default_weights_match_the_catalogue(self):
        # The solver's own fallback weights (read when a key is absent) equal
        # the catalogue defaults, so a missing key and the default config agree.
        from allocation.solver import _constraint_weight

        for key, default_weight in SOFT_ALLOCATION_CONSTRAINTS.items():
            self.assertEqual(_constraint_weight({}, key, default_weight), default_weight)
        self.assertEqual(SOFT_ALLOCATION_CONSTRAINTS, {
            'sameReligion': 6, 'roommateMatch': 8, 'sectorMatching': 7,
            'avoidYearMix_1_with_3_4': 4, 'avoidAtudaimWithHasmaha': 4,
        })


class EntryPointParityTests(PopulationFixture):
    """The three entry points hand the solver the same input where parity is expected."""

    def _record(self, calls):
        def fake(*args, **kwargs):
            calls.append({
                'args': args,
                'kwargs': kwargs,
                'student_ids': sorted(kwargs['students'].values_list('id', flat=True)),
                'room_ids': sorted(room.id for room in kwargs['rooms']),
            })
            return dict(CANNED_RESULT)
        return fake

    def _run_sync(self, constraints, **options):
        run = make_run(self.region, self.boss, status=AllocationRun.Status.RUNNING, completed=False)
        calls = []
        with patch('allocation.solver.run_improved_ortools_allocation', new=self._record(calls)), \
                patch('api.domains.allocation.runs.refresh_db_connection'):
            outcome = runs.execute_sync_allocation(run, self.region, constraints_config=constraints, **options)
        run.refresh_from_db()
        return run, calls, outcome

    def _run_background(self, constraints, max_seconds=None, **options):
        run = make_run(self.region, self.boss, status=AllocationRun.Status.QUEUED, completed=False)
        calls = []
        with patch('allocation.solver.run_improved_ortools_allocation', new=self._record(calls)), \
                patch('django.db.close_old_connections'), patch('django.db.connection.close'):
            api_views.execute_allocation_run(
                allocation_run_id=run.id, region_id=self.region.id, constraints_config=constraints,
                include_assigned=options.get('include_assigned', False),
                allocation_scope=options.get('allocation_scope'), max_seconds=max_seconds,
            )
        run.refresh_from_db()
        return run, calls

    def test_sync_and_background_send_the_same_population_inventory_and_configuration(self):
        constraints = normalize_allocation_constraints({'sameReligion': {'enabled': False}})
        for options in ({}, {'include_assigned': True}, {'allocation_scope': 'new_transfer_only'}):
            with self.subTest(options=options):
                sync_run, sync_calls, _ = self._run_sync(constraints, **options)
                bg_run, bg_calls = self._run_background(constraints, max_seconds=45, **options)
                self.assertEqual(len(sync_calls), 1)
                self.assertEqual(len(bg_calls), 1)
                sync_call, bg_call = sync_calls[0], bg_calls[0]

                self.assertEqual(sync_call['args'], ())
                self.assertEqual(bg_call['args'], ())
                self.assertEqual(list(sync_call['kwargs']), SOLVER_KWARGS)
                self.assertEqual(list(bg_call['kwargs']), SOLVER_KWARGS)
                self.assertEqual(sync_call['student_ids'], bg_call['student_ids'])
                self.assertEqual(sync_call['room_ids'], bg_call['room_ids'])
                self.assertEqual(sync_call['room_ids'], sorted([self.room_1.id, self.room_2.id]))
                self.assertIs(sync_call['kwargs']['constraints_config'], constraints)
                self.assertIs(bg_call['kwargs']['constraints_config'], constraints)
                self.assertIs(sync_call['kwargs']['enable_group_capacity_cuts'], True)
                self.assertIs(bg_call['kwargs']['enable_group_capacity_cuts'], True)

                # Intentional differences: only the background run is known to the
                # solver (live preview / stop requests / assignment tagging) and
                # carries the operator's search limit.
                self.assertIsNone(sync_call['kwargs']['allocation_run_id'])
                self.assertEqual(bg_call['kwargs']['allocation_run_id'], bg_run.id)
                self.assertIsNone(sync_call['kwargs']['max_seconds'])
                self.assertEqual(bg_call['kwargs']['max_seconds'], 45)

                # Both persist the same outcome record for the same solver result.
                for run in (sync_run, bg_run):
                    self.assertEqual(run.status, AllocationRun.Status.COMPLETED)
                    self.assertEqual(
                        (run.students_processed, run.successful_assignments, run.roommate_matches, run.conflicts),
                        (3, 2, 2, 1),
                    )
                    self.assertIsNotNone(run.completed_at)
                self.assertEqual(sorted(sync_run.diagnostics), sorted(bg_run.diagnostics))
                self.assertEqual(
                    {k: v for k, v in sync_run.diagnostics.items() if k != 'population_summary'},
                    {k: v for k, v in bg_run.diagnostics.items() if k != 'population_summary'},
                )
                self.assertEqual(sync_run.diagnostics['population_summary'], bg_run.diagnostics['population_summary'])

    def test_early_exits_share_the_outcome_record_but_keep_their_documented_differences(self):
        Student.objects.filter(accepted_dorm_type=self.dorm).update(accessibility_flag=True)
        sync_run, sync_calls, outcome = self._run_sync(normalize_allocation_constraints(None))
        bg_run, bg_calls = self._run_background(normalize_allocation_constraints(None))
        self.assertEqual((sync_calls, bg_calls), ([], []))
        self.assertEqual(outcome.kind, 'no_students')
        for run in (sync_run, bg_run):
            self.assertEqual(run.status, AllocationRun.Status.COMPLETED)
            self.assertEqual((run.students_processed, run.successful_assignments, run.roommate_matches, run.conflicts), (0, 0, 0, 0))
            # jsonb does not preserve key order on read-back; the write order is
            # pinned by the orchestration characterization and persistence tests.
            self.assertEqual(sorted(run.diagnostics), sorted(['warnings', 'anier_building_179_diagnostics', 'population_summary']))
            self.assertEqual(run.diagnostics['population_summary']['sent_to_solver_student_ids'], [])
        self.assertEqual(outcome.population_summary, sync_run.diagnostics['population_summary'])

        Student.objects.filter(accepted_dorm_type=self.dorm).update(accessibility_flag=False)
        from api.models import Room
        Room.objects.filter(apartment__building__dorm_type=self.dorm).update(is_active=False)
        sync_run, _, outcome = self._run_sync(normalize_allocation_constraints(None))
        bg_run, _ = self._run_background(normalize_allocation_constraints(None))
        self.assertEqual(outcome.kind, 'no_rooms')
        for run in (sync_run, bg_run):
            self.assertEqual(run.status, AllocationRun.Status.FAILED)
            self.assertEqual(run.error_message, persistence.NO_ACTIVE_ROOMS_MESSAGE)
        # Documented difference: the synchronous run records no diagnostics for
        # this failure, the worker records the empty document.
        self.assertEqual(sync_run.diagnostics, {})
        self.assertEqual(sorted(bg_run.diagnostics), sorted(['warnings', 'anier_building_179_diagnostics', 'population_summary']))

    def test_retry_sends_the_retry_population_tagged_with_the_retry_run(self):
        original = make_run(self.region, self.boss, diagnostics={
            'population_summary': {'sent_to_solver_student_ids': [self.new.id, self.assigned.id, self.transfer.id]},
        })
        retry_run = make_run(self.region, self.boss, status=AllocationRun.Status.RUNNING, completed=False)
        ids = runs.original_solver_population_ids(original)
        from api.domains.allocation.queries import retry_population_queryset
        retry_qs = retry_population_queryset(ids)
        retry_ids = list(retry_qs.values_list('id', flat=True))
        calls = []
        with patch('allocation.solver.run_improved_ortools_allocation', new=self._record(calls)), \
                patch('api.domains.allocation.runs.refresh_db_connection'):
            outcome = runs.execute_retry_allocation(
                original, retry_run, retry_qs, retry_ids, constraints_config=normalize_allocation_constraints(None),
            )
        call = calls[0]
        self.assertEqual(list(call['kwargs']), SOLVER_KWARGS)
        self.assertEqual(call['student_ids'], sorted([self.new.id, self.transfer.id]))
        self.assertEqual(call['room_ids'], sorted([self.room_1.id, self.room_2.id]))
        self.assertEqual(call['kwargs']['allocation_run_id'], retry_run.id)
        self.assertIsNone(call['kwargs']['max_seconds'])
        retry_run.refresh_from_db()
        self.assertEqual(retry_run.status, AllocationRun.Status.COMPLETED)
        self.assertEqual(retry_run.diagnostics['retry_of_run_id'], original.id)
        self.assertEqual(retry_run.diagnostics['population_summary'],
                         {**inputs.retry_population_summary(retry_ids), 'assigned': 2, 'unassigned': 1})
        self.assertEqual(outcome.population_summary, retry_run.diagnostics['population_summary'])
        self.assertEqual(outcome.roommate_matches, 2)


class SynchronousRunResultTaggingTests(TestCase):
    """
    Characterizes the pre-existing behaviour behind the R6 closeout
    observation: a synchronous run reports its assignments, but
    GET /api/allocation/runs/<id>/ shows none of them.

    The synchronous workflow invokes the solver without the run's id
    (SolverInput.allocation_run_id is None), so the BedAssignment rows the
    solver persists carry allocation_run_id NULL and the run-scoped row
    builder finds nothing; the endpoint's own response uses the student-
    scoped builder instead. Changing this (tagging the rows) would alter
    persisted data and the run detail / delete / current-run behaviour of
    synchronous runs - an owner decision, deliberately not made here.
    """

    def setUp(self):
        self.region = make_region('Sync Tagging Region')
        self.boss = make_boss(self.region)
        self.dorm, _building, _apartment, self.room = make_full_stack(self.region)
        self.students = [make_student(self.dorm, 'TAG-1'), make_student(self.dorm, 'TAG-2')]
        patcher = patch('allocation.solver.close_old_connections')
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_synchronous_run_assignments_are_not_tagged_with_the_run(self):
        run = make_run(self.region, self.boss, status=AllocationRun.Status.RUNNING, completed=False)
        with patch('api.domains.allocation.runs.refresh_db_connection'):
            outcome = runs.execute_sync_allocation(
                run, self.region, constraints_config=normalize_allocation_constraints(None),
            )
        self.assertEqual(outcome.kind, 'completed')
        self.assertEqual(outcome.result['successful_assignments'], 2)
        self.assertEqual(len(outcome.assignment_rows), 2)

        persisted = BedAssignment.objects.filter(student__in=self.students, status=BedAssignment.Status.ACTIVE)
        self.assertEqual(persisted.count(), 2)
        self.assertEqual(set(persisted.values_list('allocation_run_id', flat=True)), {None})

        run.refresh_from_db()
        self.assertEqual((run.status, run.successful_assignments), (AllocationRun.Status.COMPLETED, 2))
        self.assertIsNone(run.search_started_at)
        self.assertEqual(build_assignment_rows_for_run(run), [])
        self.assertEqual(len(build_assignment_rows_for_students(self.region, [s.id for s in self.students])), 2)
