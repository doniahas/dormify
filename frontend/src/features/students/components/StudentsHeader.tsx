import React from 'react';
import type { StudentsStrings } from '../StudentsPage.strings';
import styles from '../StudentsPage.module.css';

export interface StudentsHeaderProps {
  t: StudentsStrings;
  /** Hides the results count while the list is loading. */
  loading: boolean;
  listTotal: number;
  onAddStudent: () => void;
}

/** Page title, the Add Student action and the server-side result count. */
export function StudentsHeader({ t, loading, listTotal, onAddStudent }: StudentsHeaderProps): React.ReactElement {
  return (
    <div className={styles.pageTop}>
      <div>
        <h1>{t.title}</h1>
        <p>{t.subtitle}</p>
      </div>

      <div className={styles.pageTopActions}>
        <button type="button" className={styles.addStudentPrimaryBtn} onClick={onAddStudent}>
          <span className={styles.addStudentPlus}>+</span>
          {t.addStudentRequest}
        </button>

        {!loading && (
          <span className={styles.resultsCount}>
            {listTotal} {listTotal === 1 ? t.result : t.results}
          </span>
        )}
      </div>
    </div>
  );
}
