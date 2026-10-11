import { useCallback, useEffect, useMemo, useState } from 'react';
import type { DormType, Id } from '../../../shared/api/contracts';
import { idOf } from '../../../shared/api/normalize';
import type { Language } from '../../../shared/i18n';
import type { BuildingsStrings } from '../BuildingsPage.strings';
import { dormTypesForRegion, errorMessage, resolveInitialRegionId } from '../inventoryHelpers';
import { useBuildingStructure, type BuildingStructureState } from './useBuildingStructure';
import { useInventoryCatalog, type InventoryCatalogState } from './useInventoryCatalog';

export interface InventoryWorkspaceOptions {
  t: BuildingsStrings;
  language: Language;
  /** The page's query string: ?region=, ?dormTypeId= and ?building= deep links. */
  searchParams: URLSearchParams;
  /** The signed-in user's region id ('' for none). */
  userRegionId: string;
  /** Central admins and region bosses may open any region from a deep link. */
  canViewAllRegions: boolean;
}

export interface InventoryWorkspaceState extends InventoryCatalogState, BuildingStructureState {
  /** The whole page is loading (first load, region switch, refresh). */
  loading: boolean;
  pageError: string;
  setPageError: (message: string) => void;
  /** 'all' or a dorm type id; reset to 'all' on region change or when the dorm type leaves the region. */
  selectedDormTypeId: string;
  setSelectedDormTypeId: (id: string) => void;
  dormTypesInRegion: DormType[];
  /** Switches region: resets the dorm type filter and the selection, then reloads the buildings. */
  selectRegion: (regionId: Id) => Promise<void>;
  /** Re-reads the buildings, the selected building's structure and the selected room's beds. */
  refreshCurrentScope: () => Promise<void>;
  /** The header's refresh action: refreshCurrentScope behind the page busy flag. */
  handleRefresh: () => Promise<void>;
}

/**
 * The inventory tree as the page shows it: the catalog, the buildings of
 * the selected region and the selection beneath. On mount (and whenever
 * the language changes, as the page always did) it resolves the region from
 * the user / the deep link, loads the buildings and pre-selects a deep-linked
 * building.
 */
export function useInventoryWorkspace({
  t, language, searchParams, userRegionId, canViewAllRegions,
}: InventoryWorkspaceOptions): InventoryWorkspaceState {
  const catalog = useInventoryCatalog();
  const structure = useBuildingStructure({ t });
  const { dormTypes, selectedRegionId, setSelectedRegionId, loadCatalog, loadBuildings } = catalog;
  const { selectedBuildingId, selectedRoomId, clearBuilding, selectBuilding, fetchStructure, fetchBeds } = structure;

  const [loading, setLoading] = useState(true);
  const [pageError, setPageError] = useState('');
  const [selectedDormTypeId, setSelectedDormTypeId] = useState('all');

  const dormTypesInRegion = useMemo(
    () => dormTypesForRegion(dormTypes, selectedRegionId),
    [dormTypes, selectedRegionId]
  );

  const selectRegion = useCallback(async (regionId: Id) => {
    setSelectedRegionId(regionId);
    setSelectedDormTypeId('all');
    clearBuilding();
    setLoading(true);
    try {
      await loadBuildings(regionId);
    } catch (err) {
      setPageError(errorMessage(err, t.loadError));
    } finally {
      setLoading(false);
    }
  }, [setSelectedRegionId, clearBuilding, loadBuildings, t.loadError]);

  const refreshCurrentScope = useCallback(async () => {
    if (selectedRegionId) await loadBuildings(selectedRegionId);
    if (selectedBuildingId) await fetchStructure(selectedBuildingId);
    if (selectedRoomId) await fetchBeds(selectedRoomId);
  }, [selectedRegionId, selectedBuildingId, selectedRoomId, loadBuildings, fetchStructure, fetchBeds]);

  useEffect(() => {
    const init = async () => {
      setLoading(true);
      setPageError('');
      try {
        const { regionsList } = await loadCatalog();

        const resolvedRegionId = resolveInitialRegionId({
          regionsList,
          urlRegion: searchParams.get('region'),
          userRegionId,
          canViewAllRegions,
        });
        setSelectedRegionId(resolvedRegionId);

        const urlDormTypeIdRaw = searchParams.get('dormTypeId');
        if (urlDormTypeIdRaw) setSelectedDormTypeId(idOf(urlDormTypeIdRaw));

        if (resolvedRegionId) await loadBuildings(resolvedRegionId);

        // Deep link from the Data Analysis page ("View building details"):
        // ?region=<id>&building=<id> pre-selects the building on arrival.
        const urlBuildingIdRaw = searchParams.get('building');
        if (urlBuildingIdRaw) {
          await selectBuilding(idOf(urlBuildingIdRaw));
        }
      } catch (err) {
        console.error('ERROR LOADING BUILDINGS PAGE:', err);
        setPageError(errorMessage(err, t.loadError));
      } finally {
        setLoading(false);
      }
    };
    void init();
    // Re-runs only when the language changes, exactly as the page always did.
  }, [language]);

  useEffect(() => {
    if (!selectedRegionId || selectedDormTypeId === 'all') return;
    const stillValid = dormTypesInRegion.some((dt) => idOf(dt.id) === idOf(selectedDormTypeId));
    if (!stillValid) setSelectedDormTypeId('all');
  }, [selectedRegionId, selectedDormTypeId, dormTypesInRegion]);

  const handleRefresh = useCallback(async () => {
    setLoading(true);
    setPageError('');
    try {
      await refreshCurrentScope();
    } catch (err) {
      setPageError(errorMessage(err, t.loadError));
    } finally {
      setLoading(false);
    }
  }, [refreshCurrentScope, t.loadError]);

  return {
    ...catalog,
    ...structure,
    loading,
    pageError,
    setPageError,
    selectedDormTypeId,
    setSelectedDormTypeId,
    dormTypesInRegion,
    selectRegion,
    refreshCurrentScope,
    handleRefresh,
  };
}
