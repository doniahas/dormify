import React from 'react';
import { BedDouble, UserCheck, UserX, Users } from 'lucide-react';
import { cx } from '../../../../shared/lib/classNames';
import type { AllocationResultsStrings } from '../AllocationResultsPage.strings';
import type { ResultsCounts, ResultsView } from '../model';
import styles from '../AllocationResultsPage.module.css';

export interface ResultsViewTabsProps {
  t: AllocationResultsStrings;
  activeView: ResultsView;
  counts: ResultsCounts;
  onSelect: (view: ResultsView) => void;
}

/** The three view buttons with their totals: assigned students, unassigned students, available beds. */
export function ResultsViewTabs({ t, activeView, counts, onSelect }: ResultsViewTabsProps): React.ReactElement {
  return (
    <div
      className={styles.viewTabs}
      role="tablist"
      aria-label={t.title}
    >
      <button
        type="button"
        className={cx(styles.viewTab, activeView === 'assigned' && cx(styles.active, styles.assigned))}
        aria-pressed={activeView === 'assigned'}
        onClick={() => onSelect('assigned')}
      >
        <UserCheck size={18} />
        <span>
          {t.assignedStudentsView}
        </span>
        <strong>{counts.assigned}</strong>
      </button>

      <button
        type="button"
        className={cx(styles.viewTab, activeView === 'unassigned' && cx(styles.active, styles.unassigned))}
        aria-pressed={activeView === 'unassigned'}
        onClick={() => onSelect('unassigned')}
      >
        <UserX size={18} />
        <span>
          {t.unassignedStudentsView}
        </span>
        <strong>{counts.unassigned}</strong>
      </button>

      <button
        type="button"
        className={cx(styles.viewTab, activeView === 'beds' && cx(styles.active, styles.beds))}
        aria-pressed={activeView === 'beds'}
        onClick={() => onSelect('beds')}
      >
        <BedDouble size={18} />
        <span>{t.availableBedsView}</span>
        <strong>
          {counts.available_beds}
        </strong>
      </button>
    </div>
  );
}

export interface ResultsPanelHeadingProps {
  t: AllocationResultsStrings;
  activeView: ResultsView;
}

/** The active view's title row inside the panel. */
export function ResultsPanelHeading({ t, activeView }: ResultsPanelHeadingProps): React.ReactElement {
  const activeTitle =
    activeView === 'assigned'
      ? t.assignmentsTitle
      : activeView === 'unassigned'
        ? t.unassignedTitle
        : t.availableBedsTitle;

  return (
    <div className={styles.panelHeading}>
      <div className={styles.panelTitle}>
        {activeView === 'assigned' ? (
          <Users size={19} />
        ) : activeView === 'unassigned' ? (
          <UserX size={19} />
        ) : (
          <BedDouble size={19} />
        )}

        <span>{activeTitle}</span>
      </div>
    </div>
  );
}
