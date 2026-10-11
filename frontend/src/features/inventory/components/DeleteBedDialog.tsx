import React from 'react';
import type { BuildingsStrings } from '../BuildingsPage.strings';
import type { DeleteBedDialogState } from '../model';
import styles from './InventoryDialogs.module.css';
import { PageAlert, Spinner } from './InventoryPrimitives';

export interface DeleteBedDialogProps {
  t: BuildingsStrings;
  dialog: DeleteBedDialogState;
  onClose: () => void;
  onConfirm: () => void;
}

/** Bed deletion confirmation (only ever opened when the adapter offers deleteBed). */
export function DeleteBedDialog({ t, dialog, onClose, onConfirm }: DeleteBedDialogProps): React.ReactElement {
  return (
    <div className={styles.overlay} onClick={() => (!dialog.saving ? onClose() : null)}>
      <div className={styles.dialog} onClick={(e) => e.stopPropagation()}>
        <h3>{t.deleteBedTitle(dialog.label)}</h3>
        {dialog.occupied && (
          <PageAlert tone="warning">{t.deleteBedOccupiedWarning}</PageAlert>
        )}
        {dialog.error && <PageAlert>{dialog.error}</PageAlert>}
        <div className={styles.drawerFooter}>
          <button type="button" className="inv-secondaryBtn" onClick={onClose} disabled={dialog.saving}>
            {t.cancel}
          </button>
          <button type="button" className="inv-dangerBtn" onClick={onConfirm} disabled={dialog.saving || dialog.occupied}>
            {dialog.saving ? <Spinner size={14} /> : t.confirmDelete}
          </button>
        </div>
      </div>
    </div>
  );
}
