// Pure helpers of the Allocation (run) page: the constants the page has
// always used (solver bounds, polling cadences, the default constraints),
// the normalization of the summary / inbox / run replies into the views the
// page renders, the derived run flags, and the formatting of elapsed time
// and dates. No React, no I/O. The allocation itself (constraints'
// meaning, the solver, the results) is entirely the backend's; nothing here
// interprets a constraint - it only carries the configuration the user set.
import type { Id } from '../../../shared/api/contracts';
import type { RegionLike } from '../../../shared/lib/locationNames';
import type { AllocationRun, AllocationRunStatus, RunDetail } from '../types';
import type { AllocationRunStrings } from './AllocationPage.strings';
import type {
  ConstraintEntry,
  ConstraintKey,
  ConstraintSet,
  ConstraintSetting,
  EffectiveConstraintConfig,
  InboxItemView,
  InventoryTypeKey,
  InventoryTypeView,
  MaxSolverUnit,
  PopulationSummaryView,
  PreviewAssignmentRow,
  PreviewSnapshotView,
  RunResultView,
  RunStatusKey,
  SearchTiming,
  SummaryRegion,
  SummaryView,
} from './model';

// ── Constants ────────────────────────────────────────────────

export const MIN_SOLVER_SECONDS = 1;
export const MAX_SOLVER_SECONDS = 36000; // 10 hours
export const DEFAULT_SOLVER_SECONDS = 500;
export const SOLVER_UNIT_TO_SECONDS: Readonly<Record<MaxSolverUnit, number>> = {
  seconds: 1, minutes: 60, hours: 3600,
};

export const LIVE_RUN_STATUSES: readonly string[] = [
  'queued', 'running', 'cancellation_requested', 'stop_and_save_requested',
];

/** Run status is re-read every 3 s while a run is live. */
export const STATUS_POLL_INTERVAL_MS = 3000;
/** The open preview panel refreshes itself silently every 5 s. */
export const PREVIEW_POLL_INTERVAL_MS = 5000;
/** The elapsed-time display extrapolates from the server anchor once a second. */
export const ELAPSED_TICK_MS = 1000;
/** A toast hides itself after 4.5 s. */
export const TOAST_DURATION_MS = 4500;

export const DEFAULT_CONSTRAINTS: Readonly<ConstraintSet> = {
  sameGender:             { enabled: true, strict: true,  critical: true,  weight: 0 },
  priorityFirst:          { enabled: true, strict: true,  critical: true,  weight: 0 },
  roommatePositiveOnly:   { enabled: true, strict: true,  critical: true,  weight: 0 },
  ReligiousTogether:      { enabled: true, strict: true,  critical: true,  weight: 0 },

  sameReligion:           { enabled: true, strict: false, critical: false, weight: 6 },
  roommateMatch:          { enabled: true, strict: false, critical: false, weight: 8 },
  sectorMatching:         { enabled: true, strict: false, critical: false, weight: 7 },
  avoidYearMix_1_with_3_4:{ enabled: true, strict: false, critical: false, weight: 4 },
  avoidAtudaimWithHasmaha:{ enabled: true, strict: false, critical: false, weight: 4 },
};

export const CONSTRAINT_KEYS = Object.keys(DEFAULT_CONSTRAINTS) as ConstraintKey[];

export const ALLOCATION_CONSTRAINTS_STORAGE_KEY = 'dormify_allocation_constraints';

export const INVENTORY_TYPE_KEYS: readonly InventoryTypeKey[] = ['single', 'couple', 'family'];

const EMPTY_INVENTORY_ITEM: InventoryTypeView = {
  apartments: 0, rooms: 0, total_beds: 0, occupied_beds: 0, available_beds: 0,
};

// ── Narrowing ────────────────────────────────────────────────

export function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null;
}

/** A non-empty string or a non-zero number, else null (the `a || b || null` chains). */
export function idOf(value: unknown): Id | null {
  return (typeof value === 'string' || typeof value === 'number') && value ? value : null;
}

/** Accepts a bare payload or a legacy axios-style `{data}` wrapper. */
export function unwrapResponse(res: unknown): unknown {
  if (isRecord(res) && 'data' in res) return res.data;
  return res;
}

/**
 * unwrapResponse for a typed reply: the unwrapped object when it is one,
 * otherwise null (so `response?.field` reads as undefined, as before).
 */
export function unwrapTyped<T extends Record<string, unknown>>(raw: T): T | null {
  const data = unwrapResponse(raw);
  return isRecord(data) ? (data as T) : null;
}

/** The page's historical error-message resolution, ending in the dictionary's unknownError. */
export function describeError(err: unknown, unknownError: string): string {
  if (!err) return unknownError;
  if (typeof err === 'string') return err;
  const response = isRecord(err) ? err.response : undefined;
  const data = isRecord(response) ? response.data : undefined;
  if (typeof data === 'string') return data;
  if (isRecord(data) && data.error) return String(data.error);
  if (isRecord(data) && data.message) return String(data.message);
  if (isRecord(err) && typeof err.message === 'string' && err.message) return err.message;
  return unknownError;
}

/** A 409 from the backend, or any message mentioning "approved", means the allocation was approved. */
export function isApprovedDeleteError(err: unknown, msg: string): boolean {
  const response = isRecord(err) ? err.response : undefined;
  const status = isRecord(response) ? response.status : undefined;
  return status === 409 || (typeof msg === 'string' && msg.toLowerCase().includes('approved'));
}

// ── Summary / inbox normalization ────────────────────────────

export function normalizeInboxStatus(statusValue: unknown): string {
  const s = String(statusValue || '').trim().toLowerCase();
  if (s === 'pending') return 'pending';
  if (s === 'viewed') return 'viewed';
  if (s === 'processed') return 'processed';
  return s;
}

const POPULATION_FIELDS = [
  'imported_students', 'excluded_accessibility', 'excluded_leaving',
  'excluded_overlap', 'excluded_total', 'sent_to_solver',
] as const;

export function safePopulationSummary(raw: unknown): PopulationSummaryView | null {
  if (!isRecord(raw)) return null;
  const hasAnyField = POPULATION_FIELDS.some((key) => raw[key] !== undefined);
  if (!hasAnyField) return null;

  return {
    imported_students:      Number(raw.imported_students) || 0,
    excluded_accessibility: Number(raw.excluded_accessibility) || 0,
    excluded_leaving:       Number(raw.excluded_leaving) || 0,
    excluded_overlap:       Number(raw.excluded_overlap) || 0,
    excluded_total:         Number(raw.excluded_total) || 0,
    sent_to_solver:         Number(raw.sent_to_solver) || 0,
    assigned:   raw.assigned !== undefined ? Number(raw.assigned) || 0 : null,
    unassigned: raw.unassigned !== undefined ? Number(raw.unassigned) || 0 : null,
  };
}

function inventoryByType(inventory: Record<string, unknown>): Record<InventoryTypeKey, InventoryTypeView> {
  const out = {} as Record<InventoryTypeKey, InventoryTypeView>;
  for (const key of INVENTORY_TYPE_KEYS) {
    const raw = inventory[key];
    const item = isRecord(raw) ? raw : {};
    out[key] = {
      apartments:    Number(item.apartments) || 0,
      rooms:         Number(item.rooms) || 0,
      total_beds:    Number(item.total_beds) || 0,
      occupied_beds: Number(item.occupied_beds) || 0,
      available_beds:Number(item.available_beds) || 0,
    };
  }
  return out;
}

/**
 * Normalizes the summary reply; throws the dictionary's malformedSummary
 * message when the reply is not an object. The raw reply is spread last,
 * exactly as the page always did: a field the backend sends wins over its
 * normalized default.
 */
export function safeSummary(raw: unknown, malformedMessage: string): SummaryView {
  const data = unwrapResponse(raw);
  if (!isRecord(data)) throw new Error(malformedMessage);

  const category = data.students_by_category;
  const inventory = data.inventory_by_type;
  const normalized: SummaryView = {
    total_students:      Number(data.total_students) || 0,
    unassigned_students: Number(data.unassigned_students) || 0,
    assigned_students:   Number(data.assigned_students) || 0,
    available_beds:      Number(data.available_beds) || 0,
    priority_students:   Number(data.priority_students) || 0,
    total_capacity:      Number(data.total_capacity) || 0,
    occupancy_rate:      Number(data.occupancy_rate) || 0,
    population_summary:  safePopulationSummary(data.population_summary),
    latest_inbox:        isRecord(data.latest_inbox) ? data.latest_inbox : null,
    students_by_category: isRecord(category)
      ? {
          new:        Number(category.new) || 0,
          continuing: Number(category.continuing) || 0,
          transfer:   Number(category.transfer) || 0,
          leaving:    Number(category.leaving) || 0,
        }
      : null,
    students_by_housing_type: data.students_by_housing_type || null,
    inventory_by_type: isRecord(inventory) ? inventoryByType(inventory) : null,
    region: isRecord(data.region) ? data.region : null,
  };
  return { ...normalized, ...data } as SummaryView;
}

export function safeInbox(raw: unknown): InboxItemView | null {
  const data = unwrapResponse(raw);
  if (!isRecord(data)) return null;
  const inbox = data.inbox;
  if (!isRecord(inbox)) return null;
  return {
    ...inbox,
    status: normalizeInboxStatus(inbox.status),
  };
}

export function inboxItemId(item: InboxItemView | null | undefined): Id | null {
  return idOf(item?.id);
}

/** The inbox item's received date in the interface locale, '-' when missing. */
export function formatInboxDate(created: unknown, locale: string): string {
  if (!created) return '-';
  const value = typeof created === 'string' || typeof created === 'number' ? created : String(created);
  return new Date(value).toLocaleDateString(locale);
}

// ── Region ───────────────────────────────────────────────────

/** `summary.region.id`, as the active-run lookup has always been scoped. */
export function regionIdOf(region: SummaryRegion | null | undefined): Id | null {
  return idOf(region?.id);
}

function summaryRegionIdOrName(summary: SummaryView | null): Id | null {
  return idOf(summary?.region?.id) || idOf(summary?.region?.name) || null;
}

/**
 * The region a run starts for: the user's own region (AuthContext), falling
 * back to the summary's region id/name. An object-shaped region value is
 * read defensively (id / name / region), as the page always did.
 */
export function resolveRegionId(regionValue: unknown, summary: SummaryView | null): Id | null {
  if (!regionValue) return summaryRegionIdOrName(summary);
  if (typeof regionValue === 'string' || typeof regionValue === 'number') return regionValue;
  if (typeof regionValue === 'object') {
    const region = regionValue as Record<string, unknown>;
    return idOf(region.id) || idOf(region.name) || idOf(region.region) || null;
  }
  return summaryRegionIdOrName(summary);
}

/** The {id, name} slice localizeRegionName reads. */
export function regionLikeOf(region: SummaryRegion | null | undefined): RegionLike | null {
  if (!region) return null;
  return {
    id: idOf(region.id),
    name: typeof region.name === 'string' ? region.name : null,
  };
}

/** The "upper dorms" region swaps the priority card's texts for the ANIR ones. */
export function isUpperDormRegion(summary: SummaryView | null): boolean {
  return summary?.region?.id === 'gush-elyon';
}

// ── Max search time ("זמן חיפוש מרבי") ───────────────────────

/**
 * Validates the input against the same bounds the backend enforces
 * (MIN_USER_SOLVER_TIME_SECONDS / MAX_USER_SOLVER_TIME_SECONDS in
 * allocation/solver.py) so an invalid value is caught before ever reaching
 * the server. Returns the message, or '' when valid.
 */
export function validateMaxSolverTime(
  value: string,
  unit: MaxSolverUnit,
  t: Pick<AllocationRunStrings, 'maxSearchTimeInvalid' | 'maxSearchTimeTooLow' | 'maxSearchTimeTooHigh'>
): string {
  const numeric = Number(value);
  if (!value || !Number.isFinite(numeric) || numeric <= 0) {
    return t.maxSearchTimeInvalid;
  }
  const seconds = numeric * (SOLVER_UNIT_TO_SECONDS[unit] || 1);
  if (seconds < MIN_SOLVER_SECONDS) return t.maxSearchTimeTooLow;
  if (seconds > MAX_SOLVER_SECONDS) return t.maxSearchTimeTooHigh;
  return '';
}

/** The input converted to seconds (the max_solver_seconds payload value), null when not a positive number. */
export function maxSolverSeconds(value: string, unit: MaxSolverUnit): number | null {
  const numeric = Number(value);
  if (!Number.isFinite(numeric) || numeric <= 0) return null;
  return numeric * (SOLVER_UNIT_TO_SECONDS[unit] || 1);
}

/** m:ss, or h:mm:ss once an hour has passed. */
export function formatElapsed(secs: unknown): string {
  const total = Math.max(0, Math.round(Number(secs) || 0));
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  if (h > 0) {
    return `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
  }
  return `${m}:${String(s).padStart(2, '0')}`;
}

// ── Constraints (the configuration the user sets; not their semantics) ──

/**
 * Merges a parsed localStorage value over the defaults, key by key, the
 * way `{...default, ...(saved[key] || {})}` always did: a null store throws
 * (the caller falls back to the defaults), a primitive store yields no
 * overrides, an object entry contributes its own fields.
 */
export function mergeStoredConstraints(parsed: unknown): ConstraintSet {
  if (parsed === null || parsed === undefined) {
    throw new TypeError(`Cannot read properties of ${String(parsed)}`);
  }
  const entries = CONSTRAINT_KEYS.map((key): ConstraintEntry => {
    const stored = isRecord(parsed) ? parsed[key] : undefined;
    const overrides = isRecord(stored) ? stored : {};
    return [key, { ...DEFAULT_CONSTRAINTS[key], ...overrides } as ConstraintSetting];
  });
  return Object.fromEntries(entries) as ConstraintSet;
}

export function toggleConstraint(prev: ConstraintSet, key: ConstraintKey): ConstraintSet {
  const current = prev[key];
  if (!current || current.critical) return prev;
  return { ...prev, [key]: { ...current, enabled: !current.enabled } };
}

/** Clamps the slider value to 0..10 (0 when not numeric). */
export function clampWeight(nextWeight: string | number): number {
  const parsed = Number(nextWeight);
  return Number.isFinite(parsed) ? Math.max(0, Math.min(10, parsed)) : 0;
}

export function withConstraintWeight(
  prev: ConstraintSet,
  key: ConstraintKey,
  nextWeight: string | number
): ConstraintSet {
  const w = clampWeight(nextWeight);
  const current = prev[key];
  if (!current || current.critical) return prev;
  return { ...prev, [key]: { ...current, weight: w } };
}

/** Critical constraints first, then the optimization preferences (object order). */
export function splitConstraints(constraints: ConstraintSet): {
  hard: ConstraintEntry[];
  flexible: ConstraintEntry[];
} {
  const entries = Object.entries(constraints) as ConstraintEntry[];
  return {
    hard: entries.filter(([, v]) => v.critical),
    flexible: entries.filter(([, v]) => !v.critical),
  };
}

/**
 * The `constraints` object the page sends with a run (and hands to the
 * results page): critical constraints forced on at weight 0, flexible ones
 * with their toggle and weight. Byte-identical to what it always sent.
 */
export function buildEffectiveConfig(constraints: ConstraintSet): EffectiveConstraintConfig {
  const out: EffectiveConstraintConfig = {};
  Object.entries(constraints).forEach(([k, v]) => {
    out[k] = {
      enabled: v.critical ? true : !!v.enabled,
      strict:  !!v.strict,
      critical: !!v.critical,
      weight:  v.critical ? 0 : Number(v.weight) || 0,
    };
  });
  return out;
}

/** The dictionary entry for a constraint key (or its description), when it exists. */
export function conditionText(t: AllocationRunStrings, key: string): string | undefined {
  const value = (t as Record<string, unknown>)[key];
  return typeof value === 'string' ? value : undefined;
}

// ── Run timing / progress ────────────────────────────────────

/** Anchors the timing display to the backend's run timing fields. */
export function toSearchTiming(runData: AllocationRun | null | undefined): SearchTiming | null {
  if (!runData) return null;
  const max = runData.max_search_seconds != null ? Number(runData.max_search_seconds) : null;
  const elapsed = Number(runData.elapsed_search_seconds) || 0;
  const remaining = runData.remaining_search_seconds != null ? Number(runData.remaining_search_seconds) : null;
  return {
    maxSearchSeconds: max,
    elapsedAtSync: elapsed,
    remainingAtSync: remaining,
    syncedAtClientMs: Date.now(),
    live: LIVE_RUN_STATUSES.includes(runData.status),
  };
}

/** Bar = elapsed / configured max search time only - never an optimality estimate. */
export function progressPercent(searchTiming: SearchTiming | null, displayElapsed: number): number {
  return searchTiming?.maxSearchSeconds
    ? Math.min(100, Math.round((displayElapsed / searchTiming.maxSearchSeconds) * 100))
    : 0;
}

// ── Run results ──────────────────────────────────────────────

/** The result shown once polling sees the run complete. */
export function buildCompletedResult(data: RunDetail, runData: AllocationRun | undefined): RunResultView {
  return {
    successful_assignments: data.successful_assignments ?? runData?.successful_assignments ?? 0,
    roommate_matches:       data.roommate_matches ?? runData?.roommate_matches ?? 0,
    conflicts:              typeof data.conflicts === 'number' ? data.conflicts : (runData?.conflicts ?? 0),
    assignments:            data.assignments ?? [],
    population_summary:     safePopulationSummary(data.population_summary),
    solver_status:          data.solver_status ?? null,
    optimality_proven:      Boolean(data.optimality_proven),
    stopped_early_by_user:  Boolean(data.stopped_early_by_user),
    final_search_seconds:   runData?.elapsed_search_seconds ?? null,
    run:                    runData,
  };
}

/**
 * The result restored for a completed run that still has assignments in
 * the database: assigned/unassigned come from the current summary, the
 * rest from the run detail.
 */
export function buildRecoveredResult(
  detail: RunDetail,
  assignedNow: number,
  currentSummary: SummaryView | null
): RunResultView {
  return {
    successful_assignments: assignedNow,
    roommate_matches:       detail.roommate_matches ?? detail.run?.roommate_matches ?? 0,
    conflicts:              Number(currentSummary?.unassigned_students) || 0,
    assignments:            detail.assignments ?? [],
    population_summary:     safePopulationSummary(detail.population_summary),
    final_search_seconds:   detail.run?.elapsed_search_seconds ?? null,
    run:                    detail.run,
  };
}

export interface RunFlagsInput {
  isRunning: boolean;
  isStopping: boolean;
  isStoppingSave: boolean;
  runId: Id | null;
  runStatus: AllocationRunStatus | null;
  result: RunResultView | null;
  canRun: boolean;
  summary: SummaryView | null;
}

export interface RunFlags {
  currentAssignedStudents: number;
  currentUnassignedStudents: number;
  hasCurrentAllocation: boolean;
  /** Unassigned students exist, so a run can be started. */
  hasStudents: boolean;
  statusKey: RunStatusKey;
  /** Cancel and Stop & Save are mutually exclusive once either is in flight. */
  isStopRequested: boolean;
  showCancelBtn: boolean;
  showStopSaveBtn: boolean;
  showPreviewBtn: boolean;
  showDelBtn: boolean;
}

export function computeStatusKey({
  isRunning, isStopping, isStoppingSave, runStatus, hasCurrentAllocation,
}: Pick<RunFlagsInput, 'isRunning' | 'isStopping' | 'isStoppingSave' | 'runStatus'> & {
  hasCurrentAllocation: boolean;
}): RunStatusKey {
  if (isRunning && isStopping) return 'cancellation_requested';
  if (isRunning && isStoppingSave) return 'stop_and_save_requested';
  if (isRunning) return runStatus || 'running';
  if (!hasCurrentAllocation) return 'not_started';
  if (runStatus === 'completed') return 'completed';
  return 'not_started';
}

/** The flags that drive the header badge and the controls bar. */
export function deriveRunFlags(input: RunFlagsInput): RunFlags {
  const { isRunning, isStopping, isStoppingSave, runId, runStatus, result, canRun, summary } = input;
  const currentAssignedStudents = Number(summary?.assigned_students) || 0;
  const currentUnassignedStudents = Number(summary?.unassigned_students) || 0;
  const hasCurrentAllocation = currentAssignedStudents > 0;
  const hasStudents = currentUnassignedStudents > 0;
  // Cancel ("בטל הרצה") and Stop & Save ("עצור ושמור תוצאה") are mutually
  // exclusive requests once one is in flight - both hide as soon as either
  // isStopping or isStoppingSave becomes true, matching the backend's own
  // race guard (whichever request wins the row lock first "claims" the
  // stop; the other gets 409).
  const isStopRequested = isStopping || isStoppingSave;
  return {
    currentAssignedStudents,
    currentUnassignedStudents,
    hasCurrentAllocation,
    hasStudents,
    statusKey: computeStatusKey({ isRunning, isStopping, isStoppingSave, runStatus, hasCurrentAllocation }),
    isStopRequested,
    showCancelBtn: isRunning && !isStopRequested && Boolean(runId) && canRun,
    showStopSaveBtn: isRunning && !isStopRequested && Boolean(runId) && canRun,
    showPreviewBtn: isRunning && Boolean(runId),
    showDelBtn:
      hasCurrentAllocation &&
      runStatus === 'completed' &&
      !isRunning &&
      Boolean(result) &&
      Boolean(runId) &&
      canRun,
  };
}

/** The completed/started timestamp of the shown result, only while an allocation is stored. */
export function lastRunTimestamp(hasCurrentAllocation: boolean, result: RunResultView | null): string | null {
  return hasCurrentAllocation
    ? (result?.run?.completed_at || result?.run?.started_at || null)
    : null;
}

export function formatLastRunDate(timestamp: string | null, locale: string): string | null {
  return timestamp
    ? new Date(timestamp).toLocaleString(locale, {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      })
    : null;
}

/** The population card shows the run's own summary once an allocation is stored, else the page summary's. */
export function activePopulationSummary(
  hasCurrentAllocation: boolean,
  result: RunResultView | null,
  summary: SummaryView | null
): PopulationSummaryView | null {
  const active = (hasCurrentAllocation && result?.population_summary)
    ? result.population_summary
    : summary?.population_summary;
  return active || null;
}

// ── Inventory ────────────────────────────────────────────────

export function inventoryItem(
  inventory: Record<InventoryTypeKey, InventoryTypeView>,
  key: InventoryTypeKey
): InventoryTypeView {
  return inventory[key] || EMPTY_INVENTORY_ITEM;
}

export function occupancyPercent(item: InventoryTypeView): number {
  const total = item.total_beds || 0;
  const available = item.available_beds || 0;
  return total > 0 ? Math.round(((total - available) / total) * 100) : 0;
}

// ── Current-result preview ───────────────────────────────────

export function readPreviewSnapshot(snapshot: Record<string, unknown> | null): PreviewSnapshotView | null {
  if (!snapshot) return null;
  const assignments = Array.isArray(snapshot.assignments)
    ? (snapshot.assignments as PreviewAssignmentRow[])
    : [];
  return {
    assignments,
    assignedCount: typeof snapshot.assigned_count === 'number' ? snapshot.assigned_count : assignments.length,
    unassignedCount: typeof snapshot.unassigned_count === 'number' ? snapshot.unassigned_count : 0,
    solverStatus: snapshot.solver_status,
    wallTime: Number(snapshot.wall_time_seconds) || 0,
  };
}

/** The table row key: the student's db id, else bed+student. */
export function previewRowKey(row: PreviewAssignmentRow): string {
  return row.student_db_id != null ? String(row.student_db_id) : `${row.bed_id}-${row.student_id}`;
}

/** Renders a preview cell exactly as `{row.field}` did (strings/numbers; nothing otherwise). */
export function previewCell(value: unknown): string | number | null {
  return typeof value === 'string' || typeof value === 'number' ? value : null;
}
