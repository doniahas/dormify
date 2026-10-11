import { useCallback, useState } from 'react';
import type { WizardStudent } from '../model';
import { canAdvanceSwap } from '../transferHelpers';

export interface SwapWizardState {
  step: number;
  studentA: WizardStudent | null;
  setStudentA: (student: WizardStudent | null) => void;
  studentB: WizardStudent | null;
  setStudentB: (student: WizardStudent | null) => void;
  reason: string;
  setReason: (reason: string) => void;
  canNext: boolean;
  next: () => void;
  back: () => void;
}

/** The Swap wizard: two assigned students swap their current beds/rooms. */
export function useSwapWizard(): SwapWizardState {
  const [step, setStep] = useState(0);
  const [studentA, setStudentA] = useState<WizardStudent | null>(null);
  const [studentB, setStudentB] = useState<WizardStudent | null>(null);
  const [reason, setReason] = useState('');

  const next = useCallback(() => setStep((s) => s + 1), []);
  const back = useCallback(() => setStep((s) => s - 1), []);

  return {
    step, studentA, setStudentA, studentB, setStudentB, reason, setReason,
    canNext: canAdvanceSwap(step, studentA, studentB, reason),
    next, back,
  };
}
