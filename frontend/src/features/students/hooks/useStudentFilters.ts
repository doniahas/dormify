import { useCallback, useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { studentsAPI } from '../api';
import { STUDENT_TABS, type StudentFilters, type StudentTab } from '../model';
import { countActiveFilters, EMPTY_FILTERS } from '../studentHelpers';
import type { StudentFilterOptions } from '../types';

export interface StudentFiltersState {
  activeTab: StudentTab;
  setActiveTab: (tab: StudentTab) => void;
  searchQuery: string;
  setSearchQuery: (query: string) => void;
  filters: StudentFilters;
  setFilters: (next: StudentFilters) => void;
  /** Removes one value from one filter list; clearing a region also clears the buildings. */
  removeFilterValue: (key: keyof StudentFilters, value: string) => void;
  activeFilterCount: number;
  filtersOpen: boolean;
  openFilters: () => void;
  closeFilters: () => void;
  /** Back to the "all" tab with no search and no drawer selections. */
  clearFilters: () => void;
  /** The drawer's choices (/api/students/filter-options/), null until loaded. */
  filterOptions: StudentFilterOptions | null;
}

function isStudentTab(value: string | null): value is StudentTab {
  return value !== null && (STUDENT_TABS as readonly string[]).includes(value);
}

/**
 * Everything that narrows the list: the status tab (initialised from the
 * ?tab= query parameter), the search box, and the drawer's selections -
 * plus the drawer's option catalogue, loaded once.
 */
export function useStudentFilters(): StudentFiltersState {
  const [searchParams] = useSearchParams();
  const [activeTab, setActiveTab] = useState<StudentTab>(() => {
    const requested = searchParams.get('tab');
    return isStudentTab(requested) ? requested : 'all';
  });
  const [searchQuery, setSearchQuery] = useState('');
  const [filters, setFilters] = useState<StudentFilters>(EMPTY_FILTERS);
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [filterOptions, setFilterOptions] = useState<StudentFilterOptions | null>(null);

  useEffect(() => {
    studentsAPI.getFilterOptions().then(setFilterOptions).catch(console.error);
  }, []);

  const activeFilterCount = useMemo(() => countActiveFilters(filters), [filters]);

  const removeFilterValue = useCallback((key: keyof StudentFilters, value: string) => {
    setFilters((f) => ({
      ...f,
      [key]: f[key].filter((x) => String(x) !== String(value)),
      ...(key === 'regions' ? { buildings: [] } : {}),
    }));
  }, []);

  const clearFilters = useCallback(() => {
    setActiveTab('all');
    setSearchQuery('');
    setFilters(EMPTY_FILTERS);
  }, []);

  const openFilters = useCallback(() => setFiltersOpen(true), []);
  const closeFilters = useCallback(() => setFiltersOpen(false), []);

  return {
    activeTab, setActiveTab,
    searchQuery, setSearchQuery,
    filters, setFilters, removeFilterValue,
    activeFilterCount,
    filtersOpen, openFilters, closeFilters,
    clearFilters,
    filterOptions,
  };
}
