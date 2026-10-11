import React from 'react';
import { BedDouble, LogOut, RefreshCw, UserCheck, UserPlus, Users, type LucideIcon } from 'lucide-react';
import { cx } from '../../../shared/lib/classNames';
import type { StudentTab, StudentTabCounts } from '../model';
import type { StudentsStrings } from '../StudentsPage.strings';
import styles from '../StudentsPage.module.css';

interface TabDef {
  v: StudentTab;
  color: 'gray' | 'green' | 'blue' | 'purple' | 'red' | 'orange';
  primary: string;
  secondary: string;
  icon: LucideIcon;
}

function tabDefs(t: StudentsStrings): TabDef[] {
  return [
    { v: 'all',        color: 'gray',   primary: t.tabAllPrimary,          secondary: t.tabAllSecondary,          icon: Users },
    { v: 'continuing', color: 'green',  primary: t.tabStayingPrimary,      secondary: t.tabStayingSecondary,      icon: UserCheck },
    { v: 'new',        color: 'blue',   primary: t.tabNewPrimary,          secondary: t.tabNewSecondary,          icon: UserPlus },
    { v: 'transfer',   color: 'purple', primary: t.tabTransferringPrimary, secondary: t.tabTransferringSecondary, icon: RefreshCw },
    { v: 'leaving',    color: 'red',    primary: t.tabLeavingPrimary,      secondary: t.tabLeavingSecondary,      icon: LogOut },
    { v: 'unassigned', color: 'orange', primary: t.tabUnassignedPrimary,   secondary: t.tabUnassignedSecondary,   icon: BedDouble },
  ];
}

export interface StudentStatTabsProps {
  t: StudentsStrings;
  activeTab: StudentTab;
  counts: StudentTabCounts;
  onSelect: (tab: StudentTab) => void;
}

/** The six status cards that double as the list's tabs. */
export function StudentStatTabs({ t, activeTab, counts, onSelect }: StudentStatTabsProps): React.ReactElement {
  return (
    <div className={styles.statTabs}>
      {tabDefs(t).map((tab) => {
        const Icon = tab.icon;
        const isActive = activeTab === tab.v;
        return (
          <button
            key={tab.v}
            type="button"
            className={cx(styles.statTab, styles[tab.color], isActive && styles.active)}
            aria-pressed={isActive}
            onClick={() => onSelect(tab.v)}
          >
            <div className={styles.statIconWrap}><Icon size={22} /></div>
            <div className={styles.statText}>
              <div className={styles.statPrimary}>{tab.primary}</div>
              {tab.secondary && <div className={styles.statSecondary}>{tab.secondary}</div>}
            </div>
            <div className={styles.statCount}>{counts[tab.v] ?? 0}</div>
          </button>
        );
      })}
    </div>
  );
}
