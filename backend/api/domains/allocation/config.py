"""
Allocation constraint configuration.

HARD_ALLOCATION_CONSTRAINTS lists the always-on hard constraint keys,
SOFT_ALLOCATION_CONSTRAINTS maps each optional soft constraint key to its
default weight, and normalize_allocation_constraints() turns a request's
constraint settings into the normalized configuration for an allocation run.
The api.views compatibility facade (api/views/__init__.py) imports all
three names from here, so references through the api.views namespace keep
resolving to these same objects.
"""

HARD_ALLOCATION_CONSTRAINTS = {
    'sameGender',
    'priorityFirst',
    'roommatePositiveOnly',
    'ReligiousTogether',
}

SOFT_ALLOCATION_CONSTRAINTS = {
    'sameReligion': 6,
    'roommateMatch': 8,
    'sectorMatching': 7,
    'avoidYearMix_1_with_3_4': 4,
    'avoidAtudaimWithHasmaha': 4,
}


def normalize_allocation_constraints(raw_config):
    """
    Normalize the frontend allocation configuration before passing it to
    the solver. Hard constraints are always active and weightless, while
    optimization preferences remain optional and weighted.
    """
    if not isinstance(raw_config, dict):
        raw_config = {}

    normalized = {}

    for key in HARD_ALLOCATION_CONSTRAINTS:
        normalized[key] = {
            'enabled': True,
            'strict': True,
            'critical': True,
            'weight': 0,
        }

    for key, default_weight in SOFT_ALLOCATION_CONSTRAINTS.items():
        raw_value = raw_config.get(key, {})
        if not isinstance(raw_value, dict):
            raw_value = {}

        enabled = bool(raw_value.get('enabled', True))

        try:
            weight = int(raw_value.get('weight', default_weight))
        except (TypeError, ValueError):
            weight = default_weight

        normalized[key] = {
            'enabled': enabled,
            'strict': False,
            'critical': False,
            'weight': max(0, min(weight, 10)),
        }

    return normalized


# Legacy per-region allocation conditions (the unrouted allocation_conditions
# endpoint). DEFAULT_CONDITIONS is the catalogue; _CONDITIONS_STORE is the
# in-memory store keyed by region id (or '__global__').
_CONDITIONS_STORE = {}

DEFAULT_CONDITIONS = {
    'sameGender':              {'enabled': True,  'strict': True,  'critical': True,  'weight': 0},
    'priorityFirst':           {'enabled': True,  'strict': True,  'critical': True,  'weight': 0},
    'roommatePositiveOnly':    {'enabled': True,  'strict': True,  'critical': True,  'weight': 0},
    'ReligiousTogether':       {'enabled': True,  'strict': True,  'critical': True,  'weight': 0},
    'sameReligion':            {'enabled': True,  'strict': False, 'critical': False, 'weight': 6},
    'roommateMatch':           {'enabled': True,  'strict': False, 'critical': False, 'weight': 8},
    'sectorMatching':          {'enabled': True,  'strict': False, 'critical': False, 'weight': 7},
    'avoidYearMix_1_with_3_4': {'enabled': True,  'strict': False, 'critical': False, 'weight': 4},
    'avoidAtudaimWithHasmaha': {'enabled': True,  'strict': False, 'critical': False, 'weight': 4},
}


def sanitize_allocation_conditions(incoming):
    """
    Normalize a conditions update for the legacy in-memory store: critical
    conditions stay enabled, strict and weightless; the rest keep their
    submitted enabled/strict flags with the weight clamped to 0..10.
    Non-dict entries are dropped.
    """
    validated = {}
    for key, value in incoming.items():
        if not isinstance(value, dict):
            continue
        is_critical = DEFAULT_CONDITIONS.get(key, {}).get('critical', False)
        validated[key] = {
            'enabled': True if is_critical else bool(value.get('enabled', True)),
            'strict': bool(value.get('strict', is_critical)),
            'critical': is_critical,
            'weight': 0 if is_critical else max(0, min(10, int(value.get('weight', 5)))),
        }
    return validated
