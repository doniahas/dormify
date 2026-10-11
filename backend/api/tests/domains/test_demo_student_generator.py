"""
Tests for scripts/generate_demo_students.py: the workbook it writes is
deterministic, uses only headers the importer recognises, contains only
synthetic identities, and imports through the real status-report path.
"""

import re
import tempfile
from pathlib import Path

import pandas as pd
from django.test import SimpleTestCase, TestCase

from api.domains.imports import batches, ingestion
from api.domains.imports.parsing import COLUMN_ALIASES
from api.models import ImportBatch, Student
from scripts import generate_demo_students as gen

from ._fixtures import make_central_admin, make_dorm, make_region

KNOWN_HEADERS = {alias for aliases in COLUMN_ALIASES.values() for alias in aliases}
STUDENT_ID = re.compile(r'^9\d{8}$')
PHONE = re.compile(r'^050-1\d{6}$')


def _all_rows(rows_by_sheet):
    return [row for rows in rows_by_sheet.values() for row in rows]


class GeneratorRowsTests(SimpleTestCase):
    def test_every_column_is_a_header_the_importer_recognises(self):
        unknown = [column for column in gen.COLUMNS if column not in KNOWN_HEADERS]
        self.assertEqual(unknown, [])
        for required in ingestion.REQUIRED_COLUMNS:
            self.assertIn(required, gen.COLUMNS)

    def test_same_seed_and_count_give_the_same_rows(self):
        first = gen.build_workbook_rows(count=50, seed=11)
        second = gen.build_workbook_rows(count=50, seed=11)
        self.assertEqual(first, second)
        self.assertNotEqual(first, gen.build_workbook_rows(count=50, seed=12))
        self.assertEqual(len(_all_rows(gen.build_workbook_rows(count=37, seed=11))), 37)

    def test_identities_are_synthetic_and_unique(self):
        rows = _all_rows(gen.build_workbook_rows(count=gen.DEFAULT_COUNT, seed=gen.DEFAULT_SEED))
        self.assertEqual(len(rows), gen.DEFAULT_COUNT)
        ids = [row[gen.COL_STUDENT_ID] for row in rows]
        self.assertEqual(len(set(ids)), len(ids))
        for row in rows:
            self.assertRegex(row[gen.COL_STUDENT_ID], STUDENT_ID)
            self.assertTrue(row[gen.COL_EMAIL].endswith('@example.edu'), row[gen.COL_EMAIL])
            self.assertRegex(row[gen.COL_PHONE], PHONE)
            self.assertIn(row[gen.COL_FIRST_NAME], gen.FIRST_NAMES_FEMALE + gen.FIRST_NAMES_MALE + gen.FIRST_NAMES_NEUTRAL)
            self.assertIn(row[gen.COL_LAST_NAME], gen.LAST_NAMES)

    def test_population_is_diverse_enough_for_a_demo(self):
        rows_by_sheet = gen.build_workbook_rows(count=gen.DEFAULT_COUNT, seed=gen.DEFAULT_SEED)
        rows = _all_rows(rows_by_sheet)

        self.assertGreater(len(rows_by_sheet[gen.SHEET_CONTINUING]), 0)
        self.assertGreater(len(rows_by_sheet[gen.SHEET_NEW]), 0)
        self.assertEqual(len(rows_by_sheet[gen.SHEET_LEAVING]), gen.DEFAULT_COUNT // 25)

        self.assertEqual({row[gen.COL_TENANT_TYPE] for row in rows}, {'Z1', 'Z2', 'Z3', 'Z4', 'Z6'})
        self.assertGreaterEqual(len({row[gen.COL_DECISION_DORM_CODE] for row in rows}), 4)
        self.assertGreaterEqual(len({row[gen.COL_RELIGION] for row in rows}), 3)
        self.assertGreater(sum(1 for row in rows if row[gen.COL_RELIGIOUS] == gen.YES), 0)
        self.assertGreater(sum(1 for row in rows if row[gen.COL_ACCESSIBILITY] == gen.YES), 0)
        self.assertGreater(sum(1 for row in rows if row[gen.COL_ANIER]), 0)
        self.assertGreater(sum(1 for row in rows if row[gen.COL_SPECIAL_STATUS_1]), 0)
        self.assertGreater(sum(1 for row in rows if row[gen.COL_DECISION_STATUS] == gen.DECISION_NEGATIVE), 0)
        self.assertGreater(len({row[gen.COL_STUDY_POINTS] for row in rows}), 3)

        # Single applicants carry a resident gender; household types may not.
        for row in rows:
            if row[gen.COL_TENANT_TYPE] in ('Z1', 'Z2'):
                self.assertIn(row[gen.COL_GENDER], ('זכר', 'נקבה'))
        # ANIR students only exist in the dorm type with the reserved population.
        for row in rows:
            if row[gen.COL_ANIER]:
                self.assertEqual(row[gen.COL_DECISION_DORM_CODE], 15)

    def test_roommate_requests_point_at_compatible_students(self):
        rows = _all_rows(gen.build_workbook_rows(count=gen.DEFAULT_COUNT, seed=gen.DEFAULT_SEED))
        by_id = {row[gen.COL_STUDENT_ID]: row for row in rows}
        requesters = [row for row in rows if row[gen.COL_ROOMMATE_FLAG_1] == gen.YES]
        self.assertGreaterEqual(len(requesters), 4)
        mutual = 0
        for row in requesters:
            partner = by_id[row[gen.COL_ROOMMATE_ID_1]]
            self.assertEqual(row[gen.COL_ROOMMATE_NAME_1], gen._full_name(partner))
            self.assertEqual(row[gen.COL_TENANT_TYPE], partner[gen.COL_TENANT_TYPE])
            self.assertEqual(row[gen.COL_DECISION_DORM_CODE], partner[gen.COL_DECISION_DORM_CODE])
            if partner[gen.COL_ROOMMATE_ID_1] == row[gen.COL_STUDENT_ID]:
                mutual += 1
        self.assertGreaterEqual(mutual, 2)

    def test_cli_writes_a_workbook_and_help_exits_zero(self):
        with self.assertRaises(SystemExit) as raised:
            gen.main(['--help'])
        self.assertEqual(raised.exception.code, 0)

        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / 'nested' / 'demo.xlsx'
            self.assertEqual(gen.main(['--count', '30', '--seed', '3', '--output', str(output)]), 0)
            self.assertTrue(output.exists())

            workbook = pd.ExcelFile(output)
            self.assertEqual(workbook.sheet_names, [gen.SHEET_CONTINUING, gen.SHEET_NEW, gen.SHEET_LEAVING])
            frames = [workbook.parse(name) for name in workbook.sheet_names]
            self.assertEqual(sum(len(frame) for frame in frames), 30)
            for frame in frames:
                self.assertEqual(list(frame.columns), gen.COLUMNS)

            again = Path(tmp) / 'again.xlsx'
            self.assertEqual(gen.main(['--count', '30', '--seed', '3', '--output', str(again)]), 0)
            for name in workbook.sheet_names:
                pd.testing.assert_frame_equal(workbook.parse(name), pd.ExcelFile(again).parse(name))

        self.assertEqual(gen.main(['--count', '0', '--output', str(output)]), 2)


class GeneratorImportTests(TestCase):
    """The generated workbook goes through the real status-report import."""

    def setUp(self):
        self.admin = make_central_admin()
        canada = make_region('Gen Canada')
        hasmaha = make_region('Gen Hasmaha')
        mizrah = make_region('Gen Mizrah')
        self.dorms = {
            2: make_dorm(canada, name='קנדה', code=2),
            15: make_dorm(hasmaha, name='כפר הסמכה', code=15),
            12: make_dorm(mizrah, name='מזרח חדש', code=12),
            5: make_dorm(mizrah, name='מזרח ישן', code=5),
        }
        # No dorm type for code 17: those rows must import with a warning.

    def test_workbook_imports_every_row_with_the_expected_attributes(self):
        count = 80
        rows_by_sheet = gen.build_workbook_rows(count=count, seed=5)
        with tempfile.TemporaryDirectory() as tmp:
            path = gen.write_workbook(rows_by_sheet, Path(tmp) / 'demo.xlsx')
            batch = batches.claim_pending_batch(
                ImportBatch.objects.create(uploaded_by=self.admin, kind=ImportBatch.Kind.MAIN).id,
                'demo.xlsx',
            )
            result = ingestion.run_status_report_import(batch, pd.ExcelFile(path))

        self.assertEqual(result['created'], count)
        self.assertEqual(result['skipped'], 0)
        self.assertEqual(Student.objects.count(), count)

        rows = _all_rows(rows_by_sheet)
        students = {student.student_id: student for student in Student.objects.select_related('accepted_dorm_type')}
        self.assertEqual(set(students), {row[gen.COL_STUDENT_ID] for row in rows})

        categories = {student.category for student in students.values()}
        self.assertEqual(categories, {
            Student.StudentCategory.CONTINUING, Student.StudentCategory.NEW, Student.StudentCategory.LEAVING,
        })
        self.assertEqual(
            {student.housing_type for student in students.values()},
            {choice for choice, _label in Student.HousingType.choices},
        )

        for row in rows:
            student = students[row[gen.COL_STUDENT_ID]]
            self.assertEqual(student.email, row[gen.COL_EMAIL])
            code = row[gen.COL_DECISION_DORM_CODE]
            if code in self.dorms:
                self.assertEqual(student.accepted_dorm_type_id, self.dorms[code].id)
            else:
                self.assertIsNone(student.accepted_dorm_type)
            if row[gen.COL_TENANT_TYPE] == 'Z1':
                self.assertEqual(student.gender, Student.Gender.MALE)
            if row[gen.COL_TENANT_TYPE] == 'Z2':
                self.assertEqual(student.gender, Student.Gender.FEMALE)
            if row[gen.COL_ANIER]:
                self.assertTrue(student.is_priority)
                self.assertIn('אנייר', ' '.join(filter(None, [
                    student.special_status_1, student.special_status_2,
                    student.special_status_3, student.special_status_4,
                ])))
            if row[gen.COL_ACCESSIBILITY] == gen.YES:
                self.assertTrue(student.accessibility_flag)
            if row[gen.COL_RELIGIOUS] == gen.YES:
                self.assertEqual(student.religious, Student.Religious.RELIGIOUS)
            if row[gen.COL_ROOMMATE_FLAG_1] == gen.YES:
                self.assertTrue(student.roommate_request_flag_1)
                self.assertEqual(student.roommate_request_student_id_1, row[gen.COL_ROOMMATE_ID_1])

        self.assertTrue(any(student.accessibility_flag for student in students.values()))
        self.assertTrue(any(student.is_priority for student in students.values()))
        unresolved = [warning for warning in result['warnings'] if 'could not be resolved' in warning]
        self.assertEqual(len(unresolved), sum(1 for row in rows if row[gen.COL_DECISION_DORM_CODE] not in self.dorms))
