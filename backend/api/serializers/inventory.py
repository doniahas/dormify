"""Inventory serializers and write-conflict helpers."""

from rest_framework import serializers

from ..models import Building, Apartment, Room, Bed, BedAssignment



# Fields that may only be changed through the availability ("what-if")
# workflow (/api/what-if/availability/simulate/ + /confirm/), which shows an
# impact warning and preserves existing occupants instead of silently
# flipping is_active as a side effect of an ordinary inventory edit.
_INVENTORY_AVAILABILITY_ONLY_FIELDS = {'is_active'}


def _availability_only_field_conflict(instance, data):
    """
    Returns a flat {field, code, message} dict if `data` tries to change
    is_active directly, or None if the change is safe. Deliberately
    returned rather than raised: raising serializers.ValidationError from
    inside a serializer's .validate() gets rewrapped by DRF into the
    standard {field: [errors]} shape (via as_serializer_error), which does
    not match the flat structured-error contract these inventory endpoints
    are required to return. Callers (the ViewSets) check this before
    invoking the serializer at all.
    """
    if instance is None:
        return None
    for field_name in _INVENTORY_AVAILABILITY_ONLY_FIELDS:
        if field_name in data and data[field_name] != getattr(instance, field_name):
            return {
                'field': field_name,
                'code': 'USE_AVAILABILITY_WORKFLOW',
                'message': (
                    'שינוי סטטוס פעיל/לא פעיל מתבצע רק דרך תהליך "שינוי זמינות" '
                    '(/api/what-if/availability/), הכולל אזהרת השפעה על דיירים קיימים.'
                ),
            }
    return None


def check_building_write_conflict(instance, data):
    """Flat structured-error check for Building create/update. See
    _availability_only_field_conflict for why this returns instead of
    raising."""
    conflict = _availability_only_field_conflict(instance, data)
    if conflict:
        return conflict

    new_dorm_type_id = data.get('dorm_type', getattr(instance, 'dorm_type_id', None))
    new_number = data.get('number', getattr(instance, 'number', None))
    if new_dorm_type_id is not None and new_number is not None:
        duplicate_qs = Building.objects.filter(dorm_type_id=new_dorm_type_id, number=new_number)
        if instance is not None:
            duplicate_qs = duplicate_qs.exclude(pk=instance.pk)
        if duplicate_qs.exists():
            return {
                'field': 'number',
                'code': 'DUPLICATE_BUILDING_NUMBER',
                'message': 'כבר קיים בניין עם מספר זה עבור סוג המעונות הנבחר.',
            }

    if instance is not None:
        new_restriction = data.get('gender_restriction', instance.gender_restriction)
        if new_restriction != instance.gender_restriction and new_restriction:
            conflicting = BedAssignment.objects.filter(
                bed__room__apartment__building=instance,
                status=BedAssignment.Status.ACTIVE,
            ).exclude(student__gender=new_restriction).exists()
            if conflicting:
                return {
                    'field': 'gender_restriction',
                    'code': 'ACTIVE_OCCUPANT_CONFLICT',
                    'message': (
                        'לא ניתן להגביל את הבניין למגדר זה — קיימים דיירים פעילים '
                        'שאינם תואמים להגבלה החדשה.'
                    ),
                }

    return None


def check_apartment_write_conflict(instance, data):
    """Flat structured-error check for Apartment create/update."""
    conflict = _availability_only_field_conflict(instance, data)
    if conflict:
        return conflict

    if instance is None:
        return None

    active_assignments = list(
        BedAssignment.objects.filter(
            bed__room__apartment=instance, status=BedAssignment.Status.ACTIVE,
        ).select_related('student')
    )

    new_category = data.get('category', instance.category)
    new_apartment_type = data.get('apartment_type', instance.apartment_type)
    category_or_type_changed = (
        new_category != instance.category or new_apartment_type != instance.apartment_type
    )

    if active_assignments and category_or_type_changed:
        from ..domains.allocation.gateway import _housing_matches_apartment
        from copy import copy

        hypothetical = copy(instance)
        hypothetical.category = new_category
        hypothetical.apartment_type = new_apartment_type

        conflicting = [
            assignment for assignment in active_assignments
            if not _housing_matches_apartment(assignment.student, hypothetical)
        ]
        if conflicting:
            changed_field = 'category' if new_category != instance.category else 'apartment_type'
            return {
                'field': changed_field,
                'code': 'ACTIVE_OCCUPANT_CONFLICT',
                'message': (
                    f'לא ניתן לשנות את סיווג הדירה — {len(conflicting)} דיירים פעילים '
                    'אינם תואמים לקטגוריה/סוג הדיור החדשים. יש לפנות את הדירה תחילה.'
                ),
            }

    new_capacity = data.get('apartment_capacity', instance.apartment_capacity)
    occupant_count = len(active_assignments)
    if new_capacity is not None and new_capacity < occupant_count:
        return {
            'field': 'apartment_capacity',
            'code': 'CAPACITY_BELOW_OCCUPANCY',
            'message': (
                f'לא ניתן להגדיר קיבולת ({new_capacity}) נמוכה ממספר הדיירים '
                f'הפעילים הנוכחי ({occupant_count}).'
            ),
        }

    return None


def check_room_write_conflict(instance, data):
    """Flat structured-error check for Room create/update."""
    conflict = _availability_only_field_conflict(instance, data)
    if conflict:
        return conflict

    if instance is None:
        return None

    new_capacity = data.get('capacity', instance.capacity)
    occupancy = instance.current_occupancy
    if new_capacity < occupancy:
        return {
            'field': 'capacity',
            'code': 'CAPACITY_BELOW_OCCUPANCY',
            'message': (
                f'לא ניתן להגדיר קיבולת ({new_capacity}) נמוכה ממספר הדיירים '
                f'הפעילים הנוכחי ({occupancy}).'
            ),
        }

    return None


class BuildingSerializer(serializers.ModelSerializer):
    """Serialize building data"""

    dorm_type_name = serializers.CharField(source='dorm_type.name', read_only=True)
    dorm_type_code = serializers.IntegerField(source='dorm_type.code', read_only=True)
    region = serializers.CharField(source='dorm_type.region.id', read_only=True)
    region_name = serializers.CharField(source='dorm_type.region.name', read_only=True)
    gender_restriction_display = serializers.CharField(source='get_gender_restriction_display', read_only=True)
    apartment_count = serializers.SerializerMethodField()
    room_count = serializers.SerializerMethodField()
    bed_count = serializers.SerializerMethodField()
    occupied_beds = serializers.SerializerMethodField()
    free_beds = serializers.SerializerMethodField()

    class Meta:
        model = Building
        fields = [
            'id',
            'number',
            'dorm_type',
            'dorm_type_name',
            'dorm_type_code',
            'region',
            'region_name',
            'is_active',
            'gender_restriction',
            'gender_restriction_display',
            'apartment_count',
            'room_count',
            'bed_count',
            'occupied_beds',
            'free_beds',
        ]

    # apartment_count/room_count/bed_count/occupied_beds are computed at the
    # queryset level (see views._annotate_building_inventory_counts) as
    # correlated-subquery annotations (_apartment_count/_room_count/
    # _bed_count/_occupied_beds), so BuildingViewSet.get_queryset() results
    # carry them with zero extra queries per row (performance baseline
    # finding BLD-01). Each getter here reads that annotation when present
    # (fast path) and falls back to the original per-object query only when
    # it isn't - e.g. a freshly created Building from
    # BuildingViewSet.create(), which serializes a plain unannotated
    # instance returned by serializer.save() rather than one fetched via
    # get_queryset(). The fallback query is byte-for-byte the original
    # get_*_count implementation, so behavior/values are identical either
    # way - only the query count differs.
    def get_apartment_count(self, obj):
        value = getattr(obj, '_apartment_count', None)
        if value is not None:
            return value
        return obj.apartments.filter(is_active=True).count()

    def get_room_count(self, obj):
        value = getattr(obj, '_room_count', None)
        if value is not None:
            return value
        return Room.objects.filter(apartment__building=obj, is_active=True, apartment__is_active=True).count()

    def get_bed_count(self, obj):
        value = getattr(obj, '_bed_count', None)
        if value is not None:
            return value
        return Bed.objects.filter(room__apartment__building=obj, room__is_active=True, room__apartment__is_active=True).count()

    def get_occupied_beds(self, obj):
        value = getattr(obj, '_occupied_beds', None)
        if value is not None:
            return value
        return BedAssignment.objects.filter(
            bed__room__apartment__building=obj, status=BedAssignment.Status.ACTIVE,
        ).values('bed_id').distinct().count()

    def get_free_beds(self, obj):
        return max(self.get_bed_count(obj) - self.get_occupied_beds(obj), 0)


class ApartmentSerializer(serializers.ModelSerializer):
    """Serialize apartment data"""

    building_number = serializers.IntegerField(source='building.number', read_only=True)
    category_display = serializers.CharField(source='get_category_display', read_only=True)
    apartment_type_display = serializers.CharField(source='get_apartment_type_display', read_only=True)
    inactive_reason_display = serializers.CharField(source='get_inactive_reason_display', read_only=True)
    region = serializers.CharField(source='region.id', read_only=True)
    region_name = serializers.CharField(source='region.name', read_only=True)
    dorm_type = serializers.CharField(source='dorm_type.name', read_only=True)
    actual_room_count = serializers.SerializerMethodField()
    bed_count = serializers.SerializerMethodField()
    occupied_beds = serializers.SerializerMethodField()
    free_beds = serializers.SerializerMethodField()

    class Meta:
        model = Apartment
        fields = [
            'id',
            'building',
            'building_number',
            'number',
            'category',
            'category_display',
            'apartment_type',
            'apartment_type_display',
            'room_count',
            'actual_room_count',
            'apartment_capacity',
            'bed_count',
            'occupied_beds',
            'free_beds',
            'is_active',
            'inactive_reason',
            'inactive_reason_display',
            'region',
            'region_name',
            'dorm_type',
        ]

    # actual_room_count/bed_count/occupied_beds are computed at the
    # queryset level (see views._annotate_apartment_inventory_counts) as
    # correlated-subquery annotations (_actual_room_count/_bed_count/
    # _occupied_beds), so ApartmentViewSet.get_queryset() results carry
    # them with zero extra queries per row (performance baseline finding
    # BLD-02). Each getter here reads that annotation when present (fast
    # path) and falls back to the original per-object query only when it
    # isn't - e.g. a freshly created Apartment from
    # ApartmentViewSet.create(), which serializes a plain unannotated
    # instance returned by serializer.save() rather than one fetched via
    # get_queryset(). The fallback query is byte-for-byte the original
    # get_*_count implementation, so behavior/values are identical either
    # way - only the query count differs.
    def get_actual_room_count(self, obj):
        value = getattr(obj, '_actual_room_count', None)
        if value is not None:
            return value
        return obj.rooms.filter(is_active=True).count()

    def get_bed_count(self, obj):
        value = getattr(obj, '_bed_count', None)
        if value is not None:
            return value
        return Bed.objects.filter(room__apartment=obj, room__is_active=True).count()

    def get_occupied_beds(self, obj):
        value = getattr(obj, '_occupied_beds', None)
        if value is not None:
            return value
        return BedAssignment.objects.filter(
            bed__room__apartment=obj, status=BedAssignment.Status.ACTIVE,
        ).values('bed_id').distinct().count()

    def get_free_beds(self, obj):
        return max(self.get_bed_count(obj) - self.get_occupied_beds(obj), 0)


class RoomSerializer(serializers.ModelSerializer):
    """Serialize room data"""

    apartment_number = serializers.CharField(source='apartment.number', read_only=True)
    building_number = serializers.IntegerField(source='building.number', read_only=True)
    region = serializers.CharField(source='region.id', read_only=True)
    region_name = serializers.CharField(source='region.name', read_only=True)
    number = serializers.CharField(read_only=True)
    current_occupancy = serializers.SerializerMethodField()
    available_beds = serializers.SerializerMethodField()
    is_full = serializers.SerializerMethodField()
    bed_count = serializers.SerializerMethodField()
    has_missing_bed_records = serializers.SerializerMethodField()

    class Meta:
        model = Room
        fields = [
            'id',
            'apartment',
            'apartment_number',
            'building_number',
            'region',
            'region_name',
            'name',
            'number',
            'capacity',
            'bed_count',
            'current_occupancy',
            'available_beds',
            'is_full',
            'is_active',
            'has_missing_bed_records',
        ]

    # current_occupancy/available_beds/is_full/bed_count/
    # has_missing_bed_records are computed at the queryset level (see
    # views._annotate_room_inventory_counts) as correlated-subquery /
    # Case-expression annotations (_current_occupancy/_available_beds/
    # _is_full/_bed_count/_has_missing_bed_records), so
    # RoomViewSet.get_queryset() results carry them with zero extra
    # queries per row (performance baseline finding BLD-03). Each getter
    # here reads that annotation when present (fast path) and falls back
    # to the original Room model property / query only when it isn't -
    # e.g. a freshly created Room from RoomViewSet.create(), which
    # serializes a plain unannotated instance returned by
    # serializer.save() rather than one fetched via get_queryset(). The
    # fallback path is byte-for-byte the original property/query, so
    # behavior/values are identical either way - only the query count
    # differs. `getattr(..., None) is not None` correctly distinguishes a
    # legitimately-annotated `0`/`False` from "annotation absent", since
    # every annotation is wrapped in Coalesce(...) or a Case with an
    # explicit default - it is never actually NULL when present.
    def get_current_occupancy(self, obj):
        value = getattr(obj, '_current_occupancy', None)
        if value is not None:
            return value
        return obj.current_occupancy

    def get_available_beds(self, obj):
        value = getattr(obj, '_available_beds', None)
        if value is not None:
            return value
        return obj.available_beds

    def get_is_full(self, obj):
        value = getattr(obj, '_is_full', None)
        if value is not None:
            return value
        return obj.is_full

    def get_bed_count(self, obj):
        value = getattr(obj, '_bed_count', None)
        if value is not None:
            return value
        return obj.beds.count()

    def get_has_missing_bed_records(self, obj):
        # Bed rows are only materialized by the admin-only
        # `manage.py materialize_beds` command, never automatically on
        # capacity edits (see ensure_room_beds in api/domains/placement/beds.py) — surfaced here
        # so staff can see the gap instead of it looking like a silent bug.
        value = getattr(obj, '_has_missing_bed_records', None)
        if value is not None:
            return value
        return obj.beds.count() < obj.capacity


class BedSerializer(serializers.ModelSerializer):
    """Serialize bed data.

    Beds are only editable at the label level: individual creation/deletion
    and activation/deactivation are not supported by the current schema —
    Bed rows are derived from Room.capacity and materialized exclusively by
    the admin-only `manage.py materialize_beds` command.
    """

    room_name = serializers.CharField(source='room.name', read_only=True)
    apartment_number = serializers.CharField(source='room.apartment.number', read_only=True)
    building_number = serializers.IntegerField(source='room.apartment.building.number', read_only=True)
    is_occupied = serializers.SerializerMethodField()

    class Meta:
        model = Bed
        fields = [
            'id',
            'label',
            'room',
            'room_name',
            'apartment_number',
            'building_number',
            'is_occupied',
        ]
        read_only_fields = ['room']

    # is_occupied is computed at the queryset level (see
    # views._annotate_bed_occupancy) as an Exists(...) annotation
    # (_is_occupied), so BedViewSet.get_queryset() results carry it with
    # zero extra queries per row (performance baseline finding BLD-04).
    # Reads that annotation when present (fast path) and falls back to
    # the original Bed.is_occupied model property only when it isn't -
    # there is no bed-creation endpoint (BedViewSet only supports
    # get/patch/head/options), so the only realistic unannotated case is
    # a Bed instance constructed/fetched some other way; the fallback
    # keeps that path correct regardless. `is not None` correctly
    # distinguishes a legitimately-annotated `False` from "annotation
    # absent", since Exists(...) is a real boolean and never NULL.
    def get_is_occupied(self, obj):
        value = getattr(obj, '_is_occupied', None)
        if value is not None:
            return value
        return obj.is_occupied
