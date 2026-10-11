import { useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import type { Id } from '../../../../shared/api/contracts';
import { buildBuildingsSearch } from '../allocationResultsHelpers';
import type { UnassignedAnalysisGroup } from '../model';

export interface ResultsNavigation {
  /** Back to the Allocation page. */
  goBack: () => void;
  /** Buildings management, pre-scoped to an analysis group's dorm type and region. */
  goToBuildings: (group: UnassignedAnalysisGroup) => void;
}

/** Where the results page leads: back to the allocation run, or on to Buildings management. */
export function useResultsNavigation(regionId: Id | null): ResultsNavigation {
  const navigate = useNavigate();

  const goBack = useCallback(() => {
    navigate('/allocation');
  }, [navigate]);

  const goToBuildings = useCallback((group: UnassignedAnalysisGroup) => {
    navigate(`/buildings?${buildBuildingsSearch(regionId, group)}`);
  }, [navigate, regionId]);

  return { goBack, goToBuildings };
}
