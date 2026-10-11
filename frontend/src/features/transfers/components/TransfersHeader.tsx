import React from 'react';
import { Plus, RefreshCw } from 'lucide-react';
import { cx } from '../../../shared/lib/classNames';
import type { TransfersStrings } from '../TransfersPage.strings';
import styles from '../TransfersPage.module.css';

export interface TransfersHeaderProps {
  t: TransfersStrings;
  loading: boolean;
  onRefresh: () => void;
  onNewRequest: () => void;
}

/** The top bar: title, subtitle, refresh and the New Request button. */
export function TransfersHeader({ t, loading, onRefresh, onNewRequest }: TransfersHeaderProps): React.ReactElement {
  return (
    <div className={styles.tpTop}>
      <div className={styles.tpTitleRow}>
        <div>
          <h1>{t.pageTitle}</h1>
          <span className={styles.tpSub}>{t.pageSubtitle}</span>
        </div>
      </div>
      <div className={styles.tpTopActions}>
        <button type="button" className={styles.btnRefresh} onClick={onRefresh} disabled={loading} title={t.refresh}>
          <RefreshCw size={13} className={cx(loading && styles.spin)} />
        </button>
        <button type="button" className={styles.btnNew} onClick={onNewRequest}>
          <Plus size={14} /> {t.newRequest}
        </button>
      </div>
    </div>
  );
}
