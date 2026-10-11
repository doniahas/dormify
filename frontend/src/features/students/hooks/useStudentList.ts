import { useCallback, useEffect, useRef, useState } from 'react';
import type { StudentSummary } from '../../../shared/api/contracts';
import { isRequestCancelled, studentsAPI } from '../api';
import type { StudentFilters, StudentTab } from '../model';
import { buildStudentListParams, errorMessage } from '../studentHelpers';

export interface StudentListInput {
  activeTab: StudentTab;
  searchQuery: string;
  filters: StudentFilters;
}

export interface StudentListState {
  list: StudentSummary[];
  /** The server-side total of the current search, not the rows loaded so far. */
  listTotal: number;
  loading: boolean;
  error: string;
  /** True while a further page is available. */
  hasMore: boolean;
  loadingMore: boolean;
  loadMore: () => Promise<void>;
  /** Re-issues the current search from the first page. */
  reload: () => Promise<void>;
}

const DEBOUNCE_MS = 300;

/**
 * The paginated student list for the current tab/search/filters. Requests
 * are debounced by 300 ms and the in-flight one is cancelled when a newer
 * one starts, so a slow earlier response can never overwrite fresher
 * results. "Load more" appends the next page rather than re-fetching.
 */
export function useStudentList({ activeTab, searchQuery, filters }: StudentListInput): StudentListState {
  const [list, setList] = useState<StudentSummary[]>([]);
  const [listTotal, setListTotal] = useState(0);
  const [listNextUrl, setListNextUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState('');
  const listAbortRef = useRef<AbortController | null>(null);

  // The latest inputs, read by reload() so callers that refresh after a
  // write (create/update) never need to pass them again.
  const inputRef = useRef<StudentListInput>({ activeTab, searchQuery, filters });
  inputRef.current = { activeTab, searchQuery, filters };

  const reload = useCallback(async () => {
    if (listAbortRef.current) listAbortRef.current.abort();
    const controller = new AbortController();
    listAbortRef.current = controller;
    try {
      setLoading(true);
      setError('');
      const current = inputRef.current;
      const params = buildStudentListParams(current.activeTab, current.searchQuery, current.filters);
      const data = await studentsAPI.getStudents(params, { signal: controller.signal });
      // A superseded request normally rejects on abort; a reply that still
      // arrives after a newer request started is ignored rather than shown.
      if (listAbortRef.current !== controller) return;
      const items = Array.isArray(data) ? data : (data.results || []);
      setList(items);
      // Paginated response shape: {count, next, previous, results}. A plain
      // array has no server-side total beyond what was returned.
      setListTotal(Array.isArray(data) ? items.length : (data.count ?? items.length));
      setListNextUrl(Array.isArray(data) ? null : (data.next || null));
    } catch (err) {
      if (isRequestCancelled(err)) return;
      setError(errorMessage(err, 'Failed to load students'));
      setList([]);
      setListTotal(0);
      setListNextUrl(null);
    } finally {
      if (listAbortRef.current === controller) setLoading(false);
    }
  }, []);

  useEffect(() => {
    const timer = setTimeout(() => { void reload(); }, DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [activeTab, searchQuery, filters, reload]);

  const loadMore = useCallback(async () => {
    if (!listNextUrl || loadingMore) return;
    try {
      setLoadingMore(true);
      const data = await studentsAPI.getNextPage(listNextUrl);
      setList((prev) => [...prev, ...(data.results || [])]);
      setListNextUrl(data.next || null);
    } catch (err) {
      console.error('Failed to load more students:', err);
    } finally {
      setLoadingMore(false);
    }
  }, [listNextUrl, loadingMore]);

  return {
    list, listTotal, loading, error,
    hasMore: listNextUrl !== null,
    loadingMore, loadMore, reload,
  };
}
