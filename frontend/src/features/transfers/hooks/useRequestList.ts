import { useCallback, useEffect, useRef, useState } from 'react';
import type { Id } from '../../../shared/api/contracts';
import { requestsAPI } from '../api';
import type { RegionFilter } from '../model';
import { buildRequestListParams, errorMessage } from '../transferHelpers';
import type { TransfersStrings } from '../TransfersPage.strings';
import type { StudentRequest } from '../types';

export interface RequestListOptions {
  t: TransfersStrings;
  isCentralAdmin: boolean;
  regionFilter: RegionFilter;
}

export interface RequestListState {
  requests: StudentRequest[];
  loading: boolean;
  pageError: string;
  /** The request the detail pane shows; refreshed from the list on every reload. */
  selected: StudentRequest | null;
  select: (request: StudentRequest | null) => void;
  /** Re-reads every status from the backend (the status tabs filter client-side). */
  reload: () => Promise<void>;
  /** Drops a request the backend has just deleted, closing its detail pane. */
  removeRequest: (id: Id) => void;
}

/**
 * The request list: always every status (the tabs and the type/search
 * filters narrow it client-side), scoped by the central admin's region
 * filter. The selected request is replaced by its fresh copy on reload, so
 * a decision shows its new status without re-selecting.
 */
export function useRequestList({ t, isCentralAdmin, regionFilter }: RequestListOptions): RequestListState {
  const [requests, setRequests] = useState<StudentRequest[]>([]);
  const [loading, setLoading] = useState(false);
  const [pageError, setPageError] = useState('');
  const [selected, setSelected] = useState<StudentRequest | null>(null);

  // The latest inputs, read by reload() so callers that refresh after a
  // decision never need to pass them again.
  const inputRef = useRef<RequestListOptions>({ t, isCentralAdmin, regionFilter });
  inputRef.current = { t, isCentralAdmin, regionFilter };
  const selectedRef = useRef<StudentRequest | null>(selected);
  selectedRef.current = selected;

  const reload = useCallback(async () => {
    setLoading(true);
    setPageError('');
    try {
      const current = inputRef.current;
      const d = await requestsAPI.getAll(buildRequestListParams(current.isCentralAdmin, current.regionFilter));
      const list = Array.isArray(d) ? d : (d.results || []);
      setRequests(list);
      const sel = selectedRef.current;
      if (sel) {
        const upd = list.find((r) => r.id === sel.id);
        if (upd) setSelected(upd);
      }
    } catch (err) {
      setPageError(errorMessage(err, inputRef.current.t.errLoad));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void reload();
  }, [regionFilter, reload]);

  const removeRequest = useCallback((id: Id) => {
    setRequests((prev) => prev.filter((r) => r.id !== id));
    setSelected((prev) => (prev?.id === id ? null : prev));
  }, []);

  return { requests, loading, pageError, selected, select: setSelected, reload, removeRequest };
}
