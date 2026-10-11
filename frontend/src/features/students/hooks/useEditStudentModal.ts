import { useCallback, useMemo, useState } from 'react';
import type { Student } from '../../../shared/api/contracts';
import { studentsAPI } from '../api';
import type { StudentDetailView } from '../model';
import type { StudentsStrings } from '../StudentsPage.strings';
import {
  buildStudentPayload,
  dormTypeOptionsForRegion,
  errorMessage,
  missingStudentFormFields,
  studentFormFromStudent,
} from '../studentHelpers';
import type { DormTypeFilterOption, StudentFilterOptions } from '../types';
import { fieldErrorsOf, useStudentForm, type StudentFormState } from './useStudentForm';

export interface EditStudentModalOptions {
  isCentralAdmin: boolean;
  filterOptions: StudentFilterOptions | null;
  t: StudentsStrings;
  /** The student was saved; the list and the totals should be re-read. */
  onUpdated: (updated: Student) => void;
  /**
   * The modal has closed itself after the success message. returnToAssign is
   * set when it was opened from the bed-assignment modal's blocking message,
   * so the caller re-opens the assign flow with the fixed record.
   */
  onAfterClose: (updated: Student, returnToAssign: boolean) => void;
}

export interface EditStudentModalState extends StudentFormState {
  isOpen: boolean;
  /** The student being edited (its id and student_id are read-only in the form). */
  target: StudentDetailView | null;
  open: (student: StudentDetailView, options?: { returnToAssign?: boolean }) => void;
  close: () => void;
  dormTypeOptions: DormTypeFilterOption[];
  submit: () => Promise<void>;
}

const CLOSE_AFTER_SAVE_MS = 700;

/**
 * The Edit Student modal. Opened either from the detail view, or from the
 * Assign Bed modal's "missing data" blocking message (returnToAssign=true
 * re-opens the assign flow after a successful save instead of just closing).
 */
export function useEditStudentModal({
  isCentralAdmin, filterOptions, t, onUpdated, onAfterClose,
}: EditStudentModalOptions): EditStudentModalState {
  const formState = useStudentForm();
  const { form, loading, reset, clearMessages, setError, setSuccess, setFieldErrors, setLoading } = formState;
  const [isOpen, setIsOpen] = useState(false);
  const [target, setTarget] = useState<StudentDetailView | null>(null);
  const [returnToAssign, setReturnToAssign] = useState(false);

  const open = useCallback((student: StudentDetailView, options: { returnToAssign?: boolean } = {}) => {
    setTarget(student);
    setReturnToAssign(Boolean(options.returnToAssign));
    clearMessages();
    reset(studentFormFromStudent(student));
    setIsOpen(true);
  }, [clearMessages, reset]);

  const close = useCallback(() => {
    if (loading) return;
    setIsOpen(false);
    setTarget(null);
    clearMessages();
    setFieldErrors({});
    setReturnToAssign(false);
  }, [loading, clearMessages, setFieldErrors]);

  const dormTypeOptions = useMemo(
    () => dormTypeOptionsForRegion(filterOptions?.dorm_types, isCentralAdmin, form.region),
    [filterOptions?.dorm_types, isCentralAdmin, form.region]
  );

  const submit = useCallback(async () => {
    if (!target) return;
    setError('');
    setFieldErrors({});
    setSuccess('');

    const missing = missingStudentFormFields(form, { requireStudentId: false, isCentralAdmin });
    if (missing.length > 0) {
      setError(t.fillRequiredFields);
      return;
    }

    const payload = buildStudentPayload(form, { includeStudentId: false });
    try {
      setLoading(true);
      const updated = await studentsAPI.update(target.id, payload);
      setSuccess(t.editStudentSuccess);
      onUpdated(updated);

      const shouldReturnToAssign = returnToAssign;
      setTimeout(() => {
        setIsOpen(false);
        setSuccess('');
        setTarget(null);
        setReturnToAssign(false);
        onAfterClose(updated, shouldReturnToAssign);
      }, CLOSE_AFTER_SAVE_MS);
    } catch (err) {
      const fieldErrors = fieldErrorsOf(err);
      if (fieldErrors) setFieldErrors(fieldErrors);
      setError(errorMessage(err, t.editStudentFailed));
    } finally {
      setLoading(false);
    }
  }, [target, form, isCentralAdmin, t, returnToAssign, onUpdated, onAfterClose, setError, setFieldErrors, setSuccess, setLoading]);

  return { ...formState, isOpen, target, open, close, dormTypeOptions, submit };
}
