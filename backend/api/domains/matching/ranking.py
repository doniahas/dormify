"""
Read-only candidate-room matching and ranking for student placement.
"""

from collections import defaultdict

from ...models import Apartment, BedAssignment, Room, Student, Transfer
from ..placement.rules import _z_compatibility


def _religion_group(religion):
    if religion == Student.Religion.Jewish:
        return 'jewish'
    if religion in (Student.Religion.Muslim, Student.Religion.Christian, Student.Religion.Druze):
        return 'arab'
    return 'unknown'


def _sector_group(placement_sector):
    """
    Coarse jewish/arab/other/unknown placement-sector bucket, independent of
    the finer-grained religion field - mirrors the allocation solver's
    sectorMatching signal (allocation/solver.py:_get_student_sector).
    placement_sector is a field staff set explicitly for placement purposes
    and can be more/less complete than requested_religion, so it is scored
    as its own distinct warning rather than folded into the religion check.
    """
    if placement_sector == Student.PlacementSector.JEWISH:
        return 'jewish'
    if placement_sector == Student.PlacementSector.ARAB:
        return 'arab'
    if placement_sector == Student.PlacementSector.OTHER:
        return 'other'
    return 'unknown'


def _year_group(study_points):
    """
    Coarse academic-year bucket used only to avoid mixing first-years with
    3rd/4th-years in the same apartment - mirrors the allocation solver's
    avoidYearMix signal (allocation/solver.py:_get_student_year_group).
    Missing/unset study_points is 'other' (unknown), never 0 - it must not
    be silently treated as a real, matchable year1 value.
    """
    if study_points is None or study_points == '':
        return 'other'
    try:
        points = float(study_points)
    except (TypeError, ValueError):
        return 'other'
    if 0 <= points <= 40:
        return 'year1'
    if points >= 60:
        return 'year3_4'
    return 'other'


def _student_transfer_history(student):
    """
    Real, stored historical signal (Transfer records) for this student -
    never invented, never inferred from unrelated behavior. Returns the set
    of dorm_type ids the student has previously *requested to move to*
    (any Transfer status - even a rejected/pending request shows real
    interest) and the set they've previously *requested to move away from*.
    Both are used only to explain an option, never to gate/exclude it.
    """
    if student is None or not getattr(student, 'pk', None):
        return {'requested_to': set(), 'requested_away_from': set()}

    transfers = Transfer.objects.filter(student=student).select_related(
        'to_room__apartment__building__dorm_type',
        'from_room__apartment__building__dorm_type',
    )
    requested_to = set()
    requested_away_from = set()
    for t in transfers:
        to_dorm_type_id = (
            t.to_room.apartment.building.dorm_type_id if t.to_room and t.to_room.apartment.building else None
        )
        from_dorm_type_id = (
            t.from_room.apartment.building.dorm_type_id if t.from_room and t.from_room.apartment.building else None
        )
        if to_dorm_type_id:
            requested_to.add(to_dorm_type_id)
        if from_dorm_type_id:
            requested_away_from.add(from_dorm_type_id)
    return {'requested_to': requested_to, 'requested_away_from': requested_away_from}


def _infer_housing_type(student_data):
    """Best-effort mapping from the Add-Student wizard's loose dorm_type hint
    ('couples' / 'single') + gender into a real Student.HousingType value."""
    dorm_hint = (student_data.get('dorm_type') or student_data.get('housing_type') or '').strip().lower()
    gender = student_data.get('gender')

    if dorm_hint in ('couples', 'couple', 'זוגות'):
        return Student.HousingType.COUPLE
    if dorm_hint in ('single', 'בודדים', 'רווקים', 'רווקות', 'רווקים/ות בדירה'):
        return Student.HousingType.SINGLE_FEMALE if gender == 'female' else Student.HousingType.SINGLE_MALE

    if gender == 'female':
        return Student.HousingType.SINGLE_FEMALE
    if gender == 'male':
        return Student.HousingType.SINGLE_MALE
    return ''


# ---------------------------------------------------------------------------
# Central match-scoring configuration - single source of truth for §3.
#
# These weights mirror the *relative* importance already established by the
# allocation solver's SOFT_ALLOCATION_CONSTRAINTS (allocation/solver.py):
# roommateMatch=8 is its strongest soft signal, followed by
# sectorMatching=7, sameReligion=6, and avoidYearMix=4 (its weakest default
# soft signal). The solver has no existing weight split for "mutual" vs
# "one-sided" roommate requests specifically - its fixtures (e.g.
# case_02_soft_tradeoff_one_sided_bad_roommate) only establish that a
# one-sided request is a weaker signal than a mutual one. That split is
# therefore defined explicitly here, once, rather than as a magic number
# inside the scoring loop.
# ---------------------------------------------------------------------------
MATCH_SCORE_WEIGHTS = {
    'base': 50,
    'roommate_match_mutual': 35,
    'roommate_match_one_sided': 15,
    'roommate_future_capacity': 10,
    'preferred_dormitory': 14,
    'empty_apartment': 15,
    'religion_compatible': 10,
    'religion_conflict_penalty': -15,
    'sector_compatible': 12,
    'sector_conflict_penalty': -18,
    'year_mix_penalty': -8,
    'city_match': 8,
    'priority_student_bonus': 5,
    'history_bonus': 4,
}
BEST_MATCH_SCORE_THRESHOLD = 70
# The numeric score above is sort/threshold plumbing ONLY - it is never sent
# to the frontend. Every reason attached to an option (matched/warning/
# historical) is a (code, label) pair from this table, so the UI can render
# "why", never a percentage. recommendation_level is the only thing the
# client sees for ranking, mapped from match_level (itself derived from the
# score) via RECOMMENDATION_LEVEL_MAP below.
REASON_LABELS = {
    'mutual_roommate_request': 'בקשת שותפים הדדית',
    'roommate_already_here': 'השותף המבוקש כבר משובץ בדירה זו',
    'roommate_future_capacity': 'בדירה קיימות שתי מיטות פנויות עבור שני השותפים',
    'preferred_dormitory': 'המעון נמצא בעדיפות הסטודנט',
    'empty_apartment': 'דירה ריקה - ללא סיכון התאמה',
    'religion_match': 'התאמה דתית/עדתית',
    'religion_conflict': 'בדירה יש דיירים מקבוצה דתית שונה',
    'sector_match': 'התאמת סקטור שיבוץ',
    'sector_conflict': 'בדירה יש דיירים מסקטור שיבוץ שונה',
    'year_mix_conflict': 'ערבוב שנתונים בדירה (שנה א׳ עם שנה ג׳-ד׳)',
    'city_match': 'התאמת עיר מגורים',
    'priority_student': 'סטודנט/ית בעדיפות',
    'roommate_incompatible_hard_rule': 'השותף המבוקש נמצא בדירה זו, אך קיים חוסר התאמה בדרישות חובה',
    'previously_requested_dormitory': 'הסטודנט/ית ביקש/ה בעבר מעון זה',
    'previously_transferred_away': 'הסטודנט/ית ביקש/ה בעבר לעבור ממעון זה',
}

RECOMMENDATION_LEVEL_MAP = {
    'best_match': ('best', 'ההתאמה המומלצת ביותר', 4),
    'empty': ('good', 'התאמה טובה', 3),
    'valid': ('valid', 'אפשרות תקינה', 2),
    'warning': ('warning', 'אפשרות עם אזהרות', 1),
    'conflict': ('unavailable', 'לא זמין', 0),
}


def _reason(code):
    return {'code': code, 'label': REASON_LABELS[code]}


# Assisted Allocation's own 3-tier classification (find_matching_room_options
# assisted_mode=True) - distinct from the 5-level recommendation_level/
# match_level scheme above, which stays unchanged for the Students/Transfers
# pages that also call find_matching_room_options. 'possible' covers what
# match_level calls 'valid' and 'warning' (a soft, non-blocking mismatch -
# e.g. sector/year-mix - is still a directly assignable candidate, just a
# lower-ranked one); 'override_required' is its own tier because that bed is
# NOT directly assignable - it requires the explicit override flow.
ASSISTED_STATUS_LABELS = {
    'recommended': 'מומלץ',
    'possible': 'אפשרי',
    'override_required': 'דורש חריגה',
}
ASSISTED_STATUS_SORT_RANK = {'recommended': 0, 'possible': 1, 'override_required': 2}

MAX_CONFLICT_EXAMPLES = 5
MAX_CONFLICT_BUFFER = 50
# Rooms whose only problem is "no free bed" are a far more useful diagnostic
# sample than rooms that are also the wrong gender/housing type for this
# student - a female student looking at "male apartment 1 is full" learns
# nothing. _conflict_priority ranks type/gender-mismatched rooms last so the
# sample favors "same category as the student, just full" whenever any exist.
_TYPE_OR_GENDER_MISMATCH_REASONS = {
    'אי-התאמת סוג הדירה לסוג הדיור של הסטודנט',
    'אי-התאמת מגדר/קטגוריית הדירה',
    'לסטודנט אין סוג דיור נתמך לשיבוץ',
    'הדירה שמורה בלעדית לדייר/ת בשיבוץ רווקים/ות בדירה',
    'נדרשת דירת זוגות עבור שיבוץ מסוג רווקים/ות בדירה',
}


def _conflict_priority(conflicts):
    has_type_or_gender_mismatch = any(c in _TYPE_OR_GENDER_MISMATCH_REASONS for c in conflicts)
    return (has_type_or_gender_mismatch, len(conflicts))


def _classify_match_level(score, warnings, conflicts, is_empty=False):
    """Single source of truth for match_level, used both when tallying
    filter-chip counts over every valid bed and when building the display
    dict for the handful actually returned - keeps the two in sync.

    'empty' is its own top-level category (a zero-resident apartment carries
    no compatibility risk at all - safer than any occupied "best_match")
    rather than folding into 'best_match' as before, where a plain empty
    apartment with no other bonus (no roommate/city/priority match) scored
    exactly 65 - below BEST_MATCH_SCORE_THRESHOLD - and was silently
    downgraded to 'valid'."""
    if conflicts:
        return 'conflict'
    if is_empty:
        return 'empty'
    if score >= BEST_MATCH_SCORE_THRESHOLD and not warnings:
        return 'best_match'
    if warnings:
        return 'warning'
    return 'valid'


def _room_conflicts(student, room, apartment, residents, available_beds):
    """
    Hard-constraint (CONFLICT) reasons for a candidate room, computed only
    from already-fetched data - no DB queries. Mirrors
    validate_apartment_assignment's policy via the shared _z_compatibility
    table so the two never drift apart, but returns every violation reason
    instead of raising on the first one, since the matching engine has to
    classify every candidate room, not just validate a single chosen one.
    """
    reasons = []

    if not room.is_active:
        reasons.append('החדר אינו פעיל')
    if not apartment.is_active:
        reason = apartment.get_inactive_reason_display() if apartment.inactive_reason else 'לא פעילה'
        reasons.append(f'הדירה אינה פעילה ({reason})')
    if not apartment.building.is_active:
        reasons.append('הבניין אינו פעיל')

    if available_beds <= 0:
        reasons.append('אין מיטות פנויות בחדר - תפוסה מלאה')

    other_residents = [r for r in residents if r['id'] != getattr(student, 'id', None)]

    if student.housing_type == Student.HousingType.SINGLE_IN_APARTMENT:
        if apartment.apartment_type != Apartment.ApartmentType.COUPLE:
            reasons.append('נדרשת דירת זוגות עבור שיבוץ מסוג רווקים/ות בדירה')
        if other_residents:
            reasons.append('הדירה תפוסה - נדרשת דירה ריקה לחלוטין')
        return reasons

    if any(r['housing_type'] == Student.HousingType.SINGLE_IN_APARTMENT for r in other_residents):
        reasons.append('הדירה שמורה בלעדית לדייר/ת בשיבוץ רווקים/ות בדירה')

    expected = _z_compatibility(student.housing_type)
    if expected is None:
        reasons.append('לסטודנט אין סוג דיור נתמך לשיבוץ')
    else:
        from ..allocation.gateway import _effective_apartment_category

        expected_type, expected_category = expected
        if apartment.apartment_type != expected_type:
            reasons.append('אי-התאמת סוג הדירה לסוג הדיור של הסטודנט')
        # Effective category: a building-wide gender_restriction (shared-
        # facility buildings) overrides a possibly wrong/conflicting
        # individual apartment category - mirrors
        # allocation.manual_placement.evaluate_manual_override so browsing
        # and the override-confirmation dialog never disagree about which
        # rooms are gender-compatible.
        if _effective_apartment_category(apartment) != expected_category:
            reasons.append('אי-התאמת מגדר/קטגוריית הדירה')

    return reasons


def _room_candidate_queryset(user, region_id=None, region_ids=None):
    """
    Region-scoped, active-only candidate rooms. `region_id` (single) or
    `region_ids` (cross-region transfer: one or more destination regions)
    let a central admin explicitly target regions; a regional user is
    always confined to their own region regardless of what is passed in,
    so a client can never widen its own scope by sending region ids.
    """
    queryset = Room.objects.select_related(
        'apartment',
        'apartment__building',
        'apartment__building__dorm_type',
        'apartment__building__dorm_type__region',
    ).filter(
        is_active=True,
        apartment__is_active=True,
        apartment__building__is_active=True,
    )

    if user.is_central_admin:
        if region_ids:
            queryset = queryset.filter(apartment__building__dorm_type__region_id__in=region_ids)
        elif region_id:
            queryset = queryset.filter(apartment__building__dorm_type__region_id=region_id)
    else:
        if not user.region_id:
            return queryset.none()
        queryset = queryset.filter(apartment__building__dorm_type__region_id=user.region_id)

    return queryset


def find_matching_room_options(
    user, student=None, student_data=None, same_apartment=None,
    region_id=None, region_ids=None, limit=10, offset=0, explain_conflicts_if_empty=True,
    assisted_mode=False,
):
    """
    Real, currently-available placement options for a student (existing, or
    a not-yet-created student described by student_data), returned as a
    building-paged hierarchy:

        buildings[] -> apartments[] -> rooms[] -> beds[]

    This is the single reusable matching service - assign, reassign,
    room/apartment requests and add-student allocation all call this instead
    of re-implementing matching logic.

    READ-ONLY GUARANTEE: browsing/matching never writes to the database.
    Only real, existing Bed rows are ever offered as selectable; a room
    whose configured capacity says "free" but that has no free real Bed row
    contributes zero selectable beds and is reported under `data_integrity`
    in the response instead of triggering any row creation. Materializing
    Bed rows from room capacity is an explicit, admin-only operation
    (manage.py materialize_beds) and is never run from here.

    PAGINATION UNIT IS THE BUILDING (by primary key, never by the reusable
    building *number*): `offset`/`limit` count buildings, and every building
    on the returned page carries its complete apartment/room/bed subtree, so
    the client can always expand exactly what it received - there are no
    partial parents. Buildings are ordered by their best apartment's
    (roommate_tier, score); the tier implements the required roommate
    ranking lexicographically, so no combination of soft preferences can
    ever outrank a higher roommate tier:

        3 - mutual roommate request, roommate already assigned here
        2 - one-sided roommate request, roommate already assigned here
        1 - mutual roommate request, roommate unassigned anywhere, and this
            apartment has free capacity for both students
        0 - no roommate signal (score refines: preferred dormitory, then
            the other soft preferences)

    Hard constraints (gender/housing type/capacity/active flags/region
    scoping via the queryset) always exclude a room entirely - they are
    never outrankable by any preference.

    Occupancy is always computed from the real active BedAssignment rows
    (never from the Room record alone), so a two-bed room with one occupied
    bed is "one free", not "full", and only the actually-free bed is
    selectable.

    The numeric score is internal plumbing only - the response never
    contains a score or percentage, only recommendation_level/label (fixed
    tiers) plus matched_reasons/warnings/historical_reasons as {code,label}
    pairs.

    assisted_mode: used only by the Assisted Allocation workbench
    (assisted_allocation_recommendations). When True:
      - candidates are hard-restricted to the student's own
        accepted_dorm_type (never merely the region) - staying inside the
        dorm type the student was actually accepted to is a business rule,
        not a preference, so it is enforced unconditionally here (including
        for is_priority students - unlike the automatic solver's own
        _should_enforce_accepted_dorm_type bypass, which is intentionally
        left untouched for automatic runs). A student with no
        accepted_dorm_type_id yields zero candidates rather than an
        unrestricted region-wide scan.
      - each apartment additionally carries assisted_status
        ('recommended' | 'possible' | 'override_required') and
        override_violations - the same {code,label,overridable,consequence}
        shape allocation.manual_placement.evaluate_manual_override returns,
        computed from the residents/data already fetched here (no extra
        queries) so a bed needing a documented override is visibly
        distinguished from a normal recommendation instead of only
        surfacing at assign-time.
    """
    student_data = student_data or {}
    current_room = None

    if student is not None and student.pk:
        current_room = student.assigned_room
    elif student is None:
        student = Student(
            gender=student_data.get('gender') or '',
            housing_type=student_data.get('housing_type') or _infer_housing_type(student_data),
            requested_religion=(
                student_data.get('requested_religion')
                or student_data.get('religion')
                or Student.Religion.NOT_SPECIFIED
            ),
            city=student_data.get('city', ''),
            is_priority=bool(student_data.get('is_priority')),
        )

    current_apartment_id = current_room.apartment_id if current_room else None

    rooms_qs = _room_candidate_queryset(user, region_id=region_id, region_ids=region_ids)
    if current_room:
        rooms_qs = rooms_qs.exclude(id=current_room.id)
    if same_apartment is True and current_apartment_id:
        rooms_qs = rooms_qs.filter(apartment_id=current_apartment_id)
    elif same_apartment is False and current_apartment_id:
        rooms_qs = rooms_qs.exclude(apartment_id=current_apartment_id)

    if assisted_mode:
        accepted_dorm_type_id = getattr(student, 'accepted_dorm_type_id', None)
        if not accepted_dorm_type_id:
            rooms_qs = rooms_qs.none()
        else:
            rooms_qs = rooms_qs.filter(apartment__building__dorm_type_id=accepted_dorm_type_id)

    rooms = list(rooms_qs.prefetch_related('beds'))  # query #1 (Room + select_related chain), query #2 (beds prefetch)
    apartment_ids = {r.apartment_id for r in rooms}

    resident_assignments = BedAssignment.objects.filter(
        status=BedAssignment.Status.ACTIVE,
        bed__room__apartment_id__in=apartment_ids,
    ).select_related('student', 'bed__room')  # query #3 - every resident of every candidate apartment, in one shot

    residents_by_apartment = defaultdict(list)
    occupied_bed_ids_by_room = defaultdict(set)
    occupant_name_by_bed_id = {}
    for a in resident_assignments:
        occupied_bed_ids_by_room[a.bed.room_id].add(a.bed_id)
        rs = a.student
        occupant_name_by_bed_id[a.bed_id] = rs.full_name
        rs_roommate_ids = {
            rs.roommate_request_student_id_1, rs.roommate_request_student_id_2,
            rs.roommate_request_student_id_3, rs.roommate_request_student_id_4,
            rs.roommate_request_student_id_5,
        }
        rs_roommate_ids.discard(''); rs_roommate_ids.discard(None)
        residents_by_apartment[a.bed.room.apartment_id].append({
            'id': rs.id,
            'student_id': rs.student_id,
            'full_name': rs.full_name,
            'city': rs.city,
            'religion': rs.requested_religion,
            'religion_display': rs.get_requested_religion_display(),
            'religious': rs.religious,
            'placement_sector': rs.placement_sector,
            'sector_display': rs.get_placement_sector_display(),
            'study_points': rs.study_points,
            'housing_type': rs.housing_type,
            'roommate_ids': rs_roommate_ids,
            'room_name': a.bed.room.name,
        })

    roommate_ids = {
        student_data.get('roommate_request_student_id_1'),
        getattr(student, 'roommate_request_student_id_1', None),
        getattr(student, 'roommate_request_student_id_2', None),
        getattr(student, 'roommate_request_student_id_3', None),
        getattr(student, 'roommate_request_student_id_4', None),
        getattr(student, 'roommate_request_student_id_5', None),
    }
    roommate_ids.discard(None)
    roommate_ids.discard('')
    student_own_id = getattr(student, 'student_id', None)
    student_city = (student.city or '').strip().lower()
    student_group = _religion_group(student.requested_religion)
    student_sector = _sector_group(getattr(student, 'placement_sector', None))
    student_year_group = _year_group(getattr(student, 'study_points', None))
    history = _student_transfer_history(student)
    preferred_dorm_type_id = getattr(student, 'accepted_dorm_type_id', None)

    # Ranking case "mutual request + capacity for both" requires knowing
    # whether an UNASSIGNED requested roommate requested this student back -
    # their stored lists are fetched once (bounded: at most 5 ids).
    requested_roommate_lists = {}
    if roommate_ids:
        for rm in Student.objects.filter(student_id__in=roommate_ids):  # query #4 (<=5 rows)
            ids = {
                rm.roommate_request_student_id_1, rm.roommate_request_student_id_2,
                rm.roommate_request_student_id_3, rm.roommate_request_student_id_4,
                rm.roommate_request_student_id_5,
            }
            ids.discard(None); ids.discard('')
            requested_roommate_lists[rm.student_id] = ids

    assigned_requested_roommate_ids = {
        r['student_id']
        for residents in residents_by_apartment.values()
        for r in residents
        if r['student_id'] in roommate_ids
    }
    has_unassigned_mutual_roommate = bool(student_own_id) and any(
        rm_id not in assigned_requested_roommate_ids and student_own_id in their_ids
        for rm_id, their_ids in requested_roommate_lists.items()
    )

    apartment_dorm_type_ids = {}
    for room in rooms:
        apartment_dorm_type_ids[room.apartment_id] = room.apartment.building.dorm_type_id

    def _score_apartment(apartment_id, other_residents, apartment_free_selectable):
        """
        One score per APARTMENT - all rooms in an apartment share the same
        residents, hence the same warnings/reasons/score. Returns
        (roommate_tier, score, warnings, matched_preferences, historical).
        The tier ranks the roommate cases lexicographically; the score only
        refines ordering within a tier and picks the recommendation level.
        Neither is ever exposed to the client as a number.
        """
        warnings = []
        matched_preferences = []
        historical_reasons = []
        score = MATCH_SCORE_WEIGHTS['base']
        tier = 0

        mutual = one_sided = False
        for r in other_residents:
            if r['student_id'] in roommate_ids:
                one_sided = True
                if student_own_id and student_own_id in r.get('roommate_ids', set()):
                    mutual = True
        if mutual:
            tier = 3
            score += MATCH_SCORE_WEIGHTS['roommate_match_mutual']
            matched_preferences.append(_reason('mutual_roommate_request'))
            matched_preferences.append(_reason('roommate_already_here'))
        elif one_sided:
            tier = 2
            score += MATCH_SCORE_WEIGHTS['roommate_match_one_sided']
            matched_preferences.append(_reason('roommate_already_here'))
        elif has_unassigned_mutual_roommate and apartment_free_selectable >= 2:
            # Mutual request, roommate not assigned anywhere yet, and this
            # apartment really has two free REAL beds - both students fit.
            tier = 1
            score += MATCH_SCORE_WEIGHTS['roommate_future_capacity']
            matched_preferences.append(_reason('roommate_future_capacity'))

        if preferred_dorm_type_id and apartment_dorm_type_ids.get(apartment_id) == preferred_dorm_type_id:
            # The dormitory the student was accepted to is their explicit
            # dormitory preference - ranks above the remaining soft
            # preferences but below every roommate tier.
            score += MATCH_SCORE_WEIGHTS['preferred_dormitory']
            matched_preferences.append(_reason('preferred_dormitory'))

        if not other_residents:
            score += MATCH_SCORE_WEIGHTS['empty_apartment']
            matched_preferences.append(_reason('empty_apartment'))
        else:
            if student_group != 'unknown':
                mismatch = any(_religion_group(r['religion']) not in (student_group, 'unknown') for r in other_residents)
                if mismatch:
                    warnings.append(_reason('religion_conflict'))
                    score += MATCH_SCORE_WEIGHTS['religion_conflict_penalty']
                else:
                    score += MATCH_SCORE_WEIGHTS['religion_compatible']
                    matched_preferences.append(_reason('religion_match'))

            # sectorMatching - a coarser, separately-maintained placement
            # field (staff may set it even when requested_religion is
            # blank), so it is its own warning rather than reusing the
            # religion-group check above.
            if student_sector != 'unknown':
                sector_mismatch = any(
                    _sector_group(r['placement_sector']) not in (student_sector, 'unknown')
                    for r in other_residents
                )
                if sector_mismatch:
                    warnings.append(_reason('sector_conflict'))
                    score += MATCH_SCORE_WEIGHTS['sector_conflict_penalty']
                else:
                    score += MATCH_SCORE_WEIGHTS['sector_compatible']
                    matched_preferences.append(_reason('sector_match'))

            # avoidYearMix - flag only the specific year1-with-year3_4
            # combination (mirrors the solver); "other"/unknown academic
            # standing never triggers this warning.
            if student_year_group in ('year1', 'year3_4'):
                year_mismatch = any(
                    {_year_group(r['study_points']), student_year_group} == {'year1', 'year3_4'}
                    for r in other_residents
                )
                if year_mismatch:
                    warnings.append(_reason('year_mix_conflict'))
                    score += MATCH_SCORE_WEIGHTS['year_mix_penalty']

        if student_city and any((r['city'] or '').strip().lower() == student_city for r in other_residents):
            score += MATCH_SCORE_WEIGHTS['city_match']
            matched_preferences.append(_reason('city_match'))

        if getattr(student, 'is_priority', False):
            score += MATCH_SCORE_WEIGHTS['priority_student_bonus']
            matched_preferences.append(_reason('priority_student'))

        # Real stored history only (Transfer records) - never invented, and
        # never based on identity/behavior unrelated to housing requests.
        dorm_type_id = apartment_dorm_type_ids.get(apartment_id)
        if dorm_type_id:
            if dorm_type_id in history['requested_to']:
                score += MATCH_SCORE_WEIGHTS['history_bonus']
                historical_reasons.append(_reason('previously_requested_dormitory'))
            if dorm_type_id in history['requested_away_from']:
                historical_reasons.append(_reason('previously_transferred_away'))

        return tier, max(0, min(100, score)), warnings, matched_preferences, historical_reasons

    def _public_residents(other_residents):
        # roommate_ids is internal matching detail (a set, and other
        # students' private request lists) - never serialized to the client.
        # religious (observance level) is internal matching detail used only
        # to compute religion_conflict/override_violations server-side.
        _internal_keys = {'roommate_ids', 'religious'}
        return [{k: v for k, v in r.items() if k not in _internal_keys} for r in other_residents]

    # ---- pass 1: hard constraints + real-bed availability per room -------
    valid_rooms_by_apartment = defaultdict(list)
    conflict_rooms = []  # (room, apartment, residents, capacity_free, conflicts)
    apartment_selectable_free = defaultdict(int)
    integrity_rooms_missing = 0
    integrity_missing_beds = 0
    integrity_rooms_extra = 0

    for room in rooms:
        apartment = room.apartment
        occupied_ids = occupied_bed_ids_by_room.get(room.id, set())
        occupied_count = len(occupied_ids)
        capacity_free = max(room.capacity - occupied_count, 0)
        residents = residents_by_apartment.get(apartment.id, [])
        conflicts = _room_conflicts(student, room, apartment, residents, capacity_free)

        if conflicts:
            # Hard-conflict rooms are never part of the normal result set.
            # They are only surfaced (disabled, clearly marked) as a short
            # explanation when there is nothing valid to show at all.
            if explain_conflicts_if_empty and len(conflict_rooms) < MAX_CONFLICT_BUFFER:
                conflict_rooms.append((room, apartment, residents, capacity_free, conflicts))
            continue

        real_beds = sorted(room.beds.all(), key=lambda b: b.id)  # from the prefetch - no query
        free_real = [b for b in real_beds if b.id not in occupied_ids]
        # Never offer more beds than the room's configured capacity allows,
        # and never offer a bed that does not exist as a real row.
        selectable = free_real[:capacity_free]
        selectable_ids = {b.id for b in selectable}
        missing = max(capacity_free - len(free_real), 0)
        if missing:
            integrity_rooms_missing += 1
            integrity_missing_beds += missing
        if len(free_real) > len(selectable):
            integrity_rooms_extra += 1

        apartment_selectable_free[apartment.id] += len(selectable)
        valid_rooms_by_apartment[apartment.id].append({
            'room': room,
            'occupied_ids': occupied_ids,
            'occupied_count': occupied_count,
            'capacity_free': capacity_free,
            'real_beds': real_beds,
            'selectable_ids': selectable_ids,
            'missing': missing,
        })

    # ---- pass 2: score each apartment once, aggregate into buildings -----
    buildings_by_id = {}
    level_counts = {'best_match': 0, 'empty': 0, 'valid': 0, 'warning': 0, 'conflict': 0}
    assisted_status_counts = {'recommended': 0, 'possible': 0, 'override_required': 0}
    fully_empty_count = 0
    roommate_match_count = 0
    total_apartments = 0
    total_rooms = 0
    total_valid_beds = 0

    if assisted_mode:
        from types import SimpleNamespace

        from ..allocation.gateway import (
            OVERRIDE_VIOLATION_CONSEQUENCE, religion_conflict_for_candidate,
        )
        from ..allocation.gateway import _get_student_priority, _has_anier_special_status

    for apartment_id, room_entries in valid_rooms_by_apartment.items():
        apartment = room_entries[0]['room'].apartment
        building = apartment.building
        residents = residents_by_apartment.get(apartment_id, [])
        other_residents = [r for r in residents if r['id'] != getattr(student, 'id', None)]
        apt_selectable = apartment_selectable_free.get(apartment_id, 0)

        tier, score, warnings, matched_preferences, historical_reasons = _score_apartment(
            apartment_id, other_residents, apt_selectable
        )
        is_empty = not other_residents
        match_level = _classify_match_level(score, warnings, [], is_empty=is_empty)
        rec_level, rec_label, rec_rank = RECOMMENDATION_LEVEL_MAP[match_level]

        level_counts[match_level] += apt_selectable
        if is_empty:
            fully_empty_count += apt_selectable
        if tier >= 2:
            roommate_match_count += apt_selectable

        override_violations = []
        if assisted_mode:
            # preferred_dormitory is guaranteed true for every candidate here
            # (the queryset is already hard-restricted to the accepted dorm
            # type) - showing it on every single card would be redundant,
            # not informative.
            matched_preferences = [r for r in matched_preferences if r['code'] != 'preferred_dormitory']

            resident_ns = [
                SimpleNamespace(requested_religion=r['religion'], religious=r.get('religious', ''))
                for r in other_residents
            ]
            if religion_conflict_for_candidate(student, resident_ns):
                override_violations.append({
                    'code': 'religion', 'label': 'אין התאמה דתית לדיירים הקיימים',
                    'overridable': True, 'consequence': OVERRIDE_VIOLATION_CONSEQUENCE['religion'],
                })
                # Superseded by the precise violation above - the coarser
                # group-level warning would just repeat the same fact with
                # different wording.
                warnings = [w for w in warnings if w['code'] != 'religion_conflict']
            if apartment.inactive_reason == Apartment.InactiveReason.RESERVED and not (
                _get_student_priority(student) or _has_anier_special_status(student)
            ):
                override_violations.append({
                    'code': 'reserved', 'label': 'הדירה שמורה',
                    'overridable': True, 'consequence': OVERRIDE_VIOLATION_CONSEQUENCE['reserved'],
                })

            if override_violations:
                assisted_status = 'override_required'
            elif match_level in ('best_match', 'empty'):
                assisted_status = 'recommended'
            else:
                assisted_status = 'possible'
            assisted_status_label = ASSISTED_STATUS_LABELS[assisted_status]

        rooms_payload = []
        apt_capacity_free = 0
        apt_missing = 0
        for entry in sorted(room_entries, key=lambda e: str(e['room'].name)):
            room = entry['room']
            apt_capacity_free += entry['capacity_free']
            apt_missing += entry['missing']
            rooms_payload.append({
                'room_id': room.id,
                'room_name': room.name,
                'capacity': room.capacity,
                'occupied_beds_count': entry['occupied_count'],
                'available_beds_count': len(entry['selectable_ids']),
                'capacity_free_count': entry['capacity_free'],
                'missing_bed_records': entry['missing'],
                'beds': [
                    {
                        'bed_id': b.id,
                        'bed_label': b.label,
                        'is_occupied': b.id in entry['occupied_ids'],
                        'occupant_name': occupant_name_by_bed_id.get(b.id),
                        'is_selectable': b.id in entry['selectable_ids'],
                    }
                    for b in entry['real_beds']
                ],
            })

        apartment_payload = {
            'apartment_id': apartment.id,
            'apartment_number': apartment.number,
            'apartment_gender': apartment.category,
            'apartment_type': apartment.apartment_type,
            'residents': _public_residents(other_residents),
            'match_level': match_level,
            'recommendation_level': rec_level,
            'recommendation_label': rec_label,
            'recommendation_rank': rec_rank,
            'matched_reasons': matched_preferences,
            'warnings': warnings,
            'historical_reasons': historical_reasons,
            'available_bed_count': apt_selectable,
            'capacity_free_count': apt_capacity_free,
            'missing_bed_records': apt_missing,
            'room_count': len(rooms_payload),
            'has_roommate_match': tier >= 2,
            'rooms': rooms_payload,
            '_sort_key': (-tier, -score, -rec_rank, str(apartment.number)),
        }
        if assisted_mode:
            apartment_payload['assisted_status'] = assisted_status
            apartment_payload['assisted_status_label'] = assisted_status_label
            apartment_payload['override_violations'] = override_violations
            # Status always outranks score: an override-required apartment
            # must never sort above a plain recommended/possible one just
            # because a roommate match happens to raise its score.
            apartment_payload['_sort_key'] = (
                ASSISTED_STATUS_SORT_RANK[assisted_status], -tier, -score, -rec_rank, str(apartment.number),
            )

        b = buildings_by_id.get(building.id)
        if b is None:
            dorm_type = building.dorm_type
            region = dorm_type.region if dorm_type else None
            b = buildings_by_id[building.id] = {
                'building_id': building.id,
                'building_number': building.number,
                'building_name': (
                    f'בניין {building.number}' if building.number is not None
                    else f'בניין (מזהה {building.id})'
                ),
                'region': region.id if region else None,
                'region_name': region.name if region else None,
                'dorm_type': dorm_type.name if dorm_type else None,
                'dorm_type_id': dorm_type.id if dorm_type else None,
                'apartment_count': 0,
                'room_count': 0,
                'available_bed_count': 0,
                'capacity_free_count': 0,
                'missing_bed_records': 0,
                'recommendation_level': rec_level,
                'recommendation_label': rec_label,
                'recommendation_rank': rec_rank,
                'has_roommate_match': False,
                'top_reasons': [],
                'recommended_bed_count': 0,
                'roommate_bed_count': 0,
                'warning_free_bed_count': 0,
                'apartments': [],
                # Sentinel guaranteed lower than any real apt_key so the
                # first apartment always wins the update below. Assisted
                # mode's apt_key leads with -ASSISTED_STATUS_SORT_RANK
                # (0 down to -2), so a plain (-1, -1) is NOT low enough - an
                # override_required-only building's rank (-2) would never
                # beat it and _best_key would stay a 2-tuple, breaking the
                # 3-tuple sort key read below.
                '_best_key': (-1, -1) if not assisted_mode else (-999, -1, -1),
            }
            if assisted_mode:
                b['assisted_status'] = assisted_status
                b['assisted_status_label'] = assisted_status_label
                b['assisted_counts'] = {'recommended': 0, 'possible': 0, 'override_required': 0}

        b['apartment_count'] += 1
        b['room_count'] += len(rooms_payload)
        b['available_bed_count'] += apt_selectable
        b['capacity_free_count'] += apt_capacity_free
        b['missing_bed_records'] += apt_missing
        b['has_roommate_match'] = b['has_roommate_match'] or tier >= 2
        if match_level in ('best_match', 'empty'):
            b['recommended_bed_count'] += apt_selectable
        if tier >= 2:
            b['roommate_bed_count'] += apt_selectable
        if match_level in ('best_match', 'empty', 'valid'):
            b['warning_free_bed_count'] += apt_selectable
        b['apartments'].append(apartment_payload)
        if assisted_mode:
            b['assisted_counts'][assisted_status] += apt_selectable
            assisted_status_counts[assisted_status] += apt_selectable

        apt_key = (-ASSISTED_STATUS_SORT_RANK[assisted_status], tier, score) if assisted_mode else (tier, score)
        if apt_key > tuple(b['_best_key']):
            b['_best_key'] = apt_key
            b['recommendation_level'] = rec_level
            b['recommendation_label'] = rec_label
            b['recommendation_rank'] = rec_rank
            b['top_reasons'] = matched_preferences[:3]
            if assisted_mode:
                b['assisted_status'] = assisted_status
                b['assisted_status_label'] = assisted_status_label

        total_apartments += 1
        total_rooms += len(rooms_payload)
        total_valid_beds += apt_selectable

    # Distinct-PK totals by construction: buildings_by_id is keyed by
    # Building.pk, and each apartment/room is visited exactly once.
    ordered_buildings = sorted(
        buildings_by_id.values(),
        key=lambda b: (
            -b['_best_key'][0], -b['_best_key'][1],
            b['building_number'] if b['building_number'] is not None else 10 ** 9,
            b['building_id'],
        ) if not assisted_mode else (
            -b['_best_key'][0], -b['_best_key'][1], -b['_best_key'][2],
            b['building_number'] if b['building_number'] is not None else 10 ** 9,
            b['building_id'],
        ),
    )

    total_buildings = len(ordered_buildings)
    if limit:
        page_buildings = ordered_buildings[offset:offset + limit]
    else:
        page_buildings = ordered_buildings[offset:]
    loaded_buildings = offset + len(page_buildings)
    has_more = loaded_buildings < total_buildings
    next_offset = loaded_buildings if has_more else None

    for b in page_buildings:
        b['apartments'].sort(key=lambda a: a['_sort_key'])
        for a in b['apartments']:
            a.pop('_sort_key', None)
        b.pop('_best_key', None)

    conflict_examples = []
    if not buildings_by_id and explain_conflicts_if_empty:
        # Rank so the sample favors rooms that match the student's own
        # housing type/gender and are merely full, over rooms rejected for
        # an unrelated reason (e.g. wrong gender).
        conflict_rooms.sort(key=lambda t: _conflict_priority(t[4]))
        expected = _z_compatibility(student.housing_type)
        for room, apartment, residents, capacity_free, conflicts in conflict_rooms[:MAX_CONFLICT_EXAMPLES]:
            other_residents = [r for r in residents if r['id'] != getattr(student, 'id', None)]
            _tier, _score, warnings, matched_preferences, historical_reasons = _score_apartment(
                apartment.id, other_residents, apartment_selectable_free.get(apartment.id, 0)
            )
            # A requested roommate who does live in this exact apartment,
            # but the apartment itself hard-fails one of the student's own
            # constraints - say so explicitly instead of silently going
            # quiet about why "the roommate's apartment" isn't recommended.
            if roommate_ids and any(r['student_id'] in roommate_ids for r in other_residents):
                conflicts = conflicts + [REASON_LABELS['roommate_incompatible_hard_rule']]
            conflict_examples.append({
                'building': apartment.building.number,
                'building_id': apartment.building_id,
                'apartment': apartment.number,
                'apartment_id': apartment.id,
                'room': room.name,
                'room_id': room.id,
                'region_name': (
                    apartment.building.dorm_type.region.name
                    if apartment.building.dorm_type and apartment.building.dorm_type.region else None
                ),
                'conflicts': conflicts,
                'warnings': warnings,
                'matched_reasons': matched_preferences,
                'historical_reasons': historical_reasons,
                'residents': _public_residents(other_residents),
                'diagnostic': {
                    'student_housing_type': student.housing_type,
                    'student_housing_type_display': student.get_housing_type_display() if student.housing_type else None,
                    'required_apartment_type': expected[0] if expected else None,
                    'required_apartment_category': expected[1] if expected else None,
                    'room_apartment_type': apartment.apartment_type,
                    'room_apartment_category': apartment.category,
                    'room_capacity': room.capacity,
                    'bed_record_count': len(room.beds.all()),
                    'active_assignment_count': len(occupied_bed_ids_by_room.get(room.id, set())),
                    'available_beds_calculated': capacity_free,
                    'failed_hard_constraints': conflicts,
                },
            })

    return {
        'buildings': page_buildings,
        'loaded_buildings': loaded_buildings,
        'total_buildings': total_buildings,
        'total_apartments': total_apartments,
        'total_rooms': total_rooms,
        'total_valid_beds': total_valid_beds,
        # Legacy alias: 'total_valid' has always meant "free beds" - kept so
        # existing readers keep working while they migrate to the explicit
        # 'total_valid_beds'.
        'total_valid': total_valid_beds,
        'limit': limit,
        'offset': offset,
        'has_more': has_more,
        'next_offset': next_offset,
        'conflict_examples': conflict_examples,
        # Real, exact counts per filter chip, computed over every SELECTABLE
        # bed (real Bed rows only) - never approximated from just one page.
        'counts': {
            'all': total_valid_beds,
            'best_match': level_counts['best_match'],
            'empty': level_counts['empty'],
            'warning_free': level_counts['best_match'] + level_counts['empty'] + level_counts['valid'],
            'with_warnings': level_counts['warning'],
            'with_roommate': roommate_match_count,
            'fully_empty': fully_empty_count,
        },
        # Rooms whose configured capacity exceeds their real Bed rows (or
        # vice versa). Reported, never silently "fixed" - materializing
        # missing rows is manage.py materialize_beds, an explicit admin
        # operation.
        'data_integrity': {
            'rooms_missing_bed_records': integrity_rooms_missing,
            'missing_bed_records': integrity_missing_beds,
            'rooms_with_extra_bed_records': integrity_rooms_extra,
        },
        **({'assisted_status_counts': assisted_status_counts} if assisted_mode else {}),
    }
