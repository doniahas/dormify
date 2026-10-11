import React, { useState } from 'react';
import {
  Activity, AlertTriangle, Check, CheckCircle, MapPin, RefreshCw, UserMinus, XCircle,
} from 'lucide-react';
import type { Id } from '../../../shared/api/contracts';
import type { Language } from '../../../shared/i18n';
import BedMatchPicker, { assignActionLabel } from '../../allocation/BedMatchPicker';
import type { BedSelection, RequestReviewView } from '../model';
import { bedLabelFor, regionNamesOf, scopeContextFor } from '../transferHelpers';
import type { TransfersStrings } from '../TransfersPage.strings';
import type { StudentRequest } from '../types';
import styles from './RequestDetail.module.css';
import { Spinner } from './RequestAtoms';

export interface RequestActionPanelProps {
  t: TransfersStrings;
  language: Language;
  request: StudentRequest;
  review: RequestReviewView;
  acting: boolean;
  /** The region-authority check (central admin, or the regional boss of that region). */
  canEditRegion: (regionId: Id | null) => boolean;
  onApprove: (id: number, roomId?: Id | null, bedId?: Id | null) => void;
  onReject: (id: number, reason: string) => void;
  onCheckFeas: (id: number) => void;
  onLoadMoreFeas: () => void;
  onLoadMoreBedOptions: () => void;
  onSetRoom: (selection: BedSelection) => void;
  onSelFeasOpt: (selection: BedSelection) => void;
}

/**
 * The reviewer's controls of a pending request: approve (with the picked
 * target bed where one is needed), reject with a reason, check or re-check
 * availability.
 */
export function RequestActionPanel({
  t, language, request, review, acting, canEditRegion,
  onApprove, onReject, onCheckFeas, onLoadMoreFeas, onLoadMoreBedOptions, onSetRoom, onSelFeasOpt,
}: RequestActionPanelProps): React.ReactElement | null {
  const [rejectText, setRejectText] = useState('');
  const [showReject, setShowReject] = useState(false);
  const {
    feasData, checkingFeas, loadingMoreFeas, loadMoreFeasError,
    bedOptions: rawBedOptions, loadingBeds, bedsError, loadingMoreBeds, loadMoreBedsError,
    roomSelection: roomId, feasSelection: selFeasOpt,
  } = review;
  const isAdd = request.request_type === 'add_student';
  const isRem = request.request_type === 'remove_student';
  const isSwap = request.request_type === 'swap';
  const hasFeas = feasData?.feasible !== undefined;

  if (request.status !== 'pending') return null;

  // A region_transfer's approve/reject authority is the DESTINATION
  // region (or central admin) - see _user_can_review_request() in
  // views.py, which the backend already enforces regardless of what the
  // frontend shows. canEditRegion() is the same region-authority check
  // already used elsewhere in the app (EDIT_ANY_REGION for central admin,
  // EDIT_OWN_REGION matched against the target region for a regional
  // boss), reused here rather than re-derived, so this can never drift
  // from the backend's own rule. The SOURCE region (and any unrelated
  // region) can still see this request in the list/detail pane - they
  // just get a status note here instead of action buttons they could
  // never actually use.
  if (request.request_type === 'region_transfer' && !canEditRegion(request.target_region)) {
    return (
      <div className={styles.actionPanel}>
        <span className={styles.apLabel}>{t.actionsLabel}</span>
        <div className={styles.scopeRegionNote}>
          <MapPin size={13} /> {t.pendingDestinationReviewNote}
        </div>
      </div>
    );
  }

  const rejectButton = (
    <button type="button" className={styles.btnRejOutline} onClick={() => setShowReject(true)}><XCircle size={12} /> {t.rejectBtn}</button>
  );

  return (
    <div className={styles.actionPanel}>
      <span className={styles.apLabel}>{t.actionsLabel}</span>
      {showReject ? (
        <div className={styles.rejectForm}>
          <textarea rows={2} value={rejectText} onChange={(e) => setRejectText(e.target.value)} placeholder={t.rejectPlaceholder} />
          <div className={styles.rfRow}>
            <button type="button" className={styles.btnGhostSm} onClick={() => setShowReject(false)}>{t.cancel}</button>
            <button type="button" className={styles.btnRejSm} onClick={() => onReject(request.id, rejectText)} disabled={acting}>
              {acting ? <Spinner size={12} /> : <XCircle size={12} />} {t.rejectBtn}
            </button>
          </div>
        </div>
      ) : isRem ? (
        <div className={styles.actRow}>
          <button type="button" className={styles.btnApproveDanger} onClick={() => onApprove(request.id)} disabled={acting}>
            {acting ? <Spinner size={12} /> : <UserMinus size={12} />} {t.approveRemoveBtn}
          </button>
          {rejectButton}
        </div>
      ) : isSwap ? (
        <div className={styles.actRow}>
          <button type="button" className={styles.btnApprove} onClick={() => onApprove(request.id)} disabled={acting}>
            {acting ? <Spinner size={12} /> : <RefreshCw size={12} />} {t.approveSwapBtn}
          </button>
          {rejectButton}
        </div>
      ) : isAdd ? (
        <>
          {bedsError && <div className={styles.feasNo}><AlertTriangle size={13} />{bedsError}</div>}
          <BedMatchPicker
            buildings={rawBedOptions?.buildings || []}
            totalBuildings={rawBedOptions?.total_buildings}
            totalApartments={rawBedOptions?.total_apartments}
            totalRooms={rawBedOptions?.total_rooms}
            totalValidBeds={rawBedOptions?.total_valid_beds}
            counts={rawBedOptions?.counts}
            dataIntegrity={rawBedOptions?.data_integrity}
            conflictExamples={rawBedOptions?.conflict_examples}
            loading={loadingBeds}
            loadingMore={loadingMoreBeds}
            hasMore={!!rawBedOptions?.has_more}
            onLoadMore={onLoadMoreBedOptions}
            loadMoreError={loadMoreBedsError}
            selectedBedId={roomId?.bed_id}
            onSelectBed={(bed) => onSetRoom(bed)}
            language={language}
          />
          {roomId && (
            <div className={styles.assignConfirmNote}>
              <CheckCircle size={13} />
              {t.assignNotePrefix} {t.loc3(roomId.building, roomId.apartment, roomId.room)}
              {` · ${bedLabelFor(t, roomId)}`}
            </div>
          )}
          <div className={styles.actRow} style={{ marginTop: 8 }}>
            <button
              type="button"
              className={styles.btnApprove}
              onClick={() => onApprove(request.id, roomId?.room_id, roomId?.bed_id)}
              disabled={acting || !roomId || !roomId.bed_id}
            >
              {acting ? <Spinner size={12} /> : <Check size={12} />} {roomId ? assignActionLabel(roomId, language) : t.selectBedToApprove}
            </button>
            {rejectButton}
          </div>
        </>
      ) : !hasFeas ? (
        <div className={styles.actRow}>
          <button type="button" className={styles.btnCheck} onClick={() => onCheckFeas(request.id)} disabled={checkingFeas}>
            {checkingFeas ? <><Spinner size={12} /> {t.checkingEllipsis}</> : <><Activity size={12} /> {t.checkAvailabilityBtn}</>}
          </button>
          {rejectButton}
        </div>
      ) : (
        <>
          {regionNamesOf(feasData.search_regions).length > 0 && (
            <div className={styles.scopeRegionNote}>
              <MapPin size={13} />
              {request.transfer_scope === 'cross_region'
                ? <>
                    {request.source_region_name
                      ? <>{t.crossRegionFromPrefix}<strong>{request.source_region_name}</strong>{t.crossRegionFromSuffix}</>
                      : t.targetRegionColon}
                    <strong>{regionNamesOf(feasData.search_regions).join(', ')}</strong>
                    <span className={styles.scopeRegionHint}>{t.crossRegionHint}</span>
                  </>
                : <>{t.targetRegionColon}<strong>{regionNamesOf(feasData.search_regions).join(', ')}</strong></>}
            </div>
          )}
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
            selectedBedId={selFeasOpt?.bed_id}
            onSelectBed={onSelFeasOpt}
            language={language}
            scopeContext={scopeContextFor(request)}
          />
          {selFeasOpt && (
            <div className={styles.assignConfirmNote}>
              <CheckCircle size={13} />
              {t.assignNotePrefix} {t.loc3(selFeasOpt.building, selFeasOpt.apartment, selFeasOpt.room)}
              {` · ${bedLabelFor(t, selFeasOpt)}`}
              {selFeasOpt.region_name ? ` (${selFeasOpt.region_name})` : ''}
            </div>
          )}
          <div className={styles.actRow}>
            {feasData.feasible === true && (
              <button
                type="button"
                className={styles.btnApprove}
                disabled={acting || !selFeasOpt || !selFeasOpt.bed_id}
                onClick={() => onApprove(request.id, selFeasOpt?.room_id, selFeasOpt?.bed_id)}
              >
                {acting ? <Spinner size={12} /> : <Check size={12} />} {selFeasOpt ? assignActionLabel(selFeasOpt, language) : t.selectBedToApprove}
              </button>
            )}
            <button type="button" className={styles.btnRecheck} onClick={() => onCheckFeas(request.id)} disabled={checkingFeas}><RefreshCw size={12} /> {t.recheckBtn}</button>
            {rejectButton}
          </div>
        </>
      )}
    </div>
  );
}
