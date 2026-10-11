// UI-level types owned by the Transfers feature: the list's tabs and filters,
// the per-request review state (feasibility, add-student bed options and
// the bed picked for approval), and the New Request wizards' form state.
// Wire types stay in shared/api/contracts and ./types.ts.
import type { Id, Student, StudentSummary } from '../../shared/api/contracts';
import type { BedSelection } from '../allocation/types';
import type { FeasibilityResult, StudentRequest, TransferScope } from './types';

/** The status tabs of the list; the stat cards select the same keys. */
export type RequestTab = 'all' | 'pending' | 'approved' | 'rejected';

export const REQUEST_TABS: readonly RequestTab[] = ['all', 'pending', 'approved', 'rejected'];

/** The request-type <select> of the list toolbar. */
export type RequestTypeFilter =
  | 'all'
  | 'add_student'
  | 'remove_student'
  | 'room'
  | 'apartment'
  | 'swap'
  | 'other';

/** 'all' or a region id (central admins only). */
export type RegionFilter = string;

/** Client-side totals over the loaded requests (the list always loads every status). */
export interface RequestCounts {
  all: number;
  pending: number;
  approved: number;
  rejected: number;
  add_student: number;
  remove_student: number;
  transfers: number;
}

/** The four stat cards above the two-pane body. */
export type StatCardKey = RequestTab;

export type StatColor = 'slate' | 'amber' | 'green' | 'rose';

/** The colour strip / avatar / tag colour of a request type. */
export type TypeColor = 'violet' | 'teal' | 'amber' | 'blue' | 'rose' | 'indigo';

export type StatusColor = 'amber' | 'green' | 'rose' | 'slate';

export type TypeLabelKey =
  | 'typeLabelRoom'
  | 'typeLabelApartment'
  | 'typeLabelOther'
  | 'typeLabelAddStudent'
  | 'typeLabelRemoveStudent'
  | 'typeLabelSwap'
  | 'typeLabelRegionTransfer'
  | 'typeLabelCrossRegion';

export type StatusLabelKey = 'statusPending' | 'statusApproved' | 'statusRejected' | 'statusCancelled';

/** How a request type renders: its colour and the dictionary key of its label. */
export interface RequestTypeMeta {
  color: TypeColor;
  labelKey: TypeLabelKey;
}

export interface RequestStatusMeta {
  color: StatusColor;
  labelKey: StatusLabelKey;
}

/** One step of the request-route timeline in the detail pane. */
export interface TimelineEvent {
  label: string;
  sub: string;
  done: boolean;
  active?: boolean;
}

/** The hierarchical match-options reply (feasibility / add-student beds). */
export type FeasibilityData = FeasibilityResult;

/**
 * The review state of ONE request as the detail pane sees it: the
 * feasibility results (room/apartment transfers), the add-student bed
 * options, their paging state and the bed picked for approval.
 */
export interface RequestReviewView {
  feasData: FeasibilityData | null | undefined;
  checkingFeas: boolean;
  loadingMoreFeas: boolean;
  loadMoreFeasError: string;
  bedOptions: FeasibilityData | undefined;
  loadingBeds: boolean;
  bedsError: string | undefined;
  loadingMoreBeds: boolean;
  loadMoreBedsError: string;
  /** The bed picked for an add_student approval. */
  roomSelection: BedSelection | undefined;
  /** The bed picked for a transfer approval. */
  feasSelection: BedSelection | undefined;
}

/** The kinds the New Request modal's type picker offers. */
export type NewRequestKind = 'add_student' | 'remove_student' | 'transfer' | 'swap' | 'other';

/** The accent colour of a wizard (progress bar + primary button). */
export type WizardColor = 'blue' | 'rose' | 'indigo' | 'violet' | 'amber';

/** The unified transfer scope of the Transfer wizard. */
export type NewTransferScope = 'same_apartment' | 'same_region' | 'cross_region';

/** The Transfer wizard serves both transfer and "other" requests. */
export type TransferWizardType = 'transfer' | 'other';

export type TransferStepKey = 'student' | 'scope' | 'details' | 'options' | 'confirm';

/** The Add Student wizard's fields (all input strings). */
export interface AddStudentForm {
  student_id: string;
  first_name: string;
  last_name: string;
  phone: string;
  email: string;
  city: string;
  gender: string;
  religion: string;
  dorm_type: string;
  reason: string;
}

export type AddStudentField = keyof AddStudentForm;

/**
 * A student as StudentSearch hands it over (a list row), possibly completed
 * with the full record (region_name) once the wizard fetched it.
 */
export type WizardStudent = StudentSummary & Partial<Pick<Student, 'region_name' | 'region_id'>>;

/** What a feasibility preview (match-options for a request being composed) searches. */
export interface FeasibilityPreviewArgs {
  studentId: Id;
  reqType: 'room' | 'apartment';
  sameApt: boolean | null;
  transferScope: TransferScope;
  regionIds: Id[] | undefined;
}

export type { BedSelection } from '../allocation/types';

/** The fields the type/scope presentation reads off a request. */
export type RequestLike = Pick<StudentRequest, 'request_type' | 'transfer_scope'>;
