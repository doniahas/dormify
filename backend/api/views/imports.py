"""Excel import and region-inbox HTTP views."""

import os
import traceback

import pandas as pd
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from ..domains.imports.batches import (
    ImportBatchStateError,
    claim_pending_batch,
    delete_batch_created_students,
    request_batch_stop,
    request_batch_stop_and_delete,
)
from ..domains.imports.ingestion import (
    run_additions_import,
    run_status_report_import,
)
from ..domains.imports.parsing import validate_gender_model_for_housing_import
from ..models import ImportBatch, RegionInbox
from ..serializers import ImportBatchSerializer, RegionInboxSerializer
from ..contracts.errors import error_response, failure_response


def _get_owned_batch_or_error(request, batch_id, expected_kind=None):
    """Shared lookup+ownership+kind check for the batch-lifecycle endpoints.

    Returns (batch, None) on success, or (None, Response) on failure - the
    caller just does `if error: return error`.
    """
    if not request.user.is_central_admin:
        return None, error_response(status.HTTP_403_FORBIDDEN, 'רק מנהל מרכזי יכול לבצע פעולה זו', error_en='Only Central Admin can perform this action')

    try:
        batch = ImportBatch.objects.get(pk=batch_id)
    except ImportBatch.DoesNotExist:
        return None, error_response(status.HTTP_404_NOT_FOUND, 'קובץ יבוא לא נמצא', error_en='Import batch not found')

    if batch.uploaded_by_id != request.user.id:
        return None, error_response(status.HTTP_403_FORBIDDEN, 'קובץ יבוא זה שייך למשתמש אחר', error_en='This import batch belongs to a different user')

    if expected_kind is not None and batch.kind != expected_kind:
        return None, error_response(status.HTTP_400_BAD_REQUEST, 'סוג קובץ היבוא אינו תואם', error_en='Import batch kind mismatch')

    return batch, None


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def init_import_batch(request):
    """Step 1 of the upload handshake: create a PENDING batch and hand its
    id to the frontend BEFORE any file is sent, so Stop/Status can target
    an explicit batch_id from the very start of the upload flow."""
    if not request.user.is_central_admin:
        return error_response(status.HTTP_403_FORBIDDEN, 'רק מנהל מרכזי יכול להעלות קבצים', error_en='Only Central Admin can upload files')

    kind = request.data.get('kind') or ImportBatch.Kind.MAIN
    if kind not in ImportBatch.Kind.values:
        return error_response(status.HTTP_400_BAD_REQUEST, 'סוג קובץ לא תקין', error_en='Invalid upload kind')

    batch = ImportBatch.objects.create(
        uploaded_by=request.user,
        kind=kind,
        status=ImportBatch.Status.PENDING,
    )

    return Response({
        'batch_id': batch.id,
        'status': batch.status,
    }, status=status.HTTP_201_CREATED)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_import_batch_status(request, batch_id):
    batch, error = _get_owned_batch_or_error(request, batch_id)
    if error:
        return error

    return Response(ImportBatchSerializer(batch).data, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def stop_import_batch(request, batch_id):
    batch, error = _get_owned_batch_or_error(request, batch_id)
    if error:
        return error

    try:
        batch = request_batch_stop(batch.id)
    except ImportBatchStateError as blocked:
        return error_response(status.HTTP_409_CONFLICT, 'ניתן לעצור רק קובץ שנמצא כרגע בעיבוד', error_en='Only a batch currently processing can be stopped', status=blocked.batch.status)

    return Response(ImportBatchSerializer(batch).data, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def stop_and_delete_import_batch(request, batch_id):
    batch, error = _get_owned_batch_or_error(request, batch_id)
    if error:
        return error

    try:
        batch = request_batch_stop_and_delete(batch.id)
    except ImportBatchStateError as blocked:
        return error_response(status.HTTP_409_CONFLICT, 'לא ניתן לעצור ולמחוק קובץ שכבר הסתיים. השתמשו בפעולת המחיקה הרגילה.', error_en='Cannot stop-and-delete a batch that already finished. Use the plain delete action.', status=blocked.batch.status)

    return Response(ImportBatchSerializer(batch).data, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def delete_import_batch(request, batch_id):
    batch, error = _get_owned_batch_or_error(request, batch_id)
    if error:
        return error

    try:
        batch = delete_batch_created_students(batch.id)
    except ImportBatchStateError as blocked:
        return error_response(status.HTTP_409_CONFLICT, 'ניתן למחוק סטודנטים רק לאחר שההעלאה הסתיימה או נעצרה', error_en='Students can only be deleted once the upload has finished or stopped', status=blocked.batch.status)

    return Response(ImportBatchSerializer(batch).data, status=status.HTTP_200_OK)


MAX_UPLOAD_FILE_SIZE_BYTES = int(os.getenv('MAX_UPLOAD_FILE_SIZE_MB', '25')) * 1024 * 1024


def _validate_upload_file_or_error(uploaded_file):
    """
    Shared main/additions upload validation (G3-21):
    1. extension allow-list (unchanged - kept as the fast first check)
    2. explicit byte-size ceiling, checked from Django's UploadedFile.size
       without reading the file into memory
    3. actual content validation - attempts to open the workbook with
       pandas/openpyxl; a corrupt file, a renamed non-Excel file, or any
       other structurally invalid upload fails HERE with a clean 400,
       never as an unhandled exception deeper in the row-by-row import
       loop (and never leaking a pandas/openpyxl stack trace to the
       client - that detail stays server-side via traceback.print_exc()).

    Returns (excel_file, error_response). On success error_response is
    None and excel_file is the already-opened pd.ExcelFile, reused by the
    caller instead of re-opening the upload a second time.
    """
    if not uploaded_file.name.lower().endswith(('.xlsx', '.xls')):
        return None, error_response(status.HTTP_400_BAD_REQUEST, 'סוג קובץ לא נתמך. נא להעלות קובץ Excel (.xlsx או .xls)', error_en='Unsupported file type. Please upload an Excel file (.xlsx or .xls)')

    if uploaded_file.size is not None and uploaded_file.size > MAX_UPLOAD_FILE_SIZE_BYTES:
        max_mb = MAX_UPLOAD_FILE_SIZE_BYTES // (1024 * 1024)
        return None, error_response(status.HTTP_400_BAD_REQUEST, f'הקובץ גדול מדי. הגודל המרבי המותר הוא {max_mb}MB.', error_en=f'File is too large. Maximum allowed size is {max_mb}MB.')

    if uploaded_file.size == 0:
        return None, error_response(status.HTTP_400_BAD_REQUEST, 'הקובץ ריק', error_en='The uploaded file is empty')

    try:
        excel_file = pd.ExcelFile(uploaded_file)
        # Touch sheet_names now (cheap - it's already parsed the workbook's
        # central directory/structure to open it) so a workbook that
        # "opens" but has no readable sheet structure also fails here
        # rather than later.
        _ = excel_file.sheet_names
    except Exception:
        # Server-side only - never returned to the client (no stack trace
        # leak; see docstring above).
        traceback.print_exc()
        return None, error_response(status.HTTP_400_BAD_REQUEST, 'לא ניתן לקרוא את הקובץ - ודאו שמדובר בקובץ Excel תקין (.xlsx/.xls) ולא פגום.', error_en='Could not read the file - please make sure it is a valid, non-corrupted Excel file (.xlsx/.xls).')

    return excel_file, None


def _claim_upload_batch_or_error(request, uploaded_file, expected_kind):
    """
    Shared upload-request handling after file validation: requires a
    batch_id, checks ownership/kind and claims the PENDING batch for
    processing. Returns (batch, None) or (None, error_response).
    """
    batch_id = request.data.get('batch_id')
    if not batch_id:
        return None, error_response(status.HTTP_400_BAD_REQUEST, 'נדרש batch_id. יש לאתחל את ההעלאה תחילה.', error_en='batch_id is required. Initialize the upload first.')

    batch, error = _get_owned_batch_or_error(request, batch_id, expected_kind=expected_kind)
    if error:
        return None, error

    try:
        batch = claim_pending_batch(batch.id, uploaded_file.name)
    except ImportBatchStateError as blocked:
        return None, error_response(status.HTTP_409_CONFLICT, 'קובץ יבוא זה כבר עובד או הסתיים', error_en='This import batch has already been processed', status=blocked.batch.status)

    return batch, None


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def upload_excel(request):
    """
    Upload status report Excel (עוזבים / מעברים / נכנסים חדשים / נשארים).
    See api.domains.imports.ingestion.run_status_report_import for the
    import rules.
    """
    if not request.user.is_central_admin:
        return error_response(status.HTTP_403_FORBIDDEN, 'רק מנהל מרכזי יכול להעלות קבצים', error_en='Only Central Admin can upload files')

    if 'file' not in request.FILES:
        return error_response(status.HTTP_400_BAD_REQUEST, 'לא נבחר קובץ', error_en='No file selected')

    uploaded_file = request.FILES['file']

    # G3-21: size/content validation, before anything else touches this
    # upload or the ImportBatch's state - see _validate_upload_file_or_error.
    excel_file, upload_error = _validate_upload_file_or_error(uploaded_file)
    if upload_error:
        return upload_error

    validate_gender_model_for_housing_import()

    batch, error = _claim_upload_batch_or_error(request, uploaded_file, ImportBatch.Kind.MAIN)
    if error:
        return error

    try:
        result_payload = run_status_report_import(batch, excel_file)
    except Exception as e:
        # G3-21: the stack trace stays server-side - never echoed back to
        # the client.
        return failure_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            f'שגיאה בעיבוד דוח השיבוץ: {str(e)}',
            error_en=f'Error processing status report: {str(e)}',
        )

    return Response(result_payload, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def upload_additions_excel(request):
    """
    Upload the additions ('מתווספים') Excel file. See
    api.domains.imports.ingestion.run_additions_import for the import rules.
    """
    if not request.user.is_central_admin:
        return error_response(status.HTTP_403_FORBIDDEN, 'רק מנהל מרכזי יכול להעלות קבצים', error_en='Only Central Admin can upload files')

    if 'file' not in request.FILES:
        return error_response(status.HTTP_400_BAD_REQUEST, 'לא נבחר קובץ', error_en='No file selected')

    uploaded_file = request.FILES['file']

    # G3-21: size/content validation, before anything else touches this
    # upload or the ImportBatch's state - see _validate_upload_file_or_error.
    excel_file, upload_error = _validate_upload_file_or_error(uploaded_file)
    if upload_error:
        return upload_error

    validate_gender_model_for_housing_import()

    batch, error = _claim_upload_batch_or_error(request, uploaded_file, ImportBatch.Kind.ADDITIONS)
    if error:
        return error

    try:
        result_payload = run_additions_import(batch, excel_file)
    except Exception as e:
        # G3-21: the stack trace stays server-side - never echoed back to
        # the client.
        return failure_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            f'שגיאה בעיבוד קובץ המתווספים: {str(e)}',
            error_en=f'Error processing additions file: {str(e)}',
        )

    return Response(result_payload, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_batches(request):
    if request.user.is_central_admin:
        batches = ImportBatch.objects.all()[:20]
    else:
        batch_ids = RegionInbox.objects.filter(
            region=request.user.region
        ).values_list('batch_id', flat=True)
        batches = ImportBatch.objects.filter(id__in=batch_ids)[:20]

    serializer = ImportBatchSerializer(batches, many=True)
    return Response({'batches': serializer.data})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def region_inbox(request):
    if request.user.is_central_admin:
        inbox_items = RegionInbox.objects.all()[:50]
    else:
        if not request.user.region:
            return error_response(status.HTTP_400_BAD_REQUEST, 'משתמש לא משויך לאזור', error_en='User not assigned to a region')
        inbox_items = RegionInbox.objects.filter(region=request.user.region)

    serializer = RegionInboxSerializer(inbox_items, many=True)
    return Response({'inbox': serializer.data})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def region_inbox_latest(request):
    if request.user.is_central_admin:
        return error_response(status.HTTP_400_BAD_REQUEST, 'מנהל מרכזי אינו מקבל הודעות תיבת דואר', error_en='Central admin does not receive inbox items')

    if not request.user.region:
        return error_response(status.HTTP_400_BAD_REQUEST, 'משתמש לא משויך לאזור', error_en='User not assigned to a region')

    inbox_item = RegionInbox.objects.filter(
        region=request.user.region,
        status__in=[RegionInbox.Status.PENDING, RegionInbox.Status.VIEWED]
    ).order_by('-created_at').first()

    if not inbox_item:
        return Response({
            'inbox': None,
            'message': 'אין הודעות חדשות'
        })

    serializer = RegionInboxSerializer(inbox_item)
    return Response({'inbox': serializer.data})


@api_view(['PUT'])
@permission_classes([IsAuthenticated])
def mark_inbox_viewed(request, inbox_id):
    try:
        inbox_item = RegionInbox.objects.get(id=inbox_id)
    except RegionInbox.DoesNotExist:
        return error_response(status.HTTP_404_NOT_FOUND, 'הודעה לא נמצאה')

    if not request.user.is_central_admin and inbox_item.region != request.user.region:
        return error_response(status.HTTP_403_FORBIDDEN, 'אין הרשאה לצפות בהודעה זו')

    if inbox_item.status == RegionInbox.Status.PENDING:
        inbox_item.status = RegionInbox.Status.VIEWED
        inbox_item.viewed_at = timezone.now()
        inbox_item.save()

    serializer = RegionInboxSerializer(inbox_item)
    return Response({'inbox': serializer.data})


@api_view(['PUT'])
@permission_classes([IsAuthenticated])
def mark_inbox_processed(request, inbox_id):
    try:
        inbox_item = RegionInbox.objects.get(id=inbox_id)
    except RegionInbox.DoesNotExist:
        return error_response(status.HTTP_404_NOT_FOUND, 'הודעה לא נמצאה')

    if not request.user.is_boss:
        return error_response(status.HTTP_403_FORBIDDEN, 'רק מנהל יכול לסמן הודעה כטופלה')

    if not request.user.is_central_admin and inbox_item.region != request.user.region:
        return error_response(status.HTTP_403_FORBIDDEN, 'אין הרשאה לעדכן הודעה זו')

    inbox_item.status = RegionInbox.Status.PROCESSED
    inbox_item.processed_at = timezone.now()
    inbox_item.save()

    serializer = RegionInboxSerializer(inbox_item)
    return Response({'inbox': serializer.data})
