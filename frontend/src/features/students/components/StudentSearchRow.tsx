import React from 'react';
import { Filter, Loader2, Search, X } from 'lucide-react';
import { cx } from '../../../shared/lib/classNames';
import type { StudentsStrings } from '../StudentsPage.strings';
import styles from '../StudentsPage.module.css';

export interface StudentSearchRowProps {
  t: StudentsStrings;
  searchQuery: string;
  onSearchChange: (query: string) => void;
  loading: boolean;
  listTotal: number;
  activeFilterCount: number;
  onOpenFilters: () => void;
}

/** The search box, the matching-students counter and the Filters button. */
export function StudentSearchRow({
  t, searchQuery, onSearchChange, loading, listTotal, activeFilterCount, onOpenFilters,
}: StudentSearchRowProps): React.ReactElement {
  return (
    <div className={styles.searchRow}>
      <div className={styles.searchBox}>
        <Search size={20} className={styles.searchIcon} />
        <input
          type="text"
          placeholder={t.placeholder}
          value={searchQuery}
          onChange={(e) => onSearchChange(e.target.value)}
        />
        {loading && <Loader2 size={18} className={styles.spinner} />}
        {searchQuery && !loading && (
          <button type="button" className={styles.clearBtn} onClick={() => onSearchChange('')}><X size={16} /></button>
        )}
      </div>
      <button className={styles.matchingStudentsBtn} type="button">
        <span className={styles.matchingNumber}>{listTotal}</span>
        <span className={styles.matchingText}>{t.matchingStudents}<small>{t.matchingSubtitle}</small></span>
      </button>
      <button
        type="button"
        className={cx(styles.filtersBtn, activeFilterCount > 0 && styles.hasFilters)}
        onClick={onOpenFilters}
      >
        <Filter size={16} />{t.filters}
        {activeFilterCount > 0 && <span className={styles.filterBadge}>{activeFilterCount}</span>}
      </button>
    </div>
  );
}
