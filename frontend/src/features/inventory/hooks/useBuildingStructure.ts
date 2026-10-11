import { useCallback, useState } from 'react';
import type { Apartment, Bed, Id, Room } from '../../../shared/api/contracts';
import { asArray, idOf } from '../../../shared/api/normalize';
import { dormInventoryAPI } from '../api';
import type { BuildingsStrings } from '../BuildingsPage.strings';
import { errorMessage } from '../inventoryHelpers';

export interface BuildingStructureState {
  /** '' while nothing is selected at that level. */
  selectedBuildingId: Id;
  selectedApartmentId: Id;
  selectedRoomId: Id;
  selectedBedId: Id;
  buildingApartments: Apartment[];
  buildingRooms: Room[];
  roomBeds: Bed[];
  loadingStructure: boolean;
  loadingBeds: boolean;
  /** The building's details strip is expanded. */
  buildingDetailsOpen: boolean;
  toggleBuildingDetails: () => void;
  /** Errors from loading a building's structure or a room's beds. */
  actionError: string;
  clearActionError: () => void;
  /** Deselects the building and everything under it. */
  clearBuilding: () => void;
  /** Selects a building and loads its apartments and rooms; selecting it again deselects it. */
  selectBuilding: (buildingId: Id) => Promise<void>;
  selectApartment: (apartmentId: Id) => void;
  /** Selects a room and loads its beds; selecting it again deselects it. */
  selectRoom: (roomId: Id) => Promise<void>;
  selectBed: (bedId: Id) => void;
  /** Re-reads a building's apartments and rooms (no busy flag; errors propagate). */
  fetchStructure: (buildingId: Id) => Promise<void>;
  /** Re-reads a room's beds (no busy flag; errors propagate). */
  fetchBeds: (roomId: Id) => Promise<void>;
}

export interface BuildingStructureOptions {
  t: BuildingsStrings;
}

/**
 * The selection below the region - building, apartment, room, bed - and
 * the apartments/rooms/beds loaded for it. Selecting a level again toggles
 * it off; changing a level clears everything beneath it.
 */
export function useBuildingStructure({ t }: BuildingStructureOptions): BuildingStructureState {
  const [selectedBuildingId, setSelectedBuildingId] = useState<Id>('');
  const [selectedApartmentId, setSelectedApartmentId] = useState<Id>('');
  const [selectedRoomId, setSelectedRoomId] = useState<Id>('');
  const [selectedBedId, setSelectedBedId] = useState<Id>('');

  const [buildingApartments, setBuildingApartments] = useState<Apartment[]>([]);
  const [buildingRooms, setBuildingRooms] = useState<Room[]>([]);
  const [roomBeds, setRoomBeds] = useState<Bed[]>([]);

  const [loadingStructure, setLoadingStructure] = useState(false);
  const [loadingBeds, setLoadingBeds] = useState(false);
  const [actionError, setActionError] = useState('');
  const [buildingDetailsOpen, setBuildingDetailsOpen] = useState(false);

  const resetSelectionBelowBuilding = useCallback(() => {
    setSelectedApartmentId('');
    setSelectedRoomId('');
    setSelectedBedId('');
    setBuildingApartments([]);
    setBuildingRooms([]);
    setRoomBeds([]);
  }, []);

  const clearBuilding = useCallback(() => {
    setSelectedBuildingId('');
    resetSelectionBelowBuilding();
  }, [resetSelectionBelowBuilding]);

  const fetchStructure = useCallback(async (buildingId: Id) => {
    const [apartmentsData, roomsData] = await Promise.all([
      dormInventoryAPI.getApartments({ building: buildingId, is_active: 'all' }),
      dormInventoryAPI.getRooms({ building: buildingId, is_active: 'all' }),
    ]);
    setBuildingApartments(asArray<Apartment>(apartmentsData));
    setBuildingRooms(asArray<Room>(roomsData));
  }, []);

  const fetchBeds = useCallback(async (roomId: Id) => {
    const data = await dormInventoryAPI.getBeds({ room: roomId });
    setRoomBeds(asArray<Bed>(data));
  }, []);

  const selectBuilding = useCallback(async (buildingId: Id) => {
    setBuildingDetailsOpen(false);
    if (idOf(selectedBuildingId) === idOf(buildingId)) {
      setSelectedBuildingId('');
      resetSelectionBelowBuilding();
      return;
    }
    setSelectedBuildingId(buildingId);
    resetSelectionBelowBuilding();
    setLoadingStructure(true);
    try {
      await fetchStructure(buildingId);
    } catch (err) {
      setActionError(errorMessage(err, t.loadError));
    } finally {
      setLoadingStructure(false);
    }
  }, [selectedBuildingId, resetSelectionBelowBuilding, fetchStructure, t.loadError]);

  const selectApartment = useCallback((apartmentId: Id) => {
    setSelectedApartmentId((prev) => (idOf(prev) === idOf(apartmentId) ? '' : apartmentId));
    setSelectedRoomId('');
    setSelectedBedId('');
    setRoomBeds([]);
  }, []);

  const selectRoom = useCallback(async (roomId: Id) => {
    if (idOf(selectedRoomId) === idOf(roomId)) {
      setSelectedRoomId('');
      setSelectedBedId('');
      setRoomBeds([]);
      return;
    }
    setSelectedRoomId(roomId);
    setSelectedBedId('');
    setLoadingBeds(true);
    try {
      await fetchBeds(roomId);
    } catch (err) {
      setActionError(errorMessage(err, t.loadError));
    } finally {
      setLoadingBeds(false);
    }
  }, [selectedRoomId, fetchBeds, t.loadError]);

  const selectBed = useCallback((bedId: Id) => {
    setSelectedBedId((prev) => (idOf(prev) === idOf(bedId) ? '' : bedId));
  }, []);

  const toggleBuildingDetails = useCallback(() => setBuildingDetailsOpen((o) => !o), []);
  const clearActionError = useCallback(() => setActionError(''), []);

  return {
    selectedBuildingId, selectedApartmentId, selectedRoomId, selectedBedId,
    buildingApartments, buildingRooms, roomBeds,
    loadingStructure, loadingBeds,
    buildingDetailsOpen, toggleBuildingDetails,
    actionError, clearActionError,
    clearBuilding, selectBuilding, selectApartment, selectRoom, selectBed,
    fetchStructure, fetchBeds,
  };
}
