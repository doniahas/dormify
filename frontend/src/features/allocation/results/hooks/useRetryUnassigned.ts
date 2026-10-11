import { useCallback, useState } from 'react';
import type { Id } from '../../../../shared/api/contracts';
import { allocationAPI } from '../../api';
import type { AllocationResultsStrings } from '../AllocationResultsPage.strings';
import { errorMessage, retryOutcome } from '../allocationResultsHelpers';

export interface RetryUnassignedOptions {
  t: AllocationResultsStrings;
  /** The run whose unassigned students are retried; null disables the action. */
  currentRunId: Id | null;
  /** Re-reads the saved results once the retry succeeded. */
  onRetried: () => Promise<void>;
}

export interface RetryUnassignedState {
  confirmOpen: boolean;
  openConfirm: () => void;
  closeConfirm: () => void;
  loading: boolean;
  error: string | null;
  success: string | null;
  /** Posts the retry, then refreshes the page's data from the server. */
  retry: () => Promise<void>;
}

/**
 * The "retry unassigned students" workflow: the confirmation modal, the
 * POST scoped to the current run, its success/error message and the
 * refresh of the results that follows a successful retry.
 */
export function useRetryUnassigned({ t, currentRunId, onRetried }: RetryUnassignedOptions): RetryUnassignedState {
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const openConfirm = useCallback(() => setConfirmOpen(true), []);
  const closeConfirm = useCallback(() => setConfirmOpen(false), []);

  const retry = useCallback(async () => {
    if (!currentRunId) {
      setError(t.noRunToRetry);
      return;
    }

    setLoading(true);
    setError(null);
    setSuccess(null);

    try {
      const response = await allocationAPI.retryUnassigned(currentRunId);
      const { assignedNow, retried } = retryOutcome(response);

      setSuccess(t.retryUnassignedSuccess(assignedNow, retried));
      setConfirmOpen(false);

      await onRetried();
    } catch (err) {
      setError(errorMessage(err, t.retryError));
    } finally {
      setLoading(false);
    }
  }, [currentRunId, t, onRetried]);

  return { confirmOpen, openConfirm, closeConfirm, loading, error, success, retry };
}
