"""
Assisted Allocation write services: manual placement (with and without a
rule override), each leaving an AssistedAllocationAudit record with the
before/after placement snapshot.
"""

from ...models import AssistedAllocationAudit, BedAssignment
from ..placement.services import assign_student_to_room
from ..transfers.services import _assignment_snapshot


def manual_override_violations(student, room):
    """Server-side evaluation of the rules a placement would break."""
    from ..allocation.gateway import evaluate_manual_override
    return evaluate_manual_override(student, room)


def blocking_violations(violations):
    """
    Structural violations (gender / housing type / building / dorm-type
    eligibility) can never be overridden, by anyone, for any reason.
    """
    return [v for v in violations if not v['overridable']]


def override_check(student, room):
    """The override-check payload: violations, whether the placement is blocked, whether a note is needed."""
    violations = manual_override_violations(student, room)
    blocked = any(not v['overridable'] for v in violations)
    overridable_violations = [v for v in violations if v['overridable']]
    return {
        'violations': violations,
        # blocked: at least one violation is structural - this placement
        # can never be confirmed, with or without an override note.
        'blocked': blocked,
        # requires_override: compatible except for administrative
        # (religion/reserved) violations an authorized admin may knowingly
        # waive with a documented reason.
        'requires_override': (not blocked) and bool(overridable_violations),
    }


def record_manual_assignment(student, room, bed, actor):
    """
    Place an unassigned student on ``bed`` with full rule validation and
    record a MANUAL_ASSIGNMENT audit entry. ValueError / ValidationError
    from the placement rules propagate unchanged.
    """
    previous_state = _assignment_snapshot(student)

    assignment = assign_student_to_room(
        student=student, room=room, assigned_by=actor,
        assignment_type=BedAssignment.AssignmentType.MANUAL, bed_id=bed.id,
    )

    student.refresh_from_db()
    AssistedAllocationAudit.objects.create(
        action_type=AssistedAllocationAudit.ActionType.MANUAL_ASSIGNMENT,
        actor=actor,
        student=student,
        bed_assignment=assignment,
        building=room.apartment.building,
        apartment=room.apartment,
        previous_state=previous_state,
        new_state=_assignment_snapshot(student),
    )

    return assignment


def record_manual_override(student, room, bed, actor, *, violations, note):
    """
    Place an unassigned student on ``bed`` while knowingly waiving the
    (already evaluated, non-blocking) ``violations`` and record a
    MANUAL_OVERRIDE audit entry carrying them and the operator's note.
    Every other placement safety step still runs (see
    assign_student_to_room's skip_validation).
    """
    previous_state = _assignment_snapshot(student)

    assignment = assign_student_to_room(
        student=student, room=room, assigned_by=actor,
        assignment_type=BedAssignment.AssignmentType.MANUAL, bed_id=bed.id,
        skip_validation=True,
    )

    student.refresh_from_db()
    AssistedAllocationAudit.objects.create(
        action_type=AssistedAllocationAudit.ActionType.MANUAL_OVERRIDE,
        actor=actor,
        student=student,
        bed_assignment=assignment,
        building=room.apartment.building,
        apartment=room.apartment,
        previous_state=previous_state,
        new_state=_assignment_snapshot(student),
        overridden_rules=violations,
        note=note,
    )

    return assignment
