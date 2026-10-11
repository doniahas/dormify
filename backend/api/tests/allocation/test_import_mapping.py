import threading
import time
from unittest.mock import patch

from django.test import TestCase, TransactionTestCase
from rest_framework.test import APIClient

from api.models import (
    Region, Student, DormType, Building, Apartment, Room, Bed, ImportBatch,
)

from ._support import _make_central_admin


# ---------------------------------------------------------------------------
# Priority vs. accessibility: is_priority must come only from
# special_status_1..4, never from accessibility/medical import data.
# ---------------------------------------------------------------------------

class StudentPriorityImportTest(TestCase):
    """
    Regression tests for the separation of accessibility from is_priority
    in the Excel importer (api/views.py: build_student_payload_from_row,
    is_accessibility_priority, priority_fields_from_special_statuses).

    Accessible students are still allocated manually by the dorm office, so
    accessibility/medical columns must keep being read and parsed by the
    importer — they must simply never set is_priority, feed the solver's
    priorityFirst score, affect building-179 exclusivity, or influence
    priority-clustering.
    """

    def _make_row(self, **overrides):
        import pandas as pd

        values = {
            'ת"ז ישראלית': overrides.pop('student_id', 'IMP1'),
            'שם פרטי': overrides.pop('first_name', 'Test'),
            'שם משפחה': overrides.pop('last_name', 'Student'),
            'תיאור סוג מגורים': overrides.pop('housing_type', 'רווקות'),
        }

        alias_to_header = {
            'accessibility_flag': 'החלטה-זקוק להנגשה',
            'disability_percent': '%נכות',
            'medical_reason': 'סיבה רפואית מאושרת מרופאת הטכניון',
            'special_status_1': 'תאור סטטוס מיוחד1',
            'special_status_2': 'תאור סטטוס מיוחד2',
            'special_status_3': 'תאור סטטוס מיוחד3',
            'special_status_4': 'תאור סטטוס מיוחד4',
        }
        for key, header in alias_to_header.items():
            if key in overrides:
                values[header] = overrides.pop(key)

        assert not overrides, f"Unrecognized row overrides: {overrides}"
        return pd.Series(values)

    # ------------------------------------------------------------------
    # 1. Accessibility data is still imported and preserved.
    # ------------------------------------------------------------------

    def test_accessibility_data_still_parsed_and_preserved(self):
        """
        is_accessibility_priority still reads and recognizes
        accessibility_flag / disability_percent / medical_reason from the
        Excel row exactly as before — the columns are not removed from the
        importer — even though a student with only this data is not made
        priority (see test 2 below).
        """
        from api.views import is_accessibility_priority

        row = self._make_row(
            student_id='ACC_IMP1',
            accessibility_flag='כן',
            disability_percent='40',
            medical_reason='מצב רפואי מאושר',
        )
        self.assertTrue(is_accessibility_priority(row))

        row_medical_only = self._make_row(
            student_id='ACC_IMP2',
            medical_reason='מצב רפואי מאושר',
        )
        self.assertTrue(is_accessibility_priority(row_medical_only))

        row_none = self._make_row(student_id='ACC_IMP3')
        self.assertFalse(is_accessibility_priority(row_none))

    # ------------------------------------------------------------------
    # 1b. Accessibility values are actually persisted and retrievable
    #     after import (not merely computed and discarded).
    # ------------------------------------------------------------------

    def test_accessibility_values_persisted_and_retrievable_after_import(self):
        """
        Import a row carrying accessibility_flag/disability_percent/
        medical_reason, reload the Student from the database, and confirm
        all three values are still there — proving this data is genuinely
        stored (Student.accessibility_flag/disability_percent/
        medical_reason), not just computed and thrown away, while
        is_priority/priority_reason remain untouched by it. Also confirm
        the fields are exposed through StudentSerializer.
        """
        from decimal import Decimal
        from api.views import build_student_payload_from_row
        from api.serializers import StudentSerializer

        row = self._make_row(
            student_id='ACC_PERSIST1',
            accessibility_flag='כן',
            disability_percent='40',
            medical_reason='מצב רפואי מאושר',
        )
        payload = build_student_payload_from_row(row)
        student = Student.objects.create(**payload)

        reloaded = Student.objects.get(pk=student.pk)
        self.assertTrue(reloaded.accessibility_flag)
        self.assertEqual(reloaded.disability_percent, Decimal('40'))
        self.assertEqual(reloaded.medical_reason, 'מצב רפואי מאושר')

        # Separation from priority must hold even though the data is stored.
        self.assertFalse(reloaded.is_priority)
        self.assertEqual(reloaded.priority_reason, '')

        serialized = StudentSerializer(reloaded).data
        self.assertTrue(serialized['accessibility_flag'])
        self.assertEqual(Decimal(str(serialized['disability_percent'])), Decimal('40'))
        self.assertEqual(serialized['medical_reason'], 'מצב רפואי מאושר')

    # ------------------------------------------------------------------
    # 2. Accessibility alone does not create priority.
    # ------------------------------------------------------------------

    def test_accessibility_alone_does_not_create_priority(self):
        """A row with accessibility/medical data but no special_status must
        import as is_priority=False with an empty priority_reason."""
        from api.views import build_student_payload_from_row

        row = self._make_row(
            student_id='ACC_NOPRI',
            accessibility_flag='כן',
            disability_percent='100',
            medical_reason='מצב רפואי מאושר',
        )
        payload = build_student_payload_from_row(row)

        self.assertFalse(payload['is_priority'])
        self.assertEqual(payload['priority_reason'], '')

    # ------------------------------------------------------------------
    # 3. Any non-empty special-status field creates priority.
    # ------------------------------------------------------------------

    def test_any_non_empty_special_status_creates_priority(self):
        """Any single non-empty special_status_1..4 field must set
        is_priority=True and populate priority_reason, with no
        accessibility data present at all."""
        from api.views import build_student_payload_from_row

        row = self._make_row(student_id='PRI_STATUS1', special_status_1='הסמכה')
        payload = build_student_payload_from_row(row)
        self.assertTrue(payload['is_priority'])
        self.assertEqual(payload['priority_reason'], 'הסמכה')

        row2 = self._make_row(student_id='PRI_STATUS2', special_status_3='אנייר')
        payload2 = build_student_payload_from_row(row2)
        self.assertTrue(payload2['is_priority'])
        self.assertEqual(payload2['priority_reason'], 'אנייר')

        row3 = self._make_row(
            student_id='PRI_STATUS3',
            special_status_1='הסמכה',
            special_status_2='אנייר',
        )
        payload3 = build_student_payload_from_row(row3)
        self.assertTrue(payload3['is_priority'])
        self.assertEqual(payload3['priority_reason'], 'הסמכה | אנייר')

        row_none = self._make_row(student_id='NO_STATUS')
        payload_none = build_student_payload_from_row(row_none)
        self.assertFalse(payload_none['is_priority'])
        self.assertEqual(payload_none['priority_reason'], '')

    # ------------------------------------------------------------------
    # 4. Existing priority allocation behavior still works end-to-end:
    #    an imported, special-status-derived priority student is still
    #    preferred by the solver's priorityFirst rule, while an imported
    #    accessibility-only student is not.
    # ------------------------------------------------------------------

    def test_imported_special_status_priority_still_wins_allocation(self):
        """
        Build two students purely through the real importer
        (build_student_payload_from_row): one with a special_status (thus
        is_priority=True) and one with only accessibility data (thus
        is_priority=False). With capacity for only one of two candidates,
        priorityFirst must still favor the special-status student —
        proving the solver's existing priority behavior is unaffected by
        this import-layer change.
        """
        from api.views import build_student_payload_from_row
        from allocation.solver import run_improved_ortools_allocation

        dorm = DormType.objects.create(name='ImportPriorityDorm')
        building = Building.objects.create(number=1, dorm_type=dorm)
        apartment = Apartment.objects.create(
            building=building,
            number='1',
            category=Apartment.Category.FEMALE,
            apartment_type=Apartment.ApartmentType.SINGLE,
            room_count=1,
        )
        room = Room.objects.create(apartment=apartment, name='A', capacity=1)
        Bed.objects.create(room=room, label='1')

        priority_row = self._make_row(
            student_id='IMPPRI1', special_status_1='הסמכה',
        )
        priority_payload = build_student_payload_from_row(priority_row)
        priority_student = Student.objects.create(**priority_payload)

        accessibility_row = self._make_row(
            student_id='IMPACC1',
            accessibility_flag='כן',
            medical_reason='מצב רפואי מאושר',
        )
        accessibility_payload = build_student_payload_from_row(accessibility_row)
        accessibility_student = Student.objects.create(**accessibility_payload)

        self.assertTrue(priority_student.is_priority)
        self.assertFalse(accessibility_student.is_priority)

        patcher = patch('allocation.solver.close_old_connections')
        patcher.start()
        self.addCleanup(patcher.stop)

        config = {
            'sameGender': {'enabled': True, 'strict': True, 'critical': True, 'weight': 0},
            'priorityFirst': {'enabled': True, 'strict': True, 'critical': True, 'weight': 0},
        }
        result = run_improved_ortools_allocation(
            [priority_student, accessibility_student],
            [room],
            config,
        )

        assigned_ids = {item['student_db_id'] for item in result['proposed_assignments']}
        self.assertIn(priority_student.id, assigned_ids)
        self.assertNotIn(accessibility_student.id, assigned_ids)


# ---------------------------------------------------------------------------
# Anir (אנייר) upload/import mapping: the Excel column that sets the marker.
#
# Solver-side eligibility/Building-179 behavior for this marker is covered
# separately by Building179AutomaticAllocationTest, which uses the
# confirmed-correct DormType.code == 15 (כפר הסמכה) mapping. This class
# previously also contained solver-eligibility tests built on
# DormType.code == 11 — code 11 is confirmed to be עליון עמים, a real,
# different dorm type unrelated to this policy, so those tests modeled an
# impossible configuration and have been removed rather than fixed in
# place; Building179AutomaticAllocationTest is their authoritative
# replacement.
# ---------------------------------------------------------------------------
class AnierImportMappingTest(TestCase):
    """
    Upload mapping: the main upload's Excel column '9108-אנייר' (an 'X'
    flag) must be read and normalized into special_status_1..4 via
    inject_special_status_marker in build_student_payload_from_row —
    shared by both /api/upload/excel/ and /api/upload/additions-excel/
    (both call this same function, so one fix covers both flows).
    """

    def _make_row(self, **overrides):
        import pandas as pd

        values = {
            'ת"ז ישראלית': overrides.pop('student_id', 'ANIERROW1'),
            'שם פרטי': overrides.pop('first_name', 'Test'),
            'שם משפחה': overrides.pop('last_name', 'Student'),
            'תיאור סוג מגורים': overrides.pop('housing_type', 'רווקות'),
        }

        alias_to_header = {
            'anier_flag': '9108-אנייר',
            'special_status_1': 'תאור סטטוס מיוחד1',
            'special_status_2': 'תאור סטטוס מיוחד2',
            'special_status_3': 'תאור סטטוס מיוחד3',
            'special_status_4': 'תאור סטטוס מיוחד4',
        }
        for key, header in alias_to_header.items():
            if key in overrides:
                values[header] = overrides.pop(key)

        assert not overrides, f"Unrecognized row overrides: {overrides}"
        return pd.Series(values)

    # ------------------------------------------------------------------
    # 1. The 9108-אנייר column injects the אנייר marker.
    # ------------------------------------------------------------------

    def test_anier_column_flag_injects_special_status(self):
        """A bare '9108-אנייר'='X' flag, with no other special status, must
        result in 'אנייר' recorded in special_status_1..4, is_priority=True,
        and priority_reason == 'אנייר'."""
        from api.views import build_student_payload_from_row

        row = self._make_row(student_id='ANIER1', anier_flag='X')
        payload = build_student_payload_from_row(row)

        statuses = [
            payload['special_status_1'], payload['special_status_2'],
            payload['special_status_3'], payload['special_status_4'],
        ]
        self.assertIn('אנייר', statuses)
        self.assertTrue(payload['is_priority'])
        self.assertEqual(payload['priority_reason'], 'אנייר')

    def test_anier_flag_combines_with_existing_special_status(self):
        """An existing הסמכה special status plus the אנייר column flag must
        produce BOTH markers, joined in priority_reason."""
        from api.views import build_student_payload_from_row

        row = self._make_row(student_id='ANIER2', special_status_1='הסמכה', anier_flag='X')
        payload = build_student_payload_from_row(row)

        statuses = [
            payload['special_status_1'], payload['special_status_2'],
            payload['special_status_3'], payload['special_status_4'],
        ]
        self.assertIn('הסמכה', statuses)
        self.assertIn('אנייר', statuses)
        self.assertEqual(payload['priority_reason'], 'הסמכה | אנייר')

    def test_anier_flag_not_duplicated_when_already_present(self):
        """If 'אנייר' is already present as a special-status value (legacy
        data), the column flag must not create a duplicate entry."""
        from api.views import build_student_payload_from_row

        row = self._make_row(student_id='ANIER3', special_status_2='אנייר', anier_flag='X')
        payload = build_student_payload_from_row(row)

        statuses = [
            payload['special_status_1'], payload['special_status_2'],
            payload['special_status_3'], payload['special_status_4'],
        ]
        self.assertEqual(statuses.count('אנייר'), 1)

    def test_anier_flag_absent_leaves_special_status_untouched(self):
        """A blank/absent 9108-אנייר column must not add anything."""
        from api.views import build_student_payload_from_row

        row = self._make_row(student_id='ANIER4', special_status_1='הסמכה')
        payload = build_student_payload_from_row(row)

        statuses = [
            payload['special_status_1'], payload['special_status_2'],
            payload['special_status_3'], payload['special_status_4'],
        ]
        self.assertNotIn('אנייר', statuses)

    # ------------------------------------------------------------------
    # 2. Real Excel upload end-to-end — proves the column-name mapping
    #    survives the actual pandas read_excel round trip, not just a
    #    hand-built pandas Series.
    # ------------------------------------------------------------------

    def test_upload_excel_saves_anier_student_via_real_column(self):
        import io

        import pandas as pd
        from django.core.files.uploadedfile import SimpleUploadedFile

        buffer = io.BytesIO()
        pd.DataFrame([{
            'ת"ז ישראלית': 'ANIER_UP1',
            'שם פרטי': 'Test',
            'שם משפחה': 'Upload',
            'תיאור סוג מגורים': 'רווקות',
            '9108-אנייר': 'X',
        }]).to_excel(buffer, index=False, sheet_name='נכנסים חדשים')
        buffer.seek(0)

        try:
            pd.ExcelFile(buffer)
        except ImportError as exc:
            self.skipTest(
                f"openpyxl/pandas version mismatch in this environment ({exc}); "
                "this pre-existing environment issue is unrelated to the fix — "
                "see build_student_payload_from_row unit tests above for full "
                "coverage of the actual shared mapping logic."
            )
        buffer.seek(0)

        admin = _make_central_admin()
        client = APIClient()
        client.force_authenticate(user=admin)

        upload_file = SimpleUploadedFile(
            'anier.xlsx', buffer.read(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
        init_response = client.post('/api/upload/batches/init/', {'kind': 'main'}, format='json')
        self.assertEqual(init_response.status_code, 201, init_response.data)
        batch_id = init_response.data['batch_id']

        response = client.post(
            '/api/upload/excel/', {'file': upload_file, 'batch_id': batch_id}, format='multipart'
        )
        self.assertEqual(response.status_code, 200, response.data)

        student = Student.objects.get(student_id='ANIER_UP1')
        self.assertTrue(student.is_priority)
        self.assertIn('אנייר', [
            student.special_status_1, student.special_status_2,
            student.special_status_3, student.special_status_4,
        ])


# ---------------------------------------------------------------------------
# End-to-end proof that /api/upload/additions-excel/ shares the identical
# accessibility + אנייר mapping as /api/upload/excel/ (both call
# build_student_payload_from_row).
# ---------------------------------------------------------------------------
class AdditionsUploadSharedMappingTest(TestCase):
    """
    /api/upload/excel/ and /api/upload/additions-excel/ both route every
    row through api.views.build_student_payload_from_row — one shared
    mapping, per the requirement that both upload flows use the same
    logic. This test exercises the additions endpoint specifically (a
    real .xlsx upload, not a hand-built pandas Series) and verifies, from
    the saved Student record, that:
      - accessibility fields (accessibility_flag/disability_percent/
        medical_reason) are saved correctly;
      - the 9108-אנייר='X' column creates the canonical 'אנייר'
        special-status value;
      - a pre-existing special status (special_status_1='הסמכה') is
        preserved alongside the injected 'אנייר' marker;
      - is_priority and priority_reason are derived correctly from the
        combined special statuses.
    """

    def test_upload_additions_excel_saves_accessibility_and_anier_correctly(self):
        import io
        from decimal import Decimal

        import pandas as pd
        from django.core.files.uploadedfile import SimpleUploadedFile

        region = Region.objects.create(id='additions_region', name='Additions Region')
        dorm_type = DormType.objects.create(name='AdditionsDorm', code=77, region=region)
        Building.objects.create(number=200, dorm_type=dorm_type, is_active=True)

        admin = _make_central_admin()
        client = APIClient()
        client.force_authenticate(user=admin)

        buffer = io.BytesIO()
        pd.DataFrame([{
            'ת"ז ישראלית': 'ADD_ANIER1',
            'שם פרטי': 'Test',
            'שם משפחה': 'Additions',
            'תיאור סוג מגורים': 'רווקות',
            'החלטה-החלטת מעונות - תאור': 'החלטה חיובית',
            'החלטה-תוכן החלטה – מעונות': '77',
            'תאור סטטוס מיוחד1': 'הסמכה',
            '9108-אנייר': 'X',
            'החלטה-זקוק להנגשה': 'כן',
            '%נכות': '30',
            'סיבה רפואית מאושרת מרופאת הטכניון': 'מצב רפואי מאושר',
        }]).to_excel(buffer, index=False, sheet_name='תוספות')
        buffer.seek(0)

        upload_file = SimpleUploadedFile(
            'additions.xlsx', buffer.read(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
        init_response = client.post('/api/upload/batches/init/', {'kind': 'additions'}, format='json')
        self.assertEqual(init_response.status_code, 201, init_response.data)
        batch_id = init_response.data['batch_id']

        response = client.post(
            '/api/upload/additions-excel/', {'file': upload_file, 'batch_id': batch_id}, format='multipart'
        )
        self.assertEqual(response.status_code, 200, response.data)

        student = Student.objects.get(student_id='ADD_ANIER1')

        # Accessibility fields saved correctly.
        self.assertTrue(student.accessibility_flag)
        self.assertEqual(student.disability_percent, Decimal('30'))
        self.assertEqual(student.medical_reason, 'מצב רפואי מאושר')

        # 9108-אנייר='X' created the canonical 'אנייר' status, and the
        # pre-existing 'הסמכה' status was preserved (not overwritten).
        statuses = [
            student.special_status_1, student.special_status_2,
            student.special_status_3, student.special_status_4,
        ]
        self.assertIn('הסמכה', statuses)
        self.assertIn('אנייר', statuses)

        # is_priority/priority_reason derived correctly from the combined
        # special statuses (never from the accessibility columns).
        self.assertTrue(student.is_priority)
        self.assertEqual(student.priority_reason, 'הסמכה | אנייר')


# ---------------------------------------------------------------------------
# Import batch lifecycle: init handshake, live status/progress, Stop,
# Stop & Delete, Delete - covers the two-step batch_id handshake, the
# PENDING/PROCESSING/CANCELLATION_REQUESTED/STOP_AND_DELETE_REQUESTED/
# STOPPED state machine, created_in_batch-scoped deletion safety, and that
# Stop genuinely interrupts a synchronous upload request from a concurrent
# request (not just a DB flag nobody ever reads).
# ---------------------------------------------------------------------------
class ImportBatchLifecycleTest(TransactionTestCase):
    """TransactionTestCase (not TestCase) because the concurrency tests below
    run the upload in a real background thread against the SAME database -
    TestCase's per-test wrapping transaction would hide the thread's writes
    from the main thread (and vice versa)."""

    def setUp(self):
        self.admin = _make_central_admin(email='batchadmin@test.com')
        self.other_admin = _make_central_admin(email='otheradmin@test.com')
        self.client = APIClient()
        self.client.force_authenticate(user=self.admin)

    @staticmethod
    def _make_xlsx_bytes(row_count, sheet_name='נכנסים חדשים', student_id_prefix='LC'):
        import io
        import pandas as pd

        buffer = io.BytesIO()
        pd.DataFrame([
            {
                'ת"ז ישראלית': f'{student_id_prefix}{i:05d}',
                'שם פרטי': 'Test',
                'שם משפחה': f'Row{i}',
                'תיאור סוג מגורים': 'רווקות',
            }
            for i in range(row_count)
        ]).to_excel(buffer, index=False, sheet_name=sheet_name)
        buffer.seek(0)
        return buffer.read()

    def _init(self, kind='main', client=None):
        client = client or self.client
        resp = client.post('/api/upload/batches/init/', {'kind': kind}, format='json')
        self.assertEqual(resp.status_code, 201, resp.data)
        return resp.data['batch_id']

    def test_init_creates_pending_batch(self):
        batch_id = self._init(kind='main')
        batch = ImportBatch.objects.get(pk=batch_id)
        self.assertEqual(batch.status, ImportBatch.Status.PENDING)
        self.assertEqual(batch.kind, ImportBatch.Kind.MAIN)
        self.assertIsNone(batch.started_at)

    def test_upload_without_batch_id_is_rejected(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        upload_file = SimpleUploadedFile(
            'x.xlsx', self._make_xlsx_bytes(1),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
        resp = self.client.post('/api/upload/excel/', {'file': upload_file}, format='multipart')
        self.assertEqual(resp.status_code, 400)

    def test_upload_rejects_wrong_kind(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        batch_id = self._init(kind='additions')
        upload_file = SimpleUploadedFile(
            'x.xlsx', self._make_xlsx_bytes(1),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
        resp = self.client.post(
            '/api/upload/excel/', {'file': upload_file, 'batch_id': batch_id}, format='multipart'
        )
        self.assertEqual(resp.status_code, 400)

    def test_upload_rejects_other_admins_batch(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        other_client = APIClient()
        other_client.force_authenticate(user=self.other_admin)
        batch_id = self._init(kind='main', client=other_client)

        upload_file = SimpleUploadedFile(
            'x.xlsx', self._make_xlsx_bytes(1),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
        resp = self.client.post(
            '/api/upload/excel/', {'file': upload_file, 'batch_id': batch_id}, format='multipart'
        )
        self.assertEqual(resp.status_code, 403)

    def test_happy_path_completes_and_persists_result(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        batch_id = self._init(kind='main')
        upload_file = SimpleUploadedFile(
            'x.xlsx', self._make_xlsx_bytes(5, student_id_prefix='HP'),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
        resp = self.client.post(
            '/api/upload/excel/', {'file': upload_file, 'batch_id': batch_id}, format='multipart'
        )
        self.assertEqual(resp.status_code, 200, resp.data)

        batch = ImportBatch.objects.get(pk=batch_id)
        self.assertEqual(batch.status, ImportBatch.Status.COMPLETED)
        self.assertIsNotNone(batch.started_at)
        self.assertIsNotNone(batch.finished_at)
        self.assertEqual(batch.processed_rows, 5)
        self.assertEqual(batch.total_rows, 5)
        self.assertIsNotNone(batch.result)
        self.assertEqual(Student.objects.filter(created_in_batch=batch).count(), 5)

        status_resp = self.client.get(f'/api/upload/batches/{batch_id}/status/')
        self.assertEqual(status_resp.status_code, 200)
        self.assertEqual(status_resp.data['status'], ImportBatch.Status.COMPLETED)
        self.assertIsNotNone(status_resp.data['result'])

    def test_delete_removes_only_created_students_not_updated(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        pre_existing = Student.objects.create(
            student_id='PREEXIST1', first_name='Pre', last_name='Existing',
            gender=Student.Gender.FEMALE, housing_type=Student.HousingType.SINGLE_FEMALE,
        )

        import io
        import pandas as pd
        buffer = io.BytesIO()
        pd.DataFrame([
            {'ת"ז ישראלית': 'PREEXIST1', 'שם פרטי': 'Pre', 'שם משפחה': 'Existing', 'תיאור סוג מגורים': 'רווקות'},
            {'ת"ז ישראלית': 'BRANDNEW1', 'שם פרטי': 'Brand', 'שם משפחה': 'New', 'תיאור סוג מגורים': 'רווקות'},
        ]).to_excel(buffer, index=False, sheet_name='נכנסים חדשים')
        buffer.seek(0)

        batch_id = self._init(kind='main')
        upload_file = SimpleUploadedFile(
            'x.xlsx', buffer.read(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
        resp = self.client.post(
            '/api/upload/excel/', {'file': upload_file, 'batch_id': batch_id}, format='multipart'
        )
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertTrue(Student.objects.filter(pk=pre_existing.pk).exists())
        self.assertTrue(Student.objects.filter(student_id='BRANDNEW1').exists())

        delete_resp = self.client.post(f'/api/upload/batches/{batch_id}/delete/')
        self.assertEqual(delete_resp.status_code, 200, delete_resp.data)

        # The pre-existing student (merely updated by this batch) survives.
        self.assertTrue(Student.objects.filter(pk=pre_existing.pk).exists())
        # The genuinely new student (created by this batch) is gone.
        self.assertFalse(Student.objects.filter(student_id='BRANDNEW1').exists())

        deletion = delete_resp.data['result']['deletion']
        self.assertEqual(deletion['deleted_count'], 1)
        self.assertEqual(deletion['protected_count'], 0)

    def test_delete_rejected_while_processing(self):
        batch_id = self._init(kind='main')
        # Still PENDING (never uploaded) - delete is only valid once terminal.
        resp = self.client.post(f'/api/upload/batches/{batch_id}/delete/')
        self.assertEqual(resp.status_code, 409)

    def test_stop_rejected_when_not_processing(self):
        batch_id = self._init(kind='main')
        resp = self.client.post(f'/api/upload/batches/{batch_id}/stop/')
        self.assertEqual(resp.status_code, 409)

    def test_stop_and_delete_on_pending_batch_resolves_immediately(self):
        batch_id = self._init(kind='main')
        resp = self.client.post(f'/api/upload/batches/{batch_id}/stop-and-delete/')
        self.assertEqual(resp.status_code, 200, resp.data)

        batch = ImportBatch.objects.get(pk=batch_id)
        self.assertEqual(batch.status, ImportBatch.Status.STOPPED)
        self.assertEqual(batch.result['deletion']['deleted_count'], 0)

    def _run_upload_in_thread(self, batch_id, row_count, student_id_prefix, upload_url='/api/upload/excel/'):
        from django.core.files.uploadedfile import SimpleUploadedFile
        from django.db import connections

        result_holder = {}

        def _run():
            thread_client = APIClient()
            thread_client.force_authenticate(user=self.admin)
            upload_file = SimpleUploadedFile(
                'big.xlsx',
                self._make_xlsx_bytes(row_count, student_id_prefix=student_id_prefix),
                content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            )
            resp = thread_client.post(
                upload_url, {'file': upload_file, 'batch_id': batch_id}, format='multipart'
            )
            result_holder['status_code'] = resp.status_code
            result_holder['data'] = resp.data
            connections.close_all()

        thread = threading.Thread(target=_run, daemon=True)
        thread.start()
        return thread, result_holder

    def _wait_for_progress(self, batch_id, min_processed=20, timeout=20):
        deadline = time.time() + timeout
        while time.time() < deadline:
            processed = ImportBatch.objects.filter(pk=batch_id).values_list(
                'processed_rows', flat=True
            ).first()
            if processed is not None and processed >= min_processed:
                return processed
            time.sleep(0.05)
        self.fail(
            f"Batch {batch_id} did not reach {min_processed} processed_rows "
            f"within {timeout}s (concurrency/visibility problem, or the row "
            "loop is not actually running/committing progress)."
        )

    def test_stop_genuinely_interrupts_a_running_upload(self):
        """Proves the Decision-4 concurrency claim for real: a second
        request (this test's main thread) can flip the batch's status to
        CANCELLATION_REQUESTED WHILE a separate thread's upload request is
        still inside its row loop, and that loop actually notices and
        halts before processing every row."""
        batch_id = self._init(kind='main')
        thread, result_holder = self._run_upload_in_thread(batch_id, row_count=4000, student_id_prefix='ST')

        self._wait_for_progress(batch_id, min_processed=20)

        stop_client = APIClient()
        stop_client.force_authenticate(user=self.admin)
        stop_resp = stop_client.post(f'/api/upload/batches/{batch_id}/stop/')
        self.assertEqual(stop_resp.status_code, 200, stop_resp.data)

        thread.join(timeout=60)
        self.assertFalse(thread.is_alive(), "upload thread did not finish after being stopped")
        self.assertEqual(result_holder.get('status_code'), 200, result_holder.get('data'))

        batch = ImportBatch.objects.get(pk=batch_id)
        self.assertEqual(batch.status, ImportBatch.Status.STOPPED)
        self.assertIsNotNone(batch.finished_at)
        # The whole point of the test: it stopped meaningfully early, not
        # by coincidentally finishing all 4000 rows first.
        self.assertLess(batch.processed_rows, 4000)
        self.assertGreater(batch.processed_rows, 0)
        # Whatever rows WERE processed before the stop are real, committed
        # Student rows - not corrupted/partial counters.
        self.assertEqual(
            Student.objects.filter(created_in_batch=batch).count(),
            batch.result['created'],
        )

    def test_stop_and_delete_removes_students_created_before_the_stop(self):
        batch_id = self._init(kind='main')
        thread, result_holder = self._run_upload_in_thread(batch_id, row_count=4000, student_id_prefix='SD')

        self._wait_for_progress(batch_id, min_processed=20)

        stop_client = APIClient()
        stop_client.force_authenticate(user=self.admin)
        stop_resp = stop_client.post(f'/api/upload/batches/{batch_id}/stop-and-delete/')
        self.assertEqual(stop_resp.status_code, 200, stop_resp.data)

        thread.join(timeout=60)
        self.assertFalse(thread.is_alive())
        self.assertEqual(result_holder.get('status_code'), 200, result_holder.get('data'))

        batch = ImportBatch.objects.get(pk=batch_id)
        self.assertEqual(batch.status, ImportBatch.Status.STOPPED)
        self.assertLess(batch.processed_rows, 4000)
        self.assertIn('deletion', batch.result)
        self.assertGreater(batch.result['deletion']['deleted_count'], 0)
        # Everything this batch created was actually removed.
        self.assertEqual(Student.objects.filter(created_in_batch=batch).count(), 0)
