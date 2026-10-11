"""Direct tests for api.domains.imports.batches, .ingestion and the additions parsing helpers."""

import io
from unittest.mock import patch

import pandas as pd
from django.test import TestCase

from api.domains.imports import batches, ingestion
from api.domains.imports.parsing import additions_housing_bucket, normalize_additions_housing_type
from api.models import ImportBatch, RegionInbox, Student

from ._fixtures import (
    assign,
    make_central_admin,
    make_dorm,
    make_full_stack,
    make_region,
    make_student,
)


def _batch(admin, status=ImportBatch.Status.PENDING, kind=ImportBatch.Kind.MAIN):
    return ImportBatch.objects.create(uploaded_by=admin, kind=kind, status=status)


class BatchLifecycleTests(TestCase):
    def setUp(self):
        self.admin = make_central_admin()

    def test_claim_pending_batch_marks_processing_with_filename(self):
        batch = _batch(self.admin)
        claimed = batches.claim_pending_batch(batch.id, 'roster.xlsx')
        self.assertEqual(claimed.status, ImportBatch.Status.PROCESSING)
        self.assertEqual(claimed.filename, 'roster.xlsx')
        self.assertIsNotNone(claimed.started_at)

    def test_claim_refuses_a_batch_that_left_pending(self):
        batch = _batch(self.admin, status=ImportBatch.Status.PROCESSING)
        with self.assertRaises(batches.ImportBatchStateError) as raised:
            batches.claim_pending_batch(batch.id, 'again.xlsx')
        self.assertEqual(raised.exception.batch.status, ImportBatch.Status.PROCESSING)

    def test_request_stop_only_for_processing(self):
        processing = _batch(self.admin, status=ImportBatch.Status.PROCESSING)
        self.assertEqual(batches.request_batch_stop(processing.id).status, ImportBatch.Status.CANCELLATION_REQUESTED)

        completed = _batch(self.admin, status=ImportBatch.Status.COMPLETED)
        with self.assertRaises(batches.ImportBatchStateError):
            batches.request_batch_stop(completed.id)

    def test_stop_and_delete_resolves_pending_immediately(self):
        batch = batches.request_batch_stop_and_delete(_batch(self.admin).id)
        self.assertEqual(batch.status, ImportBatch.Status.STOPPED)
        self.assertIsNotNone(batch.finished_at)
        self.assertEqual(batch.result['deletion']['deleted_count'], 0)
        self.assertTrue(batch.result['stopped'])

    def test_stop_and_delete_flags_a_running_batch(self):
        for status in (ImportBatch.Status.PROCESSING, ImportBatch.Status.CANCELLATION_REQUESTED):
            batch = batches.request_batch_stop_and_delete(_batch(self.admin, status=status).id)
            self.assertEqual(batch.status, ImportBatch.Status.STOP_AND_DELETE_REQUESTED)

    def test_stop_and_delete_refuses_a_finished_batch(self):
        finished = _batch(self.admin, status=ImportBatch.Status.COMPLETED)
        with self.assertRaises(batches.ImportBatchStateError):
            batches.request_batch_stop_and_delete(finished.id)

    def test_delete_created_students_skips_protected_rows_and_records_summary(self):
        region = make_region('Batch Region')
        dorm, _b, _a, room = make_full_stack(region)
        batch = _batch(self.admin, status=ImportBatch.Status.COMPLETED)
        created = make_student(dorm, 'CREATED-1', batch=batch, created_in_batch=batch)
        placed = make_student(dorm, 'PLACED-1', batch=batch, created_in_batch=batch)
        assign(placed, room)
        updated_only = make_student(dorm, 'UPDATED-1', batch=batch)

        batch = batches.delete_batch_created_students(batch.id)

        deletion = batch.result['deletion']
        self.assertEqual(deletion['deleted_count'], 1)
        self.assertEqual(deletion['protected_count'], 1)
        self.assertEqual(deletion['protected_students'], [{'id': placed.id, 'student_id': 'PLACED-1'}])
        self.assertFalse(Student.objects.filter(pk=created.pk).exists())
        self.assertTrue(Student.objects.filter(pk=placed.pk).exists())
        self.assertTrue(Student.objects.filter(pk=updated_only.pk).exists())

    def test_delete_created_students_refuses_a_running_batch(self):
        running = _batch(self.admin, status=ImportBatch.Status.PROCESSING)
        with self.assertRaises(batches.ImportBatchStateError):
            batches.delete_batch_created_students(running.id)


def _workbook(rows, sheet_name='נכנסים חדשים'):
    buffer = io.BytesIO()
    pd.DataFrame(rows).to_excel(buffer, index=False, sheet_name=sheet_name)
    buffer.seek(0)
    return pd.ExcelFile(buffer)


class StatusReportImportTests(TestCase):
    def setUp(self):
        self.admin = make_central_admin()

    def test_creates_students_and_completes_the_batch(self):
        batch = batches.claim_pending_batch(_batch(self.admin).id, 'roster.xlsx')
        workbook = _workbook([
            {'ת"ז ישראלית': 'ING-1', 'שם פרטי': 'A', 'שם משפחה': 'One', 'תיאור סוג מגורים': 'רווקות'},
            {'ת"ז ישראלית': 'ING-2', 'שם פרטי': 'B', 'שם משפחה': 'Two', 'תיאור סוג מגורים': 'רווקים'},
            {'ת"ז ישראלית': '', 'שם פרטי': 'C', 'שם משפחה': 'Three', 'תיאור סוג מגורים': 'רווקים'},
        ])

        payload = ingestion.run_status_report_import(batch, workbook)

        self.assertTrue(payload['success'])
        self.assertFalse(payload['stopped'])
        self.assertEqual((payload['created'], payload['updated'], payload['skipped']), (2, 0, 1))
        self.assertEqual(payload['skipped_by_reason'], {'missing_student_id': 1})
        self.assertEqual(payload['category_counts']['new'], 2)
        self.assertEqual(payload['sheet_counts']['נכנסים חדשים']['rows'], 3)
        self.assertEqual(
            set(Student.objects.filter(created_in_batch=batch).values_list('student_id', flat=True)),
            {'ING-1', 'ING-2'},
        )

        batch.refresh_from_db()
        self.assertEqual(batch.status, ImportBatch.Status.COMPLETED)
        self.assertEqual((batch.total_rows, batch.processed_rows, batch.total_students), (3, 3, 2))
        self.assertEqual(batch.result['created'], 2)

    def test_existing_student_is_updated_without_clearing_values(self):
        region = make_region('Ingest Region')
        dorm = make_dorm(region, name='Ingest Dorm', code='9001')
        existing = make_student(dorm, 'ING-EXISTING', city='Haifa',
                                category=Student.StudentCategory.CONTINUING)
        batch = batches.claim_pending_batch(_batch(self.admin).id, 'roster.xlsx')
        workbook = _workbook([
            {'ת"ז ישראלית': 'ING-EXISTING', 'שם פרטי': 'Renamed', 'שם משפחה': 'Same', 'תיאור סוג מגורים': 'רווקים'},
        ])

        payload = ingestion.run_status_report_import(batch, workbook)

        self.assertEqual((payload['created'], payload['updated']), (0, 1))
        existing.refresh_from_db()
        self.assertEqual(existing.first_name, 'Renamed')
        self.assertEqual(existing.city, 'Haifa')
        self.assertEqual(existing.accepted_dorm_type, dorm)
        self.assertEqual(existing.batch, batch)
        self.assertEqual(existing.category, Student.StudentCategory.NEW)

    def test_sheet_missing_required_columns_is_skipped_whole(self):
        batch = batches.claim_pending_batch(_batch(self.admin).id, 'roster.xlsx')
        workbook = _workbook([{'שם פרטי': 'A', 'שם משפחה': 'One'}, {'שם פרטי': 'B', 'שם משפחה': 'Two'}])

        payload = ingestion.run_status_report_import(batch, workbook)

        self.assertEqual(payload['skipped'], 2)
        self.assertEqual(payload['skipped_by_reason'], {'missing_required_columns': 2})
        self.assertEqual(len(payload['errors']), 1)
        self.assertEqual(Student.objects.count(), 0)

    def test_stop_request_between_rows_stops_and_deletes_when_asked(self):
        batch = batches.claim_pending_batch(_batch(self.admin).id, 'roster.xlsx')
        workbook = _workbook([
            {'ת"ז ישראלית': 'STOP-1', 'שם פרטי': 'A', 'שם משפחה': 'One', 'תיאור סוג מגורים': 'רווקים'},
            {'ת"ז ישראלית': 'STOP-2', 'שם פרטי': 'B', 'שם משפחה': 'Two', 'תיאור סוג מגורים': 'רווקים'},
        ])
        original_row_done = ingestion._ImportRun.row_done

        def stop_after_first_row(run):
            ImportBatch.objects.filter(pk=run.batch.id).update(
                status=ImportBatch.Status.STOP_AND_DELETE_REQUESTED,
            )
            return original_row_done(run)

        with patch.object(ingestion._ImportRun, 'row_done', stop_after_first_row):
            payload = ingestion.run_status_report_import(batch, workbook)

        self.assertTrue(payload['stopped'])
        self.assertEqual(payload['created'], 1)
        self.assertEqual(payload['deletion']['deleted_count'], 1)
        batch.refresh_from_db()
        self.assertEqual(batch.status, ImportBatch.Status.STOPPED)
        self.assertEqual(batch.processed_rows, 1)
        self.assertFalse(Student.objects.filter(student_id__startswith='STOP-').exists())

    def test_unexpected_failure_marks_the_batch_failed_and_propagates(self):
        batch = batches.claim_pending_batch(_batch(self.admin).id, 'roster.xlsx')

        class BrokenWorkbook:
            @property
            def sheet_names(self):
                raise RuntimeError('corrupt workbook')

        with self.assertRaises(RuntimeError):
            ingestion.run_status_report_import(batch, BrokenWorkbook())

        batch.refresh_from_db()
        self.assertEqual(batch.status, ImportBatch.Status.FAILED)
        self.assertEqual(batch.error_message, 'corrupt workbook')
        self.assertIsNotNone(batch.finished_at)


class AdditionsImportTests(TestCase):
    def setUp(self):
        self.admin = make_central_admin()
        self.region = make_region('Additions Region')
        self.dorm = make_dorm(self.region, name='Additions Dorm', code='9108')
        make_full_stack(self.region, dorm=self.dorm)

    def test_positive_decisions_create_new_students_and_notify_the_region(self):
        batch = batches.claim_pending_batch(
            _batch(self.admin, kind=ImportBatch.Kind.ADDITIONS).id, 'additions.xlsx',
        )
        workbook = _workbook([
            {
                'ת"ז ישראלית': 'ADD-1', 'שם פרטי': 'A', 'שם משפחה': 'One',
                'החלטה-תאור סוג מגורים': 'רווקים', 'החלטה-סוג מגורים של הדייר': 'Z1',
                'החלטה-החלטת מעונות - תאור': 'החלטה חיובית', 'החלטה-תוכן החלטה – מעונות': '9108',
            },
            {
                'ת"ז ישראלית': 'ADD-2', 'שם פרטי': 'B', 'שם משפחה': 'Two',
                'החלטה-תאור סוג מגורים': 'רווקים', 'החלטה-סוג מגורים של הדייר': 'Z1',
                'החלטה-החלטת מעונות - תאור': 'החלטה שלילית', 'החלטה-תוכן החלטה – מעונות': '9108',
            },
        ], sheet_name='תוספות')

        payload = ingestion.run_additions_import(batch, workbook)

        self.assertEqual(payload['created'], 1)
        self.assertEqual(payload['sheet_counts']['תוספות']['non_positive_decisions'], 1)
        self.assertEqual(payload['housing_type_counts']['single_male'], 1)
        student = Student.objects.get(student_id='ADD-1')
        self.assertEqual(student.category, Student.StudentCategory.NEW)
        self.assertEqual(student.accepted_dorm_type, self.dorm)
        self.assertEqual(payload['region_breakdown'], [{
            'region_id': self.region.id, 'region_name': self.region.name,
            'count': 1, 'created': 1, 'updated': 0,
        }])
        inbox = RegionInbox.objects.get(region=self.region)
        self.assertEqual(inbox.batch_id, batch.id)
        self.assertEqual(inbox.status, RegionInbox.Status.PENDING)
        self.assertEqual(inbox.students_count, 1)

    def test_existing_student_keeps_category_and_assignment(self):
        existing = make_student(self.dorm, 'ADD-EXISTING', category=Student.StudentCategory.CONTINUING)
        batch = batches.claim_pending_batch(
            _batch(self.admin, kind=ImportBatch.Kind.ADDITIONS).id, 'additions.xlsx',
        )
        workbook = _workbook([{
            'ת"ז ישראלית': 'ADD-EXISTING', 'שם פרטי': 'Renamed', 'שם משפחה': 'Kept',
            'החלטה-תאור סוג מגורים': 'רווקים', 'החלטה-סוג מגורים של הדייר': 'Z1',
            'החלטה-החלטת מעונות - תאור': 'החלטה חיובית', 'החלטה-תוכן החלטה – מעונות': '9108',
        }], sheet_name='תוספות')

        payload = ingestion.run_additions_import(batch, workbook)

        self.assertEqual((payload['created'], payload['updated']), (0, 1))
        self.assertEqual(payload['existing_category_preserved'], 1)
        existing.refresh_from_db()
        self.assertEqual(existing.category, Student.StudentCategory.CONTINUING)
        self.assertEqual(existing.first_name, 'Renamed')


class AdditionsParsingTests(TestCase):
    def test_housing_buckets(self):
        self.assertEqual(additions_housing_bucket(Student.HousingType.FAMILY), 'family')
        self.assertEqual(additions_housing_bucket(Student.HousingType.COUPLE), 'couple')
        self.assertEqual(additions_housing_bucket(Student.HousingType.SINGLE_IN_APARTMENT), 'single_mixed')
        self.assertEqual(additions_housing_bucket(Student.HousingType.SINGLE_FEMALE), 'single_female')
        self.assertEqual(additions_housing_bucket(Student.HousingType.SINGLE_MALE), 'single_male')
        self.assertEqual(additions_housing_bucket(''), 'unknown')

    def test_normalize_additions_housing_type_uses_decision_columns(self):
        row = pd.Series({'החלטה-תאור סוג מגורים': 'רווקות', 'החלטה-סוג מגורים של הדייר': 'Z2'})
        self.assertEqual(normalize_additions_housing_type(row), Student.HousingType.SINGLE_FEMALE)
