"""Public compatibility facade for API serializers."""

from .auth import UserSerializer, LoginSerializer
from .organization import (
    RegionSerializer,
    OfficeSerializer,
    StaffProfileSerializer,
    DormTypeSerializer,
)
from .inventory import (
    check_building_write_conflict,
    check_apartment_write_conflict,
    check_room_write_conflict,
    BuildingSerializer,
    ApartmentSerializer,
    RoomSerializer,
    BedSerializer,
)
from .students import StudentListSerializer, StudentSerializer
from .workflows import (
    BedAssignmentSerializer,
    MovementRequestSerializer,
    TransferSerializer,
    StudentRequestSerializer,
)
from .operations import (
    AllocationRunSerializer,
    ImportBatchSerializer,
    RegionInboxSerializer,
)


__all__ = (
    'UserSerializer',
    'LoginSerializer',
    'RegionSerializer',
    'OfficeSerializer',
    'StaffProfileSerializer',
    'DormTypeSerializer',
    'check_building_write_conflict',
    'check_apartment_write_conflict',
    'check_room_write_conflict',
    'BuildingSerializer',
    'ApartmentSerializer',
    'RoomSerializer',
    'BedSerializer',
    'StudentListSerializer',
    'StudentSerializer',
    'BedAssignmentSerializer',
    'MovementRequestSerializer',
    'TransferSerializer',
    'StudentRequestSerializer',
    'AllocationRunSerializer',
    'ImportBatchSerializer',
    'RegionInboxSerializer',
)

