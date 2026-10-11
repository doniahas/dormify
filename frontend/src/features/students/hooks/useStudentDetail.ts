import { useCallback, useState } from 'react';
import type { Id, StudentSummary } from '../../../shared/api/contracts';
import type { StudentRequest } from '../../transfers/types';
import { studentsAPI } from '../api';
import type { StudentDetailView } from '../model';

export interface StudentDetailState {
  /** The student whose detail view is open; null shows the list. */
  selectedStudent: StudentDetailView | null;
  loadingDetails: boolean;
  studentRequests: StudentRequest[];
  loadingStudentRequests: boolean;
  /** Opens the detail view on a list row and loads the full record behind it. */
  open: (student: StudentSummary) => Promise<void>;
  close: () => void;
  /** Replaces the shown student (after an edit or a placement). */
  show: (student: StudentDetailView) => void;
  /** Re-reads the student from the backend and shows the fresh record. */
  refresh: (studentId: Id) => Promise<void>;
  reloadRequests: (studentId: Id) => Promise<void>;
}

/** The detail view's student, its full record and the requests filed for it. */
export function useStudentDetail(): StudentDetailState {
  const [selectedStudent, setSelectedStudent] = useState<StudentDetailView | null>(null);
  const [loadingDetails, setLoadingDetails] = useState(false);
  const [studentRequests, setStudentRequests] = useState<StudentRequest[]>([]);
  const [loadingStudentRequests, setLoadingStudentRequests] = useState(false);

  const reloadRequests = useCallback(async (studentId: Id) => {
    try {
      setLoadingStudentRequests(true);
      const data = await studentsAPI.getRequests(studentId);
      setStudentRequests(data);
    } catch (err) {
      console.error('Failed to load student requests:', err);
      setStudentRequests([]);
    } finally {
      setLoadingStudentRequests(false);
    }
  }, []);

  const open = useCallback(async (student: StudentSummary) => {
    try {
      setLoadingDetails(true);
      setSelectedStudent(student);
      const full = await studentsAPI.getById(student.id);
      setSelectedStudent(full);
      void reloadRequests(full.id);
    } catch (err) {
      console.error('Failed to load full student details:', err);
    } finally {
      setLoadingDetails(false);
    }
  }, [reloadRequests]);

  const refresh = useCallback(async (studentId: Id) => {
    const full = await studentsAPI.getById(studentId);
    setSelectedStudent(full);
  }, []);

  const close = useCallback(() => setSelectedStudent(null), []);
  const show = useCallback((student: StudentDetailView) => setSelectedStudent(student), []);

  return {
    selectedStudent, loadingDetails,
    studentRequests, loadingStudentRequests,
    open, close, show, refresh, reloadRequests,
  };
}
