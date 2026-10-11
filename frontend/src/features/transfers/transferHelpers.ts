// Pure helpers of the Transfers feature: formatting, the type/status
// presentation tables, the client-side list filtering/counting, and the
// translation of UI state into the exact backend parameters/payloads the
// page has always sent. No React, no I/O.
import type { Id } from '../../shared/api/contracts';
import type { BedSelection } from '../allocation/types';
import type {
  AddStudentForm,
  FeasibilityData,
  NewTransferScope,
  RegionFilter,
  RequestCounts,
  RequestLike,
  RequestStatusMeta,
  RequestTab,
  RequestTypeFilter,
  RequestTypeMeta,
  TimelineEvent,
  TransferStepKey,
  TransferWizardType,
  WizardStudent,
} from './model';
import type { TransfersStrings } from './TransfersPage.strings';
import type {
  ApproveRequestPayload,
  RequestListParams,
  RequestStatus,
  StudentRequest,
  StudentRequestPayload,
  TransferScope,
} from './types';

/** A location part (building / apartment / room / bed) as the API carries it. */
export type Loc = string | number | null | undefined;

/** A date value as the API carries it (ISO string; tolerated: a timestamp). */
export type DateValue = string | number | null | undefined;

// ── Formatting ───────────────────────────────────────────────

/** dd.mm.yyyy, hh:mm in the he-IL locale (the page's historical format), '—' when empty. */
export function fmtDate(iso: DateValue): string {
  if (!iso) return '—';
  try {
    return new Date(iso).toLocaleDateString('he-IL', {
      year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit',
    });
  } catch {
    return String(iso);
  }
}

/** "dd MMM" in the he-IL locale, '—' when empty. */
export function fmtDateShort(iso: DateValue): string {
  if (!iso) return '—';
  try {
    return new Date(iso).toLocaleDateString('he-IL', { month: 'short', day: '2-digit' });
  } catch {
    return String(iso);
  }
}

/** The request's number, or the REQ-<year>-<id> label the page derives when it is missing. */
export function fmtReqId(r: Partial<Pick<StudentRequest, 'request_number' | 'created_at' | 'id'>> | null | undefined): string {
  if (r?.request_number) return r.request_number;
  const yr = r?.created_at ? new Date(r.created_at).getFullYear() : new Date().getFullYear();
  return `REQ-${yr}-${String(r?.id || 0).padStart(6, '0')}`;
}

/** Narrows an untyped payload field (placement history) to a renderable location part. */
export function locOf(value: unknown): Loc {
  if (typeof value === 'string' || typeof value === 'number' || value == null) return value;
  return String(value);
}

/** Narrows an untyped payload field (placement history) to a date value. */
export function dateOf(value: unknown): DateValue {
  if (typeof value === 'string' || typeof value === 'number' || value == null) return value;
  return String(value);
}

type NameLike = Partial<Pick<WizardStudent, 'full_name' | 'first_name' | 'last_name'>> | null | undefined;

export function getName(s: NameLike): string {
  return s?.full_name || `${s?.first_name || ''} ${s?.last_name || ''}`.trim();
}

/** Error text for a thrown value, with the page's historical fallbacks. */
export function errorMessage(err: unknown, fallback: string): string {
  return err instanceof Error && err.message ? err.message : fallback;
}

// ── Type / status presentation ───────────────────────────────

export const TYPE_META: Readonly<Record<string, RequestTypeMeta>> = {
  room:            { color: 'violet', labelKey: 'typeLabelRoom' },
  apartment:       { color: 'teal',   labelKey: 'typeLabelApartment' },
  other:           { color: 'amber',  labelKey: 'typeLabelOther' },
  add_student:     { color: 'blue',   labelKey: 'typeLabelAddStudent' },
  remove_student:  { color: 'rose',   labelKey: 'typeLabelRemoveStudent' },
  swap:            { color: 'indigo', labelKey: 'typeLabelSwap' },
  region_transfer: { color: 'violet', labelKey: 'typeLabelRegionTransfer' },
};

// Cross-region transfers are stored as room/apartment + transfer_scope -
// but must never be LABELED "מעבר מדירה"; the scope is the meaningful type.
export const TYPE_META_CROSS: RequestTypeMeta = { color: 'violet', labelKey: 'typeLabelCrossRegion' };

export function typeMetaFor(request: RequestLike | null | undefined): RequestTypeMeta {
  if (
    request?.transfer_scope === 'cross_region'
    && (request.request_type === 'room' || request.request_type === 'apartment')
  ) {
    return TYPE_META_CROSS;
  }
  return (request ? TYPE_META[request.request_type] : undefined) || TYPE_META.other;
}

export const STATUS_META: Readonly<Record<RequestStatus, RequestStatusMeta>> = {
  pending:   { color: 'amber', labelKey: 'statusPending' },
  approved:  { color: 'green', labelKey: 'statusApproved' },
  rejected:  { color: 'rose',  labelKey: 'statusRejected' },
  cancelled: { color: 'slate', labelKey: 'statusCancelled' },
};

export function statusMetaFor(status: string | null | undefined): RequestStatusMeta {
  return (status ? STATUS_META[status as RequestStatus] : undefined) || STATUS_META.pending;
}

export function typeLabel(t: TransfersStrings, meta: RequestTypeMeta): string {
  return t[meta.labelKey];
}

export function statusLabel(t: TransfersStrings, meta: RequestStatusMeta): string {
  return t[meta.labelKey];
}

/** The picker's scope hint for a stored request. */
export function scopeContextFor(request: Pick<StudentRequest, 'transfer_scope' | 'same_apartment'>): NewTransferScope {
  return request.transfer_scope === 'cross_region' ? 'cross_region'
    : request.same_apartment === true ? 'same_apartment'
    : 'same_region';
}

/** The "Transfer Type" value of the detail pane for a room/apartment request. */
export function transferTypeText(
  t: TransfersStrings,
  request: Pick<StudentRequest, 'transfer_scope' | 'same_apartment' | 'transfer_scope_display'>
): string {
  return request.transfer_scope === 'cross_region' ? t.transferTypeCrossRegion
    : request.same_apartment === true ? t.transferTypeSameApartment
    : request.same_apartment === false ? t.transferTypeSameRegionDiffApt
    : (request.transfer_scope_display || t.transferTypeFallback);
}

/** The region names of a match-options reply's search_regions (untyped on the wire). */
export function regionNamesOf(list: unknown[] | undefined): string[] {
  return (list || []).map((r) => {
    if (r && typeof r === 'object' && 'name' in r) {
      const name = (r as { name?: unknown }).name;
      return name == null ? '' : String(name);
    }
    return '';
  });
}

/** " · bed 2" / " · single place" after a selected target's location. */
export function bedLabelFor(t: TransfersStrings, sel: BedSelection): string {
  return sel.single_bed_room ? t.singlePlace : `${t.bedWord} ${sel.bed_display || sel.bed_label}`;
}

/** The three steps of the request-route timeline. */
export function buildTimeline(t: TransfersStrings, request: StudentRequest): TimelineEvent[] {
  return [
    { label: t.tlCreated, sub: `${fmtDate(request.created_at)} · ${request.requested_by_name || t.dash}`, done: true },
    { label: t.tlPendingApproval, sub: '', done: request.status !== 'pending', active: request.status === 'pending' },
    {
      label: request.status === 'approved' ? statusLabel(t, STATUS_META.approved)
        : request.status === 'rejected' ? statusLabel(t, STATUS_META.rejected) : t.tlApprovalFallback,
      sub: request.reviewed_at ? `${fmtDate(request.reviewed_at)} · ${request.reviewed_by_name || ''}` : '',
      done: request.status === 'approved' || request.status === 'rejected',
    },
  ];
}

const DELETABLE_STATUSES: readonly string[] = ['pending', 'rejected', 'cancelled'];

export function isDeletableStatus(status: string): boolean {
  return DELETABLE_STATUSES.includes(status);
}

// ── List: parameters, counts, filtering ──────────────────────

/** Only a central admin's region filter reaches the backend; every status is always fetched. */
export function buildRequestListParams(isCentralAdmin: boolean, regionFilter: RegionFilter): RequestListParams {
  const params: RequestListParams = {};
  if (isCentralAdmin && regionFilter !== 'all') {
    params.region = regionFilter;
  }
  return params;
}

export function countRequests(requests: StudentRequest[]): RequestCounts {
  return {
    all: requests.length,
    pending: requests.filter((r) => r.status === 'pending').length,
    approved: requests.filter((r) => r.status === 'approved').length,
    rejected: requests.filter((r) => r.status === 'rejected').length,
    add_student: requests.filter((r) => r.request_type === 'add_student').length,
    remove_student: requests.filter((r) => r.request_type === 'remove_student').length,
    transfers: requests.filter((r) => ['room', 'apartment'].includes(r.request_type)).length,
  };
}

/** Status tab, then type, then the search over name / id number / request number. */
export function filterRequests(
  requests: StudentRequest[],
  tab: RequestTab,
  typeFilter: RequestTypeFilter,
  searchQ: string
): StudentRequest[] {
  let list = requests.filter((r) => tab === 'all' || r.status === tab);
  if (typeFilter !== 'all') list = list.filter((r) => r.request_type === typeFilter);
  if (searchQ.trim()) {
    const q = searchQ.toLowerCase();
    list = list.filter((r) =>
      (r.student_name || '').toLowerCase().includes(q)
      || (r.student_id_number || '').includes(q)
      || fmtReqId(r).toLowerCase().includes(q)
    );
  }
  return list;
}

// ── Review actions ───────────────────────────────────────────

/** PUT .../approve/ body: only the chosen target, when one was picked. */
export function buildApprovePayload(roomId?: Id | null, bedId?: Id | null): ApproveRequestPayload {
  const payload: ApproveRequestPayload = {};
  if (roomId) payload.target_room = roomId;
  if (bedId) payload.bed_id = bedId;
  return payload;
}

// ── Wizards ──────────────────────────────────────────────────

export const EMPTY_ADD_STUDENT_FORM: AddStudentForm = {
  student_id: '', first_name: '', last_name: '', phone: '', email: '', city: '',
  gender: '', religion: '', dorm_type: '', reason: '',
};

export function canAdvanceAddStudent(step: number, d: AddStudentForm): boolean {
  if (step === 0) return Boolean(d.student_id && d.first_name && d.last_name);
  if (step === 1) return !!d.gender;
  if (step === 2) return d.reason.trim().length > 0;
  return true;
}

export function buildAddStudentPayload(d: AddStudentForm): StudentRequestPayload {
  const { reason, ...studentFields } = d;
  return { request_type: 'add_student', reason, student_data: studentFields };
}

export function canAdvanceRemove(step: number, student: WizardStudent | null, reason: string): boolean {
  if (step === 0) return !!student;
  if (step === 2) return reason.trim().length > 0;
  return true;
}

export function buildRemovePayload(student: WizardStudent | null, reason: string): StudentRequestPayload {
  return { student: student?.id, reason, request_type: 'remove_student' };
}

export function canAdvanceSwap(
  step: number, studentA: WizardStudent | null, studentB: WizardStudent | null, reason: string
): boolean {
  if (step === 0) return !!studentA;
  if (step === 1) return !!studentB && studentB.id !== studentA?.id;
  if (step === 2) return reason.trim().length > 0;
  return true;
}

export function buildSwapPayload(
  studentA: WizardStudent | null, studentB: WizardStudent | null, reason: string
): StudentRequestPayload {
  return { student: studentA?.id, swap_with_student: studentB?.id, reason, request_type: 'swap' };
}

export function transferStepKeys(isTransfer: boolean): TransferStepKey[] {
  return isTransfer
    ? ['student', 'scope', 'details', 'options', 'confirm']
    : ['student', 'details', 'confirm'];
}

/**
 * The three scopes map onto existing backend request fields only:
 *   same_apartment -> room      + same_apartment=true
 *   same_region    -> apartment + same_apartment=false + scope same_region
 *   cross_region   -> apartment + scope cross_region + destination_regions
 */
export interface EffectiveTransferFields {
  reqType: 'room' | 'apartment';
  sameApt: boolean | null;
  scope: TransferScope;
}

export function effectiveTransferFields(scope: NewTransferScope | null): EffectiveTransferFields {
  return {
    reqType: scope === 'same_apartment' ? 'room' : 'apartment',
    sameApt: scope === 'same_apartment' ? true : scope === 'same_region' ? false : null,
    scope: scope === 'cross_region' ? 'cross_region' : 'same_region',
  };
}

export interface TransferDraft {
  student: WizardStudent | null;
  scope: NewTransferScope | null;
  destRegions: Id[];
  reason: string;
  otherDesc: string;
  selOpt: BedSelection | null;
}

export function canAdvanceTransfer(stepKey: TransferStepKey, d: TransferDraft): boolean {
  if (stepKey === 'student') return !!d.student;
  if (stepKey === 'scope') return !!d.scope && (d.scope !== 'cross_region' || d.destRegions.length > 0);
  if (stepKey === 'details') return d.reason.trim().length > 0;
  if (stepKey === 'options') return !!d.selOpt;
  return true;
}

/** The picked target room's id (room_id, falling back to the legacy roomId key). */
function pickedRoomId(sel: BedSelection | null): number | undefined {
  const v: unknown = sel?.room_id || sel?.roomId;
  if (typeof v === 'number') return v;
  if (typeof v === 'string' && v !== '') return Number(v);
  return undefined;
}

/** POST /api/requests/ body of the Transfer wizard (transfer or other). */
export function buildTransferPayload(
  type: TransferWizardType, d: TransferDraft, central: boolean
): StudentRequestPayload {
  const isTransfer = type === 'transfer';
  const eff = effectiveTransferFields(d.scope);
  return {
    student: d.student?.id,
    request_type: isTransfer ? eff.reqType : type,
    reason: d.reason,
    other_description: d.otherDesc,
    same_apartment: isTransfer ? eff.sameApt : null,
    target_room: pickedRoomId(d.selOpt),
    ...(isTransfer ? {
      transfer_scope: central ? eff.scope : 'same_region',
      // Region PKs are slug strings (e.g. "broshim") - pass them through
      // untouched, only dropping null/empty.
      destination_regions: (central && d.scope === 'cross_region')
        ? d.destRegions.filter((v) => v != null && String(v).trim() !== '').map(String)
        : [],
    } : {}),
  };
}

/** Regions whose name contains the (trimmed, case-insensitive) query. */
export function filterRegionsByQuery<R extends { name?: string | null }>(regions: R[], query: string): R[] {
  const q = query.trim().toLowerCase();
  return regions.filter((r) => !q || (r.name || '').toLowerCase().includes(q));
}

export function regionNamesFor<R extends { id: Id; name: string }>(regions: R[], ids: Id[]): string[] {
  return regions.filter((r) => ids.includes(r.id)).map((r) => r.name);
}

/** The reply the page stores when a feasibility call fails (never thrown at the UI). */
export function failedFeasibility(err: unknown, key: 'options' | 'buildings'): FeasibilityData {
  return { feasible: false, reason: err instanceof Error ? err.message : undefined, [key]: [] };
}
