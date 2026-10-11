// Inventory-feature payloads beyond the shared Building/Apartment/Room/Bed
// contracts (backend/api/views/inventory.py).
import type {
  Apartment,
  ApartmentCategory,
  ApartmentType,
  Bed,
  Building,
  DormType,
  Id,
  ListResponse,
  Region,
  Room,
} from '../../shared/api/contracts';

/** Query parameters the inventory list endpoints accept. */
export interface InventoryListParams {
  region?: Id;
  dorm_type?: Id;
  building?: Id;
  apartment?: Id;
  room?: Id;
  /** 'all' lists inactive rows too; the default lists active rows only. */
  is_active?: 'all' | boolean | string;
  page?: number;
  [key: string]: string | number | boolean | null | undefined;
}

export type BuildingPayload = Partial<
  Pick<Building, 'number' | 'dorm_type' | 'is_active' | 'gender_restriction'>
> & { [key: string]: unknown };

export type ApartmentPayload = Partial<
  Pick<
    Apartment,
    | 'building'
    | 'number'
    | 'category'
    | 'apartment_type'
    | 'room_count'
    | 'apartment_capacity'
    | 'is_active'
    | 'inactive_reason'
  >
> & { [key: string]: unknown };

export type RoomPayload = Partial<
  Pick<Room, 'apartment' | 'name' | 'capacity' | 'is_active'>
> & { [key: string]: unknown };

export type BedPayload = Partial<Pick<Bed, 'label' | 'room'>> & { [key: string]: unknown };

/** One room group of a bulk-create apartment group: `count` rooms of `capacity` beds. */
export interface BulkRoomGroup {
  capacity: number;
  count: number;
}

/** One apartment group of POST /api/buildings/<id>/bulk-create-inventory/. */
export interface BulkApartmentGroup {
  category?: ApartmentCategory | string;
  apartment_type?: ApartmentType | string;
  apartment_capacity?: number | null;
  numbers: Array<string | number>;
  room_groups: BulkRoomGroup[];
  [key: string]: unknown;
}

/** POST /api/buildings/<id>/bulk-create-inventory/ - the key is `apartment_groups`. */
export interface BulkCreateInventoryPayload {
  apartment_groups: BulkApartmentGroup[];
  [key: string]: unknown;
}

export interface BulkCreateInventoryResponse {
  success?: boolean;
  building_id?: number;
  created_apartments?: number;
  created_rooms?: number;
  created_beds?: number;
  conflicting_numbers?: Array<string | number>;
  detail?: string;
  error?: string;
  error_type?: string;
  code?: string;
  [key: string]: unknown;
}

/** GET /api/inventory/by-housing-type/ - legacy: the view exists but is not routed in api/urls.py. */
export interface InventoryByHousingType {
  region?: Record<string, unknown> | null;
  inventory?: Array<Record<string, unknown>> | Record<string, unknown>;
  error?: string;
  [key: string]: unknown;
}

/** The regions + dorm types catalog, in the raw shapes the views return. */
export interface InventoryCatalog {
  regions: ListResponse<Region>;
  dormTypes: ListResponse<DormType>;
}
