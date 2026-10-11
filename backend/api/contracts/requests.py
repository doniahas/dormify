"""
Typed parsers for the request bodies the thin views read by hand.

Each parser takes the request's ``data`` mapping (or query params) and
returns plain Python values, reproducing the endpoint's historical rules
exactly: which keys are read (and their aliases), what counts as absent,
what defaults apply and which message a rejection carries. A rejection is
``ValueError(<user-facing message>)``; the view maps it to the status code
and body it always answered with.

Nothing here touches the database or authorizes anything - region and
object resolution stay in the views.
"""

from dataclasses import dataclass

from ..domains.whatif.queries import TARGET_TYPES as WHATIF_TARGET_TYPES

ALLOCATION_SCOPE_NEW_TRANSFER_ONLY = 'new_transfer_only'


@dataclass(frozen=True)
class AllocationRunRequest:
    """
    Body of POST /api/allocation/run/ and /api/allocation/start/.

    region_value       - the first non-empty of ``region`` / ``region_id`` /
                         ``region_name`` (None when none is given); resolved
                         and authorized by the view.
    constraints        - the raw ``constraints`` value; the view normalizes it
                         with normalize_allocation_constraints (any non-dict
                         means "defaults").
    include_assigned   - True only for the JSON literal ``true``; the strings
                         'true' / '1' are deliberately NOT accepted, so a
                         full re-allocation can never be triggered by a
                         loosely typed client.
    allocation_scope   - the raw ``allocation_scope`` value; only
                         'new_transfer_only' narrows the population, anything
                         else is ignored.
    max_solver_seconds - the raw ``max_solver_seconds`` value (start only);
                         None / '' mean the solver default, anything else is
                         validated by parse_max_solver_seconds.
    """

    region_value: object
    constraints: object
    include_assigned: bool
    allocation_scope: object
    max_solver_seconds: object


def parse_allocation_run_request(data):
    return AllocationRunRequest(
        region_value=(
            data.get('region')
            or data.get('region_id')
            or data.get('region_name')
        ),
        constraints=data.get('constraints'),
        include_assigned=data.get('include_assigned') is True,
        allocation_scope=data.get('allocation_scope'),
        max_solver_seconds=data.get('max_solver_seconds'),
    )


def parse_building_ids(data):
    """``building_ids`` (alias ``buildings``): a non-empty list, as sent."""
    building_ids = data.get('building_ids') or data.get('buildings') or []

    if not isinstance(building_ids, list) or len(building_ids) == 0:
        raise ValueError('building_ids must be a non-empty list.')

    return building_ids


def parse_target_selection(data):
    """
    ``target_type`` (default 'building') and ``target_ids``: a non-empty
    list, de-duplicated (order not guaranteed, as before). Returns
    ``(target_type, target_ids)``.
    """
    target_type = data.get('target_type') or 'building'
    target_ids = data.get('target_ids') or []

    if target_type not in WHATIF_TARGET_TYPES:
        raise ValueError('target_type must be one of: building, apartment, room.')

    if not isinstance(target_ids, list) or len(target_ids) == 0:
        raise ValueError('target_ids must be a non-empty list.')

    return target_type, list(set(target_ids))


def parse_availability_action(data):
    """``action``: 'inactivate' (default) or 'reactivate'."""
    action = data.get('action') or 'inactivate'

    if action not in ['inactivate', 'reactivate']:
        raise ValueError('action must be inactivate or reactivate.')

    return action


def student_reference(data, key='student_id'):
    """The student reference (``student_id`` or ``student``): a PK or a student number."""
    value = data.get(key) or data.get('student')
    if not value:
        raise ValueError('Missing student_id')
    return value


def room_reference(data, key='room_id'):
    """The room reference (``room_id`` or ``room``): a PK."""
    value = data.get(key) or data.get('room')
    if not value:
        raise ValueError('Missing room_id')
    return value


def swap_pair(data):
    """The two student references of a swap (snake_case or camelCase keys); either may be empty."""
    return (
        data.get('student_a_id') or data.get('studentAId'),
        data.get('student_b_id') or data.get('studentBId'),
    )


def parse_match_pagination(source):
    """
    ``limit`` (default 10, clamped to 1..20) and ``offset`` (default 0,
    floored at 0) of the match-options / feasibility endpoints. They count
    BUILDINGS, not beds. A non-numeric value falls back to its default.
    """
    try:
        limit = int(source.get('limit', 10))
    except (TypeError, ValueError):
        limit = 10
    try:
        offset = int(source.get('offset', 0))
    except (TypeError, ValueError):
        offset = 0
    return max(1, min(limit, 20)), max(0, offset)


def parse_region_ids(raw_region_ids):
    """``region_ids`` of match-options: a scalar becomes a one-item list; empty values are dropped."""
    if raw_region_ids is None:
        raw_region_ids = []
    elif not isinstance(raw_region_ids, (list, tuple)):
        raw_region_ids = [raw_region_ids]
    return [r for r in raw_region_ids if r]


def parse_override_request(data):
    """``bed_id`` (as sent) and the stripped ``note`` of an assisted override."""
    return data.get('bed_id'), (data.get('note') or '').strip()
