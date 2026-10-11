import React, { useCallback, useMemo } from 'react';
import { AlertTriangle } from 'lucide-react';
import { useLanguage } from '../../shared/i18n';
import { useAuth } from '../auth/AuthContext';
import type { AuthUser } from '../auth/types';
import { EmptyDetailState } from './components/EmptyDetailState';
import { NewRequestModal } from './components/NewRequestModal';
import { RequestDetailPane } from './components/RequestDetailPane';
import { RequestListPane } from './components/RequestListPane';
import { RequestStatCards } from './components/RequestStatCards';
import { TransfersHeader } from './components/TransfersHeader';
import { useNewRequestModal } from './hooks/useNewRequestModal';
import { useRequestActions } from './hooks/useRequestActions';
import { useRequestFilters } from './hooks/useRequestFilters';
import { useRequestList } from './hooks/useRequestList';
import { useRequestReview } from './hooks/useRequestReview';
import { useSplitter } from './hooks/useSplitter';
import { countRequests, filterRequests } from './transferHelpers';
import { transfersStrings } from './TransfersPage.strings';
import type { StudentRequest } from './types';
import styles from './TransfersPage.module.css';

/** The pre-contract `regionName` key some stored sessions still carry. */
function legacyRegionName(user: AuthUser | null): string | undefined {
  return typeof user?.regionName === 'string' ? user.regionName : undefined;
}

/**
 * The Transfers page: every student request (add / remove / transfer / swap
 * / other) in a two-pane layout - the filterable list on one side, the
 * selected request's details and the reviewer's decision on the other -
 * plus the New Request modal and its wizards. The page composes the feature
 * hooks and components; state lives with the hook that owns it.
 */
function TransfersPage(): React.ReactElement {
  const { user, isCentralAdmin, canEditRegion } = useAuth();
  const { language, dir, t: pickStrings } = useLanguage();
  const t = pickStrings(transfersStrings);
  const central = isCentralAdmin();

  const filters = useRequestFilters({ isCentralAdmin: central });
  const list = useRequestList({ t, isCentralAdmin: central, regionFilter: filters.regionFilter });
  const review = useRequestReview({ t });
  const actions = useRequestActions({ t, reload: list.reload, onDeleted: list.removeRequest });
  const splitter = useSplitter();
  const newRequest = useNewRequestModal({ t, onCreated: list.reload });

  const counts = useMemo(() => countRequests(list.requests), [list.requests]);
  const visible = useMemo(
    () => filterRequests(list.requests, filters.tab, filters.typeFilter, filters.searchQ),
    [list.requests, filters.tab, filters.typeFilter, filters.searchQ]
  );

  const handleSelect = useCallback((req: StudentRequest) => {
    list.select(req);
    void review.loadBedOptions(req);
  }, [list.select, review.loadBedOptions]);

  const selected = list.selected;

  return (
    <div className={styles.tpRoot} dir={dir}>

      <TransfersHeader
        t={t}
        loading={list.loading}
        onRefresh={() => { void list.reload(); }}
        onNewRequest={newRequest.open}
      />

      <RequestStatCards
        t={t}
        counts={counts}
        tab={filters.tab}
        typeFilter={filters.typeFilter}
        onSelect={(key) => {
          filters.selectStatCard(key);
          list.select(null);
        }}
      />

      {list.pageError && <div className={styles.pageErr}><AlertTriangle size={13} /> {list.pageError}</div>}

      {/* Two-pane */}
      <div className={styles.tpBody} style={{ gridTemplateColumns: `${splitter.listWidth}px 6px 1fr` }}>

        <RequestListPane
          t={t}
          isCentralAdmin={central}
          searchQ={filters.searchQ}
          onSearchChange={filters.setSearchQ}
          onClearSearch={filters.clearSearch}
          tab={filters.tab}
          onSelectTab={(v) => {
            filters.setTab(v);
            list.select(null);
          }}
          typeFilter={filters.typeFilter}
          onSelectType={(v) => {
            filters.setTypeFilter(v);
            list.select(null);
          }}
          regions={filters.regions}
          regionFilter={filters.regionFilter}
          onSelectRegion={filters.setRegionFilter}
          loading={list.loading}
          requests={list.requests}
          visible={visible}
          selectedId={selected?.id ?? null}
          onSelect={handleSelect}
        />

        {/* Splitter */}
        <div className={styles.splitter} onMouseDown={splitter.onSplitterMouseDown}>
          <div className={styles.splitterHandle} />
        </div>

        {/* Detail pane */}
        <div className={styles.detailOuter}>
          {!selected
            ? <EmptyDetailState t={t} noRequests={list.requests.length === 0} />
            : (
              <RequestDetailPane
                t={t}
                language={language}
                request={selected}
                review={review.forRequest(selected.id)}
                acting={actions.actionId === selected.id}
                deleting={actions.deletingId === selected.id}
                canEditRegion={canEditRegion}
                onApprove={actions.approve}
                onReject={actions.reject}
                onDelete={actions.remove}
                onCheckFeas={review.checkFeasibility}
                onLoadMoreFeas={() => review.loadMoreFeasibility(selected.id)}
                onLoadMoreBedOptions={() => review.loadMoreBedOptions(selected.id)}
                onSetRoom={(sel) => review.setRoomSelection(selected.id, sel)}
                onSelFeasOpt={(sel) => review.setFeasSelection(selected.id, sel)}
              />
            )}
        </div>
      </div>

      {newRequest.isOpen && (
        <NewRequestModal
          t={t}
          language={language}
          isCentralAdmin={central}
          userRegionName={user?.region_name || legacyRegionName(user)}
          regions={filters.regions}
          state={newRequest}
        />
      )}
    </div>
  );
}

export default TransfersPage;
