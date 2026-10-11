import React from 'react';
import { FileSearch, Loader2, Star } from 'lucide-react';
import type { StudentSummary } from '../../../shared/api/contracts';
import { cx } from '../../../shared/lib/classNames';
import type { StudentRow } from '../model';
import type { StudentsStrings } from '../StudentsPage.strings';
import { getInitial, getName, isRemoved } from '../studentHelpers';
import styles from '../StudentsPage.module.css';
import { CategoryBadge, RelevantDateChip, RemovedDateChip } from './StudentBadges';

export interface StudentListProps {
  t: StudentsStrings;
  loading: boolean;
  error: string;
  list: StudentRow[];
  hasMore: boolean;
  loadingMore: boolean;
  onLoadMore: () => void;
  onSelect: (student: StudentSummary) => void;
  onClearFilters: () => void;
}

const SKELETON_ROWS = 8;

/** The result rows, with their loading skeleton, empty card, error box and "load more". */
export function StudentList({
  t, loading, error, list, hasMore, loadingMore, onLoadMore, onSelect, onClearFilters,
}: StudentListProps): React.ReactElement {
  return (
    <>
      {error && <div className={styles.errorBox}>{error}</div>}

      {!loading && list.length === 0 && !error ? (
        <div className={styles.emptyCard}>
          <div className={styles.emptyIllustration}><FileSearch size={64} /></div>
          <h3>{t.noResults}</h3>
          <p>{t.noResultsHint}</p>
          <button type="button" className={styles.clearFiltersBtn} onClick={onClearFilters}>{t.clearFilters}</button>
        </div>
      ) : loading ? (
        <div className={styles.resultsGrid} aria-busy="true">
          {Array.from({ length: SKELETON_ROWS }).map((_, i) => (
            <div key={i} className={styles.resultRowSkeleton}>
              <div className={styles.skelAvatar} />
              <div className={styles.skelLines}>
                <div className={cx(styles.skelLine, styles.skelLineWide)} />
                <div className={cx(styles.skelLine, styles.skelLineNarrow)} />
              </div>
            </div>
          ))}
        </div>
      ) : list.length > 0 ? (
        <div className={styles.resultsGrid}>
          {list.map((s) => (
            <StudentListRow key={s.id} student={s} t={t} onSelect={onSelect} />
          ))}
        </div>
      ) : null}

      {!loading && hasMore && (
        <button
          type="button"
          className={styles.loadMoreStudentsBtn}
          onClick={onLoadMore}
          disabled={loadingMore}
        >
          {loadingMore ? <Loader2 size={16} className={styles.spinner} /> : t.loadMore}
        </button>
      )}
    </>
  );
}

function StudentListRow({
  student: s, t, onSelect,
}: { student: StudentRow; t: StudentsStrings; onSelect: (student: StudentSummary) => void }): React.ReactElement {
  const removed = isRemoved(s);
  return (
    <div className={cx(styles.resultRow, removed && styles.removed)} onClick={() => onSelect(s)}>
      <div className={cx(styles.avatar, removed && styles.removed)}>{getInitial(s)}</div>
      <div className={styles.rowInfo}>
        <div className={styles.rowName}>
          {getName(s)}
          {s.is_priority && <Star size={14} className={styles.priorityIcon} />}
          {removed && <span className={styles.removedBadge}>{t.removedBadge}</span>}
        </div>
        <div className={styles.rowMeta}>
          <span className={styles.mono}>{s.student_id}</span>
          {s.phone && <span>· {s.phone}</span>}
        </div>
        <div className={styles.rowBadges}>
          <CategoryBadge student={s} t={t} />
          <span className={cx(styles.statusBadge, s.is_assigned ? styles.assigned : styles.unassigned)}>
            {s.is_assigned ? t.assigned : t.unassigned}
          </span>
          <RelevantDateChip student={s} t={t} />
          {removed && s.move_out_date && <RemovedDateChip date={s.move_out_date} t={t} />}
        </div>
      </div>
    </div>
  );
}
