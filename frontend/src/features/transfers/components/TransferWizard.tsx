import React from 'react';
import { Activity, Building2, Check, DoorOpen, Home, MapPin, Search } from 'lucide-react';
import type { Region } from '../../../shared/api/contracts';
import type { Language } from '../../../shared/i18n';
import { cx } from '../../../shared/lib/classNames';
import BedMatchPicker from '../../allocation/BedMatchPicker';
import StudentSearch from '../../students/StudentSearch';
import { useTransferWizard } from '../hooks/useTransferWizard';
import type {
  FeasibilityData, FeasibilityPreviewArgs, NewTransferScope, TransferWizardType, WizardStudent,
} from '../model';
import { bedLabelFor, filterRegionsByQuery, regionNamesFor, regionNamesOf } from '../transferHelpers';
import type { TransfersStrings } from '../TransfersPage.strings';
import type { StudentRequestPayload } from '../types';
import styles from './NewRequestModal.module.css';
import { Spinner } from './RequestAtoms';
import { PickedBar, WizardBar, WizardField, WizardFooter } from './WizardChrome';

export interface TransferWizardProps {
  t: TransfersStrings;
  language: Language;
  type: TransferWizardType;
  isCentralAdmin: boolean;
  /** The signed-in regional user's region name (the read-only target region). */
  userRegionName: string | null | undefined;
  /** The regions a central admin may pick as the cross-region destination. */
  regions: Region[];
  submitting: boolean;
  error: string;
  onSubmit: (payload: StudentRequestPayload) => void;
  onCancel: () => void;
  /** The feasibility preview of the "options" step. */
  feasData: FeasibilityData | null;
  checkingFeas: boolean;
  loadingMoreFeas: boolean;
  loadMoreFeasError: string;
  onCheckFeas: (args: FeasibilityPreviewArgs) => void;
  onClearFeas: () => void;
  onLoadMoreFeas: () => void;
}

interface ScopeOption {
  v: NewTransferScope;
  l: string;
  centralOnly?: boolean;
}

/**
 * Transfer request (room / apartment / cross-region) and, with fewer steps,
 * the "other" request: student, scope (+ destination region), details,
 * options (feasibility preview with the bed picker), confirm.
 */
export function TransferWizard({
  t, language, type, isCentralAdmin: central, userRegionName, regions,
  submitting, error, onSubmit, onCancel,
  feasData, checkingFeas, loadingMoreFeas, loadMoreFeasError, onCheckFeas, onClearFeas, onLoadMoreFeas,
}: TransferWizardProps): React.ReactElement {
  const w = useTransferWizard({ type, onInvalidate: onClearFeas });
  const {
    step, stepKeys, stepKey, lastStep, isTransfer,
    student, scope, destRegions, reason, otherDesc, selOpt, regionQuery, effective,
  } = w;
  const colorKey = isTransfer ? 'violet' : 'amber';

  const stepLabels: Record<typeof stepKey, string> = {
    student: t.transferStepStudent, scope: t.transferStepScope, details: t.transferStepDetails,
    options: t.transferStepOptions, confirm: t.transferStepConfirm,
  };
  const steps = stepKeys.map((k) => stepLabels[k]);

  const visibleRegions = filterRegionsByQuery(regions, regionQuery);
  const destRegionNames = regionNamesFor(regions, destRegions);
  const currentRegionLabel = student?.region_name || t.currentStudentRegionFallback;
  const searchedRegionNames = regionNamesOf(feasData?.search_regions);
  const scopeLabel = scope ? {
    same_apartment: t.scopeSameApartment,
    same_region: t.scopeSameRegion,
    cross_region: t.scopeCrossRegion,
  }[scope] : '';

  const scopeOptions: ScopeOption[] = [
    { v: 'same_apartment', l: t.scopeSameApartment },
    { v: 'same_region',    l: t.scopeSameRegion },
    { v: 'cross_region',   l: t.scopeCrossRegion, centralOnly: true },
  ];

  return (
    <div className={styles.wzRoot}>
      <WizardBar steps={steps} current={step} colorKey={colorKey} />
      <div className={styles.wzContent}>
        {stepKey === 'student' && (<>
          <h3 className={styles.wzTitle}>{t.transferStudentTitle}</h3>
          {student ? <PickedBar student={student} onClear={w.clearStudent} /> : (
            <StudentSearch
              onPick={w.pickStudent}
              filter={(s: WizardStudent) => s.is_assigned}
              placeholder={t.studentSearchPlaceholder}
              language={language}
            />
          )}
          {student && (
            <div className={cx(styles.assignmentPanel, styles.violetPanel)} style={{ marginTop: 12 }}>
              {student.region_name && <div className={styles.apRow}><MapPin size={13} /><span>{t.fieldRegion}</span><strong>{student.region_name}</strong></div>}
              <div className={styles.apRow}><Building2 size={13} /><span>{t.fieldBuilding}</span><strong>{student.current_building || t.dash}</strong></div>
              <div className={styles.apRow}><DoorOpen size={13} /><span>{t.fieldApartment}</span><strong>{student.current_apartment || t.dash}</strong></div>
              <div className={styles.apRow}><Home size={13} /><span>{t.fieldRoom}</span><strong>{student.current_room || t.dash}</strong></div>
            </div>
          )}
        </>)}

        {stepKey === 'scope' && (<>
          <h3 className={styles.wzTitle}>{t.transferScopeTitle}</h3>
          <div className={styles.prefGroup}>
            {scopeOptions.map((o) => (
              <button
                key={o.v}
                type="button"
                className={cx(styles.prefBtn, scope === o.v && styles.prefActive)}
                aria-pressed={scope === o.v}
                disabled={o.centralOnly && !central}
                title={o.centralOnly && !central ? t.scopeCentralOnlyTitle : undefined}
                onClick={() => w.setScope(o.v)}
              >{o.l}</button>
            ))}
          </div>
          {(scope === 'same_apartment' || scope === 'same_region') && (
            <div className={styles.scopeRegionNote}>
              <MapPin size={13} /> {t.targetRegionLabel} <strong>{central ? currentRegionLabel : (userRegionName || currentRegionLabel)}</strong>
              <span className={styles.scopeRegionHint}>
                {scope === 'same_apartment'
                  ? t.hintSameApartment
                  : t.hintSameRegion}
              </span>
            </div>
          )}
          {!central && (
            <div className={styles.scopeRegionNote}>
              <MapPin size={13} />
              <span className={styles.scopeRegionHint}>{t.nonCentralNote}</span>
            </div>
          )}
          {scope === 'cross_region' && central && (
            <div className={styles.regionMs}>
              <label className={styles.regionMsLabel}>{t.destRegionLabel}<span className={styles.req}>*</span></label>
              <div className={styles.regionMsSearch}>
                <Search size={12} />
                <input value={regionQuery} onChange={(e) => w.setRegionQuery(e.target.value)} placeholder={t.searchRegionPlaceholder} />
              </div>
              <div className={styles.regionMsList}>
                {visibleRegions.map((r) => (
                  <label key={r.id} className={cx(styles.regionMsRow, destRegions.includes(r.id) && styles.regionMsOn)}>
                    <input type="radio" name="dest-region" checked={destRegions.includes(r.id)} onChange={() => w.setDestRegions([r.id])} />
                    <span>{r.name}</span>
                    {student?.region_name === r.name && <span className={styles.regionMsCur}>{t.currentRegionTag}</span>}
                  </label>
                ))}
                {visibleRegions.length === 0 && <div className={styles.regionMsEmpty}>{t.noRegionsFound}</div>}
              </div>
              {destRegions.length > 0 && (
                <div className={styles.regionMsPicked}>{t.selectedLabel} <strong>{destRegionNames.join(', ')}</strong></div>
              )}
            </div>
          )}
        </>)}

        {stepKey === 'details' && (<>
          <h3 className={styles.wzTitle}>{t.detailsTitle}</h3>
          {type === 'other' && (
            <WizardField label={t.otherDescLabel}>
              <input value={otherDesc} onChange={(e) => w.setOtherDesc(e.target.value)} placeholder={t.otherDescPlaceholder} />
            </WizardField>
          )}
          <WizardField label={t.labelReason} required>
            <textarea rows={3} value={reason} onChange={(e) => w.setReason(e.target.value)} placeholder={t.transferReasonPlaceholder} />
          </WizardField>
        </>)}

        {stepKey === 'options' && (<>
          <h3 className={styles.wzTitle}>{t.optionsTitle}</h3>
          <div className={styles.scopeRegionNote}>
            <MapPin size={13} />
            {scope === 'cross_region'
              ? <>{t.targetRegionColon}<strong>{(searchedRegionNames.length ? searchedRegionNames : destRegionNames).join(', ')}</strong></>
              : <>{t.targetRegionColon}<strong>{searchedRegionNames[0] || currentRegionLabel}</strong></>}
            {scope === 'same_apartment' && <span className={styles.scopeRegionHint}>{t.optionsSameApartmentHint}</span>}
          </div>
          {!feasData && !checkingFeas && (
            <button
              type="button"
              className={styles.checkFeasBtn}
              onClick={() => student && onCheckFeas({
                studentId: student.id,
                reqType: effective.reqType,
                sameApt: effective.sameApt,
                transferScope: effective.scope,
                regionIds: scope === 'cross_region' ? destRegions : undefined,
              })}
            >
              <Activity size={14} /> {t.checkOptionsBtn}
            </button>
          )}
          {checkingFeas && <div className={styles.checkingState}><Spinner /> {t.searchingEllipsis}</div>}
          {feasData && (
            <BedMatchPicker
              buildings={feasData.buildings || []}
              totalBuildings={feasData.total_buildings}
              totalApartments={feasData.total_apartments}
              totalRooms={feasData.total_rooms}
              totalValidBeds={feasData.total_valid_beds}
              counts={feasData.counts}
              dataIntegrity={feasData.data_integrity}
              conflictExamples={feasData.conflict_examples}
              loading={checkingFeas}
              loadingMore={loadingMoreFeas}
              hasMore={!!feasData.has_more}
              onLoadMore={onLoadMoreFeas}
              loadMoreError={loadMoreFeasError}
              selectedBedId={selOpt?.bed_id}
              onSelectBed={w.setSelOpt}
              language={language}
              scopeContext={scope}
            />
          )}
        </>)}

        {stepKey === 'confirm' && (<>
          <h3 className={styles.wzTitle}>{t.confirmSummaryTitle}</h3>
          <div className={styles.wzSummary}>
            <div className={styles.sumRow}><span className={styles.sumK}>{t.summaryStudent}</span><span className={styles.sumV}>{student?.full_name}</span></div>
            <div className={styles.sumRow}><span className={styles.sumK}>{t.summaryCurrentPlacement}</span><span className={styles.sumV}>{t.loc3WithRegion(student?.region_name, student?.current_building, student?.current_apartment, student?.current_room)}</span></div>
            {isTransfer && <div className={styles.sumRow}><span className={styles.sumK}>{t.summaryTransferType}</span><span className={styles.sumV}>{scopeLabel}</span></div>}
            {isTransfer && scope === 'cross_region' && <div className={styles.sumRow}><span className={styles.sumK}>{t.summaryTargetRegion}</span><span className={styles.sumV}>{destRegionNames.join(', ')}</span></div>}
            {isTransfer && selOpt && <div className={styles.sumRow}><span className={styles.sumK}>{t.summarySelectedTarget}</span><span className={styles.sumV}>{t.loc3WithRegion(selOpt.region_name, selOpt.building, selOpt.apartment, selOpt.room)} · {bedLabelFor(t, selOpt)}</span></div>}
            {reason && <div className={styles.sumRow}><span className={styles.sumK}>{t.summaryReason}</span><span className={styles.sumV}>{reason}</span></div>}
            {otherDesc && <div className={styles.sumRow}><span className={styles.sumK}>{t.summaryDescription}</span><span className={styles.sumV}>{otherDesc}</span></div>}
          </div>
          {error && <div className={styles.wzErr}>{error}</div>}
        </>)}
      </div>
      <WizardFooter
        t={t}
        language={language}
        step={step}
        stepsCount={lastStep + 1}
        colorKey={colorKey}
        canNext={w.canNext}
        submitting={submitting}
        submitIcon={<Check size={13} />}
        submitLabel={t.submit}
        onCancel={onCancel}
        onBack={w.back}
        onNext={w.next}
        onSubmit={() => onSubmit(w.buildPayload(central))}
      />
    </div>
  );
}
