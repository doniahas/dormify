from django.utils import timezone

from api.models import (
    User, Region, AllocationRun, Student, DormType, Building, Apartment, Room,
    Bed,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_region(name='TestRegion'):
    # Region.id is a CharField primary key — must be supplied explicitly.
    region_id = name.lower().replace(' ', '_')
    return Region.objects.create(id=region_id, name=name)


def _make_central_admin(region=None, email='admin@test.com'):
    user = User.objects.create_user(
        username=email,
        email=email,
        password='testpass123',
        role=User.Role.CENTRAL_ADMIN,
        first_name='Admin',
        last_name='User',
    )
    if region:
        user.region = region
        user.save()
    return user


def _make_region_boss(region, email='boss@test.com'):
    user = User.objects.create_user(
        username=email,
        email=email,
        password='testpass123',
        role=User.Role.REGION_BOSS,
        first_name='Boss',
        last_name='User',
        region=region,
    )
    return user


def _make_employee(region, email='emp@test.com'):
    return User.objects.create_user(
        username=email,
        email=email,
        password='testpass123',
        role=User.Role.EMPLOYEE,
        first_name='Emp',
        last_name='User',
        region=region,
    )


def _make_run(region, user, status_val=AllocationRun.Status.COMPLETED, completed=True):
    run = AllocationRun(
        region=region,
        run_by=user,
        status=status_val,
        students_processed=0,
        successful_assignments=0,
        roommate_matches=0,
        conflicts=0,
        error_message='' if status_val != AllocationRun.Status.FAILED else 'test error',
        completed_at=timezone.now() if completed else None,
    )
    AllocationRun.objects.bulk_create([run])
    return AllocationRun.objects.filter(region=region).order_by('-started_at').first()


# ---------------------------------------------------------------------------
# Helpers for max-solver-time / live-preview / Stop & Save / Cancel tests
# (configurable search duration, current-result preview, real early
# interruption). Reuse the exact category='male'/housing_type='single_male'
# combination already proven to match in _make_run_with_assignment above,
# and the same minimal-config shape SolverReligiousJewishRuleTest already
# uses successfully for direct run_improved_ortools_allocation calls.
# ---------------------------------------------------------------------------

def _make_minimal_infra(region, beds_per_apt=1, num_apts=1):
    """A small, always-solvable inventory: one building, `num_apts` single-room
    apartments with `beds_per_apt` beds each, all region-scoped so the async
    view layer's accepted_dorm_type__region filter can find them too."""
    dorm_type = DormType.objects.create(
        name=f'Dorm_{region.id}_{num_apts}x{beds_per_apt}',
        region=region,
    )
    building = Building.objects.create(number=100, dorm_type=dorm_type)
    rooms = []
    for i in range(num_apts):
        apartment = Apartment.objects.create(
            building=building,
            number=str(i + 1),
            category=Apartment.Category.MALE,
            apartment_type=Apartment.ApartmentType.SINGLE,
            room_count=1,
        )
        room = Room.objects.create(apartment=apartment, name='A', capacity=beds_per_apt)
        for j in range(beds_per_apt):
            Bed.objects.create(room=room, label=str(j + 1))
        rooms.append(room)
    return dorm_type, rooms


def _make_minimal_student(student_id, dorm_type):
    # housing_type must be the real Hebrew choice value (Student.HousingType
    # is a plain CharField with Hebrew choices, e.g. SINGLE_MALE='רווקים') -
    # a plain .create() bypasses choice validation, so an invalid raw
    # string like 'single_male' would silently create a student with zero
    # candidate apartments instead of raising.
    return Student.objects.create(
        student_id=student_id,
        first_name='Test',
        last_name=student_id,
        housing_type=Student.HousingType.SINGLE_MALE,
        accepted_dorm_type=dorm_type,
    )


MINIMAL_SOLVER_CONFIG = {
    "ReligiousTogether": {"enabled": False},
    "sameReligion": {"enabled": False},
    "sectorMatching": {"enabled": False},
    "roommateMatch": {"enabled": False},
    "roommatePositiveOnly": {"enabled": False},
    "avoidYearMix_1_with_3_4": {"enabled": False},
    "avoidAtudaimWithHasmaha": {"enabled": False},
    "priorityFirst": {"enabled": False},
}
