import React from 'react';
import { AlertTriangle, UserMinus } from 'lucide-react';
import type { Language } from '../../../shared/i18n';
import { cx } from '../../../shared/lib/classNames';
import StudentSearch from '../../students/StudentSearch';
import { useRemoveWizard } from '../hooks/useRemoveWizard';
import type { WizardStudent } from '../model';
import { buildRemovePayload } from '../transferHelpers';
import type { TransfersStrings } from '../TransfersPage.strings';
import type { StudentRequestPayload } from '../types';
import styles from './NewRequestModal.module.css';
import { AssignmentPanel, PickedBar, WizardBar, WizardField, WizardFooter } from './WizardChrome';

export interface RemoveWizardProps {
  t: TransfersStrings;
  language: Language;
  submitting: boolean;
  error: string;
  onSubmit: (payload: StudentRequestPayload) => void;
  onCancel: () => void;
}

/** Removal request: pick an assigned student, review the placement, reason, confirm. */
export function RemoveWizard({ t, language, submitting, error, onSubmit, onCancel }: RemoveWizardProps): React.ReactElement {
  const w = useRemoveWizard();
  const { step, student, setStudent, reason, setReason } = w;
  const steps = t.removeSteps;

  return (
    <div className={styles.wzRoot}>
      <WizardBar steps={steps} current={step} colorKey="rose" />
      <div className={styles.wzContent}>
        {step === 0 && (<>
          <h3 className={styles.wzTitle}>{t.removeStep0Title}</h3>
          {student
            ? <PickedBar student={student} onClear={() => setStudent(null)} />
            : <StudentSearch onPick={setStudent} filter={(s: WizardStudent) => s.is_assigned} placeholder={t.studentSearchPlaceholder} language={language} />}
        </>)}
        {step === 1 && student && (<>
          <h3 className={styles.wzTitle}>{t.removeStep1Title}</h3>
          <AssignmentPanel t={t} student={student} tone="rose" />
          <div className={cx(styles.wzNote, styles.roseNote)}><AlertTriangle size={13} /> {t.removeNote}</div>
        </>)}
        {step === 2 && (<>
          <h3 className={styles.wzTitle}>{t.removeStep2Title}</h3>
          <WizardField label={t.labelReason} required>
            <textarea rows={4} value={reason} onChange={(e) => setReason(e.target.value)} placeholder={t.removeReasonPlaceholder} />
          </WizardField>
        </>)}
        {step === 3 && (<>
          <h3 className={styles.wzTitle}>{t.removeStep3Title}</h3>
          <div className={styles.wzSummary}>
            <div className={styles.sumRow}><span className={styles.sumK}>{t.summaryStudent}</span><span className={styles.sumV}>{student?.full_name}</span></div>
            <div className={styles.sumRow}><span className={styles.sumK}>{t.summaryIdShort}</span><span className={cx(styles.sumV, styles.mono)}>{student?.student_id}</span></div>
            <div className={styles.sumRow}><span className={styles.sumK}>{t.summaryPlacement}</span><span className={styles.sumV}>{t.loc3(student?.current_building, student?.current_apartment, student?.current_room)}</span></div>
            <div className={styles.sumRow}><span className={styles.sumK}>{t.summaryReason}</span><span className={styles.sumV}>{reason}</span></div>
          </div>
          {error && <div className={styles.wzErr}>{error}</div>}
        </>)}
      </div>
      <WizardFooter
        t={t}
        language={language}
        step={step}
        stepsCount={steps.length}
        colorKey="rose"
        canNext={w.canNext}
        submitting={submitting}
        submitIcon={<UserMinus size={13} />}
        submitLabel={t.confirmRemoveBtn}
        onCancel={onCancel}
        onBack={w.back}
        onNext={w.next}
        onSubmit={() => onSubmit(buildRemovePayload(student, reason))}
      />
    </div>
  );
}
