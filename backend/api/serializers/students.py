"""Student serializers."""

from rest_framework import serializers

from ..models import Student


# ===========================================
# STUDENT LIST SERIALIZER
# ===========================================

class StudentListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for students list page"""

    full_name = serializers.CharField(read_only=True)
    gender_display = serializers.CharField(source='get_gender_display', read_only=True)
    requested_religion_display = serializers.CharField(source='get_requested_religion_display', read_only=True)
    category_display = serializers.CharField(source='get_category_display', read_only=True)

    accepted_dorm_type_name = serializers.CharField(source='accepted_dorm_type.name', read_only=True)
    accepted_dorm_type_code = serializers.IntegerField(source='accepted_dorm_type.code', read_only=True)

    is_assigned = serializers.BooleanField(read_only=True)

    current_building = serializers.SerializerMethodField()
    current_apartment = serializers.SerializerMethodField()
    current_room = serializers.SerializerMethodField()
    current_bed = serializers.SerializerMethodField()

    class Meta:
        model = Student
        fields = [
            'id',
            'student_id',
            'business_partner_id',
            'first_name',
            'last_name',
            'full_name',
            'email',
            'phone',
            'gender',
            'gender_display',
            'requested_religion',
            'requested_religion_display',
            'category',
            'category_display',
            'housing_type',
            'accepted_dorm_type',
            'accepted_dorm_type_name',
            'accepted_dorm_type_code',
            'is_priority',
            'priority_reason',
            'assigned_room',
            'is_assigned',
            'current_building',
            'current_apartment',
            'current_room',
            'current_bed',
        ]

    def get_current_building(self, obj):
        return obj.assigned_room.apartment.building.number if obj.assigned_room else None

    def get_current_apartment(self, obj):
        return obj.assigned_room.apartment.number if obj.assigned_room else None

    def get_current_room(self, obj):
        return obj.assigned_room.name if obj.assigned_room else None

    def get_current_bed(self, obj):
        # Uses the queryset's prefetched 'prefetched_active_assignments'
        # (one extra query total for the whole page) rather than
        # obj.current_bed, whose default property issues a fresh
        # BedAssignment query per student - the list page's N+1 source.
        # Falls back to the property only if a caller passes an object that
        # wasn't built through StudentViewSet's list queryset.
        assignments = getattr(obj, 'prefetched_active_assignments', None)
        if assignments is not None:
            return assignments[0].bed.label if assignments else None
        bed = obj.current_bed
        return bed.label if bed else None

# ===========================================
# STUDENT SERIALIZER
# ===========================================
class StudentSerializer(serializers.ModelSerializer):
    """Serialize student data"""

    full_name = serializers.CharField(read_only=True)
    gender_display = serializers.CharField(source='get_gender_display', read_only=True)
    requested_religion_display = serializers.CharField(source='get_requested_religion_display', read_only=True)
    religious_display = serializers.CharField(source='get_religious_display', read_only=True)
    category_display = serializers.CharField(source='get_category_display', read_only=True)

    accepted_dorm_type_name = serializers.CharField(source='accepted_dorm_type.name', read_only=True)
    accepted_dorm_type_code = serializers.IntegerField(source='accepted_dorm_type.code', read_only=True)
    # The student's own (home) region - lets the assign/reassign UI default
    # the region selector without a second round trip through dorm_types.
    region_id = serializers.CharField(source='accepted_dorm_type.region_id', read_only=True, default=None)
    region_name = serializers.CharField(source='accepted_dorm_type.region.name', read_only=True, default=None)

    assigned_room_name = serializers.CharField(source='assigned_room.name', read_only=True)
    assigned_room_id = serializers.IntegerField(source='assigned_room.id', read_only=True)
    assigned_building_number = serializers.IntegerField(
        source='assigned_room.apartment.building.number',
        read_only=True
    )
    assigned_apartment_number = serializers.CharField(
        source='assigned_room.apartment.number',
        read_only=True
    )

    housing_gender = serializers.CharField(read_only=True)
    is_assigned = serializers.BooleanField(read_only=True)

    current_bed_id = serializers.SerializerMethodField()
    current_bed_label = serializers.SerializerMethodField()

    batch_id = serializers.IntegerField(source='batch.id', read_only=True, allow_null=True)

    class Meta:
        model = Student
        fields = [
            'id',
            'student_id',
            'business_partner_id',
            'first_name',
            'last_name',
            'full_name',
            'email',
            'email_secondary',
            'phone',
            'phone_secondary',
            'city',
            'gender',
            'gender_display',
            'requested_religion',
            'requested_religion_display',
            'religious',
            'religious_display',
            'category',
            'category_display',
            'housing_type',
            'housing_gender',
            'allocation_group',
            'accepted_dorm_type',
            'accepted_dorm_type_name',
            'accepted_dorm_type_code',
            'region_id',
            'region_name',
            'batch',
            'batch_id',
            'roommate_request_1',
            'roommate_request_2',
            'roommate_request_3',
            'roommate_request_4',
            'roommate_request_5',
            'roommate_request_flag_1',
            'roommate_request_flag_2',
            'roommate_request_flag_3',
            'roommate_request_flag_4',
            'roommate_request_flag_5',
            'special_status_1',
            'special_status_2',
            'special_status_3',
            'special_status_4',
            'is_priority',
            'priority_reason',
            'accessibility_flag',
            'disability_percent',
            'medical_reason',
            'study_points',
            'current_address',
            'current_dorm_type',
            'move_in_date',
            'move_out_date',
            'assigned_room',
            'assigned_room_id',
            'assigned_room_name',
            'assigned_building_number',
            'assigned_apartment_number',
            'is_assigned',
            'current_bed_id',
            'current_bed_label',
            'created_at',
            'updated_at',
        ]
        read_only_fields = [
            'id',
            'full_name',
            'housing_gender',
            'is_assigned',
            'current_bed_id',
            'current_bed_label',
            'created_at',
            'updated_at',
            # G3-06: assigned_room must never be settable through a direct
            # Student PATCH/POST - it bypasses assign_student_to_room's
            # locking, capacity checks, business validation, BedAssignment
            # creation and audit trail entirely. All real placement changes
            # go through room-assignments/assign|move|unassign/swap,
            # StudentRequestViewSet.approve(), or assisted-allocation
            # assign()/override() - every one of those writes assigned_room
            # via the model layer (assign_student_to_room), not this field.
            'assigned_room',
        ]

    def _current_bed_cached(self, obj):
        # Student.current_bed is an uncached @property that runs a fresh
        # BedAssignment query on every access - get_current_bed_id and
        # get_current_bed_label both used to call it independently,
        # issuing the identical query twice per detail/create/update
        # response. Cache the result on the instance for the lifetime of
        # this serialization instead (DRF calls both methods on the same
        # obj), so it runs once. Same underlying query/semantics, just
        # not repeated. (G1-15.)
        if not hasattr(obj, '_cached_current_bed'):
            obj._cached_current_bed = obj.current_bed
        return obj._cached_current_bed

    def get_current_bed_id(self, obj):
        bed = self._current_bed_cached(obj)
        return bed.id if bed else None

    def get_current_bed_label(self, obj):
        bed = self._current_bed_cached(obj)
        return bed.label if bed else None

    def validate(self, attrs):
        """
        housing_type/accepted_dorm_type are only required for students who
        are actually eligible for a dorm assignment (every category except
        LEAVING - leaving students are exempt). This
        runs on both create and update (PATCH), reading whichever of
        housing_type/category/accepted_dorm_type is present in this request
        and falling back to the existing instance value for a partial update.
        """
        instance = self.instance

        def effective(field, default=None):
            if field in attrs:
                return attrs[field]
            if instance is not None:
                return getattr(instance, field)
            return default

        category = effective('category', Student.StudentCategory.NEW)
        is_eligible = category != Student.StudentCategory.LEAVING

        if is_eligible:
            housing_type = effective('housing_type', '')
            if not housing_type:
                raise serializers.ValidationError({
                    'housing_type': ['יש לבחור סוג דיור לפני שניתן לבצע שיבוץ.']
                })

            accepted_dorm_type = effective('accepted_dorm_type', None)
            if not accepted_dorm_type:
                raise serializers.ValidationError({
                    'accepted_dorm_type': ['יש לבחור אזור/סוג מעונות לפני שניתן לבצע שיבוץ.']
                })

        return attrs
