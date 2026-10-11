"""
Boundary between the api layer and the allocation package.

The api layer reaches solver, manual-placement and live-registry
functionality only through the names listed here. Each name resolves,
when it is requested, to the current binding in its allocation module,
so no allocation module is imported before one of these names is used.
"""

_SOLVER_EXPORTS = frozenset({
    'run_improved_ortools_allocation',
    'analyze_unassigned_group',
    'MIN_USER_SOLVER_TIME_SECONDS',
    'MAX_USER_SOLVER_TIME_SECONDS',
    'DEFAULT_SOLVER_TIME_SECONDS',
    'EMPTY_ANIER_BUILDING_179_DIAGNOSTICS',
    '_housing_matches_apartment',
    '_effective_apartment_category',
    '_get_student_priority',
    '_has_anier_special_status',
    '_is_hasmaha_anier_student',
})

_MANUAL_PLACEMENT_EXPORTS = frozenset({
    'evaluate_manual_override',
    'find_configuration_opportunities',
    'has_unsafe_configuration_candidates',
    'religion_conflict_for_candidate',
    'OVERRIDE_VIOLATION_CONSEQUENCE',
})

__all__ = sorted(_SOLVER_EXPORTS | _MANUAL_PLACEMENT_EXPORTS | {'live_registry'})


def __getattr__(name):
    if name in _SOLVER_EXPORTS:
        from allocation import solver
        return getattr(solver, name)
    if name in _MANUAL_PLACEMENT_EXPORTS:
        from allocation import manual_placement
        return getattr(manual_placement, name)
    if name == 'live_registry':
        from allocation import live_registry
        return live_registry
    raise AttributeError(f'module {__name__!r} has no attribute {name!r}')


def __dir__():
    return sorted(set(globals()) | set(__all__))
