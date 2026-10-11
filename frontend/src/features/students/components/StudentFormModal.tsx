import React from 'react';
import { User } from 'lucide-react';
import type { FieldErrors, Region } from '../../../shared/api/contracts';
import type { Language } from '../../../shared/i18n';
import { cx } from '../../../shared/lib/classNames';
import { localizeDormTypeName, localizeRegionName } from '../../../shared/lib/locationNames';
import type { AddStudentMode, StudentFormField, StudentFormValues } from '../model';
import type { StudentsStrings } from '../StudentsPage.strings';
import { fieldErrorText } from '../studentHelpers';
import type { DormTypeFilterOption, StudentFilterOption } from '../types';
import styles from './StudentModals.module.css';

export interface StudentFormModalProps {
  t: StudentsStrings;
  language: Language;
  /** "add" creates a student (POST); "edit" saves changes to an existing one (PATCH). */
  mode: 'add' | 'edit';
  isCentralAdmin: boolean;
  /** The signed-in regional user's region name, shown read-only instead of the region select. */
  userRegionName: string | null | undefined;
  /** The regions a central admin can pick from. */
  regions: Region[];
  dormTypeOptions: DormTypeFilterOption[];
  housingTypes: StudentFilterOption[];
  /** The existing student's number, shown read-only in edit mode. */
  existingStudentId?: string;
  form: StudentFormValues;
  fieldErrors: FieldErrors;
  error: string;
  success: string;
  loading: boolean;
  onFieldChange: (field: StudentFormField, value: string) => void;
  onClose: () => void;
  onSubmit: (mode: AddStudentMode) => void;
}

/** The Add Student / Edit Student modal: identity, contact, housing/placement and notes. */
export function StudentFormModal({
  t, language, mode, isCentralAdmin, userRegionName, regions, dormTypeOptions, housingTypes,
  existingStudentId, form, fieldErrors, error, success, loading, onFieldChange, onClose, onSubmit,
}: StudentFormModalProps): React.ReactElement {
  const isEdit = mode === 'edit';

  const fieldError = (field: StudentFormField): React.ReactElement | null =>
    fieldErrors[field] ? (
      <span className={styles.fieldErrorMsg}>{fieldErrorText(fieldErrors[field])}</span>
    ) : null;
  const labelClass = (field: StudentFormField): string | undefined =>
    fieldErrors[field] ? styles.fieldError : undefined;

  return (
    <div className={styles.modalOverlay} onClick={onClose}>
      <div
        className={cx(styles.modalContent, styles.xwide, styles.addStudentModal)}
        dir={language === 'he' ? 'rtl' : undefined}
        onClick={(e) => e.stopPropagation()}
      >
        <div className={styles.modalHeader}>
          <div className={styles.modalTitleRow}>
            <div className={cx(styles.modalIcon, styles.blue)}>{isEdit ? <User size={18} /> : '+'}</div>
            <div>
              <h2>{isEdit ? t.editStudentTitle : t.createAddStudentRequest}</h2>
              <p className={styles.modalSubtitle}>{isEdit ? t.editStudentSubtitle : t.addStudentSubtitle}</p>
            </div>
          </div>
          <button type="button" className={styles.modalClose} onClick={onClose}>×</button>
        </div>

        <div className={styles.modalBody}>
          {error && <div className={cx(styles.formAlert, styles.error)}>{error}</div>}
          {success && <div className={cx(styles.formAlert, styles.success)}>{success}</div>}

          <section className={styles.modalSection}>
            <h3>{t.studentIdentity}</h3>
            <div className={styles.formGrid}>
              {isEdit ? (
                <label>
                  {t.studentId}
                  <input value={existingStudentId || ''} disabled />
                </label>
              ) : (
                <label className={labelClass('student_id')}>
                  {t.studentId} *
                  <input
                    value={form.student_id}
                    onChange={(e) => onFieldChange('student_id', e.target.value)}
                    placeholder={t.studentIdExample}
                  />
                  {fieldError('student_id')}
                </label>
              )}

              <label className={labelClass('first_name')}>
                {t.firstName} *
                <input value={form.first_name} onChange={(e) => onFieldChange('first_name', e.target.value)} />
                {fieldError('first_name')}
              </label>

              <label className={labelClass('last_name')}>
                {t.lastName} *
                <input value={form.last_name} onChange={(e) => onFieldChange('last_name', e.target.value)} />
                {fieldError('last_name')}
              </label>
            </div>
          </section>

          <section className={styles.modalSection}>
            <h3>{t.contactInfo}</h3>
            <div className={styles.formGrid}>
              <label>
                {t.phone}
                <input value={form.phone} onChange={(e) => onFieldChange('phone', e.target.value)} />
              </label>

              <label className={labelClass('email')}>
                {t.email}
                <input type="email" value={form.email} onChange={(e) => onFieldChange('email', e.target.value)} />
                {fieldError('email')}
              </label>

              <label>
                {t.city}
                <input value={form.city} onChange={(e) => onFieldChange('city', e.target.value)} />
              </label>
            </div>
          </section>

          <section className={styles.modalSection}>
            <h3>{t.housingPlacement}</h3>

            {/* Central admin picks a region explicitly, loaded from the real
                regions API (never hardcoded); regional staff see their own
                region as a fixed, read-only value. */}
            {isCentralAdmin ? (
              <div className={styles.formGrid}>
                <label className={labelClass('region')}>
                  {t.region} *
                  <select value={form.region} onChange={(e) => onFieldChange('region', e.target.value)}>
                    <option value="">{t.selectRegion}</option>
                    {regions.map((r) => (
                      <option key={r.id} value={r.id}>{localizeRegionName(r, language)}</option>
                    ))}
                  </select>
                  {fieldError('region')}
                </label>
              </div>
            ) : (
              <div className={styles.readonlyRegionBadge}>
                {t.myRegionLabel}: <strong>{userRegionName || '—'}</strong>
              </div>
            )}

            <div className={styles.formGrid}>
              <label className={labelClass('gender')}>
                {t.gender} *
                <select value={form.gender} onChange={(e) => onFieldChange('gender', e.target.value)}>
                  <option value="">{t.selectGender}</option>
                  <option value="male">{t.male}</option>
                  <option value="female">{t.female}</option>
                </select>
                {fieldError('gender')}
              </label>

              <label>
                {t.religion}
                <select value={form.requested_religion} onChange={(e) => onFieldChange('requested_religion', e.target.value)}>
                  <option value="not_specified">{t.notSpecified}</option>
                  <option value="Jewish">{t.jewish}</option>
                  <option value="Muslims">{t.muslims}</option>
                  <option value="Christian">{t.christian}</option>
                  <option value="Druze">{t.druze}</option>
                </select>
              </label>

              <label className={labelClass('accepted_dorm_type')}>
                {t.dormType} *
                <select
                  value={form.accepted_dorm_type}
                  onChange={(e) => onFieldChange('accepted_dorm_type', e.target.value)}
                  disabled={isCentralAdmin && !form.region}
                >
                  <option value="">
                    {isCentralAdmin && !form.region ? t.selectRegionFirst : t.selectDormType}
                  </option>
                  {dormTypeOptions.map((dt) => (
                    <option key={dt.id} value={dt.id}>{localizeDormTypeName(dt, language)}</option>
                  ))}
                </select>
                {fieldError('accepted_dorm_type')}
              </label>

              <label>
                {t.category}
                <select value={form.category} onChange={(e) => onFieldChange('category', e.target.value)}>
                  <option value="new">{t.newCategory}</option>
                  <option value="continuing">{t.stayingCategory}</option>
                  <option value="transfer">{t.transferringCategory}</option>
                  <option value="leaving">{t.leavingCategory}</option>
                </select>
              </label>

              {/* Only required for students actually eligible for assignment -
                  a leaving student is exempt (mirrors the backend's
                  Student.is_assignment_eligible check). Choices are loaded
                  from Student.HousingType on the backend, never guessed from
                  gender - the employee must pick the real value. */}
              {form.category !== 'leaving' && (
                <label className={labelClass('housing_type')}>
                  {t.housingType} *
                  <select value={form.housing_type} onChange={(e) => onFieldChange('housing_type', e.target.value)}>
                    <option value="">{t.selectHousingType}</option>
                    {housingTypes.map((h) => (
                      <option key={h.id} value={h.id}>{h.name}</option>
                    ))}
                  </select>
                  {fieldError('housing_type')}
                </label>
              )}
            </div>
          </section>

          {!isEdit && (
            <section className={styles.modalSection}>
              <h3>{t.requestReason}</h3>
              <label>
                {t.reason}
                <textarea
                  value={form.reason}
                  onChange={(e) => onFieldChange('reason', e.target.value)}
                  rows={3}
                  placeholder={t.addStudentReasonPlaceholder}
                />
              </label>
            </section>
          )}
        </div>

        <div className={styles.modalFooter}>
          <button type="button" className={styles.secondaryBtn} onClick={onClose} disabled={loading}>
            {t.cancel}
          </button>
          {isEdit ? (
            <button type="button" className={styles.primaryBtn} onClick={() => onSubmit('save')} disabled={loading}>
              {loading ? t.creating : t.saveEditStudentBtn}
            </button>
          ) : (
            <>
              <button type="button" className={styles.secondaryBtn} onClick={() => onSubmit('save')} disabled={loading}>
                {loading ? t.creating : t.createAddStudentBtn}
              </button>
              <button type="button" className={styles.primaryBtn} onClick={() => onSubmit('save_and_match')} disabled={loading}>
                {loading ? t.creating : t.saveAndMatchBtn}
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
