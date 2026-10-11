"""
Allocation-engine boundary: what the solver receives, the one place that
invokes it, and the typed view of what it returns.

The OR-Tools model itself lives in ``allocation.solver``; nothing here
changes how it solves. This module only makes the handover explicit:

``SolverInput``     the complete, typed argument set of
                    ``run_improved_ortools_allocation`` as the three entry
                    points (synchronous run, retry-unassigned, background
                    worker) use it. The student and room querysets are
                    handed over as querysets - the solver materializes them
                    with its own ``select_related``/``prefetch_related`` -
                    and ``constraints_config`` is the dict returned by
                    ``config.normalize_allocation_constraints``, passed
                    through by identity.
``invoke_solver``   the single call site. It resolves the solver through the
                    lazy gateway at call time, so ``allocation.solver`` is
                    never imported before a run actually starts and a patch
                    of ``allocation.solver.run_improved_ortools_allocation``
                    is honoured.
``SolverOutcome``   read access to the solver's result dict with the exact
                    fallbacks every caller applied by hand before
                    (``successful_assignments`` defaults to 0, the roommate
                    total falls back to mutual + one-sided only when the
                    solver gave no explicit value, ...). The raw dict stays
                    available as ``raw``: the HTTP layer maps it unchanged.

No HTTP or DRF object ever crosses this boundary, and nothing here touches
the database.
"""

from dataclasses import dataclass

# Keys and order of the diagnostics block persisted on AllocationRun for a
# solved run (followed by 'population_summary' and the per-path markers).
RUN_DIAGNOSTICS_KEYS = (
    'warnings',
    'anier_building_179_diagnostics',
    'solver_status',
    'optimality_proven',
    'objective_value',
    'best_objective_bound',
    'absolute_gap',
    'relative_gap',
)


@dataclass(frozen=True)
class SolverInput:
    """
    The argument set of one ``run_improved_ortools_allocation`` call.

    students / rooms            - the exact querysets (or lists) the solver
                                  materializes; see inputs.SolverPopulation.
    constraints_config          - normalized constraint configuration dict.
    allocation_run_id           - the run the solver tags persisted
                                  assignments with and publishes live
                                  previews / honours stop requests for; None
                                  disables all of that (synchronous legacy
                                  endpoint, management command).
    max_seconds                 - maximum search time; None means the
                                  solver's own DEFAULT_SOLVER_TIME_SECONDS.
    enable_group_capacity_cuts  - always True for application runs.
    persistence_guard           - optional callable the solver invokes inside
                                  its persistence transaction before writing
                                  any assignment (the durable worker's claim
                                  fence, see fencing.ClaimFence); None - the
                                  synchronous and retry paths - leaves the
                                  solver call exactly as before.
    run_ownership_filter        - optional row lookups (the durable worker's
                                  claim generation) the solver applies to its
                                  own run-row writes and its stop watcher;
                                  None leaves the solver call as before.
    """

    students: object
    rooms: object
    constraints_config: dict
    allocation_run_id: object = None
    max_seconds: object = None
    enable_group_capacity_cuts: bool = True
    persistence_guard: object = None
    run_ownership_filter: object = None

    def solver_kwargs(self):
        """
        The keyword arguments handed to the solver: always the six-key set,
        plus ``persistence_guard`` / ``run_ownership_filter`` only when a
        fence supplied them.
        """
        kwargs = {
            'students': self.students,
            'rooms': self.rooms,
            'constraints_config': self.constraints_config,
            'allocation_run_id': self.allocation_run_id,
            'max_seconds': self.max_seconds,
            'enable_group_capacity_cuts': self.enable_group_capacity_cuts,
        }
        if self.persistence_guard is not None:
            kwargs['persistence_guard'] = self.persistence_guard
        if self.run_ownership_filter is not None:
            kwargs['run_ownership_filter'] = self.run_ownership_filter
        return kwargs


def invoke_solver(solver_input):
    """
    Run the OR-Tools allocation for ``solver_input`` and return its raw
    result dict (an empty dict when the solver returned nothing).
    """
    from .gateway import run_improved_ortools_allocation

    return run_improved_ortools_allocation(**solver_input.solver_kwargs()) or {}


def run_diagnostics_payload(result):
    """
    The solver-derived part of AllocationRun.diagnostics, in its persisted
    key order. A non-dict result yields the empty payload.
    """
    if not isinstance(result, dict):
        return {
            'warnings': [],
            'anier_building_179_diagnostics': {},
            'solver_status': None,
            'optimality_proven': False,
            'objective_value': None,
            'best_objective_bound': None,
            'absolute_gap': None,
            'relative_gap': None,
        }
    return {
        'warnings': result.get('warnings', []),
        'anier_building_179_diagnostics': result.get('anier_building_179_diagnostics', {}),
        'solver_status': result.get('solver_status'),
        'optimality_proven': bool(result.get('optimality_proven', False)),
        'objective_value': result.get('objective_value'),
        'best_objective_bound': result.get('best_objective_bound'),
        'absolute_gap': result.get('absolute_gap'),
        'relative_gap': result.get('relative_gap'),
    }


@dataclass(frozen=True)
class SolverOutcome:
    """
    Typed read access to a solver result dict. Every accessor applies the
    exact default the entry points used; ``raw`` is the dict itself.
    """

    raw: dict

    @classmethod
    def from_result(cls, result):
        """Wrap a solver return value; None becomes an empty result."""
        return cls(result if result is not None else {})

    def students_processed(self, default):
        """Students the solver processed, or ``default`` when it did not report it."""
        return self.raw.get('students_processed', default)

    @property
    def successful_assignments(self):
        return self.raw.get('successful_assignments', 0)

    @property
    def conflicts(self):
        return self.raw.get('conflicts', 0)

    @property
    def roommate_matches(self):
        """
        The solver's explicit roommate total; only when it gave none, the
        sum of its mutual and one-sided counts (an explicit 0 is kept).
        """
        roommate_matches = self.raw.get('roommate_matches')
        if roommate_matches is None:
            roommate_matches = (
                self.raw.get('mutual_roommate_matches', 0)
                + self.raw.get('one_sided_roommate_matches', 0)
            )
        return roommate_matches

    @property
    def solver_status(self):
        return self.raw.get('solver_status')

    @property
    def solution_persisted(self):
        """Whether the solver committed assignments (truthy flag, as the worker reads it)."""
        return bool(self.raw.get('solution_persisted'))

    @property
    def warnings(self):
        return self.raw.get('warnings', [])

    @property
    def anier_building_179_diagnostics(self):
        return self.raw.get('anier_building_179_diagnostics', {})

    def diagnostics_payload(self):
        """``run_diagnostics_payload`` of this result."""
        return run_diagnostics_payload(self.raw)
