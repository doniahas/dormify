"""
Allocation result read models: assignment table rows, the current
allocation results of a region (assigned / unassigned / available beds)
and the grouped unassigned-students analysis.

The api.views compatibility facade (api/views/__init__.py) re-exports
``_build_unassigned_analysis`` from here, so references through the
api.views namespace keep resolving to this same object.
"""

from collections import defaultdict

from ...models import Apartment, Bed, BedAssignment, Room
from .queries import unassigned_students_queryset

_ASSIGNMENT_SELECT_RELATED = (
    'student',
    'student__accepted_dorm_type',
    'bed',
    'bed__room',
    'bed__room__apartment',
    'bed__room__apartment__building',
    'bed__room__apartment__building__dorm_type',
    'bed__room__apartment__building__dorm_type__region',
)

_ASSIGNMENT_ORDER_BY = (
    'bed__room__apartment__building__number',
    'bed__room__apartment__number',
    'bed__room__name',
    'bed__label',
)


def _assignment_row(assignment):
    """Assignment table row returned by the run endpoints."""
    student = assignment.student
    bed = assignment.bed
    room = bed.room
    apartment = room.apartment
    building = apartment.building
    dorm_type = building.dorm_type
    assignment_region = dorm_type.region if dorm_type else None

    return {
        'student_id': student.student_id,
        'student_name': student.full_name,
        'full_name': student.full_name,
        'first_name': student.first_name,
        'last_name': student.last_name,

        'gender': student.gender,
        'requested_religion': student.requested_religion,
        'religion': student.requested_religion,
        'religious': student.religious,
        'placement_sector': student.placement_sector,
        'sector': student.placement_sector,

        'building': building.number,
        'building_number': building.number,
        'apartment': apartment.number,
        'apartment_number': apartment.number,
        'room': room.name,
        'room_name': room.name,
        'bed': bed.label,
        'bed_label': bed.label,

        'dorm_type': dorm_type.name if dorm_type else '',
        'region': assignment_region.name if assignment_region else '',
        'region_id': assignment_region.id if assignment_region else '',

        'assignment_type': assignment.assignment_type,
        'assignment_status': assignment.status,
        'assigned_at': assignment.assigned_at.isoformat() if assignment.assigned_at else '',
    }


def build_assignment_rows_for_run(run):
    """Build the assignment table rows for a completed allocation run."""
    active_assignments = BedAssignment.objects.filter(
        allocation_run=run,
        status=BedAssignment.Status.ACTIVE,
    ).select_related(*_ASSIGNMENT_SELECT_RELATED).order_by(*_ASSIGNMENT_ORDER_BY)

    return [_assignment_row(assignment) for assignment in active_assignments]


def build_assignment_rows_for_students(region, student_ids):
    """
    Assignment table rows for the students a synchronous run sent to the
    solver - this run's population only, never every historical active
    assignment in the region.
    """
    active_assignments = BedAssignment.objects.filter(
        status=BedAssignment.Status.ACTIVE,
        student_id__in=student_ids,
        bed__room__apartment__building__dorm_type__region=region,
    ).select_related(*_ASSIGNMENT_SELECT_RELATED).order_by(*_ASSIGNMENT_ORDER_BY)

    return [_assignment_row(assignment) for assignment in active_assignments]


def inventory_breakdown_rows(items):
    """Attach display labels to analyze_unassigned_group's inventory breakdown."""
    category_labels = dict(Apartment.Category.choices)
    apartment_type_labels = dict(Apartment.ApartmentType.choices)
    return [
        {
            'category': item['category'],
            'category_display': category_labels.get(item['category'], item['category'] or ''),
            'apartment_type': item['apartment_type'],
            'apartment_type_display': apartment_type_labels.get(
                item['apartment_type'], item['apartment_type'] or '',
            ),
            'free_beds': item['free_beds'],
        }
        for item in items
    ]


def _build_unassigned_analysis(students):
    """
    Group currently-unassigned students by the characteristics that
    actually determine bed compatibility (accepted dorm type, gender,
    housing type) and explain, for each group, why they are blocked
    right now — physically free beds vs. beds actually compatible with
    them, and the first hard-constraint stage responsible.

    Reuses allocation.solver.analyze_unassigned_group — the exact staged
    predicates the solver's own candidate generation uses — so the
    reported reason can never diverge from real solver behavior. This
    function only handles grouping and current-inventory lookup; it
    contains no eligibility rules of its own.

    Computed against CURRENT active inventory (not a historical snapshot
    from any particular run), so it stays correct and actionable after
    staff convert apartments and reflects "what would happen if allocation
    ran again right now."
    """
    groups = defaultdict(list)
    for student in students:
        dorm_type = student.accepted_dorm_type
        key = (
            dorm_type.id if dorm_type else None,
            student.gender or '',
            student.housing_type or '',
        )
        groups[key].append(student)

    if not groups:
        return []

    from .gateway import analyze_unassigned_group

    dorm_type_ids = {key[0] for key in groups if key[0] is not None}
    rooms_by_dorm_type = defaultdict(list)
    if dorm_type_ids:
        rooms_qs = Room.objects.filter(
            apartment__building__dorm_type_id__in=dorm_type_ids,
            is_active=True,
            apartment__is_active=True,
            apartment__building__is_active=True,
        ).select_related(
            'apartment',
            'apartment__building',
            'apartment__building__dorm_type',
        ).prefetch_related('beds')
        for room in rooms_qs:
            rooms_by_dorm_type[room.apartment.building.dorm_type_id].append(room)

    analysis = []
    for (dorm_type_id, gender, housing_type), group_students in groups.items():
        representative = group_students[0]
        dorm_type = representative.accepted_dorm_type
        housing_type_display = (
            representative.get_housing_type_display() if housing_type else ''
        )

        if dorm_type_id is None:
            analysis.append({
                'accepted_dorm_type_id': None,
                'accepted_dorm_type_code': None,
                'accepted_dorm_type_name': '',
                'gender': gender,
                'housing_type': housing_type,
                'housing_type_display': housing_type_display,
                'student_count': len(group_students),
                'physically_free_beds_in_accepted_dorm': 0,
                'compatible_free_beds': 0,
                'reason_code': 'NO_ACCEPTED_DORM_TYPE',
                'inventory_breakdown': [],
            })
            continue

        group_rooms = rooms_by_dorm_type.get(dorm_type_id, [])
        result = analyze_unassigned_group(representative, group_rooms)

        analysis.append({
            'accepted_dorm_type_id': dorm_type_id,
            'accepted_dorm_type_code': getattr(dorm_type, 'code', None),
            'accepted_dorm_type_name': dorm_type.name if dorm_type else '',
            'gender': gender,
            'housing_type': housing_type,
            'housing_type_display': housing_type_display,
            'student_count': len(group_students),
            'physically_free_beds_in_accepted_dorm': result['physically_free_beds_in_accepted_dorm'],
            'compatible_free_beds': result['compatible_free_beds'],
            'reason_code': result['reason_code'],
            'inventory_breakdown': inventory_breakdown_rows(result['inventory_breakdown']),
        })

    analysis.sort(key=lambda row: -row['student_count'])
    return analysis


def _results_assignment_row(assignment):
    student = assignment.student
    bed = assignment.bed
    room = bed.room
    apartment = room.apartment
    building = apartment.building
    dorm_type = building.dorm_type
    dorm_region = dorm_type.region if dorm_type else None

    return {
        'student_id': student.student_id,
        'student_name': student.full_name,
        'full_name': student.full_name,
        'first_name': student.first_name,
        'last_name': student.last_name,

        'gender': student.gender,
        'housing_type': student.housing_type,
        'housing_type_display': (
            student.get_housing_type_display()
            if student.housing_type
            else ''
        ),

        'requested_religion': student.requested_religion,
        'religion': student.requested_religion,
        'religion_display': (
            student.get_requested_religion_display()
            if student.requested_religion
            else ''
        ),

        'religious': student.religious,
        'placement_sector': student.placement_sector,
        'sector': student.placement_sector,
        'is_priority': student.is_priority,

        'building': building.number,
        'building_number': building.number,

        'apartment': apartment.number,
        'apartment_number': apartment.number,

        'apartment_type': apartment.apartment_type,
        'apartment_type_display': (
            apartment.get_apartment_type_display()
            if apartment.apartment_type
            else ''
        ),

        'apartment_category': apartment.category,
        'apartment_category_display': (
            apartment.get_category_display()
            if apartment.category
            else ''
        ),

        'room': room.name,
        'room_name': room.name,

        'bed': bed.label,
        'bed_label': bed.label,

        'dorm_type': dorm_type.name if dorm_type else '',
        'dorm_type_id': dorm_type.id if dorm_type else None,

        'region': dorm_region.name if dorm_region else '',
        'region_id': dorm_region.id if dorm_region else '',

        'assignment_type': assignment.assignment_type,
        'assignment_status': assignment.status,
        'assigned_at': (
            assignment.assigned_at.isoformat()
            if assignment.assigned_at
            else ''
        ),
    }


def _results_unassigned_row(student, is_hasmaha_anier_student):
    dorm_type = student.accepted_dorm_type
    student_region = dorm_type.region if dorm_type else None

    special_statuses = [
        getattr(student, 'special_status_1', ''),
        getattr(student, 'special_status_2', ''),
        getattr(student, 'special_status_3', ''),
        getattr(student, 'special_status_4', ''),
    ]

    special_statuses = [
        value
        for value in special_statuses
        if value not in (None, '')
    ]

    return {
        'student_db_id': student.id,
        'student_id': student.student_id,
        'business_partner_id': getattr(
            student,
            'business_partner_id',
            '',
        ),

        'student_name': student.full_name,
        'full_name': student.full_name,
        'first_name': student.first_name,
        'last_name': student.last_name,

        'gender': student.gender,
        'gender_display': (
            student.get_gender_display()
            if student.gender
            else ''
        ),

        'housing_type': student.housing_type,
        'housing_type_display': (
            student.get_housing_type_display()
            if student.housing_type
            else ''
        ),

        'requested_religion': student.requested_religion,
        'religion': student.requested_religion,
        'religion_display': (
            student.get_requested_religion_display()
            if student.requested_religion
            else ''
        ),

        'religious': student.religious,
        'placement_sector': student.placement_sector,
        'placement_sector_display': (
            student.get_placement_sector_display()
            if student.placement_sector
            else ''
        ),

        'is_priority': student.is_priority,
        'priority_reason': student.priority_reason,

        'category': student.category,
        'category_display': (
            student.get_category_display()
            if student.category
            else ''
        ),

        'accepted_dorm_type_id': (
            dorm_type.id
            if dorm_type
            else None
        ),
        'accepted_dorm_type': (
            dorm_type.name
            if dorm_type
            else ''
        ),

        'region_id': (
            student_region.id
            if student_region
            else ''
        ),
        'region': (
            student_region.name
            if student_region
            else ''
        ),

        'special_statuses': special_statuses,
        'unassigned_reason': (
            'סטודנט אנייר זכאי לבניין 179 (כפר הסמכה) — לא נמצאה מיטה '
            'מתאימה בבניין 179 או בבניין אחר בכפר הסמכה בתוצאת השיבוץ '
            'הנוכחית.'
            if is_hasmaha_anier_student(student)
            else 'לא נמצא שיבוץ חוקי בתוצאת השיבוץ הנוכחית'
        ),
    }


def _results_available_bed_row(bed):
    room = bed.room
    apartment = room.apartment
    building = apartment.building
    dorm_type = building.dorm_type
    dorm_region = dorm_type.region if dorm_type else None

    inactive_reason = getattr(apartment, 'inactive_reason', '')

    is_reserved = (
        str(inactive_reason).strip().lower() == 'reserved'
        or str(inactive_reason).strip() == 'שמור'
    )

    return {
        'bed_id': bed.id,
        'bed': bed.label,
        'bed_label': bed.label,

        'room_id': room.id,
        'room': room.name,
        'room_name': room.name,
        'room_capacity': room.capacity,

        'apartment_id': apartment.id,
        'apartment': apartment.number,
        'apartment_number': apartment.number,
        'apartment_type': apartment.apartment_type,
        'apartment_type_display': (
            apartment.get_apartment_type_display()
            if apartment.apartment_type
            else ''
        ),
        'apartment_category': apartment.category,
        'apartment_category_display': (
            apartment.get_category_display()
            if apartment.category
            else ''
        ),
        'is_reserved': is_reserved,

        'building_id': building.id,
        'building': building.number,
        'building_number': building.number,
        'building_gender_restriction': getattr(
            building,
            'gender_restriction',
            '',
        ),

        'dorm_type_id': (
            dorm_type.id
            if dorm_type
            else None
        ),
        'dorm_type': (
            dorm_type.name
            if dorm_type
            else ''
        ),

        'region_id': (
            dorm_region.id
            if dorm_region
            else ''
        ),
        'region': (
            dorm_region.name
            if dorm_region
            else ''
        ),
    }


def build_allocation_results(region):
    """
    Current allocation results for a region (or every region when
    ``region`` is None - the caller has already applied the user's
    region-scoping rules):

    1. assigned students (active assignments in active inventory)
    2. unassigned allocatable students
    3. available real Bed records
    4. the grouped unassigned analysis
    """
    assignments_qs = BedAssignment.objects.filter(
        status=BedAssignment.Status.ACTIVE,
        bed__room__is_active=True,
        bed__room__apartment__is_active=True,
        bed__room__apartment__building__is_active=True,
    ).select_related(
        'student',
        'student__accepted_dorm_type',
        'student__accepted_dorm_type__region',
        'bed',
        'bed__room',
        'bed__room__apartment',
        'bed__room__apartment__building',
        'bed__room__apartment__building__dorm_type',
        'bed__room__apartment__building__dorm_type__region',
    )

    if region:
        assignments_qs = assignments_qs.filter(
            bed__room__apartment__building__dorm_type__region=region
        )

    assignments_qs = assignments_qs.order_by(*_ASSIGNMENT_ORDER_BY)

    assignments = [_results_assignment_row(assignment) for assignment in assignments_qs]

    # Materialized once so both the per-student rows and the grouped
    # unassigned_analysis iterate the same population without a second
    # database round trip.
    unassigned_student_objects = list(unassigned_students_queryset(region))

    # Gives an eligible Hasmaha ANIR student a more specific unassigned
    # reason than the generic message, so a solver-level hard-constraint
    # failure for this group is visibly distinguishable from an ordinary
    # student's generic "no valid assignment" outcome. Accessibility-flagged
    # students never reach this point at all — they are excluded from the
    # unassigned queryset, not shown here with a reason.
    from .gateway import _is_hasmaha_anier_student

    unassigned_students = [
        _results_unassigned_row(student, _is_hasmaha_anier_student)
        for student in unassigned_student_objects
    ]

    # Available real beds: only active buildings/apartments/rooms, and a bed
    # with an ACTIVE BedAssignment is not available.
    occupied_bed_ids = BedAssignment.objects.filter(
        status=BedAssignment.Status.ACTIVE
    ).values_list(
        'bed_id',
        flat=True,
    )

    available_beds_qs = Bed.objects.filter(
        room__is_active=True,
        room__apartment__is_active=True,
        room__apartment__building__is_active=True,
    ).exclude(
        id__in=occupied_bed_ids
    ).select_related(
        'room',
        'room__apartment',
        'room__apartment__building',
        'room__apartment__building__dorm_type',
        'room__apartment__building__dorm_type__region',
    )

    if region:
        available_beds_qs = available_beds_qs.filter(
            room__apartment__building__dorm_type__region=region
        )

    available_beds_qs = available_beds_qs.order_by(
        'room__apartment__building__number',
        'room__apartment__number',
        'room__name',
        'label',
    )

    available_beds = [_results_available_bed_row(bed) for bed in available_beds_qs]

    return {
        'assignments': assignments,
        'unassigned_students': unassigned_students,
        'available_beds': available_beds,
        'unassigned_analysis': _build_unassigned_analysis(unassigned_student_objects),
    }
