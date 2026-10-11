import React from 'react';
import { Clock3 } from 'lucide-react';
import { cx } from '../../../../shared/lib/classNames';
import type { AllocationResultsStrings } from '../AllocationResultsPage.strings';
import styles from '../AllocationResultsPage.module.css';

export interface ResultsMetaCardsProps {
  t: AllocationResultsStrings;
  /** The last-allocation date, already formatted for the interface language. */
  lastAllocationAt: string;
}

/** The meta row above the panel: when the last allocation happened. */
export function ResultsMetaCards({ t, lastAllocationAt }: ResultsMetaCardsProps): React.ReactElement {
  return (
    <section className={cx(styles.metaGrid, styles.singleMeta)}>
      <div className={styles.metaCard}>
        <span className={cx(styles.metaIcon, styles.purple)}>
          <Clock3 size={19} />
        </span>

        <div>
          <div className={styles.metaLabel}>
            {t.lastAllocationAt}
          </div>

          <div className={styles.metaValue}>
            {lastAllocationAt}
          </div>
        </div>
      </div>
    </section>
  );
}
