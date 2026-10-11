import React from 'react';
import { AlertTriangle, Check, Clock, Home, Users } from 'lucide-react';
import { cx } from '../../../../shared/lib/classNames';
import { formatElapsed } from '../allocationRunHelpers';
import type { AllocationRunStrings } from '../AllocationPage.strings';
import type { RunResultView, RunStatusKey, SummaryView } from '../model';
import { RunStatusBadge } from './RunStatusBadge';
import styles from '../AllocationPage.module.css';

export interface AllocationHeaderCardProps {
  t: AllocationRunStrings;
  statusKey: RunStatusKey;
  regionLabel: string | null;
  lastRunDate: string | null;
  /** Frozen final search duration, shown only after completion (not while running). */
  finalSearchSeconds: number | null;
  result: RunResultView | null;
  summary: SummaryView | null;
  currentAssignedStudents: number;
  hasCurrentAllocation: boolean;
}

/** Page title, status badge, region chip, last-run meta and the four stat tiles. */
export function AllocationHeaderCard({
  t, statusKey, regionLabel, lastRunDate, finalSearchSeconds,
  result, summary, currentAssignedStudents, hasCurrentAllocation,
}: AllocationHeaderCardProps): React.ReactElement {
  return (
    <div className={styles.apHeaderCard}>
      <div className={styles.apHeaderTop}>
        <div>
          <h1 className={styles.apPageTitle}>{t.title}</h1>
          <p className={styles.apPageSubtitle}>{t.subtitle}</p>
        </div>
        <div className={styles.apHeaderMeta}>
          <RunStatusBadge statusKey={statusKey} t={t} />
          {regionLabel && (
            <span className={styles.apRegionChip}>{regionLabel}</span>
          )}
          {lastRunDate && (
            <div className={styles.apLastRun}>
              <Clock size={13} />
              <span>{lastRunDate}</span>
            </div>
          )}
          {/* Frozen final search duration, only after completion - no
              max/remaining shown here, matching the live card. The
              live-preview's own elapsed label (PreviewPanel) stays
              entirely separate and is never conflated with this. */}
          {finalSearchSeconds != null && (
            <div className={styles.apLastRun}>
              <Clock size={13} />
              <span>{t.finalSearchDurationLabel}: {formatElapsed(finalSearchSeconds)}</span>
            </div>
          )}
        </div>
      </div>

      <div className={styles.apHeaderStats}>
        {result && hasCurrentAllocation ? (
          <>
            <div className={styles.apStatItem}>
              <div className={cx(styles.apStatIcon, styles.apStatGreen)}><Check size={16} /></div>
              <div>
                <div className={cx(styles.apStatVal, styles.apStatGreenText)}>{currentAssignedStudents}</div>
                <div className={styles.apStatLbl}>{t.successfulAssign}</div>
              </div>
            </div>
            <div className={styles.apStatDivider} />
            <div className={styles.apStatItem}>
              <div className={cx(styles.apStatIcon, styles.apStatBlue)}><Users size={16} /></div>
              <div>
                <div className={styles.apStatVal}>{result.roommate_matches || 0}</div>
                <div className={styles.apStatLbl}>{t.roommateMatches}</div>
              </div>
            </div>
            <div className={styles.apStatDivider} />
            <div className={styles.apStatItem}>
              <div className={cx(styles.apStatIcon, styles.apStatAmber)}><AlertTriangle size={16} /></div>
              <div>
                <div className={cx(styles.apStatVal, styles.apStatAmberText)}>{result.conflicts || 0}</div>
                <div className={styles.apStatLbl}>{t.conflicts}</div>
              </div>
            </div>
            <div className={styles.apStatDivider} />
            <div className={styles.apStatItem}>
              <div className={cx(styles.apStatIcon, styles.apStatSlate)}><Home size={16} /></div>
              <div>
                <div className={styles.apStatVal}>{summary?.available_beds || 0}</div>
                <div className={styles.apStatLbl}>{t.freeBedsLabel}</div>
              </div>
            </div>
          </>
        ) : (
          <>
            <div className={styles.apStatItem}>
              <div className={cx(styles.apStatIcon, styles.apStatBlue)}><Users size={16} /></div>
              <div>
                <div className={styles.apStatVal}>{summary?.total_students || 0}</div>
                <div className={styles.apStatLbl}>{t.totalStudents}</div>
              </div>
            </div>
            <div className={styles.apStatDivider} />
            <div className={styles.apStatItem}>
              <div className={cx(styles.apStatIcon, styles.apStatGreen)}><Check size={16} /></div>
              <div>
                <div className={cx(styles.apStatVal, styles.apStatGreenText)}>{summary?.assigned_students || 0}</div>
                <div className={styles.apStatLbl}>{t.allocatedStudents}</div>
              </div>
            </div>
            <div className={styles.apStatDivider} />
            <div className={styles.apStatItem}>
              <div className={cx(styles.apStatIcon, styles.apStatAmber)}><AlertTriangle size={16} /></div>
              <div>
                <div className={cx(styles.apStatVal, styles.apStatAmberText)}>{summary?.unassigned_students || 0}</div>
                <div className={styles.apStatLbl}>{t.unallocatedStudents}</div>
              </div>
            </div>
            <div className={styles.apStatDivider} />
            <div className={styles.apStatItem}>
              <div className={cx(styles.apStatIcon, styles.apStatSlate)}><Home size={16} /></div>
              <div>
                <div className={styles.apStatVal}>{summary?.available_beds || 0}</div>
                <div className={styles.apStatLbl}>{t.freeBedsLabel}</div>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
