"""Compact model fixtures shared by the domain tests."""

from django.utils import timezone

from api.models import (
    AllocationRun,
    Apartment,
    Bed,
    BedAssignment,
    Building,
    DormType,
    Region,
    Room,
    Student,
    User,
)

_building_counter = [5000]


def make_region(name='Domain Region'):
    return Region.objects.create(id=name.lower().replace(' ', '_'), name=name)


def make_user(role, region=None, email=None):
    email = email or f'{role}-{region.id if region else "global"}@domain.test'
    return User.objects.create_user(
        username=email, email=email, password='x', role=role,
        first_name='F', last_name='L', region=region,
    )


def make_central_admin(email='domain-admin@domain.test'):
    return make_user(User.Role.CENTRAL_ADMIN, email=email)


def make_boss(region, email=None):
    return make_user(User.Role.REGION_BOSS, region=region, email=email)


def make_employee(region, email=None):
    return make_user(User.Role.EMPLOYEE, region=region, email=email)


def make_dorm(region, name=None, code=None):
    return DormType.objects.create(name=name or f'Dorm {region.id}', code=code, region=region)


def make_building(dorm, number=None, is_active=True, **extra):
    if number is None:
        _building_counter[0] += 1
        number = _building_counter[0]
    return Building.objects.create(number=number, dorm_type=dorm, is_active=is_active, **extra)


def make_apartment(building, number='1', category=Apartment.Category.MALE,
                   apartment_type=Apartment.ApartmentType.SINGLE, room_count=1, is_active=True):
    return Apartment.objects.create(
        building=building, number=number, category=category,
        apartment_type=apartment_type, room_count=room_count, is_active=is_active,
    )


def make_room(apartment, name='A', capacity=2, is_active=True, beds=True):
    room = Room.objects.create(apartment=apartment, name=name, capacity=capacity, is_active=is_active)
    if beds:
        for index in range(1, capacity + 1):
            Bed.objects.create(room=room, label=str(index))
    return room


def make_student(dorm, student_id, gender=Student.Gender.MALE,
                 housing_type=Student.HousingType.SINGLE_MALE, **extra):
    return Student.objects.create(
        student_id=student_id, first_name='First', last_name=student_id,
        gender=gender, housing_type=housing_type, accepted_dorm_type=dorm, **extra,
    )


def assign(student, room, run=None, assignment_type=BedAssignment.AssignmentType.INITIAL):
    occupied = BedAssignment.objects.filter(status=BedAssignment.Status.ACTIVE).values_list('bed_id', flat=True)
    bed = room.beds.exclude(id__in=occupied).order_by('label').first()
    assignment = BedAssignment.objects.create(
        student=student, bed=bed, status=BedAssignment.Status.ACTIVE,
        assignment_type=assignment_type, allocation_run=run,
    )
    Student.objects.filter(pk=student.pk).update(assigned_room=room)
    student.refresh_from_db()
    return assignment


def make_run(region, user, status=AllocationRun.Status.COMPLETED, completed=True, **extra):
    return AllocationRun.objects.create(
        region=region, run_by=user, status=status,
        completed_at=timezone.now() if completed else None, **extra,
    )


def make_full_stack(region, dorm=None):
    """Region -> dorm -> building -> apartment -> room(2 beds)."""
    dorm = dorm or make_dorm(region)
    building = make_building(dorm)
    apartment = make_apartment(building)
    room = make_room(apartment)
    return dorm, building, apartment, room
