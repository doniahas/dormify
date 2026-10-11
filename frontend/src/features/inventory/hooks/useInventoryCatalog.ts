import { useCallback, useState } from 'react';
import type { Building, DormType, Id, Region } from '../../../shared/api/contracts';
import { asArray } from '../../../shared/api/normalize';
import { dormInventoryAPI, getInventoryCatalog } from '../api';

export interface InventoryCatalogState {
  regions: Region[];
  dormTypes: DormType[];
  /** Every building of the selected region, active and inactive alike. */
  buildings: Building[];
  /** '' while no region is selected. */
  selectedRegionId: Id;
  setSelectedRegionId: (regionId: Id) => void;
  /** GET /api/regions/ + /api/dorm-types/; resolves with the lists it stored. */
  loadCatalog: () => Promise<{ regionsList: Region[]; dormTypesList: DormType[] }>;
  /** GET /api/buildings/?region=<id>&is_active=all; an empty region clears the list. */
  loadBuildings: (regionId: Id) => Promise<void>;
}

/** The regions / dorm types catalog and the building list of the selected region. */
export function useInventoryCatalog(): InventoryCatalogState {
  const [regions, setRegions] = useState<Region[]>([]);
  const [dormTypes, setDormTypes] = useState<DormType[]>([]);
  const [buildings, setBuildings] = useState<Building[]>([]);
  const [selectedRegionId, setSelectedRegionId] = useState<Id>('');

  const loadCatalog = useCallback(async () => {
    const { regions: regionData, dormTypes: dormTypeData } = await getInventoryCatalog();
    setRegions(asArray<Region>(regionData));
    setDormTypes(asArray<DormType>(dormTypeData));
    return { regionsList: asArray<Region>(regionData), dormTypesList: asArray<DormType>(dormTypeData) };
  }, []);

  const loadBuildings = useCallback(async (regionId: Id) => {
    if (!regionId) {
      setBuildings([]);
      return;
    }
    const data = await dormInventoryAPI.getBuildings({ region: regionId, is_active: 'all' });
    setBuildings(asArray<Building>(data));
  }, []);

  return { regions, dormTypes, buildings, selectedRegionId, setSelectedRegionId, loadCatalog, loadBuildings };
}
