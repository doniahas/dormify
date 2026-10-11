import { useCallback, useEffect, useMemo, useState } from 'react';
import { useLocation } from 'react-router-dom';
import type { Id } from '../../../../shared/api/contracts';
import { allocationAPI } from '../../api';
import {
  asRows,
  buildAllocationHierarchy,
  currentRunIdFrom,
  deriveCounts,
  EMPTY_RESULTS,
  errorMessage,
  lastAllocationDate,
  mergeRefreshedResults,
  regionIdFrom,
  resultsFromServer,
  unwrapResults,
} from '../allocationResultsHelpers';
import type {
  AllocationHierarchy,
  AssignmentRow,
  AvailableBedRow,
  ResultsCounts,
  ResultsData,
  ResultsRegion,
  ResultsRouteState,
  ResultsSummary,
  UnassignedAnalysisGroup,
  UnassignedStudentRow,
} from '../model';

export interface AllocationResultsOptions {
  /** The localized fallback shown when a failed load carries no message. */
  errorLoadingResults: string;
}

export interface AllocationResultsState {
  /** What the Allocation page handed over through router state (every field null on a cold visit). */
  routeResult: ResultsData | null;
  summary: ResultsSummary | null;
  region: ResultsRegion | null;
  generatedAt: string | null;
  /** The region the saved results are read for; null means the user's own scope. */
  regionId: Id | null;
  /** The run the page shows, when known - the retry-unassigned action is scoped to it. */
  currentRunId: Id | null;
  result: ResultsData;
  assignments: AssignmentRow[];
  unassignedStudents: UnassignedStudentRow[];
  availableBeds: AvailableBedRow[];
  unassignedAnalysis: UnassignedAnalysisGroup[];
  counts: ResultsCounts;
  hierarchy: AllocationHierarchy;
  /** When the last allocation happened (ISO string or Date), null when unknown. */
  lastAllocationAt: string | Date | null;
  loading: boolean;
  error: string | null;
  /** Re-issues the load after a failure. */
  reload: () => void;
  /** Re-reads the saved results from the server and merges them in (after a retry). */
  refresh: () => Promise<void>;
}

/**
 * The saved allocation results of the region handed over through router
 * state (or of the user's own scope when none was), loaded through the
 * typed adapter on mount and on every retry, plus everything the views
 * derive from them: the typed lists, the tab totals, the location
 * hierarchy and the last-allocation date.
 */
export function useAllocationResults({ errorLoadingResults }: AllocationResultsOptions): AllocationResultsState {
  const location = useLocation();
  const routeState = (location.state as ResultsRouteState | null) || {};
  const {
    result: routeResult = null,
    summary = null,
    region = null,
    generatedAt = null,
  } = routeState;

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [retryToken, setRetryToken] = useState(0);
  const [serverResult, setServerResult] = useState<ResultsData>(routeResult || EMPTY_RESULTS);

  const regionId = regionIdFrom(region, summary);

  /* =======================================================
     Load results
     ======================================================= */

  useEffect(() => {
    let isMounted = true;

    const loadResults = async () => {
      setLoading(true);
      setError(null);

      try {
        const regionIdForLoad = region?.id || summary?.region?.id || summary?.region_id || null;

        const responseRaw = regionIdForLoad
          ? await allocationAPI.getResults(regionIdForLoad)
          : await allocationAPI.getResults();

        const data = unwrapResults(responseRaw);

        if (!isMounted) {
          return;
        }

        setServerResult(resultsFromServer(data, routeResult));
      } catch (err) {
        console.error('Failed to load allocation results:', err);

        if (!isMounted) {
          return;
        }

        setError(errorMessage(err, errorLoadingResults));
      } finally {
        if (isMounted) {
          setLoading(false);
        }
      }
    };

    void loadResults();

    return () => {
      isMounted = false;
    };
  }, [
    region?.id,
    summary?.region?.id,
    summary?.region_id,
    routeResult,
    errorLoadingResults,
    retryToken,
  ]);

  const reload = useCallback(() => {
    setRetryToken((previous) => previous + 1);
  }, []);

  // Refresh this page's data from the server so newly-assigned students
  // move from the "unassigned" tab into "assigned" and the analysis
  // reflects the new state - never a local/optimistic edit.
  const refresh = useCallback(async () => {
    const refreshed = regionId
      ? await allocationAPI.getResults(regionId)
      : await allocationAPI.getResults();
    const refreshedData = unwrapResults(refreshed);

    setServerResult((previous) => mergeRefreshedResults(previous, refreshedData));
  }, [regionId]);

  /* =======================================================
     Derived data
     ======================================================= */

  const result = serverResult || EMPTY_RESULTS;

  const assignments = useMemo(() => asRows<AssignmentRow>(result.assignments), [result.assignments]);
  const unassignedStudents = useMemo(
    () => asRows<UnassignedStudentRow>(result.unassigned_students),
    [result.unassigned_students]
  );
  const availableBeds = useMemo(() => asRows<AvailableBedRow>(result.available_beds), [result.available_beds]);
  const unassignedAnalysis = useMemo(
    () => asRows<UnassignedAnalysisGroup>(result.unassigned_analysis),
    [result.unassigned_analysis]
  );

  const hierarchy = useMemo(
    () => buildAllocationHierarchy(assignments, availableBeds),
    [assignments, availableBeds]
  );

  return {
    routeResult,
    summary,
    region,
    generatedAt,
    regionId,
    currentRunId: currentRunIdFrom(routeResult, summary),
    result,
    assignments,
    unassignedStudents,
    availableBeds,
    unassignedAnalysis,
    counts: deriveCounts(result, assignments, unassignedStudents, availableBeds),
    hierarchy,
    lastAllocationAt: lastAllocationDate(result, summary, assignments, generatedAt),
    loading,
    error,
    reload,
    refresh,
  };
}
