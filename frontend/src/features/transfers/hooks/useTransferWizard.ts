import { useCallback, useEffect, useRef, useState } from 'react';
import type { Id } from '../../../shared/api/contracts';
import { studentsAPI } from '../../students/api';
import type {
  BedSelection,
  NewTransferScope,
  TransferStepKey,
  TransferWizardType,
  WizardStudent,
} from '../model';
import {
  buildTransferPayload,
  canAdvanceTransfer,
  effectiveTransferFields,
  transferStepKeys,
  type EffectiveTransferFields,
  type TransferDraft,
} from '../transferHelpers';
import type { StudentRequestPayload } from '../types';

export interface TransferWizardOptions {
  type: TransferWizardType;
  /** The search definition changed: previously fetched options are stale. */
  onInvalidate: () => void;
}

export interface TransferWizardState extends TransferDraft {
  step: number;
  stepKeys: TransferStepKey[];
  stepKey: TransferStepKey;
  lastStep: number;
  isTransfer: boolean;
  /** Picks a student; the slim search row is completed with the full record (region_name). */
  pickStudent: (student: WizardStudent) => void;
  clearStudent: () => void;
  setScope: (scope: NewTransferScope) => void;
  setDestRegions: (ids: Id[]) => void;
  regionQuery: string;
  setRegionQuery: (query: string) => void;
  setReason: (reason: string) => void;
  setOtherDesc: (desc: string) => void;
  setSelOpt: (selection: BedSelection | null) => void;
  /** The backend fields the chosen scope maps onto. */
  effective: EffectiveTransferFields;
  canNext: boolean;
  next: () => void;
  back: () => void;
  buildPayload: (central: boolean) => StudentRequestPayload;
}

/**
 * The Transfer wizard (room / apartment / cross-region) and, with fewer
 * steps, the "other" request. The unified transfer scope - same_apartment /
 * same_region / cross_region - maps onto existing backend request fields.
 * Cross-region creation is central-admin only; the backend enforces this
 * independently of the UI (serializer PermissionDenied).
 */
export function useTransferWizard({ type, onInvalidate }: TransferWizardOptions): TransferWizardState {
  const [step, setStep] = useState(0);
  const [student, setStudent] = useState<WizardStudent | null>(null);
  const [reason, setReason] = useState('');
  const [otherDesc, setOtherDesc] = useState('');
  const [selOpt, setSelOpt] = useState<BedSelection | null>(null);
  const [scope, setScope] = useState<NewTransferScope | null>(null);
  const [destRegions, setDestRegions] = useState<Id[]>([]);
  const [regionQuery, setRegionQuery] = useState('');

  const isTransfer = type === 'transfer';
  const stepKeys = transferStepKeys(isTransfer);
  const stepKey = stepKeys[step];
  const lastStep = stepKeys.length - 1;

  // Any change to what defines the search invalidates previously fetched
  // options (and the previously selected bed) - never show stale results.
  // The callback is read through a ref so only the search definition
  // re-runs the effect, exactly as before.
  const invalidateRef = useRef(onInvalidate);
  invalidateRef.current = onInvalidate;
  useEffect(() => {
    if (!isTransfer) return;
    setSelOpt(null);
    invalidateRef.current();
  }, [isTransfer, scope, destRegions, student]);

  const pickStudent = useCallback((s: WizardStudent) => {
    setStudent(s);
    // The slim search payload has no region_name - fetch the full record so
    // the read-only target-region label can show the real current region
    // name on the scope step.
    if (!s.region_name) {
      studentsAPI.getById(s.id)
        .then((full) => setStudent((prev) => (prev && prev.id === s.id ? { ...prev, ...full } : prev)))
        .catch(() => {});
    }
  }, []);

  const clearStudent = useCallback(() => setStudent(null), []);
  const next = useCallback(() => setStep((s) => s + 1), []);
  const back = useCallback(() => setStep((s) => s - 1), []);

  const draft: TransferDraft = { student, scope, destRegions, reason, otherDesc, selOpt };

  const buildPayload = (central: boolean) => buildTransferPayload(type, draft, central);

  return {
    ...draft,
    step, stepKeys, stepKey, lastStep, isTransfer,
    pickStudent, clearStudent,
    setScope, setDestRegions, regionQuery, setRegionQuery,
    setReason, setOtherDesc, setSelOpt,
    effective: effectiveTransferFields(scope),
    canNext: canAdvanceTransfer(stepKey, draft),
    next, back, buildPayload,
  };
}
