import { useCallback, useState } from 'react';
import type { Apartment, Building, Room } from '../../../shared/api/contracts';
import { whatIfAPI } from '../../what-if/api';
import type { BuildingsStrings } from '../BuildingsPage.strings';
import { availabilityReasonText, entityLabel, errorMessage } from '../inventoryHelpers';
import type { AvailabilityAction, AvailabilityDialogState, AvailabilityImpact, AvailabilityTargetType } from '../model';

export interface AvailabilityDialogOptions {
  t: BuildingsStrings;
  refreshCurrentScope: () => Promise<void>;
}

export interface AvailabilityDialogController {
  dialog: AvailabilityDialogState | null;
  /** Opens the dialog; a deactivation first simulates its impact through the what-if API. */
  open: (targetType: AvailabilityTargetType, target: Building | Apartment | Room, action: AvailabilityAction) => Promise<void>;
  close: () => void;
  setReason: (reason: string) => void;
  setNote: (note: string) => void;
  /** Confirms the change (a deactivation needs a reason) and refreshes the scope. */
  confirm: () => Promise<void>;
}

/** The activate / deactivate dialog for a building, apartment or room. */
export function useAvailabilityDialog({ t, refreshCurrentScope }: AvailabilityDialogOptions): AvailabilityDialogController {
  const [dialog, setDialog] = useState<AvailabilityDialogState | null>(null);

  const open = useCallback(async (
    targetType: AvailabilityTargetType,
    target: Building | Apartment | Room,
    action: AvailabilityAction
  ) => {
    setDialog({
      targetType,
      targetId: target.id,
      label: entityLabel(targetType, target, t),
      action,
      impact: null,
      loadingImpact: action === 'inactivate',
      reason: '',
      note: '',
      saving: false,
      error: '',
    });

    if (action !== 'inactivate') return;

    try {
      const data = await whatIfAPI.simulateAvailabilityChange({ targetType, targetIds: [target.id], action });
      const impact = data.summary as AvailabilityImpact | undefined;
      setDialog((prev) => (prev ? { ...prev, impact, loadingImpact: false } : prev));
    } catch (err) {
      setDialog((prev) => (prev ? { ...prev, loadingImpact: false, error: errorMessage(err, t.actionError) } : prev));
    }
  }, [t]);

  const close = useCallback(() => setDialog(null), []);

  const setReason = useCallback((reason: string) => {
    setDialog((prev) => (prev ? { ...prev, reason, error: '' } : prev));
  }, []);

  const setNote = useCallback((note: string) => {
    setDialog((prev) => (prev ? { ...prev, note } : prev));
  }, []);

  const confirm = useCallback(async () => {
    if (!dialog) return;

    if (dialog.action === 'inactivate' && !dialog.reason) {
      setDialog((prev) => (prev ? { ...prev, error: t.reasonRequired } : prev));
      return;
    }

    setDialog((prev) => (prev ? { ...prev, saving: true, error: '' } : prev));
    try {
      await whatIfAPI.confirmAvailabilityChange({
        targetType: dialog.targetType,
        targetIds: [dialog.targetId],
        action: dialog.action,
        reason: availabilityReasonText(dialog, t),
      });
      setDialog(null);
      await refreshCurrentScope();
    } catch (err) {
      setDialog((prev) => (prev ? { ...prev, saving: false, error: errorMessage(err, t.actionError) } : prev));
    }
  }, [dialog, t, refreshCurrentScope]);

  return { dialog, open, close, setReason, setNote, confirm };
}
