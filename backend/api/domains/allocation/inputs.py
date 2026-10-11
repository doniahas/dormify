"""
Allocation-input boundary: the one owner of the solver population and
inventory an application run is built from.

``load_solver_population`` composes the region's solver-eligible student
population and active inventory as querysets - it issues no query - and
``measure_population`` executes the fixed set of reads every run performs
before solving (the region total, the exact solver-input ids, the
population summary and the two counts), in one canonical order.

Both the synchronous run and the background worker previously built this
population inline with identical filters; this module is the shared
definition. The synchronous endpoint's sibling helpers in
``api.domains.allocation.queries`` remain the underlying querysets.
"""

from dataclasses import dataclass

from .orchestration import _population_summary_for_region
from .queries import solver_rooms_for_region, solver_students_for_region


@dataclass(frozen=True)
class SolverPopulation:
    """
    The querysets an application run hands to the solver, unevaluated.

    students_base - the region's solver-eligible population: accepted into a
                    dorm type of ``region``, leavers and accessibility
                    students excluded (``_exclude_non_solver_students``).
    students      - the subset actually sent to the solver after the
                    include_assigned / allocation_scope narrowing.
    rooms         - active rooms in active apartments and buildings of the
                    region, with beds prefetched.
    """

    region: object
    include_assigned: bool
    allocation_scope: object
    students_base: object
    students: object
    rooms: object


def load_solver_population(region, *, include_assigned=False, allocation_scope=None):
    """Compose the solver population and inventory of ``region`` (no query runs)."""
    students_base, students = solver_students_for_region(
        region, include_assigned=include_assigned, allocation_scope=allocation_scope,
    )
    return SolverPopulation(
        region=region,
        include_assigned=include_assigned,
        allocation_scope=allocation_scope,
        students_base=students_base,
        students=students,
        rooms=solver_rooms_for_region(region),
    )


@dataclass(frozen=True)
class PopulationSnapshot:
    """
    What a run records about its population before solving.

    students_total_in_region - size of ``students_base``.
    student_ids              - the exact ids sent to the solver, captured
                               before the solver updates assignments (the
                               response table, the persisted population
                               summary and retry-unassigned all describe
                               this run through these ids).
    students_count           - size of ``students``.
    rooms_count              - size of ``rooms``.
    population_summary       - ``_population_summary_for_region`` for these
                               ids (no 'assigned' / 'unassigned' yet).
    """

    students_total_in_region: int
    student_ids: list
    students_count: int
    rooms_count: int
    population_summary: dict


def measure_population(population):
    """
    Execute the pre-solve reads of ``population`` in the canonical order:
    region total, solver-input ids, population summary, students count,
    rooms count. The counts are taken before the solver runs so no query is
    needed after a long solve.
    """
    students_total_in_region = population.students_base.count()
    student_ids = list(population.students.values_list('id', flat=True))
    population_summary = _population_summary_for_region(
        population.region, sent_to_solver_student_ids=student_ids,
    )
    students_count = population.students.count()
    rooms_count = population.rooms.count()
    return PopulationSnapshot(
        students_total_in_region=students_total_in_region,
        student_ids=student_ids,
        students_count=students_count,
        rooms_count=rooms_count,
        population_summary=population_summary,
    )


def retry_population_summary(student_ids):
    """
    The population summary of a retry-unassigned run: the retried students
    ARE the population (they were already screened by the original run), so
    every exclusion count is zero. Intentionally not the region breakdown of
    ``_population_summary_for_region``.
    """
    student_ids = list(student_ids)
    return {
        'imported_students': len(student_ids),
        'excluded_accessibility': 0,
        'excluded_leaving': 0,
        'excluded_overlap': 0,
        'excluded_total': 0,
        'sent_to_solver': len(student_ids),
        'sent_to_solver_student_ids': student_ids,
    }
