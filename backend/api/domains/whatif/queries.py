"""
What-if querysets and inventory arithmetic: the selected buildings /
apartments / rooms, the active assignments they shelter, the region a
simulation should be scoped to, the capacity lost by deactivating them and
the before/after occupancy snapshot.
"""

from ...models import Apartment, Bed, BedAssignment, Building, Region, Room, Student

TARGET_TYPES = ('building', 'apartment', 'room')

_AFFECTED_ASSIGNMENT_SELECT_RELATED = (
    'student',
    'student__accepted_dorm_type',
    'bed',
    'bed__room',
    'bed__room__apartment',
    'bed__room__apartment__building',
    'bed__room__apartment__building__dorm_type',
    'bed__room__apartment__building__dorm_type__region',
)

_AFFECTED_ASSIGNMENT_ORDER_BY = (
    'bed__room__apartment__building__number',
    'bed__room__apartment__number',
    'bed__room__name',
    'bed__label',
)


def buildings_for_ids(building_ids):
    """The selected buildings; raises ValueError when any id is unknown."""
    buildings = Building.objects.filter(id__in=building_ids).select_related(
        'dorm_type',
        'dorm_type__region'
    )

    if buildings.count() != len(set(building_ids)):
        raise ValueError('One or more selected buildings were not found.')

    return buildings


def targets_for_ids(target_type, target_ids):
    """
    The selected buildings, apartments or rooms (``target_ids`` already
    de-duplicated); raises ValueError when any id is unknown.
    """
    if target_type == 'building':
        targets = Building.objects.filter(id__in=target_ids).select_related(
            'dorm_type',
            'dorm_type__region'
        )
    elif target_type == 'apartment':
        targets = Apartment.objects.filter(id__in=target_ids).select_related(
            'building',
            'building__dorm_type',
            'building__dorm_type__region'
        )
    else:
        targets = Room.objects.filter(id__in=target_ids).select_related(
            'apartment',
            'apartment__building',
            'apartment__building__dorm_type',
            'apartment__building__dorm_type__region'
        )

    if targets.count() != len(target_ids):
        raise ValueError('One or more selected targets were not found.')

    return targets


def affected_assignments_for_targets(target_type, target_ids):
    """Active assignments sheltered by the selected inventory, in table order."""
    filters = {
        'status': BedAssignment.Status.ACTIVE,
    }

    if target_type == 'building':
        filters['bed__room__apartment__building_id__in'] = target_ids
    elif target_type == 'apartment':
        filters['bed__room__apartment_id__in'] = target_ids
    else:
        filters['bed__room_id__in'] = target_ids

    return BedAssignment.objects.filter(**filters).select_related(
        *_AFFECTED_ASSIGNMENT_SELECT_RELATED
    ).order_by(*_AFFECTED_ASSIGNMENT_ORDER_BY)


def snapshot_region_for_targets(target_type, targets):
    """
    The single region every selected target belongs to, or None when the
    selection spans regions (or none of them resolves a region).
    """
    if target_type == 'building':
        region_ids = list(
            targets.values_list('dorm_type__region_id', flat=True).distinct()
        )
    elif target_type == 'apartment':
        region_ids = list(
            targets.values_list('building__dorm_type__region_id', flat=True).distinct()
        )
    else:
        region_ids = list(
            targets.values_list(
                'apartment__building__dorm_type__region_id',
                flat=True
            ).distinct()
        )

    region_ids = [region_id for region_id in region_ids if region_id]

    if len(region_ids) == 1:
        return Region.objects.filter(pk=region_ids[0]).first()

    return None


def analysis_snapshot(
    region=None,
    excluded_building_ids=None,
    excluded_apartment_ids=None,
    excluded_room_ids=None,
):
    """
    Occupancy snapshot of the active inventory (optionally scoped to one
    region) with the given buildings / apartments / rooms treated as gone.
    """
    excluded_building_ids = excluded_building_ids or []
    excluded_apartment_ids = excluded_apartment_ids or []
    excluded_room_ids = excluded_room_ids or []

    buildings_qs = Building.objects.filter(
        is_active=True
    ).select_related(
        'dorm_type',
        'dorm_type__region'
    )

    rooms_qs = Room.objects.filter(
        is_active=True,
        apartment__is_active=True,
        apartment__building__is_active=True,
    )

    assignments_qs = BedAssignment.objects.filter(
        status=BedAssignment.Status.ACTIVE,
        bed__room__is_active=True,
        bed__room__apartment__is_active=True,
        bed__room__apartment__building__is_active=True,
    )

    students_qs = Student.objects.all()

    if region:
        buildings_qs = buildings_qs.filter(
            dorm_type__region=region
        )
        rooms_qs = rooms_qs.filter(
            apartment__building__dorm_type__region=region
        )
        assignments_qs = assignments_qs.filter(
            bed__room__apartment__building__dorm_type__region=region
        )
        students_qs = students_qs.filter(
            accepted_dorm_type__region=region
        )

    if excluded_building_ids:
        buildings_qs = buildings_qs.exclude(
            id__in=excluded_building_ids
        )
        rooms_qs = rooms_qs.exclude(
            apartment__building_id__in=excluded_building_ids
        )
        assignments_qs = assignments_qs.exclude(
            bed__room__apartment__building_id__in=excluded_building_ids
        )

    if excluded_apartment_ids:
        rooms_qs = rooms_qs.exclude(
            apartment_id__in=excluded_apartment_ids
        )
        assignments_qs = assignments_qs.exclude(
            bed__room__apartment_id__in=excluded_apartment_ids
        )

    if excluded_room_ids:
        rooms_qs = rooms_qs.exclude(
            id__in=excluded_room_ids
        )
        assignments_qs = assignments_qs.exclude(
            bed__room_id__in=excluded_room_ids
        )

    total_students = students_qs.count()
    assigned_students = assignments_qs.values('student_id').distinct().count()
    unassigned_students = max(total_students - assigned_students, 0)

    total_capacity = sum(
        rooms_qs.values_list('capacity', flat=True)
    )

    occupied_beds = assignments_qs.values('bed_id').distinct().count()
    available_beds = max(total_capacity - occupied_beds, 0)

    occupancy_rate = 0
    if total_capacity > 0:
        occupancy_rate = round((occupied_beds / total_capacity) * 100, 2)

    return {
        'total_students': total_students,
        'assigned_students': assigned_students,
        'unassigned_students': unassigned_students,
        'total_buildings': buildings_qs.count(),
        'total_rooms': rooms_qs.count(),
        'total_capacity': total_capacity,
        'total_beds': total_capacity,
        'occupied_beds': occupied_beds,
        'assigned_beds': occupied_beds,
        'available_beds': available_beds,
        'occupancy_rate': occupancy_rate,
    }


def lost_resources_for_targets(target_type, target_ids):
    """Active apartments / rooms / capacity / beds the selection takes away."""
    if target_type == 'building':
        lost_apartments_qs = Apartment.objects.filter(
            building_id__in=target_ids,
            is_active=True,
        )

        lost_rooms_qs = Room.objects.filter(
            apartment__building_id__in=target_ids,
            is_active=True,
            apartment__is_active=True,
        )

        lost_beds_qs = Bed.objects.filter(
            room__apartment__building_id__in=target_ids,
            room__is_active=True,
            room__apartment__is_active=True,
        )

    elif target_type == 'apartment':
        lost_apartments_qs = Apartment.objects.filter(
            id__in=target_ids,
            is_active=True,
        )

        lost_rooms_qs = Room.objects.filter(
            apartment_id__in=target_ids,
            is_active=True,
            apartment__is_active=True,
        )

        lost_beds_qs = Bed.objects.filter(
            room__apartment_id__in=target_ids,
            room__is_active=True,
            room__apartment__is_active=True,
        )

    else:
        lost_rooms_qs = Room.objects.filter(
            id__in=target_ids,
            is_active=True,
            apartment__is_active=True,
        )

        lost_apartments_qs = Apartment.objects.filter(
            rooms__id__in=target_ids
        ).distinct()

        lost_beds_qs = Bed.objects.filter(
            room_id__in=target_ids,
            room__is_active=True,
            room__apartment__is_active=True,
        )

    lost_rooms = lost_rooms_qs.count()
    lost_capacity = sum(
        lost_rooms_qs.values_list('capacity', flat=True)
    )

    return {
        'lost_apartments': lost_apartments_qs.count(),
        'lost_rooms': lost_rooms,
        'lost_capacity': lost_capacity,
        'lost_beds': lost_beds_qs.count(),
    }
