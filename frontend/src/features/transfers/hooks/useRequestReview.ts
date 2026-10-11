import { useCallback, useRef, useState } from 'react';
import { mergeBuildings } from '../../allocation/BedMatchPicker';
import { isRequestCancelled, requestsAPI } from '../api';
import type { BedSelection, FeasibilityData, RequestReviewView } from '../model';
import { errorMessage, failedFeasibility } from '../transferHelpers';
import type { TransfersStrings } from '../TransfersPage.strings';
import type { StudentRequest } from '../types';

export interface RequestReviewOptions {
  t: TransfersStrings;
}

type ById<T> = Record<number, T>;

export interface RequestReviewState {
  /** The review slice of one request, as the detail pane consumes it. */
  forRequest: (id: number) => RequestReviewView;
  /** Loads the add-student bed options once per request (on selection). */
  loadBedOptions: (request: StudentRequest) => Promise<void>;
  loadMoreBedOptions: (id: number) => Promise<void>;
  /** Runs (or re-runs) the feasibility check of a pending transfer request. */
  checkFeasibility: (id: number) => Promise<void>;
  loadMoreFeasibility: (id: number) => Promise<void>;
  setRoomSelection: (id: number, selection: BedSelection) => void;
  setFeasSelection: (id: number, selection: BedSelection) => void;
}

/**
 * Per-request review state, keyed by request id so switching between
 * requests keeps what was already checked or picked: feasibility results
 * for room/apartment transfers, bed options for add_student requests, their
 * building-paged "load more", and the bed chosen for approval. Buildings are
 * the pagination unit: the next page is appended, never replacing what is
 * already on screen, and an in-flight check is aborted by a newer one.
 */
export function useRequestReview({ t }: RequestReviewOptions): RequestReviewState {
  const [feasData, setFeasData] = useState<ById<FeasibilityData | null>>({});
  const [checkingFeas, setCheckingFeas] = useState<number | null>(null);
  const [loadingMoreFeasId, setLoadingMoreFeasId] = useState<number | null>(null);
  const [bedOptions, setBedOptions] = useState<ById<FeasibilityData>>({});
  const [loadingBeds, setLoadingBeds] = useState<number | null>(null);
  const [loadingMoreBedsId, setLoadingMoreBedsId] = useState<number | null>(null);
  const [bedsError, setBedsError] = useState<ById<string>>({});
  // Failed "load more buildings" attempts, keyed by request id - existing
  // results always stay visible; the picker shows the error with a retry.
  const [loadMoreFeasErr, setLoadMoreFeasErr] = useState<ById<string>>({});
  const [loadMoreBedsErr, setLoadMoreBedsErr] = useState<ById<string>>({});
  const [selRoom, setSelRoom] = useState<ById<BedSelection>>({});
  const [selFeasOpt, setSelFeasOpt] = useState<ById<BedSelection>>({});
  const feasAbortRef = useRef<AbortController | null>(null);
  const bedsAbortRef = useRef<AbortController | null>(null);

  const loadBedOptions = useCallback(async (req: StudentRequest) => {
    if (req.request_type !== 'add_student' || bedOptions[req.id]) return;
    if (bedsAbortRef.current) bedsAbortRef.current.abort();
    const controller = new AbortController();
    bedsAbortRef.current = controller;
    setLoadingBeds(req.id);
    try {
      const d = await requestsAPI.getAddStudentBeds(req.id, { signal: controller.signal });
      setBedOptions((p) => ({ ...p, [req.id]: d }));
    } catch (err) {
      if (isRequestCancelled(err)) return;
      setBedsError((p) => ({ ...p, [req.id]: errorMessage(err, '') }));
    } finally {
      if (bedsAbortRef.current === controller) setLoadingBeds(null);
    }
  }, [bedOptions]);

  const loadMoreBedOptions = useCallback(async (id: number) => {
    const current = bedOptions[id];
    if (!current || loadingMoreBedsId) return;
    setLoadingMoreBedsId(id);
    setLoadMoreBedsErr((p) => ({ ...p, [id]: '' }));
    try {
      // Pagination unit is the BUILDING: the next page starts after the
      // buildings already loaded, and is APPENDED - never replaces them.
      const d = await requestsAPI.getAddStudentBeds(id, { offset: (current.buildings || []).length });
      setBedOptions((p) => ({ ...p, [id]: { ...d, buildings: mergeBuildings(p[id]?.buildings, d.buildings) } }));
    } catch (err) {
      setLoadMoreBedsErr((p) => ({ ...p, [id]: errorMessage(err, t.errGeneric) }));
    } finally {
      setLoadingMoreBedsId(null);
    }
  }, [bedOptions, loadingMoreBedsId, t]);

  const checkFeasibility = useCallback(async (id: number) => {
    if (feasAbortRef.current) feasAbortRef.current.abort();
    const controller = new AbortController();
    feasAbortRef.current = controller;
    setCheckingFeas(id);
    // Clear any stale results for this request immediately - "שוב" (recheck)
    // must never leave a previous filter's results mixed with the new ones.
    setFeasData((p) => ({ ...p, [id]: null }));
    try {
      const d = await requestsAPI.checkFeasibility(id, { signal: controller.signal });
      setFeasData((p) => ({ ...p, [id]: d }));
    } catch (err) {
      if (isRequestCancelled(err)) return;
      setFeasData((p) => ({ ...p, [id]: failedFeasibility(err, 'options') }));
    } finally {
      if (feasAbortRef.current === controller) setCheckingFeas(null);
    }
  }, []);

  const loadMoreFeasibility = useCallback(async (id: number) => {
    const current = feasData[id];
    if (!current || loadingMoreFeasId) return;
    setLoadingMoreFeasId(id);
    setLoadMoreFeasErr((p) => ({ ...p, [id]: '' }));
    try {
      const d = await requestsAPI.checkFeasibility(id, { offset: (current.buildings || []).length });
      setFeasData((p) => ({ ...p, [id]: { ...d, buildings: mergeBuildings(p[id]?.buildings, d.buildings) } }));
    } catch (err) {
      setLoadMoreFeasErr((p) => ({ ...p, [id]: errorMessage(err, t.errGeneric) }));
    } finally {
      setLoadingMoreFeasId(null);
    }
  }, [feasData, loadingMoreFeasId, t]);

  const setRoomSelection = useCallback((id: number, selection: BedSelection) => {
    setSelRoom((p) => ({ ...p, [id]: selection }));
  }, []);

  const setFeasSelection = useCallback((id: number, selection: BedSelection) => {
    setSelFeasOpt((p) => ({ ...p, [id]: selection }));
  }, []);

  const forRequest = useCallback((id: number): RequestReviewView => ({
    feasData: feasData[id],
    checkingFeas: checkingFeas === id,
    loadingMoreFeas: loadingMoreFeasId === id,
    loadMoreFeasError: loadMoreFeasErr[id] || '',
    bedOptions: bedOptions[id],
    loadingBeds: loadingBeds === id,
    bedsError: bedsError[id],
    loadingMoreBeds: loadingMoreBedsId === id,
    loadMoreBedsError: loadMoreBedsErr[id] || '',
    roomSelection: selRoom[id],
    feasSelection: selFeasOpt[id],
  }), [
    feasData, checkingFeas, loadingMoreFeasId, loadMoreFeasErr,
    bedOptions, loadingBeds, bedsError, loadingMoreBedsId, loadMoreBedsErr,
    selRoom, selFeasOpt,
  ]);

  return {
    forRequest,
    loadBedOptions, loadMoreBedOptions,
    checkFeasibility, loadMoreFeasibility,
    setRoomSelection, setFeasSelection,
  };
}
