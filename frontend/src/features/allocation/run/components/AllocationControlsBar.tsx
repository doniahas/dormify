import React from 'react';
import { ExternalLink, Info, Loader, Play, RefreshCw, Square, Trash2 } from 'lucide-react';
import { cx } from '../../../../shared/lib/classNames';
import type { AllocationRunStrings } from '../AllocationPage.strings';
import styles from '../AllocationPage.module.css';

export interface AllocationControlsBarProps {
  t: AllocationRunStrings;
  isRunning: boolean;
  isStopping: boolean;
  isStoppingSave: boolean;
  isDeleting: boolean;
  canRun: boolean;
  hasStudents: boolean;
  isStopRequested: boolean;
  showPreviewBtn: boolean;
  showStopSaveBtn: boolean;
  showCancelBtn: boolean;
  showDelBtn: boolean;
  onRun: () => void;
  onPreview: () => void;
  onStopAndSave: () => void;
  onCancel: () => void;
  onViewResults: () => void;
  onDelete: () => void;
}

/** Run / preview / stop-and-save / cancel on the left; view results / delete on the right. */
export function AllocationControlsBar({
  t, isRunning, isStopping, isStoppingSave, isDeleting, canRun, hasStudents, isStopRequested,
  showPreviewBtn, showStopSaveBtn, showCancelBtn, showDelBtn,
  onRun, onPreview, onStopAndSave, onCancel, onViewResults, onDelete,
}: AllocationControlsBarProps): React.ReactElement {
  return (
    <div className={styles.apControlsBar}>
      <div className={styles.apControlsLeft}>
        {/* Run */}
        <button
          type="button"
          className={cx(styles.apBtn, styles.apBtnPrimary)}
          onClick={onRun}
          disabled={isRunning || !canRun || !hasStudents || isDeleting}
          title={!hasStudents ? t.noStudents : !canRun ? t.noPermission : ''}
        >
          {isRunning ? (
            <>
              <RefreshCw size={15} className={styles.apSpin} />
              {isStopping ? t.stoppingStopping : isStoppingSave ? t.stoppingSave : t.running}
            </>
          ) : (
            <><Play size={15} /> {t.runAllocation}</>
          )}
        </button>

        {/* View Current Result ("צפה בתוצאה הנוכחית") - never stops the solver */}
        {showPreviewBtn && (
          <button type="button" className={cx(styles.apBtn, styles.apBtnGhost)} onClick={onPreview}>
            <Info size={15} />
            {t.viewCurrentResult}
          </button>
        )}

        {/* Stop & Save ("עצור ושמור תוצאה") - keeps the best feasible result */}
        {showStopSaveBtn && (
          <button
            type="button"
            className={cx(styles.apBtn, styles.apBtnWarning)}
            onClick={onStopAndSave}
            disabled={isStopRequested}
          >
            <Square size={15} />
            {t.stopAndSave}
          </button>
        )}

        {/* Cancel ("בטל הרצה") - discards any partial work, smaller/secondary */}
        {showCancelBtn && (
          <button
            type="button"
            className={cx(styles.apBtn, styles.apBtnGhostDanger, styles.apBtnSm)}
            onClick={onCancel}
            disabled={isStopRequested}
          >
            <Square size={13} />
            {t.stopAllocation}
          </button>
        )}

        {/* Stopping indicator */}
        {isStopRequested && !showStopSaveBtn && (
          <div className={cx(styles.apInlineChip, styles.apChipAmber)}>
            <Loader size={13} className={styles.apSpin} />
            {isStoppingSave ? t.stoppingSave : t.stoppingStopping}
          </div>
        )}
      </div>

      <div className={styles.apControlsRight}>
        {/* View Results - always available: it shows the current
            effective allocation stored in the DB, not just the result
            of a run just executed in this browser session. */}
        <button
          type="button"
          className={cx(styles.apBtn, styles.apBtnGhost)}
          onClick={onViewResults}
        >
          <ExternalLink size={15} />
          {t.viewResults}
        </button>

        {/* Delete */}
        {showDelBtn && (
          <button
            type="button"
            className={cx(styles.apBtn, styles.apBtnGhostDanger)}
            onClick={onDelete}
            disabled={isDeleting}
          >
            {isDeleting ? <><Loader size={13} className={styles.apSpin} /> {t.deletingResults}</> : <><Trash2 size={15} /> {t.deleteResults}</>}
          </button>
        )}
      </div>
    </div>
  );
}
