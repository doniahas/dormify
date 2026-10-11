import { api, getErrorMessage, throwApiError } from "../../shared/api/client";
import type {
  Apartment,
  Bed,
  Building,
  DormType,
  Id,
  ListResponse,
  Paginated,
  Region,
  Room,
} from "../../shared/api/contracts";
import { asArray, continuationPath } from "../../shared/api/normalize";
import type {
  ApartmentPayload,
  BedPayload,
  BuildingPayload,
  BulkCreateInventoryPayload,
  BulkCreateInventoryResponse,
  InventoryByHousingType,
  InventoryCatalog,
  InventoryListParams,
  RoomPayload,
} from "./types";

export const inventoryAPI = {
  getByHousingType: async (regionId: Id | null = null): Promise<InventoryByHousingType> => {
    try {
      const url = regionId
        ? `/api/inventory/by-housing-type/?region=${regionId}`
        : "/api/inventory/by-housing-type/";
      const { data } = await api.get<InventoryByHousingType>(url);
      return data;
    } catch (err) {
      throw new Error(getErrorMessage(err, "Failed to load inventory by housing type"));
    }
  },
};

export const apartmentsAPI = {
  getAll: async (): Promise<ListResponse<Apartment>> => {
    try {
      const { data } = await api.get<ListResponse<Apartment>>("/api/apartments/");
      return data;
    } catch (err) {
      throw new Error(getErrorMessage(err, "Failed to load apartments"));
    }
  },
};

export const roomsAPI = {
  getAll: async (): Promise<ListResponse<Room>> => {
    try {
      const { data } = await api.get<ListResponse<Room>>("/api/rooms/");
      return data;
    } catch (err) {
      throw new Error(getErrorMessage(err, "Failed to load rooms"));
    }
  },
};

// Dormitory structure management (BuildingsPage): Building -> Apartment ->
// Room -> Bed. Named distinctly from the pre-existing `inventoryAPI`
// (housing-type inventory summary) above to avoid a name collision.
// Every write goes through throwApiError so structured backend errors
// ({field, code, message} for occupant-conflict / capacity / availability
// rules) survive as err.fieldErrors instead of being flattened into a
// single opaque string.

export const dormInventoryAPI = {
  getBuildings: async (params: InventoryListParams = {}): Promise<ListResponse<Building>> => {
    try {
      const { data } = await api.get<ListResponse<Building>>("/api/buildings/", { params });
      return data;
    } catch (err) {
      return throwApiError(err, "Failed to load buildings");
    }
  },
  createBuilding: async (payload: BuildingPayload): Promise<Building> => {
    try {
      const { data } = await api.post<Building>("/api/buildings/", payload);
      return data;
    } catch (err) {
      return throwApiError(err, "Failed to create building");
    }
  },
  updateBuilding: async (id: Id, payload: BuildingPayload): Promise<Building> => {
    try {
      const { data } = await api.patch<Building>(`/api/buildings/${id}/`, payload);
      return data;
    } catch (err) {
      return throwApiError(err, "Failed to update building");
    }
  },
  // Building Setup Wizard: transactionally create many Apartments (each
  // with its own Rooms and materialized Beds) under one Building in a
  // single call. See BuildingViewSet.bulk_create_inventory on the backend.
  bulkCreateInventory: async (
    buildingId: Id,
    payload: BulkCreateInventoryPayload
  ): Promise<BulkCreateInventoryResponse> => {
    try {
      const { data } = await api.post<BulkCreateInventoryResponse>(
        `/api/buildings/${buildingId}/bulk-create-inventory/`,
        payload
      );
      return data;
    } catch (err) {
      return throwApiError(err, "Failed to create building inventory");
    }
  },

  getApartments: async (params: InventoryListParams = {}): Promise<ListResponse<Apartment>> => {
    try {
      const { data } = await api.get<ListResponse<Apartment>>("/api/apartments/", { params });
      return data;
    } catch (err) {
      return throwApiError(err, "Failed to load apartments");
    }
  },
  createApartment: async (payload: ApartmentPayload): Promise<Apartment> => {
    try {
      const { data } = await api.post<Apartment>("/api/apartments/", payload);
      return data;
    } catch (err) {
      return throwApiError(err, "Failed to create apartment");
    }
  },
  updateApartment: async (id: Id, payload: ApartmentPayload): Promise<Apartment> => {
    try {
      const { data } = await api.patch<Apartment>(`/api/apartments/${id}/`, payload);
      return data;
    } catch (err) {
      return throwApiError(err, "Failed to update apartment");
    }
  },

  getRooms: async (params: InventoryListParams = {}): Promise<ListResponse<Room>> => {
    try {
      const { data } = await api.get<ListResponse<Room>>("/api/rooms/", { params });
      return data;
    } catch (err) {
      return throwApiError(err, "Failed to load rooms");
    }
  },
  createRoom: async (payload: RoomPayload): Promise<Room> => {
    try {
      const { data } = await api.post<Room>("/api/rooms/", payload);
      return data;
    } catch (err) {
      return throwApiError(err, "Failed to create room");
    }
  },
  updateRoom: async (id: Id, payload: RoomPayload): Promise<Room> => {
    try {
      const { data } = await api.patch<Room>(`/api/rooms/${id}/`, payload);
      return data;
    } catch (err) {
      return throwApiError(err, "Failed to update room");
    }
  },

  getBeds: async (params: InventoryListParams = {}): Promise<ListResponse<Bed>> => {
    try {
      const { data } = await api.get<ListResponse<Bed>>("/api/beds/", { params });
      return data;
    } catch (err) {
      return throwApiError(err, "Failed to load beds");
    }
  },
  updateBed: async (id: Id, payload: BedPayload): Promise<Bed> => {
    try {
      const { data } = await api.patch<Bed>(`/api/beds/${id}/`, payload);
      return data;
    } catch (err) {
      return throwApiError(err, "Failed to update bed");
    }
  },
};

// Assisted Allocation workbench (accessibility + unassigned students).
// Same throwApiError convention as dormInventoryAPI/requestsAPI so
// structured backend errors (violated-rule lists, {error} messages) survive
// as err.fieldErrors instead of being flattened.

export const regionsAPI = {
  getAll: async (): Promise<Region[]> => {
    try {
      const { data } = await api.get<ListResponse<Region>>('/api/regions/');
      return asArray<Region>(data);
    } catch (err) {
      throw new Error(getErrorMessage(err, 'Failed to load regions'));
    }
  },
};

// Follows a paginated list to its end. A view that answers with a plain
// array is complete in one page; the continuation link is absolute and is
// reduced to its path so the shared client applies the base URL.
export async function getAllInventoryPages<T>(firstUrl: string): Promise<T[]> {
  let allItems: T[] = [];
  let nextUrl: string | null = firstUrl;

  while (nextUrl) {
    const { data } = await api.get<Paginated<T> | T[] | null>(nextUrl);

    if (Array.isArray(data)) {
      allItems = data;
      nextUrl = null;
    } else {
      allItems = [...allItems, ...(data?.results || [])];
      nextUrl = continuationPath(data?.next);
    }
  }

  return allItems;
}

export async function getInventoryCatalog(): Promise<InventoryCatalog> {
  const [regions, dormTypes] = await Promise.all([
    api.get<ListResponse<Region>>('/api/regions/'),
    api.get<ListResponse<DormType>>('/api/dorm-types/'),
  ]);
  return { regions: regions.data, dormTypes: dormTypes.data };
}
