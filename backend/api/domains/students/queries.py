"""
Student list queries: the latest completed run's still-unassigned
population, the Students page filter set, and the filter-option lists.
"""

from dataclasses import dataclass, field

from django.db.models import Q

from ...models import AllocationRun, Apartment, Building, DormType, Region, Room, Student


def unassigned_student_ids_from_latest_completed_run(region_id):
    """
    Ids of the students the region's latest COMPLETED allocation run sent
    to the solver who are still unassigned (and still solver-eligible).
    Empty when there is no such run or it predates population tracking.
    """
    latest_run = AllocationRun.objects.filter(
        status=AllocationRun.Status.COMPLETED,
        region_id=region_id,
    ).order_by('-started_at').first()

    if not latest_run:
        return []

    population_summary = (
        (latest_run.diagnostics or {}).get('population_summary') or {}
    )

    run_student_ids = population_summary.get(
        'sent_to_solver_student_ids'
    ) or []

    if not run_student_ids:
        return []

    return list(
        Student.objects.filter(
            id__in=run_student_ids,
            assigned_room__isnull=True,
        )
        .exclude(
            category=Student.StudentCategory.LEAVING
        )
        .exclude(
            accessibility_flag=True
        )
        .values_list('id', flat=True)
    )


@dataclass
class StudentFilters:
    """The Students page filters, already parsed from the query string."""

    search: str = ''
    genders: list = field(default_factory=list)
    religions: list = field(default_factory=list)
    religious: str = ''
    placement_sector: str = ''
    region_ids: list = field(default_factory=list)
    dorm_type_ids: list = field(default_factory=list)
    building_ids: list = field(default_factory=list)
    apartment_ids: list = field(default_factory=list)
    room_ids: list = field(default_factory=list)
    status: str = ''
    # Only consulted when status == 'unassigned': the ids computed by
    # unassigned_student_ids_from_latest_completed_run for the caller.
    unassigned_student_ids: list = field(default_factory=list)
    has_roommate_request: str = ''
    category: str = ''


_ROOMMATE_REQUEST_Q = (
    Q(roommate_request_1__gt='') | Q(roommate_request_2__gt='') |
    Q(roommate_request_3__gt='') | Q(roommate_request_4__gt='') |
    Q(roommate_request_5__gt='')
)


def filter_students(queryset, filters):
    """Apply the Students page filters to an already region-scoped queryset."""
    if filters.search:
        queryset = queryset.filter(
            Q(first_name__icontains=filters.search) |
            Q(last_name__icontains=filters.search) |
            Q(student_id__icontains=filters.search) |
            Q(business_partner_id__icontains=filters.search)
        )

    if filters.genders:
        queryset = queryset.filter(gender__in=filters.genders)

    if filters.religions:
        queryset = queryset.filter(requested_religion__in=filters.religions)

    if filters.religious and filters.religious != 'all':
        queryset = queryset.filter(religious=filters.religious)

    if filters.placement_sector and filters.placement_sector != 'all':
        queryset = queryset.filter(placement_sector=filters.placement_sector)

    # Location filters. Region PKs are slugs; the rest are integer PKs.
    if filters.region_ids:
        queryset = queryset.filter(accepted_dorm_type__region_id__in=filters.region_ids)

    if filters.dorm_type_ids:
        queryset = queryset.filter(accepted_dorm_type_id__in=filters.dorm_type_ids)

    if filters.building_ids:
        queryset = queryset.filter(assigned_room__apartment__building_id__in=filters.building_ids)

    if filters.apartment_ids:
        queryset = queryset.filter(assigned_room__apartment_id__in=filters.apartment_ids)

    if filters.room_ids:
        queryset = queryset.filter(assigned_room_id__in=filters.room_ids)

    if filters.status == 'assigned':
        queryset = queryset.filter(assigned_room__isnull=False)
    elif filters.status == 'unassigned':
        queryset = queryset.filter(id__in=filters.unassigned_student_ids)
    elif filters.status == 'priority':
        queryset = queryset.filter(is_priority=True)

    if filters.has_roommate_request in ('yes', 'no'):
        queryset = (
            queryset.filter(_ROOMMATE_REQUEST_Q)
            if filters.has_roommate_request == 'yes'
            else queryset.exclude(_ROOMMATE_REQUEST_Q)
        )

    if filters.category and filters.category != 'all':
        queryset = queryset.filter(category=filters.category)

    return queryset


def build_student_filter_options(region_id=None):
    """
    The option lists behind the Students page filters and the Add/Edit
    Student form, scoped to ``region_id`` when given.
    """
    regions = Region.objects.all()
    buildings = Building.objects.select_related('dorm_type').all()
    dorm_types = DormType.objects.select_related('region').all()
    apartments = Apartment.objects.select_related('building').all()
    rooms = Room.objects.select_related('apartment').all()

    if region_id:
        regions = regions.filter(id=region_id)
        buildings = buildings.filter(dorm_type__region_id=region_id)
        dorm_types = dorm_types.filter(region_id=region_id)
        apartments = apartments.filter(building__dorm_type__region_id=region_id)
        rooms = rooms.filter(apartment__building__dorm_type__region_id=region_id)

    religions = [
        {'id': choice_value, 'name': str(choice_label)}
        for choice_value, choice_label in Student.Religion.choices
    ]

    # Single source of truth for the canonical housing-type values -
    # Add/Edit Student must offer exactly these 5 choices (Z1/Z2/Z3/Z4/Z6),
    # never a hardcoded frontend copy that can drift from the model.
    housing_types = [
        {'id': choice_value, 'name': str(choice_label)}
        for choice_value, choice_label in Student.HousingType.choices
    ]

    return {
        'regions': [{'id': r.id, 'name': r.name} for r in regions],
        'buildings': [{'id': b.id, 'name': str(b.number)} for b in buildings],
        'dorm_types': [
            {'id': d.id, 'name': d.name, 'region_id': d.region_id, 'region_name': d.region.name if d.region else None}
            for d in dorm_types
        ],
        'apartments': [{'id': a.id, 'name': a.number} for a in apartments],
        'rooms': [{'id': r.id, 'name': r.name} for r in rooms],
        'religions': religions,
        'housing_types': housing_types,
    }
