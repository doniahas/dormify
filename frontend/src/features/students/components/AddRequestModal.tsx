import React from 'react';
import { FileText, Loader2, MapPin, Plus, UserMinus, X } from 'lucide-react';
import type { Language } from '../../../shared/i18n';
import { cx } from '../../../shared/lib/classNames';
import { localizeRegionName } from '../../../shared/lib/locationNames';
import type { AddRequestModalState } from '../hooks/useAddRequestModal';
import type { StudentDetailView, StudentRequestKind, StudentTransferScope } from '../model';
import type { StudentsStrings } from '../StudentsPage.strings';
import { getInitial, getName } from '../studentHelpers';
import styles from './StudentModals.module.css';

export interface AddRequestModalProps {
  t: StudentsStrings;
  language: Language;
  student: StudentDetailView;
  isCentralAdmin: boolean;
  /** The signed-in regional user's region name, shown on the locked-scope note. */
  userRegionName: string | null | undefined;
  state: AddRequestModalState;
}

interface TypeOption {
  v: StudentRequestKind;
  l: string;
  icon: React.ReactElement;
  color: 'purple' | 'orange';
}

interface ScopeOption {
  v: StudentTransferScope;
  l: string;
  centralOnly?: boolean;
}

/** New request for an assigned student: transfer (with scope), other, or removal. */
export function AddRequestModal({
  t, language, student, isCentralAdmin, userRegionName, state,
}: AddRequestModalProps): React.ReactElement {
  const {
    close, reqType, setReqType, reqScope, setReqScope, reqTargetRegion, selectTargetRegion,
    regions, reqOtherDesc, setReqOtherDesc, reqReason, setReqReason,
    submitting, error, success, disabledReason, canSubmit, submit,
  } = state;

  const typeOptions: TypeOption[] = [
    { v: 'transfer', l: t.typeTransfer, icon: <MapPin size={20} />,   color: 'purple' },
    { v: 'other',    l: t.typeOther,    icon: <FileText size={20} />, color: 'orange' },
  ];
  const scopeOptions: ScopeOption[] = [
    { v: 'same_apartment', l: t.scopeSameApt },
    { v: 'same_region',    l: t.scopeSameRegion },
    { v: 'cross_region',   l: t.scopeCrossRegion, centralOnly: true },
  ];
  const disabledHint: Partial<Record<NonNullable<typeof disabledReason>, string>> = {
    'empty-reason': t.missingReason,
    'no-scope': t.missingScope,
    'invalid-target-region': t.missingTargetRegion,
    'empty-other-description': t.missingOtherDesc,
  };

  return (
    <div className={styles.modalOverlay} onClick={close}>
      <div className={styles.modalContent} onClick={(e) => e.stopPropagation()}>
        <div className={styles.modalHeaderModern}>
          <div className={styles.modalTitleWrap}>
            <div className={styles.modalIcon}><Plus size={18} /></div>
            <h3>{t.newRequestTitle}</h3>
          </div>
          <button type="button" className={styles.modalClose} onClick={close}><X size={20} /></button>
        </div>
        <div className={styles.modalBody}>
          <div className={styles.selectedStudentPill}>
            <div className={styles.miniAvatar}>{getInitial(student)}</div>
            <div><div className={styles.ssName}>{getName(student)}</div><div className={cx(styles.ssMeta, styles.mono)}>{student.student_id}</div></div>
          </div>

          <div className={styles.formSection}>
            <label>{t.requestType}</label>
            {/* Primary types */}
            <div className={styles.typeOptionsModern} style={{ marginBottom: 10 }}>
              {typeOptions.map((opt) => (
                <button key={opt.v} type="button"
                  className={cx(styles.typeOptionModern, styles[opt.color], reqType === opt.v && styles.active)}
                  onClick={() => setReqType(opt.v)}>
                  <div className={styles.optIcon}>{opt.icon}</div>
                  <span>{opt.l}</span>
                </button>
              ))}
            </div>
            {/* Remove student */}
            <button type="button"
              className={cx(styles.typeOptionSpecial, styles.red, styles.fullWidth, reqType === 'remove_student' && styles.active)}
              onClick={() => setReqType('remove_student')}>
              <div className={styles.optIconSm}><UserMinus size={18} /></div>
              <span>{t.typeRemoveStudent}</span>
            </button>
          </div>

          {reqType === 'remove_student' && (
            <div className={cx(styles.typeNote, styles.red)}><UserMinus size={14} /> {t.removeStudentNote}</div>
          )}

          {reqType === 'transfer' && (
            <div className={styles.formSection}>
              <label>{t.scopeLabel}</label>
              <div className={styles.subOptions}>
                {scopeOptions.map((opt) => (
                  <button key={opt.v} type="button"
                    className={cx(styles.subOption, reqScope === opt.v && styles.active)}
                    disabled={opt.centralOnly && !isCentralAdmin}
                    title={opt.centralOnly && !isCentralAdmin ? t.centralOnlyCross : undefined}
                    onClick={() => setReqScope(opt.v)}>{opt.l}</button>
                ))}
              </div>
              {!isCentralAdmin && (
                <div className={styles.typeNote} style={{ marginTop: 8 }}>
                  <MapPin size={14} /> {t.crossRegionLockedNote}
                  {userRegionName ? <>: <strong>{userRegionName}</strong></> : null}
                </div>
              )}
              {reqScope === 'cross_region' && isCentralAdmin && (
                <div style={{ marginTop: 10 }}>
                  <label>{t.targetRegionLabel} *</label>
                  {regions.length === 0 ? (
                    <div className={styles.typeNote} style={{ marginTop: 6 }}>
                      <Loader2 size={14} className={styles.spinner} /> {t.selectTargetRegion}...
                    </div>
                  ) : (
                    <div style={{
                      display: 'flex', flexDirection: 'column', gap: 6,
                      maxHeight: 170, overflowY: 'auto', marginTop: 6,
                      border: '1px solid #e5e7eb', borderRadius: 10, padding: 6,
                      pointerEvents: 'auto', position: 'relative', zIndex: 1,
                    }}>
                      {regions.map((r, idx) => {
                        // Region PK is kept RAW and compared as a string - never
                        // coerced with Number() (NaN made clicks look like they
                        // did nothing).
                        const rid = r.id;
                        if (rid == null) return null;
                        const active = String(reqTargetRegion) === String(rid);
                        const isCurrent = student.region_name === r.name;
                        return (
                          <button key={String(rid) || idx} type="button"
                            className={cx(styles.subOption, active && styles.active)}
                            style={{
                              width: '100%', justifyContent: 'space-between',
                              display: 'flex', alignItems: 'center',
                              cursor: 'pointer', pointerEvents: 'auto',
                            }}
                            onClick={(e) => {
                              e.stopPropagation();
                              selectTargetRegion(rid);
                            }}>
                            <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                              <MapPin size={13} /> {localizeRegionName(r, language)}
                            </span>
                            <span style={{ fontSize: 11, opacity: 0.7 }}>
                              {isCurrent ? t.currentRegionTag : ''}
                              {active ? ' ✓' : ''}
                            </span>
                          </button>
                        );
                      })}
                    </div>
                  )}
                  {reqTargetRegion == null && (
                    <div className={styles.msg} style={{ marginTop: 6, fontSize: 12, color: '#92400e' }}>
                      {t.missingTargetRegion}
                    </div>
                  )}
                </div>
              )}
            </div>
          )}

          {reqType === 'other' && (
            <div className={styles.formSection}>
              <label>{t.otherDescLabel}</label>
              <textarea rows={2} placeholder={t.otherDescPlaceholder} value={reqOtherDesc} onChange={(e) => setReqOtherDesc(e.target.value)} />
            </div>
          )}

          <div className={styles.formSection}>
            <label>{t.reasonLabel}</label>
            <textarea rows={4}
              placeholder={reqType === 'remove_student' ? t.removeReasonPlaceholder : t.reasonPlaceholder}
              value={reqReason} onChange={(e) => setReqReason(e.target.value)} />
          </div>

          {error && <div className={cx(styles.msg, styles.errorMsg)}>{error}</div>}
          {success && <div className={cx(styles.msg, styles.successMsg)}>{success}</div>}
          {!error && !success && !canSubmit && !submitting && (
            <div className={styles.msg} style={{ background: '#fef3c7', color: '#92400e', fontSize: 13 }}>
              {(disabledReason && disabledHint[disabledReason]) || ''}
            </div>
          )}

          <div className={styles.modalActions}>
            <button type="button" className={styles.btnSecondary} onClick={close} disabled={submitting}>{t.cancel}</button>
            <button
              type="button"
              className={cx(styles.btnPrimary, reqType === 'remove_student' && styles.danger)}
              onClick={submit}
              disabled={!canSubmit}>
              {submitting ? <Loader2 size={16} className={styles.spinner} /> : <><Plus size={16} /> {t.submit}</>}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
