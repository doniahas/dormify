"""Direct tests for api.domains.inventory.services and build_inventory_by_housing_type."""

from django.db import transaction
from django.test import TestCase
from rest_framework.exceptions import ValidationError as DRFValidationError

from api.domains.inventory import services
from api.domains.inventory.queries import build_inventory_by_housing_type
from api.models import Apartment, AssistedAllocationAudit, Bed, Room

from ._fixtures import (
    assign,
    make_apartment,
    make_boss,
    make_building,
    make_dorm,
    make_region,
    make_room,
    make_student,
)


class BulkInventoryValidationTests(TestCase):
    def setUp(self):
        self.region = make_region('Bulk Region')
        self.building = make_building(make_dorm(self.region))

    def _error(self, groups):
        with self.assertRaises(services.BulkInventoryError) as raised:
            services.validate_bulk_inventory_groups(self.building, groups)
        return raised.exception.payload

    def test_shape_errors_name_the_offending_path(self):
        self.assertEqual(self._error([]), {'error': 'apartment_groups must be a non-empty list.'})
        self.assertEqual(self._error(['x']), {'error': 'apartment_groups[0] must be an object.'})
        self.assertEqual(
            self._error([{'numbers': [], 'room_groups': [{'capacity': 1, 'count': 1}]}]),
            {'error': 'apartment_groups[0].numbers must be a non-empty list.'},
        )
        self.assertEqual(
            self._error([{'numbers': ['1'], 'room_groups': []}]),
            {'error': 'apartment_groups[0].room_groups must be a non-empty list.'},
        )
        self.assertEqual(
            self._error([{'numbers': ['1'], 'room_groups': [{'capacity': 0, 'count': 1}]}]),
            {'error': 'apartment_groups[0].room_groups[0].capacity must be a positive integer.'},
        )
        self.assertEqual(
            self._error([{'numbers': ['1'], 'room_groups': [{'capacity': 1, 'count': 'two'}]}]),
            {'error': 'apartment_groups[0].room_groups[0].count must be a positive integer.'},
        )

    def test_duplicate_numbers_in_request_and_in_building(self):
        groups = [{'numbers': ['1', 1], 'room_groups': [{'capacity': 1, 'count': 1}]}]
        self.assertEqual(self._error(groups)['code'], 'DUPLICATE_APARTMENT_NUMBER')

        make_apartment(self.building, number='7')
        payload = self._error([{'numbers': ['7', '8'], 'room_groups': [{'capacity': 1, 'count': 1}]}])
        self.assertEqual(payload['code'], 'DUPLICATE_APARTMENT_NUMBER')
        self.assertEqual(payload['conflicting_numbers'], ['7'])

    def test_valid_groups_pass(self):
        services.validate_bulk_inventory_groups(
            self.building, [{'numbers': ['1', '2'], 'room_groups': [{'capacity': 2, 'count': 1}]}],
        )


class BulkInventoryCreateTests(TestCase):
    def setUp(self):
        self.region = make_region('Bulk Create Region')
        self.building = make_building(make_dorm(self.region))

    def test_creates_apartments_rooms_and_materialized_beds(self):
        groups = [{
            'category': Apartment.Category.FEMALE, 'apartment_type': Apartment.ApartmentType.SINGLE,
            'apartment_capacity': 3, 'numbers': ['101', '102'],
            'room_groups': [{'capacity': 1, 'count': 1}, {'capacity': 2, 'count': 1}],
        }]

        created = services.bulk_create_inventory(self.building, groups)

        self.assertEqual(created, (2, 4, 6))
        apartment = Apartment.objects.get(building=self.building, number='101')
        self.assertEqual(apartment.room_count, 2)
        self.assertEqual(list(apartment.rooms.order_by('name').values_list('name', 'capacity')), [('1', 1), ('2', 2)])
        self.assertEqual(
            sorted(Bed.objects.filter(room__apartment=apartment).values_list('label', flat=True)),
            ['Bed 1', 'Bed 1', 'Bed 2'],
        )

    def test_serializer_rejection_rolls_back_everything(self):
        groups = [
            {'category': Apartment.Category.MALE, 'apartment_type': Apartment.ApartmentType.SINGLE,
             'apartment_capacity': 1, 'numbers': ['201'], 'room_groups': [{'capacity': 1, 'count': 1}]},
            {'category': 'not-a-category', 'apartment_type': Apartment.ApartmentType.SINGLE,
             'apartment_capacity': 1, 'numbers': ['202'], 'room_groups': [{'capacity': 1, 'count': 1}]},
        ]
        with self.assertRaises(DRFValidationError):
            with transaction.atomic():
                services.bulk_create_inventory(self.building, groups)
        self.assertEqual(Apartment.objects.filter(building=self.building).count(), 0)
        self.assertEqual(Room.objects.count(), 0)


class ConfigChangeAuditTests(TestCase):
    def setUp(self):
        self.region = make_region('Audit Region')
        self.boss = make_boss(self.region)
        self.building = make_building(make_dorm(self.region))
        self.apartment = make_apartment(self.building)

    def test_building_restriction_change_is_audited_only_when_it_changed(self):
        services.record_building_restriction_change(self.boss, self.building, self.building.gender_restriction)
        self.assertEqual(AssistedAllocationAudit.objects.count(), 0)

        services.record_building_restriction_change(self.boss, self.building, 'something-else')
        audit = AssistedAllocationAudit.objects.get()
        self.assertEqual(audit.action_type, AssistedAllocationAudit.ActionType.CONFIG_CHANGE)
        self.assertEqual(audit.building, self.building)
        self.assertEqual(audit.previous_state, {'gender_restriction': 'something-else'})
        self.assertEqual(audit.new_state, {'gender_restriction': self.building.gender_restriction})

    def test_apartment_config_change_is_audited_with_both_fields(self):
        previous = services.apartment_config_state(self.apartment)
        Apartment.objects.filter(pk=self.apartment.pk).update(category=Apartment.Category.FEMALE)

        services.record_apartment_config_change(self.boss, self.apartment, previous)

        audit = AssistedAllocationAudit.objects.get()
        self.assertEqual(audit.apartment, self.apartment)
        self.assertEqual(audit.building, self.building)
        self.assertEqual(audit.previous_state, previous)
        self.assertEqual(audit.new_state, {'category': 'female', 'apartment_type': previous['apartment_type']})

    def test_locks_return_fresh_rows_inside_a_transaction(self):
        with transaction.atomic():
            locked_building = services.lock_building_and_apartments(self.building.pk)
            locked_apartment = services.lock_apartment(self.apartment.pk)
        self.assertEqual(locked_building, self.building)
        self.assertEqual(locked_apartment, self.apartment)


class InventoryByHousingTypeTests(TestCase):
    def test_counts_active_inventory_and_occupancy_per_dorm_type(self):
        region = make_region('Housing Region')
        dorm = make_dorm(region, name='Housing Dorm', code='7001')
        building = make_building(dorm)
        apartment = make_apartment(building)
        room = make_room(apartment, capacity=2)
        inactive_apartment = make_apartment(building, number='9', is_active=False)
        make_room(inactive_apartment, capacity=5)
        make_building(dorm, is_active=False)
        assign(make_student(dorm, 'HT-1'), room)

        other_region = make_region('Housing Other')
        make_building(make_dorm(other_region))

        rows = build_inventory_by_housing_type(region)

        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual((row['code'], row['buildings_count'], row['apartments'], row['rooms']), (7001, 1, 1, 1))
        self.assertEqual((row['total_beds'], row['occupied_beds'], row['available_beds']), (2, 1, 1))
        self.assertEqual(row['occupancy_pct'], 50.0)
        self.assertEqual(row['buildings'][0]['number'], building.number)
        self.assertEqual(len(build_inventory_by_housing_type(None)), 2)
