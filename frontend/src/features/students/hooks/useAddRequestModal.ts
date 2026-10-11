import { useCallback, useMemo, useState } from 'react';
import type { Id, Region } from '../../../shared/api/contracts';
import { regionsAPI } from '../../inventory/api';
import { requestsAPI } from '../../transfers/api';
import type {
  RequestDisabledReason,
  StudentDetailView,
  StudentRequestKind,
  StudentTransferScope,
} from '../model';
import type { StudentsStrings } from '../StudentsPage.strings';
import { buildRequestPayload, errorMessage, requestDisabledReason } from '../studentHelpers';

export interface AddRequestModalOptions {
  /** The student the request is filed for (the one the detail view shows). */
  student: StudentDetailView | null;
  isCentralAdmin: boolean;
  t: StudentsStrings;
  /** A request was created; the student's request list should be re-read. */
  onSubmitted: (studentId: Id) => void;
}

export interface AddRequestModalState {
  isOpen: boolean;
  open: () => void;
  close: () => void;
  reqType: StudentRequestKind;
  setReqType: (type: StudentRequestKind) => void;
  reqScope: StudentTransferScope | null;
  setReqScope: (scope: StudentTransferScope) => void;
  /** The chosen target region's raw PK (a slug string); null until chosen. */
  reqTargetRegion: Id | null;
  selectTargetRegion: (regionId: Id) => void;
  /** Regions a cross-region transfer may target (central admins only). */
  regions: Region[];
  reqOtherDesc: string;
  setReqOtherDesc: (value: string) => void;
  reqReason: string;
  setReqReason: (value: string) => void;
  submitting: boolean;
  error: string;
  success: string;
  disabledReason: RequestDisabledReason | null;
  canSubmit: boolean;
  submit: () => Promise<void>;
}

const CLOSE_AFTER_SUBMIT_MS = 1500;

/** The Add Request modal for an assigned student: transfer / other / removal. */
export function useAddRequestModal({
  student, isCentralAdmin, t, onSubmitted,
}: AddRequestModalOptions): AddRequestModalState {
  const [isOpen, setIsOpen] = useState(false);
  const [reqType, setReqType] = useState<StudentRequestKind>('transfer');
  // Unified transfer scope: same_apartment / same_region / cross_region -
  // maps onto the existing request fields (request_type / same_apartment /
  // transfer_scope / destination_regions), no new backend fields.
  const [reqScope, setReqScope] = useState<StudentTransferScope | null>(null);
  // Holds the selected target region's raw PK - the backend expects real
  // Region PKs in destination_regions.
  const [reqTargetRegion, setReqTargetRegion] = useState<Id | null>(null);
  const [regions, setRegions] = useState<Region[]>([]);
  const [reqOtherDesc, setReqOtherDesc] = useState('');
  const [reqReason, setReqReason] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  const open = useCallback(() => {
    setReqType(student?.is_assigned ? 'transfer' : 'other');
    setReqScope(null);
    setReqTargetRegion(null);
    setReqOtherDesc('');
    setReqReason('');
    setError('');
    setSuccess('');
    setIsOpen(true);
    // Real regions from the backend for the cross-region dropdown
    // (central admin only - regional users cannot pick another region).
    if (isCentralAdmin && regions.length === 0) {
      regionsAPI.getAll().then(setRegions).catch(() => setRegions([]));
    }
  }, [student?.is_assigned, isCentralAdmin, regions.length]);

  const close = useCallback(() => setIsOpen(false), []);

  const selectTargetRegion = useCallback((regionId: Id) => {
    setReqTargetRegion(regionId);
    setError('');
  }, []);

  const draft = useMemo(
    () => ({ reqType, reqScope, reqTargetRegion, reqOtherDesc, reqReason }),
    [reqType, reqScope, reqTargetRegion, reqOtherDesc, reqReason]
  );

  const disabledReason = requestDisabledReason(draft, {
    hasStudent: student !== null,
    submitting,
    submitted: Boolean(success),
  });
  const canSubmit = disabledReason === null;

  const submit = useCallback(async () => {
    if (!student || !reqReason.trim()) { setError(t.missingReason); return; }
    if (reqType === 'other' && !reqOtherDesc.trim()) { setError(t.missingOtherDesc); return; }
    if (reqType === 'transfer' && !reqScope) { setError(t.missingScope); return; }
    // Never rely on the backend's "Invalid pk" error: a cross-region
    // transfer must carry one real Region PK before submit.
    if (reqType === 'transfer' && reqScope === 'cross_region'
        && !(reqTargetRegion != null && String(reqTargetRegion).trim() !== '')) {
      setError(t.missingTargetRegion);
      return;
    }
    try {
      setSubmitting(true);
      setError('');
      await requestsAPI.create(buildRequestPayload(student.id, draft));
      setSuccess(t.requestSubmitted);
      onSubmitted(student.id);
      setTimeout(() => {
        setIsOpen(false);
        setSuccess('');
      }, CLOSE_AFTER_SUBMIT_MS);
    } catch (err) {
      setError(errorMessage(err, 'Failed to create request'));
    } finally {
      setSubmitting(false);
    }
  }, [student, reqType, reqScope, reqTargetRegion, reqOtherDesc, reqReason, draft, t, onSubmitted]);

  return {
    isOpen, open, close,
    reqType, setReqType,
    reqScope, setReqScope,
    reqTargetRegion, selectTargetRegion, regions,
    reqOtherDesc, setReqOtherDesc,
    reqReason, setReqReason,
    submitting, error, success,
    disabledReason, canSubmit, submit,
  };
}
