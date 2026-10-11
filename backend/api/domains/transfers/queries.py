"""
StudentRequest list querysets: the base queryset with every related row the
serializer reads prefetched, and the bounded placement-history prefetch.
"""

from django.db.models import Prefetch
from django.db.models.expressions import RawSQL

from ...models import BedAssignment, StudentRequest


def top10_bed_assignment_history_qs():
    """
    BedAssignment queryset bounded to each student's 10 most-recent rows
    (by assigned_at desc, id desc as a deterministic tiebreak), used as the
    queryset for the placement_history Prefetch below.

    Measured, and now pinned by test_placement_history_verification:
    prefetching this relation with an ordinary (unbounded) queryset and
    slicing to [:10] in Python stays flat at 5 queries per page, but loads
    ALL of every relevant student's historical BedAssignment rows into the
    app server (grows unboundedly with each student's lifetime history).
    Django's ORM cannot filter on a Window() annotation directly, so a
    small raw ROW_NUMBER() subquery, referenced via pk__in=RawSQL(...), is
    the standard/smallest way to express a bounded "top N per group"
    query. Prefetch() then appends its own student_id__in=[...] filter on
    top of this, so the query stays a single flat statement, correct, and
    bounded to exactly 10 rows/student.
    """
    table = BedAssignment._meta.db_table
    top10_ids_sql = (
        f'SELECT id FROM ('
        f'SELECT id, ROW_NUMBER() OVER ('
        f'PARTITION BY student_id ORDER BY assigned_at DESC, id DESC'
        f') AS rn FROM {table}'
        f') ranked WHERE rn <= 10'
    )
    return BedAssignment.objects.filter(
        pk__in=RawSQL(top10_ids_sql, ()),
    ).select_related(
        'bed__room__apartment__building',
        'bed__room__apartment__building__dorm_type__region',
    ).order_by('-assigned_at', '-id')


def student_request_base_queryset():
    """
    StudentRequest rows with everything StudentRequestSerializer reads
    joined or prefetched, so listing a page runs a fixed number of
    queries regardless of page size.
    """
    return StudentRequest.objects.select_related(
        'student',
        'student__assigned_room__apartment__building__dorm_type__region',
        'student__accepted_dorm_type__region',
        'target_room__apartment__building__dorm_type__region',
        'swap_with_student', 'target_region',
        'requested_by', 'requested_by__region', 'reviewed_by',
        'source_region',
    ).prefetch_related(
        # destination_regions is read twice per row by
        # StudentRequestSerializer (the declared PrimaryKeyRelatedField
        # AND get_destination_region_names()) - one prefetch satisfies
        # both .all() calls from a single query.
        'destination_regions',
        # current_bed and placement_history need DIFFERENT slices of the
        # same student.bed_assignments relation (current_bed: at most the
        # one ACTIVE assignment; placement_history: the most recent 10
        # regardless of status) - two separate Prefetch() objects on the
        # same lookup path, distinguished by to_attr, so Django runs
        # exactly one query per slice instead of one per row.
        Prefetch(
            'student__bed_assignments',
            queryset=BedAssignment.objects.filter(
                status=BedAssignment.Status.ACTIVE,
            ).select_related('bed', 'bed__room'),
            to_attr='prefetched_current_assignment_list',
        ),
        Prefetch(
            'student__bed_assignments',
            queryset=top10_bed_assignment_history_qs(),
            to_attr='prefetched_placement_history_all',
        ),
    )
