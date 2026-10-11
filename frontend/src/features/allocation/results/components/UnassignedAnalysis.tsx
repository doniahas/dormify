import React from 'react';
import { AlertTriangle, Building2, Loader, RefreshCw, UserCheck } from 'lucide-react';
import type { Id } from '../../../../shared/api/contracts';
import { cx } from '../../../../shared/lib/classNames';
import type { AllocationResultsStrings } from '../AllocationResultsPage.strings';
import { reasonTextKey } from '../allocationResultsHelpers';
import type { RetryUnassignedState } from '../hooks/useRetryUnassigned';
import type { UnassignedAnalysisGroup } from '../model';
import { RetryConfirmModal } from './RetryConfirmModal';
import styles from './UnassignedAnalysis.module.css';

export interface UnassignedAnalysisProps {
  t: AllocationResultsStrings;
  groups: UnassignedAnalysisGroup[];
  /** How many students the retry would cover (the confirmation quotes it). */
  unassignedCount: number;
  /** The run the retry is scoped to; without one the action is disabled. */
  currentRunId: Id | null;
  retry: RetryUnassignedState;
  onGoToBuildings: (group: UnassignedAnalysisGroup) => void;
}

/**
 * Why some students stayed unassigned: one card per (dorm type, gender,
 * housing type) group with its free-inventory figures and reason, the
 * "retry unassigned" action with its outcome message, and the retry
 * confirmation. Renders nothing when the server sent no analysis.
 */
export function UnassignedAnalysis({
  t, groups, unassignedCount, currentRunId, retry, onGoToBuildings,
}: UnassignedAnalysisProps): React.ReactElement | null {
  if (groups.length === 0) return null;

  return (
    <div className={styles.unassignedAnalysis}>
      <div className={styles.unassignedAnalysisHeader}>
        <AlertTriangle size={17} />
        <span>{t.unassignedAnalysisTitle}</span>
      </div>

      <div className={styles.unassignedAnalysisGroups}>
        {groups.map((group, index) => {
          const reasonKey = reasonTextKey(group.reason_code);
          return (
            <div
              className={styles.unassignedAnalysisCard}
              key={`${group.accepted_dorm_type_code ?? 'none'}-${group.gender}-${group.housing_type}-${index}`}
            >
              <div className={styles.unassignedAnalysisCardTitle}>
                <strong>{group.student_count}</strong> {t.studentsUnassignedLabel}
                {' — '}
                {group.housing_type_display || group.housing_type || '-'}
                {group.accepted_dorm_type_name ? ` · ${group.accepted_dorm_type_name}` : ''}
              </div>

              <div className={styles.unassignedAnalysisCounts}>
                <span>{group.physically_free_beds_in_accepted_dorm} {t.physicallyFreeBedsLabel}</span>
                <span className={styles.unassignedAnalysisCompatible}>
                  {group.compatible_free_beds} {t.compatibleFreeBedsLabel}
                </span>
              </div>

              {group.inventory_breakdown && group.inventory_breakdown.length > 0 && (
                <div className={styles.unassignedAnalysisInventory}>
                  <span className={styles.unassignedAnalysisInventoryLabel}>
                    {t.inventoryBreakdownLabel}:
                  </span>
                  {group.inventory_breakdown.map((item, itemIndex) => (
                    <span className={styles.unassignedAnalysisInventoryChip} key={itemIndex}>
                      {item.free_beds} {item.category_display || item.category} · {item.apartment_type_display || item.apartment_type}
                    </span>
                  ))}
                </div>
              )}

              <div className={styles.unassignedAnalysisReason}>
                {reasonKey ? t[reasonKey] : ''}
              </div>

              {group.accepted_dorm_type_code !== null && group.accepted_dorm_type_code !== undefined && (
                <button
                  type="button"
                  className={styles.unassignedAnalysisBuildingsBtn}
                  onClick={() => onGoToBuildings(group)}
                >
                  <Building2 size={14} />
                  {t.showRelevantBeds}
                </button>
              )}
            </div>
          );
        })}
      </div>

      <div className={styles.unassignedRetryBlock}>
        <button
          type="button"
          className={styles.unassignedRetryBtn}
          onClick={retry.openConfirm}
          disabled={retry.loading || !currentRunId}
          title={!currentRunId ? t.noRunToRetry : ''}
        >
          {retry.loading ? (
            <><Loader size={15} className={styles.spin} /> {t.retrying}</>
          ) : (
            <><RefreshCw size={15} /> {t.retryUnassigned}</>
          )}
        </button>
        {retry.error && (
          <div className={cx(styles.unassignedRetryMessage, styles.error)}>
            <AlertTriangle size={14} /> {retry.error}
          </div>
        )}
        {retry.success && (
          <div className={cx(styles.unassignedRetryMessage, styles.success)}>
            <UserCheck size={14} /> {retry.success}
          </div>
        )}
      </div>

      {retry.confirmOpen && (
        <RetryConfirmModal
          t={t}
          unassignedCount={unassignedCount}
          loading={retry.loading}
          onCancel={retry.closeConfirm}
          onConfirm={() => { void retry.retry(); }}
        />
      )}
    </div>
  );
}
