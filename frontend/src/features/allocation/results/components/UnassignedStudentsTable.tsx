import React, { type ReactNode } from 'react';
import type { Language } from '../../../../shared/i18n';
import { cx } from '../../../../shared/lib/classNames';
import { localizeGender } from '../../../../shared/lib/genderLabels';
import type { AllocationResultsStrings } from '../AllocationResultsPage.strings';
import type { UnassignedStudentRow } from '../model';
import { EmptyState } from './ResultsStates';
import styles from './ResultsTables.module.css';

export interface UnassignedStudentsTableProps {
  t: AllocationResultsStrings;
  language: Language;
  students: UnassignedStudentRow[];
  /** The unassigned analysis, rendered inside the empty state or above the table. */
  analysis: ReactNode;
}

/** The students the run could not place, one row each, with the analysis above them. */
export function UnassignedStudentsTable({
  t, language, students, analysis,
}: UnassignedStudentsTableProps): React.ReactElement {
  if (students.length === 0) {
    return (
      <EmptyState text={t.noUnassignedStudents}>
        {analysis}
      </EmptyState>
    );
  }

  return (
    <div className={styles.tableWrap}>
      {analysis}
      <table className={cx(styles.resultsTable, styles.unassignedTable)}>
        <thead>
          <tr>
            <th>{t.student}</th>
            <th>{t.studentId}</th>
            <th>{t.gender}</th>
            <th>{t.housingType}</th>
            <th>{t.acceptedDormType}</th>
            <th>{t.religion}</th>
            <th>{t.religiousLevel}</th>
            <th>{t.sector}</th>
            <th>{t.priority}</th>
            <th>{t.specialStatuses}</th>
            <th>{t.reason}</th>
          </tr>
        </thead>

        <tbody>
          {students.map((student, index) => (
            <tr key={`${student?.student_id || 'unassigned'}-${index}`}>
              <td>
                {student?.student_name || student?.full_name || '-'}
              </td>

              <td>
                {student?.student_id || '-'}
              </td>

              <td>
                {localizeGender(student?.gender, language) || student?.gender_display || '-'}
              </td>

              <td>
                {student?.housing_type_display || student?.housing_type || '-'}
              </td>

              <td>
                {student?.accepted_dorm_type || '-'}
              </td>

              <td>
                {student?.religion_display || student?.requested_religion || student?.religion || '-'}
              </td>

              <td>
                {student?.religious || '-'}
              </td>

              <td>
                {student?.placement_sector_display || student?.placement_sector || student?.sector || '-'}
              </td>

              <td>
                <span className={cx(styles.booleanChip, student?.is_priority && styles.active)}>
                  {student?.is_priority ? t.yes : t.no}
                </span>
              </td>

              <td>
                {Array.isArray(student?.special_statuses) && student.special_statuses.length > 0
                  ? student.special_statuses.join(', ')
                  : '-'}
              </td>

              <td>
                {student?.unassigned_reason || '-'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
