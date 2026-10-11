import { useCallback, useState } from 'react';
import type { AddStudentField, AddStudentForm } from '../model';
import { canAdvanceAddStudent, EMPTY_ADD_STUDENT_FORM } from '../transferHelpers';

export interface AddStudentWizardState {
  step: number;
  form: AddStudentForm;
  setField: (field: AddStudentField, value: string) => void;
  canNext: boolean;
  next: () => void;
  back: () => void;
}

/** The Add Student wizard's step and form state (details, preferences, reason, summary). */
export function useAddStudentWizard(): AddStudentWizardState {
  const [step, setStep] = useState(0);
  const [form, setForm] = useState<AddStudentForm>(EMPTY_ADD_STUDENT_FORM);

  const setField = useCallback((field: AddStudentField, value: string) => {
    setForm((p) => ({ ...p, [field]: value }));
  }, []);

  const next = useCallback(() => setStep((s) => s + 1), []);
  const back = useCallback(() => setStep((s) => s - 1), []);

  return { step, form, setField, canNext: canAdvanceAddStudent(step, form), next, back };
}
