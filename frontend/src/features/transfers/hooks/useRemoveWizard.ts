import { useCallback, useState } from 'react';
import type { WizardStudent } from '../model';
import { canAdvanceRemove } from '../transferHelpers';

export interface RemoveWizardState {
  step: number;
  student: WizardStudent | null;
  setStudent: (student: WizardStudent | null) => void;
  reason: string;
  setReason: (reason: string) => void;
  canNext: boolean;
  next: () => void;
  back: () => void;
}

/** The Remove Student wizard: pick an assigned student, see the placement, give a reason, confirm. */
export function useRemoveWizard(): RemoveWizardState {
  const [step, setStep] = useState(0);
  const [student, setStudent] = useState<WizardStudent | null>(null);
  const [reason, setReason] = useState('');

  const next = useCallback(() => setStep((s) => s + 1), []);
  const back = useCallback(() => setStep((s) => s - 1), []);

  return {
    step, student, setStudent, reason, setReason,
    canNext: canAdvanceRemove(step, student, reason),
    next, back,
  };
}
