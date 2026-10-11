import { useCallback, useState } from 'react';
import type { Bed, Id } from '../../../shared/api/contracts';
import type { BuildingsStrings } from '../BuildingsPage.strings';
import { deleteBedViaApi, errorMessage } from '../inventoryHelpers';
import type { DeleteBedDialogState } from '../model';

export interface BedDeleteDialogOptions {
  t: BuildingsStrings;
  /** Deleting is only wired when the adapter actually offers deleteBed. */
  canDeleteBed: boolean;
  selectedRoomId: Id;
  fetchBeds: (roomId: Id) => Promise<void>;
}

export interface BedDeleteDialogController {
  dialog: DeleteBedDialogState | null;
  open: (bed: Bed) => void;
  close: () => void;
  /** Deletes the bed (never an occupied one) and re-reads the room's beds. */
  confirm: () => Promise<void>;
}

/** The bed deletion dialog (only ever opened when canDeleteBed is true). */
export function useBedDeleteDialog({ t, canDeleteBed, selectedRoomId, fetchBeds }: BedDeleteDialogOptions): BedDeleteDialogController {
  const [dialog, setDialog] = useState<DeleteBedDialogState | null>(null);

  const open = useCallback((bed: Bed) => {
    setDialog({ id: bed.id, label: bed.label, occupied: bed.is_occupied, saving: false, error: '' });
  }, []);

  const close = useCallback(() => setDialog(null), []);

  const confirm = useCallback(async () => {
    if (!dialog || dialog.occupied || !canDeleteBed) return;
    setDialog((prev) => (prev ? { ...prev, saving: true, error: '' } : prev));
    try {
      await deleteBedViaApi(dialog.id);
      setDialog(null);
      if (selectedRoomId) await fetchBeds(selectedRoomId);
    } catch (err) {
      setDialog((prev) => (prev ? { ...prev, saving: false, error: errorMessage(err, t.actionError) } : prev));
    }
  }, [dialog, canDeleteBed, selectedRoomId, fetchBeds, t.actionError]);

  return { dialog, open, close, confirm };
}
