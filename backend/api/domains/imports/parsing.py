"""
Excel student-import parsing, normalization, and spreadsheet-to-student
payload mapping.
"""

import re
from decimal import Decimal, InvalidOperation

import pandas as pd

from ...model_metadata import _get_model_field_names
from ...models import DormType, Student


# Legacy/demo-file name aliases. Every alias resolves to the official
# DormType.code, never to a database primary key and never to an arbitrary
# "first dorm in region" row.
EXCEL_DORM_NAME_TO_OFFICIAL_CODE = {
    'ריפקין': 1,
    'קנדה': 2,
    'מעונות קנדה': 2,
    'קסל': 3,
    'זוגות': 4,
    'מזרח ישן': 5,
    'נווה אמריקה': 6,
    'סנט': 7,
    'משפחות': 8,
    'יחיד בחדר': 10,
    'עליון עמים': 11,
    'מזרח חדש': 12,
    'סגל זוטר': 13,
    'כפר משתלמים': 14,
    'כפר הסמכה': 15,
    'רות הכהן': 16,
    'ברושים': 17,
    'סנט חדש': 18,
}

# Real dorm-office sheets that should not enter allocation.
LEAVING_SHEET_NAMES = {'עוזבים'}

# Column aliases: supports both the old demo Excel and the real dorm-office Excel.
COLUMN_ALIASES = {
    'student_id': ['ת"ז ישראלית'],
    'business_partner_id': ['שותף עסקי'],
    'first_name': ['שם פרטי'],
    'last_name': ['שם משפחה'],
    'phone': ['טלפון 1'],
    'phone_secondary': ['טלפון חירום', 'טלפון 2'],
    'email': ['אימייל 1'],
    'email_secondary': ['אימייל 2'],
    'city': ['שם ישוב'],

    'gender': ['תיאור מגדר'],
    'housing_type': ['תיאור סוג מגורים', 'החלטה-תאור סוג מגורים'],
    'tenant_type': ['החלטה-סוג מגורים של הדייר'],

    'decision_status': [
        'החלטת מעונות - אביב',
        'החלטה-החלטת מעונות - תאור',
        'גריעה/תוספת-תיאור קוד החלטה',
        'גריעה/תוספת-סוג החלטה',
    ],
    'decision_dorm_code': [
        'אזור החלטה לאביב',
        'החלטה-תוכן החלטה – מעונות',
        'החלטה-תוכן החלטה - מעונות',
        'החלטה-תוכן החלטה מעונות',
        'גריעה/תוספת-תוכן ההחלטה',
    ],
    'decision_dorm_name': [
        'גריעה/תוספת-תוכן ההחלטה-תיאור',
        'גריעה/תוספת-תוכן החלטה-תיאור',
        'גריעה/תוספת-תוכן החלטה-סוג',
    ],
    'current_dorm_code': ['אזור מגורים נוכחי'],
    'current_address': ['כתובת במעונות נוכחית', 'כ.נוכחית-כתובת במעונות-תיאור'],

    'religion': [
        'תיאור קוד לאום מבוקש',
        'החלטה-תאור קוד לאום מבוקש',
        'החלטה-קוד לאום מבוקש',
    ],
    'religious': [
        'החלטה אחרונה - דתי לצורך שיבוץ תיאור',
        'החלטה אחרונה - דתי לצרכי שיבוץ',
    ],
    'allocation_group': [
        'תיאור קבוצת הקצאה',
        'קבוצת הקצאה',
        'החלטה-תאור קבוצת הקצאה',
        'החלטה-קבוצת הקצאה',
    ],

    'accessibility_flag': ['החלטה-זקוק להנגשה'],
    'disability_percent': ['%נכות'],
    'medical_reason': ['סיבה רפואית מאושרת מרופאת הטכניון'],
    'anier_flag': ['9108-אנייר'],

    'roommate_flag_1': ['בקשה לגור עם סטודנטים חבר1'],
    'roommate_flag_2': ['החלטה אחרונה: בקשה לגור עם סטודנטים חבר2'],
    'roommate_flag_3': ['החלטה אחרונה: בקשה לגור עם סטודנטים חבר3'],
    'roommate_flag_4': ['החלטה אחרונה: בקשה לגור עם סטודנטים חבר4'],
    'roommate_flag_5': ['החלטה אחרונה: בקשה לגור עם סטודנטים חבר5'],
    'roommate_name_1': ['החלטה אחרונה: שם חבר 1'],
    'roommate_name_2': ['החלטה אחרונה: שם חבר 2'],
    'roommate_name_3': ['החלטה אחרונה: שם חבר 3'],
    'roommate_name_4': ['החלטה אחרונה: שם חבר 4'],
    'roommate_name_5': ['החלטה אחרונה: שם חבר 5'],
    'roommate_id_1': ['החלטה אחרונה: תז חבר 1', 'ת"ז חבר 1', 'מספר סטודנט חבר 1'],
    'roommate_id_2': ['החלטה אחרונה: תז חבר 2', 'ת"ז חבר 2', 'מספר סטודנט חבר 2'],
    'roommate_id_3': ['החלטה אחרונה: תז חבר 3', 'ת"ז חבר 3', 'מספר סטודנט חבר 3'],
    'roommate_id_4': ['החלטה אחרונה: תז חבר 4', 'ת"ז חבר 4', 'מספר סטודנט חבר 4'],
    'roommate_id_5': ['החלטה אחרונה: תז חבר 5', 'ת"ז חבר 5', 'מספר סטודנט חבר 5'],

    'special_status_1': ['תאור סטטוס מיוחד1'],
    'special_status_2': ['תאור סטטוס מיוחד2'],
    'special_status_3': ['תאור סטטוס מיוחד3'],
    'special_status_4': ['תאור סטטוס מיוחד4'],
    'study_points': ['נ.אקדמי מצטבר'],
}


def is_blank(value):
    if value is None:
        return True
    try:
        if pd.isna(value):
            return True
    except Exception:
        pass
    return str(value).strip() == ''


def safe_str(value, default=''):
    if is_blank(value):
        return default

    if isinstance(value, float):
        if value.is_integer():
            return str(int(value))
        return str(value).strip()

    return str(value).strip()


def safe_int(value, default=0):
    if is_blank(value):
        return default
    try:
        return int(float(value))
    except Exception:
        return default


def safe_decimal(value, default=None):
    if is_blank(value):
        return default
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return default


def normalize_compact(value):
    """Normalize text for comparisons where spaces are unreliable in the Excel."""
    return re.sub(r'\s+', '', safe_str(value)).lower()


def get_row_value(row, *column_names, default=''):
    for column_name in column_names:
        if column_name in row.index:
            value = row.get(column_name)
            if not is_blank(value):
                return value
    return default


def get_alias_value(row, alias_key, default=''):
    return get_row_value(row, *COLUMN_ALIASES.get(alias_key, []), default=default)


def normalize_phone(value):
    value = safe_str(value)
    if not value:
        return ''

    value = value.replace('-', '').replace(' ', '').replace('.0', '')

    if value.startswith('972') and len(value) >= 11:
        value = '0' + value[3:]

    return value


def parse_yes_no_code(value):
    value = normalize_compact(value)

    if value in {'כן', 'yes', 'true', '1', 'x', 'v', 'y'}:
        return True

    return False


def extract_roommate_flag(value):
    return parse_yes_no_code(value)


STUDENT_HOUSING_CODE_MAP = {
    'z1': Student.HousingType.SINGLE_MALE,
    'z2': Student.HousingType.SINGLE_FEMALE,
    'z3': Student.HousingType.COUPLE,
    'z4': Student.HousingType.FAMILY,
    'z6': Student.HousingType.SINGLE_IN_APARTMENT,
}


def normalize_student_housing_type(housing_type='', tenant_type=''):
    """Return only values supported by Student.HousingType."""
    housing_description = safe_str(housing_type)
    tenant_type_code = normalize_compact(tenant_type)

    mapped_value = STUDENT_HOUSING_CODE_MAP.get(tenant_type_code)
    if mapped_value:
        return mapped_value

    normalized_description = normalize_compact(housing_description)
    if not normalized_description:
        return ''

    # Check the mixed-single value before the male/female single values.
    if (
        'רווקים/ות' in normalized_description
        or 'רווקיםות' in normalized_description
        or 'singlemixed' in normalized_description
    ):
        return Student.HousingType.SINGLE_IN_APARTMENT

    if 'משפח' in normalized_description or 'family' in normalized_description:
        return Student.HousingType.FAMILY

    if 'זוג' in normalized_description or 'couple' in normalized_description:
        return Student.HousingType.COUPLE

    if 'רווקות' in normalized_description or 'בנות' in normalized_description:
        return Student.HousingType.SINGLE_FEMALE

    if 'רווקים' in normalized_description or 'בנים' in normalized_description:
        return Student.HousingType.SINGLE_MALE

    # Do not store values outside Student.HousingType.choices.
    return ''


def parse_explicit_gender(value):
    """Parse a real male/female value when the Excel explicitly provides one."""
    value_norm = normalize_compact(value)

    if value_norm in {'זכר', 'בנים', 'בן', 'male', 'man', 'men', 'm'}:
        return Student.Gender.MALE

    if value_norm in {'נקבה', 'בנות', 'בת', 'female', 'woman', 'women', 'f'}:
        return Student.Gender.FEMALE

    return None


def _housing_type_does_not_require_gender(housing_type):
    """Z3, Z4 and Z6 are allocated by housing type, not resident gender."""
    return housing_type in {
        Student.HousingType.COUPLE,
        Student.HousingType.FAMILY,
        Student.HousingType.SINGLE_IN_APARTMENT,
    }


def _gender_field_supports_empty_value():
    """Return True only after the nullable-gender model migration is applied."""
    gender_field = Student._meta.get_field('gender')
    return bool(gender_field.null or gender_field.blank)


def validate_gender_model_for_housing_import():
    """
    Fail early instead of silently importing only Z1/Z2.

    Z3/Z4/Z6 may legitimately have no gender value in the additions workbook,
    so the deployed Student.gender field must accept NULL/blank.
    """
    if not _gender_field_supports_empty_value():
        raise RuntimeError(
            'Student.gender is still NOT NULL. Update the model to null=True, '
            'blank=True and apply the migration before importing Z3/Z4/Z6.'
        )


def gender_value_is_valid_for_import(value, housing_type):
    """Validate only what the housing business rules actually require."""
    if value not in (None, ''):
        return True

    if _housing_type_does_not_require_gender(housing_type):
        return _gender_field_supports_empty_value()

    return False


def parse_gender_from_housing_type(
    housing_type,
    tenant_type='',
    explicit_gender='',
    existing_student=None,
):
    """
    Resolve Student.gender without confusing resident gender with apartment type.

    - Preserve an explicit Excel gender when present.
    - Preserve an existing student's real gender.
    - Z1 implies male and Z2 implies female.
    - Z3, Z4 and Z6 do not need gender for allocation, so NULL is valid.
    """
    parsed_explicit_gender = parse_explicit_gender(explicit_gender)
    if parsed_explicit_gender is not None:
        return parsed_explicit_gender

    if existing_student and getattr(existing_student, 'gender', None) not in (None, ''):
        return existing_student.gender

    normalized_housing_type = normalize_student_housing_type(
        housing_type,
        tenant_type,
    )

    if normalized_housing_type == Student.HousingType.SINGLE_MALE:
        return Student.Gender.MALE

    if normalized_housing_type == Student.HousingType.SINGLE_FEMALE:
        return Student.Gender.FEMALE

    if _housing_type_does_not_require_gender(normalized_housing_type):
        return None

    return None


def parse_requested_religion(value):
    value = safe_str(value)
    value_norm = normalize_compact(value)

    if value_norm in {'יהודי', 'jewish'}:
        return Student.Religion.Jewish

    if value_norm in {'מוסלמי', 'מוסלמים', 'muslim', 'muslims'}:
        return Student.Religion.Muslim

    if value_norm in {'נוצרי', 'christian'}:
        return Student.Religion.Christian

    if value_norm in {'דרוזי', 'druze'}:
        return Student.Religion.Druze

    return Student.Religion.NOT_SPECIFIED


def parse_placement_sector(row):
    religion = parse_requested_religion(get_alias_value(row, 'religion', default=''))

    if religion == Student.Religion.Jewish:
        return Student.PlacementSector.JEWISH

    if religion in {
        Student.Religion.Muslim,
        Student.Religion.Christian,
        Student.Religion.Druze,
    }:
        return Student.PlacementSector.ARAB

    return Student.PlacementSector.UNKNOWN


def parse_religious(value):
    value_norm = normalize_compact(value)

    if value_norm in {'כן', 'דתי', 'religious', 'yes', 'true', '1'}:
        return Student.Religious.RELIGIOUS

    if value_norm in {'לא', 'לאמשנה', 'no', 'false', '0', 'nopreference'}:
        return Student.Religious.NO_PREFERENCE

    return Student.Religious.NOT_SPECIFIED


def parse_category(value, sheet_name=''):
    sheet_norm = normalize_compact(sheet_name)

    if sheet_norm == normalize_compact('עוזבים'):
        return Student.StudentCategory.LEAVING

    if sheet_norm == normalize_compact('מעברים'):
        return Student.StudentCategory.TRANSFER

    if sheet_norm == normalize_compact('נכנסים חדשים'):
        return Student.StudentCategory.NEW

    if sheet_norm == normalize_compact('נשארים'):
        return Student.StudentCategory.CONTINUING

    # Confirmed exact allocation-group ("החלטה-תאור קבוצת הקצאה") values
    # take priority over the generic substring heuristic below: the
    # staying/continuing value contains the substring 'חדשים' (it lists
    # veterans + new-who-were-disqualified-as-new), which the heuristic
    # would otherwise misread as StudentCategory.NEW.
    exact_category = allocation_group_category(value)
    if exact_category is not None:
        return exact_category

    value = safe_str(value)
    value_norm = normalize_compact(value)

    if any(x in value_norm for x in ['מעבר', 'מעברים', 'transfer']):
        return Student.StudentCategory.TRANSFER

    if any(x in value_norm for x in ['עזיבה', 'עוזב', 'leaving']):
        return Student.StudentCategory.LEAVING

    if any(x in value_norm for x in ['חדשים', 'חדש', 'new']):
        return Student.StudentCategory.NEW

    return Student.StudentCategory.CONTINUING


def get_decision_status(row):
    return safe_str(get_alias_value(row, 'decision_status', default=''))


def is_positive_decision(decision_status):
    if is_blank(decision_status):
        # Preserve old behavior: blank decision does not block import.
        return True
    return normalize_compact(decision_status) == normalize_compact('החלטה חיובית')


def get_decision_dorm_code(row):
    """Return the authoritative dorm/area code from the dorm-office Excel."""
    return safe_str(get_alias_value(row, 'decision_dorm_code', default=''))


def get_decision_dorm_name(row):
    """Return a human-readable dorm name where available; real file mostly uses numeric codes."""
    return safe_str(get_alias_value(row, 'decision_dorm_name', default=''))



# The dorm-office area number is the official DormType.code.
# It must never be translated through Django primary keys.


def _normalize_excel_area_code(code_value):
    """Normalize Excel dorm-office area codes such as 06 -> 6 and 2.0 -> 2."""
    code_text = safe_str(code_value)
    if not code_text:
        return ''

    code_int = safe_int(code_text, default=None)
    if code_int is not None:
        return str(code_int)

    return code_text.strip()


def _find_dorm_type_by_code(code_value):
    """Resolve a dorm strictly by its stable official DormType.code."""
    normalized_code = _normalize_excel_area_code(code_value)
    code_int = safe_int(normalized_code, default=None)

    if code_int is None:
        return None

    return DormType.objects.filter(
        code=code_int
    ).select_related('region').first()


def get_or_create_dorm_type_from_excel(dorm_code=None, dorm_name=None):
    """
    Resolve DormType without creating rows.

    A supplied dorm decision code is authoritative. When that field is present,
    resolution is performed only through DormType.code. It never falls back to
    a name, a region, or DormType.pk.

    Name/legacy-alias resolution is retained only for old files in which the
    dorm-code field itself is blank.
    """
    dorm_code_text = safe_str(dorm_code)
    if dorm_code_text:
        return _find_dorm_type_by_code(dorm_code_text)

    dorm_name = safe_str(dorm_name)
    if not dorm_name:
        return None

    dorm_type = DormType.objects.filter(
        name__iexact=dorm_name
    ).select_related('region').first()
    if dorm_type:
        return dorm_type

    alias_code = EXCEL_DORM_NAME_TO_OFFICIAL_CODE.get(
        normalize_compact(dorm_name)
    )
    if alias_code is not None:
        return _find_dorm_type_by_code(alias_code)

    return None


def read_accessibility_fields(row):
    """
    Read the raw accessibility/medical columns from the Excel row, exactly
    as imported — independent of whether they end up implying priority.
    """
    explicit_flag = parse_yes_no_code(get_alias_value(row, 'accessibility_flag', default=''))
    disability_percent = safe_decimal(get_alias_value(row, 'disability_percent', default=''), default=None)
    medical_reason = safe_str(get_alias_value(row, 'medical_reason', default=''))
    return explicit_flag, disability_percent, medical_reason


def is_accessibility_priority(row):
    explicit_flag, disability_percent, medical_reason = read_accessibility_fields(row)
    return explicit_flag or (disability_percent is not None and disability_percent > 0) or bool(medical_reason)


def _normalize_allocation_group_value(value):
    """
    Like normalize_compact, but additionally unifies dash characters
    (Excel exports mix '-', '–' and '—' inconsistently across identical
    category values) before whitespace-stripping/lowercasing.
    """
    text = safe_str(value).replace('–', '-').replace('—', '-')
    return normalize_compact(text)



# The Excel column name itself ("החלטה-תאור קבוצת הקצאה", aliased in
# COLUMN_ALIASES['allocation_group']) is kept separate from the cell
# VALUES it can contain below. Never compare a value against the column
# name — see test_allocation_group_header_is_not_treated_as_value.
ALLOCATION_GROUP_EXCEL_COLUMN_NAME = "החלטה-תאור קבוצת הקצאה"

# Confirmed exact allocation-group cell values. All students in this
# column are still sent to the solver EXCEPT the accessibility value —
# staying/continuing and new students are both re-allocated from scratch.
ALLOCATION_GROUP_VALUE_STAYING = "הסמכה – ותיקים+חדשים שנפסלו כחדשים+בינלאומי מלאות2"
ALLOCATION_GROUP_VALUES_NEW = (
    "הסמכה – חדשים",
    "מסיימי מכינה מאוחרים – שנה 1",
)
ALLOCATION_GROUP_VALUE_ACCESSIBILITY = "הסמכה - נכים"

_ALLOCATION_GROUP_STAYING_NORMALIZED = _normalize_allocation_group_value(ALLOCATION_GROUP_VALUE_STAYING)
_ALLOCATION_GROUP_NEW_NORMALIZED = {
    _normalize_allocation_group_value(value) for value in ALLOCATION_GROUP_VALUES_NEW
}

# Only 'הסמכה - נכים' marks a student as accessibility/disability. This is
# an exact-match whitelist, never a substring/bool(cell) rule — a value
# merely containing 'הסמכה' or 'נכים' as part of a longer, unrelated
# category name must NOT match.
ACCESSIBILITY_ALLOCATION_GROUP_VALUES = {
    _normalize_allocation_group_value(ALLOCATION_GROUP_VALUE_ACCESSIBILITY)
}


def allocation_group_indicates_accessibility(allocation_group_value):
    """
    True only when allocation_group_value exactly matches (after dash/
    whitespace/case normalization) one of the confirmed accessibility
    allocation-group category values in ACCESSIBILITY_ALLOCATION_GROUP_VALUES.
    """
    return _normalize_allocation_group_value(allocation_group_value) in ACCESSIBILITY_ALLOCATION_GROUP_VALUES


def allocation_group_category(allocation_group_value):
    """
    Exact-match staying/new classification for the confirmed
    allocation-group values, reusing the existing Student.category field
    (StudentCategory.CONTINUING/NEW) instead of a new database column.

    Returns None when allocation_group_value is not one of the confirmed
    staying/new values, so callers can fall back to the generic
    substring heuristic in parse_category() for other sheets/files.
    """
    normalized = _normalize_allocation_group_value(allocation_group_value)

    if normalized == _ALLOCATION_GROUP_STAYING_NORMALIZED:
        return Student.StudentCategory.CONTINUING

    if normalized in _ALLOCATION_GROUP_NEW_NORMALIZED:
        return Student.StudentCategory.NEW

    return None


def classify_allocation_group_bucket(allocation_group_value):
    """
    Non-persisted classification used only for import-summary logging
    (see upload_excel). Never stored on the Student model.
    """
    if allocation_group_indicates_accessibility(allocation_group_value):
        return 'accessibility'

    category = allocation_group_category(allocation_group_value)
    if category == Student.StudentCategory.CONTINUING:
        return 'staying'
    if category == Student.StudentCategory.NEW:
        return 'new'

    return 'other'


def priority_fields_from_special_statuses(*special_statuses):
    """
    is_priority/priority_reason are derived solely from special_status_1..4.
    Accessibility/medical data (is_accessibility_priority) is imported and
    preserved for the dorm office to allocate those students manually, but
    must never affect is_priority, the solver, priority score, clustering,
    or building rules.
    """
    non_empty = [status for status in special_statuses if status]
    return bool(non_empty), ' | '.join(non_empty)


def inject_special_status_marker(special_statuses, marker):
    """
    Insert `marker` into the first blank slot among the 4 special_status
    values, unless it is already present in one of them. Returns a new
    4-tuple.

    Some special-status signals (e.g. the 'אנייר' / anier group) arrive
    via their own dedicated raw Excel column ('9108-אנייר' == 'X'), not
    already embedded in the 'תאור סטטוס מיוחד1..4' description text the
    way הסמכה/עתודאי already are. Without this, _has_anier_special_status
    (and priority_fields_from_special_statuses) would never see the
    marker, even though the student was correctly flagged in the source
    file.
    """
    statuses = list(special_statuses)
    if any(marker in status for status in statuses if status):
        return tuple(statuses)
    for index, status in enumerate(statuses):
        if not status:
            statuses[index] = marker
            return tuple(statuses)
    # All four slots occupied: append rather than silently dropping the marker.
    statuses[-1] = f"{statuses[-1]} | {marker}"
    return tuple(statuses)


def filter_payload_to_student_fields(payload):
    """Avoid create/update errors if the model does not contain optional fields."""
    student_fields = _get_model_field_names(Student)
    return {key: value for key, value in payload.items() if key in student_fields}


def build_student_payload_from_row(row, existing_student=None, sheet_name=''):
    housing_type = safe_str(get_alias_value(row, 'housing_type', default=''))
    tenant_type = safe_str(get_alias_value(row, 'tenant_type', default=''))
    gender_text = safe_str(get_alias_value(row, 'gender', default=''))
    normalized_housing_type = normalize_student_housing_type(
        housing_type,
        tenant_type,
    )

    decision_dorm_code = get_decision_dorm_code(row)
    decision_dorm_name = get_decision_dorm_name(row)

    accepted_dorm_type = get_or_create_dorm_type_from_excel(
        decision_dorm_code,
        decision_dorm_name
    )

    # Accessibility/medical data is imported and stored on its own fields
    # (accessibility_flag/disability_percent/medical_reason) so the dorm
    # office can allocate these students manually. It must never feed
    # is_priority — see priority_fields_from_special_statuses below.
    accessibility_flag, disability_percent, medical_reason = read_accessibility_fields(row)
    placement_sector = parse_placement_sector(row)
    allocation_group_value = get_alias_value(row, 'allocation_group', default='')

    # Some allocation groups (e.g. 'הסמכה - נכים') mark accessibility even
    # when the explicit accessibility columns are blank for this row.
    if allocation_group_indicates_accessibility(allocation_group_value):
        accessibility_flag = True

    special_status_1 = safe_str(get_alias_value(row, 'special_status_1'))
    special_status_2 = safe_str(get_alias_value(row, 'special_status_2'))
    special_status_3 = safe_str(get_alias_value(row, 'special_status_3'))
    special_status_4 = safe_str(get_alias_value(row, 'special_status_4'))

    if parse_yes_no_code(get_alias_value(row, 'anier_flag', default='')):
        special_status_1, special_status_2, special_status_3, special_status_4 = (
            inject_special_status_marker(
                (special_status_1, special_status_2, special_status_3, special_status_4),
                'אנייר',
            )
        )

    is_priority, priority_reason = priority_fields_from_special_statuses(
        special_status_1, special_status_2, special_status_3, special_status_4,
    )

    current_dorm_type_value = (
        accepted_dorm_type.name
        if accepted_dorm_type
        else (decision_dorm_code or decision_dorm_name)
    )

    payload = {
        'student_id': safe_str(get_alias_value(row, 'student_id')),
        'first_name': safe_str(get_alias_value(row, 'first_name')),
        'last_name': safe_str(get_alias_value(row, 'last_name')),
        'phone': normalize_phone(get_alias_value(row, 'phone')),
        'phone_secondary': normalize_phone(get_alias_value(row, 'phone_secondary')),
        'email': safe_str(get_alias_value(row, 'email')),
        'city': safe_str(get_alias_value(row, 'city')),

        'gender': parse_gender_from_housing_type(
            normalized_housing_type,
            tenant_type=tenant_type,
            explicit_gender=gender_text,
            existing_student=existing_student,
        ),

        'requested_religion': parse_requested_religion(get_alias_value(row, 'religion', default='')),
        'placement_sector': placement_sector,
        'religious': parse_religious(get_alias_value(row, 'religious', default='')),
        'category': parse_category(allocation_group_value, sheet_name=sheet_name),

        'housing_type': normalized_housing_type,
        'allocation_group': safe_str(allocation_group_value),
        'accepted_dorm_type': accepted_dorm_type,

        'roommate_request_1': safe_str(get_alias_value(row, 'roommate_name_1')),
        'roommate_request_2': safe_str(get_alias_value(row, 'roommate_name_2')),
        'roommate_request_3': safe_str(get_alias_value(row, 'roommate_name_3')),
        'roommate_request_4': safe_str(get_alias_value(row, 'roommate_name_4')),
        'roommate_request_5': safe_str(get_alias_value(row, 'roommate_name_5')),

        'roommate_request_student_id_1': safe_str(get_alias_value(row, 'roommate_id_1')),
        'roommate_request_student_id_2': safe_str(get_alias_value(row, 'roommate_id_2')),
        'roommate_request_student_id_3': safe_str(get_alias_value(row, 'roommate_id_3')),
        'roommate_request_student_id_4': safe_str(get_alias_value(row, 'roommate_id_4')),
        'roommate_request_student_id_5': safe_str(get_alias_value(row, 'roommate_id_5')),

        'roommate_request_flag_1': extract_roommate_flag(get_alias_value(row, 'roommate_flag_1')),
        'roommate_request_flag_2': extract_roommate_flag(get_alias_value(row, 'roommate_flag_2')),
        'roommate_request_flag_3': extract_roommate_flag(get_alias_value(row, 'roommate_flag_3')),
        'roommate_request_flag_4': extract_roommate_flag(get_alias_value(row, 'roommate_flag_4')),
        'roommate_request_flag_5': extract_roommate_flag(get_alias_value(row, 'roommate_flag_5')),

        'special_status_1': special_status_1,
        'special_status_2': special_status_2,
        'special_status_3': special_status_3,
        'special_status_4': special_status_4,

        'study_points': safe_decimal(get_alias_value(row, 'study_points', default=''), default=None),
        'current_address': safe_str(get_alias_value(row, 'current_address', default='')),
        'current_dorm_type': current_dorm_type_value,

        'is_priority': is_priority,
        'priority_reason': priority_reason,

        'accessibility_flag': accessibility_flag,
        'disability_percent': disability_percent,
        'medical_reason': medical_reason,
    }

    optional_fields = {
        'business_partner_id': safe_str(get_alias_value(row, 'business_partner_id')),
        'email_secondary': safe_str(get_alias_value(row, 'email_secondary')),
        'current_dorm_code': safe_str(get_alias_value(row, 'current_dorm_code')),
        'accepted_dorm_code': decision_dorm_code,
    }

    payload.update(optional_fields)
    return filter_payload_to_student_fields(payload)

def get_additions_decision_status(row):
    """
    For additions file, use the final dorm decision status.
    We do not want to rely on gria/tosefet status if the final decision exists.
    """
    return safe_str(
        get_row_value(
            row,
            'החלטה-החלטת מעונות - תאור',
            default=''
        )
    )


def get_additions_decision_dorm_code(row):
    """
    In the additions file, the real dorm decision code is usually in
    the 'decision content - dorms' column.

    Important:
    Do NOT use company code columns like 3000 as dorm type code.
    """
    return safe_str(
        get_row_value(
            row,
            'החלטה-תוכן החלטה – מעונות',
            'החלטה-תוכן החלטה - מעונות',
            'החלטה-תוכן החלטה מעונות',
            'החלטה-תוכן החלטה מעונות-קוד',
            'אזור החלטה לאביב',
            default=''
        )
    )


def is_additions_positive_decision(row):
    decision_status = get_additions_decision_status(row)

    if is_blank(decision_status):
        return False

    return normalize_compact(decision_status) == normalize_compact('החלטה חיובית')


# ---------------------------------------------------------------------------
# Additions ("מתווספים") file helpers
# ---------------------------------------------------------------------------

ADDITIONS_HOUSING_CODE_MAP = STUDENT_HOUSING_CODE_MAP


def normalize_additions_housing_type(row):
    """Return one of the five canonical Student.HousingType values."""
    return normalize_student_housing_type(
        get_alias_value(row, 'housing_type', default=''),
        get_alias_value(row, 'tenant_type', default=''),
    )


def additions_housing_bucket(housing_type):
    """Return a stable import-summary bucket for a canonical housing value."""
    if housing_type == Student.HousingType.FAMILY:
        return 'family'
    if housing_type == Student.HousingType.COUPLE:
        return 'couple'
    if housing_type == Student.HousingType.SINGLE_IN_APARTMENT:
        return 'single_mixed'
    if housing_type == Student.HousingType.SINGLE_FEMALE:
        return 'single_female'
    if housing_type == Student.HousingType.SINGLE_MALE:
        return 'single_male'

    return 'unknown'
