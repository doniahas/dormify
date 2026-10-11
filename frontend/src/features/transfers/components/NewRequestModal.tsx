import React from 'react';
import { ArrowRightLeft, FileText, RefreshCw, UserMinus, UserPlus, X, type LucideIcon } from 'lucide-react';
import type { Region } from '../../../shared/api/contracts';
import type { Language } from '../../../shared/i18n';
import { cx } from '../../../shared/lib/classNames';
import type { NewRequestModalState } from '../hooks/useNewRequestModal';
import type { NewRequestKind, WizardColor } from '../model';
import type { TransfersStrings } from '../TransfersPage.strings';
import styles from './NewRequestModal.module.css';
import { AddStudentWizard } from './AddStudentWizard';
import { capitalize } from './RequestAtoms';
import { RemoveWizard } from './RemoveWizard';
import { SwapWizard } from './SwapWizard';
import { TransferWizard } from './TransferWizard';
import { directionalArrows } from './WizardChrome';

export interface NewRequestModalProps {
  t: TransfersStrings;
  language: Language;
  isCentralAdmin: boolean;
  userRegionName: string | null | undefined;
  regions: Region[];
  state: NewRequestModalState;
}

interface TypeCard {
  v: NewRequestKind;
  Icon: LucideIcon;
  color: WizardColor;
  title: string;
  sub: string;
}

function typeCards(t: TransfersStrings): TypeCard[] {
  return [
    { v: 'add_student',    Icon: UserPlus,       color: 'blue',   title: t.typeAddStudentTitle,    sub: t.typeAddStudentSub },
    { v: 'remove_student', Icon: UserMinus,      color: 'rose',   title: t.typeRemoveStudentTitle, sub: t.typeRemoveStudentSub },
    { v: 'transfer',       Icon: ArrowRightLeft, color: 'violet', title: t.typeTransferTitle,      sub: t.typeTransferSub },
    { v: 'swap',           Icon: RefreshCw,      color: 'indigo', title: t.typeSwapTitle,          sub: t.typeSwapSub },
    { v: 'other',          Icon: FileText,       color: 'amber',  title: t.typeOtherTitle,         sub: t.typeOtherSub },
  ];
}

/** The New Request modal: the type picker, then the chosen wizard. */
export function NewRequestModal({
  t, language, isCentralAdmin, userRegionName, regions, state,
}: NewRequestModalProps): React.ReactElement {
  const { type, setType, close, submit, submitting, error } = state;
  const { BackArrow, NextArrow } = directionalArrows(language);
  const wizardProps = { t, language, submitting, error, onSubmit: submit, onCancel: close };

  return (
    <div className={styles.modalOverlay} onClick={close}>
      <div className={styles.modalBox} role="dialog" aria-modal="true" onClick={(e) => e.stopPropagation()}>
        <div className={styles.modalHead}>
          <div className={styles.mhLeft}>
            {type && <button type="button" className={styles.backType} onClick={() => setType(null)}><BackArrow size={13} /> {t.modalBackToTypes}</button>}
            <h2>{type ? t.modalNewRequest : t.modalChooseType}</h2>
          </div>
          <button type="button" className={styles.modalClose} onClick={close} aria-label={t.cancel}><X size={17} /></button>
        </div>

        {!type && (
          <div className={styles.typePicker}>
            {typeCards(t).map((tc) => {
              const Icon = tc.Icon;
              return (
                <button key={tc.v} type="button" className={styles.tpCard} onClick={() => setType(tc.v)}>
                  <div className={cx(styles.tpIco, styles[`tpIco${capitalize(tc.color)}`])}><Icon size={18} /></div>
                  <div className={styles.tpInfo}>
                    <span className={styles.tpTitle}>{tc.title}</span>
                    <span className={styles.tpSub}>{tc.sub}</span>
                  </div>
                  <NextArrow size={13} className={styles.tpArrow} />
                </button>
              );
            })}
          </div>
        )}
        {type === 'add_student'    && <AddStudentWizard {...wizardProps} />}
        {type === 'remove_student' && <RemoveWizard {...wizardProps} />}
        {type === 'swap'           && <SwapWizard {...wizardProps} />}
        {(type === 'transfer' || type === 'other') && (
          <TransferWizard
            {...wizardProps}
            type={type}
            isCentralAdmin={isCentralAdmin}
            userRegionName={userRegionName}
            regions={regions}
            feasData={state.feasData}
            checkingFeas={state.checkingFeas}
            loadingMoreFeas={state.loadingMoreFeas}
            loadMoreFeasError={state.loadMoreFeasError}
            onCheckFeas={state.checkFeasibility}
            onClearFeas={state.clearFeasibility}
            onLoadMoreFeas={state.loadMoreFeasibility}
          />
        )}
      </div>
    </div>
  );
}
