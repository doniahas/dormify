"""Contracts of the upload-batch, Excel upload and region-inbox endpoints."""

import io

import pandas as pd
from django.core.files.uploadedfile import SimpleUploadedFile

from api.models import ImportBatch, RegionInbox
from api.serializers import ImportBatchSerializer, RegionInboxSerializer

from ._support import ContractTestCase, make_region, serializer_keys

BATCH_KEYS = serializer_keys(ImportBatchSerializer)
INBOX_KEYS = serializer_keys(RegionInboxSerializer)
XLSX = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'

UPLOAD_RESULT_KEYS = [
    'success', 'stopped', 'message', 'messageEn', 'batch_id', 'total_students', 'created', 'updated',
    'skipped', 'category_counts', 'region_breakdown', 'sheet_counts', 'skipped_by_reason', 'warnings', 'errors',
]
ADDITIONS_RESULT_KEYS = [
    'success', 'stopped', 'message', 'messageEn', 'batch_id', 'total_students', 'created', 'updated',
    'skipped', 'existing_category_preserved', 'housing_type_counts', 'region_breakdown', 'sheet_counts',
    'skipped_by_reason', 'warnings', 'errors',
]


def _workbook_bytes(rows, sheet_name):
    buffer = io.BytesIO()
    pd.DataFrame(rows).to_excel(buffer, index=False, sheet_name=sheet_name)
    return buffer.getvalue()


class ImportBatchContractTests(ContractTestCase):
    def _batch(self, status=ImportBatch.Status.PENDING, kind=ImportBatch.Kind.MAIN, user=None):
        return ImportBatch.objects.create(uploaded_by=user or self.admin, kind=kind, status=status)

    def test_init_bodies(self):
        admin = self.client_for(self.admin)
        response = admin.post('/api/upload/batches/init/', {'kind': 'additions'}, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        self.assertKeys(response.data, ['batch_id', 'status'])
        self.assertEqual(response.data['status'], 'pending')
        self.assertErrorBody(admin.post('/api/upload/batches/init/', {'kind': 'other'}, format='json'), 400,
                             'סוג קובץ לא תקין', error_en='Invalid upload kind')
        self.assertErrorBody(self.client_for(self.boss).post('/api/upload/batches/init/', {}, format='json'), 403,
                             'רק מנהל מרכזי יכול להעלות קבצים', error_en='Only Central Admin can upload files')

    def test_status_and_ownership_bodies(self):
        batch = self._batch()
        response = self.client_for(self.admin).get(f'/api/upload/batches/{batch.id}/status/')
        self.assertEqual(response.status_code, 200)
        self.assertKeys(response.data, BATCH_KEYS)
        self.assertEqual(response.data['region_breakdown'], [])
        self.assertErrorBody(self.client_for(self.admin).get('/api/upload/batches/999999/status/'), 404,
                             'קובץ יבוא לא נמצא', error_en='Import batch not found')
        self.assertErrorBody(self.client_for(self.boss).get(f'/api/upload/batches/{batch.id}/status/'), 403,
                             'רק מנהל מרכזי יכול לבצע פעולה זו', error_en='Only Central Admin can perform this action')
        other_admin_batch = self._batch(user=self.boss)
        self.assertErrorBody(self.client_for(self.admin).get(f'/api/upload/batches/{other_admin_batch.id}/status/'), 403,
                             'קובץ יבוא זה שייך למשתמש אחר', error_en='This import batch belongs to a different user')

    def test_lifecycle_transition_bodies(self):
        admin = self.client_for(self.admin)
        pending = self._batch()
        self.assertErrorBody(admin.post(f'/api/upload/batches/{pending.id}/stop/'), 409,
                             'ניתן לעצור רק קובץ שנמצא כרגע בעיבוד',
                             error_en='Only a batch currently processing can be stopped', status='pending')
        response = admin.post(f'/api/upload/batches/{pending.id}/stop-and-delete/')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertKeys(response.data, BATCH_KEYS)
        self.assertEqual(response.data['status'], 'stopped')
        self.assertEqual(response.data['result']['deletion']['deleted_count'], 0)

        processing = self._batch(status=ImportBatch.Status.PROCESSING)
        response = admin.post(f'/api/upload/batches/{processing.id}/stop/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['status'], 'cancellation_requested')
        self.assertErrorBody(admin.post(f'/api/upload/batches/{processing.id}/delete/'), 409,
                             'ניתן למחוק סטודנטים רק לאחר שההעלאה הסתיימה או נעצרה',
                             error_en='Students can only be deleted once the upload has finished or stopped',
                             status='cancellation_requested')
        done = self._batch(status=ImportBatch.Status.COMPLETED)
        self.assertErrorBody(admin.post(f'/api/upload/batches/{done.id}/stop-and-delete/'), 409,
                             'לא ניתן לעצור ולמחוק קובץ שכבר הסתיים. השתמשו בפעולת המחיקה הרגילה.',
                             error_en='Cannot stop-and-delete a batch that already finished. Use the plain delete action.',
                             status='completed')
        response = admin.post(f'/api/upload/batches/{done.id}/delete/')
        self.assertEqual(response.status_code, 200)
        self.assertKeys(response.data['result']['deletion'], ['requested', 'deleted_count', 'protected_count', 'protected_students', 'performed_at'])

    def test_upload_request_validation_bodies(self):
        admin = self.client_for(self.admin)
        self.assertErrorBody(admin.post('/api/upload/excel/', {}, format='multipart'), 400, 'לא נבחר קובץ', error_en='No file selected')
        self.assertErrorBody(self.client_for(self.boss).post('/api/upload/excel/', {}, format='multipart'), 403,
                             'רק מנהל מרכזי יכול להעלות קבצים', error_en='Only Central Admin can upload files')
        workbook = _workbook_bytes([{'ת"ז ישראלית': 'UP-1', 'שם פרטי': 'A', 'שם משפחה': 'B', 'תיאור סוג מגורים': 'רווקים'}], 'נכנסים חדשים')
        response = admin.post('/api/upload/excel/', {'file': SimpleUploadedFile('r.xlsx', workbook, content_type=XLSX)}, format='multipart')
        self.assertErrorBody(response, 400, 'נדרש batch_id. יש לאתחל את ההעלאה תחילה.',
                             error_en='batch_id is required. Initialize the upload first.')
        wrong_kind = self._batch(kind=ImportBatch.Kind.ADDITIONS)
        response = admin.post('/api/upload/excel/', {
            'file': SimpleUploadedFile('r.xlsx', workbook, content_type=XLSX), 'batch_id': wrong_kind.id,
        }, format='multipart')
        self.assertErrorBody(response, 400, 'סוג קובץ היבוא אינו תואם', error_en='Import batch kind mismatch')
        used = self._batch(status=ImportBatch.Status.COMPLETED)
        response = admin.post('/api/upload/excel/', {
            'file': SimpleUploadedFile('r.xlsx', workbook, content_type=XLSX), 'batch_id': used.id,
        }, format='multipart')
        self.assertErrorBody(response, 409, 'קובץ יבוא זה כבר עובד או הסתיים',
                             error_en='This import batch has already been processed', status='completed')

    def test_upload_success_bodies(self):
        admin = self.client_for(self.admin)
        batch = self._batch()
        workbook = _workbook_bytes([{'ת"ז ישראלית': 'UP-2', 'שם פרטי': 'A', 'שם משפחה': 'B', 'תיאור סוג מגורים': 'רווקים'}], 'נכנסים חדשים')
        response = admin.post('/api/upload/excel/', {
            'file': SimpleUploadedFile('r.xlsx', workbook, content_type=XLSX), 'batch_id': batch.id,
        }, format='multipart')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertKeys(response.data, UPLOAD_RESULT_KEYS)
        self.assertEqual((response.data['created'], response.data['stopped'], response.data['batch_id']), (1, False, batch.id))
        self.assertKeys(response.data['category_counts'], ['new', 'continuing', 'transfer', 'leaving'])

        additions = self._batch(kind=ImportBatch.Kind.ADDITIONS)
        workbook = _workbook_bytes([{'ת"ז ישראלית': 'UP-3', 'שם פרטי': 'A', 'שם משפחה': 'B'}], 'תוספות')
        response = admin.post('/api/upload/additions-excel/', {
            'file': SimpleUploadedFile('a.xlsx', workbook, content_type=XLSX), 'batch_id': additions.id,
        }, format='multipart')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertKeys(response.data, ADDITIONS_RESULT_KEYS)
        self.assertKeys(response.data['housing_type_counts'], ['single_male', 'single_female', 'single_mixed', 'couple', 'family', 'unknown'])
        self.assertEqual(response.data['skipped_by_reason'], {'non_positive_decision': 1})

    def test_batches_list_body(self):
        self._batch()
        response = self.client_for(self.admin).get('/api/batches/')
        self.assertKeys(response.data, ['batches'])
        self.assertKeys(response.data['batches'][0], BATCH_KEYS)
        self.assertEqual(self.client_for(self.boss).get('/api/batches/').data, {'batches': []})


class RegionInboxContractTests(ContractTestCase):
    def _inbox(self, region=None, status=RegionInbox.Status.PENDING):
        batch = ImportBatch.objects.create(uploaded_by=self.admin, status=ImportBatch.Status.COMPLETED)
        return RegionInbox.objects.create(region=region or self.region, batch=batch, students_count=3, status=status)

    def test_inbox_list_and_latest_bodies(self):
        boss = self.client_for(self.boss)
        self.assertEqual(boss.get('/api/inbox/latest/').data, {'inbox': None, 'message': 'אין הודעות חדשות'})
        item = self._inbox()
        response = boss.get('/api/inbox/latest/')
        self.assertKeys(response.data, ['inbox'])
        self.assertKeys(response.data['inbox'], INBOX_KEYS)
        self.assertEqual(response.data['inbox']['id'], item.id)
        response = boss.get('/api/inbox/')
        self.assertKeys(response.data, ['inbox'])
        self.assertKeys(response.data['inbox'][0], INBOX_KEYS)
        self.assertErrorBody(self.client_for(self.admin).get('/api/inbox/latest/'), 400,
                             'מנהל מרכזי אינו מקבל הודעות תיבת דואר', error_en='Central admin does not receive inbox items')

    def test_mark_viewed_and_processed_bodies(self):
        item = self._inbox()
        employee = self.client_for(self.employee)
        self.assertErrorBody(employee.put('/api/inbox/999999/viewed/'), 404, 'הודעה לא נמצאה')
        response = employee.put(f'/api/inbox/{item.id}/viewed/')
        self.assertEqual(response.status_code, 200)
        self.assertKeys(response.data, ['inbox'])
        self.assertEqual(response.data['inbox']['status'], 'viewed')
        self.assertErrorBody(employee.put(f'/api/inbox/{item.id}/processed/'), 403, 'רק מנהל יכול לסמן הודעה כטופלה')
        other = make_region('Contract Other Inbox')
        foreign = self._inbox(region=other)
        self.assertErrorBody(self.client_for(self.boss).put(f'/api/inbox/{foreign.id}/processed/'), 403, 'אין הרשאה לעדכן הודעה זו')
        self.assertErrorBody(employee.put(f'/api/inbox/{foreign.id}/viewed/'), 403, 'אין הרשאה לצפות בהודעה זו')
        response = self.client_for(self.boss).put(f'/api/inbox/{item.id}/processed/')
        self.assertEqual(response.data['inbox']['status'], 'processed')
