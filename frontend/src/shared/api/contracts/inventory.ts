// backend/api/serializers/inventory.py
//
// Note the asymmetry the serializers carry: `region` is the region's string
// id, `dorm_type` is the DormType primary key on Building but the dorm-type
// NAME on Apartment, and every *_display field is a fixed Hebrew label.

export type GenderRestriction = 'male' | 'female' | '';
export type ApartmentCategory = 'male' | 'female' | 'mixed';
export type ApartmentType = 'single' | 'couple' | 'family';
export type InactiveReason =
  | 'reserved'
  | 'maintenance'
  | 'renovation'
  | 'staff_use'
  | 'other'
  | '';

/** BuildingSerializer. */
export interface Building {
  id: number;
  /** Building.number is nullable. */
  number: number | null;
  dorm_type: number;
  dorm_type_name: string;
  /** DormType.code is nullable. */
  dorm_type_code: number | null;
  region: string;
  region_name: string;
  is_active: boolean;
  gender_restriction: GenderRestriction;
  gender_restriction_display: string;
  apartment_count: number;
  room_count: number;
  bed_count: number;
  occupied_beds: number;
  free_beds: number;
}

/** ApartmentSerializer. */
export interface Apartment {
  id: number;
  building: number;
  building_number: number | null;
  number: string;
  category: ApartmentCategory;
  category_display: string;
  apartment_type: ApartmentType;
  apartment_type_display: string;
  room_count: number;
  actual_room_count: number;
  /** Apartment.apartment_capacity is nullable. */
  apartment_capacity: number | null;
  bed_count: number;
  occupied_beds: number;
  free_beds: number;
  is_active: boolean;
  inactive_reason: InactiveReason;
  inactive_reason_display: string;
  region: string;
  region_name: string;
  /** The dorm type's name (ApartmentSerializer sources it from dorm_type.name). */
  dorm_type: string;
}

/** RoomSerializer. */
export interface Room {
  id: number;
  apartment: number;
  apartment_number: string;
  building_number: number | null;
  region: string;
  region_name: string;
  name: string;
  number: string;
  capacity: number;
  bed_count: number;
  current_occupancy: number;
  available_beds: number;
  is_full: boolean;
  is_active: boolean;
  has_missing_bed_records: boolean;
}

/** BedSerializer. */
export interface Bed {
  id: number;
  label: string;
  room: number;
  room_name: string;
  apartment_number: string;
  building_number: number | null;
  is_occupied: boolean;
}
