import React from 'react';
import { Calendar, LogOut, RefreshCw, UserCheck, UserPlus, type LucideIcon } from 'lucide-react';
import { cx } from '../../../shared/lib/classNames';
import type { StudentDetailView } from '../model';
import type { StudentsStrings } from '../StudentsPage.strings';
import { CATEGORY_META, fmtDate } from '../studentHelpers';
import styles from './StudentBadges.module.css';

const CATEGORY_ICONS: Readonly<Record<string, LucideIcon>> = {
  continuing: UserCheck,
  new: UserPlus,
  transfer: RefreshCw,
  leaving: LogOut,
};

type CategoryStudent = Pick<StudentDetailView, 'category' | 'category_display'>;

function categoryLabel(s: CategoryStudent, t: StudentsStrings): string {
  switch (s.category) {
    case 'continuing': return t.catContinuing;
    case 'new': return t.catNew;
    case 'transfer': return t.catTransfer;
    case 'leaving': return t.catLeaving;
    default: return s.category_display || s.category;
  }
}

/** The coloured category pill (staying / new / transfer / leaving). */
export function CategoryBadge({ student, t }: { student: CategoryStudent; t: StudentsStrings }): React.ReactElement | null {
  const meta = CATEGORY_META[student.category];
  const Icon = CATEGORY_ICONS[student.category];
  if (!meta || !Icon) return null;
  return (
    <span className={cx(styles.catPill, styles[meta.color])}>
      <Icon size={12} />{categoryLabel(student, t)}
    </span>
  );
}

type DatedStudent = Pick<StudentDetailView, 'category'> & Partial<Pick<StudentDetailView, 'move_in_date' | 'move_out_date'>>;

/** The move-in / move-out date chip that matters for the student's category. */
export function RelevantDateChip({ student, t }: { student: DatedStudent; t: StudentsStrings }): React.ReactElement | null {
  const meta = CATEGORY_META[student.category];
  if (!meta) return null;
  const date = student[meta.dateKey];
  if (!date) return null;
  return (
    <span className={styles.dateChip}>
      <Calendar size={11} />
      {t[meta.dateLabelKey]}: <strong>{fmtDate(date)}</strong>
    </span>
  );
}

/** The "Left: <date>" chip of a removed student. */
export function RemovedDateChip({ date, t }: { date: string; t: StudentsStrings }): React.ReactElement {
  return (
    <span className={cx(styles.dateChip, styles.removedDate)}>
      <LogOut size={11} /> {t.leftOn} <strong>{fmtDate(date)}</strong>
    </span>
  );
}
