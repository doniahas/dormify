import React from 'react';
import { AlertTriangle, Loader, XCircle } from 'lucide-react';
import type { AllocationRunStrings } from '../AllocationPage.strings';
import styles from '../AllocationPage.module.css';

/** The whole-page loading state shown until the first summary reply. */
export function AllocationLoadingState({ t }: { t: AllocationRunStrings }): React.ReactElement {
  return (
    <div className={styles.apPage}>
      <div className={styles.apLoadingState}>
        <Loader size={36} className={styles.apSpin} />
        <span>{t.loading}</span>
      </div>
    </div>
  );
}

export interface AllocationErrorStateProps {
  t: AllocationRunStrings;
  error: string;
  onRetry: () => void;
}

/** The whole-page error state (no summary could be loaded). */
export function AllocationErrorState({ t, error, onRetry }: AllocationErrorStateProps): React.ReactElement {
  return (
    <div className={styles.apPage}>
      <div className={styles.apErrorState}>
        <XCircle size={36} />
        <p className={styles.apErrorTitle}>{t.error}</p>
        <p className={styles.apErrorMsg}>{error}</p>
        <button type="button" className={styles.apRetryBtn} onClick={onRetry}>{t.retry}</button>
      </div>
    </div>
  );
}

export interface InlineAlertProps {
  message: string;
  onDismiss: () => void;
}

/** The non-fatal error line under the controls (a summary is still shown). */
export function InlineAlert({ message, onDismiss }: InlineAlertProps): React.ReactElement {
  return (
    <div className={styles.apInlineAlert}>
      <AlertTriangle size={15} />
      <span>{message}</span>
      <button type="button" onClick={onDismiss}>×</button>
    </div>
  );
}
