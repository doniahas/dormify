"""Student view ownership."""

from django.db.models import Count, Prefetch
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied as DRFPermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from ..domains.students.queries import (
    StudentFilters,
    build_student_filter_options,
    filter_students,
    unassigned_student_ids_from_latest_completed_run,
)
from ..models import BedAssignment, Student
from ..pagination import StandardResultsPagination
from ..permissions import _resolve_region
from ..serializers import StudentListSerializer, StudentSerializer


def _latest_run_unassigned_student_ids(user, region_value=None):
    """
    Return only students from the latest completed allocation run
    who were sent to the solver and are still unassigned, for the region
    the caller may see: a central admin's explicitly selected region, or
    a regional user's own region.
    """
    if user.is_central_admin:
        if not region_value:
            return []
        region = _resolve_region(region_value)
        if not region:
            return []
        region_id = region.id
    else:
        if not user.region_id:
            return []
        region_id = user.region_id

    return unassigned_student_ids_from_latest_completed_run(region_id)


class StudentViewSet(viewsets.ModelViewSet):
    serializer_class = StudentSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsPagination
    # G3-15: Student records must never be hard-deletable through generic
    # CRUD - there is no legitimate "delete a student record" workflow in
    # this codebase (the existing REMOVE_STUDENT StudentRequest workflow
    # ends the active BedAssignment and clears assigned_room, it never
    # deletes the Student row - see StudentRequestViewSet.approve()). No
    # 'delete' is intentionally listed here rather than inventing a new
    # broad delete privilege.
    http_method_names = ['get', 'post', 'patch', 'head', 'options']

    def get_serializer_class(self):

        if self.action == 'list':
            return StudentListSerializer
        return StudentSerializer

    def _csv_params(self, name):
        """
        Multi-value filter params: accepts repeated params AND comma-joined
        values (?gender=male,female or ?gender=male&gender=female). 'all'
        and empties are dropped.
        """
        values = []
        for chunk in self.request.query_params.getlist(name):
            values.extend(
                v.strip() for v in str(chunk).split(',')
                if v.strip() and v.strip() != 'all'
            )
        return values

    def _int_params(self, name):
        """Integer multi-value params; invalid values filter nothing extra."""
        out = []
        for v in self._csv_params(name):
            try:
                out.append(int(v))
            except (TypeError, ValueError):
                pass
        return out

    def _parse_filters(self):
        """The Students page filters, parsed from the query string."""
        params = self.request.query_params
        status_filter = params.get('status') or ''

        return StudentFilters(
            search=params.get('search') or '',
            # Values are validated against model choices - invalid input
            # filters nothing extra rather than erroring.
            genders=[v for v in self._csv_params('gender') if v in Student.Gender.values],
            religions=[v for v in self._csv_params('requested_religion') if v in Student.Religion.values],
            religious=params.get('religious') or '',
            placement_sector=params.get('placement_sector') or '',
            region_ids=self._csv_params('region'),
            dorm_type_ids=self._int_params('dorm_type'),
            building_ids=self._int_params('building'),
            apartment_ids=self._int_params('apartment'),
            room_ids=self._int_params('room'),
            status=status_filter,
            unassigned_student_ids=(
                _latest_run_unassigned_student_ids(self.request.user, params.get('region'))
                if status_filter == 'unassigned' else []
            ),
            has_roommate_request=params.get('has_roommate_request') or '',
            category=params.get('category') or '',
        )

    def get_queryset(self):
        queryset = Student.objects.select_related(
            'accepted_dorm_type',
            'accepted_dorm_type__region',
            'assigned_room',
            'assigned_room__apartment',
            'assigned_room__apartment__building',
        )
        if self.action == 'list':
            # The list serializer's current_bed field must never issue a
            # per-student BedAssignment query (obj.current_bed's default
            # property does exactly that) - prefetch each student's one
            # active assignment (+ its bed) in a single extra query instead.
            # Scoped to action='list' only: the detail serializer reads the
            # same current_bed property, which is fine as a single query on
            # one object when opening a single student.
            queryset = queryset.prefetch_related(
                Prefetch(
                    'bed_assignments',
                    queryset=BedAssignment.objects.filter(
                        status=BedAssignment.Status.ACTIVE
                    ).select_related('bed'),
                    to_attr='prefetched_active_assignments',
                )
            )
        else:
            # StudentSerializer.batch_id (source='batch.id') is only read
            # outside the list action (StudentListSerializer has no batch
            # field) - added here only, so the list query's JOIN shape is
            # completely unchanged. Previously a lazy per-response query
            # on every detail/create/update; the performance suite pins the
            # detail query count.
            queryset = queryset.select_related('batch')

        user = self.request.user
        region_value = self.request.query_params.get('region')

        if user.is_central_admin or user.is_boss:
            if region_value:
                region = _resolve_region(region_value)
                if not region:
                    return queryset.none()
                queryset = queryset.filter(accepted_dorm_type__region=region)
            elif not user.is_central_admin:
                if not user.region_id:
                    return queryset.none()
                queryset = queryset.filter(
                    accepted_dorm_type__region_id=user.region_id
                )
        else:
            if not user.region_id:
                return queryset.none()
            queryset = queryset.filter(
                accepted_dorm_type__region_id=user.region_id
            )

        # Regional users are already hard-scoped above; the filters only
        # ever narrow within that scope.
        return filter_students(queryset, self._parse_filters())

    def _check_student_region_authorization(self, user, dorm_type):
        """
        §1: central admins may add/edit a student in any region (via their
        choice of accepted_dorm_type, which carries the region); regional
        staff may only add/edit students within their own region - a
        manipulated request naming a dorm type from another region is
        rejected outright here, not merely hidden in the UI.
        """
        if not user.is_central_admin:
            if not user.region_id:
                raise DRFPermissionDenied('אין לך אזור מוגדר - לא ניתן להוסיף/לערוך סטודנטים')
            if dorm_type and dorm_type.region_id and dorm_type.region_id != user.region_id:
                raise DRFPermissionDenied('אינך מורשה לשייך סטודנט לאזור זה')

    def perform_create(self, serializer):
        user = self.request.user
        dorm_type = serializer.validated_data.get('accepted_dorm_type')
        self._check_student_region_authorization(user, dorm_type)
        # housing_type is never guessed from gender - the serializer already
        # requires an explicit, employee-chosen value for any student
        # eligible for assignment (every category except LEAVING).
        serializer.save()

    def perform_update(self, serializer):
        user = self.request.user
        dorm_type = serializer.validated_data.get(
            'accepted_dorm_type', serializer.instance.accepted_dorm_type
        )
        self._check_student_region_authorization(user, dorm_type)
        serializer.save()

    @action(detail=False, methods=['get'])
    def counts(self, request):
        queryset = self.get_queryset()

        by_category = dict(
            queryset.values_list('category').annotate(n=Count('id'))
        )

        unassigned_ids = _latest_run_unassigned_student_ids(
            request.user,
            request.query_params.get('region'),
        )

        return Response({
            'all': queryset.count(),
            'continuing': by_category.get(
                Student.StudentCategory.CONTINUING, 0
            ),
            'new': by_category.get(
                Student.StudentCategory.NEW, 0
            ),
            'transfer': by_category.get(
                Student.StudentCategory.TRANSFER, 0
            ),
            'leaving': by_category.get(
                Student.StudentCategory.LEAVING, 0
            ),
            'unassigned': len(unassigned_ids),
        })

    @action(detail=False, methods=['get'], url_path='filter-options')
    def filter_options(self, request):
        user = request.user
        region_id = None if user.is_central_admin else user.region_id

        return Response({
            'is_central_admin': user.is_central_admin,
            **build_student_filter_options(region_id),
        })
