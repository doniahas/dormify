import React from 'react';
import type { AllocationRunStrings } from '../AllocationPage.strings';
import type { ConfirmModalState } from '../model';
import styles from './AllocationOverlays.module.css';

export interface ConfirmDialogProps {
  modal: ConfirmModalState | null;
  t: AllocationRunStrings;
  onClose: () => void;
}

/** The cancel / stop-and-save / delete confirmation. */
export function ConfirmDialog({ modal, t, onClose }: ConfirmDialogProps): React.ReactElement | null {
  if (!modal) return null;
  return (
    <div className={styles.apModalOverlay} role="dialog" aria-modal="true">
      <div className={styles.apModalBox}>
        <h3 className={styles.apModalTitle}>{modal.title}</h3>
        <p className={styles.apModalBody}>{modal.message}</p>
        <div className={styles.apModalActions}>
          <button type="button" className={styles.apModalCancel} onClick={onClose}>{t.cancel}</button>
          <button type="button" className={styles.apModalConfirm} onClick={modal.onConfirm}>{t.confirm}</button>
        </div>
      </div>
    </div>
  );
}
