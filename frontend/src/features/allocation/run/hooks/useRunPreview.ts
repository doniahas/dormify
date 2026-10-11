import { useCallback, useEffect, useRef, useState } from 'react';
import type { Id } from '../../../../shared/api/contracts';
import { allocationAPI } from '../../api';
import { PREVIEW_POLL_INTERVAL_MS, describeError } from '../allocationRunHelpers';
import type { AllocationRunStrings } from '../AllocationPage.strings';

export interface RunPreviewOptions {
  t: AllocationRunStrings;
}

export interface RunPreviewState {
  isOpen: boolean;
  /** The raw snapshot of the current best-feasible result. */
  snapshot: Record<string, unknown> | null;
  loading: boolean;
  errorMsg: string;
  /** A newer snapshot exists; the one on screen is kept until refreshed. */
  hasNewer: boolean;
  /** Opens the panel for a run and starts its silent 5 s refresh. */
  open: (runId: Id | null) => void;
  close: () => void;
  /** Replaces the shown snapshot with the latest one. */
  refreshToLatest: () => void;
  /** Forgets the previous run's snapshot (a new run is starting). */
  reset: () => void;
}

interface FetchOptions {
  silent?: boolean;
  force?: boolean;
}

/**
 * "צפה בתוצאה הנוכחית": a lightweight read of the current best-feasible
 * snapshot while a run is still RUNNING. Never stops the solver, never
 * creates BedAssignment rows (backend get_allocation_run_preview). While
 * open, the panel re-reads silently every 5 s; a snapshot with a higher
 * sequence is only announced, so what the user is reading stays in place
 * until they refresh.
 */
export function useRunPreview({ t }: RunPreviewOptions): RunPreviewState {
  const [isOpen, setIsOpen] = useState(false);
  const [snapshot, setSnapshot] = useState<Record<string, unknown> | null>(null);
  const [loading, setLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState('');
  const [hasNewer, setHasNewer] = useState(false);

  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const sequenceRef = useRef(0);
  const hasContentRef = useRef(false);
  const mountedRef = useRef(true);
  const runIdRef = useRef<Id | null>(null);

  const stopPolling = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  const close = useCallback(() => {
    setIsOpen(false);
    stopPolling();
  }, [stopPolling]);

  const fetchPreview = useCallback(async ({ silent = false, force = false }: FetchOptions = {}) => {
    const runId = runIdRef.current;
    if (!runId) return;
    if (!silent) setLoading(true);
    if (!silent) setErrorMsg('');

    try {
      const data = await allocationAPI.getPreview(runId);
      if (!mountedRef.current) return;

      if (!data?.available || !data.snapshot) {
        return;
      }

      const incomingSeq = Number(data.snapshot.sequence) || 0;
      const shouldReplace =
        force || !hasContentRef.current || incomingSeq === sequenceRef.current;

      if (shouldReplace) {
        sequenceRef.current = incomingSeq;
        hasContentRef.current = true;
        setSnapshot(data.snapshot);
        setHasNewer(false);
      } else if (incomingSeq > sequenceRef.current) {
        setHasNewer(true);
      }
    } catch (err) {
      if (!silent) setErrorMsg(describeError(err, t.unknownError) || t.previewErrorMsg);
    } finally {
      if (!silent) setLoading(false);
    }
  }, [t.previewErrorMsg, t.unknownError]);

  const open = useCallback((runId: Id | null) => {
    if (!runId) return;
    runIdRef.current = runId;
    setIsOpen(true);
    void fetchPreview();
    stopPolling();
    pollRef.current = setInterval(() => {
      fetchPreview({ silent: true }).catch(() => {});
    }, PREVIEW_POLL_INTERVAL_MS);
  }, [fetchPreview, stopPolling]);

  const refreshToLatest = useCallback(() => {
    fetchPreview({ force: true }).catch(() => {});
  }, [fetchPreview]);

  const reset = useCallback(() => {
    setSnapshot(null);
    setHasNewer(false);
    sequenceRef.current = 0;
    hasContentRef.current = false;
  }, []);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      stopPolling();
    };
  }, [stopPolling]);

  return { isOpen, snapshot, loading, errorMsg, hasNewer, open, close, refreshToLatest, reset };
}
