import React from 'react';
import { AlertTriangle } from 'lucide-react';
import type { BuildingsStrings } from '../BuildingsPage.strings';
import type { AvailabilityDialogState } from '../model';
import styles from './InventoryDialogs.module.css';
import { FormField, PageAlert, Spinner } from './InventoryPrimitives';

export interface AvailabilityDialogProps {
  t: BuildingsStrings;
  dialog: AvailabilityDialogState;
  onClose: () => void;
  onReasonChange: (reason: string) => void;
  onNoteChange: (note: string) => void;
  onConfirm: () => void;
}

/** Activate / deactivate confirmation, with the simulated impact and the reason for a deactivation. */
export function AvailabilityDialog({
  t, dialog, onClose, onReasonChange, onNoteChange, onConfirm,
}: AvailabilityDialogProps): React.ReactElement {
  return (
    <div className={styles.overlay} onClick={() => (!dialog.saving ? onClose() : null)}>
      <div className={styles.dialog} onClick={(e) => e.stopPropagation()}>
        <h3>{dialog.action === 'inactivate' ? t.deactivateTitle(dialog.label) : t.activateTitle(dialog.label)}</h3>

        {dialog.action === 'inactivate' ? (
          <>
            <div className={styles.impactBox}>
              <div className={styles.impactTitle}>
                <AlertTriangle size={14} /> {t.impactTitle}
              </div>
              {dialog.loadingImpact ? (
                <div className={styles.centerInline}>
                  <Spinner size={16} /> {t.loadingImpact}
                </div>
              ) : dialog.impact ? (
                <>
                  <div className={styles.impactGrid}>
                    <div>
                      <span>{t.impactApartments}</span>
                      <strong>{dialog.impact.lost_apartments}</strong>
                    </div>
                    <div>
                      <span>{t.impactRooms}</span>
                      <strong>{dialog.impact.lost_rooms}</strong>
                    </div>
                    <div>
                      <span>{t.impactBeds}</span>
                      <strong>{dialog.impact.lost_beds}</strong>
                    </div>
                    <div>
                      <span>{t.impactAssignments}</span>
                      <strong>{dialog.impact.affected_students_count}</strong>
                    </div>
                  </div>
                  <p className={styles.impactNote}>
                    {(dialog.impact.affected_students_count ?? 0) > 0 ? t.impactNote : t.impactNoAssignments}
                  </p>
                </>
              ) : null}
            </div>

            <FormField label={t.reasonLabel} htmlFor="inv-avail-reason">
              <select
                id="inv-avail-reason"
                value={dialog.reason}
                onChange={(e) => onReasonChange(e.target.value)}
              >
                <option value="">{t.chooseReason}</option>
                {t.deactivationReasons.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>
            </FormField>
            <FormField label={t.noteLabel} htmlFor="inv-avail-note">
              <textarea
                id="inv-avail-note"
                rows={2}
                value={dialog.note}
                onChange={(e) => onNoteChange(e.target.value)}
              />
            </FormField>
          </>
        ) : (
          <p>{t.confirmActivateShort}</p>
        )}

        {dialog.error && <PageAlert>{dialog.error}</PageAlert>}

        <div className={styles.drawerFooter}>
          <button type="button" className="inv-secondaryBtn" onClick={onClose} disabled={dialog.saving}>
            {t.cancel}
          </button>
          <button
            type="button"
            className={dialog.action === 'inactivate' ? 'inv-dangerBtn' : 'inv-successBtn'}
            onClick={onConfirm}
            disabled={dialog.saving || dialog.loadingImpact}
          >
            {dialog.saving ? <Spinner size={14} /> : t.confirmProceed}
          </button>
        </div>
      </div>
    </div>
  );
}
