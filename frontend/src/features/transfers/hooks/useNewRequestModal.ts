import { useCallback, useRef, useState } from 'react';
import { mergeBuildings } from '../../allocation/BedMatchPicker';
import { isRequestCancelled, requestsAPI } from '../api';
import type { FeasibilityData, FeasibilityPreviewArgs, NewRequestKind } from '../model';
import { errorMessage, failedFeasibility } from '../transferHelpers';
import type { TransfersStrings } from '../TransfersPage.strings';
import type { StudentRequestPayload } from '../types';

export interface NewRequestModalOptions {
  t: TransfersStrings;
  /** A request was created and the modal has closed; the list should be re-read. */
  onCreated: () => void;
}

export interface NewRequestModalState {
  isOpen: boolean;
  open: () => void;
  close: () => void;
  /** The wizard chosen on the type picker; null while picking. */
  type: NewRequestKind | null;
  setType: (type: NewRequestKind | null) => void;
  submitting: boolean;
  error: string;
  /** POST /api/requests/ with the wizard's payload, then close and refresh. */
  submit: (payload: StudentRequestPayload) => Promise<void>;
  /** Feasibility preview of the Transfer wizard's "options" step. */
  feasData: FeasibilityData | null;
  checkingFeas: boolean;
  loadingMoreFeas: boolean;
  loadMoreFeasError: string;
  checkFeasibility: (args: FeasibilityPreviewArgs) => Promise<void>;
  loadMoreFeasibility: () => Promise<void>;
  clearFeasibility: () => void;
}

/**
 * The New Request modal: the picked wizard, the shared submit, and the
 * feasibility preview (match-options for a request that does not exist
 * yet) the Transfer wizard shows before the request is filed. "Load more"
 * repeats the exact search definition of the last check at the next
 * building offset, appending to what is already on screen.
 */
export function useNewRequestModal({ t, onCreated }: NewRequestModalOptions): NewRequestModalState {
  const [isOpen, setIsOpen] = useState(false);
  const [type, setType] = useState<NewRequestKind | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  const [feasData, setFeasData] = useState<FeasibilityData | null>(null);
  const [checkingFeas, setCheckingFeas] = useState(false);
  const [loadingMoreFeas, setLoadingMoreFeas] = useState(false);
  const [loadMoreFeasError, setLoadMoreFeasError] = useState('');
  // Remembers the params of the last feasibility check so "load more" can
  // repeat the exact same filter (student/type/same-apartment/scope/regions)
  // at the next offset instead of guessing - never mixes results from a
  // different query.
  const feasParamsRef = useRef<FeasibilityPreviewArgs | null>(null);
  const feasAbortRef = useRef<AbortController | null>(null);

  const reset = useCallback(() => {
    if (feasAbortRef.current) feasAbortRef.current.abort();
    feasAbortRef.current = null;
    feasParamsRef.current = null;
    setType(null);
    setSubmitting(false);
    setError('');
    setFeasData(null);
    setCheckingFeas(false);
    setLoadingMoreFeas(false);
    setLoadMoreFeasError('');
  }, []);

  const open = useCallback(() => {
    reset();
    setIsOpen(true);
  }, [reset]);

  const close = useCallback(() => {
    reset();
    setIsOpen(false);
  }, [reset]);

  const submit = useCallback(async (payload: StudentRequestPayload) => {
    setError('');
    setSubmitting(true);
    try {
      await requestsAPI.create(payload);
      onCreated();
      close();
    } catch (err) {
      setError(errorMessage(err, t.errSubmit));
    } finally {
      setSubmitting(false);
    }
  }, [onCreated, close, t]);

  const checkFeasibility = useCallback(async (args: FeasibilityPreviewArgs) => {
    if (feasAbortRef.current) feasAbortRef.current.abort();
    const controller = new AbortController();
    feasAbortRef.current = controller;
    // Remember the FULL search definition (incl. transfer scope and the
    // selected destination regions) so "load more" repeats it exactly.
    feasParamsRef.current = args;
    setCheckingFeas(true);
    setFeasData(null); // clear stale results from a previous filter immediately
    try {
      const d = await requestsAPI.checkFeasibilityForStudent(args.studentId, args.reqType, args.sameApt, {
        signal: controller.signal, transferScope: args.transferScope, regionIds: args.regionIds,
      });
      setFeasData(d);
    } catch (err) {
      if (isRequestCancelled(err)) return;
      setFeasData(failedFeasibility(err, 'buildings'));
    } finally {
      if (feasAbortRef.current === controller) setCheckingFeas(false);
    }
  }, []);

  const loadMoreFeasibility = useCallback(async () => {
    const p = feasParamsRef.current;
    if (!p || !feasData || loadingMoreFeas) return;
    setLoadingMoreFeas(true);
    setLoadMoreFeasError('');
    try {
      // Building-paged: offset counts BUILDINGS already loaded; the next
      // page is appended, never replacing what is already on screen.
      const d = await requestsAPI.checkFeasibilityForStudent(p.studentId, p.reqType, p.sameApt, {
        offset: (feasData.buildings || []).length,
        transferScope: p.transferScope, regionIds: p.regionIds,
      });
      setFeasData((prev) => ({ ...d, buildings: mergeBuildings(prev?.buildings, d.buildings) }));
    } catch (err) {
      // keep existing results visible - a failed "load more" isn't fatal.
      setLoadMoreFeasError(errorMessage(err, t.errGeneric));
    } finally {
      setLoadingMoreFeas(false);
    }
  }, [feasData, loadingMoreFeas, t]);

  const clearFeasibility = useCallback(() => setFeasData(null), []);

  return {
    isOpen, open, close,
    type, setType,
    submitting, error, submit,
    feasData, checkingFeas, loadingMoreFeas, loadMoreFeasError,
    checkFeasibility, loadMoreFeasibility, clearFeasibility,
  };
}
