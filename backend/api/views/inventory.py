"""Inventory view ownership."""

import traceback

from django.db import transaction
from rest_framework import status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from ..domains.inventory.queries import (
    _annotate_apartment_inventory_counts,
    _annotate_bed_occupancy,
    _annotate_building_inventory_counts,
    _annotate_room_inventory_counts,
    build_inventory_by_housing_type,
)
from ..domains.inventory.services import (
    BulkInventoryError,
    apartment_config_state,
    bulk_create_inventory,
    lock_apartment,
    lock_building_and_apartments,
    record_apartment_config_change,
    record_building_restriction_change,
    validate_bulk_inventory_groups,
)
from ..domains.placement.services import _room_region
from ..models import (
    Apartment,
    Bed,
    Building,
    DormType,
    Region,
    Room,
)
from ..permissions import (
    IsCentralAdmin,
    _inventory_create_permission_error,
    _region_scoped_inventory_queryset,
    _resolve_region,
)
from ..serializers import (
    ApartmentSerializer,
    BedSerializer,
    BuildingSerializer,
    DormTypeSerializer,
    RegionSerializer,
    RoomSerializer,
    check_apartment_write_conflict,
    check_building_write_conflict,
    check_room_write_conflict,
)
from ..contracts.errors import error_response


class RegionViewSet(viewsets.ModelViewSet):
    serializer_class = RegionSerializer
    permission_classes = [IsAuthenticated]

    def get_permissions(self):
        # G3-05: Region is a system-level definition, not operational data -
        # any authenticated regional/employee user may still read it
        # (scoped to their own region below), but creating/editing/deleting
        # a region is a central-admin-only action.
        if self.action in ('create', 'update', 'partial_update', 'destroy'):
            return [IsAuthenticated(), IsCentralAdmin()]
        return [IsAuthenticated()]

    def get_queryset(self):
        queryset = Region.objects.all()
        user = self.request.user

        if user.is_central_admin:
            return queryset

        if not user.region_id:
            return queryset.none()

        return queryset.filter(pk=user.region_id)

class DormTypeViewSet(viewsets.ModelViewSet):
    serializer_class = DormTypeSerializer
    permission_classes = [IsAuthenticated]

    def get_permissions(self):
        # G3-05: same rule as RegionViewSet above - DormType is a
        # system-level definition, central-admin-only to write.
        if self.action in ('create', 'update', 'partial_update', 'destroy'):
            return [IsAuthenticated(), IsCentralAdmin()]
        return [IsAuthenticated()]

    def get_queryset(self):
        queryset = DormType.objects.select_related('region').all()
        user = self.request.user

        if user.is_central_admin:
            return queryset

        if not user.region_id:
            return queryset.none()

        return queryset.filter(region_id=user.region_id)

def _parse_is_active_filter(request, default='true'):
    """
    Shared 'Active status: all / active / inactive' query-param parsing for
    the inventory viewsets. Returns True, False, or None (meaning: no
    is_active filter, i.e. 'all'). Defaults to True (active-only) so
    existing callers that never pass this param keep their current
    behavior unchanged.
    """
    raw = (request.query_params.get('is_active') or default or '').strip().lower()
    if raw in ('all', ''):
        return None
    if raw in ('true', '1', 'active'):
        return True
    if raw in ('false', '0', 'inactive'):
        return False
    return None

class BuildingViewSet(viewsets.ModelViewSet):
    serializer_class = BuildingSerializer
    permission_classes = [IsAuthenticated]
    # No PUT (full-replace semantics don't fit the partial edit-drawer UI)
    # and no DELETE — buildings are never hard-deleted through this API,
    # only deactivated via the availability workflow (see
    # _reject_direct_availability_change / what_if_availability_confirm).
    http_method_names = ['get', 'post', 'patch', 'head', 'options']

    def get_queryset(self):
        queryset = _annotate_building_inventory_counts(
            Building.objects.select_related(
                'dorm_type',
                'dorm_type__region',
            )
        )
        is_active = _parse_is_active_filter(self.request)
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active)

        user = self.request.user
        region_value = self.request.query_params.get('region')
        return _region_scoped_inventory_queryset(user, queryset, region_value, 'dorm_type__region')

    def create(self, request, *args, **kwargs):
        if not request.user.is_boss:
            return _inventory_create_permission_error()

        if not request.user.is_central_admin:
            dorm_type = DormType.objects.filter(
                pk=request.data.get('dorm_type')
            ).select_related('region').first()
            if not dorm_type or dorm_type.region_id != request.user.region_id:
                return error_response(status.HTTP_403_FORBIDDEN, 'ניתן ליצור בניין רק בתוך סוג מעונות באזור המשויך למשתמש')

        conflict = check_building_write_conflict(None, request.data)
        if conflict:
            return Response(conflict, status=status.HTTP_400_BAD_REQUEST)

        return super().create(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        # Editing a building (e.g. gender_restriction) is a boss-level
        # action; ordinary employees may only view. get_queryset() above
        # already scopes region_boss users to their own region, so a boss
        # editing a building outside their region gets a 404 from
        # get_object() below rather than reaching this check.
        if not request.user.is_boss:
            return error_response(status.HTTP_403_FORBIDDEN, 'רק מנהל אזור או מנהל מרכזי יכול לערוך בניין')

        instance = self.get_object()

        # G3-04: explicitly re-validate the OBJECT'S REAL region against
        # the caller's own region - never rely solely on get_queryset()
        # (which is itself query-param-influenced) as the authorization
        # check for a write. Belt-and-braces alongside the
        # _region_scoped_inventory_queryset() fix above.
        if not request.user.is_central_admin:
            real_region_id = instance.dorm_type.region_id if instance.dorm_type else None
            if real_region_id != request.user.region_id:
                return error_response(status.HTTP_403_FORBIDDEN, 'אין הרשאה לערוך בניין באזור זה')

            # G3-12: reparenting - a PATCH that changes dorm_type must not
            # move this building into a DormType belonging to another
            # region. Only relevant when 'dorm_type' is actually present in
            # the request body (a normal edit that omits it is unaffected).
            new_dorm_type_id = request.data.get('dorm_type')
            if new_dorm_type_id is not None and str(new_dorm_type_id) != str(instance.dorm_type_id):
                new_dorm_type = DormType.objects.filter(pk=new_dorm_type_id).select_related('region').first()
                if not new_dorm_type or new_dorm_type.region_id != request.user.region_id:
                    return error_response(status.HTTP_403_FORBIDDEN, 'לא ניתן להעביר בניין לסוג מעונות מחוץ לאזור המשויך למשתמש')

        with transaction.atomic():
            # Hold the building and all its apartments locked for the
            # occupancy re-check AND the save (see
            # lock_building_and_apartments), so a "שינוי הגדרה" suggestion
            # built while the building was empty cannot be applied moments
            # after another employee filled a bed.
            locked_instance = lock_building_and_apartments(instance.pk)

            conflict = check_building_write_conflict(locked_instance, request.data)
            if conflict:
                return Response(conflict, status=status.HTTP_400_BAD_REQUEST)

            previous_restriction = locked_instance.gender_restriction
            response = super().update(request, *args, **kwargs)
            if response.status_code == 200:
                record_building_restriction_change(request.user, locked_instance, previous_restriction)
        return response

    @action(detail=True, methods=['get'])
    def apartments(self, request, pk=None):
        building = self.get_object()
        apartments = building.apartments.filter(is_active=True).select_related('building')

        category = request.query_params.get('category')
        if category:
            apartments = apartments.filter(category=category)

        apartment_type = request.query_params.get('apartment_type')
        if apartment_type:
            apartments = apartments.filter(apartment_type=apartment_type)

        serializer = ApartmentSerializer(apartments, many=True)
        return Response({'apartments': serializer.data})

    @action(detail=True, methods=['get'])
    def rooms(self, request, pk=None):
        building = self.get_object()
        rooms = Room.objects.filter(
            apartment__building=building,
            is_active=True,
            apartment__is_active=True,
            apartment__building__is_active=True,
        ).select_related(
            'apartment',
            'apartment__building',
            'apartment__building__dorm_type',
            'apartment__building__dorm_type__region',
        )

        available_only = request.query_params.get('available', 'false') == 'true'
        if available_only:
            rooms = [room for room in rooms if not room.is_full]

        serializer = RoomSerializer(rooms, many=True)
        return Response({'rooms': serializer.data})

    @action(detail=True, methods=['post'], url_path='bulk-create-inventory')
    def bulk_create_inventory(self, request, pk=None):
        """
        Transactionally create many Apartments - each with its own Rooms and
        materialized Beds - under this Building in a single call. Backend
        counterpart of the Building Setup Wizard's apartment/room
        configuration-group step, so staff never have to create a dozen
        near-identical apartments one at a time.

        Reuses ApartmentSerializer/RoomSerializer for validation exactly
        like the single-object create endpoints above, and the same
        `f'Bed {i}'` materialization convention used everywhere else in the
        codebase (manage.py materialize_beds, allocation.solver
        ._ensure_beds_for_room) - so the result is indistinguishable from
        manually created inventory.

        Expected body:
        {
          "apartment_groups": [
            {
              "category": "female", "apartment_type": "single",
              "apartment_capacity": 3,
              "numbers": ["101", "102", ...],
              "room_groups": [{"capacity": 1, "count": 3}]
            },
            ...
          ]
        }
        Apartment numbers are generated/edited client-side (Apartment.number
        is free-text with no format constraint - see model) and submitted
        explicitly, never guessed server-side.
        """
        if not request.user.is_boss:
            return _inventory_create_permission_error()

        building = self.get_object()

        if not request.user.is_central_admin:
            region_id = building.dorm_type.region_id if building.dorm_type else None
            if region_id != request.user.region_id:
                return error_response(status.HTTP_403_FORBIDDEN, 'ניתן ליצור מלאי רק בבניין באזור המשויך למשתמש')

        groups = request.data.get('apartment_groups')

        try:
            validate_bulk_inventory_groups(building, groups)
        except BulkInventoryError as invalid:
            return Response(invalid.payload, status=status.HTTP_400_BAD_REQUEST)

        try:
            created_apartments, created_rooms, created_beds = bulk_create_inventory(building, groups)
        except DRFValidationError as exc:
            return error_response(status.HTTP_400_BAD_REQUEST, 'Bulk inventory creation failed; no changes were made.', detail=exc.detail)
        except Exception as exc:
            traceback.print_exc()
            return error_response(status.HTTP_500_INTERNAL_SERVER_ERROR, str(exc), error_type=exc.__class__.__name__)

        return Response({
            'success': True,
            'building_id': building.id,
            'created_apartments': created_apartments,
            'created_rooms': created_rooms,
            'created_beds': created_beds,
        }, status=status.HTTP_201_CREATED)

class ApartmentViewSet(viewsets.ModelViewSet):
    serializer_class = ApartmentSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ['get', 'post', 'patch', 'head', 'options']

    def get_queryset(self):
        queryset = _annotate_apartment_inventory_counts(
            Apartment.objects.select_related(
                'building',
                'building__dorm_type',
                'building__dorm_type__region'
            ).all()
        )

        is_active = _parse_is_active_filter(self.request, default='all')
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active)

        building_id = self.request.query_params.get('building')
        if building_id:
            queryset = queryset.filter(building_id=building_id)

        user = self.request.user
        region_value = self.request.query_params.get('region')
        # G3-04: centralized region scoping (see
        # _region_scoped_inventory_queryset) - a mismatched ?region= for a
        # region_boss/employee yields no results, never the foreign
        # region's apartments (and, since get_object() is built from this
        # same queryset, never a foreign apartment to write to either).
        queryset = _region_scoped_inventory_queryset(user, queryset, region_value, 'building__dorm_type__region')

        return queryset.order_by(
            'building__number',
            'number'
        )

    def create(self, request, *args, **kwargs):
        if not request.user.is_boss:
            return _inventory_create_permission_error()

        if not request.user.is_central_admin:
            building = Building.objects.filter(
                pk=request.data.get('building')
            ).select_related('dorm_type__region').first()
            if not building or not building.dorm_type or building.dorm_type.region_id != request.user.region_id:
                return error_response(status.HTTP_403_FORBIDDEN, 'ניתן ליצור דירה רק בבניין באזור המשויך למשתמש')

        conflict = check_apartment_write_conflict(None, request.data)
        if conflict:
            return Response(conflict, status=status.HTTP_400_BAD_REQUEST)

        return super().create(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        if not request.user.is_boss:
            return error_response(status.HTTP_403_FORBIDDEN, 'רק מנהל אזור או מנהל מרכזי יכול לערוך דירה')

        instance = self.get_object()

        # G3-04/G3-12: explicitly re-validate the OBJECT'S REAL region
        # (never rely solely on get_queryset()), and if this PATCH
        # reparents the apartment to a different building, validate that
        # NEW building's region too - a regional manager must never move an
        # apartment into a building belonging to another region.
        if not request.user.is_central_admin:
            real_region_id = (
                instance.building.dorm_type.region_id
                if instance.building and instance.building.dorm_type else None
            )
            if real_region_id != request.user.region_id:
                return error_response(status.HTTP_403_FORBIDDEN, 'אין הרשאה לערוך דירה באזור זה')

            new_building_id = request.data.get('building')
            if new_building_id is not None and str(new_building_id) != str(instance.building_id):
                new_building = Building.objects.filter(pk=new_building_id).select_related('dorm_type').first()
                new_building_region_id = (
                    new_building.dorm_type.region_id
                    if new_building and new_building.dorm_type else None
                )
                if new_building_region_id != request.user.region_id:
                    return error_response(status.HTTP_403_FORBIDDEN, 'לא ניתן להעביר דירה לבניין מחוץ לאזור המשויך למשתמש')

        with transaction.atomic():
            # Hold the apartment locked for the occupancy re-check AND the
            # save (see lock_apartment), closing the race where a "שינוי
            # הגדרה" recommendation was generated while the apartment was
            # empty but another employee assigned a student into it a
            # moment before this request was confirmed.
            locked_instance = lock_apartment(instance.pk)
            conflict = check_apartment_write_conflict(locked_instance, request.data)
            if conflict:
                return Response(conflict, status=status.HTTP_400_BAD_REQUEST)

            previous_state = apartment_config_state(locked_instance)
            response = super().update(request, *args, **kwargs)
            if response.status_code == 200:
                record_apartment_config_change(request.user, locked_instance, previous_state)
        return response

class RoomViewSet(viewsets.ModelViewSet):
    serializer_class = RoomSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ['get', 'post', 'patch', 'head', 'options']

    def get_queryset(self):
        queryset = _annotate_room_inventory_counts(
            Room.objects.select_related(
                'apartment',
                'apartment__building',
                'apartment__building__dorm_type',
                'apartment__building__dorm_type__region'
            ).all()
        )

        is_active = _parse_is_active_filter(self.request, default='all')
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active)

        apartment_id = self.request.query_params.get('apartment')
        if apartment_id:
            queryset = queryset.filter(apartment_id=apartment_id)

        building_id = self.request.query_params.get('building')
        if building_id:
            queryset = queryset.filter(apartment__building_id=building_id)

        user = self.request.user
        region_value = self.request.query_params.get('region')
        # G3-04: centralized region scoping (see
        # _region_scoped_inventory_queryset) - see BuildingViewSet/
        # ApartmentViewSet above for the full rationale.
        queryset = _region_scoped_inventory_queryset(
            user, queryset, region_value, 'apartment__building__dorm_type__region'
        )

        return queryset.order_by(
            'apartment__building__number',
            'apartment__number',
            'name'
        )

    def create(self, request, *args, **kwargs):
        if not request.user.is_boss:
            return _inventory_create_permission_error()

        if not request.user.is_central_admin:
            apartment = Apartment.objects.filter(
                pk=request.data.get('apartment')
            ).select_related('building__dorm_type__region').first()
            region_id = (
                apartment.building.dorm_type.region_id
                if apartment and apartment.building and apartment.building.dorm_type
                else None
            )
            if not apartment or region_id != request.user.region_id:
                return error_response(status.HTTP_403_FORBIDDEN, 'ניתן ליצור חדר רק בדירה באזור המשויך למשתמש')

        conflict = check_room_write_conflict(None, request.data)
        if conflict:
            return Response(conflict, status=status.HTTP_400_BAD_REQUEST)

        return super().create(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        if not request.user.is_boss:
            return error_response(status.HTTP_403_FORBIDDEN, 'רק מנהל אזור או מנהל מרכזי יכול לערוך חדר')

        instance = self.get_object()

        # G3-04/G3-12: explicitly re-validate the OBJECT'S REAL region, and
        # if this PATCH reparents the room to a different apartment,
        # validate that NEW apartment's region too.
        if not request.user.is_central_admin:
            real_region = _room_region(instance)
            real_region_id = real_region.id if real_region else None
            if real_region_id != request.user.region_id:
                return error_response(status.HTTP_403_FORBIDDEN, 'אין הרשאה לערוך חדר באזור זה')

            new_apartment_id = request.data.get('apartment')
            if new_apartment_id is not None and str(new_apartment_id) != str(instance.apartment_id):
                new_apartment = Apartment.objects.filter(pk=new_apartment_id).select_related(
                    'building__dorm_type'
                ).first()
                new_region_id = (
                    new_apartment.building.dorm_type.region_id
                    if new_apartment and new_apartment.building and new_apartment.building.dorm_type
                    else None
                )
                if new_region_id != request.user.region_id:
                    return error_response(status.HTTP_403_FORBIDDEN, 'לא ניתן להעביר חדר לדירה מחוץ לאזור המשויך למשתמש')

        conflict = check_room_write_conflict(instance, request.data)
        if conflict:
            return Response(conflict, status=status.HTTP_400_BAD_REQUEST)

        return super().update(request, *args, **kwargs)

class BedViewSet(viewsets.ModelViewSet):
    """
    Read-only browsing plus label-only editing. Individual bed
    creation/deletion and activation/deactivation are intentionally not
    supported: Bed rows are derived from Room.capacity and materialized
    exclusively by the admin-only `manage.py materialize_beds` command
    (see ensure_room_beds), so exposing free-form bed CRUD here would risk
    silently desynchronizing bed rows from room capacity.
    """
    serializer_class = BedSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ['get', 'patch', 'head', 'options']

    def get_queryset(self):
        queryset = _annotate_bed_occupancy(
            Bed.objects.select_related(
                'room',
                'room__apartment',
                'room__apartment__building',
                'room__apartment__building__dorm_type',
                'room__apartment__building__dorm_type__region',
            ).all()
        )

        room_id = self.request.query_params.get('room')
        if room_id:
            queryset = queryset.filter(room_id=room_id)

        apartment_id = self.request.query_params.get('apartment')
        if apartment_id:
            queryset = queryset.filter(room__apartment_id=apartment_id)

        user = self.request.user
        if not user.is_central_admin:
            if not user.region_id:
                return queryset.none()
            queryset = queryset.filter(
                room__apartment__building__dorm_type__region=user.region
            )

        return queryset.order_by(
            'room__apartment__building__number',
            'room__apartment__number',
            'room__name',
            'label',
        )

    def update(self, request, *args, **kwargs):
        if not request.user.is_boss:
            return error_response(status.HTTP_403_FORBIDDEN, 'רק מנהל אזור או מנהל מרכזי יכול לערוך תווית מיטה')
        allowed_fields = {'label'}
        extra_fields = set(request.data.keys()) - allowed_fields
        if extra_fields:
            return Response(
                {
                    'field': next(iter(extra_fields)),
                    'code': 'FIELD_NOT_EDITABLE',
                    'message': 'ניתן לערוך רק את תווית המיטה — שדות אחרים אינם נתמכים לעריכה ברמת המיטה.',
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        return super().update(request, *args, **kwargs)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def inventory_by_housing_type(request):
    """
    Returns detailed inventory breakdown per housing type (DormType),
    including building-level details.
    """
    user = request.user
    region_value = request.query_params.get('region')

    if region_value:
        region = _resolve_region(region_value)
        if not region:
            return error_response(status.HTTP_404_NOT_FOUND, 'אזור לא נמצא')
    elif user.is_central_admin:
        region = None
    elif user.region:
        region = user.region
    else:
        return error_response(status.HTTP_400_BAD_REQUEST, 'המשתמש אינו משויך לאזור')

    return Response({
        'region': RegionSerializer(region).data if region else None,
        'inventory': build_inventory_by_housing_type(region),
    }, status=status.HTTP_200_OK)
