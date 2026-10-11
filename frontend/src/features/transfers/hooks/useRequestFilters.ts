import { useCallback, useEffect, useState } from 'react';
import type { Region } from '../../../shared/api/contracts';
import { regionsAPI } from '../../inventory/api';
import type { RegionFilter, RequestTab, RequestTypeFilter } from '../model';

export interface RequestFiltersOptions {
  isCentralAdmin: boolean;
}

export interface RequestFiltersState {
  tab: RequestTab;
  setTab: (tab: RequestTab) => void;
  typeFilter: RequestTypeFilter;
  setTypeFilter: (type: RequestTypeFilter) => void;
  /** A stat card selects its status and resets the type filter. */
  selectStatCard: (tab: RequestTab) => void;
  searchQ: string;
  setSearchQ: (query: string) => void;
  clearSearch: () => void;
  /** The regions a central admin may filter by (empty for regional users). */
  regions: Region[];
  regionFilter: RegionFilter;
  setRegionFilter: (region: RegionFilter) => void;
}

/**
 * Everything that narrows the list client-side (status tab, type, search)
 * plus the region filter, which is the one filter sent to the backend.
 * Region filter - central admins only (§9/§11). Loaded from the real
 * regions API, never hardcoded. Regional users never see this selector
 * and the backend ignores any region param they might send directly.
 */
export function useRequestFilters({ isCentralAdmin }: RequestFiltersOptions): RequestFiltersState {
  const [tab, setTab] = useState<RequestTab>('all');
  const [typeFilter, setTypeFilter] = useState<RequestTypeFilter>('all');
  const [searchQ, setSearchQ] = useState('');
  const [regions, setRegions] = useState<Region[]>([]);
  const [regionFilter, setRegionFilter] = useState<RegionFilter>('all');

  useEffect(() => {
    if (isCentralAdmin) {
      regionsAPI.getAll().then(setRegions).catch(() => setRegions([]));
    }
  }, [isCentralAdmin]);

  const selectStatCard = useCallback((key: RequestTab) => {
    setTab(key);
    setTypeFilter('all');
  }, []);

  const clearSearch = useCallback(() => setSearchQ(''), []);

  return {
    tab, setTab,
    typeFilter, setTypeFilter,
    selectStatCard,
    searchQ, setSearchQ, clearSearch,
    regions, regionFilter, setRegionFilter,
  };
}
