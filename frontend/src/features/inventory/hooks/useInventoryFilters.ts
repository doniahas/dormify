import { useMemo, useState } from 'react';
import type { Apartment, Bed, Building, DormType, Id, Region, Room } from '../../../shared/api/contracts';
import { sameId } from '../../../shared/api/normalize';
import {
  filterApartments,
  filterBuildings,
  roomsForApartment,
  summarizeBuildings,
} from '../inventoryHelpers';
import type { InventoryStatusFilter, InventorySummaryMetrics } from '../model';

export interface InventoryFiltersInput {
  regions: Region[];
  dormTypesInRegion: DormType[];
  buildings: Building[];
  buildingApartments: Apartment[];
  buildingRooms: Room[];
  roomBeds: Bed[];
  selectedRegionId: Id;
  selectedDormTypeId: string;
  selectedBuildingId: Id;
  selectedApartmentId: Id;
  selectedRoomId: Id;
  selectedBedId: Id;
}

export interface InventoryFiltersState {
  statusFilter: InventoryStatusFilter;
  setStatusFilter: (status: InventoryStatusFilter) => void;
  searchQuery: string;
  setSearchQuery: (query: string) => void;
  /** The navigator list after the dorm type, status and search filters. */
  filteredBuildings: Building[];
  selectedRegion: Region | null;
  selectedDormType: DormType | null;
  selectedBuilding: Building | null;
  /** The selected building's apartments after the search filter. */
  apartmentsForSelectedBuilding: Apartment[];
  selectedApartment: Apartment | null;
  /** The selected apartment's rooms after the search filter. */
  roomsForSelectedApartment: Room[];
  selectedRoom: Room | null;
  selectedBed: Bed | null;
  summaryMetrics: InventorySummaryMetrics;
}

/**
 * The status/search filters and everything derived from the loaded tree and
 * the selection: the filtered lists at each level, the selected records and
 * the summary strip counters.
 */
export function useInventoryFilters({
  regions, dormTypesInRegion, buildings, buildingApartments, buildingRooms, roomBeds,
  selectedRegionId, selectedDormTypeId, selectedBuildingId, selectedApartmentId, selectedRoomId, selectedBedId,
}: InventoryFiltersInput): InventoryFiltersState {
  const [statusFilter, setStatusFilter] = useState<InventoryStatusFilter>('active');
  const [searchQuery, setSearchQuery] = useState('');

  const filteredBuildings = useMemo(
    () => filterBuildings(buildings, selectedDormTypeId, statusFilter, searchQuery),
    [buildings, selectedDormTypeId, statusFilter, searchQuery]
  );

  const selectedRegion = useMemo(
    () => regions.find((r) => sameId(r.id, selectedRegionId)) || null,
    [regions, selectedRegionId]
  );
  const selectedDormType = useMemo(
    () => (selectedDormTypeId === 'all' ? null : dormTypesInRegion.find((dt) => sameId(dt.id, selectedDormTypeId)) || null),
    [dormTypesInRegion, selectedDormTypeId]
  );
  const selectedBuilding = useMemo(
    () => buildings.find((b) => sameId(b.id, selectedBuildingId)) || null,
    [buildings, selectedBuildingId]
  );

  const apartmentsForSelectedBuilding = useMemo(
    () => filterApartments(buildingApartments, searchQuery),
    [buildingApartments, searchQuery]
  );
  const selectedApartment = useMemo(
    () => buildingApartments.find((a) => sameId(a.id, selectedApartmentId)) || null,
    [buildingApartments, selectedApartmentId]
  );
  const roomsForSelectedApartment = useMemo(
    () => roomsForApartment(buildingRooms, selectedApartmentId, searchQuery),
    [buildingRooms, selectedApartmentId, searchQuery]
  );
  const selectedRoom = useMemo(
    () => buildingRooms.find((r) => sameId(r.id, selectedRoomId)) || null,
    [buildingRooms, selectedRoomId]
  );
  const selectedBed = useMemo(
    () => roomBeds.find((b) => sameId(b.id, selectedBedId)) || null,
    [roomBeds, selectedBedId]
  );

  const summaryMetrics = useMemo(
    () => summarizeBuildings(buildings, selectedDormTypeId),
    [buildings, selectedDormTypeId]
  );

  return {
    statusFilter, setStatusFilter, searchQuery, setSearchQuery,
    filteredBuildings, selectedRegion, selectedDormType, selectedBuilding,
    apartmentsForSelectedBuilding, selectedApartment, roomsForSelectedApartment, selectedRoom, selectedBed,
    summaryMetrics,
  };
}
