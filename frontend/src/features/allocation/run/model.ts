// UI-level types owned by the Allocation (run) page: the constraint
// configuration as the page edits and persists it, the normalized summary /
// inbox / result views the page renders, the run-timing anchor, and the
// small UI states (toast, confirm dialog). Wire types stay in
// shared/api/contracts and ../types.ts.
import type { AllocationRun, AllocationRunStatus, RegionInbox } from '../types';

/** The unit selector next to the "maximum search time" input. */
export type MaxSolverUnit = 'seconds' | 'minutes' | 'hours';

/** The constraint keys the page configures (DEFAULT_CONSTRAINTS order). */
export type ConstraintKey =
  | 'sameGender'
  | 'priorityFirst'
  | 'roommatePositiveOnly'
  | 'ReligiousTogether'
  | 'sameReligion'
  | 'roommateMatch'
  | 'sectorMatching'
  | 'avoidYearMix_1_with_3_4'
  | 'avoidAtudaimWithHasmaha';

/** One constraint as the page holds it (and persists it in localStorage). */
export interface ConstraintSetting {
  enabled: boolean;
  strict: boolean;
  critical: boolean;
  weight: number;
}

export type ConstraintSet = Record<ConstraintKey, ConstraintSetting>;

/** A [key, setting] entry, as the condition lists are rendered. */
export type ConstraintEntry = [ConstraintKey, ConstraintSetting];

/**
 * The `constraints` object sent in POST /api/allocation/start/ and carried
 * in the results route state: every key, with critical constraints forced
 * on at weight 0. Shape and values are exactly what the page always sent.
 */
export type EffectiveConstraintConfig = Record<string, ConstraintSetting>;

/** The status badge / header state; 'not_started' is the page's own idle key. */
export type RunStatusKey = 'not_started' | AllocationRunStatus;

/** The population summary (imported -> excluded -> sent to solver) after normalization. */
export interface PopulationSummaryView {
  imported_students: number;
  excluded_accessibility: number;
  excluded_leaving: number;
  excluded_overlap: number;
  excluded_total: number;
  sent_to_solver: number;
  assigned: number | null;
  unassigned: number | null;
}

export type InventoryTypeKey = 'single' | 'couple' | 'family';

export interface InventoryTypeView {
  apartments: number;
  rooms: number;
  total_beds: number;
  occupied_beds: number;
  available_beds: number;
}

export interface StudentsByCategoryView {
  new: number;
  continuing: number;
  transfer: number;
  leaving: number;
}

/** A region as the summary carries it (`{id, name, ...}`). */
export type SummaryRegion = Record<string, unknown>;

/**
 * The summary as the page holds it: the normalized numeric fields, followed
 * by the raw reply spread over them exactly as the page always did (so a
 * field the backend sends wins over the normalized default).
 */
export interface SummaryView {
  total_students: number;
  unassigned_students: number;
  assigned_students: number;
  available_beds: number;
  priority_students: number;
  total_capacity: number;
  occupancy_rate: number;
  population_summary: PopulationSummaryView | null;
  latest_inbox: Record<string, unknown> | null;
  students_by_category: StudentsByCategoryView | null;
  students_by_housing_type: unknown;
  inventory_by_type: Record<InventoryTypeKey, InventoryTypeView> | null;
  region: SummaryRegion | null;
  [key: string]: unknown;
}

/**
 * The latest inbox item (RegionInboxSerializer) as the page holds it: the
 * reply's item spread as received, with its status lower-cased/trimmed.
 * Fields are read defensively (Number(...), typeof) exactly as before, so
 * the view keeps the record shape rather than asserting the serializer's.
 */
export type InboxItemView = Record<string, unknown> & { status: string };

/** Mirrors RegionInbox for readers that want the typed field names. */
export type InboxItemFields = Partial<RegionInbox>;

/**
 * The last server-confirmed search-timing snapshot plus the client clock at
 * the moment it was received; the elapsed display only ever extrapolates
 * from this anchor (AllocationRun.search_started_at), never from how long
 * the page has been open.
 */
export interface SearchTiming {
  maxSearchSeconds: number | null;
  elapsedAtSync: number;
  remainingAtSync: number | null;
  syncedAtClientMs: number;
  live: boolean;
}

/** The result of the run the page shows (from the detail reply or the recovered run). */
export interface RunResultView {
  successful_assignments: number;
  roommate_matches: number;
  conflicts: number;
  assignments: Array<Record<string, unknown>>;
  population_summary: PopulationSummaryView | null;
  solver_status?: string | null;
  optimality_proven?: boolean;
  stopped_early_by_user?: boolean;
  final_search_seconds: number | null;
  run: AllocationRun | undefined;
}

/** One row of the current-result preview table. */
export interface PreviewAssignmentRow {
  student_db_id?: unknown;
  student_id?: unknown;
  bed_id?: unknown;
  student_name?: unknown;
  apartment_code?: unknown;
  room_code?: unknown;
  bed_label?: unknown;
}

/** The preview snapshot fields the panel renders, read from the raw snapshot. */
export interface PreviewSnapshotView {
  assignments: PreviewAssignmentRow[];
  assignedCount: number;
  unassignedCount: number;
  solverStatus: unknown;
  wallTime: number;
}

export type ToastType = 'success' | 'error' | 'info' | 'warning';

export interface ToastState {
  message: string;
  type: ToastType;
}

export interface ConfirmModalState {
  title: string;
  message: string;
  onConfirm: () => void;
}

/** The router state handed to /allocation/results. */
export interface AllocationResultsRouteState {
  result: RunResultView | null;
  summary: SummaryView | null;
  constraints: EffectiveConstraintConfig;
  region: SummaryRegion | null;
  generatedAt: string | null;
}
