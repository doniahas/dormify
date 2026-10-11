"""
What-if simulation read models: the affected-student rows, breakdowns,
selected-target descriptions and the before/after analysis for a proposed
building inactivation or availability change. Nothing here writes.
"""

from ...models import Region, Student
from .queries import (
    affected_assignments_for_targets,
    analysis_snapshot,
    lost_resources_for_targets,
    snapshot_region_for_targets,
)

BREAKDOWN_KEYS = (
    'gender', 'requested_religion', 'religious', 'placement_sector', 'category', 'housing_type',
)


def format_affected_student(assignment):
    student = assignment.student
    bed = assignment.bed
    room = bed.room
    apartment = room.apartment
    building = apartment.building
    dorm_type = building.dorm_type
    region = dorm_type.region if dorm_type else None

    return {
        'assignment_id': assignment.id,

        'student_db_id': student.id,
        'student_id': student.student_id,
        'business_partner_id': student.business_partner_id,
        'full_name': student.full_name,
        'first_name': student.first_name,
        'last_name': student.last_name,

        'gender': student.gender,
        'requested_religion': student.requested_religion,
        'religious': student.religious,
        'placement_sector': student.placement_sector,
        'category': student.category,
        'housing_type': student.housing_type,

        # Same get_FOO_display() convention StudentSerializer already
        # exposes as gender_display/requested_religion_display/
        # religious_display, so the What-If "Affected Students" table can
        # show the same human-readable labels used everywhere else.
        'gender_display': student.get_gender_display() if student.gender else '',
        'requested_religion_display': student.get_requested_religion_display(),
        'religious_display': student.get_religious_display(),

        'is_priority': student.is_priority,
        'priority_reason': student.priority_reason,

        'accepted_dorm_type_id': student.accepted_dorm_type_id,
        'accepted_dorm_type_name': student.accepted_dorm_type.name if student.accepted_dorm_type else '',

        'current_building_id': building.id,
        'current_building_number': building.number,
        'current_apartment_id': apartment.id,
        'current_apartment_number': apartment.number,
        'current_room_id': room.id,
        'current_room_name': room.name,
        'current_bed_id': bed.id,
        'current_bed_label': bed.label,

        'dorm_type_id': dorm_type.id if dorm_type else None,
        'dorm_type_name': dorm_type.name if dorm_type else '',
        'region_id': region.id if region else '',
        'region_name': region.name if region else '',

        'status': 'needs_transfer',
    }


def count_by_value(items, key):
    counts = {}

    for item in items:
        value = item.get(key) or 'not_specified'
        counts[value] = counts.get(value, 0) + 1

    return [
        {
            'value': value,
            'count': count
        }
        for value, count in counts.items()
    ]


def _breakdowns(affected_students):
    return {key: count_by_value(affected_students, key) for key in BREAKDOWN_KEYS}


def _gender_counts(affected_students):
    return {
        'male_count': sum(
            1 for student in affected_students
            if student.get('gender') == Student.Gender.MALE
        ),
        'female_count': sum(
            1 for student in affected_students
            if student.get('gender') == Student.Gender.FEMALE
        ),
    }


def format_buildings(buildings):
    selected_buildings = []

    for building in buildings:
        dorm_type = building.dorm_type
        region = dorm_type.region if dorm_type else None

        selected_buildings.append({
            'id': building.id,
            'number': building.number,
            'dorm_type_id': dorm_type.id if dorm_type else None,
            'dorm_type_name': dorm_type.name if dorm_type else '',
            'region_id': region.id if region else '',
            'region_name': region.name if region else '',
            'is_active': building.is_active,
        })

    return selected_buildings


def format_targets(target_type, targets):
    formatted = []

    for target in targets:
        if target_type == 'building':
            dorm_type = target.dorm_type
            region = dorm_type.region if dorm_type else None

            formatted.append({
                'id': target.id,
                'target_type': 'building',
                'label': f'Building {target.number}',
                'number': target.number,
                'building_id': target.id,
                'building_number': target.number,
                'dorm_type_id': dorm_type.id if dorm_type else None,
                'dorm_type_name': dorm_type.name if dorm_type else '',
                'region_id': region.id if region else '',
                'region_name': region.name if region else '',
                'is_active': target.is_active,
            })

        elif target_type == 'apartment':
            building = target.building
            dorm_type = building.dorm_type if building else None
            region = dorm_type.region if dorm_type else None

            formatted.append({
                'id': target.id,
                'target_type': 'apartment',
                'label': f'Building {building.number} / Apartment {target.number}',
                'number': target.number,
                'apartment_id': target.id,
                'apartment_number': target.number,
                'building_id': building.id if building else None,
                'building_number': building.number if building else '',
                'dorm_type_id': dorm_type.id if dorm_type else None,
                'dorm_type_name': dorm_type.name if dorm_type else '',
                'region_id': region.id if region else '',
                'region_name': region.name if region else '',
                'is_active': target.is_active,
            })

        else:
            apartment = target.apartment
            building = apartment.building if apartment else None
            dorm_type = building.dorm_type if building else None
            region = dorm_type.region if dorm_type else None

            formatted.append({
                'id': target.id,
                'target_type': 'room',
                'label': f'Building {building.number} / Apartment {apartment.number} / Room {target.name}',
                'room_id': target.id,
                'room_name': target.name,
                'apartment_id': apartment.id if apartment else None,
                'apartment_number': apartment.number if apartment else '',
                'building_id': building.id if building else None,
                'building_number': building.number if building else '',
                'dorm_type_id': dorm_type.id if dorm_type else None,
                'dorm_type_name': dorm_type.name if dorm_type else '',
                'region_id': region.id if region else '',
                'region_name': region.name if region else '',
                'capacity': target.capacity,
                'is_active': target.is_active,
            })

    return formatted


def _building_selection_region(buildings):
    """
    The building-inactivation simulation's snapshot region: the selected
    buildings' single distinct region value, only when that value is a real
    region. Unlike snapshot_region_for_targets, a building without a region
    is NOT filtered out first - mixing it with regional buildings yields the
    nationwide snapshot (None), exactly as this endpoint always behaved.
    """
    selected_regions = list(
        buildings.values_list('dorm_type__region_id', flat=True).distinct()
    )

    if len(selected_regions) == 1 and selected_regions[0]:
        return Region.objects.filter(pk=selected_regions[0]).first()

    return None


def simulate_building_inactivation(buildings):
    """
    What would happen if the selected buildings were inactivated: the
    affected students, what inventory is lost and the region snapshot
    before and after. Nothing is written.
    """
    building_ids = list(buildings.values_list('id', flat=True))

    affected_students = [
        format_affected_student(assignment)
        for assignment in affected_assignments_for_targets('building', building_ids)
    ]

    snapshot_region = _building_selection_region(buildings)

    lost_resources = lost_resources_for_targets('building', building_ids)

    selected_buildings = format_buildings(buildings)

    analysis_before = analysis_snapshot(region=snapshot_region)

    analysis_after = analysis_snapshot(
        region=snapshot_region,
        excluded_building_ids=building_ids,
    )

    return {
        'scenario': 'building_inactivation',
        'selected_buildings': selected_buildings,

        'summary': {
            'affected_students_count': len(affected_students),
            'students_without_valid_placement': len(affected_students),
            **_gender_counts(affected_students),
            **lost_resources,
        },

        'breakdowns': _breakdowns(affected_students),

        'analysis_before': analysis_before,
        'analysis_after': analysis_after,
        'affected_students': affected_students,
    }


def simulate_availability_change(target_type, target_ids, targets):
    """
    What would happen if the selected buildings / apartments / rooms became
    unavailable: the affected students, what inventory is lost and the
    region snapshot before and after. Nothing is written.
    """
    affected_students = [
        format_affected_student(assignment)
        for assignment in affected_assignments_for_targets(target_type, target_ids)
    ]

    snapshot_region = snapshot_region_for_targets(target_type, targets)

    excluded_building_ids = target_ids if target_type == 'building' else []
    excluded_apartment_ids = target_ids if target_type == 'apartment' else []
    excluded_room_ids = target_ids if target_type == 'room' else []

    analysis_before = analysis_snapshot(region=snapshot_region)

    analysis_after = analysis_snapshot(
        region=snapshot_region,
        excluded_building_ids=excluded_building_ids,
        excluded_apartment_ids=excluded_apartment_ids,
        excluded_room_ids=excluded_room_ids,
    )

    lost_resources = lost_resources_for_targets(target_type, target_ids)

    return {
        'scenario': f'{target_type}_availability_change',
        'target_type': target_type,
        'target_ids': target_ids,
        'selected_targets': format_targets(target_type, targets),

        'summary': {
            'affected_students_count': len(affected_students),
            'students_without_valid_placement': len(affected_students),
            **_gender_counts(affected_students),
            **lost_resources,
        },

        'breakdowns': _breakdowns(affected_students),

        'analysis_before': analysis_before,
        'analysis_after': analysis_after,
        'affected_students': affected_students,
    }
