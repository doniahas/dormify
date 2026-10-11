import React from 'react';
import { Activity, Clock, Users } from 'lucide-react';
import { formatElapsed } from '../allocationRunHelpers';
import type { AllocationRunStrings } from '../AllocationPage.strings';
import styles from '../AllocationPage.module.css';

export interface RunProgressCardProps {
  t: AllocationRunStrings;
  isStopping: boolean;
  isStoppingSave: boolean;
  displayElapsed: number;
  progressPct: number;
  unassignedStudents: number;
}

/** The live run card: status line, elapsed time and the elapsed/max bar. */
export function RunProgressCard({
  t, isStopping, isStoppingSave, displayElapsed, progressPct, unassignedStudents,
}: RunProgressCardProps): React.ReactElement {
  return (
    <div className={styles.apProgressCard}>
      <div className={styles.apProgressHeader}>
        <div className={styles.apProgressStatus}>
          <Activity size={15} />
          <span>
            {isStopping ? t.stoppingStopping : isStoppingSave ? t.stoppingSave : t.progressTitle}
          </span>
        </div>
        <div className={styles.apProgressTimer}>
          <Clock size={13} />
          <span>{t.elapsedLabel}</span>
          <span>{formatElapsed(displayElapsed)}</span>
        </div>
      </div>

      {/* Bar = elapsed / configured max search time ONLY - never an
          algorithm/optimality-completion estimate. CP-SAT gives no
          live "how close to done" signal beyond elapsed time; do not
          relabel this as "% completed". Anchored to the backend
          (AllocationRun.search_started_at via elapsed_search_seconds),
          never to how long this page happened to be open - survives
          navigation, refresh, and a second tab. This is a MAXIMUM,
          not a promise: an earlier OPTIMAL proof stops the solver
          (and this bar) sooner. */}
      <div className={styles.apProgressBarWrap}>
        <div className={styles.apProgressBar}>
          <div className={styles.apProgressFill} style={{ width: `${progressPct}%` }} />
        </div>
        <span className={styles.apProgressPct}>{progressPct}%</span>
      </div>

      <div className={styles.apProgressDetail}>
        <span>
          <Users size={12} />
          {unassignedStudents} {t.students}
        </span>
      </div>
    </div>
  );
}
