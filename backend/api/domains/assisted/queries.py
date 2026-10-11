"""
Assisted Allocation workbench read models: the queue buckets and tabs,
the per-student row, the student detail panel and the ranked
recommendations.
"""

from dataclasses import dataclass

from ...models import (
    AssistedAllocationAudit,
    BedAssignment,
    Room,
    Student,
    StudentRequest,
)
from ..allocation.queries import (
    accessibility_pending_queryset,
    unassigned_students_queryset,
)
from ..allocation.results import inventory_breakdown_rows
from ..matching.ranking import find_matching_room_options
from ..transfers.services import _assignment_snapshot

QUEUE_TABS = ('needs_placement', 'accessibility', 'unassigned', 'resolved', 'transfer_pending')

_EMPTY_CANDIDATES = {
    'buildings': [], 'total_valid_beds': 0, 'has_more': False,
    'next_offset': None, 'feasible': False,
}


def pending_region_transfer(student):
    """
    The student's pending region_transfer StudentRequest, if any, or None.

    Single source of truth reused by the queue, the student-detail panel,
    the recommendations endpoint, and the assign/override write endpoints -
    a student with a pending region-transfer request must read as
    consistently "not locally actionable" everywhere, never computed
    independently in more than one place.
    """
    return StudentRequest.objects.filter(
        student=student,
        request_type=StudentRequest.RequestType.REGION_TRANSFER,
        status=StudentRequest.Status.PENDING,
    ).select_related(
        'target_region', 'source_region', 'requested_by', 'reviewed_by',
    ).order_by('-created_at').first()


def transfer_requested_student_ids():
    """Ids of every student with a pending region_transfer request."""
    return set(
        StudentRequest.objects.filter(
            request_type=StudentRequest.RequestType.REGION_TRANSFER,
            status=StudentRequest.Status.PENDING,
        ).values_list('student_id', flat=True)
    )


def assisted_student_row(student, group='', is_transfer_requested=False):
    dorm_type = student.accepted_dorm_type
    region = dorm_type.region if dorm_type else None
    special_statuses = [
        value for value in [
            student.special_status_1, student.special_status_2,
            student.special_status_3, student.special_status_4,
        ] if value
    ]

    return {
        'student_db_id': student.id,
        'student_id': student.student_id,
        'full_name': student.full_name,
        'first_name': student.first_name,
        'last_name': student.last_name,

        'gender': student.gender,
        'gender_display': student.get_gender_display() if student.gender else '',

        'accepted_dorm_type_id': dorm_type.id if dorm_type else None,
        'accepted_dorm_type': dorm_type.name if dorm_type else '',

        'housing_type': student.housing_type,
        'housing_type_display': (
            student.get_housing_type_display() if student.housing_type else ''
        ),

        'requested_religion': student.requested_religion,
        'religion_display': (
            student.get_requested_religion_display() if student.requested_religion else ''
        ),

        'region_id': region.id if region else '',
        'region': region.name if region else '',

        'is_priority': student.is_priority,
        'priority_reason': student.priority_reason,

        'accessibility_flag': student.accessibility_flag,
        'disability_percent': (
            str(student.disability_percent) if student.disability_percent is not None else None
        ),
        'medical_reason': student.medical_reason,
        'special_statuses': special_statuses,

        'group': group,
        'is_transfer_requested': is_transfer_requested,
    }


@dataclass
class AssistedQueue:
    """The workbench's population buckets for one region (or all regions)."""

    accessibility_students: list
    unassigned_students: list
    resolved_students: list
    transfer_pending_students: list
    transfer_requested_ids: set

    @property
    def counts(self):
        counts = {
            'accessibility_pending': len(self.accessibility_students),
            'unassigned': len(self.unassigned_students),
            'resolved': len(self.resolved_students),
            'transfer_requested': len(self.transfer_pending_students),
        }
        counts['needs_placement'] = counts['accessibility_pending'] + counts['unassigned']
        return counts

    def tab(self, tab):
        """(students, group_of) for a queue tab; unknown tabs mean needs_placement."""
        if tab == 'accessibility':
            students = self.accessibility_students
            group_of = {s.id: 'accessibility' for s in students}
        elif tab == 'unassigned':
            students = self.unassigned_students
            group_of = {s.id: 'unassigned' for s in students}
        elif tab == 'resolved':
            students = self.resolved_students
            group_of = {s.id: 'resolved' for s in students}
        elif tab == 'transfer_pending':
            students = self.transfer_pending_students
            group_of = {s.id: 'transfer_pending' for s in students}
        else:
            students = self.accessibility_students + self.unassigned_students
            group_of = {s.id: 'accessibility' for s in self.accessibility_students}
            for s in self.unassigned_students:
                group_of.setdefault(s.id, 'unassigned')
        return students, group_of


def build_assisted_queue(region):
    """
    The queue buckets for ``region`` (None = every region). A student with
    a pending region_transfer request is kept OUT of the accessibility /
    unassigned buckets - a student must never simultaneously read as
    "locally actionable" and "pending transfer to another region".
    """
    transfer_requested_ids = transfer_requested_student_ids()

    accessibility_students = [
        s for s in accessibility_pending_queryset(region) if s.id not in transfer_requested_ids
    ]
    unassigned_students = [
        s for s in unassigned_students_queryset(region) if s.id not in transfer_requested_ids
    ]

    transfer_pending_qs = Student.objects.filter(id__in=transfer_requested_ids).select_related(
        'accepted_dorm_type', 'accepted_dorm_type__region',
    )
    if region:
        transfer_pending_qs = transfer_pending_qs.filter(accepted_dorm_type__region=region)
    transfer_pending_students = list(transfer_pending_qs.order_by('last_name', 'first_name', 'student_id'))

    resolved_audit_qs = AssistedAllocationAudit.objects.filter(
        action_type__in=[
            AssistedAllocationAudit.ActionType.MANUAL_ASSIGNMENT,
            AssistedAllocationAudit.ActionType.MANUAL_OVERRIDE,
        ],
        bed_assignment__status=BedAssignment.Status.ACTIVE,
        student__isnull=False,
    ).select_related(
        'student', 'student__accepted_dorm_type', 'student__accepted_dorm_type__region',
    ).order_by('-created_at')
    if region:
        resolved_audit_qs = resolved_audit_qs.filter(student__accepted_dorm_type__region=region)

    resolved_students = []
    seen_ids = set()
    for audit in resolved_audit_qs:
        if audit.student_id in seen_ids:
            continue
        seen_ids.add(audit.student_id)
        resolved_students.append(audit.student)

    return AssistedQueue(
        accessibility_students=accessibility_students,
        unassigned_students=unassigned_students,
        resolved_students=resolved_students,
        transfer_pending_students=transfer_pending_students,
        transfer_requested_ids=transfer_requested_ids,
    )


def filter_queue_students(students, *, gender=None, dorm_type_id=None, search=''):
    """Apply the workbench's gender / dorm type / free-text filters to a tab."""
    if gender:
        students = [s for s in students if s.gender == gender]

    if dorm_type_id:
        students = [s for s in students if str(s.accepted_dorm_type_id) == str(dorm_type_id)]

    search = (search or '').strip().lower()
    if search:
        students = [
            s for s in students
            if search in s.full_name.lower() or search in (s.student_id or '').lower()
        ]

    return students


def student_group(student, pending_transfer):
    """
    The workbench group a student belongs to. A real placement is the
    most authoritative state, so is_assigned wins (a manually-resolved
    accessibility student reads as 'resolved', matching the queue's
    audit-based resolved tab); next, a pending region_transfer takes the
    student out of the locally-actionable population entirely; otherwise
    they read as accessibility / unassigned.
    """
    if student.is_assigned:
        return 'resolved'
    if pending_transfer is not None:
        return 'transfer_pending'
    if student.accessibility_flag:
        return 'accessibility'
    return 'unassigned'


def roommate_requests(student):
    requests = []
    for i in range(1, 6):
        name = getattr(student, f'roommate_request_{i}', '')
        if not name:
            continue
        requests.append({
            'name': name,
            'student_id': getattr(student, f'roommate_request_student_id_{i}', ''),
            'mutual': bool(getattr(student, f'roommate_request_flag_{i}', False)),
        })
    return requests


def unassigned_reason(student):
    """
    Why an unassigned, non-accessibility student has no bed right now,
    computed with the solver's own staged predicates against the current
    active inventory of their accepted dorm type.
    """
    dorm_type = student.accepted_dorm_type
    if dorm_type is None:
        return {'reason_code': 'NO_ACCEPTED_DORM_TYPE', 'inventory_breakdown': []}

    from ..allocation.gateway import analyze_unassigned_group

    rooms = list(
        Room.objects.filter(
            apartment__building__dorm_type=dorm_type,
            is_active=True,
            apartment__is_active=True,
            apartment__building__is_active=True,
        ).select_related(
            'apartment', 'apartment__building', 'apartment__building__dorm_type',
        ).prefetch_related('beds')
    )
    analysis = analyze_unassigned_group(student, rooms)
    return {
        'reason_code': analysis['reason_code'],
        'physically_free_beds_in_accepted_dorm': analysis['physically_free_beds_in_accepted_dorm'],
        'compatible_free_beds': analysis['compatible_free_beds'],
        'inventory_breakdown': inventory_breakdown_rows(analysis['inventory_breakdown']),
    }


def student_audit_history(student, limit=10):
    return [
        {
            'action_type': entry.action_type,
            'action_type_display': entry.get_action_type_display(),
            'actor_name': entry.actor.get_full_name() if entry.actor else '',
            'created_at': entry.created_at.isoformat(),
            'note': entry.note,
            'overridden_rules': entry.overridden_rules,
        }
        for entry in AssistedAllocationAudit.objects.filter(student=student)
            .select_related('actor').order_by('-created_at')[:limit]
    ]


def build_student_detail(student):
    """
    The student-detail panel: the row, roommate requests, the unassigned
    reason (only for a locally-actionable, non-accessibility student), the
    audit history, the current placement snapshot and the pending
    region_transfer request (a model instance, or None).
    """
    pending_transfer = pending_region_transfer(student)
    group = student_group(student, pending_transfer)
    row = assisted_student_row(student, group=group, is_transfer_requested=pending_transfer is not None)

    reason = None
    if not student.accessibility_flag and not student.is_assigned and pending_transfer is None:
        reason = unassigned_reason(student)

    return {
        'student': row,
        'roommate_requests': roommate_requests(student),
        'reason': reason,
        'history': student_audit_history(student),
        # Lets the frontend show WHERE an already-resolved student now lives
        # (building/apartment/room/bed) - reuses the same snapshot helper
        # used to record before/after state on StudentRequest and
        # AssistedAllocationAudit, so this can never disagree with them.
        'current_placement': _assignment_snapshot(student),
        'pending_transfer_request': pending_transfer,
    }


def build_recommendations(user, student):
    """
    Ranked initial candidates for a student plus the region-wide
    configuration opportunities. An already-assigned student, or one with
    a pending region_transfer, has left this workbench's local placement
    population: no candidates are (re)computed for them.
    """
    dorm_type = student.accepted_dorm_type
    region = dorm_type.region if dorm_type else None

    if student.is_assigned or pending_region_transfer(student) is not None:
        return {
            'candidates': dict(_EMPTY_CANDIDATES),
            'config_opportunities': [],
            'has_unsafe_config_candidates': False,
            'accepted_dorm_type': {'id': dorm_type.id, 'name': dorm_type.name} if dorm_type else None,
            'already_assigned': student.is_assigned,
            'transfer_pending': not student.is_assigned,
        }

    if dorm_type is None:
        return {
            'candidates': dict(_EMPTY_CANDIDATES),
            'config_opportunities': [],
            'accepted_dorm_type': None,
            'reason': 'לסטודנט אין סוג מעונות/אזור מוגדר',
        }

    # No pagination: candidates are hard-scoped to the student's own
    # accepted dorm type (never the whole region), which is a small,
    # bounded inventory - fetching it in full lets the frontend offer real
    # client-side search across every eligible bed.
    candidates = find_matching_room_options(
        user, student=student, region_id=region.id if region else None,
        limit=None, offset=0, assisted_mode=True,
    )

    from ..allocation.gateway import (
        find_configuration_opportunities,
        has_unsafe_configuration_candidates,
    )

    config_opportunities = []
    has_unsafe_config_candidates = False
    if region is not None:
        queue_students = list(accessibility_pending_queryset(region)) + list(unassigned_students_queryset(region))
        config_opportunities = find_configuration_opportunities(region, queue_students)
        for opportunity in config_opportunities:
            opportunity['helps_selected_student'] = student.id in opportunity.get('affected_student_ids', [])
        # Informational only (see has_unsafe_configuration_candidates
        # docstring) - never affects config_opportunities itself, which
        # already only ever contains genuinely empty, safe-to-change units.
        has_unsafe_config_candidates = has_unsafe_configuration_candidates(region, queue_students)

    return {
        'candidates': candidates,
        'config_opportunities': config_opportunities,
        'has_unsafe_config_candidates': has_unsafe_config_candidates,
        'accepted_dorm_type': {'id': dorm_type.id, 'name': dorm_type.name},
    }
