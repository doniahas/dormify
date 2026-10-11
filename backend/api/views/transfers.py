from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Q
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied as DRFPermissionDenied
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from ..contracts.requests import parse_match_pagination, parse_region_ids
from ..domains.matching.feasibility import (
    empty_match_payload,
    match_infeasibility_reason,
    student_assignment_blocker,
)
from ..domains.matching.ranking import find_matching_room_options
from ..domains.placement.beds import get_free_bed
from ..domains.placement.rules import validate_apartment_assignment
from ..domains.placement.services import _user_can_edit_room
from ..domains.transfers.queries import student_request_base_queryset
from ..domains.transfers.services import (
    _student_current_region_id,
    _user_can_cancel_request,
    _user_can_review_request,
    approve_legacy_transfer,
    approve_student_request,
    cancel_student_request,
    create_legacy_transfer,
    finalize_student_request_creation,
    infer_movement_type,
    reject_legacy_transfer,
    reject_student_request,
    user_can_approve_transfer,
)
from ..models import (
    Region,
    Room,
    Student,
    StudentRequest,
    Transfer,
)
from ..pagination import StandardResultsPagination
from ..serializers import (
    RegionSerializer,
    StudentRequestSerializer,
    TransferSerializer,
)
from ..contracts.errors import error_response


class TransferViewSet(viewsets.ModelViewSet):
    serializer_class = TransferSerializer
    permission_classes = [IsAuthenticated]
    # G3-24: Transfer rows are workflow/audit history - 'delete' is
    # intentionally absent so no authenticated user can erase a transfer
    # record through generic CRUD. 'put'/'patch' stay listed (the
    # approve()/reject() actions below need PUT on their own sub-URLs), but
    # update()/partial_update() to the base '/transfers/<pk>/' resource are
    # overridden below to refuse writes (G3-02).
    http_method_names = ['get', 'post', 'put', 'patch', 'head', 'options']

    def get_queryset(self):
        queryset = Transfer.objects.select_related(
            'student',
            'from_room', 'from_room__apartment', 'from_room__apartment__building',
            'to_room', 'to_room__apartment', 'to_room__apartment__building',
            'requested_by', 'requested_by__region', 'reviewed_by',
        )

        if not self.request.user.is_central_admin:
            queryset = queryset.filter(
                Q(from_room__apartment__building__dorm_type__region=self.request.user.region) |
                Q(to_room__apartment__building__dorm_type__region=self.request.user.region)
            )

        status_filter = self.request.query_params.get('status')
        if status_filter and status_filter != 'all':
            queryset = queryset.filter(status=status_filter)

        return queryset.order_by('-created_at')

    def update(self, request, *args, **kwargs):
        # G3-02: the legacy generic update endpoint must never be usable to
        # set status/reviewed_by/reviewed_at/rejection_reason directly,
        # bypassing user_can_approve_transfer(), the room-availability
        # check, or the BedAssignment creation that approve()/reject()
        # perform. All transitions must go through those dedicated actions.
        # (TransferSerializer also marks those fields read_only as a second
        # layer of defense - this blocks the endpoint outright.)
        return error_response(status.HTTP_405_METHOD_NOT_ALLOWED, 'לא ניתן לערוך בקשת העברה ישירות - יש להשתמש בפעולות אישור/דחייה.')

    def perform_create(self, serializer):
        student = serializer.validated_data['student']
        from_room = serializer.validated_data.get('from_room') or student.assigned_room
        to_room = serializer.validated_data['to_room']

        if not from_room:
            raise DRFValidationError('הסטודנט אינו משויך כרגע לחדר מקור')

        # G3-07: a non-central-admin may only create a (same-region) legacy
        # Transfer wholly inside their own region - never for a student/room
        # belonging to another region. Cross-region movement has its own,
        # explicitly-authorized path (StudentRequestViewSet's
        # region_transfer workflow); this endpoint was never meant to cross
        # regions and must not silently allow it.
        user = self.request.user
        if not user.is_central_admin:
            if not user.region_id:
                raise DRFPermissionDenied('אין לך אזור מוגדר - לא ניתן ליצור בקשת העברה')
            from_region = getattr(getattr(getattr(from_room, 'apartment', None), 'building', None), 'dorm_type', None)
            from_region_id = from_region.region_id if from_region else None
            to_region = getattr(getattr(getattr(to_room, 'apartment', None), 'building', None), 'dorm_type', None)
            to_region_id = to_region.region_id if to_region else None
            if from_region_id != user.region_id or to_region_id != user.region_id:
                raise DRFPermissionDenied('אינך מורשה ליצור בקשת העברה עבור אזור זה')

        validate_apartment_assignment(student, to_room)
        movement_type = infer_movement_type(from_room, to_room)

        with transaction.atomic():
            try:
                target_bed = get_free_bed(to_room)
            except ValueError as exc:
                # Data-integrity case (capacity free but no real Bed rows) -
                # surfaced as a validation error, never silently "fixed".
                raise DRFValidationError(str(exc))
            if not target_bed:
                raise DRFValidationError('אין מיטה פנויה בחדר היעד')

            # NOTE (G2 implementation, Transfer.movement_type bug):
            # Transfer has no movement_type field of its own - it is
            # only ever stored on the related MovementRequest created
            # just below (transfer.movement_request.movement_type).
            # Passing movement_type=... into serializer.save() here used
            # to raise TypeError: Transfer() got unexpected keyword
            # arguments: 'movement_type', crashing every single Transfer
            # creation unconditionally (confirmed via direct
            # reproduction: Transfer(movement_type='room') raises
            # TypeError). The concurrency suite covers Transfer creation
            # end to end so this cannot silently regress.
            transfer = serializer.save(
                requested_by=self.request.user,
                from_room=from_room,
            )

            create_legacy_transfer(transfer, student, target_bed, movement_type, self.request.user)

    @action(detail=True, methods=['put'])
    def approve(self, request, pk=None):
        if not request.user.is_boss:
            return error_response(status.HTTP_403_FORBIDDEN, 'רק מנהל יכול לאשר בקשות')

        transfer = self.get_object()

        if transfer.status != Transfer.Status.PENDING:
            return error_response(status.HTTP_400_BAD_REQUEST, 'הבקשה כבר טופלה')

        if not user_can_approve_transfer(request.user, transfer):
            return error_response(status.HTTP_403_FORBIDDEN, 'אין הרשאה לאשר בקשה זו')

        if transfer.to_room.is_full:
            return error_response(status.HTTP_400_BAD_REQUEST, 'החדר היעד מלא')

        try:
            if not approve_legacy_transfer(transfer, request.user):
                return error_response(status.HTTP_400_BAD_REQUEST, 'הבקשה כבר טופלה')

            return Response({
                'message': 'הבקשה אושרה בהצלחה',
                'transfer': TransferSerializer(transfer).data
            })

        except (ValueError, ValidationError) as e:
            return error_response(status.HTTP_400_BAD_REQUEST, str(e))
        except IntegrityError:
            # Defensive backstop (G2-02-equivalent): a legitimate
            # concurrent-write conflict surfaces as a clean 4xx, never an
            # unhandled 500.
            return error_response(status.HTTP_400_BAD_REQUEST, 'הבקשה כבר טופלה או שהתרחשה התנגשות נתונים - נא לרענן ולנסות שוב.')

    @action(detail=True, methods=['put'])
    def reject(self, request, pk=None):
        if not request.user.is_boss:
            return error_response(status.HTTP_403_FORBIDDEN, 'רק מנהל יכול לדחות בקשות')

        transfer = self.get_object()

        if transfer.status != Transfer.Status.PENDING:
            return error_response(status.HTTP_400_BAD_REQUEST, 'הבקשה כבר טופלה')

        # G3-22: reject() must use the exact same authorization rule as
        # approve() - previously this checked only to_room's region while
        # approve() required both from_room and to_room to match the boss's
        # region, two inconsistent ad-hoc policies for the same decision.
        if not user_can_approve_transfer(request.user, transfer):
            return error_response(status.HTTP_403_FORBIDDEN, 'אין הרשאה לדחות בקשה זו')

        if not reject_legacy_transfer(transfer, request.user, lambda: request.data.get('reason', '')):
            return error_response(status.HTTP_400_BAD_REQUEST, 'הבקשה כבר טופלה')

        return Response({
            'message': 'הבקשה נדחתה',
            'transfer': TransferSerializer(transfer).data
        })


class StudentRequestViewSet(viewsets.ModelViewSet):
    serializer_class = StudentRequestSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsPagination
    # G3-24: StudentRequest rows are workflow/audit history - the
    # legitimate way for a requester to withdraw their own still-pending
    # request is the cancel() action below (role/ownership/status
    # checked there), never a generic DELETE that erases the record.
    http_method_names = ['get', 'post', 'put', 'patch', 'head', 'options']

    def get_queryset(self):
        queryset = student_request_base_queryset()

        user = self.request.user
        if not user.is_central_admin:
            # A regional user's own region always wins - a region_id sent by
            # the client is never trusted/consulted here.
            if not user.region_id:
                queryset = queryset.filter(requested_by=user)
            else:
                queryset = queryset.filter(
                    Q(requested_by__region_id=user.region_id) |
                    Q(student__accepted_dorm_type__region_id=user.region_id) |
                    Q(target_room__apartment__building__dorm_type__region_id=user.region_id) |
                    # A region_transfer's DESTINATION region must be able to
                    # see (list/retrieve) the incoming request - it owns
                    # approve/reject (see _user_can_review_request()). The
                    # source-side Q()s above already keep it visible to the
                    # requester's/student's own region too - both sides see
                    # it, only the destination side (or central admin) can
                    # act on it.
                    Q(target_region_id=user.region_id)
                )
        else:
            # Central admins may explicitly narrow to one region (Requests
            # page region selector); "all regions" is the default (no filter).
            region_filter = self.request.query_params.get('region')
            if region_filter and region_filter != 'all':
                queryset = queryset.filter(
                    Q(requested_by__region_id=region_filter) |
                    Q(student__accepted_dorm_type__region_id=region_filter) |
                    Q(target_room__apartment__building__dorm_type__region_id=region_filter)
                )

        status_filter = self.request.query_params.get('status')
        if status_filter and status_filter != 'all':
            queryset = queryset.filter(status=status_filter)

        request_type_filter = self.request.query_params.get('request_type')
        if request_type_filter and request_type_filter != 'all':
            queryset = queryset.filter(request_type=request_type_filter)

        student_filter = self.request.query_params.get('student')
        if student_filter:
            queryset = queryset.filter(student_id=student_filter)

        date_from = self.request.query_params.get('date_from')
        if date_from:
            queryset = queryset.filter(created_at__date__gte=date_from)
        date_to = self.request.query_params.get('date_to')
        if date_to:
            queryset = queryset.filter(created_at__date__lte=date_to)

        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(
                Q(request_number__icontains=search) |
                Q(student__first_name__icontains=search) |
                Q(student__last_name__icontains=search) |
                Q(student__student_id__icontains=search) |
                Q(student_data__student_id__icontains=search)
            )

        return queryset.distinct().order_by('-created_at')

    def perform_create(self, serializer):
        instance = serializer.save(requested_by=self.request.user)
        finalize_student_request_creation(instance)

    def destroy(self, request, *args, **kwargs):
        if not request.user.is_boss:
            return error_response(status.HTTP_403_FORBIDDEN, 'רק מנהל יכול למחוק בקשות')

        req = self.get_object()

        if req.status not in (
                StudentRequest.Status.PENDING,
                StudentRequest.Status.REJECTED,
                StudentRequest.Status.CANCELLED,
        ):
            return error_response(status.HTTP_400_BAD_REQUEST, 'ניתן למחוק רק בקשה ממתינה, שנדחתה או שבוטלה')

        req.delete()

        return Response(
            {'message': 'הבקשה נמחקה בהצלחה'},
            status=status.HTTP_200_OK,
        )

    @action(detail=False, methods=['get'], url_path='transfer-target-regions')
    def transfer_target_regions(self, request):
        """
        Regions a region_transfer request may legally name as target_region.

        Deliberately NOT RegionViewSet: that endpoint scopes a non-central
        user to only their own region (RegionViewSet.get_queryset()), which
        is correct for general operational access but wrong here -
        StudentRequestSerializer.validate() places no role/region
        restriction on who may create a region_transfer request or which
        region they may name (only StudentRequestViewSet.approve() is
        central-admin-gated for it). A regional employee legitimately
        needs to see every OTHER region's name/id to request a transfer
        there, without that grant giving them any access to that region's
        buildings/rooms/students - this action returns only id+name (via
        the same minimal RegionSerializer RegionViewSet already uses), the
        same shape the frontend's normal regions list has always used.

        Excluding the student's own current region is left to the caller
        (the Assisted Allocation transfer dialog already does this using
        the student's own region_id from the student-detail endpoint) -
        this action has no student in scope to exclude one correctly, and
        returning the full list keeps this endpoint reusable by any future
        target_region UI without baking in one caller's exclusion rule.
        """
        return Response(RegionSerializer(Region.objects.all().order_by('name'), many=True).data)

    @action(detail=False, methods=['post'], url_path='match-options')
    def match_options(self, request):
        student = None
        student_value = request.data.get('student_id') or request.data.get('student')

        if student_value:
            try:
                student = Student.objects.select_related(
                    'assigned_room__apartment__building__dorm_type__region',
                    'accepted_dorm_type__region',
                ).get(pk=student_value)
            except (Student.DoesNotExist, ValueError, TypeError):
                return Response(
                    {'feasible': False, 'buildings': [], 'reason': 'הסטודנט לא נמצא'},
                    status=status.HTTP_404_NOT_FOUND
                )

            if not request.user.is_central_admin:
                # A student with no accepted_dorm_type at all has no region
                # to check against - that's a missing-data problem (surfaced
                # below by student_assignment_blocker), not an
                # authorization problem, so it must not be misreported as
                # "no permission for this region".
                if student.accepted_dorm_type_id:
                    region_id = student.accepted_dorm_type.region_id
                    if not request.user.region_id or region_id != request.user.region_id:
                        return Response(
                            {'feasible': False, 'buildings': [], 'reason': 'אין הרשאה לאזור זה'},
                            status=status.HTTP_403_FORBIDDEN
                        )

        limit, offset = parse_match_pagination(request.data)

        if student:
            blocker = student_assignment_blocker(student)
            if blocker:
                blocking_field, message = blocker
                return Response({
                    'feasible': False,
                    'reason': message,
                    'blocking_field': blocking_field,
                    **empty_match_payload(limit, offset),
                })

        student_data = request.data.get('student_data') or {}
        same_apartment = request.data.get('same_apartment', None)

        transfer_scope = request.data.get('transfer_scope') or None
        raw_region_ids = parse_region_ids(request.data.get('region_ids'))

        # Backend-enforced role rules (frontend role checks are never
        # trusted): a regional user may not browse or perform a cross-region
        # transfer, nor smuggle a foreign region id into the search.
        if not request.user.is_central_admin:
            foreign_multi = [r for r in raw_region_ids if str(r) != str(request.user.region_id)]
            single = request.data.get('region_id')
            foreign_single = single and str(single) != str(request.user.region_id)
            if transfer_scope == StudentRequest.TransferScope.CROSS_REGION or foreign_multi or foreign_single:
                return Response(
                    {'detail': 'אין לך הרשאה לבצע מעבר לאזור אחר.'},
                    status=status.HTTP_403_FORBIDDEN,
                )

        # A region override is only ever honored for central admins - a
        # regional user's own region always wins inside _room_candidate_queryset,
        # regardless of what region ids a direct API call might send.
        region_id = request.data.get('region_id') if request.user.is_central_admin else None
        region_ids = None
        if transfer_scope == StudentRequest.TransferScope.CROSS_REGION:
            # Central-admin-only (regional users were rejected above). Search
            # ONLY the explicitly selected destination regions - the
            # student's current region is never included implicitly.
            if not raw_region_ids:
                return Response(
                    {'feasible': False, 'reason': 'יש לבחור לפחות אזור יעד אחד עבור מעבר לאזור אחר.',
                     **empty_match_payload(limit, offset)},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            region_ids = raw_region_ids
            region_id = None
        elif transfer_scope == StudentRequest.TransferScope.SAME_REGION:
            # The student's CURRENT region is used automatically - the
            # region selector is neither needed nor honored in this mode.
            current_region = _student_current_region_id(student)
            region_ids = [current_region] if current_region else None
            region_id = None
        elif not region_id and student and student.accepted_dorm_type_id:
            # Legacy default (assign/reassign flows without a transfer
            # scope): the student's own accepted region rather than a
            # nationwide scan. An explicit region_id always overrides.
            region_id = student.accepted_dorm_type.region_id

        result = find_matching_room_options(
            request.user, student=student, student_data=student_data,
            same_apartment=same_apartment, region_id=region_id, region_ids=region_ids,
            limit=limit, offset=offset,
        )
        searched = region_ids or ([region_id] if region_id else [])
        return Response({
            'feasible': result['total_valid_beds'] > 0,
            'reason': match_infeasibility_reason(result, 'לא נמצאו מיטות פנויות מתאימות עבור סטודנט זה.'),
            'transfer_scope': transfer_scope,
            'search_regions': [
                {'id': r.id, 'name': r.name} for r in Region.objects.filter(id__in=searched)
            ],
            **result,
        })

    @action(detail=True, methods=['get'])
    def feasibility(self, request, pk=None):
        req = self.get_object()
        limit, offset = parse_match_pagination(request.query_params)

        if req.student:
            blocker = student_assignment_blocker(req.student)
            if blocker:
                blocking_field, message = blocker
                return Response({
                    'feasible': False,
                    'reason': message,
                    'blocking_field': blocking_field,
                    **empty_match_payload(limit, offset),
                })

        # Region scope comes from what is PERSISTED on the request - never
        # from client-sent parameters: same-region searches the stored
        # source region (falling back to the student's current region);
        # cross-region searches exactly the stored destination regions.
        # Regional users remain hard-scoped to their own region inside
        # _room_candidate_queryset regardless of these values.
        region_ids = None
        if req.request_type in (StudentRequest.RequestType.ROOM, StudentRequest.RequestType.APARTMENT):
            if req.transfer_scope == StudentRequest.TransferScope.CROSS_REGION:
                region_ids = list(req.destination_regions.values_list('id', flat=True)) or None
            else:
                source = req.source_region_id or _student_current_region_id(req.student)
                region_ids = [source] if source else None
        elif req.request_type == StudentRequest.RequestType.REGION_TRANSFER and req.target_region_id:
            region_ids = [req.target_region_id]

        result = find_matching_room_options(
            request.user,
            student=req.student,
            student_data=req.student_data,
            same_apartment=req.same_apartment,
            region_ids=region_ids,
            limit=limit, offset=offset,
        )
        return Response({
            'feasible': result['total_valid_beds'] > 0,
            'reason': match_infeasibility_reason(result, 'לא נמצאו מיטות פנויות מתאימות עבור בקשה זו.'),
            'transfer_scope': req.transfer_scope,
            'search_regions': [
                {'id': r.id, 'name': r.name} for r in Region.objects.filter(id__in=region_ids or [])
            ],
            **result,
        })

    @action(detail=True, methods=['put'])
    def approve(self, request, pk=None):
        if not request.user.is_boss:
            return error_response(status.HTTP_403_FORBIDDEN, 'רק מנהל יכול לאשר בקשות')

        req = self.get_object()
        if req.status != StudentRequest.Status.PENDING:
            return error_response(status.HTTP_400_BAD_REQUEST, 'הבקשה כבר טופלה')

        if not _user_can_review_request(request.user, req):
            return error_response(status.HTTP_403_FORBIDDEN, 'אין הרשאה לאשר בקשה זו')

        target_room_id = request.data.get('target_room') or request.data.get('room_id')
        target_room = None
        if target_room_id:
            try:
                target_room = Room.objects.select_related(
                    'apartment', 'apartment__building',
                    'apartment__building__dorm_type', 'apartment__building__dorm_type__region',
                ).get(pk=target_room_id)
            except Room.DoesNotExist:
                return error_response(status.HTTP_404_NOT_FOUND, 'החדר שנבחר לא נמצא')

            if not _user_can_edit_room(request.user, target_room):
                return error_response(status.HTTP_403_FORBIDDEN, 'אין הרשאה לערוך חדר באזור זה')

        bed_id = request.data.get('bed_id')

        try:
            if not approve_student_request(req, request.user, target_room, bed_id):
                return error_response(status.HTTP_400_BAD_REQUEST, 'הבקשה כבר טופלה')

        except PermissionError as e:
            return Response({'detail': str(e), 'error': str(e)}, status=status.HTTP_403_FORBIDDEN)
        except (ValueError, ValidationError) as e:
            message = '; '.join(e.messages) if isinstance(e, ValidationError) and hasattr(e, 'messages') else str(e)
            return error_response(status.HTTP_400_BAD_REQUEST, message)
        except IntegrityError:
            # G2-02 fix: _create_student_from_request_data() (transfers services) does
            # a check-then-create on Student.student_id - the DB's real
            # unique constraint is the final backstop against a duplicate
            # row, but without this handler a legitimate concurrent-write
            # conflict (two different ADD_STUDENT requests racing to
            # create the same new student_id) surfaced as an unhandled
            # 500 instead of a clean, deterministic 4xx. The
            # transaction.atomic() block above has already rolled back
            # any partial write from this attempt.
            return error_response(status.HTTP_400_BAD_REQUEST, 'הבקשה לא אושרה עקב התנגשות נתונים - ייתכן שסטודנט עם ת.ז זו כבר נוצר או שהבקשה כבר טופלה. נא לרענן ולנסות שוב.')

        # req.student may have just gained/lost a BedAssignment above (new
        # assignment, ended assignment, or a swap) - req itself came from
        # get_queryset(), so req.student may still be carrying the
        # PRE-approval prefetched_current_assignment_list/
        # prefetched_placement_history_all caches (see get_queryset()).
        # Drop them so the response below reflects what was just
        # committed, not a stale pre-approval snapshot - the serializer's
        # getattr(..., None) fallback then re-queries fresh, exactly like
        # the original (pre-optimization) behavior always did.
        if req.student_id:
            for cache_attr in ('prefetched_current_assignment_list', 'prefetched_placement_history_all'):
                if hasattr(req.student, cache_attr):
                    delattr(req.student, cache_attr)

        return Response({
            'message': 'הבקשה אושרה בהצלחה',
            'request': StudentRequestSerializer(req).data,
        })

    @action(detail=True, methods=['put'])
    def reject(self, request, pk=None):
        if not request.user.is_boss:
            return error_response(status.HTTP_403_FORBIDDEN, 'רק מנהל יכול לדחות בקשות')

        req = self.get_object()
        if req.status != StudentRequest.Status.PENDING:
            return error_response(status.HTTP_400_BAD_REQUEST, 'הבקשה כבר טופלה')

        if not _user_can_review_request(request.user, req):
            return error_response(status.HTTP_403_FORBIDDEN, 'אין הרשאה לדחות בקשה זו')

        if not reject_student_request(req, request.user, lambda: request.data.get('reason', '')):
            return error_response(status.HTTP_400_BAD_REQUEST, 'הבקשה כבר טופלה')

        return Response({
            'message': 'הבקשה נדחתה',
            'request': StudentRequestSerializer(req).data,
        })

    @action(detail=True, methods=['put'])
    def cancel(self, request, pk=None):
        """
        Withdraw the caller's own still-pending request - distinct from
        reject(): REJECTED means a reviewer considered and declined the
        request; CANCELLED means the requesting side changed its mind
        before any reviewer acted. Used today by the Assisted Allocation
        "בהעברה" panel's "ביטול בקשת העברה" action on a pending
        region_transfer request, but left generic (any pending
        StudentRequest) rather than request_type-gated, matching how
        approve()/reject() are already generic actions on this viewset.
        """
        req = self.get_object()
        if req.status != StudentRequest.Status.PENDING:
            return error_response(status.HTTP_400_BAD_REQUEST, 'ניתן לבטל רק בקשה הממתינה לאישור')

        user = request.user
        is_requester = req.requested_by_id == user.id
        if not is_requester and not _user_can_cancel_request(user, req):
            return error_response(status.HTTP_403_FORBIDDEN, 'אין הרשאה לבטל בקשה זו')

        if not cancel_student_request(req, user):
            return error_response(status.HTTP_400_BAD_REQUEST, 'ניתן לבטל רק בקשה הממתינה לאישור')

        return Response({
            'message': 'בקשת ההעברה בוטלה',
            'request': StudentRequestSerializer(req).data,
        })
