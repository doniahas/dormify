import { useCallback, useEffect, useRef, useState } from 'react';
import type { AllocationRun } from '../../types';
import { ELAPSED_TICK_MS, toSearchTiming } from '../allocationRunHelpers';
import type { SearchTiming } from '../model';

export interface SearchTimingState {
  searchTiming: SearchTiming | null;
  /** Seconds elapsed, extrapolated from the server anchor while the run is live. */
  displayElapsed: number;
  /** Re-anchors to a run's timing fields; clears when there is no run. */
  applySearchTiming: (runData?: AllocationRun | null) => void;
  resetSearchTiming: () => void;
}

/**
 * Search timing anchored to the backend's AllocationRun.search_started_at
 * (via AllocationRunSerializer.elapsed_search_seconds /
 * remaining_search_seconds - see get_active_allocation_run /
 * get_allocation_run_detail), never to local React lifetime. `searchTiming`
 * holds the last server-confirmed snapshot plus the client clock at the
 * moment it was received; the ticking effect only ever extrapolates FROM
 * that anchor, so a page navigation, refresh, or a second tab opened on
 * /allocation all recompute the same correct elapsed/remaining from
 * persisted backend state instead of restarting from zero.
 */
export function useSearchTiming(): SearchTimingState {
  const [searchTiming, setSearchTiming] = useState<SearchTiming | null>(null);
  const [displayElapsed, setDisplayElapsed] = useState(0);
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;
    return () => { mountedRef.current = false; };
  }, []);

  useEffect(() => {
    if (!searchTiming) {
      setDisplayElapsed(0);
      return;
    }

    const tick = () => {
      if (!mountedRef.current) return;
      if (searchTiming.live) {
        const nextElapsed = searchTiming.elapsedAtSync + (Date.now() - searchTiming.syncedAtClientMs) / 1000;
        setDisplayElapsed(nextElapsed);
      } else {
        setDisplayElapsed(searchTiming.elapsedAtSync);
      }
    };

    tick();
    if (!searchTiming.live) return undefined;

    const id = setInterval(tick, ELAPSED_TICK_MS);
    return () => clearInterval(id);
  }, [searchTiming]);

  const applySearchTiming = useCallback((runData?: AllocationRun | null) => {
    setSearchTiming(toSearchTiming(runData));
  }, []);

  const resetSearchTiming = useCallback(() => setSearchTiming(null), []);

  return { searchTiming, displayElapsed, applySearchTiming, resetSearchTiming };
}
