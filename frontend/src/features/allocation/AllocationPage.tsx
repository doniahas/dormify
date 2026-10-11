import React, { useCallback, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useLanguage } from '../../shared/i18n';
import { localizeRegionName } from '../../shared/lib/locationNames';
import { useAuth } from '../auth/AuthContext';
import {
  activePopulationSummary,
  deriveRunFlags,
  formatLastRunDate,
  isUpperDormRegion,
  lastRunTimestamp,
  progressPercent,
  regionLikeOf,
} from './run/allocationRunHelpers';
import { allocationRunStrings } from './run/AllocationPage.strings';
import { AllocationControlsBar } from './run/components/AllocationControlsBar';
import { AllocationHeaderCard } from './run/components/AllocationHeaderCard';
import { AllocationErrorState, AllocationLoadingState, InlineAlert } from './run/components/AllocationPageStates';
import { ConditionsCard } from './run/components/ConditionsCard';
import { ConfirmDialog } from './run/components/ConfirmDialog';
import { InboxNotice } from './run/components/InboxNotice';
import { InventoryCard } from './run/components/InventoryCard';
import { MaxSearchTimeCard } from './run/components/MaxSearchTimeCard';
import { PopulationCard } from './run/components/PopulationCard';
import { PreviewPanel } from './run/components/PreviewPanel';
import { RunProgressCard } from './run/components/RunProgressCard';
import { ToastNotification } from './run/components/ToastNotification';
import { useAllocationConstraints } from './run/hooks/useAllocationConstraints';
import { useAllocationRun } from './run/hooks/useAllocationRun';
import { useAllocationSummary } from './run/hooks/useAllocationSummary';
import { useAllocationToast } from './run/hooks/useAllocationToast';
import { useMaxSolverTime } from './run/hooks/useMaxSolverTime';
import { useRunPreview } from './run/hooks/useRunPreview';
import { useSearchTiming } from './run/hooks/useSearchTiming';
import type { AllocationResultsRouteState, InventoryTypeKey } from './run/model';
import styles from './run/AllocationPage.module.css';

/**
 * The Allocation page: starts, watches and stops the backend allocation
 * run for the user's region, shows the stored result and the inventory /
 * population summary, and carries the user's constraint configuration
 * (critical vs flexible, weights, max search time) to the run. The page
 * composes the feature hooks and components; state lives with the hook
 * that owns it. The allocation itself is entirely the backend's.
 */
function AllocationPage(): React.ReactElement {
  const navigate = useNavigate();
  const { isCentralAdmin, getUserRegion, canRunAllocation } = useAuth();
  const { language, t: pickStrings } = useLanguage();
  const t = pickStrings(allocationRunStrings);

  const central = isCentralAdmin() === true;
  const canRun = canRunAllocation();

  const [showPopulationDetails, setShowPopulationDetails] = useState(false);
  const [expandedType, setExpandedType] = useState<InventoryTypeKey | null>(null);

  const { toast, showToast } = useAllocationToast();
  const constraints = useAllocationConstraints();
  const maxSolver = useMaxSolverTime(t);
  const page = useAllocationSummary({ central, t });
  const timing = useSearchTiming();
  const preview = useRunPreview({ t });
  const run = useAllocationRun({
    t,
    getUserRegion,
    summary: page.summary,
    inboxItem: page.inboxItem,
    loadPage: page.loadPage,
    setError: page.setError,
    showToast,
    validateMaxSolverTime: maxSolver.validate,
    setMaxSolverError: maxSolver.setError,
    maxSolverSeconds: maxSolver.seconds,
    effectiveConfig: constraints.effectiveConfig,
    applySearchTiming: timing.applySearchTiming,
    resetSearchTiming: timing.resetSearchTiming,
    closePreview: preview.close,
    resetPreview: preview.reset,
  });

  const { summary, inboxItem, error } = page;
  const { result, runId, runStatus, isRunning, isStopping, isStoppingSave, isDeleting } = run;

  const flags = deriveRunFlags({
    isRunning, isStopping, isStoppingSave, runId, runStatus, result, canRun, summary,
  });
  const progressPct = progressPercent(timing.searchTiming, timing.displayElapsed);

  const handleViewResults = useCallback(() => {
    const state: AllocationResultsRouteState = {
      result: result || null,
      summary,
      constraints: constraints.effectiveConfig,
      region: summary?.region || null,
      generatedAt: result ? new Date().toISOString() : null,
    };
    navigate('/allocation/results', { state });
  }, [navigate, result, summary, constraints.effectiveConfig]);

  const toggleInventoryType = useCallback((key: InventoryTypeKey) => {
    setExpandedType((prev) => (prev === key ? null : key));
  }, []);

  // ── Loading / Error States ───────────────────
  if (page.loading) {
    return <AllocationLoadingState t={t} />;
  }

  if (error && !summary) {
    return <AllocationErrorState t={t} error={error} onRetry={() => { void page.loadPage(); }} />;
  }

  const lastRunDate = formatLastRunDate(lastRunTimestamp(flags.hasCurrentAllocation, result), t.dateLocale);
  const regionLabel = summary?.region ? localizeRegionName(regionLikeOf(summary.region), language) : null;
  const activePopulation = activePopulationSummary(flags.hasCurrentAllocation, result, summary);

  return (
    <div className={styles.apPage}>
      <ToastNotification toast={toast} />
      <ConfirmDialog modal={run.confirmModal} t={t} onClose={run.closeConfirm} />
      <PreviewPanel t={t} state={preview} />

      <div className={styles.apShell}>

        {/* ── 1. Page Header ─────────────────── */}
        <AllocationHeaderCard
          t={t}
          statusKey={flags.statusKey}
          regionLabel={regionLabel}
          lastRunDate={lastRunDate}
          finalSearchSeconds={!isRunning && result?.final_search_seconds != null ? result.final_search_seconds : null}
          result={result}
          summary={summary}
          currentAssignedStudents={flags.currentAssignedStudents}
          hasCurrentAllocation={flags.hasCurrentAllocation}
        />

        {/* ── 1b. Population Summary (compact) ── */}
        {activePopulation && (
          <PopulationCard
            t={t}
            population={activePopulation}
            showDetails={showPopulationDetails}
            onToggleDetails={() => setShowPopulationDetails((prev) => !prev)}
          />
        )}

        {/* ── 1c. Max Search Time (before run) ── */}
        {!isRunning && (
          <MaxSearchTimeCard
            t={t}
            value={maxSolver.value}
            unit={maxSolver.unit}
            error={maxSolver.error}
            disabled={isRunning}
            onValueChange={maxSolver.changeValue}
            onUnitChange={maxSolver.changeUnit}
          />
        )}

        {/* ── 2. Controls Bar ────────────────── */}
        <AllocationControlsBar
          t={t}
          isRunning={isRunning}
          isStopping={isStopping}
          isStoppingSave={isStoppingSave}
          isDeleting={isDeleting}
          canRun={canRun}
          hasStudents={flags.hasStudents}
          isStopRequested={flags.isStopRequested}
          showPreviewBtn={flags.showPreviewBtn}
          showStopSaveBtn={flags.showStopSaveBtn}
          showCancelBtn={flags.showCancelBtn}
          showDelBtn={flags.showDelBtn}
          onRun={() => { void run.runAllocation(); }}
          onPreview={() => preview.open(runId)}
          onStopAndSave={run.requestStopAndSave}
          onCancel={run.requestStopAllocation}
          onViewResults={handleViewResults}
          onDelete={run.requestDeleteResults}
        />

        {/* ── 3. Progress Card (when running) ── */}
        {isRunning && (
          <RunProgressCard
            t={t}
            isStopping={isStopping}
            isStoppingSave={isStoppingSave}
            displayElapsed={timing.displayElapsed}
            progressPct={progressPct}
            unassignedStudents={summary?.unassigned_students || 0}
          />
        )}

        {/* ── 4. Inline error (non-fatal) ─────── */}
        {error && summary && (
          <InlineAlert message={error} onDismiss={() => page.setError(null)} />
        )}

        {/* ── 5. Inbox Notice (compact) ────────── */}
        {inboxItem && (
          <InboxNotice t={t} inboxItem={inboxItem} />
        )}

        {/* ── 6. Main Content ──────────────── */}
        <div className={styles.apMainCol}>
          <InventoryCard
            t={t}
            inventory={summary?.inventory_by_type ?? null}
            expandedType={expandedType}
            onToggle={toggleInventoryType}
          />

          <ConditionsCard
            t={t}
            hardConstraints={constraints.hardConstraints}
            optimizationPreferences={constraints.optimizationPreferences}
            isUpperDorm={isUpperDormRegion(summary)}
            canRun={canRun}
            onToggle={constraints.toggleConstraintEnabled}
            onWeightChange={constraints.setConstraintWeight}
          />
        </div>
      </div>
    </div>
  );
}

export default AllocationPage;
