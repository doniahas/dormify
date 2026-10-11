import React from 'react';
import { CheckCircle, Clock, Inbox, XCircle, type LucideIcon } from 'lucide-react';
import { cx } from '../../../shared/lib/classNames';
import type { RequestCounts, RequestTab, RequestTypeFilter, StatCardKey, StatColor } from '../model';
import type { TransfersStrings } from '../TransfersPage.strings';
import styles from '../TransfersPage.module.css';
import { capitalize } from './RequestAtoms';

interface StatCardDef {
  key: StatCardKey;
  label: string;
  Icon: LucideIcon;
  color: StatColor;
}

function statCardDefs(t: TransfersStrings): StatCardDef[] {
  return [
    { key: 'all',      label: t.statTotal,    Icon: Inbox,       color: 'slate' },
    { key: 'pending',  label: t.statPending,  Icon: Clock,       color: 'amber' },
    { key: 'approved', label: t.statApproved, Icon: CheckCircle, color: 'green' },
    { key: 'rejected', label: t.statRejected, Icon: XCircle,     color: 'rose' },
  ];
}

export interface RequestStatCardsProps {
  t: TransfersStrings;
  counts: RequestCounts;
  tab: RequestTab;
  typeFilter: RequestTypeFilter;
  onSelect: (key: StatCardKey) => void;
}

/** The four status totals above the two-pane body; each card also selects its status. */
export function RequestStatCards({ t, counts, tab, typeFilter, onSelect }: RequestStatCardsProps): React.ReactElement {
  return (
    <div className={styles.statsRow}>
      {statCardDefs(t).map((sc) => {
        const active = tab === sc.key || (sc.key === 'all' && tab === 'all' && typeFilter === 'all');
        return (
          <button
            key={sc.key}
            type="button"
            className={cx(styles.statCard, styles[`stat${capitalize(sc.color)}`], active && styles.statActive)}
            aria-pressed={active}
            onClick={() => onSelect(sc.key)}
          >
            <div className={styles.scIco}><sc.Icon size={14} /></div>
            <div className={styles.scVal}>{counts[sc.key] ?? 0}</div>
            <div className={styles.scLbl}>{sc.label}</div>
          </button>
        );
      })}
    </div>
  );
}
