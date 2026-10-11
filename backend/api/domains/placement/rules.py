"""
Apartment compatibility and placement validation rules.
"""

from ...models import Apartment, BedAssignment, Room, Student


def _active_apartment_assignments(apartment, exclude_student_id=None):
    queryset = BedAssignment.objects.filter(
        status=BedAssignment.Status.ACTIVE,
        bed__room__apartment=apartment,
    ).select_related('student')

    if exclude_student_id is not None:
        queryset = queryset.exclude(student_id=exclude_student_id)

    return queryset


def _z_compatibility(housing_type):
    """
    Single source of truth for Z1-Z4 apartment_type/category compatibility,
    shared by validate_apartment_assignment (write-path, authoritative,
    always re-checked live) and the read-path batch matching engine below
    (which must not re-implement this policy table separately).
    """
    return {
        Student.HousingType.SINGLE_MALE: (
            Apartment.ApartmentType.SINGLE,
            Apartment.Category.MALE,
        ),
        Student.HousingType.SINGLE_FEMALE: (
            Apartment.ApartmentType.SINGLE,
            Apartment.Category.FEMALE,
        ),
        Student.HousingType.COUPLE: (
            Apartment.ApartmentType.COUPLE,
            Apartment.Category.MIXED,
        ),
        Student.HousingType.FAMILY: (
            Apartment.ApartmentType.FAMILY,
            Apartment.Category.MIXED,
        ),
    }.get(housing_type)


def validate_apartment_assignment(student: Student, room: Room):
    """
    Validate Z1/Z2/Z3/Z4/Z6 compatibility.

    Z1 -> single apartment + male category
    Z2 -> single apartment + female category
    Z3 -> couple apartment + mixed category
    Z4 -> family apartment + mixed category
    Z6 -> any active couple-layout apartment, independent of gender/category,
          but the complete apartment is reserved exclusively for that student.
    """
    apartment = room.apartment

    if not room.is_active:
        raise ValueError('The selected room is inactive.')

    if not apartment.is_active:
        reason = (
            apartment.get_inactive_reason_display()
            if apartment.inactive_reason
            else 'inactive'
        )
        raise ValueError(f'Apartment is inactive: {reason}')

    if not apartment.building.is_active:
        raise ValueError('The selected building is inactive.')

    other_active_assignments = _active_apartment_assignments(
        apartment,
        exclude_student_id=student.id,
    )

    if student.housing_type == Student.HousingType.SINGLE_IN_APARTMENT:
        if apartment.apartment_type != Apartment.ApartmentType.COUPLE:
            raise ValueError(
                'Z6 requires a couple-layout apartment.'
            )

        if other_active_assignments.exists():
            raise ValueError(
                'Z6 requires exclusive use of the complete apartment.'
            )

        # Z6 apartments are neutral before placement. Their stored male/female/
        # mixed category does not restrict which Z6 student may receive them.
        return

    # Nobody else may enter an apartment already reserved by an active Z6
    # resident, even when another room/bed in that apartment appears empty.
    if other_active_assignments.filter(
        student__housing_type=Student.HousingType.SINGLE_IN_APARTMENT
    ).exists():
        raise ValueError(
            'This apartment is reserved exclusively for a Z6 resident.'
        )

    expected = _z_compatibility(student.housing_type)
    if expected is None:
        raise ValueError(
            'The student has no supported housing type '
            '(expected Z1, Z2, Z3, Z4, or Z6).'
        )

    expected_type, expected_category = expected

    if apartment.apartment_type != expected_type:
        raise ValueError(
            'Housing type mismatch: '
            f'student requires apartment_type={expected_type}, '
            f'but apartment has apartment_type={apartment.apartment_type}.'
        )

    if apartment.category != expected_category:
        raise ValueError(
            'Housing category mismatch: '
            f'student requires category={expected_category}, '
            f'but apartment has category={apartment.category}.'
        )

    # Z3/Z4 exclusivity: a Student record with COUPLE/FAMILY housing type
    # represents one COMPLETE application (the applicant and their
    # partner/family, who are not tracked as separate Student records) —
    # never one member of a shared household. An apartment already holding
    # any other active assignment is unavailable, unconditionally; there is
    # no second Student record that may ever join it.
    if student.housing_type in (
        Student.HousingType.COUPLE,
        Student.HousingType.FAMILY,
    ) and other_active_assignments.exists():
        raise ValueError(
            'This apartment already has an active assignment. Exclusive '
            'couple/family apartments may only be assigned to one Student '
            'record.'
        )
