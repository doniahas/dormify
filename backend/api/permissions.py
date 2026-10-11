"""
Region and role authorization policy shared by the api views.

Holds the IsCentralAdmin / IsBoss permission classes and the ?region=
scoping helpers that region-scoped endpoints use. The api.views
compatibility facade (api/views/__init__.py) imports every name defined
here, so references through the api.views namespace keep resolving to
these same objects.
"""

from rest_framework import permissions, status
from rest_framework.response import Response

from .models import Region


class IsCentralAdmin(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.is_central_admin


class IsBoss(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.is_boss


def filter_by_region(queryset, user, region_field='region'):
    if user.is_central_admin:
        return queryset
    if not user.region:
        return queryset.none()
    return queryset.filter(**{region_field: user.region})


def _resolve_region(region_value):
    if region_value in (None, '', 'null', 'undefined'):
        return None

    try:
        return Region.objects.get(pk=region_value)
    except (Region.DoesNotExist, ValueError, TypeError):
        pass

    try:
        return Region.objects.get(name=region_value)
    except Region.DoesNotExist:
        pass

    try:
        return Region.objects.get(name__iexact=str(region_value).strip())
    except Region.DoesNotExist:
        pass

    return None


def resolve_scoped_region(user, region_value, *, allow_central_all=True):
    """
    Centralized, single-source-of-truth ?region= resolution for every
    region-scoped read endpoint (G3-03/G3-04/G3-08: statistics,
    allocation_summary, allocation_results, assisted_allocation_queue,
    get_active_allocation_run, and the Building/Apartment/Room viewsets'
    get_queryset()). Returns (region, error_response):

    - central_admin: may explicitly select any region via region_value
      (global-administration workflows are intentionally allowed to do
      this); omitting it returns (None, None) meaning "no region filter"
      when allow_central_all=True, or a clean 400 ("a region is required")
      when the caller's endpoint always needs exactly one region.

    - region_boss / employee: NEVER get a foreign region, regardless of
      what ?region= names. If region_value is empty, they're scoped to
      their own user.region. If region_value is supplied and does not
      match their own region, this returns a clean 403 - it deliberately
      does NOT silently substitute their own region for a mismatched
      request, so a caller can never mistake the response for data about
      the region they actually asked for.

    A user with no region assigned (and who isn't central_admin) always
    gets a clean 400, matching the existing behavior at every call site
    this replaces.
    """
    if user.is_central_admin:
        if region_value:
            region = _resolve_region(region_value)
            if not region:
                return None, Response({'error': 'אזור לא נמצא'}, status=status.HTTP_404_NOT_FOUND)
            return region, None
        if allow_central_all:
            return None, None
        return None, Response({'error': 'נדרש לבחור אזור'}, status=status.HTTP_400_BAD_REQUEST)

    if not user.region_id:
        return None, Response({'error': 'המשתמש אינו משויך לאזור'}, status=status.HTTP_400_BAD_REQUEST)

    if region_value:
        requested = _resolve_region(region_value)
        if not requested or requested.id != user.region_id:
            return None, Response({'error': 'אין הרשאה לאזור זה'}, status=status.HTTP_403_FORBIDDEN)

    return user.region, None


def _region_scoped_inventory_queryset(user, queryset, region_value, region_field):
    """
    Shared read-path region filtering for Building/Apartment/Room
    get_queryset() (G3-04). Mirrors resolve_scoped_region()'s authorization
    semantics but returns a queryset rather than a Response, since
    ModelViewSet.get_queryset() cannot itself return an HTTP response:

    - central_admin: may filter by any region via region_value, or see
      everything with none supplied.
    - region_boss / employee: a ?region= that is not their own always
      yields queryset.none() - never the requested foreign region's data,
      and never their own region silently substituted for a request that
      named someone else's. Since get_object() (used by
      retrieve/update/destroy) is built from this same queryset, a
      mismatched ?region= can never be used to pull a foreign-region
      object into scope for a write either - closing the exact bug where
      supplying the *target's own real region* string used to make
      get_object() succeed regardless of the caller's own region.

    `region_field` is the relation path to Region from this model (e.g.
    'dorm_type__region' for Building) - `f'{region_field}_id'` is valid
    Django ORM syntax for the id shortcut on the terminal FK hop.
    """
    if user.is_central_admin:
        if region_value:
            region = _resolve_region(region_value)
            if not region:
                return queryset.none()
            return queryset.filter(**{region_field: region})
        return queryset

    if not user.region_id:
        return queryset.none()

    if region_value:
        requested = _resolve_region(region_value)
        if not requested or requested.id != user.region_id:
            return queryset.none()

    return queryset.filter(**{f'{region_field}_id': user.region_id})


def _inventory_create_permission_error():
    return Response(
        {'error': 'רק מנהל אזור או מנהל מרכזי יכולים ליצור או לערוך פריטי מלאי'},
        status=status.HTTP_403_FORBIDDEN,
    )
