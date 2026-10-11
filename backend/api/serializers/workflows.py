"""Workflow serializers."""

from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied

from ..models import Region, BedAssignment, MovementRequest, Transfer, StudentRequest


# ===========================================
# BED ASSIGNMENT SERIALIZER
# ===========================================
class BedAssignmentSerializer(serializers.ModelSerializer):
    """Serialize bed assignment data"""

    student_name = serializers.CharField(source='student.full_name', read_only=True)
    student_id_number = serializers.CharField(source='student.student_id', read_only=True)
    bed_label = serializers.CharField(source='bed.label', read_only=True)
    room_name = serializers.CharField(source='bed.room.name', read_only=True)
    apartment_number = serializers.CharField(source='bed.room.apartment.number', read_only=True)
    building_number = serializers.IntegerField(source='bed.room.apartment.building.number', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    assignment_type_display = serializers.CharField(source='get_assignment_type_display', read_only=True)
    assigned_by_name = serializers.SerializerMethodField()

    class Meta:
        model = BedAssignment
        fields = [
            'id',
            'student',
            'student_name',
            'student_id_number',
            'bed',
            'bed_label',
            'room_name',
            'apartment_number',
            'building_number',
            'status',
            'status_display',
            'assignment_type',
            'assignment_type_display',
            'assigned_by',
            'assigned_by_name',
            'assigned_at',
            'ended_at',
        ]
        read_only_fields = ['id', 'assigned_at']

    def get_assigned_by_name(self, obj):
        if not obj.assigned_by:
            return None
        return obj.assigned_by.get_full_name() or obj.assigned_by.email

    def validate(self, attrs):
        instance = self.instance

        student = attrs.get('student', getattr(instance, 'student', None))
        bed = attrs.get('bed', getattr(instance, 'bed', None))
        status = attrs.get('status', getattr(instance, 'status', None))
        ended_at = attrs.get('ended_at', getattr(instance, 'ended_at', None))

        if status == BedAssignment.Status.ACTIVE and ended_at is not None:
            raise serializers.ValidationError({
                'ended_at': 'Active assignment cannot have an ended_at value.'
            })

        if status in [BedAssignment.Status.ENDED, BedAssignment.Status.CANCELLED] and ended_at is None:
            raise serializers.ValidationError({
                'ended_at': 'Ended or cancelled assignment must have ended_at.'
            })

        if status == BedAssignment.Status.ACTIVE and bed is not None:
            qs = BedAssignment.objects.filter(
                bed=bed,
                status=BedAssignment.Status.ACTIVE
            )
            if instance:
                qs = qs.exclude(pk=instance.pk)
            if qs.exists():
                raise serializers.ValidationError({
                    'bed': 'This bed already has an active assignment.'
                })

        if status == BedAssignment.Status.ACTIVE and student is not None:
            qs = BedAssignment.objects.filter(
                student=student,
                status=BedAssignment.Status.ACTIVE
            )
            if instance:
                qs = qs.exclude(pk=instance.pk)
            if qs.exists():
                raise serializers.ValidationError({
                    'student': 'This student already has an active bed assignment.'
                })

        return attrs


# ===========================================
# MOVEMENT REQUEST SERIALIZER
# ===========================================
class MovementRequestSerializer(serializers.ModelSerializer):
    """Serialize movement request data"""

    student_name = serializers.CharField(source='student.full_name', read_only=True)
    from_assignment_id = serializers.IntegerField(source='from_assignment.id', read_only=True)
    from_bed_label = serializers.CharField(source='from_assignment.bed.label', read_only=True)
    to_bed_label = serializers.CharField(source='to_bed.label', read_only=True)
    movement_type_display = serializers.CharField(source='get_movement_type_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    requested_by_name = serializers.SerializerMethodField()
    approved_by_name = serializers.SerializerMethodField()

    class Meta:
        model = MovementRequest
        fields = [
            'id',
            'student',
            'student_name',
            'from_assignment',
            'from_assignment_id',
            'from_bed_label',
            'to_bed',
            'to_bed_label',
            'movement_type',
            'movement_type_display',
            'status',
            'status_display',
            'reason',
            'requested_by',
            'requested_by_name',
            'approved_by',
            'approved_by_name',
            'created_at',
            'reviewed_at',
            'completed_at',
        ]
        read_only_fields = ['id', 'created_at']

    def get_requested_by_name(self, obj):
        if not obj.requested_by:
            return None
        return obj.requested_by.get_full_name() or obj.requested_by.email

    def get_approved_by_name(self, obj):
        if not obj.approved_by:
            return None
        return obj.approved_by.get_full_name() or obj.approved_by.email

    def validate(self, attrs):
        instance = self.instance

        status = attrs.get('status', getattr(instance, 'status', None))
        approved_by = attrs.get('approved_by', getattr(instance, 'approved_by', None))
        reviewed_at = attrs.get('reviewed_at', getattr(instance, 'reviewed_at', None))
        completed_at = attrs.get('completed_at', getattr(instance, 'completed_at', None))
        to_bed = attrs.get('to_bed', getattr(instance, 'to_bed', None))

        if status == MovementRequest.Status.PENDING:
            if approved_by is not None or reviewed_at is not None or completed_at is not None:
                raise serializers.ValidationError(
                    'Pending request cannot have approval/completion data.'
                )

        if status == MovementRequest.Status.APPROVED:
            if approved_by is None or reviewed_at is None:
                raise serializers.ValidationError(
                    'Approved request must have approved_by and reviewed_at.'
                )

        if status == MovementRequest.Status.REJECTED:
            if approved_by is None or reviewed_at is None:
                raise serializers.ValidationError(
                    'Rejected request must have approved_by and reviewed_at.'
                )

        if status == MovementRequest.Status.COMPLETED:
            if approved_by is None or reviewed_at is None or completed_at is None:
                raise serializers.ValidationError(
                    'Completed request must have approval and completion timestamps.'
                )

        if status in [MovementRequest.Status.APPROVED, MovementRequest.Status.COMPLETED] and to_bed is None:
            raise serializers.ValidationError({
                'to_bed': 'Approved or completed request must have target bed.'
            })

        return attrs


# ===========================================
# TRANSFER SERIALIZER
# ===========================================
class TransferSerializer(serializers.ModelSerializer):
    """Serialize transfer request data"""

    student_name = serializers.CharField(source='student.full_name', read_only=True)
    student_id_number = serializers.CharField(source='student.student_id', read_only=True)
    from_room_name = serializers.CharField(source='from_room.name', read_only=True)
    to_room_name = serializers.CharField(source='to_room.name', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    requested_by_region_name = serializers.CharField(source='requested_by.region.name', read_only=True)

    from_building_number = serializers.IntegerField(source='from_room.apartment.building.number', read_only=True)
    from_apartment_number = serializers.CharField(source='from_room.apartment.number', read_only=True)

    to_building_number = serializers.IntegerField(source='to_room.apartment.building.number', read_only=True)
    to_apartment_number = serializers.CharField(source='to_room.apartment.number', read_only=True)
    requested_by_name = serializers.SerializerMethodField()
    reviewed_by_name = serializers.SerializerMethodField()

    class Meta:
        model = Transfer
        fields = [
            'id',
            'student',
            'student_name',
            'student_id_number',

            'from_room',
            'from_room_name',
            'from_building_number',
            'from_apartment_number',

            'to_room',
            'to_room_name',
            'to_building_number',
            'to_apartment_number',

            'reason',
            'status',
            'status_display',

            'requested_by',
            'requested_by_name',
            'requested_by_region_name',

            'reviewed_by',
            'reviewed_by_name',
            'reviewed_at',

            'rejection_reason',
            'movement_request',
            'created_at',
            'updated_at',
        ]
        # G3-02/G3-22: status/reviewed_by/reviewed_at/rejection_reason are
        # workflow-owned - they may only ever change through
        # TransferViewSet.approve()/reject() (which apply
        # user_can_approve_transfer(), the room-availability check, and
        # create the actual BedAssignment), never through a generic
        # PUT/PATCH to this serializer. requested_by is likewise
        # system-owned (set from request.user in perform_create) so it can
        # never be spoofed to misattribute who requested a transfer.
        # movement_request is populated internally by perform_create/
        # approve(), never client-supplied.
        read_only_fields = [
            'id', 'created_at', 'updated_at',
            'status', 'reviewed_by', 'reviewed_at', 'rejection_reason',
            'requested_by', 'movement_request',
        ]

    def get_requested_by_name(self, obj):
        return obj.requested_by.get_full_name() or obj.requested_by.email

    def get_reviewed_by_name(self, obj):
        if not obj.reviewed_by:
            return None
        return obj.reviewed_by.get_full_name() or obj.reviewed_by.email

    def validate(self, attrs):
        instance = self.instance

        from_room = attrs.get('from_room', getattr(instance, 'from_room', None))
        to_room = attrs.get('to_room', getattr(instance, 'to_room', None))
        status = attrs.get('status', getattr(instance, 'status', None))
        reviewed_by = attrs.get('reviewed_by', getattr(instance, 'reviewed_by', None))
        reviewed_at = attrs.get('reviewed_at', getattr(instance, 'reviewed_at', None))
        rejection_reason = attrs.get('rejection_reason', getattr(instance, 'rejection_reason', ''))

        if from_room and to_room and from_room == to_room:
            raise serializers.ValidationError({
                'to_room': 'Source room and target room cannot be the same.'
            })

        if status == Transfer.Status.PENDING:
            if reviewed_by is not None or reviewed_at is not None:
                raise serializers.ValidationError(
                    'Pending transfer cannot have review data.'
                )
            if rejection_reason:
                raise serializers.ValidationError(
                    'Pending transfer cannot have rejection_reason.'
                )

        if status == Transfer.Status.APPROVED:
            if reviewed_by is None or reviewed_at is None:
                raise serializers.ValidationError(
                    'Approved transfer must have reviewed_by and reviewed_at.'
                )
            if rejection_reason:
                raise serializers.ValidationError(
                    'Approved transfer cannot have rejection_reason.'
                )

        if status == Transfer.Status.REJECTED:
            if reviewed_by is None or reviewed_at is None:
                raise serializers.ValidationError(
                    'Rejected transfer must have reviewed_by and reviewed_at.'
                )

        return attrs


# ===========================================
# STUDENT REQUEST SERIALIZER
# ===========================================
class StudentRequestSerializer(serializers.ModelSerializer):
    """
    Serialize the unified "Requests" workflow (add student, remove student,
    room change, apartment change, other). Backs the /api/requests/ endpoints
    used by the Requests (Transfers) page and the Students page.
    """

    request_type_display = serializers.CharField(source='get_request_type_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    priority_display = serializers.CharField(source='get_priority_display', read_only=True)

    student_name = serializers.SerializerMethodField()
    student_id_number = serializers.CharField(source='student.student_id', read_only=True, default=None)
    student_phone = serializers.CharField(source='student.phone', read_only=True, default=None)

    requested_by_name = serializers.SerializerMethodField()
    reviewed_by_name = serializers.SerializerMethodField()

    target_room_name = serializers.CharField(source='target_room.name', read_only=True, default=None)
    target_building_number = serializers.IntegerField(
        source='target_room.apartment.building.number', read_only=True, default=None
    )
    target_apartment_number = serializers.CharField(
        source='target_room.apartment.number', read_only=True, default=None
    )

    swap_with_student_name = serializers.CharField(source='swap_with_student.full_name', read_only=True, default=None)
    swap_with_student_id_number = serializers.CharField(
        source='swap_with_student.student_id', read_only=True, default=None
    )
    target_region_name = serializers.CharField(source='target_region.name', read_only=True, default=None)

    # Transfer scope (same-region / cross-region). The scope and destination
    # regions are writable at creation (validated against the caller's
    # role); source region, assignment snapshot, and the final assignment
    # are computed and persisted server-side only.
    transfer_scope_display = serializers.CharField(
        source='get_transfer_scope_display', read_only=True, default=None
    )
    source_region_name = serializers.CharField(source='source_region.name', read_only=True, default=None)
    destination_regions = serializers.PrimaryKeyRelatedField(
        many=True, queryset=Region.objects.all(), required=False,
    )
    destination_region_names = serializers.SerializerMethodField()
    final_bed_label = serializers.CharField(source='final_assignment.bed.label', read_only=True, default=None)

    current_region = serializers.SerializerMethodField()
    current_building = serializers.SerializerMethodField()
    current_apartment = serializers.SerializerMethodField()
    current_room = serializers.SerializerMethodField()
    current_bed = serializers.SerializerMethodField()
    placement_history = serializers.SerializerMethodField()

    class Meta:
        model = StudentRequest
        fields = [
            'id', 'request_number',
            'request_type', 'request_type_display',
            'reason', 'status', 'status_display',
            'priority', 'priority_display',
            'other_description', 'same_apartment',
            'removal_notes', 'removal_reason',
            'student', 'student_name', 'student_id_number', 'student_phone', 'student_data',
            'target_room', 'target_room_name', 'target_building_number', 'target_apartment_number',
            'swap_with_student', 'swap_with_student_name', 'swap_with_student_id_number',
            'target_region', 'target_region_name',
            'transfer_scope', 'transfer_scope_display',
            'source_region', 'source_region_name',
            'destination_regions', 'destination_region_names',
            'current_assignment_snapshot', 'final_assignment', 'final_bed_label',
            'current_region', 'current_building', 'current_apartment', 'current_room', 'current_bed',
            'placement_history',
            'requested_by', 'requested_by_name',
            'reviewed_by', 'reviewed_by_name', 'reviewed_at', 'rejection_reason',
            'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'request_number', 'status',
            'source_region', 'current_assignment_snapshot', 'final_assignment',
            'requested_by', 'reviewed_by', 'reviewed_at', 'rejection_reason',
            'created_at', 'updated_at',
        ]

    def get_destination_region_names(self, obj):
        return [r.name for r in obj.destination_regions.all()]

    def get_student_name(self, obj):
        if obj.student:
            return obj.student.full_name
        data = obj.student_data or {}
        name = f"{data.get('first_name', '')} {data.get('last_name', '')}".strip()
        return name or None

    def get_requested_by_name(self, obj):
        if not obj.requested_by:
            return None
        return obj.requested_by.get_full_name() or obj.requested_by.email

    def get_reviewed_by_name(self, obj):
        if not obj.reviewed_by:
            return None
        return obj.reviewed_by.get_full_name() or obj.reviewed_by.email

    def _current_room(self, obj):
        if not obj.student_id:
            return None
        return obj.student.assigned_room

    def get_current_region(self, obj):
        room = self._current_room(obj)
        if not room:
            return None
        region = room.region
        return region.name if region else None

    def get_current_building(self, obj):
        room = self._current_room(obj)
        return room.apartment.building.number if room else None

    def get_current_apartment(self, obj):
        room = self._current_room(obj)
        return room.apartment.number if room else None

    def get_current_room(self, obj):
        room = self._current_room(obj)
        return room.name if room else None

    def get_current_bed(self, obj):
        if not obj.student_id:
            return None
        # get_queryset() prefetches at most the one ACTIVE BedAssignment per
        # student as student.prefetched_current_assignment_list (a
        # unique_active_assignment_per_student DB constraint guarantees
        # there is never more than one) - read that first, with zero extra
        # queries. Falls back to the original property (which issues its
        # own query) when the object wasn't built through get_queryset()
        # (e.g. a freshly-created StudentRequest serialized straight from
        # perform_create()), or when the cache was deliberately invalidated
        # after a mutation (see StudentRequestViewSet.approve()).
        prefetched = getattr(obj.student, 'prefetched_current_assignment_list', None)
        if prefetched is not None:
            bed = prefetched[0].bed if prefetched else None
        else:
            bed = obj.student.current_bed
        return bed.label if bed else None

    def get_placement_history(self, obj):
        if not obj.student_id:
            return []
        history = []
        # Same annotation-first-with-fallback pattern as get_current_bed:
        # student.prefetched_placement_history_all holds this student's 10
        # most-recent bed_assignments (any status, DB-bounded via
        # api.domains.transfers.queries.top10_bed_assignment_history_qs(),
        # whose bound the placement-history performance tests verify),
        # already ordered '-assigned_at' and select_related, fetched once
        # regardless of how many StudentRequest rows are on this page. The
        # [:10] slice below is now a defensive no-op (the DB query already
        # returns at most 10) kept for safety and to match the fallback
        # path exactly.
        prefetched = getattr(obj.student, 'prefetched_placement_history_all', None)
        if prefetched is not None:
            assignments = prefetched[:10]
        else:
            assignments = obj.student.bed_assignments.select_related(
                'bed__room__apartment__building',
                'bed__room__apartment__building__dorm_type__region',
            ).order_by('-assigned_at')[:10]
        for a in assignments:
            room = a.bed.room
            history.append({
                'region': room.region.name if room.region else None,
                'building': room.apartment.building.number,
                'apartment': room.apartment.number,
                'room': room.name,
                'status': a.status,
                'assigned_at': a.assigned_at,
                'ended_at': a.ended_at,
            })
        return history

    def validate(self, attrs):
        request_type = attrs.get(
            'request_type', getattr(self.instance, 'request_type', None)
        )
        student = attrs.get('student', getattr(self.instance, 'student', None))
        student_data = attrs.get(
            'student_data', getattr(self.instance, 'student_data', None)
        ) or {}

        needs_existing_student = {
            StudentRequest.RequestType.ROOM,
            StudentRequest.RequestType.APARTMENT,
            StudentRequest.RequestType.REMOVE_STUDENT,
            StudentRequest.RequestType.SWAP,
            StudentRequest.RequestType.REGION_TRANSFER,
        }

        if request_type in needs_existing_student and not student:
            raise serializers.ValidationError({
                'student': 'This request type requires selecting an existing student.'
            })

        if request_type == StudentRequest.RequestType.SWAP:
            swap_with = attrs.get('swap_with_student', getattr(self.instance, 'swap_with_student', None))
            if not swap_with:
                raise serializers.ValidationError({
                    'swap_with_student': 'A swap request requires selecting the other student.'
                })
            if student and swap_with.id == student.id:
                raise serializers.ValidationError({
                    'swap_with_student': 'A student cannot swap with themselves.'
                })

        if request_type == StudentRequest.RequestType.REGION_TRANSFER:
            target_region = attrs.get('target_region', getattr(self.instance, 'target_region', None))
            if not target_region:
                raise serializers.ValidationError({
                    'target_region': 'A region transfer request requires a destination region.'
                })

        if request_type == StudentRequest.RequestType.ADD_STUDENT and not self.instance:
            required = ['student_id', 'first_name', 'last_name', 'gender']
            missing = [f for f in required if not student_data.get(f)]
            if missing:
                raise serializers.ValidationError({
                    'student_data': f"Missing required new-student fields: {', '.join(missing)}"
                })

        # Transfer-scope role rules are enforced HERE (server-side), never by
        # trusting the frontend: only a central admin may create a
        # cross-region transfer or name destination regions, and a
        # cross-region transfer must name at least one destination region.
        if request_type in (StudentRequest.RequestType.ROOM, StudentRequest.RequestType.APARTMENT):
            request = self.context.get('request')
            user = getattr(request, 'user', None)
            scope = attrs.get('transfer_scope')
            destinations = attrs.get('destination_regions') or []
            wants_cross = scope == StudentRequest.TransferScope.CROSS_REGION
            if user is not None and not user.is_central_admin and (wants_cross or destinations):
                raise PermissionDenied('אין לך הרשאה לבצע מעבר לאזור אחר.')
            if wants_cross and not destinations:
                raise serializers.ValidationError(
                    {'destination_regions': 'יש לבחור לפחות אזור יעד אחד עבור מעבר לאזור אחר.'}
                )
            if not wants_cross:
                # Same-region (or legacy unscoped) transfers never carry
                # destination regions.
                attrs['destination_regions'] = []

        return attrs
