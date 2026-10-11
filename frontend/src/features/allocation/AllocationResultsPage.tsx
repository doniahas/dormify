import React from 'react';
import { useLanguage } from '../../shared/i18n';
import { AssignmentsHierarchy } from './results/components/AssignmentsHierarchy';
import { AvailableBedsTable } from './results/components/AvailableBedsTable';
import { ResultsHeader } from './results/components/ResultsHeader';
import { ResultsMetaCards } from './results/components/ResultsMetaCards';
import { ResultsErrorState, ResultsLoadingState } from './results/components/ResultsStates';
import { ResultsPanelHeading, ResultsViewTabs } from './results/components/ResultsViewTabs';
import { UnassignedAnalysis } from './results/components/UnassignedAnalysis';
import { UnassignedStudentsTable } from './results/components/UnassignedStudentsTable';
import { useAllocationResults } from './results/hooks/useAllocationResults';
import { useHierarchyExpansion } from './results/hooks/useHierarchyExpansion';
import { useResultsNavigation } from './results/hooks/useResultsNavigation';
import { useResultsView } from './results/hooks/useResultsView';
import { useRetryUnassigned } from './results/hooks/useRetryUnassigned';
import { formatLastAllocationDate } from './results/allocationResultsHelpers';
import { allocationResultsStrings } from './results/AllocationResultsPage.strings';
import styles from './results/AllocationResultsPage.module.css';

/**
 * The Allocation Results page: the saved results of the region handed over
 * through router state (or of the user's own scope), shown as the assigned
 * students hierarchy, the unassigned students with their analysis and
 * retry action, and the beds still available. The page composes the
 * feature hooks and components; state lives with the hook that owns it.
 */
function AllocationResultsPage(): React.ReactElement {
  const { language, dir, t: pickStrings } = useLanguage();
  const t = pickStrings(allocationResultsStrings);

  const results = useAllocationResults({ errorLoadingResults: t.errorLoadingResults });
  const view = useResultsView();
  const expansion = useHierarchyExpansion();
  // Buildings management is scoped by the region handed over, never by the summary's.
  const navigation = useResultsNavigation(results.region?.id ?? null);
  const retry = useRetryUnassigned({
    t,
    currentRunId: results.currentRunId,
    onRetried: results.refresh,
  });

  const analysis = (
    <UnassignedAnalysis
      t={t}
      groups={results.unassignedAnalysis}
      unassignedCount={results.unassignedStudents.length}
      currentRunId={results.currentRunId}
      retry={retry}
      onGoToBuildings={navigation.goToBuildings}
    />
  );

  return (
    <div
      className={styles.allocationResultsPage}
      dir={dir}
    >
      <div className={styles.resultsShell}>
        <ResultsHeader t={t} onBack={navigation.goBack} />

        <ResultsMetaCards
          t={t}
          lastAllocationAt={formatLastAllocationDate(results.lastAllocationAt, language)}
        />

        <main className={styles.resultsPanel}>
          <ResultsViewTabs
            t={t}
            activeView={view.activeView}
            counts={results.counts}
            onSelect={view.setActiveView}
          />

          <ResultsPanelHeading t={t} activeView={view.activeView} />

          {results.loading ? (
            <ResultsLoadingState t={t} />
          ) : results.error ? (
            <ResultsErrorState t={t} error={results.error} onRetry={results.reload} />
          ) : view.activeView === 'assigned' ? (
            <AssignmentsHierarchy
              t={t}
              language={language}
              expansion={expansion}
              hierarchy={results.hierarchy}
              isEmpty={results.assignments.length === 0}
            />
          ) : view.activeView === 'unassigned' ? (
            <UnassignedStudentsTable
              t={t}
              language={language}
              students={results.unassignedStudents}
              analysis={analysis}
            />
          ) : (
            <AvailableBedsTable t={t} beds={results.availableBeds} />
          )}
        </main>
      </div>
    </div>
  );
}

export default AllocationResultsPage;
