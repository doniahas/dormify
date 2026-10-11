import React from 'react';
import {
  ArrowLeft, ArrowRight, BedDouble, Building2, Check, DoorOpen, Home, X, type LucideIcon,
} from 'lucide-react';
import type { Language } from '../../../shared/i18n';
import { cx } from '../../../shared/lib/classNames';
import type { WizardColor, WizardStudent } from '../model';
import { getName } from '../transferHelpers';
import type { TransfersStrings } from '../TransfersPage.strings';
import styles from './NewRequestModal.module.css';
import { capitalize, Spinner } from './RequestAtoms';

/**
 * The directional "back"/"forward" arrows: Hebrew reads right-to-left so
 * "forward" points left and "back" points right; English mirrors this.
 */
export function directionalArrows(language: Language): { BackArrow: LucideIcon; NextArrow: LucideIcon } {
  const isHe = language === 'he';
  return { BackArrow: isHe ? ArrowRight : ArrowLeft, NextArrow: isHe ? ArrowLeft : ArrowRight };
}

export interface WizardBarProps {
  steps: string[];
  current: number;
  colorKey: WizardColor;
}

/** The wizard's progress bar: done / current / idle nodes joined by connectors. */
export function WizardBar({ steps, current, colorKey }: WizardBarProps): React.ReactElement {
  return (
    <div className={styles.wzBar}>
      {steps.map((s, i) => (
        <React.Fragment key={i}>
          <div className={cx(
            styles.wzNode,
            i < current ? styles.wzDone : i === current ? cx(styles.wzCur, styles[`wzCur${capitalize(colorKey)}`]) : styles.wzIdle
          )}>
            <div className={styles.wzCircle}>{i < current ? <Check size={10} /> : <span>{i + 1}</span>}</div>
            <span className={styles.wzLbl}>{s}</span>
          </div>
          {i < steps.length - 1 && <div className={cx(styles.wzConn, i < current && styles.wzConnDone)} />}
        </React.Fragment>
      ))}
    </div>
  );
}

export interface WizardFooterProps {
  t: TransfersStrings;
  language: Language;
  step: number;
  stepsCount: number;
  colorKey: WizardColor;
  canNext: boolean;
  submitting: boolean;
  /** The last step's submit button: its icon and label. */
  submitIcon: React.ReactElement;
  submitLabel: string;
  onCancel: () => void;
  onBack: () => void;
  onNext: () => void;
  onSubmit: () => void;
}

/** The wizard's footer: cancel/back, the step counter, next or submit. */
export function WizardFooter({
  t, language, step, stepsCount, colorKey, canNext, submitting,
  submitIcon, submitLabel, onCancel, onBack, onNext, onSubmit,
}: WizardFooterProps): React.ReactElement {
  const { BackArrow, NextArrow } = directionalArrows(language);
  const nextClass = cx(styles.wzNext, styles[`wz${capitalize(colorKey)}`]);
  return (
    <div className={styles.wzFooter}>
      <button type="button" className={styles.wzBack} onClick={step === 0 ? onCancel : onBack}>
        {step === 0 ? t.cancel : <><BackArrow size={13} /> {t.back}</>}
      </button>
      <span className={styles.wzProg}>{step + 1}/{stepsCount}</span>
      {step < stepsCount - 1
        ? <button type="button" className={nextClass} disabled={!canNext} onClick={onNext}>{t.next} <NextArrow size={13} /></button>
        : <button type="button" className={nextClass} disabled={submitting} onClick={onSubmit}>
            {submitting ? <Spinner size={13} /> : submitIcon} {submitLabel}
          </button>}
    </div>
  );
}

export interface PickedBarProps {
  student: WizardStudent;
  onClear: () => void;
}

/** The chosen student, with a clear button that returns to the search. */
export function PickedBar({ student, onClear }: PickedBarProps): React.ReactElement {
  const name = getName(student);
  return (
    <div className={styles.pickedBar}>
      <div className={styles.pbAva}>{(name[0] || '?').toUpperCase()}</div>
      <div className={styles.pbInfo}>
        <span className={styles.pbName}>{name}</span>
        <span className={cx(styles.pbId, styles.mono)}>{student?.student_id}</span>
      </div>
      <button type="button" className={styles.pbClear} onClick={onClear}><X size={12} /></button>
    </div>
  );
}

export interface AssignmentPanelProps {
  t: TransfersStrings;
  student: WizardStudent;
  tone: 'violet' | 'rose';
}

/** The student's current placement (building / apartment / room / bed). */
export function AssignmentPanel({ t, student, tone }: AssignmentPanelProps): React.ReactElement {
  return (
    <div className={cx(styles.assignmentPanel, tone === 'rose' ? styles.rosePanel : styles.violetPanel)}>
      <div className={styles.apRow}><Building2 size={13} /><span>{t.fieldBuilding}</span><strong>{student.current_building || t.dash}</strong></div>
      <div className={styles.apRow}><DoorOpen size={13} /><span>{t.fieldApartment}</span><strong>{student.current_apartment || t.dash}</strong></div>
      <div className={styles.apRow}><Home size={13} /><span>{t.fieldRoom}</span><strong>{student.current_room || t.dash}</strong></div>
      <div className={styles.apRow}><BedDouble size={13} /><span>{t.fieldBed}</span><strong>{student.current_bed || t.dash}</strong></div>
    </div>
  );
}

export interface WizardFieldProps {
  label: string;
  required?: boolean;
  children: React.ReactNode;
}

/** A labelled wizard field; the asterisk marks a required one. */
export function WizardField({ label, required, children }: WizardFieldProps): React.ReactElement {
  return (
    <div className={styles.wzField}>
      <label>{label}{required && <span className={styles.req}>*</span>}</label>
      {children}
    </div>
  );
}
