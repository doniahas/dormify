import React from 'react';
import { Loader, X } from 'lucide-react';
import { cx } from '../../../../shared/lib/classNames';
import type { AllocationResultsStrings } from '../AllocationResultsPage.strings';
import styles from './UnassignedAnalysis.module.css';

export interface RetryConfirmModalProps {
  t: AllocationResultsStrings;
  unassignedCount: number;
  loading: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}

/** "Retry the N unassigned students against the current free inventory?" - yes / no. */
export function RetryConfirmModal({
  t, unassignedCount, loading, onCancel, onConfirm,
}: RetryConfirmModalProps): React.ReactElement {
  return (
    <div className={styles.retryConfirmOverlay} role="dialog" aria-modal="true">
      <div className={styles.retryConfirmModal}>
        <div className={styles.retryConfirmHeader}>
          <span>{t.retryUnassignedConfirmTitle}</span>
          <button
            type="button"
            className={styles.retryConfirmClose}
            onClick={onCancel}
            aria-label="close"
          >
            <X size={16} />
          </button>
        </div>
        <div className={styles.retryConfirmBody}>
          {t.retryUnassignedConfirmBody(unassignedCount)}
        </div>
        <div className={styles.retryConfirmActions}>
          <button
            type="button"
            className={cx(styles.retryConfirmBtn, styles.cancel)}
            onClick={onCancel}
            disabled={loading}
          >
            {t.no}
          </button>
          <button
            type="button"
            className={cx(styles.retryConfirmBtn, styles.confirm)}
            onClick={onConfirm}
            disabled={loading}
          >
            {loading ? <Loader size={14} className={styles.spin} /> : null}
            {t.yes}
          </button>
        </div>
      </div>
    </div>
  );
}
