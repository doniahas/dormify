"""
ImportBatch lifecycle services: claiming a pending batch for processing,
stop / stop-and-delete requests, and deleting the students a batch created.

Every transition re-reads the batch under its row lock; ownership and kind
checks (who may act on the batch) stay in api.views.imports.
"""

from django.db import transaction
from django.db.models import ProtectedError
from django.utils import timezone

from ...models import ImportBatch, Student

# Statuses a running import loop treats as "stop at the next row".
IMPORT_BATCH_STOP_STATUSES = frozenset({
    ImportBatch.Status.CANCELLATION_REQUESTED,
    ImportBatch.Status.STOP_AND_DELETE_REQUESTED,
})

# Statuses in which the batch's created students may be deleted afterwards.
FINISHED_BATCH_STATUSES = (
    ImportBatch.Status.COMPLETED,
    ImportBatch.Status.STOPPED,
    ImportBatch.Status.FAILED,
)


class ImportBatchStateError(Exception):
    """The batch is not in a status that allows the requested transition."""

    def __init__(self, batch):
        super().__init__(f'import batch {batch.pk} is {batch.status}')
        self.batch = batch


def delete_students_created_by_batch(batch):
    """
    Deletes ONLY Student rows this batch created (created_in_batch) - never
    students it merely updated, never dorm inventory. BedAssignment.student
    is on_delete=PROTECT, so a created student who has since been allocated
    a bed raises ProtectedError; caught per-student here so one protected
    row never blocks the rest and is never silently reported as deleted.
    """
    deleted = []
    protected = []

    for student in Student.objects.filter(created_in_batch=batch):
        student_pk = student.pk
        student_label = student.student_id
        try:
            student.delete()
            deleted.append(student_pk)
        except ProtectedError:
            protected.append({'id': student_pk, 'student_id': student_label})

    return {
        'requested': True,
        'deleted_count': len(deleted),
        'protected_count': len(protected),
        'protected_students': protected,
        'performed_at': timezone.now().isoformat(),
    }


def claim_pending_batch(batch_id, filename):
    """
    Move a PENDING batch to PROCESSING under its row lock, recording the
    uploaded filename and start time. Raises ImportBatchStateError when the
    batch already left PENDING (a second upload for the same batch id).
    """
    with transaction.atomic():
        batch = ImportBatch.objects.select_for_update().get(pk=batch_id)

        if batch.status != ImportBatch.Status.PENDING:
            raise ImportBatchStateError(batch)

        batch.filename = filename
        batch.status = ImportBatch.Status.PROCESSING
        batch.started_at = timezone.now()
        batch.save(update_fields=['filename', 'status', 'started_at'])

    return batch


def request_batch_stop(batch_id):
    """Ask a PROCESSING batch to stop; raises ImportBatchStateError otherwise."""
    with transaction.atomic():
        batch = ImportBatch.objects.select_for_update().get(pk=batch_id)

        if batch.status != ImportBatch.Status.PROCESSING:
            raise ImportBatchStateError(batch)

        batch.status = ImportBatch.Status.CANCELLATION_REQUESTED
        batch.save(update_fields=['status'])

    return batch


def request_batch_stop_and_delete(batch_id):
    """
    Ask a running batch to stop and delete what it created. A PENDING batch
    (nothing created yet) is resolved to STOPPED immediately; a PROCESSING
    or CANCELLATION_REQUESTED batch is flagged STOP_AND_DELETE_REQUESTED so
    the still-running upload performs the deletion itself before it returns
    (see api.domains.imports.ingestion). Any other status raises
    ImportBatchStateError.
    """
    with transaction.atomic():
        batch = ImportBatch.objects.select_for_update().get(pk=batch_id)

        if batch.status == ImportBatch.Status.PENDING:
            # Nothing was ever created for this batch - resolve immediately,
            # no running loop will ever notice a requested-state flag here.
            batch.status = ImportBatch.Status.STOPPED
            batch.finished_at = timezone.now()
            batch.result = {
                'success': True,
                'stopped': True,
                'deletion': {
                    'requested': True,
                    'deleted_count': 0,
                    'protected_count': 0,
                    'protected_students': [],
                    'performed_at': timezone.now().isoformat(),
                },
            }
            batch.save(update_fields=['status', 'finished_at', 'result'])
            return batch

        if batch.status not in (
            ImportBatch.Status.PROCESSING,
            ImportBatch.Status.CANCELLATION_REQUESTED,
        ):
            raise ImportBatchStateError(batch)

        batch.status = ImportBatch.Status.STOP_AND_DELETE_REQUESTED
        batch.save(update_fields=['status'])

    return batch


def delete_batch_created_students(batch_id):
    """
    Delete the students a finished (COMPLETED / STOPPED / FAILED) batch
    created and record the deletion summary on the batch result. Raises
    ImportBatchStateError while the batch is still running.
    """
    with transaction.atomic():
        batch = ImportBatch.objects.select_for_update().get(pk=batch_id)

        if batch.status not in FINISHED_BATCH_STATUSES:
            raise ImportBatchStateError(batch)

        deletion = delete_students_created_by_batch(batch)
        result = dict(batch.result or {})
        result['deletion'] = deletion
        batch.result = result
        batch.save(update_fields=['result'])

    return batch
