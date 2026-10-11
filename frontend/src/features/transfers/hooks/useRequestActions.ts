import { useCallback, useState } from 'react';
import type { Id } from '../../../shared/api/contracts';
import { requestsAPI } from '../api';
import { buildApprovePayload, errorMessage } from '../transferHelpers';
import type { TransfersStrings } from '../TransfersPage.strings';
import type { StudentRequest } from '../types';

export interface RequestActionsOptions {
  t: TransfersStrings;
  /** Re-reads the list after a decision (the backend's answer, not a local edit). */
  reload: () => Promise<void>;
  /** The backend deleted the request; it is dropped from the list locally. */
  onDeleted: (id: Id) => void;
}

export interface RequestActionsState {
  /** The id of the request whose approve/reject is in flight. */
  actionId: number | null;
  deletingId: number | null;
  approve: (id: number, roomId?: Id | null, bedId?: Id | null) => Promise<void>;
  reject: (id: number, reason: string) => Promise<void>;
  /** Asks for confirmation, then deletes the request (pending/rejected/cancelled only). */
  remove: (request: StudentRequest) => Promise<void>;
}

/** The reviewer's decisions on a request: approve (with the chosen target), reject, delete. */
export function useRequestActions({ t, reload, onDeleted }: RequestActionsOptions): RequestActionsState {
  const [actionId, setActionId] = useState<number | null>(null);
  const [deletingId, setDeletingId] = useState<number | null>(null);

  const approve = useCallback(async (id: number, roomId?: Id | null, bedId?: Id | null) => {
    setActionId(id);
    try {
      await requestsAPI.approve(id, buildApprovePayload(roomId, bedId));
      await reload();
    } catch (err) {
      window.alert(errorMessage(err, t.errGeneric));
    } finally {
      setActionId(null);
    }
  }, [reload, t]);

  const reject = useCallback(async (id: number, reason: string) => {
    setActionId(id);
    try {
      await requestsAPI.reject(id, reason);
      await reload();
    } catch (err) {
      window.alert(errorMessage(err, t.errGeneric));
    } finally {
      setActionId(null);
    }
  }, [reload, t]);

  const remove = useCallback(async (request: StudentRequest) => {
    if (!request?.id) return;
    const confirmed = window.confirm(t.deleteRequestConfirmText(request.student_name || t.dash));
    if (!confirmed) return;
    setDeletingId(request.id);
    try {
      await requestsAPI.delete(request.id);
      onDeleted(request.id);
    } catch (err) {
      window.alert(errorMessage(err, t.deleteRequestError));
    } finally {
      setDeletingId(null);
    }
  }, [t, onDeleted]);

  return { actionId, deletingId, approve, reject, remove };
}
