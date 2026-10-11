import React, { useState } from 'react';
import {
  Activity, AlertTriangle, BedDouble, Building2, Check, ChevronDown, ChevronUp, Circle,
  DoorOpen, Hash, Home, MapPin, Trash2,
} from 'lucide-react';
import type { Id } from '../../../shared/api/contracts';
import type { Language } from '../../../shared/i18n';
import { cx } from '../../../shared/lib/classNames';
import type { BedSelection, RequestReviewView, TimelineEvent } from '../model';
import {
  buildTimeline, dateOf, fmtDate, fmtReqId, isDeletableStatus, locOf,
  statusLabel, statusMetaFor, transferTypeText, typeLabel, typeMetaFor,
} from '../transferHelpers';
import type { TransfersStrings } from '../TransfersPage.strings';
import type { StudentRequest } from '../types';
import styles from './RequestDetail.module.css';
import { capitalize, Pill, Spinner, statusIconFor, typeIconFor } from './RequestAtoms';
import { RequestActionPanel } from './RequestActionPanel';

function Timeline({ events }: { events: TimelineEvent[] }): React.ReactElement {
  return (
    <div className={styles.tlWrap}>
      {events.map((ev, i) => (
        <div key={i} className={cx(styles.tlItem, ev.done ? styles.tlDone : ev.active ? styles.tlActive : styles.tlIdle)}>
          <div className={styles.tlDot}>
            {ev.done ? <Check size={9} /> : ev.active ? <Circle size={8} /> : null}
          </div>
          {i < events.length - 1 && <div className={styles.tlLine} />}
          <div className={styles.tlBody}>
            <span className={styles.tlLbl}>{ev.label}</span>
            {ev.sub && <span className={styles.tlSub}>{ev.sub}</span>}
          </div>
        </div>
      ))}
    </div>
  );
}

export interface RequestDetailPaneProps {
  t: TransfersStrings;
  language: Language;
  request: StudentRequest;
  review: RequestReviewView;
  acting: boolean;
  deleting: boolean;
  canEditRegion: (regionId: Id | null) => boolean;
  onApprove: (id: number, roomId?: Id | null, bedId?: Id | null) => void;
  onReject: (id: number, reason: string) => void;
  onDelete: (request: StudentRequest) => void;
  onCheckFeas: (id: number) => void;
  onLoadMoreFeas: () => void;
  onLoadMoreBedOptions: () => void;
  onSetRoom: (selection: BedSelection) => void;
  onSelFeasOpt: (selection: BedSelection) => void;
}

/** The selected request: header, route timeline, placement, details, history, decision and delete. */
export function RequestDetailPane({
  t, language, request, review, acting, deleting, canEditRegion,
  onApprove, onReject, onDelete, onCheckFeas, onLoadMoreFeas, onLoadMoreBedOptions, onSetRoom, onSelFeasOpt,
}: RequestDetailPaneProps): React.ReactElement {
  const [histOpen, setHistOpen] = useState(false);
  const typeCfg = typeMetaFor(request);
  const statusCfg = statusMetaFor(request.status);
  const TypeIcon = typeIconFor(request);
  const StatIcon = statusIconFor(request.status);
  const typeColor = capitalize(typeCfg.color);

  const tl = buildTimeline(t, request);

  return (
    <div className={styles.dpRoot}>
      {/* Header */}
      <div className={styles.dpHdr}>
        <div className={styles.dpIdRow}>
          <span className={styles.dpReqId}><Hash size={11} />{fmtReqId(request)}</span>
          <Pill color={statusCfg.color}><StatIcon size={10} /> {statusLabel(t, statusCfg)}</Pill>
        </div>
        <div className={styles.dpStuRow}>
          <div className={cx(styles.dpAva, styles[`dpAva${typeColor}`])}>{(request.student_name || '?')[0]}</div>
          <div>
            <h2 className={styles.dpStuName}>{request.student_name}</h2>
            <div className={styles.dpStuMeta}>
              <span className={styles.mono}>{request.student_id_number}</span>
              {request.student_phone && <span>· {request.student_phone}</span>}
            </div>
          </div>
          <div className={cx(styles.dpTypeTag, styles[`dpType${typeColor}`])}>
            <TypeIcon size={12} />
            <span className={styles.dpTypeLabel}>{t.dpTypeLabel}</span>
            <span>{typeLabel(t, typeCfg)}</span>
          </div>
        </div>
      </div>

      {/* Body */}
      <div className={styles.dpBody}>
        {/* Timeline */}
        <section>
          <div className={styles.secTitle}>{t.sectionRequestRoute}</div>
          <Timeline events={tl} />
        </section>

        {/* Current placement */}
        {request.current_building && (
          <section>
            <div className={styles.secTitle}>{t.sectionCurrentPlacement}</div>
            <div className={styles.assignRows}>
              {request.current_region && (
                <div className={styles.assignRow}><MapPin size={18} /><span className={styles.assignRowLabel}>{t.fieldRegion}</span><span className={styles.assignRowVal}>{request.current_region}</span></div>
              )}
              <div className={styles.assignRow}><Building2 size={18} /><span className={styles.assignRowLabel}>{t.fieldBuilding}</span><span className={styles.assignRowVal}>{request.current_building}</span></div>
              <div className={styles.assignRow}><DoorOpen size={18} /><span className={styles.assignRowLabel}>{t.fieldApartment}</span><span className={styles.assignRowVal}>{request.current_apartment}</span></div>
              <div className={styles.assignRow}><Home size={18} /><span className={styles.assignRowLabel}>{t.fieldRoom}</span><span className={styles.assignRowVal}>{request.current_room}</span></div>
              {request.current_bed && (
                <div className={styles.assignRow}><BedDouble size={18} /><span className={styles.assignRowLabel}>{t.fieldBed}</span><span className={styles.assignRowVal}>{request.current_bed}</span></div>
              )}
            </div>
          </section>
        )}

        {/* Details */}
        <section>
          <div className={styles.secTitle}>{t.sectionRequestDetails}</div>
          {(request.request_type === 'room' || request.request_type === 'apartment') && (
            <div className={styles.kv}><span>{t.kvTransferType}</span><strong>{transferTypeText(t, request)}</strong></div>
          )}
          {request.transfer_scope && request.source_region_name && (
            <div className={styles.kv}><span>{t.kvSourceRegion}</span><strong>{request.source_region_name}</strong></div>
          )}
          {request.transfer_scope === 'cross_region' && (request.destination_region_names || []).length > 0 && (
            <div className={styles.kv}><span>{t.kvTargetRegion}</span><strong>{request.destination_region_names.join(', ')}</strong></div>
          )}
          {request.status === 'approved' && request.target_room_name && (
            <div className={styles.kv}><span>{t.kvFinalPlacement}</span><strong>
              {t.loc3(request.target_building_number, request.target_apartment_number, request.target_room_name)}
              {request.final_bed_label ? ` · ${t.bedWord} ${String(request.final_bed_label).replace(/^bed\s*/i, '')}` : ''}
            </strong></div>
          )}
          {request.request_type === 'swap' && request.swap_with_student_name && (
            <div className={styles.kv}><span>{t.kvSwapWith}</span><strong>{request.swap_with_student_name} ({request.swap_with_student_id_number})</strong></div>
          )}
          {request.reason && <div className={styles.kv}><span>{t.kvReason}</span><strong className={styles.kvReason}>{request.reason}</strong></div>}
          {request.other_description && <div className={styles.kv}><span>{t.kvDescription}</span><strong>{request.other_description}</strong></div>}
          <div className={styles.kv}><span>{t.kvOpenedBy}</span><strong>{request.requested_by_name || t.dash}</strong></div>
          <div className={styles.kv}><span>{t.kvDate}</span><strong>{fmtDate(request.created_at)}</strong></div>
          {request.reviewed_by_name && <div className={styles.kv}><span>{t.kvHandledBy}</span><strong>{request.reviewed_by_name}</strong></div>}
        </section>

        {/* History */}
        {Array.isArray(request.placement_history) && request.placement_history.length > 0 && (
          <section>
            <button type="button" className={styles.histToggle} aria-expanded={histOpen} onClick={() => setHistOpen((h) => !h)}>
              <Activity size={12} /> {t.historyToggle(request.placement_history.length)} {histOpen ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
            </button>
            {histOpen && (
              <div className={styles.histList}>
                {request.placement_history.map((p, i) => (
                  <div key={i} className={styles.histItem}>
                    <div className={styles.hiLoc}>{p.region ? <span className={styles.hiReg}>{locOf(p.region)}</span> : null}<span>{t.loc3(locOf(p.building), locOf(p.apartment), locOf(p.room))}</span></div>
                    <span className={styles.hiDate}>{fmtDate(dateOf(p.assigned_at))}{p.ended_at ? ` → ${fmtDate(dateOf(p.ended_at))}` : ''}</span>
                  </div>
                ))}
              </div>
            )}
          </section>
        )}

        {/* Rejection */}
        {request.status === 'rejected' && request.rejection_reason && (
          <div className={styles.rejBanner}><AlertTriangle size={13} /><strong>{t.rejectionReasonLabel}</strong> {request.rejection_reason}</div>
        )}

        {/* Actions */}
        <RequestActionPanel
          t={t}
          language={language}
          request={request}
          review={review}
          acting={acting}
          canEditRegion={canEditRegion}
          onApprove={onApprove}
          onReject={onReject}
          onCheckFeas={onCheckFeas}
          onLoadMoreFeas={onLoadMoreFeas}
          onLoadMoreBedOptions={onLoadMoreBedOptions}
          onSetRoom={onSetRoom}
          onSelFeasOpt={onSelFeasOpt}
        />

        {isDeletableStatus(request.status) && (
          <div className={styles.deleteRequestSection}>
            <button
              type="button"
              className={styles.btnDeleteRequest}
              onClick={() => onDelete(request)}
              disabled={deleting}
            >
              {deleting
                ? <Spinner size={12} />
                : <Trash2 size={13} />}

              {t.deleteRequestBtn}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
