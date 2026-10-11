"""Direct tests for api.domains.whatif (queries, simulation, services)."""

from django.test import TestCase

from api.domains.whatif import queries, services, simulation
from api.models import Building, StudentRequest

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


class WhatIfFixtures(TestCase):
    def setUp(self):
        self.region = make_region('WhatIf Region')
        self.boss = make_boss(self.region)
        self.dorm = make_dorm(self.region)
        self.building = make_building(self.dorm)
        self.apartment = make_apartment(self.building)
        self.room = make_room(self.apartment, capacity=2)
        self.other_building = make_building(self.dorm)
        self.other_room = make_room(make_apartment(self.other_building), capacity=1)
        self.occupant = make_student(self.dorm, 'WI-OCC')
        assign(self.occupant, self.room)
        self.elsewhere = make_student(self.dorm, 'WI-ELSE')
        assign(self.elsewhere, self.other_room)
        self.unassigned = make_student(self.dorm, 'WI-FREE')


class WhatIfQueryTests(WhatIfFixtures):
    def test_lookups_reject_unknown_ids(self):
        with self.assertRaises(ValueError):
            queries.buildings_for_ids([self.building.id, 999999])
        with self.assertRaises(ValueError):
            queries.targets_for_ids('room', [999999])
        self.assertEqual(list(queries.buildings_for_ids([self.building.id])), [self.building])

    def test_affected_assignments_follow_the_hierarchy_level(self):
        for target_type, target_id in (
            ('building', self.building.id), ('apartment', self.apartment.id), ('room', self.room.id),
        ):
            affected = queries.affected_assignments_for_targets(target_type, [target_id])
            self.assertEqual([a.student.student_id for a in affected], ['WI-OCC'], target_type)

    def test_snapshot_region_is_the_single_shared_region(self):
        targets = queries.targets_for_ids('building', [self.building.id])
        self.assertEqual(queries.snapshot_region_for_targets('building', targets), self.region)
        rooms = queries.targets_for_ids('room', [self.other_room.id])
        self.assertEqual(queries.snapshot_region_for_targets('room', rooms), self.region)

        other_region = make_region('WhatIf Other')
        foreign = make_building(make_dorm(other_region))
        mixed = queries.targets_for_ids('building', [self.building.id, foreign.id])
        self.assertIsNone(queries.snapshot_region_for_targets('building', mixed))

    def test_analysis_snapshot_before_and_after_exclusion(self):
        before = queries.analysis_snapshot(region=self.region)
        self.assertEqual(before['total_students'], 3)
        self.assertEqual(before['assigned_students'], 2)
        self.assertEqual(before['total_capacity'], 3)
        self.assertEqual(before['occupied_beds'], 2)
        self.assertEqual(before['occupancy_rate'], 66.67)

        after = queries.analysis_snapshot(region=self.region, excluded_building_ids=[self.building.id])
        self.assertEqual(after['total_buildings'], 1)
        self.assertEqual(after['total_capacity'], 1)
        self.assertEqual(after['occupied_beds'], 1)
        self.assertEqual(after['unassigned_students'], 2)

        by_room = queries.analysis_snapshot(region=self.region, excluded_room_ids=[self.room.id])
        self.assertEqual(by_room['total_rooms'], 1)
        self.assertEqual(by_room['total_buildings'], 2)

    def test_lost_resources_per_target_type(self):
        self.assertEqual(queries.lost_resources_for_targets('building', [self.building.id]), {
            'lost_apartments': 1, 'lost_rooms': 1, 'lost_capacity': 2, 'lost_beds': 2,
        })
        self.assertEqual(queries.lost_resources_for_targets('apartment', [self.apartment.id]), {
            'lost_apartments': 1, 'lost_rooms': 1, 'lost_capacity': 2, 'lost_beds': 2,
        })
        self.assertEqual(queries.lost_resources_for_targets('room', [self.room.id]), {
            'lost_apartments': 1, 'lost_rooms': 1, 'lost_capacity': 2, 'lost_beds': 2,
        })


class WhatIfSimulationTests(WhatIfFixtures):
    def test_building_inactivation_simulation_shape(self):
        buildings = queries.buildings_for_ids([self.building.id])
        result = simulation.simulate_building_inactivation(buildings)

        self.assertEqual(result['scenario'], 'building_inactivation')
        self.assertEqual([b['id'] for b in result['selected_buildings']], [self.building.id])
        self.assertEqual(result['summary']['affected_students_count'], 1)
        self.assertEqual(result['summary']['male_count'], 1)
        self.assertEqual(result['summary']['lost_beds'], 2)
        self.assertEqual(result['breakdowns']['gender'], [{'value': 'male', 'count': 1}])
        self.assertEqual(result['affected_students'][0]['student_id'], 'WI-OCC')
        self.assertEqual(result['affected_students'][0]['status'], 'needs_transfer')
        self.assertEqual(result['analysis_after']['total_buildings'], 1)
        self.assertTrue(Building.objects.get(pk=self.building.pk).is_active)

    def test_building_simulation_with_a_regionless_building_uses_the_nationwide_snapshot(self):
        make_student(make_dorm(make_region('WhatIf Elsewhere')), 'WI-OTHER-REGION')
        regionless = make_building(None)

        single = simulation.simulate_building_inactivation(queries.buildings_for_ids([self.building.id]))
        self.assertEqual(single['analysis_before']['total_students'], 3)

        mixed = simulation.simulate_building_inactivation(
            queries.buildings_for_ids([self.building.id, regionless.id]),
        )
        self.assertEqual(mixed['analysis_before']['total_students'], 4)

    def test_availability_simulation_for_a_room(self):
        targets = queries.targets_for_ids('room', [self.room.id])
        result = simulation.simulate_availability_change('room', [self.room.id], targets)

        self.assertEqual(result['scenario'], 'room_availability_change')
        self.assertEqual(result['target_ids'], [self.room.id])
        self.assertEqual(result['selected_targets'][0]['target_type'], 'room')
        self.assertEqual(result['selected_targets'][0]['capacity'], 2)
        self.assertEqual(result['summary']['lost_rooms'], 1)
        self.assertEqual(result['analysis_after']['total_rooms'], 1)

    def test_count_by_value_folds_missing_values(self):
        rows = [{'gender': 'male'}, {'gender': ''}, {'gender': 'male'}]
        self.assertEqual(simulation.count_by_value(rows, 'gender'), [
            {'value': 'male', 'count': 2}, {'value': 'not_specified', 'count': 1},
        ])


class WhatIfServiceTests(WhatIfFixtures):
    def test_confirm_building_inactivation_deactivates_and_raises_requests_once(self):
        buildings = queries.buildings_for_ids([self.building.id])
        affected = list(queries.affected_assignments_for_targets('building', [self.building.id]))

        created, skipped, ids = services.confirm_building_inactivation(
            buildings, affected, reason='works', requested_by=self.boss,
        )

        self.assertEqual((created, skipped), (1, 0))
        request = StudentRequest.objects.get(pk=ids[0])
        self.assertEqual(request.student, self.occupant)
        self.assertEqual(request.request_type, StudentRequest.RequestType.ROOM)
        self.assertEqual(request.status, StudentRequest.Status.PENDING)
        self.assertEqual(request.request_number, f'REQ-{request.id:06d}')
        self.assertEqual(request.source_region_id, self.region.id)
        self.assertTrue(request.current_assignment_snapshot['assigned'])
        self.assertFalse(Building.objects.get(pk=self.building.pk).is_active)

        # Idempotent: the same occupant already has a pending request.
        created, skipped, ids = services.confirm_building_inactivation(
            buildings, affected, reason='again', requested_by=self.boss, inactivate_buildings=False,
        )
        self.assertEqual((created, skipped, ids), (0, 1, []))

    def test_apply_availability_change_reactivate_creates_no_requests(self):
        self.room.is_active = False
        self.room.save()

        created, skipped, ids = services.apply_availability_change(
            'room', [self.room.id], [], action='reactivate', reason='', requested_by=self.boss,
        )

        self.assertEqual((created, skipped, ids), (0, 0, []))
        self.room.refresh_from_db()
        self.assertTrue(self.room.is_active)
        self.assertEqual(StudentRequest.objects.count(), 0)

    def test_apply_availability_change_inactivate_apartment(self):
        affected = list(queries.affected_assignments_for_targets('apartment', [self.apartment.id]))
        created, _skipped, _ids = services.apply_availability_change(
            'apartment', [self.apartment.id], affected, action='inactivate',
            reason='maintenance', requested_by=self.boss,
        )
        self.apartment.refresh_from_db()
        self.assertFalse(self.apartment.is_active)
        self.assertEqual(created, 1)
        self.assertEqual(StudentRequest.objects.get().reason, 'maintenance')
