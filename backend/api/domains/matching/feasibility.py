"""
Match-feasibility helpers shared by the request match-options and
feasibility endpoints: the single student-level blocker and the empty /
reason shapes of a find_matching_room_options result.
"""

from ...models import Student


def student_assignment_blocker(student):
    """
    Single student-level reason this student cannot be matched to *any*
    room at all, checked once before scanning candidate rooms. Without
    this, a student missing housing_type/region would have the exact same
    conflict reason repeated on every single candidate room in the result
    set - this returns one (field, message) pair instead so the caller can
    show a single blocking message. None when nothing blocks.
    """
    if student.category == Student.StudentCategory.LEAVING:
        return 'category', 'הסטודנט/ית בקטגוריית עוזבים ואינו/ה זכאי/ת לשיבוץ.'
    if not student.housing_type or student.housing_type not in Student.HousingType.values:
        return 'housing_type', 'לא ניתן לבצע שיבוץ: חסר סוג דיור בפרטי הסטודנט.'
    if not student.accepted_dorm_type_id:
        return 'region', 'לא ניתן לבצע שיבוץ: חסר אזור/סוג מעונות בפרטי הסטודנט.'
    return None


def empty_match_payload(limit, offset):
    """Zero-result shell in the exact shape of find_matching_room_options."""
    return {
        'buildings': [], 'loaded_buildings': 0,
        'total_buildings': 0, 'total_apartments': 0, 'total_rooms': 0,
        'total_valid_beds': 0, 'total_valid': 0,
        'limit': limit, 'offset': offset,
        'has_more': False, 'next_offset': None,
        'conflict_examples': [], 'counts': None, 'data_integrity': None,
    }


def match_infeasibility_reason(result, fallback):
    """
    Human reason for an infeasible result, surfacing a Bed-record
    data-integrity problem explicitly instead of a generic 'nothing
    found'. Empty when the result has at least one valid bed.
    """
    if result['total_valid_beds'] > 0:
        return ''
    di = result.get('data_integrity') or {}
    if di.get('missing_bed_records'):
        return (
            fallback +
            ' שים לב: קיימים חדרים עם קיבולת פנויה אך ללא רשומות מיטה במסד הנתונים '
            '(בעיית נתונים) - נדרשת פעולת אתחול מיטות ייעודית (manage.py materialize_beds).'
        )
    return fallback
