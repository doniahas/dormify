"""
Inventory write services: bulk apartment/room/bed creation for the
Building Setup Wizard, the occupancy-safe locking used by building and
apartment edits, and the configuration-change audit records those edits
leave behind.
"""

from django.db import transaction
from rest_framework.exceptions import ValidationError as DRFValidationError

from ...models import Apartment, AssistedAllocationAudit, Bed, Building
from ...serializers import (
    ApartmentSerializer,
    RoomSerializer,
    check_apartment_write_conflict,
    check_room_write_conflict,
)


class BulkInventoryError(Exception):
    """A bulk-create request that cannot proceed; ``payload`` is the error body."""

    def __init__(self, payload):
        super().__init__(payload.get('error'))
        self.payload = payload


def validate_bulk_inventory_groups(building, groups):
    """
    Validate the apartment_groups payload of a bulk-create request against
    its own shape rules and against the building's existing apartment
    numbers. Raises BulkInventoryError with the error body on the first
    problem found.
    """
    if not isinstance(groups, list) or not groups:
        raise BulkInventoryError({'error': 'apartment_groups must be a non-empty list.'})

    all_numbers = []
    for group_index, group in enumerate(groups):
        if not isinstance(group, dict):
            raise BulkInventoryError({'error': f'apartment_groups[{group_index}] must be an object.'})
        numbers = group.get('numbers')
        if not isinstance(numbers, list) or not numbers:
            raise BulkInventoryError({
                'error': f'apartment_groups[{group_index}].numbers must be a non-empty list.',
            })
        room_groups = group.get('room_groups')
        if not isinstance(room_groups, list) or not room_groups:
            raise BulkInventoryError({
                'error': f'apartment_groups[{group_index}].room_groups must be a non-empty list.',
            })
        for rg_index, room_group in enumerate(room_groups):
            capacity = room_group.get('capacity') if isinstance(room_group, dict) else None
            count = room_group.get('count') if isinstance(room_group, dict) else None
            if not isinstance(capacity, int) or capacity < 1:
                raise BulkInventoryError({
                    'error': f'apartment_groups[{group_index}].room_groups[{rg_index}].capacity must be a positive integer.',
                })
            if not isinstance(count, int) or count < 1:
                raise BulkInventoryError({
                    'error': f'apartment_groups[{group_index}].room_groups[{rg_index}].count must be a positive integer.',
                })
        all_numbers.extend(str(n) for n in numbers)

    if len(all_numbers) != len(set(all_numbers)):
        raise BulkInventoryError({
            'error': 'Apartment numbers must be unique within this request.',
            'code': 'DUPLICATE_APARTMENT_NUMBER',
        })

    existing = set(
        Apartment.objects.filter(
            building=building, number__in=all_numbers
        ).values_list('number', flat=True)
    )
    if existing:
        raise BulkInventoryError({
            'error': 'One or more apartment numbers already exist in this building.',
            'code': 'DUPLICATE_APARTMENT_NUMBER',
            'conflicting_numbers': sorted(existing),
        })


def bulk_create_inventory(building, groups):
    """
    Transactionally create many Apartments - each with its own Rooms and
    materialized Beds - under ``building`` from already-validated
    apartment_groups (see validate_bulk_inventory_groups).

    Reuses ApartmentSerializer/RoomSerializer for validation exactly like
    the single-object create endpoints, and the same ``f'Bed {i}'``
    materialization convention used everywhere else in the codebase
    (manage.py materialize_beds, allocation.solver._ensure_beds_for_room),
    so the result is indistinguishable from manually created inventory.

    Returns (created_apartments, created_rooms, created_beds). A
    serializer or write-conflict rejection raises DRFValidationError after
    the whole transaction rolls back; so does any other exception.
    """
    created_apartments = 0
    created_rooms = 0
    created_beds = 0

    with transaction.atomic():
        for group in groups:
            room_groups = group['room_groups']
            total_room_count = sum(rg['count'] for rg in room_groups)

            for number in group['numbers']:
                apartment_data = {
                    'building': building.id,
                    'number': str(number),
                    'category': group.get('category'),
                    'apartment_type': group.get('apartment_type'),
                    'room_count': total_room_count,
                    'apartment_capacity': group.get('apartment_capacity'),
                }
                conflict = check_apartment_write_conflict(None, apartment_data)
                if conflict:
                    raise DRFValidationError(conflict)

                apartment_serializer = ApartmentSerializer(data=apartment_data)
                apartment_serializer.is_valid(raise_exception=True)
                apartment = apartment_serializer.save()
                created_apartments += 1

                room_sequence = 0
                for room_group in room_groups:
                    for _ in range(room_group['count']):
                        room_sequence += 1
                        room_data = {
                            'apartment': apartment.id,
                            'name': str(room_sequence),
                            'capacity': room_group['capacity'],
                        }
                        conflict = check_room_write_conflict(None, room_data)
                        if conflict:
                            raise DRFValidationError(conflict)

                        room_serializer = RoomSerializer(data=room_data)
                        room_serializer.is_valid(raise_exception=True)
                        room = room_serializer.save()
                        created_rooms += 1

                        beds = [
                            Bed(room=room, label=f'Bed {bed_index}')
                            for bed_index in range(1, room_group['capacity'] + 1)
                        ]
                        Bed.objects.bulk_create(beds)
                        created_beds += len(beds)

    return created_apartments, created_rooms, created_beds


def lock_building_and_apartments(building_pk):
    """
    Lock a building's row AND every apartment in it, for the duration of
    the caller's transaction, before re-checking occupancy: a
    building-level gender_restriction change affects every apartment
    underneath it, and assign_student_to_room locks the specific apartment
    it writes to (select_for_update on that Apartment pk) - locking every
    apartment here means any concurrent assignment into ANY of them blocks
    until this transaction commits/rolls back, so the "was empty when the
    recommendation was generated" check can never go stale between the
    read and the actual save.

    Must be called inside transaction.atomic(). Returns the locked Building.
    """
    locked_building = Building.objects.select_for_update().get(pk=building_pk)
    # order_by() clears Apartment's default ordering (['building',
    # 'number']) before locking: Django resolves an FK in default
    # ordering through the related model's own Meta.ordering
    # (Building -> ['dorm_type', 'number']), which pulls in a LEFT
    # OUTER JOIN to the nullable DormType FK - Postgres refuses
    # FOR UPDATE on the nullable side of an outer join. .get() sidesteps
    # this by stripping ordering internally; a plain .filter() list does
    # not.
    list(Apartment.objects.select_for_update().filter(building=locked_building).order_by())
    return locked_building


def lock_apartment(apartment_pk):
    """
    Lock an apartment's row for the duration of the caller's transaction
    before re-checking occupancy: assign_student_to_room locks the same
    Apartment pk via select_for_update before creating a BedAssignment, so
    holding this lock for the check+write means the two can never
    interleave.

    Must be called inside transaction.atomic(). Returns the locked Apartment.
    """
    return Apartment.objects.select_for_update().get(pk=apartment_pk)


def record_building_restriction_change(actor, building, previous_restriction):
    """
    After a building edit committed: re-read gender_restriction and, if it
    changed, leave a CONFIG_CHANGE audit record.
    """
    building.refresh_from_db(fields=['gender_restriction'])
    if building.gender_restriction != previous_restriction:
        AssistedAllocationAudit.objects.create(
            action_type=AssistedAllocationAudit.ActionType.CONFIG_CHANGE,
            actor=actor,
            building=building,
            previous_state={'gender_restriction': previous_restriction},
            new_state={'gender_restriction': building.gender_restriction},
        )


def apartment_config_state(apartment):
    return {
        'category': apartment.category,
        'apartment_type': apartment.apartment_type,
    }


def record_apartment_config_change(actor, apartment, previous_state):
    """
    After an apartment edit committed: re-read category/apartment_type and,
    if either changed, leave a CONFIG_CHANGE audit record.
    """
    apartment.refresh_from_db(fields=['category', 'apartment_type'])
    new_state = apartment_config_state(apartment)
    if new_state != previous_state:
        AssistedAllocationAudit.objects.create(
            action_type=AssistedAllocationAudit.ActionType.CONFIG_CHANGE,
            actor=actor,
            apartment=apartment,
            building=apartment.building,
            previous_state=previous_state,
            new_state=new_state,
        )
