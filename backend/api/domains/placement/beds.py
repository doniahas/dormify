"""
Bed availability and acquisition helpers for student placement.
"""

from ...models import Bed, BedAssignment, Room


def ensure_room_beds(room: Room):
    """
    Materialize missing Bed rows for a room from its configured capacity.

    EXPLICIT SETUP ONLY: this writes to the database and therefore must
    never be called from any read/browse path (match-options, feasibility,
    the assignment picker, pagination) nor from the regular assignment flow.
    Its only legitimate caller is the admin-only management command
    `manage.py materialize_beds` (and test fixtures). Read paths report a
    capacity/Bed-row mismatch as a data-integrity problem instead.
    """
    existing = room.beds.count()
    if existing >= room.capacity:
        return

    for i in range(existing + 1, room.capacity + 1):
        Bed.objects.create(room=room, label=f'Bed {i}')


_MISSING_BED_RECORDS_MSG = (
    'בחדר זה קיימת קיבולת פנויה אך חסרות רשומות מיטה במסד הנתונים (בעיית נתונים). '
    'יש להריץ את פעולת האתחול הייעודית (manage.py materialize_beds) לפני שיבוץ.'
)


def get_free_bed(room: Room):
    """
    First actually-free REAL bed in the room, or None when the room is at
    capacity. Never creates Bed rows: a room with free capacity but no free
    real Bed row raises a data-integrity ValueError instead (materializing
    beds is an explicit admin operation, see ensure_room_beds).
    """
    if not room.is_active:
        return None
    if not room.apartment.is_active:
        return None
    if not room.apartment.building.is_active:
        return None

    occupied_bed_ids = set(BedAssignment.objects.filter(
        bed__room=room,
        status=BedAssignment.Status.ACTIVE
    ).values_list('bed_id', flat=True))

    # Capacity is authoritative: even if surplus Bed rows exist, the room
    # never accepts more active residents than its configured capacity.
    if len(occupied_bed_ids) >= room.capacity:
        return None

    free = room.beds.exclude(id__in=occupied_bed_ids).order_by('id').first()
    if free is None:
        raise ValueError(_MISSING_BED_RECORDS_MSG)
    return free


def get_specific_free_bed(room: Room, bed_id):
    """
    Resolve a specific bed the caller selected (e.g. from the per-bed
    matching UI) and verify it is still free right now. Raises ValueError
    (mirrors get_free_bed's None-on-no-capacity contract at the call site)
    if the bed doesn't belong to this room or was taken in the meantime -
    the caller must always re-validate the exact bed server-side rather
    than trusting whatever the client last saw. Never creates Bed rows.
    """
    if not room.is_active or not room.apartment.is_active or not room.apartment.building.is_active:
        raise ValueError('החדר אינו פעיל')

    try:
        bed = room.beds.get(pk=bed_id)
    except Bed.DoesNotExist:
        raise ValueError('המיטה שנבחרה אינה שייכת לחדר זה')

    if BedAssignment.objects.filter(bed=bed, status=BedAssignment.Status.ACTIVE).exists():
        raise ValueError('המיטה שנבחרה כבר תפוסה - נא לבחור מיטה אחרת')

    # The room's configured capacity can never be exceeded, even when more
    # Bed rows than capacity exist (data anomaly).
    active_in_room = BedAssignment.objects.filter(
        bed__room=room, status=BedAssignment.Status.ACTIVE,
    ).count()
    if active_in_room >= room.capacity:
        raise ValueError('החדר בתפוסה מלאה - לא ניתן לחרוג מקיבולת החדר')

    return bed
