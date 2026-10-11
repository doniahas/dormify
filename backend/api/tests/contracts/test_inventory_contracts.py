"""Contracts of the region / dorm-type / building / apartment / room / bed endpoints."""

from api.models import Apartment, Building
from api.serializers import (
    ApartmentSerializer,
    BedSerializer,
    BuildingSerializer,
    DormTypeSerializer,
    RegionSerializer,
    RoomSerializer,
)

from ._support import ContractTestCase, assign, make_full_stack, make_region, make_student, serializer_keys

PAGE_KEYS = ['count', 'next', 'previous', 'results']


class InventoryReadContractTests(ContractTestCase):
    def setUp(self):
        super().setUp()
        self.dorm, self.building, self.apartment, self.room = make_full_stack(self.region)

    def test_list_bodies_are_plain_arrays_of_serializer_rows(self):
        client = self.client_for(self.employee)
        for url, serializer_class in (
            ('/api/regions/', RegionSerializer), ('/api/dorm-types/', DormTypeSerializer),
            ('/api/buildings/', BuildingSerializer), ('/api/apartments/', ApartmentSerializer),
            ('/api/rooms/', RoomSerializer), ('/api/beds/', BedSerializer),
        ):
            with self.subTest(url=url):
                response = client.get(url)
                self.assertEqual(response.status_code, 200, response.data)
                self.assertIsInstance(response.data, list)
                self.assertEqual(len(response.data), 1 if serializer_class is not BedSerializer else 2)
                self.assertKeys(response.data[0], serializer_keys(serializer_class))

    def test_region_and_dorm_type_rows_are_scoped_to_the_caller(self):
        other = make_region('Contract Other Inventory')
        make_full_stack(other)
        employee = self.client_for(self.employee)
        self.assertEqual([r['id'] for r in employee.get('/api/regions/').data], [self.region.id])
        self.assertEqual(len(employee.get('/api/dorm-types/').data), 1)
        self.assertEqual(employee.get(f'/api/buildings/?region={other.id}').data, [])
        self.assertEqual(len(self.client_for(self.admin).get('/api/buildings/').data), 2)

    def test_building_row_values(self):
        row = self.client_for(self.employee).get('/api/buildings/').data[0]
        self.assertEqual(row['region'], self.region.id)
        self.assertEqual(row['dorm_type'], self.dorm.id)
        self.assertEqual((row['apartment_count'], row['room_count'], row['bed_count'], row['occupied_beds'], row['free_beds']), (1, 1, 2, 0, 2))
        self.assertEqual(row['gender_restriction'], '')

    def test_building_actions_bodies(self):
        client = self.client_for(self.employee)
        response = client.get(f'/api/buildings/{self.building.id}/apartments/')
        self.assertKeys(response.data, ['apartments'])
        self.assertKeys(response.data['apartments'][0], serializer_keys(ApartmentSerializer))
        response = client.get(f'/api/buildings/{self.building.id}/rooms/')
        self.assertKeys(response.data, ['rooms'])
        self.assertKeys(response.data['rooms'][0], serializer_keys(RoomSerializer))
        self.assertDetailBody(client.get('/api/buildings/999999/'), 404)


class InventoryWriteContractTests(ContractTestCase):
    def setUp(self):
        super().setUp()
        self.dorm, self.building, self.apartment, self.room = make_full_stack(self.region)

    def test_employee_writes_are_refused_with_the_inventory_error(self):
        employee = self.client_for(self.employee)
        message = 'רק מנהל אזור או מנהל מרכזי יכולים ליצור או לערוך פריטי מלאי'
        self.assertErrorBody(employee.post('/api/buildings/', {'number': 2, 'dorm_type': self.dorm.id}, format='json'), 403, message)
        self.assertErrorBody(employee.post('/api/apartments/', {'building': self.building.id, 'number': '9'}, format='json'), 403, message)
        self.assertErrorBody(employee.patch(f'/api/buildings/{self.building.id}/', {'number': 3}, format='json'), 403, 'רק מנהל אזור או מנהל מרכזי יכול לערוך בניין')
        self.assertErrorBody(employee.patch(f'/api/beds/{self.room.beds.first().id}/', {'label': 'Z'}, format='json'), 403, 'רק מנהל אזור או מנהל מרכזי יכול לערוך תווית מיטה')

    def test_structured_rule_violations_are_flat_field_code_message(self):
        boss = self.client_for(self.boss)
        response = boss.patch(f'/api/buildings/{self.building.id}/', {'is_active': False}, format='json')
        self.assertEqual(response.status_code, 400, response.data)
        self.assertKeys(response.data, ['field', 'code', 'message'])
        self.assertEqual((response.data['field'], response.data['code']), ('is_active', 'USE_AVAILABILITY_WORKFLOW'))
        response = boss.post('/api/buildings/', {'number': self.building.number, 'dorm_type': self.dorm.id}, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertEqual((response.data['field'], response.data['code']), ('number', 'DUPLICATE_BUILDING_NUMBER'))
        assign(make_student(self.dorm, 'INV-OCC'), self.room)
        response = boss.patch(f'/api/rooms/{self.room.id}/', {'capacity': 0}, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertEqual((response.data['field'], response.data['code']), ('capacity', 'CAPACITY_BELOW_OCCUPANCY'))
        response = boss.patch(f'/api/beds/{self.room.beds.first().id}/', {'room': self.room.id}, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertEqual((response.data['field'], response.data['code']), ('room', 'FIELD_NOT_EDITABLE'))

    def test_serializer_validation_errors_are_field_keyed_lists(self):
        response = self.client_for(self.boss).post('/api/apartments/', {'building': self.building.id}, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertIn('number', response.data)
        self.assertIsInstance(response.data['number'], list)

    def test_create_and_update_return_the_serializer_row(self):
        boss = self.client_for(self.boss)
        response = boss.post('/api/buildings/', {'number': 7, 'dorm_type': self.dorm.id}, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        self.assertKeys(response.data, serializer_keys(BuildingSerializer))
        response = boss.patch(f'/api/apartments/{self.apartment.id}/', {'apartment_capacity': 5}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertKeys(response.data, serializer_keys(ApartmentSerializer))
        self.assertEqual(response.data['apartment_capacity'], 5)

    def test_regional_reparenting_is_refused(self):
        other = make_region('Contract Other Write')
        foreign_dorm, foreign_building, _a, _r = make_full_stack(other)
        boss = self.client_for(self.boss)
        self.assertErrorBody(boss.post('/api/buildings/', {'number': 8, 'dorm_type': foreign_dorm.id}, format='json'), 403,
                             'ניתן ליצור בניין רק בתוך סוג מעונות באזור המשויך למשתמש')
        self.assertErrorBody(boss.patch(f'/api/buildings/{self.building.id}/', {'dorm_type': foreign_dorm.id}, format='json'), 403,
                             'לא ניתן להעביר בניין לסוג מעונות מחוץ לאזור המשויך למשתמש')
        self.assertErrorBody(boss.post('/api/apartments/', {'building': foreign_building.id, 'number': '5'}, format='json'), 403,
                             'ניתן ליצור דירה רק בבניין באזור המשויך למשתמש')

    def test_bulk_create_bodies(self):
        boss = self.client_for(self.boss)
        url = f'/api/buildings/{self.building.id}/bulk-create-inventory/'
        self.assertErrorBody(boss.post(url, {}, format='json'), 400, 'apartment_groups must be a non-empty list.')
        response = boss.post(url, {'apartment_groups': [{'numbers': ['1'], 'room_groups': [{'capacity': 1, 'count': 1}]}]}, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertKeys(response.data, ['error', 'code', 'conflicting_numbers'])
        self.assertEqual(response.data['conflicting_numbers'], ['1'])
        response = boss.post(url, {'apartment_groups': [{
            'category': Apartment.Category.MALE, 'apartment_type': Apartment.ApartmentType.SINGLE, 'apartment_capacity': 2,
            'numbers': ['11', '12'], 'room_groups': [{'capacity': 2, 'count': 1}],
        }]}, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data, {'success': True, 'building_id': self.building.id, 'created_apartments': 2, 'created_rooms': 2, 'created_beds': 4})
        self.assertEqual(Building.objects.get(pk=self.building.pk).apartments.count(), 3)
        response = boss.post(url, {'apartment_groups': [{
            'category': 'bad', 'apartment_type': 'single', 'apartment_capacity': 1,
            'numbers': ['21'], 'room_groups': [{'capacity': 1, 'count': 1}],
        }]}, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertKeys(response.data, ['error', 'detail'])
        self.assertEqual(response.data['error'], 'Bulk inventory creation failed; no changes were made.')
