"""Operations serializers."""

from django.utils import timezone
from rest_framework import serializers

from ..models import AllocationRun, ImportBatch, RegionInbox


# ===========================================
# ALLOCATION RUN SERIALIZER
# ===========================================
class AllocationRunSerializer(serializers.ModelSerializer):
    """Serialize allocation run data"""

    region_name = serializers.CharField(source='region.name', read_only=True)
    run_by_name = serializers.SerializerMethodField()
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    elapsed_search_seconds = serializers.SerializerMethodField()
    remaining_search_seconds = serializers.SerializerMethodField()

    class Meta:
        model = AllocationRun
        fields = [
            'id',
            'region',
            'region_name',
            'run_by',
            'run_by_name',
            'status',
            'status_display',
            'students_processed',
            'successful_assignments',
            'roommate_matches',
            'conflicts',
            'max_search_seconds',
            'search_started_at',
            'elapsed_search_seconds',
            'remaining_search_seconds',
            'started_at',
            'completed_at',
            'error_message',
        ]
        read_only_fields = ['id', 'started_at']

    def get_run_by_name(self, obj):
        if not obj.run_by:
            return None
        return obj.run_by.get_full_name() or obj.run_by.email

    def get_elapsed_search_seconds(self, obj):
        """
        Seconds of actual CP-SAT search time, anchored to
        search_started_at (stamped by allocation.solver immediately
        before solver.Solve() — see AllocationRun.search_started_at).
        0 while the solver hasn't started searching yet (QUEUED, or still
        loading/building candidates). Frozen at completed_at once the run
        reaches a terminal status, so repeated reads of a finished run
        never keep advancing.
        """
        if not obj.search_started_at:
            return 0
        end = obj.completed_at or timezone.now()
        return max(0, round((end - obj.search_started_at).total_seconds()))

    def get_remaining_search_seconds(self, obj):
        """max_search_seconds minus elapsed_search_seconds, floored at 0."""
        if obj.max_search_seconds is None:
            return None
        elapsed = self.get_elapsed_search_seconds(obj)
        return max(0, obj.max_search_seconds - elapsed)

    def validate(self, attrs):
        instance = self.instance

        status = attrs.get('status', getattr(instance, 'status', None))
        completed_at = attrs.get('completed_at', getattr(instance, 'completed_at', None))
        error_message = attrs.get('error_message', getattr(instance, 'error_message', ''))

        if status == AllocationRun.Status.RUNNING:
            if completed_at is not None:
                raise serializers.ValidationError({
                    'completed_at': 'Running allocation cannot have completed_at.'
                })
            if error_message:
                raise serializers.ValidationError({
                    'error_message': 'Running allocation cannot have error_message.'
                })

        if status == AllocationRun.Status.COMPLETED:
            if completed_at is None:
                raise serializers.ValidationError({
                    'completed_at': 'Completed allocation must have completed_at.'
                })
            if error_message:
                raise serializers.ValidationError({
                    'error_message': 'Completed allocation should not have error_message.'
                })

        if status == AllocationRun.Status.FAILED:
            if completed_at is None:
                raise serializers.ValidationError({
                    'completed_at': 'Failed allocation must have completed_at.'
                })
            if not error_message:
                raise serializers.ValidationError({
                    'error_message': 'Failed allocation should include error_message.'
                })

        return attrs


# ===========================================
# IMPORT BATCH SERIALIZER
# ===========================================
class ImportBatchSerializer(serializers.ModelSerializer):
    """Serialize import batch data"""

    uploaded_by_name = serializers.SerializerMethodField()
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    region_breakdown = serializers.SerializerMethodField()

    class Meta:
        model = ImportBatch
        fields = [
            'id',
            'uploaded_by',
            'uploaded_by_name',
            'kind',
            'filename',
            'total_students',
            'status',
            'status_display',
            'error_message',
            'created_at',
            'started_at',
            'finished_at',
            'total_rows',
            'processed_rows',
            'result',
            'region_breakdown',
        ]
        read_only_fields = ['id', 'created_at']

    def get_uploaded_by_name(self, obj):
        return obj.uploaded_by.get_full_name() or obj.uploaded_by.email

    def get_region_breakdown(self, obj):
        return [
            {
                'region_id': inbox.region.id,
                'region_name': inbox.region.name,
                'count': inbox.students_count,
                'status': inbox.status,
            }
            for inbox in obj.region_inboxes.select_related('region').all()
        ]

    def validate(self, attrs):
        instance = self.instance

        status = attrs.get('status', getattr(instance, 'status', None))
        error_message = attrs.get('error_message', getattr(instance, 'error_message', ''))

        if status == ImportBatch.Status.FAILED:
            if not error_message:
                raise serializers.ValidationError({
                    'error_message': 'Failed batch should include error_message.'
                })
        elif error_message:
            raise serializers.ValidationError({
                'error_message': f'{status} batch cannot have error_message.'
            })

        return attrs


# ===========================================
# REGION INBOX SERIALIZER
# ===========================================
class RegionInboxSerializer(serializers.ModelSerializer):
    """Serialize region inbox data"""

    region_name = serializers.CharField(source='region.name', read_only=True)
    batch_filename = serializers.CharField(source='batch.filename', read_only=True)
    batch_created_at = serializers.DateTimeField(source='batch.created_at', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = RegionInbox
        fields = [
            'id',
            'region',
            'region_name',
            'batch',
            'batch_filename',
            'batch_created_at',
            'students_count',
            'status',
            'status_display',
            'message',
            'created_at',
            'viewed_at',
            'processed_at',
        ]
        read_only_fields = ['id', 'created_at']

    def validate(self, attrs):
        instance = self.instance

        status = attrs.get('status', getattr(instance, 'status', None))
        viewed_at = attrs.get('viewed_at', getattr(instance, 'viewed_at', None))
        processed_at = attrs.get('processed_at', getattr(instance, 'processed_at', None))

        if status == RegionInbox.Status.PENDING:
            if viewed_at is not None or processed_at is not None:
                raise serializers.ValidationError(
                    'Pending inbox item cannot have viewed_at or processed_at.'
                )

        if status == RegionInbox.Status.VIEWED:
            if viewed_at is None:
                raise serializers.ValidationError({
                    'viewed_at': 'Viewed inbox item must have viewed_at.'
                })

        if status == RegionInbox.Status.PROCESSED:
            if processed_at is None:
                raise serializers.ValidationError({
                    'processed_at': 'Processed inbox item must have processed_at.'
                })

        return attrs
