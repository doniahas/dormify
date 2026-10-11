import { useCallback, useState } from 'react';
import type { FieldErrors } from '../../../shared/api/contracts';
import type { StudentFormField, StudentFormValues } from '../model';
import { EMPTY_STUDENT_FORM } from '../studentHelpers';

export interface StudentFormState {
  form: StudentFormValues;
  fieldErrors: FieldErrors;
  error: string;
  success: string;
  loading: boolean;
  /** Edits one field; changing the region invalidates the dorm type picked under the old one. */
  setField: (field: StudentFormField, value: string) => void;
  reset: (values?: StudentFormValues) => void;
  clearMessages: () => void;
  setError: (message: string) => void;
  setSuccess: (message: string) => void;
  setFieldErrors: (errors: FieldErrors) => void;
  setLoading: (loading: boolean) => void;
}

/**
 * The state the Add Student and Edit Student modals share: the field values,
 * the backend's field-keyed errors, the banner messages and the busy flag.
 */
export function useStudentForm(initial: StudentFormValues = EMPTY_STUDENT_FORM): StudentFormState {
  const [form, setForm] = useState<StudentFormValues>(initial);
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [loading, setLoading] = useState(false);

  const setField = useCallback((field: StudentFormField, value: string) => {
    setError('');
    setSuccess('');
    setFieldErrors((prev) => {
      if (!prev[field]) return prev;
      const next = { ...prev };
      delete next[field];
      return next;
    });
    setForm((prev) => {
      const next = { ...prev, [field]: value };
      // Changing the region invalidates whatever dorm type was picked from
      // the previous region's list.
      if (field === 'region') next.accepted_dorm_type = '';
      return next;
    });
  }, []);

  const reset = useCallback((values: StudentFormValues = EMPTY_STUDENT_FORM) => {
    setForm(values);
    setFieldErrors({});
  }, []);

  const clearMessages = useCallback(() => {
    setError('');
    setSuccess('');
  }, []);

  return {
    form, fieldErrors, error, success, loading,
    setField, reset, clearMessages,
    setError, setSuccess, setFieldErrors, setLoading,
  };
}

/** The field-keyed errors an ApiError carries, if any. */
export function fieldErrorsOf(err: unknown): FieldErrors | null {
  if (typeof err === 'object' && err !== null && 'fieldErrors' in err) {
    const errors = (err as { fieldErrors?: unknown }).fieldErrors;
    if (typeof errors === 'object' && errors !== null) return errors as FieldErrors;
  }
  return null;
}
