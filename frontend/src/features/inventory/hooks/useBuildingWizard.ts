import { useCallback, useState } from 'react';
import type { Building, Id } from '../../../shared/api/contracts';
import type { BuildingsStrings } from '../BuildingsPage.strings';
import { errorMessage } from '../inventoryHelpers';

export interface BuildingWizardOptions {
  t: BuildingsStrings;
  selectedRegionId: Id;
  loadBuildings: (regionId: Id) => Promise<void>;
  selectBuilding: (buildingId: Id) => Promise<void>;
  setPageError: (message: string) => void;
}

export interface BuildingWizardController {
  isOpen: boolean;
  open: () => void;
  /** The wizard was dismissed; with a building, it was created and gets selected. */
  close: (building?: Building | null) => void;
  /** The wizard finished: reload the region's buildings and select the new one. */
  completed: (building: Building) => Promise<void>;
}

/** The Building Setup Wizard's open state and its hand-back into the page. */
export function useBuildingWizard({
  t, selectedRegionId, loadBuildings, selectBuilding, setPageError,
}: BuildingWizardOptions): BuildingWizardController {
  const [isOpen, setIsOpen] = useState(false);

  const open = useCallback(() => setIsOpen(true), []);

  const completed = useCallback(async (building: Building) => {
    setIsOpen(false);
    try {
      await loadBuildings(selectedRegionId);
    } catch (err) {
      setPageError(errorMessage(err, t.loadError));
    }
    await selectBuilding(building.id);
  }, [loadBuildings, selectedRegionId, setPageError, t.loadError, selectBuilding]);

  const close = useCallback((building?: Building | null) => {
    setIsOpen(false);
    if (building) void completed(building);
  }, [completed]);

  return { isOpen, open, close, completed };
}
