"""
DORMIFY - Seed Database (synthetic demo data)

Run from backend/ with the development database configured:

    python seed.py

Creates demo regions, dormitory types (with the official codes the Excel
importer resolves), buildings, apartments, rooms and beds, plus one staff
account per role. It creates no students: generate a synthetic workbook
with scripts/generate_demo_students.py and upload it through the Students
import page (see docs/DEVELOPMENT.md). Re-running is safe; existing rows
are kept.

G3-09: this script must never contain a fixed, reusable, tracked password
(the previous 'admin123'/'test123' were the same for every clone of this
repo, forever, unless someone remembered to change them by hand). Dev
credentials now come from SEED_ADMIN_PASSWORD/SEED_STAFF_PASSWORD env vars
when the operator wants known values (e.g. for a shared local demo), or are
randomly generated per run and printed once to the console - never written
back into source. The script also refuses to run at all unless DEBUG is
explicitly true, so it cannot be pointed at a production database by
accident (see dormify.settings - DEBUG defaults to False everywhere except
local development, where .env explicitly sets it true).
"""

import os
import secrets
import sys

import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'dormify.settings')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
django.setup()

from django.conf import settings  # noqa: E402
from django.db import transaction  # noqa: E402

from api.models import (  # noqa: E402
    Apartment,
    Bed,
    Building,
    DormType,
    Region,
    Room,
    Student,
    User,
)

# Demo regions. The ids are what the frontend and the inventory API use.
REGIONS = [
    ('canada', 'מעונות קנדה'),
    ('hasmaha', 'מעונות ההסמכה'),
    ('mizrah', 'מעונות מזרח'),
    ('rifkin', 'מעונות ריפקין'),
    ('broshim', 'מעונות ברושים'),
    ('segal-zutar', 'מעונות סגל זוטר'),
]

# (official code, name, region). The codes are the dorm-office area numbers
# that api.domains.imports.parsing resolves from the "decision dorm" column,
# so a workbook from scripts/generate_demo_students.py lands in these
# regions. Codes 1, 13 and 17 get no inventory on purpose: students
# accepted there import with a warning and stay unassigned, which is what
# the assisted-allocation workbench is for.
DORM_TYPES = [
    (2, 'קנדה', 'canada'),
    (15, 'כפר הסמכה', 'hasmaha'),
    (12, 'מזרח חדש', 'mizrah'),
    (5, 'מזרח ישן', 'mizrah'),
    (1, 'ריפקין', 'rifkin'),
    (17, 'ברושים', 'broshim'),
    (13, 'סגל זוטר', 'segal-zutar'),
]

# One synthetic staff account per role; e-mails use the reserved example
# domain so they can never be mistaken for real institutional mailboxes.
USERS = [
    {'email': 'admin@example.edu', 'username': 'admin', 'first_name': 'Demo', 'last_name': 'Admin', 'role': 'central_admin', 'region': None, 'password_env': 'SEED_ADMIN_PASSWORD'},
    {'email': 'canada@example.edu', 'username': 'canada_boss', 'first_name': 'Demo', 'last_name': 'Manager', 'role': 'region_boss', 'region': 'canada', 'password_env': 'SEED_STAFF_PASSWORD'},
    {'email': 'canada.emp@example.edu', 'username': 'canada_emp', 'first_name': 'Demo', 'last_name': 'Employee', 'role': 'employee', 'region': 'canada', 'password_env': 'SEED_STAFF_PASSWORD'},
    {'email': 'hasmaha@example.edu', 'username': 'hasmaha_boss', 'first_name': 'Demo', 'last_name': 'Manager', 'role': 'region_boss', 'region': 'hasmaha', 'password_env': 'SEED_STAFF_PASSWORD'},
    {'email': 'mizrah@example.edu', 'username': 'mizrah_boss', 'first_name': 'Demo', 'last_name': 'Manager', 'role': 'region_boss', 'region': 'mizrah', 'password_env': 'SEED_STAFF_PASSWORD'},
]

# Apartment shapes: category is the resident gender the apartment is for
# (mixed for household types), rooms lists the bed capacity of each room.
APARTMENT_SHAPES = {
    'single_female': {'category': Apartment.Category.FEMALE, 'apartment_type': Apartment.ApartmentType.SINGLE, 'rooms': [2, 2]},
    'single_male': {'category': Apartment.Category.MALE, 'apartment_type': Apartment.ApartmentType.SINGLE, 'rooms': [2, 2]},
    'couple': {'category': Apartment.Category.MIXED, 'apartment_type': Apartment.ApartmentType.COUPLE, 'rooms': [2]},
    'family': {'category': Apartment.Category.MIXED, 'apartment_type': Apartment.ApartmentType.FAMILY, 'rooms': [2, 1]},
}

# Inventory per dorm-type code. Apartment numbers run 1..N in list order.
# `inactive` marks apartments (by number) that exist but are out of use, so
# the inventory pages and the solver's inactive-housing rule have something
# to show. Building 3 of code 15 is a shared-facility building restricted
# to one gender, exercising the building-level gender rule.
INVENTORY = {
    2: [
        {'number': 1, 'apartments': ['single_female'] * 3 + ['single_male'] * 5 + ['couple', 'couple', 'family']},
        {'number': 2, 'apartments': ['single_female'] * 3 + ['single_male'] * 5 + ['couple', 'couple', 'family'],
         'inactive': {3: Apartment.InactiveReason.MAINTENANCE}},
    ],
    15: [
        {'number': 1, 'apartments': ['single_female'] * 3 + ['single_male'] * 3 + ['couple', 'couple']},
        {'number': 2, 'apartments': ['single_female'] * 3 + ['single_male'] * 3 + ['family']},
        {'number': 3, 'gender_restriction': Building.GenderRestriction.FEMALE, 'apartments': ['single_female'] * 6},
    ],
    12: [
        {'number': 1, 'apartments': ['single_female'] * 4 + ['single_male'] * 4},
    ],
    5: [
        {'number': 1, 'apartments': ['single_female'] * 2 + ['single_male'] * 2 + ['couple']},
    ],
}


def _dev_password(env_var):
    """
    Returns the operator-supplied password for `env_var` if set, otherwise
    a freshly generated random one. Never a fixed literal - see the G3-09
    note above.
    """
    return os.getenv(env_var) or secrets.token_urlsafe(12)


def seed_regions():
    regions = {}
    for region_id, name in REGIONS:
        region, _ = Region.objects.get_or_create(id=region_id, defaults={'name': name})
        regions[region_id] = region
    return regions


def seed_dorm_types(regions):
    dorm_types = {}
    for code, name, region_id in DORM_TYPES:
        dorm_type, _ = DormType.objects.get_or_create(
            code=code, defaults={'name': name, 'region': regions[region_id]},
        )
        dorm_types[code] = dorm_type
    return dorm_types


def seed_users(regions, passwords):
    created = []
    for spec in USERS:
        data = dict(spec)
        region_id = data.pop('region')
        password = passwords[data.pop('password_env')]
        if User.objects.filter(email=data['email']).exists():
            continue
        User.objects.create_user(
            password=password,
            region=regions.get(region_id) if region_id else None,
            **data,
        )
        created.append(data['email'])
    return created


def seed_inventory(dorm_types):
    counts = {'buildings': 0, 'apartments': 0, 'rooms': 0, 'beds': 0}
    for code, buildings in INVENTORY.items():
        dorm_type = dorm_types[code]
        for building_spec in buildings:
            building, created = Building.objects.get_or_create(
                dorm_type=dorm_type,
                number=building_spec['number'],
                defaults={
                    'is_active': True,
                    'gender_restriction': building_spec.get('gender_restriction', ''),
                },
            )
            counts['buildings'] += int(created)
            inactive = building_spec.get('inactive', {})

            for index, shape_name in enumerate(building_spec['apartments'], start=1):
                shape = APARTMENT_SHAPES[shape_name]
                inactive_reason = inactive.get(index, '')
                apartment, created = Apartment.objects.get_or_create(
                    building=building,
                    number=str(index),
                    defaults={
                        'category': shape['category'],
                        'apartment_type': shape['apartment_type'],
                        'room_count': len(shape['rooms']),
                        'apartment_capacity': sum(shape['rooms']),
                        'is_active': not inactive_reason,
                        'inactive_reason': inactive_reason,
                    },
                )
                counts['apartments'] += int(created)

                for room_index, capacity in enumerate(shape['rooms'], start=1):
                    room, created = Room.objects.get_or_create(
                        apartment=apartment,
                        name=str(room_index),
                        defaults={'capacity': capacity, 'is_active': True},
                    )
                    counts['rooms'] += int(created)
                    if not room.beds.exists():
                        Bed.objects.bulk_create(
                            [Bed(room=room, label=f'Bed {bed_index}') for bed_index in range(1, capacity + 1)]
                        )
                        counts['beds'] += capacity
    return counts


def seed():
    if not settings.DEBUG:
        print(
            'Refusing to seed: DEBUG is not enabled. This script creates '
            'known/placeholder accounts and must only run against a local '
            'development database (ENV_FILE=.env with DEBUG=True, or '
            'ENV_FILE=.env.test). Aborting.'
        )
        sys.exit(1)

    print('Seeding synthetic demo data...\n')

    passwords = {
        'SEED_ADMIN_PASSWORD': _dev_password('SEED_ADMIN_PASSWORD'),
        'SEED_STAFF_PASSWORD': _dev_password('SEED_STAFF_PASSWORD'),
    }

    with transaction.atomic():
        regions = seed_regions()
        dorm_types = seed_dorm_types(regions)
        created_users = seed_users(regions, passwords)
        counts = seed_inventory(dorm_types)

    print(f'Regions:     {Region.objects.count()} ({len(REGIONS)} in the demo set)')
    print(f'Dorm types:  {DormType.objects.count()} ({len(DORM_TYPES)} in the demo set)')
    print(f'Users:       {User.objects.count()} ({len(created_users)} created this run)')
    print(f'Buildings:   {Building.objects.count()} (+{counts["buildings"]})')
    print(f'Apartments:  {Apartment.objects.count()} (+{counts["apartments"]})')
    print(f'Rooms:       {Room.objects.count()} (+{counts["rooms"]})')
    print(f'Beds:        {Bed.objects.count()} (+{counts["beds"]})')
    print(f'Students:    {Student.objects.count()}')
    print(
        '\nNext: python scripts/generate_demo_students.py, then upload the '
        'workbook on the Students import page as the central admin.'
    )

    print('\nLogin credentials (generated this run - not stored anywhere):')
    print(f'   Central Admin: admin@example.edu / {passwords["SEED_ADMIN_PASSWORD"]}')
    print(f'   Canada Boss:   canada@example.edu / {passwords["SEED_STAFF_PASSWORD"]}')
    print(f'   Hasmaha Boss:  hasmaha@example.edu / {passwords["SEED_STAFF_PASSWORD"]}')
    print(f'   Mizrah Boss:   mizrah@example.edu / {passwords["SEED_STAFF_PASSWORD"]}')
    print(
        '   (set SEED_ADMIN_PASSWORD / SEED_STAFF_PASSWORD before running '
        'to choose known values instead of random ones; the passwords '
        'above apply only to accounts created in this run)\n'
    )


if __name__ == '__main__':
    seed()
