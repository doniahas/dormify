// Pure helpers of the Students feature: formatting, derived flags, and the
// translation of UI state into the exact backend parameters/payloads the
// page has always sent. No React, no I/O.
import type { Id, StudentWritePayload } from '../../shared/api/contracts';
import { sameId } from '../../shared/api/normalize';
import type { StudentRequestPayload } from '../transfers/types';
import type {
  BedResultMeta,
  MatchOptionsReply,
  RequestDisabledReason,
  StudentDetailView,
  StudentFilters,
  StudentFormField,
  StudentFormValues,
  StudentRequestKind,
  StudentTab,
  StudentTransferScope,
} from './model';
import type { DormTypeFilterOption, StudentListParams } from './types';

export interface AvatarColor {
  bg: string;
  color: string;
}

const AVATAR_PALETTE: readonly AvatarColor[] = [
  { bg: 'linear-gradient(135deg, #dbeafe, #93c5fd)', color: '#1d4ed8' },
  { bg: 'linear-gradient(135deg, #dcfce7, #86efac)', color: '#047857' },
  { bg: 'linear-gradient(135deg, #ede9fe, #c4b5fd)', color: '#6d28d9' },
  { bg: 'linear-gradient(135deg, #fce7f3, #f9a8d4)', color: '#be185d' },
  { bg: 'linear-gradient(135deg, #fef3c7, #fcd34d)', color: '#b45309' },
  { bg: 'linear-gradient(135deg, #ccfbf1, #5eead4)', color: '#0f766e' },
];

/** A stable colour for a roommate avatar, derived from the seed's characters. */
export function pickAvatarColor(seed: string | number | null | undefined): AvatarColor {
  const s = String(seed || '');
  let total = 0;
  for (let i = 0; i < s.length; i++) total += s.charCodeAt(i);
  return AVATAR_PALETTE[total % AVATAR_PALETTE.length];
}

/** dd.mm.yyyy in the he-IL locale (the page's historical format), '—' when empty. */
export function fmtDate(iso: string | null | undefined): string {
  if (!iso) return '—';
  try {
    return new Date(iso).toLocaleDateString('he-IL', {
      year: 'numeric', month: '2-digit', day: '2-digit',
    });
  } catch {
    return iso;
  }
}

export type CategoryColor = 'green' | 'blue' | 'purple' | 'red';

export interface CategoryMeta {
  color: CategoryColor;
  dateKey: 'move_in_date' | 'move_out_date';
  dateLabelKey: 'movedInOn' | 'movingInOn' | 'leavingOn';
}

export const CATEGORY_META: Readonly<Record<string, CategoryMeta>> = {
  continuing: { color: 'green',  dateKey: 'move_in_date',  dateLabelKey: 'movedInOn' },
  new:        { color: 'blue',   dateKey: 'move_in_date',  dateLabelKey: 'movingInOn' },
  transfer:   { color: 'purple', dateKey: 'move_in_date',  dateLabelKey: 'movedInOn' },
  leaving:    { color: 'red',    dateKey: 'move_out_date', dateLabelKey: 'leavingOn' },
};

type NameLike = Partial<Pick<StudentDetailView, 'full_name' | 'first_name' | 'last_name'>> | null | undefined;

export function getName(s: NameLike): string {
  return s?.full_name || `${s?.first_name || ''} ${s?.last_name || ''}`.trim();
}

export function getInitial(s: NameLike): string {
  const n = getName(s);
  return n ? n[0] : '?';
}

export function getRoommateRequests(s: Partial<StudentDetailView> | null | undefined): string[] {
  return [
    s?.roommate_request_1, s?.roommate_request_2, s?.roommate_request_3,
    s?.roommate_request_4, s?.roommate_request_5,
  ].filter((v): v is string => Boolean(v));
}

/** A student who has moved out and holds no bed is shown as removed. */
export function isRemoved(s: Partial<StudentDetailView> | null | undefined): boolean {
  return Boolean(s?.move_out_date && !s?.is_assigned);
}

export const EMPTY_FILTERS: StudentFilters = {
  genders: [], religions: [], regions: [], dormTypes: [],
  buildings: [], apartments: [], rooms: [],
  assignmentStatuses: [], hasRoommateRequest: [],
};

export function countActiveFilters(f: StudentFilters): number {
  return (
    f.genders.length + f.religions.length + f.regions.length + f.dormTypes.length +
    f.buildings.length + f.apartments.length + f.rooms.length +
    f.assignmentStatuses.length + f.hasRoommateRequest.length
  );
}

/**
 * Maps the tab, the search box and the drawer state onto the exact backend
 * query parameters. The backend reads gender/requested_religion/region/
 * dorm_type/building/apartment/room (comma-joined for multi) + status +
 * has_roommate_request - never the raw drawer keys, which it ignores.
 */
export function buildStudentListParams(
  activeTab: StudentTab,
  searchQuery: string,
  f: StudentFilters
): StudentListParams {
  const params: StudentListParams = {};
  if (activeTab === 'unassigned') {
    params.status = 'unassigned';
  } else if (activeTab !== 'all') {
    params.category = activeTab;
  }
  const q = searchQuery.trim();
  if (q.length >= 2) params.search = q;
  if (f.genders.length) params.gender = f.genders.join(',');
  if (f.religions.length) params.requested_religion = f.religions.join(',');
  if (f.regions.length) params.region = f.regions.join(',');
  if (f.dormTypes.length) params.dorm_type = f.dormTypes.join(',');
  if (f.buildings.length) params.building = f.buildings.join(',');
  if (f.apartments.length) params.apartment = f.apartments.join(',');
  if (f.rooms.length) params.room = f.rooms.join(',');
  if (activeTab !== 'unassigned' && f.assignmentStatuses.length) {
    params.status = f.assignmentStatuses[0];
  }
  if (f.hasRoommateRequest.length) params.has_roommate_request = f.hasRoommateRequest[0];
  return params;
}

/**
 * Central admins pick a region first, which narrows the dorm-type list to
 * that region (accepted_dorm_type is what actually carries the student's
 * region). Regional staff's list is already scoped server-side.
 */
export function dormTypeOptionsForRegion(
  all: DormTypeFilterOption[] | undefined,
  isCentralAdmin: boolean,
  region: string
): DormTypeFilterOption[] {
  const options = all || [];
  if (!isCentralAdmin) return options;
  if (!region) return [];
  return options.filter((dt) => sameId(dt.region_id, region));
}

export const EMPTY_STUDENT_FORM: StudentFormValues = {
  student_id: '',
  first_name: '',
  last_name: '',
  phone: '',
  email: '',
  city: '',
  gender: '',
  requested_religion: 'not_specified',
  region: '',
  accepted_dorm_type: '',
  housing_type: '',
  category: 'new',
  reason: '',
};

/** Pre-fills the edit form from an existing student. */
export function studentFormFromStudent(student: StudentDetailView): StudentFormValues {
  return {
    student_id: student.student_id || '',
    first_name: student.first_name || '',
    last_name: student.last_name || '',
    phone: student.phone || '',
    email: student.email || '',
    city: student.city || '',
    gender: student.gender || '',
    requested_religion: student.requested_religion || 'not_specified',
    region: student.region_id != null ? String(student.region_id) : '',
    accepted_dorm_type: student.accepted_dorm_type != null ? String(student.accepted_dorm_type) : '',
    housing_type: student.housing_type || '',
    category: student.category || 'new',
    reason: '',
  };
}

/**
 * The required fields of the student form. housing_type/accepted_dorm_type
 * (and region, for a central admin) are only required for a student actually
 * eligible for assignment - mirrors Student.is_assignment_eligible on the
 * backend (leaving students exempt).
 */
export function missingStudentFormFields(
  form: StudentFormValues,
  { requireStudentId, isCentralAdmin }: { requireStudentId: boolean; isCentralAdmin: boolean }
): StudentFormField[] {
  const required: StudentFormField[] = requireStudentId
    ? ['student_id', 'first_name', 'last_name', 'gender']
    : ['first_name', 'last_name', 'gender'];
  if (form.category !== 'leaving') {
    required.push('accepted_dorm_type', 'housing_type');
    if (isCentralAdmin) required.push('region');
  }
  return required.filter((field) => !String(form[field] || '').trim());
}

/** The PATCH/POST body built from the form (student_id only on create). */
export function buildStudentPayload(
  form: StudentFormValues,
  { includeStudentId }: { includeStudentId: boolean }
): StudentWritePayload {
  const payload: StudentWritePayload = {
    first_name: form.first_name.trim(),
    last_name: form.last_name.trim(),
    phone: form.phone.trim(),
    email: form.email.trim(),
    city: form.city.trim(),
    gender: form.gender as StudentWritePayload['gender'],
    requested_religion: (form.requested_religion || 'not_specified') as StudentWritePayload['requested_religion'],
    // The select's string value is sent as-is (DRF resolves the PK either way).
    accepted_dorm_type: form.accepted_dorm_type || null,
    housing_type: form.housing_type || '',
    category: (form.category || 'new') as StudentWritePayload['category'],
  };
  if (includeStudentId) {
    return { student_id: form.student_id.trim(), ...payload };
  }
  return payload;
}

/** A region id is valid when it is present: Region PKs are slug strings, never numeric. */
export function isValidRegionId(value: Id | null | undefined): boolean {
  return value != null && String(value).trim() !== '';
}

export interface AddRequestDraft {
  reqType: StudentRequestKind;
  reqScope: StudentTransferScope | null;
  reqTargetRegion: Id | null;
  reqOtherDesc: string;
  reqReason: string;
}

/**
 * Single source of truth for the submit button. A cross-region transfer
 * needs ONLY: student + scope + valid region PK + non-empty reason.
 * Room/apartment/bed are chosen later, at APPROVAL time.
 */
export function requestDisabledReason(
  draft: AddRequestDraft,
  { hasStudent, submitting, submitted }: { hasStudent: boolean; submitting: boolean; submitted: boolean }
): RequestDisabledReason | null {
  const { reqType, reqScope, reqTargetRegion, reqOtherDesc, reqReason } = draft;
  if (submitting) return 'submitting';
  if (submitted) return 'already-submitted';
  if (!hasStudent) return 'no-student';
  if (!reqReason.trim()) return 'empty-reason';
  if (reqType === 'transfer' && !reqScope) return 'no-scope';
  if (reqType === 'transfer' && reqScope === 'cross_region' && !isValidRegionId(reqTargetRegion)) {
    return 'invalid-target-region';
  }
  if (reqType === 'other' && !reqOtherDesc.trim()) return 'empty-other-description';
  return null;
}

/**
 * Scope -> existing backend fields, mirroring the Transfers page:
 *   same_apartment -> room      + same_apartment=true
 *   same_region    -> apartment + same_apartment=false
 *   cross_region   -> apartment + cross_region + destination_regions
 */
export function buildRequestPayload(studentId: Id, draft: AddRequestDraft): StudentRequestPayload {
  const { reqType, reqScope, reqTargetRegion, reqOtherDesc, reqReason } = draft;
  const payload: StudentRequestPayload = {
    student: Number(studentId),
    request_type: reqType === 'transfer'
      ? (reqScope === 'same_apartment' ? 'room' : 'apartment')
      : reqType,
    reason: reqReason.trim(),
  };
  if (reqType === 'transfer') {
    payload.same_apartment =
      reqScope === 'same_apartment' ? true : reqScope === 'same_region' ? false : null;
    payload.transfer_scope = reqScope === 'cross_region' ? 'cross_region' : 'same_region';
    payload.destination_regions = reqScope === 'cross_region'
      ? [reqTargetRegion].filter(isValidRegionId).map(String)
      : [];
  }
  if (reqType === 'other') payload.other_description = reqOtherDesc.trim();
  return payload;
}

export const EMPTY_BED_META: BedResultMeta = {
  total_valid_beds: 0, total_buildings: 0, total_apartments: 0, total_rooms: 0,
  has_more: false, conflict_examples: [], counts: null, data_integrity: null,
};

/** The counters of a match-options reply, with the page's defaults for absent fields. */
export function bedMetaFromReply(data: MatchOptionsReply): BedResultMeta {
  return {
    total_valid_beds: data.total_valid_beds || 0,
    total_buildings: data.total_buildings || 0,
    total_apartments: data.total_apartments || 0,
    total_rooms: data.total_rooms || 0,
    has_more: !!data.has_more,
    conflict_examples: data.conflict_examples || [],
    counts: data.counts || null,
    data_integrity: data.data_integrity || null,
  };
}

/** Error text for a thrown value, with the page's historical fallbacks. */
export function errorMessage(err: unknown, fallback: string): string {
  return err instanceof Error && err.message ? err.message : fallback;
}

/** Joins DRF field error messages ("a", ["a", "b"]) into one line. */
export function fieldErrorText(value: unknown): string {
  if (value == null) return '';
  const list: unknown[] = Array.isArray(value) ? value : [value];
  return list.map(String).join(' ');
}
