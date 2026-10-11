#!/usr/bin/env python
"""
Generate a synthetic student workbook for Dormify's Excel import.

    python scripts/generate_demo_students.py                      # 120 students, seed 2026
    python scripts/generate_demo_students.py --count 60 --seed 7
    python scripts/generate_demo_students.py --output /tmp/demo.xlsx

Run from backend/. The workbook is written to backend/demo-data/ (git-ignored)
unless --output says otherwise, and is uploaded through the Students import
page ("main population file") as the central administrator. Column headers
are the dorm-office header names that api.domains.imports.parsing
recognises; sheet names drive the student category the way the real status
report does (continuing, new, leaving).

Everything is synthetic and deterministic for a given --seed and --count:
sequential 9-digit IDs starting with 9, names drawn from fixed lists,
@example.edu e-mails, 050-1xxxxxx phone numbers. The population is skewed
on purpose so a demo produces both assigned and unassigned students
against the inventory that backend/seed.py creates: more single-female
applicants than Canada has single-female beds, household applications
(couples, families, single-in-apartment) beyond the household apartments,
students accepted to a dorm type with no inventory, accessibility cases
(left to the assisted workbench), ANIR students, priority students,
religious-placement requests and mutual roommate requests.

The script needs only openpyxl (a runtime dependency) and never touches
the network or the database.
"""

import argparse
import random
import sys
from pathlib import Path

from openpyxl import Workbook

BACKEND_DIR = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = BACKEND_DIR / 'demo-data' / 'demo_students.xlsx'
DEFAULT_COUNT = 120
DEFAULT_SEED = 2026

# Sheet names the importer maps to student categories.
SHEET_CONTINUING = 'נשארים'
SHEET_NEW = 'נכנסים חדשים'
SHEET_LEAVING = 'עוזבים'

# Column headers, in workbook order. Each is the first alias of its key in
# api.domains.imports.parsing.COLUMN_ALIASES (the real dorm-office header).
COL_STUDENT_ID = 'ת"ז ישראלית'
COL_BUSINESS_PARTNER = 'שותף עסקי'
COL_FIRST_NAME = 'שם פרטי'
COL_LAST_NAME = 'שם משפחה'
COL_PHONE = 'טלפון 1'
COL_PHONE_SECONDARY = 'טלפון חירום'
COL_EMAIL = 'אימייל 1'
COL_CITY = 'שם ישוב'
COL_GENDER = 'תיאור מגדר'
COL_HOUSING_TYPE = 'תיאור סוג מגורים'
COL_TENANT_TYPE = 'החלטה-סוג מגורים של הדייר'
COL_DECISION_STATUS = 'החלטת מעונות - אביב'
COL_DECISION_DORM_CODE = 'אזור החלטה לאביב'
COL_DECISION_DORM_NAME = 'גריעה/תוספת-תוכן ההחלטה-תיאור'
COL_CURRENT_DORM_CODE = 'אזור מגורים נוכחי'
COL_CURRENT_ADDRESS = 'כתובת במעונות נוכחית'
COL_RELIGION = 'תיאור קוד לאום מבוקש'
COL_RELIGIOUS = 'החלטה אחרונה - דתי לצורך שיבוץ תיאור'
COL_ALLOCATION_GROUP = 'תיאור קבוצת הקצאה'
COL_ACCESSIBILITY = 'החלטה-זקוק להנגשה'
COL_DISABILITY_PERCENT = '%נכות'
COL_ANIER = '9108-אנייר'
COL_ROOMMATE_FLAG_1 = 'בקשה לגור עם סטודנטים חבר1'
COL_ROOMMATE_NAME_1 = 'החלטה אחרונה: שם חבר 1'
COL_ROOMMATE_ID_1 = 'החלטה אחרונה: תז חבר 1'
COL_SPECIAL_STATUS_1 = 'תאור סטטוס מיוחד1'
COL_SPECIAL_STATUS_2 = 'תאור סטטוס מיוחד2'
COL_STUDY_POINTS = 'נ.אקדמי מצטבר'

COLUMNS = [
    COL_STUDENT_ID, COL_BUSINESS_PARTNER, COL_FIRST_NAME, COL_LAST_NAME,
    COL_PHONE, COL_PHONE_SECONDARY, COL_EMAIL, COL_CITY,
    COL_GENDER, COL_HOUSING_TYPE, COL_TENANT_TYPE,
    COL_DECISION_STATUS, COL_DECISION_DORM_CODE, COL_DECISION_DORM_NAME,
    COL_CURRENT_DORM_CODE, COL_CURRENT_ADDRESS,
    COL_RELIGION, COL_RELIGIOUS, COL_ALLOCATION_GROUP,
    COL_ACCESSIBILITY, COL_DISABILITY_PERCENT, COL_ANIER,
    COL_ROOMMATE_FLAG_1, COL_ROOMMATE_NAME_1, COL_ROOMMATE_ID_1,
    COL_SPECIAL_STATUS_1, COL_SPECIAL_STATUS_2, COL_STUDY_POINTS,
]

# Cell values the importer parses (see parsing.py for the accepted sets).
DECISION_POSITIVE = 'החלטה חיובית'
DECISION_NEGATIVE = 'החלטה שלילית'
ALLOCATION_GROUP_STAYING = 'הסמכה – ותיקים+חדשים שנפסלו כחדשים+בינלאומי מלאות2'
ALLOCATION_GROUP_NEW = 'הסמכה – חדשים'
ALLOCATION_GROUP_NEW_LATE = 'מסיימי מכינה מאוחרים – שנה 1'
ALLOCATION_GROUP_ACCESSIBILITY = 'הסמכה - נכים'
YES = 'כן'
NO = 'לא'

# Housing types: (tenant code, description, resident gender or None).
# Z3/Z4/Z6 are allocated by apartment type, so the importer accepts a
# blank gender for them.
HOUSING_TYPES = [
    ('Z1', 'רווקים', 'זכר'),
    ('Z2', 'רווקות', 'נקבה'),
    ('Z3', 'זוגות', None),
    ('Z4', 'משפחות עד 2 ילדים (כולל)', None),
    ('Z6', 'רווקים/ות בדירה', None),
]
HOUSING_WEIGHTS = [30, 42, 10, 4, 14]

# Official dorm-type codes with the names parsing.py maps them to. Codes
# 2, 15, 12 and 5 have inventory in backend/seed.py; 17 has none.
DORM_TYPES = [
    (2, 'קנדה'),
    (15, 'כפר הסמכה'),
    (12, 'מזרח חדש'),
    (5, 'מזרח ישן'),
    (17, 'ברושים'),
]
DORM_WEIGHTS = [45, 30, 12, 6, 7]

RELIGIONS = ['יהודי', 'מוסלמי', 'נוצרי', 'דרוזי']
RELIGION_WEIGHTS = [60, 22, 10, 8]

CITIES = ['חיפה', 'תל אביב', 'ירושלים', 'נצרת', 'באר שבע', 'כרמיאל', 'עכו', 'אילת']

FIRST_NAMES_FEMALE = [
    'Noa', 'Maya', 'Lian', 'Dana', 'Amira', 'Yara', 'Tamar', 'Lina', 'Shira', 'Rana',
    'Hila', 'Salma', 'Michal', 'Layla', 'Adi', 'Nour', 'Roni', 'Hana', 'Yael', 'Dina',
]
FIRST_NAMES_MALE = [
    'Omer', 'Adam', 'Yonatan', 'Sami', 'Tal', 'Karim', 'Itai', 'Rami', 'Eitan', 'Fadi',
    'Noam', 'Said', 'Daniel', 'Majd', 'Lior', 'Bashar', 'Ido', 'Tarek', 'Amit', 'Wael',
]
FIRST_NAMES_NEUTRAL = ['Alex', 'Sam', 'Nour', 'Dani', 'Ariel', 'Rani', 'Shai', 'Tal']
LAST_NAMES = [
    'Alder', 'Birch', 'Cedar', 'Dunes', 'Elm', 'Fern', 'Grove', 'Harbor', 'Ivy', 'Juniper',
    'Kestrel', 'Linden', 'Meadow', 'Nettle', 'Orchard', 'Pine', 'Quarry', 'Reed', 'Sorrel',
    'Thistle', 'Umber', 'Vale', 'Willow', 'Yarrow',
]


def _student_id(index):
    """Nine digits starting with 9: clearly outside any real ID range."""
    return f'9{index:08d}'


def _phone(index):
    return f'050-{1000000 + index:07d}'


def _email(first, last, index):
    return f'{first}.{last}.{index:03d}@example.edu'.lower()


def _full_name(row):
    return f"{row[COL_FIRST_NAME]} {row[COL_LAST_NAME]}"


def _blank_row():
    return {column: '' for column in COLUMNS}


def _student_row(rng, index, *, sheet):
    tenant, housing_description, gender = rng.choices(HOUSING_TYPES, HOUSING_WEIGHTS)[0]
    code, dorm_name = rng.choices(DORM_TYPES, DORM_WEIGHTS)[0]

    if gender == 'זכר':
        first = rng.choice(FIRST_NAMES_MALE)
    elif gender == 'נקבה':
        first = rng.choice(FIRST_NAMES_FEMALE)
    else:
        first = rng.choice(FIRST_NAMES_NEUTRAL)
    last = rng.choice(LAST_NAMES)

    row = _blank_row()
    row[COL_STUDENT_ID] = _student_id(index)
    row[COL_BUSINESS_PARTNER] = f'BP{index:06d}'
    row[COL_FIRST_NAME] = first
    row[COL_LAST_NAME] = last
    row[COL_PHONE] = _phone(index)
    row[COL_PHONE_SECONDARY] = _phone(index + 500000) if rng.random() < 0.3 else ''
    row[COL_EMAIL] = _email(first, last, index)
    row[COL_CITY] = rng.choice(CITIES)
    row[COL_GENDER] = gender or ''
    row[COL_HOUSING_TYPE] = housing_description
    row[COL_TENANT_TYPE] = tenant
    row[COL_DECISION_STATUS] = DECISION_POSITIVE if rng.random() < 0.95 else DECISION_NEGATIVE
    row[COL_DECISION_DORM_CODE] = code
    row[COL_DECISION_DORM_NAME] = dorm_name
    row[COL_RELIGION] = rng.choices(RELIGIONS, RELIGION_WEIGHTS)[0]
    row[COL_RELIGIOUS] = YES if rng.random() < 0.25 else NO

    if sheet == SHEET_CONTINUING:
        row[COL_ALLOCATION_GROUP] = ALLOCATION_GROUP_STAYING
        row[COL_CURRENT_DORM_CODE] = code
        row[COL_CURRENT_ADDRESS] = f'בניין {rng.randint(1, 3)} דירה {rng.randint(1, 12)}'
        row[COL_STUDY_POINTS] = rng.choice([20, 35.5, 48, 62, 80, 97.5, 115, 132, 148, 160])
    else:
        row[COL_ALLOCATION_GROUP] = ALLOCATION_GROUP_NEW if rng.random() < 0.85 else ALLOCATION_GROUP_NEW_LATE
        row[COL_STUDY_POINTS] = 0

    # Accessibility cases are imported and left to the assisted workbench.
    if rng.random() < 0.05:
        row[COL_ALLOCATION_GROUP] = ALLOCATION_GROUP_ACCESSIBILITY
        row[COL_ACCESSIBILITY] = YES
        row[COL_DISABILITY_PERCENT] = rng.choice([20, 40, 60, 100])

    # ANIR students exist only in the dorm type that has the reserved
    # population; the importer injects the marker from this column.
    if code == 15 and rng.random() < 0.3:
        row[COL_ANIER] = 'X'

    # Other priority populations arrive as special-status descriptions.
    if rng.random() < 0.08:
        row[COL_SPECIAL_STATUS_1] = 'עתודאי'

    return row


def _add_roommate_requests(rng, rows):
    """
    Mutual pairs (both students name each other) plus a few one-sided
    requests, always between single students of the same housing type and
    dorm type, so the request is one the solver can actually honour.
    """
    candidates = {}
    for row in rows:
        if row[COL_TENANT_TYPE] in ('Z1', 'Z2') and not row[COL_ACCESSIBILITY]:
            key = (row[COL_TENANT_TYPE], row[COL_DECISION_DORM_CODE])
            candidates.setdefault(key, []).append(row)

    mutual_pairs = 0
    one_sided = 0
    for key in sorted(candidates):
        group = candidates[key]
        rng.shuffle(group)
        while len(group) >= 2 and mutual_pairs < 6:
            first, second = group.pop(), group.pop()
            for row, partner in ((first, second), (second, first)):
                row[COL_ROOMMATE_FLAG_1] = YES
                row[COL_ROOMMATE_NAME_1] = _full_name(partner)
                row[COL_ROOMMATE_ID_1] = partner[COL_STUDENT_ID]
            mutual_pairs += 1
        while len(group) >= 2 and one_sided < 2:
            row, partner = group.pop(), group[-1]
            row[COL_ROOMMATE_FLAG_1] = YES
            row[COL_ROOMMATE_NAME_1] = _full_name(partner)
            row[COL_ROOMMATE_ID_1] = partner[COL_STUDENT_ID]
            one_sided += 1
    return mutual_pairs, one_sided


def build_workbook_rows(count=DEFAULT_COUNT, seed=DEFAULT_SEED):
    """
    Return {sheet name: [row dict]} for `count` students. Rows are keyed by
    the importer's column headers. Deterministic for a given seed/count.
    """
    if count < 1:
        raise ValueError('count must be at least 1')
    rng = random.Random(seed)

    leaving_count = max(1, count // 25) if count >= 10 else 0
    allocation_count = count - leaving_count
    continuing_count = round(allocation_count * 0.4)

    rows_by_sheet = {SHEET_CONTINUING: [], SHEET_NEW: [], SHEET_LEAVING: []}
    index = 1
    for _ in range(continuing_count):
        rows_by_sheet[SHEET_CONTINUING].append(_student_row(rng, index, sheet=SHEET_CONTINUING))
        index += 1
    for _ in range(allocation_count - continuing_count):
        rows_by_sheet[SHEET_NEW].append(_student_row(rng, index, sheet=SHEET_NEW))
        index += 1
    for _ in range(leaving_count):
        row = _student_row(rng, index, sheet=SHEET_CONTINUING)
        row[COL_ALLOCATION_GROUP] = ''
        row[COL_ACCESSIBILITY] = ''
        row[COL_DISABILITY_PERCENT] = ''
        rows_by_sheet[SHEET_LEAVING].append(row)
        index += 1

    _add_roommate_requests(rng, rows_by_sheet[SHEET_CONTINUING] + rows_by_sheet[SHEET_NEW])
    return rows_by_sheet


def write_workbook(rows_by_sheet, path):
    """Write the sheets to `path` (.xlsx), creating the parent directory."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    workbook = Workbook()
    workbook.remove(workbook.active)
    for sheet_name, rows in rows_by_sheet.items():
        sheet = workbook.create_sheet(title=sheet_name)
        sheet.append(COLUMNS)
        for row in rows:
            sheet.append([row[column] if row[column] != '' else None for column in COLUMNS])
    workbook.save(path)
    return path


def summarize(rows_by_sheet):
    """Human-readable counts for the console."""
    all_rows = [row for rows in rows_by_sheet.values() for row in rows]
    lines = [f'{len(all_rows)} students: ' + ', '.join(
        f'{len(rows)} in "{sheet}"' for sheet, rows in rows_by_sheet.items()
    )]
    housing = {}
    dorms = {}
    for row in all_rows:
        housing[row[COL_TENANT_TYPE]] = housing.get(row[COL_TENANT_TYPE], 0) + 1
        dorms[row[COL_DECISION_DORM_CODE]] = dorms.get(row[COL_DECISION_DORM_CODE], 0) + 1
    lines.append('housing types: ' + ', '.join(f'{key} {housing[key]}' for key in sorted(housing)))
    lines.append('dorm codes: ' + ', '.join(f'{key} {dorms[key]}' for key in sorted(dorms)))
    lines.append(
        f'accessibility {sum(1 for r in all_rows if r[COL_ACCESSIBILITY])}, '
        f'ANIR {sum(1 for r in all_rows if r[COL_ANIER])}, '
        f'special status {sum(1 for r in all_rows if r[COL_SPECIAL_STATUS_1])}, '
        f'religious placement {sum(1 for r in all_rows if r[COL_RELIGIOUS] == YES)}, '
        f'roommate requests {sum(1 for r in all_rows if r[COL_ROOMMATE_FLAG_1])}'
    )
    return '\n'.join(lines)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description='Generate a synthetic student workbook for the Dormify Excel import.',
    )
    parser.add_argument('--count', type=int, default=DEFAULT_COUNT,
                        help=f'number of students including leaving rows (default {DEFAULT_COUNT})')
    parser.add_argument('--seed', type=int, default=DEFAULT_SEED,
                        help=f'random seed; the same seed and count give the same workbook (default {DEFAULT_SEED})')
    parser.add_argument('--output', type=Path, default=DEFAULT_OUTPUT,
                        help=f'.xlsx path to write (default {DEFAULT_OUTPUT})')
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    if args.count < 1:
        print('error: --count must be at least 1', file=sys.stderr)
        return 2
    rows_by_sheet = build_workbook_rows(count=args.count, seed=args.seed)
    path = write_workbook(rows_by_sheet, args.output)
    print(f'Wrote {path}')
    print(summarize(rows_by_sheet))
    return 0


if __name__ == '__main__':
    sys.exit(main())
