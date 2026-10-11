from unittest.mock import patch

from django.test import TestCase
from rest_framework.test import APIClient

from api.models import Student, DormType, Building, Apartment, Room, Bed

from ._support import _make_region, _make_central_admin, _make_region_boss


# ---------------------------------------------------------------------------
# Accessibility / disability: saved normally, never sent to the solver.
# ---------------------------------------------------------------------------
class AccessibilityAllocationExclusionTest(TestCase):
    """
    Covers the confirmed root cause of the over-flagging bug plus the
    surrounding accessibility/category behavior:

    Root cause: the allocation-group ("החלטה-תאור קבוצת הקצאה") whitelist
    used to also include the STAYING/CONTINUING category value
    ('הסמכה – ותיקים+חדשים שנפסלו כחדשים+בינלאומי מלאות2'), which is the
    majority category for returning students. That single mistaken entry
    caused 722 of 840 students to be marked accessibility_flag=True and
    excluded from the OR-Tools solver, leaving only 118 students actually
    allocated. Only the EXACT value 'הסמכה - נכים' may set
    accessibility_flag=True (see ACCESSIBILITY_ALLOCATION_GROUP_VALUES /
    allocation_group_indicates_accessibility in api/views.py).

    Separately, an accessibility_flag=True student must still be saved
    normally but excluded from the solver — neither api.views.run_allocation
    nor api.views.execute_allocation_run sends
    accessibility_flag=True students to
    allocation.solver.run_improved_ortools_allocation; the dorm office
    allocates them manually.

    None of this may affect is_priority (see
    priority_fields_from_special_statuses / StudentPriorityImportTest),
    which is derived solely from special_status_1..4.
    """

    def _make_row(self, **overrides):
        import pandas as pd

        values = {
            'ת"ז ישראלית': overrides.pop('student_id', 'ACCROW1'),
            'שם פרטי': overrides.pop('first_name', 'Test'),
            'שם משפחה': overrides.pop('last_name', 'Student'),
            'תיאור סוג מגורים': overrides.pop('housing_type', 'רווקות'),
        }

        alias_to_header = {
            'accessibility_flag': 'החלטה-זקוק להנגשה',
            'disability_percent': '%נכות',
            'medical_reason': 'סיבה רפואית מאושרת מרופאת הטכניון',
            'allocation_group': 'תיאור קבוצת הקצאה',
            'special_status_1': 'תאור סטטוס מיוחד1',
        }
        for key, header in alias_to_header.items():
            if key in overrides:
                values[header] = overrides.pop(key)

        assert not overrides, f"Unrecognized row overrides: {overrides}"
        return pd.Series(values)

    # ------------------------------------------------------------------
    # 1. allocation_group values containing נכים mark accessibility.
    # ------------------------------------------------------------------

    def test_allocation_group_hasmaha_nichim_marks_accessibility(self):
        """allocation_group='הסמכה - נכים' (no explicit accessibility
        columns) must still set accessibility_flag=True — an EXACT
        confirmed accessibility category value."""
        from api.views import build_student_payload_from_row

        row = self._make_row(student_id='ACC_GRP1', allocation_group='הסמכה - נכים')
        payload = build_student_payload_from_row(row)
        self.assertTrue(payload['accessibility_flag'])

    def test_allocation_group_kdam_academi_nichim_does_not_mark_accessibility(self):
        """allocation_group='קדםאקדמי - כולל נכים' is NOT one of the
        confirmed exact accessibility values and must NOT set
        accessibility_flag=True — only 'הסמכה - נכים' does."""
        from api.views import build_student_payload_from_row

        row = self._make_row(student_id='ACC_GRP2', allocation_group='קדםאקדמי - כולל נכים')
        payload = build_student_payload_from_row(row)
        self.assertFalse(payload['accessibility_flag'])

    def test_allocation_group_staying_value_does_not_mark_accessibility(self):
        """
        Regression test for the confirmed root cause: allocation_group=
        'הסמכה – ותיקים+חדשים שנפסלו כחדשים+בינלאומי מלאות2' identifies
        STAYING/CONTINUING students (the majority category) and must NOT
        set accessibility_flag=True. Before the fix, this exact value was
        mistakenly included in the accessibility whitelist, which flagged
        722 of 840 students as accessibility_flag=True and excluded them
        from the OR-Tools solver, leaving only 118 actually allocated.
        These students must still reach the solver like any other
        staying/continuing student, since all students are re-allocated
        from scratch.
        """
        from api.views import build_student_payload_from_row

        row = self._make_row(
            student_id='ACC_GRP3',
            allocation_group='הסמכה – ותיקים+חדשים שנפסלו כחדשים+בינלאומי מלאות2',
        )
        payload = build_student_payload_from_row(row)
        self.assertFalse(payload['accessibility_flag'])
        self.assertEqual(payload['category'], Student.StudentCategory.CONTINUING)

    def test_allocation_group_staying_value_dash_variant_still_classified_as_staying(self):
        """The same staying/continuing value, but with a plain hyphen
        instead of an en-dash (a real Excel-export inconsistency), must
        still classify as CONTINUING and not accessibility — proving
        normalization is dash-insensitive in both directions."""
        from api.views import build_student_payload_from_row

        row = self._make_row(
            student_id='ACC_GRP3B',
            allocation_group='הסמכה - ותיקים+חדשים שנפסלו כחדשים+בינלאומי מלאות2',
        )
        payload = build_student_payload_from_row(row)
        self.assertFalse(payload['accessibility_flag'])
        self.assertEqual(payload['category'], Student.StudentCategory.CONTINUING)

    def test_allocation_group_new_values_marked_new_and_not_accessibility(self):
        """allocation_group='הסמכה – חדשים' and 'מסיימי מכינה מאוחרים – שנה
        1' must classify as StudentCategory.NEW and must not be treated as
        accessibility."""
        from api.views import build_student_payload_from_row

        for index, allocation_group in enumerate((
            'הסמכה – חדשים',
            'מסיימי מכינה מאוחרים – שנה 1',
        ), start=1):
            row = self._make_row(student_id=f'ACC_GRP_NEW{index}', allocation_group=allocation_group)
            payload = build_student_payload_from_row(row)
            self.assertFalse(payload['accessibility_flag'], allocation_group)
            self.assertEqual(payload['category'], Student.StudentCategory.NEW, allocation_group)

    def test_allocation_group_other_ordinary_value_sent_normally(self):
        """allocation_group='תארים מתקדמים – מגיסטרים+דוקטורים+בינלאומיים'
        (advanced degrees) is an ordinary non-empty value: not
        accessibility, and no special category field/migration is created
        for it — it falls back to the existing CONTINUING default."""
        from api.views import build_student_payload_from_row

        row = self._make_row(
            student_id='ACC_GRP_OTHER1',
            allocation_group='תארים מתקדמים – מגיסטרים+דוקטורים+בינלאומיים',
        )
        payload = build_student_payload_from_row(row)
        self.assertFalse(payload['accessibility_flag'])
        self.assertEqual(payload['category'], Student.StudentCategory.CONTINUING)

    def test_allocation_group_unrelated_value_does_not_mark_accessibility(self):
        """An ordinary, unrelated allocation-group value must not be
        treated as accessibility."""
        from api.views import build_student_payload_from_row

        row = self._make_row(student_id='ACC_GRP5', allocation_group='רגילים')
        payload = build_student_payload_from_row(row)
        self.assertFalse(payload['accessibility_flag'])

    def test_allocation_group_header_is_not_treated_as_value(self):
        """The column header text itself ('החלטה-תאור קבוצת הקצאה' / 'תיאור
        קבוצת הקצאה') must never be read back as if it were a cell value —
        get_row_value() only ever returns row.get(column_name), never the
        column name itself, so a row whose allocation_group cell literally
        equals the header text is not one of the confirmed category values
        and must not be classified as accessibility or as any exact
        staying/new category."""
        from api.views import build_student_payload_from_row

        row = self._make_row(
            student_id='ACC_GRP_HDR1',
            allocation_group='תיאור קבוצת הקצאה',
        )
        payload = build_student_payload_from_row(row)
        self.assertFalse(payload['accessibility_flag'])
        self.assertEqual(payload['category'], Student.StudentCategory.CONTINUING)

    def test_allocation_group_partial_match_does_not_mark_accessibility(self):
        """
        A value that merely SHARES WORDS with a confirmed accessibility
        category (e.g. 'הסמכה' alone, or 'הסמכה - אחר') must NOT be
        treated as accessibility — the match is an exact confirmed
        category value, never a broad substring/partial rule that could
        misclassify ordinary הסמכה students who are not in the
        accessibility cohort.
        """
        from api.views import build_student_payload_from_row

        row_bare = self._make_row(student_id='ACC_GRP6', allocation_group='הסמכה')
        self.assertFalse(build_student_payload_from_row(row_bare)['accessibility_flag'])

        row_other = self._make_row(student_id='ACC_GRP7', allocation_group='הסמכה - אחר')
        self.assertFalse(build_student_payload_from_row(row_other)['accessibility_flag'])

    def test_allocation_group_accessibility_does_not_set_priority(self):
        """Accessibility derived from allocation_group text must never set
        is_priority — only special_status_1..4 may do that."""
        from api.views import build_student_payload_from_row

        row = self._make_row(student_id='ACC_GRP_PRI1', allocation_group='הסמכה - נכים')
        payload = build_student_payload_from_row(row)
        self.assertTrue(payload['accessibility_flag'])
        self.assertFalse(payload['is_priority'])
        self.assertEqual(payload['priority_reason'], '')

    def test_allocation_group_staying_and_new_values_do_not_set_priority(self):
        """The staying/new category values must never set is_priority
        either — only special_status_1..4 may do that."""
        from api.views import build_student_payload_from_row

        for index, allocation_group in enumerate((
            'הסמכה – ותיקים+חדשים שנפסלו כחדשים+בינלאומי מלאות2',
            'הסמכה – חדשים',
            'מסיימי מכינה מאוחרים – שנה 1',
        ), start=1):
            row = self._make_row(student_id=f'ACC_GRP_PRI2_{index}', allocation_group=allocation_group)
            payload = build_student_payload_from_row(row)
            self.assertFalse(payload['accessibility_flag'], allocation_group)
            self.assertFalse(payload['is_priority'], allocation_group)
            self.assertEqual(payload['priority_reason'], '', allocation_group)

    # ------------------------------------------------------------------
    # 2. Real Excel upload still saves accessibility students normally.
    # ------------------------------------------------------------------

    def test_upload_excel_saves_accessibility_student_via_allocation_group(self):
        """End-to-end: /api/upload/excel/ with a real .xlsx row whose only
        accessibility signal is the allocation-group text must still save
        accessibility_flag=True and is_priority=False."""
        import io

        import pandas as pd
        from django.core.files.uploadedfile import SimpleUploadedFile

        buffer = io.BytesIO()
        pd.DataFrame([{
            'ת"ז ישראלית': 'ACC_UP1',
            'שם פרטי': 'Test',
            'שם משפחה': 'Upload',
            'תיאור סוג מגורים': 'רווקות',
            'תיאור קבוצת הקצאה': 'הסמכה - נכים',
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
            'accessibility.xlsx', buffer.read(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )

        init_response = client.post('/api/upload/batches/init/', {'kind': 'main'}, format='json')
        self.assertEqual(init_response.status_code, 201, init_response.data)
        batch_id = init_response.data['batch_id']

        response = client.post(
            '/api/upload/excel/', {'file': upload_file, 'batch_id': batch_id}, format='multipart'
        )
        self.assertEqual(response.status_code, 200, response.data)

        student = Student.objects.get(student_id='ACC_UP1')
        self.assertTrue(student.accessibility_flag)
        self.assertFalse(student.is_priority)

    # ------------------------------------------------------------------
    # 3. accessibility_flag=True students are excluded from allocation.
    # ------------------------------------------------------------------

    def test_run_allocation_excludes_accessibility_students(self):
        """/api/allocation/run/ (views.run_allocation) must never send an
        accessibility_flag=True student to the solver, even though they
        have a perfectly valid candidate bed available. An ordinary
        student in the same room must still be assigned."""
        region = _make_region('AccessRegion')
        boss = _make_region_boss(region)
        dorm_type = DormType.objects.create(name='AccessDorm', region=region)
        building = Building.objects.create(number=901, dorm_type=dorm_type)
        apartment = Apartment.objects.create(
            building=building, number='1', category=Apartment.Category.FEMALE,
            apartment_type=Apartment.ApartmentType.SINGLE, room_count=1,
        )
        room = Room.objects.create(apartment=apartment, name='A', capacity=2)
        Bed.objects.create(room=room, label='1')
        Bed.objects.create(room=room, label='2')

        ordinary = Student.objects.create(
            student_id='ACC_ORD1', first_name='Ord', last_name='Student',
            gender=Student.Gender.FEMALE, housing_type=Student.HousingType.SINGLE_FEMALE,
            accepted_dorm_type=dorm_type,
        )
        accessible = Student.objects.create(
            student_id='ACC_EXCL1', first_name='Acc', last_name='Student',
            gender=Student.Gender.FEMALE, housing_type=Student.HousingType.SINGLE_FEMALE,
            accepted_dorm_type=dorm_type, accessibility_flag=True,
        )

        patcher = patch('allocation.solver.close_old_connections')
        patcher.start()
        self.addCleanup(patcher.stop)

        client = APIClient()
        client.force_authenticate(user=boss)
        response = client.post('/api/allocation/run/', {'region': region.id}, format='json')
        self.assertEqual(response.status_code, 200, response.data)

        ordinary.refresh_from_db()
        accessible.refresh_from_db()
        self.assertTrue(ordinary.is_assigned)
        self.assertFalse(accessible.is_assigned)

    # ------------------------------------------------------------------
    # 4. A student who is both eligible-ANIR/priority AND accessibility-
    #    flagged: accessibility exclusion wins for automatic allocation,
    #    while ANIR/priority metadata remains fully intact. Accessibility
    #    and priority/ANIR status are independent fields — exclusion from
    #    the solver is a read-time queryset filter, never a data mutation.
    # ------------------------------------------------------------------

    def test_anier_priority_accessibility_student_excluded_but_metadata_preserved(self):
        """A student who carries the אנייר marker (is_priority=True as a
        side effect) AND accessibility_flag=True must never be sent to the
        automatic solver — accessibility exclusion wins — but is_priority,
        priority_reason, the אנייר special_status marker, and the
        accessibility fields themselves must all remain stored and
        readable afterward. Exclusion is a queryset filter, never a data
        mutation."""
        region = _make_region('AnierAccessRegion')
        boss = _make_region_boss(region)
        dorm_type = DormType.objects.create(name='כפר הסמכה', code=15, region=region)
        building = Building.objects.create(number=179, dorm_type=dorm_type)
        apartment = Apartment.objects.create(
            building=building, number='1', category=Apartment.Category.FEMALE,
            apartment_type=Apartment.ApartmentType.SINGLE, room_count=1,
        )
        room = Room.objects.create(apartment=apartment, name='A', capacity=1)
        Bed.objects.create(room=room, label='1')

        student = Student.objects.create(
            student_id='ANIER_ACC1', first_name='Anier', last_name='Accessible',
            gender=Student.Gender.FEMALE, housing_type=Student.HousingType.SINGLE_FEMALE,
            accepted_dorm_type=dorm_type,
            is_priority=True, special_status_1='אנייר', priority_reason='אנייר',
            accessibility_flag=True, disability_percent=50, medical_reason='test reason',
        )

        patcher = patch('allocation.solver.close_old_connections')
        patcher.start()
        self.addCleanup(patcher.stop)

        client = APIClient()
        client.force_authenticate(user=boss)
        response = client.post('/api/allocation/run/', {'region': region.id}, format='json')
        self.assertEqual(response.status_code, 200, response.data)

        student.refresh_from_db()
        # Excluded from automatic allocation despite an available, otherwise
        # fully-compatible Building-179 bed.
        self.assertFalse(student.is_assigned)
        # ANIR/priority/accessibility metadata all remain intact — exclusion
        # never clears or rewrites any of it.
        self.assertTrue(student.is_priority)
        self.assertEqual(student.priority_reason, 'אנייר')
        self.assertEqual(student.special_status_1, 'אנייר')
        self.assertTrue(student.accessibility_flag)
        self.assertEqual(student.disability_percent, 50)
        self.assertEqual(student.medical_reason, 'test reason')
