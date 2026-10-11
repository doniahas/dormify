import React from 'react';
import { Info, Loader, RefreshCw, XCircle } from 'lucide-react';
import { cx } from '../../../../shared/lib/classNames';
import { formatElapsed, previewCell, previewRowKey, readPreviewSnapshot } from '../allocationRunHelpers';
import type { AllocationRunStrings } from '../AllocationPage.strings';
import type { RunPreviewState } from '../hooks/useRunPreview';
import pageStyles from '../AllocationPage.module.css';
import styles from './AllocationOverlays.module.css';

export interface PreviewPanelProps {
  t: AllocationRunStrings;
  state: Pick<RunPreviewState, 'isOpen' | 'loading' | 'errorMsg' | 'snapshot' | 'hasNewer' | 'close' | 'refreshToLatest'>;
}

/**
 * "תוצאה זמנית": the current best-feasible result while the solver is
 * still searching. Reading it never stops the run.
 */
export function PreviewPanel({ t, state }: PreviewPanelProps): React.ReactElement | null {
  const { isOpen, loading, errorMsg, snapshot, hasNewer, close, refreshToLatest } = state;
  if (!isOpen) return null;

  const view = readPreviewSnapshot(snapshot);

  return (
    <div className={styles.apModalOverlay} role="dialog" aria-modal="true">
      <div className={styles.apPreviewBox}>
        <div className={styles.apPreviewHeader}>
          <div>
            <h3 className={styles.apPreviewTitle}>{t.previewTitle}</h3>
            <p className={styles.apPreviewSubtitle}>{t.previewSubtitle}</p>
          </div>
          <button type="button" className={styles.apPreviewClose} onClick={close} aria-label={t.previewClose}>×</button>
        </div>

        {hasNewer && (
          <div className={styles.apPreviewNewerBanner}>
            <span>{t.previewNewerAvailable}</span>
            <button
              type="button"
              className={cx(pageStyles.apBtn, pageStyles.apBtnPrimary, pageStyles.apBtnSm)}
              onClick={refreshToLatest}
            >
              <RefreshCw size={13} />
              {t.previewRefresh}
            </button>
          </div>
        )}

        {loading && !view ? (
          <div className={styles.apPreviewEmpty}>
            <Loader size={20} className={styles.apSpin} />
            <span>{t.previewLoadingMsg}</span>
          </div>
        ) : errorMsg && !view ? (
          <div className={styles.apPreviewEmpty}>
            <XCircle size={20} />
            <span>{errorMsg}</span>
          </div>
        ) : !view ? (
          <div className={styles.apPreviewEmpty}>
            <Info size={20} />
            <span>{t.previewUnavailable}</span>
          </div>
        ) : (
          <>
            <div className={styles.apPreviewStats}>
              <div className={styles.apPreviewStat}>
                <div className={cx(styles.apPreviewStatVal, styles.apStatGreenText)}>{view.assignedCount}</div>
                <div className={styles.apPreviewStatLbl}>{t.previewAssignedLabel}</div>
              </div>
              <div className={styles.apPreviewStat}>
                <div className={cx(styles.apPreviewStatVal, styles.apStatAmberText)}>{view.unassignedCount}</div>
                <div className={styles.apPreviewStatLbl}>{t.previewUnassignedLabel}</div>
              </div>
              <div className={styles.apPreviewStat}>
                <div className={styles.apPreviewStatVal}>
                  {view.solverStatus === 'OPTIMAL' ? t.previewOptimalState : t.previewFeasibleState}
                </div>
                <div className={styles.apPreviewStatLbl}>{t.previewSolverStateLabel}</div>
              </div>
              <div className={styles.apPreviewStat}>
                <div className={styles.apPreviewStatVal}>{formatElapsed(Math.round(view.wallTime))}</div>
                <div className={styles.apPreviewStatLbl}>{t.previewElapsedLabel}</div>
              </div>
            </div>

            <div className={styles.apPreviewTableWrap}>
              {view.assignments.length === 0 ? (
                <div className={styles.apEmptyHint}>
                  <Info size={14} />
                  <span>{t.previewTableEmpty}</span>
                </div>
              ) : (
                <table className={styles.apPreviewTable}>
                  <thead>
                    <tr>
                      <th>{t.previewStudentCol}</th>
                      <th>{t.previewApartmentCol}</th>
                      <th>{t.previewRoomCol}</th>
                      <th>{t.previewBedCol}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {view.assignments.map((row) => (
                      <tr key={previewRowKey(row)}>
                        <td>{previewCell(row.student_name)}</td>
                        <td>{previewCell(row.apartment_code)}</td>
                        <td>{previewCell(row.room_code)}</td>
                        <td>{previewCell(row.bed_label)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
