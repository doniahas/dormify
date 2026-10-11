import React from 'react';
import { Inbox, Search, X } from 'lucide-react';
import type { Region } from '../../../shared/api/contracts';
import { cx } from '../../../shared/lib/classNames';
import { REQUEST_TABS, type RegionFilter, type RequestTab, type RequestTypeFilter } from '../model';
import type { TransfersStrings } from '../TransfersPage.strings';
import type { StudentRequest } from '../types';
import styles from '../TransfersPage.module.css';
import { EmptyPane, Spinner } from './RequestAtoms';
import { RequestListItem } from './RequestListItem';

interface TypeFilterOption {
  v: RequestTypeFilter;
  l: string;
}

function typeFilterOptions(t: TransfersStrings): TypeFilterOption[] {
  return [
    { v: 'all',            l: t.typeFilterAll },
    { v: 'add_student',    l: t.typeFilterAddStudent },
    { v: 'remove_student', l: t.typeFilterRemoveStudent },
    { v: 'room',           l: t.typeFilterRoom },
    { v: 'apartment',      l: t.typeFilterApartment },
    { v: 'swap',           l: t.typeFilterSwap },
    { v: 'other',          l: t.typeFilterOther },
  ];
}

function tabLabel(t: TransfersStrings, tab: RequestTab): string {
  switch (tab) {
    case 'pending': return t.tabPending;
    case 'approved': return t.tabApproved;
    case 'rejected': return t.tabRejected;
    default: return t.tabAll;
  }
}

export interface RequestListPaneProps {
  t: TransfersStrings;
  isCentralAdmin: boolean;
  searchQ: string;
  onSearchChange: (query: string) => void;
  onClearSearch: () => void;
  tab: RequestTab;
  onSelectTab: (tab: RequestTab) => void;
  typeFilter: RequestTypeFilter;
  onSelectType: (type: RequestTypeFilter) => void;
  regions: Region[];
  regionFilter: RegionFilter;
  onSelectRegion: (region: RegionFilter) => void;
  loading: boolean;
  /** Every loaded request (decides between the two empty states). */
  requests: StudentRequest[];
  /** The rows after the tab/type/search filters. */
  visible: StudentRequest[];
  selectedId: number | null;
  onSelect: (request: StudentRequest) => void;
}

/** The list pane: search, status tabs, type and region filters, the count and the rows. */
export function RequestListPane({
  t, isCentralAdmin,
  searchQ, onSearchChange, onClearSearch,
  tab, onSelectTab, typeFilter, onSelectType,
  regions, regionFilter, onSelectRegion,
  loading, requests, visible, selectedId, onSelect,
}: RequestListPaneProps): React.ReactElement {
  return (
    <div className={styles.listPane}>
      <div className={styles.listToolbar}>
        <div className={styles.ltSearch}>
          <Search size={12} />
          <input value={searchQ} onChange={(e) => onSearchChange(e.target.value)} placeholder={t.searchPlaceholder} />
          {searchQ && <button type="button" onClick={onClearSearch}><X size={10} /></button>}
        </div>
        <div className={styles.statusTabs}>
          {REQUEST_TABS.map((v) => (
            <button
              key={v}
              type="button"
              className={cx(styles.stab, tab === v && styles.stabActive)}
              aria-pressed={tab === v}
              onClick={() => onSelectTab(v)}
            >
              {tabLabel(t, v)}
            </button>
          ))}
        </div>
        <div className={styles.filterRow}>
          <span className={styles.filterLabel}>{t.requestTypeLabel}</span>

          <select
            className={styles.typeSelect}
            value={typeFilter}
            onChange={(e) => onSelectType(e.target.value as RequestTypeFilter)}
          >
            {typeFilterOptions(t).map((tf) => (
              <option key={tf.v} value={tf.v}>
                {tf.l}
              </option>
            ))}
          </select>
        </div>
        {isCentralAdmin && (
          <div className={styles.filterRow}>
            <span className={styles.filterLabel}>{t.regionLabel}</span>

            <select
              className={styles.regionSelect}
              value={regionFilter}
              onChange={(e) => onSelectRegion(e.target.value)}
              title={t.regionFilterTitle}
            >
              <option value="all">{t.allRegions}</option>
              {regions.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.name}
                </option>
              ))}
            </select>
          </div>
        )}
        <div className={styles.ltCount}>{t.requestsCount(visible.length)}</div>
      </div>

      <div className={styles.rqList} aria-busy={loading && !requests.length ? 'true' : undefined}>
        {loading && !requests.length && <div className={styles.listLoading}><Spinner /> {t.loadingRequests}</div>}
        {!loading && visible.length === 0 && (
          requests.length === 0
            ? <EmptyPane icon={Inbox} title={t.emptyNoRequestsTitle} sub={t.emptyNoRequestsSub} />
            : <EmptyPane icon={Search} title={t.emptyNoResultsTitle} sub={t.emptyNoResultsSub} />
        )}
        {visible.map((r) => (
          <RequestListItem
            key={r.id}
            t={t}
            request={r}
            selected={selectedId === r.id}
            onClick={() => onSelect(r)}
          />
        ))}
      </div>
    </div>
  );
}
