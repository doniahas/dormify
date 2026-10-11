import { useCallback, useEffect, useState } from 'react';
import type { Id } from '../../../shared/api/contracts';
import { mergeBuildings } from '../../allocation/BedMatchPicker';
import { studentsAPI } from '../api';
import type { BedResultMeta, BedSelection, MatchBuilding, StudentDetailView } from '../model';
import type { StudentsStrings } from '../StudentsPage.strings';
import { bedMetaFromReply, EMPTY_BED_META, errorMessage } from '../studentHelpers';
import type { AvailableBedsOptions } from '../types';

export interface BedAssignmentOptions {
  t: StudentsStrings;
  /** The placement succeeded and the modal has closed; the student and the totals should be re-read. */
  onAssigned: (studentId: Id) => void;
}

export interface BedAssignmentState {
  isOpen: boolean;
  /** The student being placed (or moved, when already assigned). */
  student: StudentDetailView | null;
  /** The loaded buildings; each carries its complete apartment/room/bed subtree. */
  buildings: MatchBuilding[];
  meta: BedResultMeta;
  loading: boolean;
  loadingMore: boolean;
  loadMoreError: string;
  assigning: boolean;
  error: string;
  success: string;
  /**
   * Set when match-options returns a single student-level blocking reason
   * (missing housing_type/region/etc.) instead of per-room results.
   */
  blockingField: string | null;
  /** Central-admin-only region override; null means the student's own home region. */
  regionOverride: Id | null;
  selection: BedSelection | null;
  select: (bed: BedSelection | null) => void;
  open: (student: StudentDetailView) => Promise<void>;
  close: () => void;
  retry: () => Promise<void>;
  changeRegion: (regionId: string) => void;
  loadMore: () => Promise<void>;
  submit: () => Promise<void>;
}

const CLOSE_AFTER_ASSIGN_MS = 1500;

/**
 * The Assign / Reassign Bed modal. Buildings are the pagination unit: every
 * loaded building carries its complete apartment/room/bed subtree, and
 * "load more" appends the next buildings rather than replacing them.
 */
export function useBedAssignment({ t, onAssigned }: BedAssignmentOptions): BedAssignmentState {
  const [isOpen, setIsOpen] = useState(false);
  const [student, setStudent] = useState<StudentDetailView | null>(null);
  const [buildings, setBuildings] = useState<MatchBuilding[]>([]);
  const [meta, setMeta] = useState<BedResultMeta>(EMPTY_BED_META);
  const [loadMoreError, setLoadMoreError] = useState('');
  const [loading, setLoading] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [assigning, setAssigning] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [blockingField, setBlockingField] = useState<string | null>(null);
  const [regionOverride, setRegionOverride] = useState<Id | null>(null);
  const [selection, setSelection] = useState<BedSelection | null>(null);

  // One result handler for the initial load, retry and the region selector,
  // so the three paths never drift apart.
  const fetchBeds = useCallback(async (studentId: Id, opts: AvailableBedsOptions) => {
    try {
      setLoading(true);
      const data = await studentsAPI.getAvailableBeds(studentId, opts);
      setBuildings((data.buildings || []) as MatchBuilding[]);
      setLoadMoreError('');
      setMeta(bedMetaFromReply(data));
      setBlockingField(data.blocking_field || null);
      if (data.blocking_field) setError(data.reason || '');
    } catch (err) {
      setError(errorMessage(err, 'Failed to load beds'));
    } finally {
      setLoading(false);
    }
  }, []);

  const open = useCallback(async (target: StudentDetailView) => {
    setStudent(target);
    setIsOpen(true);
    setSelection(null);
    setRegionOverride(null); // reset to the student's own home region on every open
    setError('');
    setSuccess('');
    setBlockingField(null);
    await fetchBeds(target.id, { offset: 0 });
  }, [fetchBeds]);

  // Re-runs the search from scratch (offset 0) for a given region.
  const loadBedsForRegion = useCallback(async (regionId: Id | null) => {
    if (!student) return;
    setSelection(null);
    setError('');
    setBlockingField(null);
    await fetchBeds(student.id, { offset: 0, regionId: regionId || undefined });
  }, [student, fetchBeds]);

  const retry = useCallback(() => loadBedsForRegion(regionOverride), [loadBedsForRegion, regionOverride]);

  const changeRegion = useCallback((regionId: string) => {
    setRegionOverride(regionId || null);
    void loadBedsForRegion(regionId || null);
  }, [loadBedsForRegion]);

  const loadMore = useCallback(async () => {
    if (!student || loadingMore) return;
    try {
      setLoadingMore(true);
      setLoadMoreError('');
      // offset = BUILDINGS already loaded, exactly as the backend expects
      // for the next page - appended, never replacing what's already shown.
      const data = await studentsAPI.getAvailableBeds(student.id, {
        offset: buildings.length, regionId: regionOverride || undefined,
      });
      setBuildings((prev) => mergeBuildings(prev, (data.buildings || []) as MatchBuilding[]));
      setMeta((prev) => ({ ...prev, has_more: !!data.has_more }));
    } catch (err) {
      setLoadMoreError(errorMessage(err, 'Failed to load more buildings'));
    } finally {
      setLoadingMore(false);
    }
  }, [student, loadingMore, buildings.length, regionOverride]);

  const close = useCallback(() => {
    setIsOpen(false);
    setSelection(null);
    setBuildings([]);
    setLoadMoreError('');
    setMeta(EMPTY_BED_META);
    setStudent(null);
    setRegionOverride(null);
    setError('');
    setSuccess('');
    setBlockingField(null);
    setLoadingMore(false);
  }, []);

  // Esc closes the modal (accessibility).
  useEffect(() => {
    if (!isOpen) return undefined;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') close();
    };
    document.addEventListener('keydown', onKeyDown);
    return () => document.removeEventListener('keydown', onKeyDown);
  }, [isOpen, close]);

  const submit = useCallback(async () => {
    if (!selection || !student) return;
    try {
      setAssigning(true);
      setError('');
      if (student.is_assigned) {
        await studentsAPI.reassignBed(student.id, selection.room_id, selection.bed_id);
      } else {
        await studentsAPI.assignBed(student.id, selection.room_id, selection.bed_id);
      }
      setSuccess(t.assignSuccess);
      const studentId = student.id;
      setTimeout(() => {
        close();
        onAssigned(studentId);
      }, CLOSE_AFTER_ASSIGN_MS);
    } catch (err) {
      setError(errorMessage(err, 'Failed to assign bed'));
    } finally {
      setAssigning(false);
    }
  }, [selection, student, t, close, onAssigned]);

  return {
    isOpen, student, buildings, meta,
    loading, loadingMore, loadMoreError, assigning,
    error, success, blockingField, regionOverride,
    selection, select: setSelection,
    open, close, retry, changeRegion, loadMore, submit,
  };
}
