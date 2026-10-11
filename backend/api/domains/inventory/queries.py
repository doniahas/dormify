"""
Inventory queryset annotations and read models.
"""

from django.db.models import (
    BooleanField,
    Case,
    Count,
    Exists,
    F,
    IntegerField,
    OuterRef,
    Subquery,
    Value,
    When,
)
from django.db.models.functions import Coalesce, Greatest

from ...models import Apartment, Bed, BedAssignment, DormType, Room


def _annotate_building_inventory_counts(queryset):
    """
    Queryset-level replacement for the per-row queries BuildingSerializer's
    apartment_count/room_count/bed_count/occupied_beds SerializerMethodFields
    used to run once per building (measured baseline BLD-01: ~6 extra SQL
    queries per building row; the buildings performance tests pin a flat
    query count).

    Each count is computed as an independent correlated subquery (Subquery +
    OuterRef grouped by the target FK), not a plain Count() annotation on a
    joined relation. This deliberately avoids the classic Django
    multi-Count() JOIN-multiplication trap, where combining several
    Count()/Sum() annotations on different related paths in one annotate()
    call can silently multiply/inflate every count by the size of the other
    joined relations. Each subquery here is independently grouped and
    evaluated per building, so results are mathematically identical to
    running each of the original four queries once per building - just
    computed inside the single list/detail query instead of once per row.

    Filtering semantics are preserved exactly, matching
    BuildingSerializer.get_apartment_count/get_room_count/get_bed_count/
    get_occupied_beds field-for-field:
    - apartment_count: active apartments only.
    - room_count: active rooms AND active parent apartment.
    - bed_count: beds under an active room AND active apartment (Bed itself
      has no is_active field).
    - occupied_beds: distinct beds with an ACTIVE BedAssignment -
      deliberately NOT filtered by room/apartment is_active, exactly like
      the original get_occupied_beds (a bed can still show as "occupied"
      after its room/apartment is deactivated; free_beds already clamps to
      0 for that case in the serializer, same as before).

    Coalesce(..., 0) makes a building with zero matches yield 0 instead of
    NULL, matching the original .count() behavior (which returns 0, never
    None).
    """
    apartment_count_sq = Apartment.objects.filter(
        building=OuterRef('pk'), is_active=True,
    ).order_by().values('building').annotate(c=Count('id')).values('c')

    room_count_sq = Room.objects.filter(
        apartment__building=OuterRef('pk'), is_active=True, apartment__is_active=True,
    ).order_by().values('apartment__building').annotate(c=Count('id')).values('c')

    bed_count_sq = Bed.objects.filter(
        room__apartment__building=OuterRef('pk'), room__is_active=True, room__apartment__is_active=True,
    ).order_by().values('room__apartment__building').annotate(c=Count('id')).values('c')

    occupied_beds_sq = BedAssignment.objects.filter(
        bed__room__apartment__building=OuterRef('pk'), status=BedAssignment.Status.ACTIVE,
    ).order_by().values('bed__room__apartment__building').annotate(c=Count('bed_id', distinct=True)).values('c')

    return queryset.annotate(
        _apartment_count=Coalesce(Subquery(apartment_count_sq, output_field=IntegerField()), 0),
        _room_count=Coalesce(Subquery(room_count_sq, output_field=IntegerField()), 0),
        _bed_count=Coalesce(Subquery(bed_count_sq, output_field=IntegerField()), 0),
        _occupied_beds=Coalesce(Subquery(occupied_beds_sq, output_field=IntegerField()), 0),
    )


def _annotate_apartment_inventory_counts(queryset):
    """
    Queryset-level replacement for the per-row queries ApartmentSerializer's
    actual_room_count/bed_count/occupied_beds SerializerMethodFields used to
    run once per apartment (measured baseline BLD-02: ~5 extra SQL queries
    per apartment row; the apartments performance tests pin a flat query
    count).

    Same technique as _annotate_building_inventory_counts (BLD-01, already
    fixed): each count is an independent correlated subquery (Subquery +
    OuterRef grouped by the target FK), not a plain Count() annotation on a
    joined relation - this avoids the classic Django multi-Count()
    JOIN-multiplication trap where combining several Count() annotations on
    different related paths in one annotate() call can silently
    multiply/inflate every count by the size of the other joined relations.
    Each subquery here is independently grouped and evaluated per
    apartment, so results are mathematically identical to running each of
    the original three queries once per apartment - just computed inside
    the single list/detail query instead of once per row.

    Filtering semantics are preserved exactly, matching
    ApartmentSerializer.get_actual_room_count/get_bed_count/
    get_occupied_beds field-for-field:
    - actual_room_count: active rooms only.
    - bed_count: beds under an active room (Bed itself has no is_active
      field).
    - occupied_beds: distinct beds with an ACTIVE BedAssignment -
      deliberately NOT filtered by room is_active, exactly like the
      original get_occupied_beds (a bed can still show as "occupied" after
      its room is deactivated; free_beds already clamps to 0 for that case
      in the serializer, same as before).

    Coalesce(..., 0) makes an apartment with zero matches yield 0 instead
    of NULL, matching the original .count() behavior (which returns 0,
    never None).
    """
    room_count_sq = Room.objects.filter(
        apartment=OuterRef('pk'), is_active=True,
    ).order_by().values('apartment').annotate(c=Count('id')).values('c')

    bed_count_sq = Bed.objects.filter(
        room__apartment=OuterRef('pk'), room__is_active=True,
    ).order_by().values('room__apartment').annotate(c=Count('id')).values('c')

    occupied_beds_sq = BedAssignment.objects.filter(
        bed__room__apartment=OuterRef('pk'), status=BedAssignment.Status.ACTIVE,
    ).order_by().values('bed__room__apartment').annotate(c=Count('bed_id', distinct=True)).values('c')

    return queryset.annotate(
        _actual_room_count=Coalesce(Subquery(room_count_sq, output_field=IntegerField()), 0),
        _bed_count=Coalesce(Subquery(bed_count_sq, output_field=IntegerField()), 0),
        _occupied_beds=Coalesce(Subquery(occupied_beds_sq, output_field=IntegerField()), 0),
    )


def _annotate_room_inventory_counts(queryset):
    """
    Queryset-level replacement for the per-row queries RoomSerializer's
    current_occupancy/available_beds/is_full/bed_count/
    has_missing_bed_records fields used to run per room (see performance
    baseline BLD-03: ~7 extra SQL queries per active room row; the rooms
    performance tests pin a flat query count).

    Same technique as _annotate_building_inventory_counts (BLD-01) /
    _annotate_apartment_inventory_counts (BLD-02): the raw counts are
    independent correlated subqueries (Subquery + OuterRef grouped by the
    target FK), not plain Count() annotations combined in one annotate()
    call - avoiding JOIN multiplication. The derived boolean/clamped
    fields (_available_beds, _is_full, _has_missing_bed_records) are then
    computed from those already-annotated columns via Case/When/F
    expressions in a second/third .annotate() step on the same queryset -
    still one SQL statement, still zero extra round trips per row.

    Filtering semantics preserved exactly, matching
    RoomSerializer.current_occupancy/available_beds/is_full/bed_count/
    has_missing_bed_records - and the Room model properties they're
    sourced from - field-for-field:
    - current_occupancy: count of ACTIVE BedAssignments for this room,
      regardless of the room's own is_active (Room.current_occupancy has
      no is_active check).
    - bed_count: total Bed rows for this room (Bed has no is_active
      field).
    - available_beds: 0 if the room is inactive (short-circuit, matches
      Room.available_beds exactly); otherwise
      max(bed_count - distinct_occupied_bed_count, 0).
    - is_full: True if the room is inactive OR available_beds <= 0
      (matches Room.is_full). This collapses to just "available_beds <= 0"
      here, because available_beds is already forced to 0 for inactive
      rooms by the rule above - making that comparison True in both the
      "inactive" and the "active but full" case, exactly like the
      original two-branch property.
    - has_missing_bed_records: bed_count < capacity (matches
      RoomSerializer.get_has_missing_bed_records exactly - no is_active
      dependency there either).
    """
    bed_count_sq = Bed.objects.filter(
        room=OuterRef('pk'),
    ).order_by().values('room').annotate(c=Count('id')).values('c')

    current_occupancy_sq = BedAssignment.objects.filter(
        bed__room=OuterRef('pk'), status=BedAssignment.Status.ACTIVE,
    ).order_by().values('bed__room').annotate(c=Count('id')).values('c')

    # Deliberately a SEPARATE subquery from current_occupancy_sq, mirroring
    # the original code exactly: Room.current_occupancy uses a plain
    # .count() of ACTIVE assignments, while Room.available_beds computes
    # "used" beds via a distinct bed_id count - two differently-written
    # queries that are numerically guaranteed equal only because of the
    # unique_active_assignment_per_bed DB constraint (at most one ACTIVE
    # assignment per bed). Keeping them as distinct annotations preserves
    # that original structure literally rather than assuming the
    # equivalence.
    used_beds_distinct_sq = BedAssignment.objects.filter(
        bed__room=OuterRef('pk'), status=BedAssignment.Status.ACTIVE,
    ).order_by().values('bed__room').annotate(c=Count('bed_id', distinct=True)).values('c')

    queryset = queryset.annotate(
        _bed_count=Coalesce(Subquery(bed_count_sq, output_field=IntegerField()), 0),
        _current_occupancy=Coalesce(Subquery(current_occupancy_sq, output_field=IntegerField()), 0),
        _used_beds_distinct=Coalesce(Subquery(used_beds_distinct_sq, output_field=IntegerField()), 0),
    )
    queryset = queryset.annotate(
        _available_beds=Case(
            When(is_active=False, then=Value(0)),
            default=Greatest(F('_bed_count') - F('_used_beds_distinct'), Value(0)),
            output_field=IntegerField(),
        ),
    )
    queryset = queryset.annotate(
        _is_full=Case(
            When(_available_beds__lte=0, then=Value(True)),
            default=Value(False),
            output_field=BooleanField(),
        ),
        _has_missing_bed_records=Case(
            When(_bed_count__lt=F('capacity'), then=Value(True)),
            default=Value(False),
            output_field=BooleanField(),
        ),
    )
    return queryset


def _annotate_bed_occupancy(queryset):
    """
    Queryset-level replacement for the per-row query BedSerializer's
    is_occupied field used to run once per bed (see performance baseline
    finding BLD-04: ~1 extra SQL query per bed row; the beds performance
    tests pin a flat query count).

    Unlike Buildings/Apartments/Rooms (BLD-01/02/03), this is a single
    boolean check, not a count - Exists(...) is the natural fit rather
    than a Subquery+Coalesce count. Exists() compiles to a correlated
    `EXISTS (SELECT 1 FROM ... WHERE ...)` subquery per row, computed
    inside the same single SQL statement as the list/detail query, with no
    JOIN-multiplication risk (there is nothing else being annotated here
    to multiply against).

    Filtering semantics match Bed.is_occupied exactly:
    `self.assignments.filter(status=ACTIVE).exists()`.
    """
    active_assignment_exists = BedAssignment.objects.filter(
        bed=OuterRef('pk'), status=BedAssignment.Status.ACTIVE,
    )
    return queryset.annotate(_is_occupied=Exists(active_assignment_exists))


def build_inventory_by_housing_type(region=None):
    """
    Detailed inventory breakdown per housing type (DormType), including
    building-level details, for the active inventory - optionally scoped
    to one region. Returns the list of dorm-type rows.
    """
    dorm_types_qs = DormType.objects.prefetch_related(
        'buildings',
        'buildings__apartments',
        'buildings__apartments__rooms',
        'buildings__apartments__rooms__beds',
    ).order_by('code', 'name')

    if region:
        dorm_types_qs = dorm_types_qs.filter(region=region)

    active_assignment_bed_ids = set(
        BedAssignment.objects.filter(
            status=BedAssignment.Status.ACTIVE
        ).values_list('bed_id', flat=True)
    )

    result = []

    for dorm_type in dorm_types_qs:
        buildings_data = []
        dt_total_beds = 0
        dt_occupied_beds = 0
        dt_available_beds = 0
        dt_total_rooms = 0
        dt_total_apts = 0
        dt_buildings = 0

        for building in dorm_type.buildings.all():
            if not building.is_active:
                continue

            b_total_beds = 0
            b_occupied = 0
            b_total_rooms = 0
            b_active_apts = 0

            for apartment in building.apartments.all():
                if not apartment.is_active:
                    continue

                b_active_apts += 1

                for room in apartment.rooms.all():
                    if not room.is_active:
                        continue

                    b_total_rooms += 1
                    room_beds = list(room.beds.all())
                    b_total_beds += len(room_beds)

                    for bed in room_beds:
                        if bed.id in active_assignment_bed_ids:
                            b_occupied += 1

            b_available = max(b_total_beds - b_occupied, 0)
            b_occupancy = round((b_occupied / b_total_beds) * 100, 1) if b_total_beds > 0 else 0

            dt_buildings += 1
            dt_total_apts += b_active_apts
            dt_total_rooms += b_total_rooms
            dt_total_beds += b_total_beds
            dt_occupied_beds += b_occupied
            dt_available_beds += b_available

            buildings_data.append({
                'id': building.id,
                'number': building.number,
                'is_active': building.is_active,
                'total_beds': b_total_beds,
                'occupied_beds': b_occupied,
                'available_beds': b_available,
                'total_rooms': b_total_rooms,
                'apartments': b_active_apts,
                'occupancy_pct': b_occupancy,
            })

        dt_occupancy = round(
            (dt_occupied_beds / dt_total_beds) * 100, 1
        ) if dt_total_beds > 0 else 0

        result.append({
            'id': dorm_type.id,
            'code': dorm_type.code,
            'name': dorm_type.name,
            'buildings_count': dt_buildings,
            'apartments': dt_total_apts,
            'rooms': dt_total_rooms,
            'total_beds': dt_total_beds,
            'occupied_beds': dt_occupied_beds,
            'available_beds': dt_available_beds,
            'temporarily_unavailable_beds': 0,
            'occupancy_pct': dt_occupancy,
            'buildings': buildings_data,
        })

    return result
