import { useCallback, useEffect, useRef, useState } from 'react';
import type { Id } from '../../../../shared/api/contracts';
import { allocationAPI, inboxAPI } from '../../api';
import type { AllocationRun, AllocationRunStatus } from '../../types';
import {
  LIVE_RUN_STATUSES,
  STATUS_POLL_INTERVAL_MS,
  buildCompletedResult,
  buildRecoveredResult,
  describeError,
  inboxItemId,
  isApprovedDeleteError,
  regionIdOf,
  resolveRegionId,
  unwrapTyped,
} from '../allocationRunHelpers';
import type { AllocationRunStrings } from '../AllocationPage.strings';
import type {
  ConfirmModalState,
  EffectiveConstraintConfig,
  InboxItemView,
  RunResultView,
  SummaryView,
  ToastType,
} from '../model';

export interface AllocationRunOptions {
  t: AllocationRunStrings;
  /** AuthContext's getUserRegion; read when a run starts. */
  getUserRegion: () => Id | null;
  summary: SummaryView | null;
  inboxItem: InboxItemView | null;
  /** Re-reads the summary (and inbox); resolves with the normalized summary. */
  loadPage: () => Promise<SummaryView | null>;
  /** The page's (non-fatal) error line. */
  setError: (message: string | null) => void;
  showToast: (message: string, type?: ToastType) => void;
  /** The max search time validation ('' when valid) and its error setter. */
  validateMaxSolverTime: () => string;
  setMaxSolverError: (message: string) => void;
  /** The max search time in seconds (non-null whenever validation passes). */
  maxSolverSeconds: number | null;
  /** The `constraints` payload a run is started with. */
  effectiveConfig: EffectiveConstraintConfig;
  applySearchTiming: (runData?: AllocationRun | null) => void;
  resetSearchTiming: () => void;
  /** The current-result preview: closed when the run ends, reset when one starts. */
  closePreview: () => void;
  resetPreview: () => void;
}

export interface AllocationRunState {
  isRunning: boolean;
  result: RunResultView | null;
  runId: Id | null;
  runStatus: AllocationRunStatus | null;
  /** Cancel ("בטל הרצה") was requested. */
  isStopping: boolean;
  /** Stop & Save ("עצור ושמור תוצאה") was requested. */
  isStoppingSave: boolean;
  isDeleting: boolean;
  confirmModal: ConfirmModalState | null;
  closeConfirm: () => void;
  runAllocation: () => Promise<void>;
  requestStopAllocation: () => void;
  requestStopAndSave: () => void;
  requestDeleteResults: () => void;
}

/**
 * The run lifecycle as the page drives it: recovery of an active or
 * completed run on mount, status polling every 3 s until the run completes
 * / stops / fails / is deleted, and the start, cancel, stop-and-save and
 * delete actions with their confirmation dialogs. The allocation itself
 * runs on the backend; this hook only starts it, watches it and shows its
 * outcome.
 */
export function useAllocationRun({
  t,
  getUserRegion,
  summary,
  inboxItem,
  loadPage,
  setError,
  showToast,
  validateMaxSolverTime,
  setMaxSolverError,
  maxSolverSeconds,
  effectiveConfig,
  applySearchTiming,
  resetSearchTiming,
  closePreview,
  resetPreview,
}: AllocationRunOptions): AllocationRunState {
  const [isRunning, setIsRunning]   = useState(false);
  const [result, setResult]         = useState<RunResultView | null>(null);
  const [runId, setRunId]           = useState<Id | null>(null);
  const [runStatus, setRunStatus]   = useState<AllocationRunStatus | null>(null);
  const [isStopping, setIsStopping] = useState(false);
  const [isStoppingSave, setIsStoppingSave] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const [confirmModal, setConfirmModal] = useState<ConfirmModalState | null>(null);

  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const mountedRef = useRef(true);

  const stopPolling = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  const startPolling = useCallback((id: Id) => {
    stopPolling();
    pollRef.current = setInterval(async () => {
      if (!mountedRef.current) { stopPolling(); return; }

      try {
        const data = await allocationAPI.getRunStatus(id);
        const runData = data?.run;
        const st = runData?.status;

        if (!mountedRef.current) return;
        setRunStatus(st ?? null);
        applySearchTiming(runData);

        if (st === 'completed') {
          stopPolling();
          closePreview();
          setIsRunning(false);
          setIsStopping(false);
          setIsStoppingSave(false);
          setResult(buildCompletedResult(data, runData));
          loadPage().catch(() => {});
          if (data.stopped_early_by_user) showToast(t.stopAndSaveSuccess, 'success');
        } else if (st === 'stopped' || st === 'failed' || st === 'deleted') {
          stopPolling();
          closePreview();
          setIsRunning(false);
          setIsStopping(false);
          setIsStoppingSave(false);
          setResult(null);
          setRunId(null);
          setRunStatus(null);
          loadPage().catch(() => {});
          if (st === 'stopped')      showToast(t.stoppedStatus, 'info');
          else if (st === 'failed')  showToast(runData?.error_message || t.unknownError, 'error');
        } else if (st === 'cancellation_requested') {
          setIsStopping(true);
        } else if (st === 'stop_and_save_requested') {
          setIsStoppingSave(true);
        }
      } catch (err) {
        console.warn('Polling error:', err);
      }
    }, STATUS_POLL_INTERVAL_MS);
  }, [stopPolling, closePreview, loadPage, showToast, t.stoppedStatus, t.unknownError, t.stopAndSaveSuccess, applySearchTiming]);

  const recoverActiveRun = useCallback(
    async (regionId: Id | null, currentSummary: SummaryView | null = null) => {
      try {
        const data = await allocationAPI.getActiveRun(regionId || undefined);

        const run = data?.run;

        if (!run || !mountedRef.current) {
          return;
        }

        const assignedNow = Number(currentSummary?.assigned_students) || 0;
        const hasAssignmentsNow = assignedNow > 0;

        // A run that is live right now is always restored, even before any
        // assignment exists.
        if (LIVE_RUN_STATUSES.includes(run.status)) {
          setRunId(run.id);
          setRunStatus(run.status);
          setIsRunning(true);
          applySearchTiming(run);

          if (run.status === 'cancellation_requested') {
            setIsStopping(true);
          }

          if (run.status === 'stop_and_save_requested') {
            setIsStoppingSave(true);
          }

          startPolling(run.id);
          return;
        }

        // The last run completed but no assignments exist in the database:
        // a historical run whose results were deleted.
        if (run.status === 'completed' && !hasAssignmentsNow) {
          setResult(null);
          setRunId(null);
          setRunStatus(null);
          setIsRunning(false);
          setIsStopping(false);
          return;
        }

        // A completed result is restored only while assignments still exist.
        if (run.status === 'completed' && hasAssignmentsNow) {
          try {
            const detail = await allocationAPI.getRunStatus(run.id);

            if (mountedRef.current && detail?.run?.status === 'completed') {
              setRunId(run.id);
              setRunStatus('completed');
              setResult(buildRecoveredResult(detail, assignedNow, currentSummary));
            }
          } catch (error) {
            console.warn(
              'Failed to load completed run detail:',
              error
            );

            setResult(null);
            setRunId(null);
            setRunStatus(null);
          }

          return;
        }

        setResult(null);
        setRunId(null);
        setRunStatus(null);
      } catch (error) {
        console.warn(
          'Failed to recover active run:',
          error
        );
      }
    },
    [startPolling, applySearchTiming]
  );

  const loadPageRef = useRef(loadPage);
  const recoverRef  = useRef(recoverActiveRun);
  useEffect(() => { loadPageRef.current = loadPage; }, [loadPage]);
  useEffect(() => { recoverRef.current = recoverActiveRun; }, [recoverActiveRun]);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      stopPolling();
    };
  }, [stopPolling]);

  // First load: the summary, then whichever run the backend reports for
  // the summary's region.
  useEffect(() => {
    let cancelled = false;

    const init = async () => {
      const loadedSummary = await loadPageRef.current();

      if (cancelled || !mountedRef.current) {
        return;
      }

      const regionId = regionIdOf(loadedSummary?.region);

      await recoverRef.current(regionId, loadedSummary);
    };

    init().catch(console.warn);

    return () => {
      cancelled = true;
    };
  }, []);

  // ── Actions ──────────────────────────────────

  const runAllocation = async () => {
    if (isRunning || isStopping || isStoppingSave || isDeleting) return;

    const maxTimeError = validateMaxSolverTime();
    if (maxTimeError) {
      setMaxSolverError(maxTimeError);
      return;
    }
    setMaxSolverError('');

    setIsRunning(true);
    setResult(null);
    setError(null);
    setRunId(null);
    setRunStatus(null);
    resetSearchTiming();
    resetPreview();

    const regionId = resolveRegionId(getUserRegion(), summary);
    if (!regionId) {
      setIsRunning(false);
      setError(t.noRegion);
      return;
    }

    try {
      const responseRaw = await allocationAPI.startRun(regionId, {
        constraints: effectiveConfig,
        // Validation above guarantees a positive number here.
        max_solver_seconds: maxSolverSeconds ?? undefined,
      });
      const response = unwrapTyped(responseRaw);
      const id = response?.run_id || response?.run?.id;
      if (!id) throw new Error(t.missingRunId);

      setRunId(id);
      setRunStatus('queued');
      applySearchTiming(response?.run);
      startPolling(id);

      const inboxId = inboxItemId(inboxItem);
      if (inboxId) {
        inboxAPI.markProcessed(inboxId).catch(() => {});
      }
    } catch (err) {
      setError(describeError(err, t.unknownError));
      setIsRunning(false);
      setRunId(null);
      setRunStatus(null);
      resetSearchTiming();
    }
  };

  const requestStopAllocation = () => {
    if (!runId) { showToast(t.missingRunId, 'error'); return; }
    if (isStopping || isStoppingSave) return;
    setConfirmModal({
      title: t.stopConfirmTitle,
      message: t.stopConfirmMsg,
      onConfirm: async () => {
        setConfirmModal(null);
        setIsStopping(true);
        try {
          await allocationAPI.stopRun(runId);
          showToast(t.stopSuccess, 'info');
          setRunStatus('cancellation_requested');
        } catch (err) {
          showToast(describeError(err, t.unknownError) || t.stopError, 'error');
          setIsStopping(false);
        }
      },
    });
  };

  const requestStopAndSave = () => {
    if (!runId) { showToast(t.missingRunId, 'error'); return; }
    if (isStopping || isStoppingSave) return;
    setConfirmModal({
      title: t.stopAndSaveConfirmTitle,
      message: t.stopAndSaveConfirmMsg,
      onConfirm: async () => {
        setConfirmModal(null);
        setIsStoppingSave(true);
        try {
          await allocationAPI.stopAndSave(runId);
          showToast(t.stopAndSaveSuccess, 'info');
          setRunStatus('stop_and_save_requested');
        } catch (err) {
          showToast(describeError(err, t.unknownError) || t.stopAndSaveError, 'error');
          setIsStoppingSave(false);
        }
      },
    });
  };

  const requestDeleteResults = () => {
    if (!runId) { showToast(t.missingRunId, 'error'); return; }
    setConfirmModal({
      title: t.deleteConfirmTitle,
      message: t.deleteConfirmMsg,
      onConfirm: async () => {
        setConfirmModal(null);
        setIsDeleting(true);
        try {
          await allocationAPI.deleteResults(runId);

          stopPolling();

          setResult(null);
          setRunId(null);
          setRunStatus(null);
          resetSearchTiming();
          setIsRunning(false);
          setIsStopping(false);

          await loadPage();

          showToast(t.deleteSuccess, 'success');
        } catch (err) {
          const msg = describeError(err, t.unknownError);
          const isApproved = isApprovedDeleteError(err, msg);
          showToast(isApproved ? t.approvedCannotDelete : (msg || t.deleteError), 'error');
        } finally {
          if (mountedRef.current) setIsDeleting(false);
        }
      },
    });
  };

  const closeConfirm = useCallback(() => setConfirmModal(null), []);

  return {
    isRunning, result, runId, runStatus, isStopping, isStoppingSave, isDeleting,
    confirmModal, closeConfirm,
    runAllocation, requestStopAllocation, requestStopAndSave, requestDeleteResults,
  };
}
