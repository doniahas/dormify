// UI-level types owned by the Students feature: the page's tabs, the filter
// drawer state, the student as the detail view holds it, and the forms.
// Wire types stay in shared/api/contracts and ./types.ts.
import type { Id, Student, StudentSummary } from '../../shared/api/contracts';
import type { BedMatchOptions } from './types';

/** The status tabs above the list. 'unassigned' maps onto status, the rest onto category. */
export type StudentTab = 'all' | 'continuing' | 'new' | 'transfer' | 'leaving' | 'unassigned';

export const STUDENT_TABS: readonly StudentTab[] = [
  'all', 'continuing', 'new', 'transfer', 'leaving', 'unassigned',
];

/** Per-tab totals as /api/students/counts/ returns them. */
export type StudentTabCounts = Record<StudentTab, number>;

/** The selections the FiltersDrawer edits; every list holds raw ids/values. */
export interface StudentFilters {
  genders: string[];
  religions: string[];
  regions: string[];
  dormTypes: string[];
  buildings: string[];
  apartments: string[];
  rooms: string[];
  assignmentStatuses: string[];
  hasRoommateRequest: string[];
}

/**
 * A list row. StudentListSerializer carries no move dates today; they are
 * read optionally so the removed/date chips render exactly as before
 * whenever a row does carry them.
 */
export type StudentRow = StudentSummary & Partial<Pick<Student, 'move_in_date' | 'move_out_date'>>;

/** A roommate as the detail view would render one (not part of StudentSerializer today). */
export interface StudentRoommate {
  id: Id;
  student_id?: string;
  full_name?: string;
  bed_label?: string | null;
}

/**
 * The student the detail view shows: a list row (StudentListSerializer)
 * immediately on click, then the full StudentSerializer payload once it
 * arrives. Either shape is accepted - the detail payload has no current_*
 * list columns and omits the assigned_* fields while unassigned - so every
 * field outside the common core is optional. The two extra fields are read
 * defensively (they are not serialized today).
 */
export type StudentDetailView = (StudentSummary | Student) &
  Partial<StudentSummary> &
  Partial<Student> & {
    roommates?: StudentRoommate[];
    assigned_region?: string | null;
  };

/** The add/edit student form as the modal edits it (all values are input strings). */
export interface StudentFormValues {
  student_id: string;
  first_name: string;
  last_name: string;
  phone: string;
  email: string;
  city: string;
  gender: string;
  requested_religion: string;
  region: string;
  accepted_dorm_type: string;
  housing_type: string;
  category: string;
  reason: string;
}

export type StudentFormField = keyof StudentFormValues;

/** Add Student can save, or save and jump straight into bed matching. */
export type AddStudentMode = 'save' | 'save_and_match';

/** The request kinds the Add Request modal offers for an assigned student. */
export type StudentRequestKind = 'transfer' | 'other' | 'remove_student';

export type StudentTransferScope = 'same_apartment' | 'same_region' | 'cross_region';

/** Why the Add Request submit button is disabled, when it is. */
export type RequestDisabledReason =
  | 'submitting'
  | 'already-submitted'
  | 'no-student'
  | 'empty-reason'
  | 'no-scope'
  | 'invalid-target-region'
  | 'empty-other-description';

export type { BedSelection, MatchBuildingNode as MatchBuilding } from '../allocation/types';

/** The result counters shown around the picker, taken from a match-options reply. */
export interface BedResultMeta {
  total_valid_beds: number;
  total_buildings: number;
  total_apartments: number;
  total_rooms: number;
  has_more: boolean;
  conflict_examples: unknown[];
  counts: Record<string, unknown> | null;
  data_integrity: Record<string, unknown> | null;
}

export type MatchOptionsReply = BedMatchOptions;
