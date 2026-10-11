import React from 'react';
import { Check } from 'lucide-react';
import type { Language } from '../../../shared/i18n';
import { useAddStudentWizard } from '../hooks/useAddStudentWizard';
import type { AddStudentField } from '../model';
import { buildAddStudentPayload } from '../transferHelpers';
import type { TransfersStrings } from '../TransfersPage.strings';
import type { StudentRequestPayload } from '../types';
import styles from './NewRequestModal.module.css';
import { WizardBar, WizardField, WizardFooter } from './WizardChrome';

export interface AddStudentWizardProps {
  t: TransfersStrings;
  language: Language;
  submitting: boolean;
  error: string;
  onSubmit: (payload: StudentRequestPayload) => void;
  onCancel: () => void;
}

interface SelectOption {
  v: string;
  l: string;
}

/** New student registration request: details, housing preferences, reason, summary. */
export function AddStudentWizard({ t, language, submitting, error, onSubmit, onCancel }: AddStudentWizardProps): React.ReactElement {
  const w = useAddStudentWizard();
  const { step, form: d, setField } = w;
  const steps = t.addSteps;

  const fld = (k: AddStudentField, lbl: string, type = 'text', req = false) => (
    <WizardField label={lbl} required={req}>
      <input type={type} value={d[k]} onChange={(e) => setField(k, e.target.value)} placeholder={lbl} />
    </WizardField>
  );
  const sel = (k: AddStudentField, lbl: string, opts: SelectOption[], req = false) => (
    <WizardField label={lbl} required={req}>
      <select value={d[k]} onChange={(e) => setField(k, e.target.value)}>
        <option value="">{t.selectPlaceholder}</option>
        {opts.map((o) => <option key={o.v} value={o.v}>{o.l}</option>)}
      </select>
    </WizardField>
  );

  const summary: Array<[string, string]> = [
    [t.summaryName, `${d.first_name} ${d.last_name}`], [t.summaryIdShort, d.student_id], [t.summaryPhone, d.phone || t.dash],
    [t.summaryEmail, d.email || t.dash], [t.summaryCity, d.city || t.dash],
    [t.summaryGender, d.gender === 'male' ? t.genderMale : d.gender === 'female' ? t.genderFemale : t.dash],
    [t.summaryReligion, d.religion || t.dash], [t.summaryDormType, d.dorm_type || t.dash], [t.summaryReason, d.reason],
  ];

  return (
    <div className={styles.wzRoot}>
      <WizardBar steps={steps} current={step} colorKey="blue" />
      <div className={styles.wzContent}>
        {step === 0 && (<>
          <h3 className={styles.wzTitle}>{t.addStep0Title}</h3>
          <div className={styles.wzG3}>{fld('student_id', t.labelId, 'text', true)}{fld('first_name', t.labelFirstName, 'text', true)}{fld('last_name', t.labelLastName, 'text', true)}</div>
          <div className={styles.wzG3}>{fld('phone', t.labelPhone, 'tel')}{fld('email', t.labelEmail, 'email')}{fld('city', t.labelCity)}</div>
        </>)}
        {step === 1 && (<>
          <h3 className={styles.wzTitle}>{t.addStep1Title}</h3>
          <div className={styles.wzG2}>
            {sel('gender', t.labelGender, [{ v: 'male', l: t.genderMale }, { v: 'female', l: t.genderFemale }], true)}
            {sel('religion', t.labelReligion, [{ v: 'Jewish', l: t.religionJewish }, { v: 'Muslims', l: t.religionMuslim }, { v: 'Christian', l: t.religionChristian }, { v: 'Druze', l: t.religionDruze }])}
            {sel('dorm_type', t.labelDormType, [{ v: 'couples', l: t.dormCouples }, { v: 'single', l: t.dormSingle }])}
          </div>
        </>)}
        {step === 2 && (<>
          <h3 className={styles.wzTitle}>{t.addStep2Title}</h3>
          <WizardField label={t.labelReason} required>
            <textarea rows={4} value={d.reason} onChange={(e) => setField('reason', e.target.value)} placeholder={t.addReasonPlaceholder} />
          </WizardField>
        </>)}
        {step === 3 && (<>
          <h3 className={styles.wzTitle}>{t.addStep3Title}</h3>
          <div className={styles.wzSummary}>
            {summary.map(([k, v]) => (
              <div key={k} className={styles.sumRow}>
                <span className={styles.sumK}>{k}</span><span className={styles.sumV}>{v}</span>
              </div>
            ))}
          </div>
          {error && <div className={styles.wzErr}>{error}</div>}
        </>)}
      </div>
      <WizardFooter
        t={t}
        language={language}
        step={step}
        stepsCount={steps.length}
        colorKey="blue"
        canNext={w.canNext}
        submitting={submitting}
        submitIcon={<Check size={13} />}
        submitLabel={t.submit}
        onCancel={onCancel}
        onBack={w.back}
        onNext={w.next}
        onSubmit={() => onSubmit(buildAddStudentPayload(d))}
      />
    </div>
  );
}
