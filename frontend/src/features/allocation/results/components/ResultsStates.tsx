import React, { type ReactNode } from 'react';
import { AlertTriangle, Info, RefreshCw } from 'lucide-react';
import { cx } from '../../../../shared/lib/classNames';
import type { AllocationResultsStrings } from '../AllocationResultsPage.strings';
import styles from '../AllocationResultsPage.module.css';

export interface EmptyStateProps {
  text: string;
  children?: ReactNode;
}

/** The dashed info box every view shows when it has nothing to list. */
export function EmptyState({ text, children }: EmptyStateProps): React.ReactElement {
  return (
    <div className={styles.emptyState}>
      <Info size={18} />
      <span>{text}</span>
      {children}
    </div>
  );
}

/** Shown while the saved results are being read. */
export function ResultsLoadingState({ t }: { t: AllocationResultsStrings }): React.ReactElement {
  return <EmptyState text={t.loadingResults} />;
}

export interface ResultsErrorStateProps {
  t: AllocationResultsStrings;
  error: string;
  onRetry: () => void;
}

/** A failed load, with the retry that re-issues it. */
export function ResultsErrorState({ t, error, onRetry }: ResultsErrorStateProps): React.ReactElement {
  return (
    <div className={cx(styles.emptyState, styles.error)}>
      <AlertTriangle size={18} />
      <span>{error}</span>
      <button
        type="button"
        className={styles.retryLoadBtn}
        onClick={onRetry}
      >
        <RefreshCw size={14} />
        {t.retryLoadResults}
      </button>
    </div>
  );
}
