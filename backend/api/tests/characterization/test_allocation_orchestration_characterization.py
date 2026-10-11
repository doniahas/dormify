"""
Characterization of the background allocation run body.

Every worker test drives the compatibility surface
``api.views.execute_allocation_run`` (the run body the durable allocation
worker executes for a claimed run; until R8 the same body ran on a daemon
thread started by the request) and patches only shared,
location-independent objects (``threading.Thread``,
``django.db.close_old_connections``, ``django.db.connection.close``,
``allocation.solver.run_improved_ortools_allocation``), so the same tests
apply unchanged wherever the implementation lives.

AllocationRun writes are observed as the UPDATE statements the worker
issues (column -> parameter, with JSON parameters kept in their Python
insertion order), because PostgreSQL jsonb does not preserve key order on
read-back.
"""
import contextlib
import datetime
import io
import re
from unittest.mock import patch

from django.db import connection
from django.db.models.query import QuerySet
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

import api.views as api_views
from api.domains.allocation.config import normalize_allocation_constraints
from api.domains.allocation.gateway import (
    DEFAULT_SOLVER_TIME_SECONDS,
    EMPTY_ANIER_BUILDING_179_DIAGNOSTICS,
)
from api.models import (
    AllocationRun,
    Apartment,
    Bed,
    BedAssignment,
    Building,
    DormType,
    Region,
    Room,
    Student,
    User,
)

DIAGNOSTICS_KEYS = [
    'warnings',
    'anier_building_179_diagnostics',
    'solver_status',
    'optimality_proven',
    'objective_value',
    'best_objective_bound',
    'absolute_gap',
    'relative_gap',
]
POPULATION_KEYS = [
    'imported_students',
    'excluded_accessibility',
    'excluded_leaving',
    'excluded_overlap',
    'excluded_total',
    'sent_to_solver',
    'sent_to_solver_student_ids',
]
SOLVER_KWARGS = {
    'students', 'rooms', 'constraints_config', 'allocation_run_id',
    'max_seconds', 'enable_group_capacity_cuts',
}
NO_ROOMS_ERROR = 'לא נמצאו חדרים פעילים באזור זה'
STOP_REASON = 'no_feasible_solution_before_stop'


class _DateTimeWritten:
    def __repr__(self):
        return '<datetime>'


DT = _DateTimeWritten()
_UPDATE_RE = re.compile(r'^UPDATE "api_allocationrun" SET (.*) WHERE "api_allocationrun"\."id" = %s$')
_SET_RE = re.compile(r'"(\w+)" = (%s|NULL)')


def _parse_run_update(sql, params):
    match = _UPDATE_RE.match(sql)
    if not match:
        return None
    values = {}
    index = 0
    for column, placeholder in _SET_RE.findall(match.group(1)):
        if placeholder == 'NULL':
            values[column] = None
            continue
        value = params[index]
        index += 1
        if hasattr(value, 'adapted'):
            value = value.adapted
        elif isinstance(value, datetime.datetime):
            value = DT
        values[column] = value
    return values


class _Harness:
    """Recording stand-ins for every collaborator the worker reaches."""

    def __init__(self, solver_behavior=None, run_thread_inline=True):
        self.events = []
        self.threads = []
        self.solver_calls = []
        self.run_writes = []
        self.solver_behavior = solver_behavior
        self.run_thread_inline = run_thread_inline
        self._in_solver = False

    def collapsed_events(self):
        collapsed = []
        for event in self.events:
            if event == 'db' and collapsed and collapsed[-1] == 'db':
                continue
            collapsed.append(event)
        return collapsed

    def worker_writes(self):
        return [values for phase, values in self.run_writes if phase == 'worker']

    def _thread_class(self):
        harness = self

        class RecordingThread:
            def __init__(self, *args, **kwargs):
                self.init_args = args
                self.init_kwargs = kwargs
                self.start_calls = 0
                harness.threads.append(self)

            def start(self):
                self.start_calls += 1
                if harness.run_thread_inline:
                    self.init_kwargs['target']()

        return RecordingThread

    def _fake_solver(self, *args, **kwargs):
        self.events.append('solver')
        self._in_solver = True
        try:
            call = {
                'args': args,
                'kwargs': kwargs,
                'student_ids': sorted(kwargs['students'].values_list('id', flat=True)),
                'room_ids': sorted(room.id for room in kwargs['rooms']),
            }
            self.solver_calls.append(call)
            result = self.solver_behavior(call) if self.solver_behavior else {}
        finally:
            self._in_solver = False
        self.events.append('solver:return')
        return result

    def _wrapper(self, execute, sql, params, many, context):
        self.events.append('db')
        values = _parse_run_update(sql, params)
        if values is not None:
            self.run_writes.append(('fake-solver' if self._in_solver else 'worker', values))
        return execute(sql, params, many, context)

    @contextlib.contextmanager
    def active(self):
        with patch('threading.Thread', self._thread_class()), \
                patch('allocation.solver.run_improved_ortools_allocation', new=self._fake_solver), \
                patch('django.db.close_old_connections',
                      side_effect=lambda: self.events.append('close_old_connections')) as close_old, \
                patch('django.db.connection.close',
                      side_effect=lambda: self.events.append('connection.close')) as conn_close, \
                connection.execute_wrapper(self._wrapper), \
                contextlib.redirect_stderr(io.StringIO()):
            self.close_old_mock = close_old
            self.connection_close_mock = conn_close
            yield self


class OrchestrationFixtures(TestCase):
    """One region with every population/inventory variant the worker filters."""

    building_number = 900

    def setUp(self):
        self.region = Region.objects.create(id='orch', name='Orchestration Region')
        self.other_region = Region.objects.create(id='orch_other', name='Other Region')
        self.boss = User.objects.create_user(
            username='orch-boss', email='orch-boss@example.test', password='x',
            role=User.Role.REGION_BOSS, region=self.region,
        )
        self.dorm = DormType.objects.create(name='Orch Dorm', region=self.region)
        self.other_dorm = DormType.objects.create(name='Orch Other Dorm', region=self.other_region)

        self.room_1 = self._room(self.dorm, 'R1')
        self.room_2 = self._room(self.dorm, 'R2')
        self.room_inactive = self._room(self.dorm, 'RI', room_active=False)
        self.room_apartment_inactive = self._room(self.dorm, 'RA', apartment_active=False)
        self.room_building_inactive = self._room(self.dorm, 'RB', building_active=False)
        self.room_other_region = self._room(self.other_dorm, 'RO')

        self.new_student = self._student('ORCH-NEW', category=Student.StudentCategory.NEW)
        self.transfer_student = self._student('ORCH-TRANSFER', category=Student.StudentCategory.TRANSFER)
        self.continuing_student = self._student('ORCH-CONT', category=Student.StudentCategory.CONTINUING)
        self.accessibility_student = self._student('ORCH-ACC', accessibility_flag=True)
        self.leaving_student = self._student('ORCH-LEAVE', category=Student.StudentCategory.LEAVING)
        self.both_student = self._student(
            'ORCH-BOTH', accessibility_flag=True, category=Student.StudentCategory.LEAVING,
        )
        self.assigned_student = self._student('ORCH-ASSIGNED', assigned_room=self.room_1)
        self.assigned_assignment = BedAssignment.objects.create(
            student=self.assigned_student,
            bed=self.room_1.beds.order_by('label').first(),
            status=BedAssignment.Status.ACTIVE,
            assignment_type=BedAssignment.AssignmentType.INITIAL,
        )
        self.other_region_student = self._student('ORCH-OTHER', dorm=self.other_dorm)

        self.default_ids = sorted([
            self.new_student.id, self.transfer_student.id, self.continuing_student.id,
        ])
        self.active_room_ids = sorted([self.room_1.id, self.room_2.id])

    def _room(self, dorm, suffix, room_active=True, apartment_active=True, building_active=True):
        OrchestrationFixtures.building_number += 1
        building = Building.objects.create(
            number=OrchestrationFixtures.building_number, dorm_type=dorm, is_active=building_active,
        )
        apartment = Apartment.objects.create(
            building=building, number=f'APT-{suffix}', category=Apartment.Category.MALE,
            apartment_type=Apartment.ApartmentType.SINGLE, room_count=1, is_active=apartment_active,
        )
        room = Room.objects.create(apartment=apartment, name=suffix, capacity=2, is_active=room_active)
        for label in ('1', '2'):
            Bed.objects.create(room=room, label=label)
        return room

    def _student(self, student_id, dorm=None, **extra):
        return Student.objects.create(
            student_id=student_id, first_name='F', last_name=student_id,
            gender=Student.Gender.MALE, housing_type=Student.HousingType.SINGLE_MALE,
            accepted_dorm_type=dorm or self.dorm, **extra,
        )

    def _run(self, status=AllocationRun.Status.QUEUED, region=None):
        return AllocationRun.objects.create(
            region=region or self.region, run_by=self.boss, status=status,
            live_snapshot={'sequence': 1},
        )

    def _execute(self, harness, run, region=None, constraints=None, include_assigned=False,
                 allocation_scope=None, **extra):
        if constraints is None:
            constraints = {'marker': 'constraints'}
        with harness.active():
            returned = api_views.execute_allocation_run(
                allocation_run_id=run.id,
                region_id=(region or self.region).id,
                constraints_config=constraints,
                include_assigned=include_assigned,
                allocation_scope=allocation_scope,
                **extra,
            )
        return returned

    def _population(self, sent_ids, assigned, unassigned):
        return {
            'imported_students': 7,
            'excluded_accessibility': 2,
            'excluded_leaving': 2,
            'excluded_overlap': 1,
            'excluded_total': 3,
            'sent_to_solver': len(sent_ids),
            'sent_to_solver_student_ids': sent_ids,
            'assigned': assigned,
            'unassigned': unassigned,
        }

    def _normalized_population(self, population):
        normalized = dict(population)
        normalized['sent_to_solver_student_ids'] = sorted(normalized['sent_to_solver_student_ids'])
        return normalized

    def _assign_in_fake(self, run, students):
        occupied = BedAssignment.objects.filter(status=BedAssignment.Status.ACTIVE).values_list('bed_id', flat=True)
        beds = list(
            Bed.objects.filter(room__in=[self.room_1, self.room_2]).exclude(id__in=occupied).order_by('id')
        )
        for student, bed in zip(students, beds):
            BedAssignment.objects.create(
                student=student, bed=bed, status=BedAssignment.Status.ACTIVE,
                assignment_type=BedAssignment.AssignmentType.INITIAL, allocation_run_id=run.id,
            )
            Student.objects.filter(pk=student.pk).update(assigned_room=bed.room)


class WorkerThreadContractTests(OrchestrationFixtures):
    def test_run_body_executes_inline_without_constructing_a_thread(self):
        """
        Since R8 the run body is executed by the durable allocation worker on
        the calling thread: it constructs no daemon thread of its own, runs
        to completion before returning, and the parameters it was called
        with are the ones the solver sees.
        """
        run = self._run()
        harness = _Harness(run_thread_inline=False)
        with harness.active():
            returned = api_views.execute_allocation_run(
                allocation_run_id=run.id, region_id=self.region.id,
                constraints_config={'marker': 'constraints'}, include_assigned=False,
                allocation_scope=None, max_seconds=45,
            )
        self.assertIsNone(returned)
        self.assertEqual(harness.threads, [])

        self.assertEqual(len(harness.solver_calls), 1)
        kwargs = harness.solver_calls[0]['kwargs']
        self.assertEqual(kwargs['allocation_run_id'], run.id)
        self.assertEqual(kwargs['constraints_config'], {'marker': 'constraints'})
        self.assertEqual(kwargs['max_seconds'], 45)
        self.assertEqual(harness.solver_calls[0]['student_ids'], self.default_ids)
        run.refresh_from_db()
        self.assertEqual(run.status, AllocationRun.Status.COMPLETED)


class WorkerConnectionLifecycleTests(OrchestrationFixtures):
    def test_normal_completion_sequence(self):
        harness = _Harness(solver_behavior=lambda call: {'successful_assignments': 0})
        self._execute(harness, self._run(), max_seconds=30)
        self.assertEqual(harness.collapsed_events(), [
            'close_old_connections', 'db', 'close_old_connections',
            'solver', 'db', 'solver:return', 'db', 'connection.close',
        ])
        self.assertEqual(harness.close_old_mock.call_count, 2)
        self.assertEqual(harness.connection_close_mock.call_count, 1)

    def test_zero_students_sequence(self):
        Student.objects.filter(accepted_dorm_type=self.dorm).update(accessibility_flag=True)
        harness = _Harness()
        self._execute(harness, self._run())
        self.assertEqual(harness.collapsed_events(), ['close_old_connections', 'db', 'connection.close'])

    def test_zero_rooms_sequence(self):
        Room.objects.filter(apartment__building__dorm_type=self.dorm).update(is_active=False)
        harness = _Harness()
        self._execute(harness, self._run())
        self.assertEqual(harness.collapsed_events(), ['close_old_connections', 'db', 'connection.close'])

    def test_pre_start_cancellation_sequence(self):
        harness = _Harness()
        self._execute(harness, self._run(status=AllocationRun.Status.CANCELLATION_REQUESTED))
        self.assertEqual(harness.collapsed_events(), ['close_old_connections', 'db', 'connection.close'])

    def test_exception_sequence(self):
        def boom(call):
            raise RuntimeError('solver exploded')
        harness = _Harness(solver_behavior=boom)
        self._execute(harness, self._run())
        self.assertEqual(harness.collapsed_events(), [
            'close_old_connections', 'db', 'close_old_connections',
            'solver', 'db', 'connection.close',
        ])

    def test_post_solve_cancellation_sequence_includes_cleanup_close_old_connections(self):
        def cancel(call):
            AllocationRun.objects.filter(pk=call['kwargs']['allocation_run_id']).update(
                status=AllocationRun.Status.CANCELLATION_REQUESTED,
            )
            return {'solution_persisted': True}
        harness = _Harness(solver_behavior=cancel)
        self._execute(harness, self._run())
        self.assertEqual(harness.collapsed_events(), [
            'close_old_connections', 'db', 'close_old_connections',
            'solver', 'db', 'solver:return', 'db',
            'close_old_connections', 'db', 'connection.close',
        ])


class WorkerNaturalSuccessTests(OrchestrationFixtures):
    RESULT = {
        'students_processed': 3,
        'successful_assignments': 2,
        'conflicts': 1,
        'mutual_roommate_matches': 1,
        'one_sided_roommate_matches': 1,
        'solver_status': 'OPTIMAL',
        'optimality_proven': True,
        'objective_value': 12.5,
        'best_objective_bound': 12.0,
        'absolute_gap': 0.5,
        'relative_gap': 0.04,
        'warnings': ['w1'],
        'anier_building_179_diagnostics': {'imported_anier_students': 3},
        'solution_persisted': True,
    }

    def test_queued_run_completes_with_exact_writes_and_solver_inputs(self):
        run = self._run()
        constraints = {'marker': 'constraints'}
        harness = _Harness(solver_behavior=lambda call: dict(self.RESULT))
        returned = self._execute(harness, run, constraints=constraints, max_seconds=45)
        self.assertIsNone(returned)

        self.assertEqual(len(harness.solver_calls), 1)
        call = harness.solver_calls[0]
        self.assertEqual(call['args'], ())
        self.assertEqual(set(call['kwargs']), SOLVER_KWARGS)
        self.assertEqual(call['student_ids'], self.default_ids)
        self.assertEqual(call['room_ids'], self.active_room_ids)
        self.assertIs(call['kwargs']['constraints_config'], constraints)
        self.assertEqual(call['kwargs']['allocation_run_id'], run.id)
        self.assertEqual(call['kwargs']['max_seconds'], 45)
        self.assertIs(call['kwargs']['enable_group_capacity_cuts'], True)

        writes = harness.worker_writes()
        self.assertEqual(len(writes), 3)
        self.assertEqual(writes[0], {'status': AllocationRun.Status.RUNNING})

        self.assertEqual(list(writes[1]), ['diagnostics'])
        diagnostics = writes[1]['diagnostics']
        self.assertEqual(list(diagnostics), DIAGNOSTICS_KEYS + ['population_summary'])
        self.assertEqual(list(diagnostics['population_summary']), POPULATION_KEYS + ['assigned', 'unassigned'])
        self.assertEqual(
            {key: diagnostics[key] for key in DIAGNOSTICS_KEYS},
            {
                'warnings': ['w1'],
                'anier_building_179_diagnostics': {'imported_anier_students': 3},
                'solver_status': 'OPTIMAL',
                'optimality_proven': True,
                'objective_value': 12.5,
                'best_objective_bound': 12.0,
                'absolute_gap': 0.5,
                'relative_gap': 0.04,
            },
        )
        self.assertEqual(
            self._normalized_population(diagnostics['population_summary']),
            self._population(self.default_ids, assigned=2, unassigned=1),
        )

        self.assertEqual(writes[2], {
            'status': AllocationRun.Status.COMPLETED,
            'students_processed': 3,
            'successful_assignments': 2,
            'roommate_matches': 2,
            'conflicts': 1,
            'completed_at': DT,
            'live_snapshot': None,
        })

        run.refresh_from_db()
        self.assertEqual(run.status, AllocationRun.Status.COMPLETED)
        self.assertIsNotNone(run.completed_at)
        self.assertIsNone(run.live_snapshot)
        self.assertEqual(run.error_message, '')
        self.assertEqual(
            (run.students_processed, run.successful_assignments, run.roommate_matches, run.conflicts),
            (3, 2, 2, 1),
        )
        self.assertEqual(run.diagnostics['solver_status'], 'OPTIMAL')
        self.assertEqual(
            self._normalized_population(run.diagnostics['population_summary']),
            self._population(self.default_ids, assigned=2, unassigned=1),
        )

    def test_none_result_is_treated_as_empty_dict(self):
        run = self._run()
        harness = _Harness(solver_behavior=lambda call: None)
        self._execute(harness, run)
        writes = harness.worker_writes()
        self.assertEqual(writes[1]['diagnostics'], {
            'warnings': [],
            'anier_building_179_diagnostics': {},
            'solver_status': None,
            'optimality_proven': False,
            'objective_value': None,
            'best_objective_bound': None,
            'absolute_gap': None,
            'relative_gap': None,
            'population_summary': writes[1]['diagnostics']['population_summary'],
        })
        self.assertEqual(writes[1]['diagnostics']['population_summary']['assigned'], 0)
        self.assertEqual(writes[1]['diagnostics']['population_summary']['unassigned'], 0)
        self.assertEqual(writes[2], {
            'status': AllocationRun.Status.COMPLETED,
            'students_processed': 3,
            'successful_assignments': 0,
            'roommate_matches': 0,
            'conflicts': 0,
            'completed_at': DT,
            'live_snapshot': None,
        })

    def test_explicit_roommate_matches_zero_is_not_replaced_by_fallback(self):
        run = self._run()
        harness = _Harness(solver_behavior=lambda call: {
            'roommate_matches': 0, 'mutual_roommate_matches': 5, 'one_sided_roommate_matches': 4,
        })
        self._execute(harness, run)
        self.assertEqual(harness.worker_writes()[2]['roommate_matches'], 0)

    def test_queued_becomes_running_before_population_and_solver(self):
        run = self._run()
        observed = []

        def inspect(call):
            observed.append(
                AllocationRun.objects.filter(pk=call['kwargs']['allocation_run_id'])
                .values_list('status', flat=True).first()
            )
            return {}

        harness = _Harness(solver_behavior=inspect)
        with CaptureQueriesContext(connection) as queries:
            self._execute(harness, run)
        captured = [query['sql'] for query in queries.captured_queries]
        self.assertEqual(observed, [AllocationRun.Status.RUNNING])

        running_index = next(
            index for index, sql in enumerate(captured)
            if sql.startswith('UPDATE "api_allocationrun" SET "status"') and "'running'" in sql
        )
        first_student_read = next(
            index for index, sql in enumerate(captured)
            if sql.startswith('SELECT') and 'FROM "api_student"' in sql
        )
        self.assertLess(running_index, first_student_read)


class WorkerSolverArgumentTests(OrchestrationFixtures):
    def _call_for(self, **execute_kwargs):
        harness = _Harness(solver_behavior=lambda call: {})
        self._execute(harness, self._run(), **execute_kwargs)
        self.assertEqual(len(harness.solver_calls), 1)
        return harness.solver_calls[0]

    def test_default_excludes_assigned_leaving_accessibility_and_other_regions(self):
        call = self._call_for()
        self.assertEqual(call['student_ids'], self.default_ids)
        self.assertEqual(call['room_ids'], self.active_room_ids)
        self.assertIsNone(call['kwargs']['max_seconds'])

    def test_include_assigned_true_adds_already_assigned_students(self):
        call = self._call_for(include_assigned=True)
        self.assertEqual(call['student_ids'], sorted(self.default_ids + [self.assigned_student.id]))

    def test_new_transfer_only_scope_keeps_only_new_and_transfer_categories(self):
        call = self._call_for(allocation_scope='new_transfer_only')
        self.assertEqual(call['student_ids'], sorted([self.new_student.id, self.transfer_student.id]))

    def test_unknown_scope_value_is_ignored(self):
        call = self._call_for(allocation_scope='something_else')
        self.assertEqual(call['student_ids'], self.default_ids)

    def test_population_summary_reports_the_exact_solver_input(self):
        harness = _Harness(solver_behavior=lambda call: {'successful_assignments': 1, 'conflicts': 1})
        self._execute(harness, self._run(), allocation_scope='new_transfer_only')
        population = harness.worker_writes()[1]['diagnostics']['population_summary']
        expected_ids = sorted([self.new_student.id, self.transfer_student.id])
        self.assertEqual(self._normalized_population(population), self._population(expected_ids, 1, 1))


class WorkerEarlyExitTests(OrchestrationFixtures):
    def test_zero_eligible_students_completes_without_solver(self):
        Student.objects.filter(
            pk__in=[self.new_student.pk, self.transfer_student.pk, self.continuing_student.pk],
        ).update(accessibility_flag=True)
        run = self._run()
        harness = _Harness()
        self._execute(harness, run)

        self.assertEqual(harness.solver_calls, [])
        writes = harness.worker_writes()
        self.assertEqual(len(writes), 2)
        self.assertEqual(writes[0], {'status': AllocationRun.Status.RUNNING})
        self.assertEqual(
            list(writes[1]),
            ['status', 'students_processed', 'successful_assignments', 'roommate_matches',
             'conflicts', 'completed_at', 'diagnostics'],
        )
        diagnostics = writes[1]['diagnostics']
        self.assertEqual(list(diagnostics), ['warnings', 'anier_building_179_diagnostics', 'population_summary'])
        self.assertEqual(diagnostics['warnings'], [])
        self.assertEqual(diagnostics['anier_building_179_diagnostics'], dict(EMPTY_ANIER_BUILDING_179_DIAGNOSTICS))
        self.assertEqual(diagnostics['population_summary'], {
            'imported_students': 7,
            'excluded_accessibility': 5,
            'excluded_leaving': 2,
            'excluded_overlap': 1,
            'excluded_total': 6,
            'sent_to_solver': 0,
            'sent_to_solver_student_ids': [],
            'assigned': 0,
            'unassigned': 0,
        })
        self.assertEqual(
            {key: writes[1][key] for key in writes[1] if key != 'diagnostics'},
            {
                'status': AllocationRun.Status.COMPLETED,
                'students_processed': 0,
                'successful_assignments': 0,
                'roommate_matches': 0,
                'conflicts': 0,
                'completed_at': DT,
            },
        )

        run.refresh_from_db()
        self.assertEqual(run.status, AllocationRun.Status.COMPLETED)
        self.assertIsNotNone(run.completed_at)
        # Current behavior: this early return does not touch live_snapshot.
        self.assertEqual(run.live_snapshot, {'sequence': 1})

    def test_zero_active_rooms_fails_without_solver(self):
        Room.objects.filter(pk__in=[self.room_1.pk, self.room_2.pk]).update(is_active=False)
        run = self._run()
        harness = _Harness()
        self._execute(harness, run)

        self.assertEqual(harness.solver_calls, [])
        writes = harness.worker_writes()
        self.assertEqual(len(writes), 2)
        self.assertEqual(writes[0], {'status': AllocationRun.Status.RUNNING})
        self.assertEqual(list(writes[1]), ['status', 'error_message', 'completed_at', 'diagnostics'])
        self.assertEqual(writes[1]['status'], AllocationRun.Status.FAILED)
        self.assertEqual(writes[1]['error_message'], NO_ROOMS_ERROR)
        self.assertIs(writes[1]['completed_at'], DT)
        diagnostics = writes[1]['diagnostics']
        self.assertEqual(list(diagnostics), ['warnings', 'anier_building_179_diagnostics', 'population_summary'])
        self.assertEqual(diagnostics['warnings'], [])
        self.assertEqual(diagnostics['anier_building_179_diagnostics'], dict(EMPTY_ANIER_BUILDING_179_DIAGNOSTICS))
        self.assertEqual(
            self._normalized_population(diagnostics['population_summary']),
            self._population(self.default_ids, assigned=0, unassigned=0),
        )

        run.refresh_from_db()
        self.assertEqual(run.status, AllocationRun.Status.FAILED)
        self.assertEqual(run.error_message, NO_ROOMS_ERROR)
        self.assertIsNotNone(run.completed_at)
        self.assertEqual(run.live_snapshot, {'sequence': 1})

    def test_pre_start_cancellation_stops_without_running(self):
        run = self._run(status=AllocationRun.Status.CANCELLATION_REQUESTED)
        assignments_before = list(BedAssignment.objects.order_by('pk').values())
        students_before = list(Student.objects.order_by('pk').values('pk', 'assigned_room_id'))
        harness = _Harness()
        self._execute(harness, run)

        self.assertEqual(harness.solver_calls, [])
        self.assertEqual(harness.worker_writes(), [
            {'status': AllocationRun.Status.STOPPED, 'completed_at': DT},
        ])
        run.refresh_from_db()
        self.assertEqual(run.status, AllocationRun.Status.STOPPED)
        self.assertIsNotNone(run.completed_at)
        self.assertEqual(run.live_snapshot, {'sequence': 1})
        self.assertEqual(list(BedAssignment.objects.order_by('pk').values()), assignments_before)
        self.assertEqual(list(Student.objects.order_by('pk').values('pk', 'assigned_room_id')), students_before)


class WorkerExceptionTests(OrchestrationFixtures):
    def test_solver_exception_marks_failed_with_truncated_message(self):
        long_message = 'x' * 5000 + 'TAIL-BEYOND-5000'

        def boom(call):
            raise RuntimeError(long_message)

        run = self._run()
        harness = _Harness(solver_behavior=boom)
        returned = self._execute(harness, run)
        self.assertIsNone(returned)

        writes = harness.worker_writes()
        self.assertEqual(len(writes), 2)
        self.assertEqual(writes[0], {'status': AllocationRun.Status.RUNNING})
        self.assertEqual(writes[1], {
            'status': AllocationRun.Status.FAILED,
            'error_message': 'x' * 5000,
            'completed_at': DT,
            'live_snapshot': None,
        })
        self.assertEqual(harness.connection_close_mock.call_count, 1)

        run.refresh_from_db()
        self.assertEqual(run.status, AllocationRun.Status.FAILED)
        self.assertEqual(run.error_message, 'x' * 5000)
        self.assertIsNotNone(run.completed_at)
        self.assertIsNone(run.live_snapshot)
        self.assertEqual(run.diagnostics, {})


class WorkerPostSolveBranchTests(OrchestrationFixtures):
    def test_cancellation_cleans_up_real_assignments_and_stops(self):
        run = self._run()
        unrelated_bed_id = self.assigned_assignment.bed_id

        def solve_then_cancel(call):
            self._assign_in_fake(run, [self.new_student, self.transfer_student])
            AllocationRun.objects.filter(pk=run.id).update(status=AllocationRun.Status.CANCELLATION_REQUESTED)
            return {'solution_persisted': True, 'successful_assignments': 2, 'conflicts': 1}

        harness = _Harness(solver_behavior=solve_then_cancel)
        self.assertEqual(
            BedAssignment.objects.filter(allocation_run=run).count(), 0,
        )
        self._execute(harness, run)

        writes = harness.worker_writes()
        self.assertEqual(len(writes), 4)
        self.assertEqual(writes[0], {'status': AllocationRun.Status.RUNNING})
        self.assertEqual(list(writes[1]), ['diagnostics'])
        self.assertEqual(writes[2], {'status': AllocationRun.Status.STOPPED, 'completed_at': DT})
        self.assertEqual(writes[3], {'live_snapshot': None})

        run_assignments = BedAssignment.objects.filter(allocation_run=run)
        self.assertEqual(run_assignments.count(), 2)
        self.assertEqual(
            set(run_assignments.values_list('status', flat=True)), {BedAssignment.Status.CANCELLED},
        )
        self.assertTrue(all(run_assignments.values_list('ended_at', flat=True)))
        self.assertFalse(run_assignments.filter(status=BedAssignment.Status.ACTIVE).exists())
        for student in (self.new_student, self.transfer_student):
            student.refresh_from_db()
            self.assertIsNone(student.assigned_room_id)

        self.assigned_assignment.refresh_from_db()
        self.assertEqual(self.assigned_assignment.status, BedAssignment.Status.ACTIVE)
        self.assertEqual(self.assigned_assignment.bed_id, unrelated_bed_id)
        self.assigned_student.refresh_from_db()
        self.assertEqual(self.assigned_student.assigned_room_id, self.room_1.id)

        run.refresh_from_db()
        self.assertEqual(run.status, AllocationRun.Status.STOPPED)
        self.assertIsNotNone(run.completed_at)
        self.assertIsNone(run.live_snapshot)

    def test_stop_and_save_without_persisted_solution_replaces_diagnostics(self):
        run = self._run()

        def stop_without_solution(call):
            AllocationRun.objects.filter(pk=run.id).update(status=AllocationRun.Status.STOP_AND_SAVE_REQUESTED)
            return {
                'solution_persisted': False,
                'solver_status': 'UNKNOWN',
                'students_processed': 3,
                'successful_assignments': 0,
                'conflicts': 3,
                'warnings': ['solver-warning'],
                'anier_building_179_diagnostics': {'imported_anier_students': 9},
            }

        harness = _Harness(solver_behavior=stop_without_solution)
        self._execute(harness, run)

        writes = harness.worker_writes()
        self.assertEqual(len(writes), 3)
        self.assertEqual(writes[0], {'status': AllocationRun.Status.RUNNING})
        self.assertEqual(writes[1]['diagnostics']['warnings'], ['solver-warning'])
        self.assertEqual(list(writes[2]), ['status', 'completed_at', 'live_snapshot', 'diagnostics'])
        self.assertEqual(writes[2]['status'], AllocationRun.Status.STOPPED)
        self.assertIs(writes[2]['completed_at'], DT)
        self.assertIsNone(writes[2]['live_snapshot'])
        self.assertEqual(list(writes[2]['diagnostics']), ['warnings', 'anier_building_179_diagnostics', 'stop_reason'])
        self.assertEqual(writes[2]['diagnostics'], {
            'warnings': [],
            'anier_building_179_diagnostics': dict(EMPTY_ANIER_BUILDING_179_DIAGNOSTICS),
            'stop_reason': STOP_REASON,
        })

        run.refresh_from_db()
        self.assertEqual(run.status, AllocationRun.Status.STOPPED)
        self.assertIsNotNone(run.completed_at)
        self.assertIsNone(run.live_snapshot)
        self.assertNotIn('population_summary', run.diagnostics)
        self.assertEqual(run.diagnostics['stop_reason'], STOP_REASON)
        self.assertEqual(
            (run.students_processed, run.successful_assignments, run.roommate_matches, run.conflicts),
            (0, 0, 0, 0),
        )
        self.assertEqual(BedAssignment.objects.filter(allocation_run=run).count(), 0)

    def test_stop_and_save_with_persisted_solution_completes_and_flags_early_stop(self):
        run = self._run()

        def stop_with_solution(call):
            self._assign_in_fake(run, [self.new_student])
            AllocationRun.objects.filter(pk=run.id).update(status=AllocationRun.Status.STOP_AND_SAVE_REQUESTED)
            return {
                'solution_persisted': True,
                'solver_status': 'FEASIBLE',
                'optimality_proven': False,
                'objective_value': 4.0,
                'students_processed': 3,
                'successful_assignments': 1,
                'conflicts': 2,
                'roommate_matches': 0,
                'warnings': [],
                'anier_building_179_diagnostics': {},
            }

        harness = _Harness(solver_behavior=stop_with_solution)
        self._execute(harness, run)

        writes = harness.worker_writes()
        self.assertEqual(len(writes), 3)
        final = writes[2]
        self.assertEqual(
            list(final),
            ['status', 'students_processed', 'successful_assignments', 'roommate_matches',
             'conflicts', 'completed_at', 'live_snapshot', 'diagnostics'],
        )
        self.assertEqual(
            {key: final[key] for key in final if key != 'diagnostics'},
            {
                'status': AllocationRun.Status.COMPLETED,
                'students_processed': 3,
                'successful_assignments': 1,
                'roommate_matches': 0,
                'conflicts': 2,
                'completed_at': DT,
                'live_snapshot': None,
            },
        )
        self.assertEqual(
            list(final['diagnostics']), DIAGNOSTICS_KEYS + ['population_summary', 'stopped_early_by_user'],
        )
        self.assertIs(final['diagnostics']['stopped_early_by_user'], True)
        self.assertEqual(final['diagnostics']['solver_status'], 'FEASIBLE')
        self.assertIs(final['diagnostics']['optimality_proven'], False)
        self.assertEqual(
            self._normalized_population(final['diagnostics']['population_summary']),
            self._population(self.default_ids, assigned=1, unassigned=2),
        )
        # The diagnostics written before the stop branch are identical apart
        # from the extra flag.
        self.assertEqual(
            {key: value for key, value in final['diagnostics'].items() if key != 'stopped_early_by_user'},
            writes[1]['diagnostics'],
        )

        run.refresh_from_db()
        self.assertEqual(run.status, AllocationRun.Status.COMPLETED)
        self.assertIsNotNone(run.completed_at)
        self.assertIsNone(run.live_snapshot)
        self.assertTrue(run.diagnostics['stopped_early_by_user'])
        self.assertEqual(
            list(BedAssignment.objects.filter(allocation_run=run).values_list('status', flat=True)),
            [BedAssignment.Status.ACTIVE],
        )


class DiagnosticsPayloadTests(TestCase):
    def test_dict_result_exact_keys_values_and_fallbacks(self):
        full = {
            'warnings': ['a'],
            'anier_building_179_diagnostics': {'k': 1},
            'solver_status': 'OPTIMAL',
            'optimality_proven': 1,
            'objective_value': 3,
            'best_objective_bound': 2,
            'absolute_gap': 1,
            'relative_gap': 0.5,
            'ignored_extra_key': 'x',
        }
        payload = api_views._run_diagnostics_payload(full)
        self.assertEqual(list(payload), DIAGNOSTICS_KEYS)
        self.assertEqual(payload, {
            'warnings': ['a'],
            'anier_building_179_diagnostics': {'k': 1},
            'solver_status': 'OPTIMAL',
            'optimality_proven': True,
            'objective_value': 3,
            'best_objective_bound': 2,
            'absolute_gap': 1,
            'relative_gap': 0.5,
        })
        self.assertIs(payload['warnings'], full['warnings'])

        empty = api_views._run_diagnostics_payload({})
        self.assertEqual(list(empty), DIAGNOSTICS_KEYS)
        self.assertEqual(empty, {
            'warnings': [],
            'anier_building_179_diagnostics': {},
            'solver_status': None,
            'optimality_proven': False,
            'objective_value': None,
            'best_objective_bound': None,
            'absolute_gap': None,
            'relative_gap': None,
        })

    def test_non_dict_result_returns_exact_default_payload(self):
        expected = {
            'warnings': [],
            'anier_building_179_diagnostics': {},
            'solver_status': None,
            'optimality_proven': False,
            'objective_value': None,
            'best_objective_bound': None,
            'absolute_gap': None,
            'relative_gap': None,
        }
        for value in (None, [], ['not', 'a', 'dict'], 'text', 0):
            payload = api_views._run_diagnostics_payload(value)
            self.assertEqual(list(payload), DIAGNOSTICS_KEYS, value)
            self.assertEqual(payload, expected, value)


class SolverPopulationHelperTests(OrchestrationFixtures):
    def test_exclude_non_solver_students_is_lazy_and_excludes_leaving_and_accessibility(self):
        source = Student.objects.filter(accepted_dorm_type__region=self.region)
        with CaptureQueriesContext(connection) as queries:
            result = api_views._exclude_non_solver_students(source)
        self.assertEqual(len(queries.captured_queries), 0)
        self.assertIsInstance(result, QuerySet)
        self.assertIsNot(result, source)
        self.assertIsNone(source._result_cache)
        self.assertEqual(
            sorted(result.values_list('id', flat=True)),
            sorted(self.default_ids + [self.assigned_student.id]),
        )
        self.assertEqual(source.count(), 7)

    def test_population_summary_without_supplied_ids(self):
        summary = api_views._population_summary_for_region(self.region)
        self.assertEqual(list(summary), POPULATION_KEYS)
        self.assertIsInstance(summary['sent_to_solver_student_ids'], list)
        self.assertEqual(
            {key: summary[key] for key in POPULATION_KEYS if key != 'sent_to_solver_student_ids'},
            {
                'imported_students': 7,
                'excluded_accessibility': 2,
                'excluded_leaving': 2,
                'excluded_overlap': 1,
                'excluded_total': 3,
                'sent_to_solver': 3,
            },
        )
        self.assertEqual(sorted(summary['sent_to_solver_student_ids']), self.default_ids)
        for key in POPULATION_KEYS[:-1]:
            self.assertIs(type(summary[key]), int, key)
        self.assertNotIn('assigned', summary)
        self.assertNotIn('unassigned', summary)

    def test_population_summary_with_supplied_ids_passes_them_through_as_list(self):
        supplied = (self.new_student.id, 999999)
        summary = api_views._population_summary_for_region(self.region, sent_to_solver_student_ids=supplied)
        self.assertEqual(list(summary), POPULATION_KEYS)
        self.assertEqual(summary['sent_to_solver_student_ids'], [self.new_student.id, 999999])
        self.assertIs(type(summary['sent_to_solver_student_ids']), list)
        self.assertEqual(summary['sent_to_solver'], 2)
        self.assertEqual(summary['imported_students'], 7)

        empty = api_views._population_summary_for_region(self.region, sent_to_solver_student_ids=[])
        self.assertEqual(empty['sent_to_solver_student_ids'], [])
        self.assertEqual(empty['sent_to_solver'], 0)


class StartAllocationRunWorkerKwargsTests(OrchestrationFixtures):
    """
    Since R8 the start request stores the run body's parameters on the
    durable AllocationRun (job_parameters) instead of handing them to a
    request-owned thread; the same values, the same types, the same QUEUED
    status at the moment the request returns.
    """

    def _start(self, payload):
        client = APIClient()
        client.force_authenticate(user=self.boss)
        with patch('threading.Thread') as thread, \
                patch('api.domains.allocation.orchestration.execute_allocation_run') as execute:
            response = client.post('/api/allocation/start/', payload, format='json')
        thread.assert_not_called()
        execute.assert_not_called()
        self.assertEqual(response.status_code, 202, response.data)
        run = AllocationRun.objects.get(pk=response.data['run_id'])
        return response, run

    def test_default_request_kwargs(self):
        response, run = self._start({'region': self.region.id})
        self.assertEqual(run.region_id, self.region.id)
        self.assertEqual(run.job_parameters, {
            'constraints_config': normalize_allocation_constraints(None),
            'include_assigned': False,
            'allocation_scope': None,
            'max_seconds': DEFAULT_SOLVER_TIME_SECONDS,
        })
        self.assertIs(type(run.job_parameters['max_seconds']), type(DEFAULT_SOLVER_TIME_SECONDS))
        self.assertEqual(run.max_search_seconds, DEFAULT_SOLVER_TIME_SECONDS)
        self.assertEqual(run.status, AllocationRun.Status.QUEUED)
        self.assertEqual((run.claimed_by, run.lease_expires_at, run.attempts), ('', None, 0))

    def test_explicit_request_kwargs(self):
        constraints = {'sameReligion': {'enabled': False}}
        response, run = self._start({
            'region': self.region.id,
            'include_assigned': True,
            'allocation_scope': 'new_transfer_only',
            'constraints': constraints,
            'max_solver_seconds': '90',
        })
        self.assertEqual(run.job_parameters, {
            'constraints_config': normalize_allocation_constraints(constraints),
            'include_assigned': True,
            'allocation_scope': 'new_transfer_only',
            'max_seconds': 90.0,
        })
        self.assertIs(type(run.job_parameters['max_seconds']), float)
        self.assertEqual(run.max_search_seconds, 90)
        self.assertEqual(run.status, AllocationRun.Status.QUEUED)

    def test_include_assigned_requires_literal_true(self):
        response, run = self._start({'region': self.region.id, 'include_assigned': 'true'})
        self.assertIs(run.job_parameters['include_assigned'], False)


class PatchTransparencyTests(OrchestrationFixtures):
    def test_shared_patches_are_observed_through_api_views(self):
        harness = _Harness(solver_behavior=lambda call: {})
        run = self._run()
        with harness.active():
            api_views.execute_allocation_run(
                allocation_run_id=run.id, region_id=self.region.id, constraints_config={},
                include_assigned=False, allocation_scope=None, max_seconds=30,
            )
        # The run body constructs no thread of its own any more (R8: the
        # durable worker executes it on the calling thread).
        self.assertEqual(harness.threads, [])
        self.assertEqual(len(harness.solver_calls), 1)
        self.assertEqual(harness.close_old_mock.call_count, 2)
        self.assertEqual(harness.connection_close_mock.call_count, 1)
        run.refresh_from_db()
        self.assertEqual(run.status, AllocationRun.Status.COMPLETED)

    def test_run_body_reached_through_api_views_is_the_orchestration_object(self):
        import importlib

        orchestration = importlib.import_module('api.domains.allocation.orchestration')
        self.assertIs(api_views.execute_allocation_run, orchestration.execute_allocation_run)
