import React from 'react';
import { AlertTriangle, BedDouble, Loader2, User, X } from 'lucide-react';
import { sameId } from '../../../shared/api/normalize';
import type { Language } from '../../../shared/i18n';
import { cx } from '../../../shared/lib/classNames';
import { localizeRegionName } from '../../../shared/lib/locationNames';
import BedMatchPicker, { assignActionLabel } from '../../allocation/BedMatchPicker';
import type { BedAssignmentState } from '../hooks/useBedAssignment';
import type { StudentDetailView } from '../model';
import type { StudentsStrings } from '../StudentsPage.strings';
import { getName } from '../studentHelpers';
import type { StudentFilterOption } from '../types';
import styles from './StudentModals.module.css';

export interface AssignBedModalProps {
  t: StudentsStrings;
  language: Language;
  isCentralAdmin: boolean;
  /** The regions a central admin may search instead of the student's home region. */
  regions: StudentFilterOption[];
  student: StudentDetailView;
  state: BedAssignmentState;
  /** Opens the Edit Student modal for the blocking-field shortcut (returns here after a save). */
  onEditStudent: (student: StudentDetailView) => void;
}

// Shown on the confirm button once a bed is picked; the modal's own copy is
// Hebrew regardless of the interface language (BedMatchPicker is rendered
// Hebrew-only here too).
const PICKER_LANGUAGE = 'he';

/** The Assign / Reassign Bed modal around the shared BedMatchPicker. */
export function AssignBedModal({
  t, language, isCentralAdmin, regions, student, state, onEditStudent,
}: AssignBedModalProps): React.ReactElement {
  const {
    buildings, meta, loading, loadingMore, loadMoreError, assigning, error, success,
    blockingField, regionOverride, selection, select, close, retry, changeRegion, loadMore, submit,
  } = state;

  const confirmLabel = !selection
    ? t.selectBedFirst
    : student.is_assigned
      ? assignActionLabel(selection, PICKER_LANGUAGE).replace('שבץ ', 'שבץ מחדש ')
      : assignActionLabel(selection, PICKER_LANGUAGE);

  return (
    <div className={styles.modalOverlay} onClick={close}>
      <div className={cx(styles.modalContent, styles.xwide)} onClick={(e) => e.stopPropagation()}>
        {/* 1. Header */}
        <div className={styles.modalHeaderModern}>
          <div className={styles.modalTitleWrap}>
            <div className={styles.modalIcon} style={{ background: 'linear-gradient(135deg, #10b981, #059669)' }}>
              <BedDouble size={18} />
            </div>
            <div>
              <h3>{student.is_assigned ? t.reassignModalTitle : t.assignModalTitle}</h3>
              <div className={styles.assignStudentMeta}>
                {getName(student)} · {student.student_id}
              </div>
            </div>
          </div>
          <button type="button" className={styles.modalClose} onClick={close} aria-label={t.assignModalClose}><X size={20} /></button>
        </div>

        {/* 2. Student / current-assignment information */}
        {student.is_assigned && (
          <div className={styles.currentAssignmentBanner}>
            <div className={styles.cabTitle}>
              <BedDouble size={13} />
              {t.currentAssignmentLine(
                student.assigned_building_number,
                student.assigned_apartment_number,
                student.assigned_room_name,
                student.current_bed_label
              )}
            </div>
            <div className={styles.cabNote}>
              <AlertTriangle size={13} /> {t.currentAssignmentNote}
            </div>
          </div>
        )}

        {/* Region scope - central admins may search a region other than the
            student's own home region (e.g. deliberate cross-region transfer);
            regional employees never see this and stay locked to their own
            authorized region on the backend regardless. */}
        {isCentralAdmin && (
          <div className={styles.assignRegionScope}>
            <span className={styles.assignRegionScopeLabel}>{t.searchRegionLabel}</span>
            <select
              value={regionOverride || student.region_id || ''}
              onChange={(e) => changeRegion(e.target.value)}
              disabled={loading}
            >
              {regions.map((r) => (
                <option key={r.id} value={r.id}>
                  {localizeRegionName(r, language)}
                  {sameId(r.id, student.region_id) ? t.homeRegionSuffix : ''}
                </option>
              ))}
            </select>
          </div>
        )}

        {/* 3-5. Summary, filters, recommended options, selected-option summary */}
        <div className={styles.assignModalBody}>
          {blockingField ? (
            // A student-level field (housing type / region / category /
            // eligibility) is missing or invalid - every candidate room would
            // fail for the exact same reason, so show one clear blocking
            // message instead of hundreds of repeated per-room conflicts.
            <div className={styles.assignBlockedBox}>
              <AlertTriangle size={28} />
              <p className={styles.assignBlockedTitle}>{t.assignBlockedTitle}</p>
              <p className={styles.assignBlockedMsg}>{error || t.assignBlockedHousingType}</p>
              <button
                type="button"
                className={styles.assignBlockedEditBtn}
                onClick={() => {
                  close();
                  onEditStudent(student);
                }}
              >
                <User size={14} /> {t.editStudentBtn}
              </button>
            </div>
          ) : (
            <BedMatchPicker
              buildings={buildings}
              totalBuildings={meta.total_buildings}
              totalApartments={meta.total_apartments}
              totalRooms={meta.total_rooms}
              totalValidBeds={meta.total_valid_beds}
              counts={meta.counts}
              dataIntegrity={meta.data_integrity}
              conflictExamples={meta.conflict_examples}
              loading={loading}
              loadingMore={loadingMore}
              hasMore={meta.has_more}
              onLoadMore={loadMore}
              loadMoreError={loadMoreError}
              selectedBedId={selection?.bed_id}
              onSelectBed={select}
              language={PICKER_LANGUAGE}
              error={error && buildings.length === 0 ? error : ''}
              onRetry={retry}
            />
          )}

          {!blockingField && error && buildings.length > 0 && <div className={cx(styles.msg, styles.errorMsg)}>{error}</div>}
          {success && <div className={cx(styles.msg, styles.successMsg)}>{success}</div>}
        </div>

        {/* 6. Sticky action footer */}
        <div className={styles.assignActionBar}>
          <button type="button" className={styles.btnSecondary} onClick={close} disabled={assigning}>{t.assignCancel}</button>
          <button
            type="button"
            className={styles.btnAssign}
            onClick={submit}
            disabled={assigning || !selection || !selection.is_selectable || !!success}
          >
            {assigning ? (
              <Loader2 size={16} className={styles.spinner} />
            ) : (
              <>
                <BedDouble size={16} />
                {confirmLabel}
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
