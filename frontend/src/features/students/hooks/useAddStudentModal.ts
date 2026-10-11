import { useCallback, useMemo, useState } from 'react';
import type { Student } from '../../../shared/api/contracts';
import { studentsAPI } from '../api';
import type { AddStudentMode, StudentFormValues } from '../model';
import type { StudentsStrings } from '../StudentsPage.strings';
import {
  buildStudentPayload,
  dormTypeOptionsForRegion,
  errorMessage,
  missingStudentFormFields,
} from '../studentHelpers';
import type { DormTypeFilterOption, StudentFilterOptions } from '../types';
import { fieldErrorsOf, useStudentForm, type StudentFormState } from './useStudentForm';

export interface AddStudentModalOptions {
  isCentralAdmin: boolean;
  filterOptions: StudentFilterOptions | null;
  t: StudentsStrings;
  /** The student was created; the list and the totals should be re-read. */
  onCreated: (created: Student) => void;
  /** The modal has closed itself after the success message; "save_and_match" continues into bed matching. */
  onAfterClose: (created: Student, mode: AddStudentMode) => void;
}

export interface AddStudentModalState extends StudentFormState {
  isOpen: boolean;
  open: () => void;
  close: () => void;
  dormTypeOptions: DormTypeFilterOption[];
  submit: (mode: AddStudentMode) => Promise<void>;
}

// The success banner stays visible briefly before the modal closes itself.
const CLOSE_AFTER_SAVE_MS = 900;
const CLOSE_BEFORE_MATCH_MS = 500;

/** The Add Student modal: form state, validation, POST /api/students/ and the follow-up. */
export function useAddStudentModal({
  isCentralAdmin, filterOptions, t, onCreated, onAfterClose,
}: AddStudentModalOptions): AddStudentModalState {
  const formState = useStudentForm();
  const { form, loading, reset, clearMessages, setError, setSuccess, setFieldErrors, setLoading } = formState;
  const [isOpen, setIsOpen] = useState(false);

  const open = useCallback(() => {
    clearMessages();
    setIsOpen(true);
  }, [clearMessages]);

  const close = useCallback(() => {
    if (loading) return;
    setIsOpen(false);
    clearMessages();
    reset();
  }, [loading, clearMessages, reset]);

  const dormTypeOptions = useMemo(
    () => dormTypeOptionsForRegion(filterOptions?.dorm_types, isCentralAdmin, form.region),
    [filterOptions?.dorm_types, isCentralAdmin, form.region]
  );

  const submit = useCallback(async (mode: AddStudentMode) => {
    setError('');
    setFieldErrors({});
    setSuccess('');

    const missing = missingStudentFormFields(form, { requireStudentId: true, isCentralAdmin });
    if (missing.length > 0) {
      setError(t.fillRequiredFields);
      return;
    }

    const payload = buildStudentPayload(form, { includeStudentId: true });
    try {
      setLoading(true);
      const created = await studentsAPI.create(payload);
      setSuccess(t.addStudentSuccess);
      onCreated(created);

      const delay = mode === 'save_and_match' ? CLOSE_BEFORE_MATCH_MS : CLOSE_AFTER_SAVE_MS;
      setTimeout(() => {
        setIsOpen(false);
        setSuccess('');
        reset();
        onAfterClose(created, mode);
      }, delay);
    } catch (err) {
      const fieldErrors = fieldErrorsOf(err);
      if (fieldErrors) setFieldErrors(fieldErrors);
      setError(errorMessage(err, t.addStudentFailed));
    } finally {
      setLoading(false);
    }
  }, [form, isCentralAdmin, t, onCreated, onAfterClose, reset, setError, setFieldErrors, setSuccess, setLoading]);

  return { ...formState, isOpen, open, close, dormTypeOptions, submit };
}

export type { StudentFormValues };
