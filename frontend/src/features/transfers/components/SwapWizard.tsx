import React from 'react';
import { AlertTriangle, RefreshCw } from 'lucide-react';
import type { Language } from '../../../shared/i18n';
import { cx } from '../../../shared/lib/classNames';
import StudentSearch from '../../students/StudentSearch';
import { useSwapWizard } from '../hooks/useSwapWizard';
import type { WizardStudent } from '../model';
import { buildSwapPayload } from '../transferHelpers';
import type { TransfersStrings } from '../TransfersPage.strings';
import type { StudentRequestPayload } from '../types';
import styles from './NewRequestModal.module.css';
import { AssignmentPanel, PickedBar, WizardBar, WizardField, WizardFooter } from './WizardChrome';

export interface SwapWizardProps {
  t: TransfersStrings;
  language: Language;
  submitting: boolean;
  error: string;
  onSubmit: (payload: StudentRequestPayload) => void;
  onCancel: () => void;
}

/** Swap request: two assigned students trade their current beds/rooms. */
export function SwapWizard({ t, language, submitting, error, onSubmit, onCancel }: SwapWizardProps): React.ReactElement {
  const w = useSwapWizard();
  const { step, studentA, setStudentA, studentB, setStudentB, reason, setReason } = w;
  const steps = t.swapSteps;

  return (
    <div className={styles.wzRoot}>
      <WizardBar steps={steps} current={step} colorKey="indigo" />
      <div className={styles.wzContent}>
        {step === 0 && (<>
          <h3 className={styles.wzTitle}>{t.swapStep0Title}</h3>
          {studentA
            ? <PickedBar student={studentA} onClear={() => setStudentA(null)} />
            : <StudentSearch onPick={setStudentA} filter={(s: WizardStudent) => s.is_assigned} placeholder={t.studentSearchPlaceholder} language={language} />}
          {studentA && <div style={{ marginTop: 12 }}><AssignmentPanel t={t} student={studentA} tone="violet" /></div>}
        </>)}
        {step === 1 && (<>
          <h3 className={styles.wzTitle}>{t.swapStep1Title}</h3>
          {studentB
            ? <PickedBar student={studentB} onClear={() => setStudentB(null)} />
            : <StudentSearch onPick={setStudentB} filter={(s: WizardStudent) => s.is_assigned && s.id !== studentA?.id} placeholder={t.studentSearchPlaceholder} language={language} />}
          {studentB && <div style={{ marginTop: 12 }}><AssignmentPanel t={t} student={studentB} tone="violet" /></div>}
          {studentB && studentB.id === studentA?.id && (
            <div className={cx(styles.wzNote, styles.roseNote)}><AlertTriangle size={13} /> {t.swapDifferentStudents}</div>
          )}
        </>)}
        {step === 2 && (<>
          <h3 className={styles.wzTitle}>{t.swapStep2Title}</h3>
          <WizardField label={t.labelReason} required>
            <textarea rows={4} value={reason} onChange={(e) => setReason(e.target.value)} placeholder={t.swapReasonPlaceholder} />
          </WizardField>
        </>)}
        {step === 3 && (<>
          <h3 className={styles.wzTitle}>{t.swapStep3Title}</h3>
          <div className={styles.wzSummary}>
            <div className={styles.sumRow}><span className={styles.sumK}>{t.summaryStudentA}</span><span className={styles.sumV}>{studentA?.full_name} · {t.loc3(studentA?.current_building, studentA?.current_apartment, studentA?.current_room)}</span></div>
            <div className={styles.sumRow}><span className={styles.sumK}>{t.summaryStudentB}</span><span className={styles.sumV}>{studentB?.full_name} · {t.loc3(studentB?.current_building, studentB?.current_apartment, studentB?.current_room)}</span></div>
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
        colorKey="indigo"
        canNext={w.canNext}
        submitting={submitting}
        submitIcon={<RefreshCw size={13} />}
        submitLabel={t.submitSwapBtn}
        onCancel={onCancel}
        onBack={w.back}
        onNext={w.next}
        onSubmit={() => onSubmit(buildSwapPayload(studentA, studentB, reason))}
      />
    </div>
  );
}
