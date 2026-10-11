import React from 'react';
import type { TransfersStrings } from '../TransfersPage.strings';
import styles from '../TransfersPage.module.css';

export interface EmptyDetailStateProps {
  t: TransfersStrings;
  /** No requests loaded at all (vs. none selected yet). */
  noRequests: boolean;
}

/** The detail pane before a request is selected (Linear style). */
export function EmptyDetailState({ t, noRequests }: EmptyDetailStateProps): React.ReactElement {
  return (
    <div className={styles.emptyDetailState}>
      <div className={styles.edsInner}>

        <div className={styles.edsIcon}>
          <svg width="48" height="48" viewBox="0 0 48 48" fill="none">
            <rect width="48" height="48" rx="14" fill="var(--blue-bg)" />
            <rect x="12" y="14" width="24" height="3" rx="1.5" fill="var(--blue)" />
            <rect x="12" y="21" width="18" height="3" rx="1.5" fill="var(--blue-bdr)" />
            <rect x="12" y="28" width="20" height="3" rx="1.5" fill="var(--blue-bdr)" />
            <circle cx="36" cy="34" r="7" fill="var(--blue)" opacity=".12" />
            <path
              d="M33.5 34h5M36 31.5v5"
              stroke="var(--blue)"
              strokeWidth="1.8"
              strokeLinecap="round"
            />
          </svg>
        </div>

        {noRequests ? (
          <>
            <h3 className={styles.edsTitle}>{t.emptyDetailNoneTitle}</h3>
            <p className={styles.edsSub}>
              {t.emptyDetailNoneSub}
            </p>
          </>
        ) : (
          <>
            <h3 className={styles.edsTitle}>{t.emptyDetailPickTitle}</h3>
            <p className={styles.edsSub}>
              {t.emptyDetailPickSub}
            </p>
          </>
        )}

      </div>
    </div>
  );
}
