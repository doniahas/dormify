// Allocation payloads (backend/api/views/allocation.py, analytics.py,
// imports.py, assisted.py and the read-model builders under
// backend/api/domains/allocation, assisted and matching).
//
// Row shapes are declared as `type` aliases on purpose: object-literal types
// keep an implicit index signature, so a typed row still satisfies the
// Record<string, unknown> parameters of the defensive page helpers.
import type {
  AllocationRun,
  AllocationRunStatus,
  Gender,
  HousingType,
  Id,
  IsoDateTime,
  Region,
  RegionInbox,
  RegionInboxStatus,
  Religion,
  Religious,
  StudentCategory,
} from '../../shared/api/contracts';

export type { AllocationRun, AllocationRunStatus, RegionInbox, RegionInboxStatus };

/** Body of POST /api/allocation/start/ and /api/allocation/run/ (parse_allocation_run_request). */
export interface AllocationRunPayload {
  constraints?: Record<string, unknown>;
  max_solver_seconds?: number;
  include_assigned?: boolean;
  allocation_scope?: string;
  [key: string]: unknown;
}

/**
 * The population accounting the solver reports per run
 * (results.population_summary and RunDetail.population_summary). The
 * allocation summary carries the first seven keys only.
 */
export type PopulationSummary = {
  imported_students: number;
  excluded_accessibility: number;
  excluded_leaving: number;
  excluded_overlap: number;
  excluded_total: number;
  sent_to_solver: number;
  sent_to_solver_student_ids: number[];
  assigned: number;
  unassigned: number;
};

export type SummaryPopulation = Omit<PopulationSummary, 'assigned' | 'unassigned'>;

/** One assignment row of GET /api/allocation/runs/<id>/ (build_run_assignment_rows). */
export type RunAssignmentRow = {
  student_id: string;
  student_name: string;
  full_name: string;
  first_name: string;
  last_name: string;
  gender: Gender | string;
  requested_religion: Religion | string;
  religion: Religion | string;
  religious: Religious | string;
  placement_sector: string;
  sector: string;
  /** Building.number is nullable. */
  building: number | null;
  building_number: number | null;
  apartment: string;
  apartment_number: string;
  room: string;
  room_name: string;
  bed: string;
  bed_label: string;
  dorm_type: string;
  region: string;
  /** '' when the assignment has no region. */
  region_id: Region['id'] | '';
  assignment_type: string;
  assignment_status: string;
  /** '' when the assignment carries no timestamp. */
  assigned_at: IsoDateTime | '';
};

/** 202 body of POST /api/allocation/start/. */
export interface StartRunResponse {
  success?: boolean;
  message?: string;
  run_id?: number;
  run?: AllocationRun;
  /** Present on the 409 failure body only. */
  region?: Region['id'];
  error?: string;
  error_code?: string;
  [key: string]: unknown;
}

/** `result` of the synchronous run (POST /api/allocation/run/). */
export type SyncRunResult = {
  students_total_in_region: number;
  students_available_for_allocation: number;
  students_processed: number;
  successful_assignments: number;
  roommate_matches: number;
  mutual_roommate_matches: number;
  one_sided_roommate_matches: number;
  conflicts: number;
  solver_status: string;
  objective_value: number | null;
  wall_time: number | null;
  warnings: string[];
  /** Database ids of the students the solver found no feasible bed for. */
  students_with_no_feasible_beds: number[];
  anier_building_179_diagnostics: Record<string, unknown>;
  population_summary: PopulationSummary;
  assignments: RunAssignmentRow[];
  run: AllocationRun;
};

/** `result` of POST /api/allocation/runs/<id>/retry-unassigned/. */
export type RetryResult = {
  retry_of_run_id: number;
  retried_student_count: number;
  successful_assignments: number;
  conflicts: number;
  assignments: RunAssignmentRow[];
  [key: string]: unknown;
};

/** POST /api/allocation/run/ (synchronous run) and retry-unassigned. */
export interface RunResultResponse extends StartRunResponse {
  result?: SyncRunResult | RetryResult | Record<string, unknown>;
  error_type?: string;
}

/** GET /api/allocation/runs/<id>/ */
export interface RunDetail {
  run?: AllocationRun;
  assignments?: RunAssignmentRow[];
  successful_assignments?: number;
  roommate_matches?: number;
  conflicts?: number;
  warnings?: string[];
  anier_building_179_diagnostics?: Record<string, unknown>;
  /** Empty for runs recorded before the population accounting existed. */
  population_summary?: Partial<PopulationSummary>;
  solver_status?: string | null;
  optimality_proven?: boolean;
  stopped_early_by_user?: boolean;
  error?: string;
  [key: string]: unknown;
}

/** One assignment of a live solver snapshot (allocation/solver.py _build_assignment_payload). */
export type SnapshotAssignment = {
  student_db_id: number;
  student_id: string;
  student_name: string;
  apartment_id: number;
  apartment_code: string;
  room_id: number;
  room_code: string;
  bed_id: number;
  bed_label: string;
  [key: string]: unknown;
};

/** AllocationRun.live_snapshot while a run is RUNNING. */
export type LiveSnapshot = {
  sequence: number;
  assignments: SnapshotAssignment[];
  assigned_count: number;
  unassigned_count: number;
  objective_value: number;
  best_objective_bound: number;
  absolute_gap: number;
  relative_gap: number;
  wall_time_seconds: number;
  solver_status: string;
  captured_at: IsoDateTime;
};

/** GET /api/allocation/runs/<id>/preview/ */
export interface RunPreview {
  available: boolean;
  snapshot: LiveSnapshot | null;
  error?: string;
}

/** stop / stop-and-save / delete */
export interface RunActionResponse {
  run_id?: number;
  status?: AllocationRunStatus | string;
  message?: string;
  deleted_assignments?: number;
  error?: string;
}

export interface ActiveRunResponse {
  run: AllocationRun | null;
}

export interface AllocationHistory {
  runs: AllocationRun[];
}

/** One assignment row of GET /api/allocation/results/ (build_results_assignment_rows). */
export type ResultsAssignmentRow = RunAssignmentRow & {
  housing_type: HousingType | null;
  housing_type_display: string;
  religion_display: string;
  is_priority: boolean;
  apartment_type: string;
  apartment_type_display: string;
  apartment_category: string;
  apartment_category_display: string;
  dorm_type_id: number | null;
};

/** One unassigned student of GET /api/allocation/results/. */
export type UnassignedStudentRow = {
  student_db_id: number;
  student_id: string;
  business_partner_id: string;
  student_name: string;
  full_name: string;
  first_name: string;
  last_name: string;
  gender: Gender | string;
  gender_display: string;
  housing_type: HousingType | null;
  housing_type_display: string;
  requested_religion: Religion | string;
  religion: Religion | string;
  religion_display: string;
  religious: Religious | string;
  placement_sector: string;
  placement_sector_display: string;
  is_priority: boolean;
  priority_reason: string;
  category: StudentCategory | string;
  category_display: string;
  accepted_dorm_type_id: number | null;
  accepted_dorm_type: string;
  region_id: Region['id'] | '';
  region: string;
  special_statuses: string[];
  unassigned_reason: string;
};

/** One free bed of GET /api/allocation/results/. */
export type AvailableBedRow = {
  bed_id: number;
  bed: string;
  bed_label: string;
  room_id: number;
  room: string;
  room_name: string;
  room_capacity: number;
  apartment_id: number;
  apartment: string;
  apartment_number: string;
  apartment_type: string;
  apartment_type_display: string;
  apartment_category: string;
  apartment_category_display: string;
  is_reserved: boolean;
  building_id: number;
  /** Building.number is nullable. */
  building: number | null;
  building_number: number | null;
  building_gender_restriction: string;
  dorm_type_id: number | null;
  dorm_type: string;
  region_id: Region['id'] | '';
  region: string;
};

export type InventoryBreakdownRow = {
  category: string;
  category_display: string;
  apartment_type: string;
  apartment_type_display: string;
  free_beds: number;
};

/** One (dorm type, gender, housing type) group of results.unassigned_analysis. */
export type UnassignedAnalysisGroup = {
  accepted_dorm_type_id: number | null;
  accepted_dorm_type_code: number | null;
  accepted_dorm_type_name: string;
  gender: Gender | string;
  housing_type: HousingType | null;
  housing_type_display: string;
  student_count: number;
  physically_free_beds_in_accepted_dorm: number;
  compatible_free_beds: number;
  reason_code: string;
  inventory_breakdown: InventoryBreakdownRow[];
};

/** GET /api/allocation/results/ */
export interface AllocationResults {
  counts?: { assigned: number; unassigned: number; available_beds: number };
  /** Legacy alias of counts.assigned. */
  count?: number;
  assignments?: ResultsAssignmentRow[];
  unassigned_students?: UnassignedStudentRow[];
  available_beds?: AvailableBedRow[];
  unassigned_analysis?: UnassignedAnalysisGroup[];
  [key: string]: unknown;
}

/** GET /api/allocation/status/ - legacy, not routed in api/urls.py. */
export interface AllocationStatus {
  status?: string;
  run?: AllocationRun | null;
  region?: Record<string, unknown> | string | null;
  error?: string;
  [key: string]: unknown;
}

/** GET/PUT /api/allocation/conditions/ - legacy, not routed in api/urls.py. */
export interface AllocationConditions {
  conditions?: Record<string, unknown>;
  region?: Record<string, unknown> | string | null;
  message?: string;
  error?: string;
  [key: string]: unknown;
}

export type InventoryTypeTotals = {
  apartments: number;
  rooms: number;
  total_beds: number;
  occupied_beds: number;
  available_beds: number;
};

/** GET /api/allocation/summary/ (analytics.allocation_summary) */
export interface AllocationSummary {
  /** null for a central admin viewing the whole system. */
  region?: { id: Region['id']; name: string } | null;
  total_students?: number;
  unassigned_students?: number;
  assigned_students?: number;
  available_beds?: number;
  priority_students?: number;
  total_capacity?: number;
  occupancy_rate?: number;
  students_by_category?: Record<StudentCategory, number>;
  students_by_housing_type?: Record<string, number>;
  inventory_by_type?: Record<'single' | 'couple' | 'family', InventoryTypeTotals>;
  population_summary?: SummaryPopulation;
  latest_inbox?: RegionInbox | null;
  latest_run?: AllocationRun | null;
  [key: string]: unknown;
}

export interface InboxResponse {
  inbox: RegionInbox | null;
  message?: string;
  error?: string;
  errorEn?: string;
}

// Assisted allocation workbench (backend/api/views/assisted.py,
// backend/api/domains/assisted).

export interface AssistedQueueParams {
  region?: Id;
  tab?: string;
  search?: string;
  gender?: string;
  [key: string]: string | number | boolean | null | undefined;
}

export type AssistedGroup = 'accessibility' | 'unassigned' | 'resolved' | 'transfer_pending' | string;

/** One queue row (assisted_student_row); also `student` of the detail reply. */
export type AssistedStudentRow = {
  student_db_id: number;
  student_id: string;
  full_name: string;
  first_name: string;
  last_name: string;
  gender: Gender | string;
  gender_display: string;
  accepted_dorm_type_id: number | null;
  accepted_dorm_type: string;
  housing_type: HousingType | null;
  housing_type_display: string;
  requested_religion: Religion | string;
  religion_display: string;
  region_id: Region['id'] | '';
  region: string;
  is_priority: boolean;
  priority_reason: string;
  accessibility_flag: boolean;
  /** Decimal serialized as a string. */
  disability_percent: string | null;
  medical_reason: string;
  special_statuses: string[];
  group: AssistedGroup;
  is_transfer_requested: boolean;
};

export type AssistedCounts = {
  accessibility_pending: number;
  unassigned: number;
  resolved: number;
  transfer_requested: number;
  needs_placement: number;
};

export interface AssistedQueue {
  students: AssistedStudentRow[];
  counts?: AssistedCounts;
  /** null for a central admin with no region filter. */
  region_id?: Region['id'] | null;
  region_name?: string | null;
  [key: string]: unknown;
}

/** Why a student is still unassigned (shares the analysis-group fields). */
export type AssistedReason = {
  reason_code: string;
  physically_free_beds_in_accepted_dorm: number;
  compatible_free_beds: number;
  inventory_breakdown: InventoryBreakdownRow[];
};

/** The student's live placement (transfers.services._assignment_snapshot). */
export type AssistedPlacement =
  | { assigned: false }
  | {
      assigned: true;
      assignment_id: number | null;
      region_id: Region['id'] | null;
      region_name: string | null;
      building_id: number;
      /** Building.number is nullable. */
      building_number: number | null;
      apartment_id: number;
      apartment_number: string;
      room_id: number;
      room_name: string;
      bed_id: number | null;
      bed_label: string | null;
    };

export type AssistedHistoryEntry = {
  actor_name: string;
  created_at: IsoDateTime;
  note: string;
  overridden_rules: unknown[];
  [key: string]: unknown;
};

export type RoommateRequest = {
  name: string;
  mutual: boolean;
  [key: string]: unknown;
};

export interface AssistedStudentDetail {
  student?: AssistedStudentRow;
  roommate_requests?: RoommateRequest[];
  /** null while a transfer is pending or the student is already placed. */
  reason?: AssistedReason | null;
  history?: AssistedHistoryEntry[];
  current_placement?: AssistedPlacement | null;
  pending_transfer_request?: Record<string, unknown> | null;
  error?: string;
  [key: string]: unknown;
}

export interface AssistedRecommendationParams {
  [key: string]: string | number | boolean | null | undefined;
}

/** A rule an assisted placement would break (ranking.override_violations / override-check). */
export type OverrideViolation = {
  code: string;
  label: string;
  overridable: boolean;
  consequence: string;
  [key: string]: unknown;
};

export interface AssistedRecommendations {
  /** The match tree in assisted mode; empty with feasible=false when already placed. */
  candidates?: MatchTree & { feasible?: boolean };
  config_opportunities?: Array<Record<string, unknown>>;
  has_unsafe_config_candidates?: boolean;
  accepted_dorm_type?: { id: number; name: string } | null;
  already_assigned?: boolean;
  transfer_pending?: boolean;
  reason?: string | null;
  error?: string;
  [key: string]: unknown;
}

export interface OverrideCheck {
  violations?: OverrideViolation[];
  blocked?: boolean;
  requires_override?: boolean;
  error?: string;
}

export interface AssistedAssignResponse {
  message?: string;
  assignment_id?: number;
  overridden_rules?: unknown[];
  violations?: OverrideViolation[];
  error?: string;
  [key: string]: unknown;
}

// The building-paged hierarchical match tree (backend/api/domains/matching/
// ranking.py) shared by match-options, request feasibility and the assisted
// recommendations. BedMatchPicker (allocation/BedMatchPicker.jsx) renders it;
// the component stays JavaScript, so its props are declared here.

/** A ranking reason (ranking._reason): a stable code plus its fixed Hebrew label. */
export type MatchReason = {
  code: string;
  label: string;
};

/** A current resident of an apartment, with matching-internal keys stripped. */
export type MatchResident = {
  id: number;
  student_id: string;
  full_name: string;
  city: string | null;
  religion: Religion | string | null;
  religion_display: string | null;
  placement_sector: string | null;
  sector_display: string | null;
  study_points: number | null;
  housing_type: HousingType | null;
  [key: string]: unknown;
};

export type MatchBedNode = {
  bed_id: number;
  bed_label: string;
  is_occupied: boolean;
  occupant_name: string | null;
  is_selectable: boolean;
};

export type MatchRoomNode = {
  room_id: number;
  room_name: string;
  capacity: number;
  occupied_beds_count: number;
  available_beds_count: number;
  capacity_free_count: number;
  missing_bed_records: number;
  beds: MatchBedNode[];
};

export type MatchApartmentNode = {
  apartment_id: number;
  apartment_number: string;
  apartment_gender: string;
  apartment_type: string;
  residents: MatchResident[];
  match_level: string;
  recommendation_level: string;
  recommendation_label: string;
  recommendation_rank: number;
  matched_reasons: MatchReason[];
  warnings: MatchReason[];
  historical_reasons: MatchReason[];
  available_bed_count: number;
  capacity_free_count: number;
  missing_bed_records: number;
  room_count: number;
  has_roommate_match: boolean;
  rooms: MatchRoomNode[];
  /** Assisted mode only. */
  assisted_status?: string;
  assisted_status_label?: string;
  override_violations?: OverrideViolation[];
  [key: string]: unknown;
};

/** One building node of a match-options tree, with its apartment/room/bed subtree. */
export type MatchBuildingNode = {
  building_id: number;
  building_number: number | null;
  building_name: string;
  region: Region['id'] | null;
  region_name: string | null;
  dorm_type: string | null;
  dorm_type_id: number | null;
  apartment_count: number;
  room_count: number;
  available_bed_count: number;
  capacity_free_count: number;
  missing_bed_records: number;
  recommendation_level: string;
  recommendation_label: string;
  recommendation_rank: number;
  has_roommate_match: boolean;
  top_reasons: MatchReason[];
  recommended_bed_count: number;
  roommate_bed_count: number;
  warning_free_bed_count: number;
  apartments: MatchApartmentNode[];
  [key: string]: unknown;
};

/** A room the student cannot take, with the failed constraints spelled out. */
export type MatchConflictExample = {
  building: number | null;
  building_id: number;
  apartment: string;
  apartment_id: number;
  room: string;
  room_id: number;
  region_name: string | null;
  /** Hard-constraint labels (plain strings, unlike the reason lists). */
  conflicts: string[];
  warnings: MatchReason[];
  matched_reasons: MatchReason[];
  historical_reasons: MatchReason[];
  residents: MatchResident[];
  diagnostic: Record<string, unknown>;
};

/** Exact per-filter-chip counts over every selectable bed. */
export type MatchCounts = {
  all: number;
  best_match: number;
  empty: number;
  warning_free: number;
  with_warnings: number;
  with_roommate: number;
  fully_empty: number;
};

export type MatchDataIntegrity = {
  rooms_missing_bed_records: number;
  missing_bed_records: number;
  rooms_with_extra_bed_records: number;
};

/**
 * The paged tree envelope: buildings -> apartments -> rooms -> beds, where
 * limit/offset page BUILDINGS, not beds. `total_valid` is the legacy alias of
 * `total_valid_beds`.
 */
export type MatchTree = {
  buildings: MatchBuildingNode[];
  loaded_buildings?: number;
  total_buildings?: number;
  total_apartments?: number;
  total_rooms?: number;
  total_valid_beds: number;
  total_valid?: number;
  /** null for the assisted recommendations, which are not paged. */
  limit?: number | null;
  offset?: number;
  has_more: boolean;
  next_offset: number | null;
  conflict_examples?: MatchConflictExample[];
  counts?: MatchCounts | null;
  data_integrity?: MatchDataIntegrity | null;
  /** Assisted mode only. */
  assisted_status_counts?: Record<string, number>;
};

/**
 * The selection BedMatchPicker hands to onSelectBed (buildBedSelection): the
 * complete location path plus the reasons, so every consumer can show where
 * the bed is without re-walking the tree.
 */
export interface BedSelection {
  bed_id: Id;
  bed_label?: string | null;
  bed_display?: string;
  room_id: Id;
  room?: string | number | null;
  room_name?: string | null;
  room_capacity?: number;
  occupied_beds?: number;
  available_beds?: number;
  single_bed_room?: boolean;
  apartment_id?: Id;
  apartment?: string | number | null;
  apartment_gender?: string | null;
  building_id?: Id;
  building?: string | number | null;
  building_name?: string | null;
  region_name?: string | null;
  dorm_type?: string | null;
  recommendation_level?: string | null;
  recommendation_label?: string | null;
  matched_reasons?: unknown[];
  warnings?: unknown[];
  historical_reasons?: unknown[];
  is_selectable?: boolean;
  [key: string]: unknown;
}

export interface BedMatchPickerProps {
  buildings?: MatchBuildingNode[];
  totalBuildings?: number;
  totalApartments?: number;
  totalRooms?: number;
  totalValidBeds?: number;
  counts?: MatchCounts | Record<string, unknown> | null;
  dataIntegrity?: MatchDataIntegrity | Record<string, unknown> | null;
  loading?: boolean;
  loadingMore?: boolean;
  hasMore?: boolean;
  onLoadMore?: () => void;
  loadMoreError?: string;
  conflictExamples?: MatchConflictExample[] | unknown[];
  selectedBedId?: Id | null;
  onSelectBed?: (selection: BedSelection) => void;
  language?: string;
  error?: string;
  onRetry?: () => void;
  /** 'same_apartment' | 'same_region' | 'cross_region' - lets the empty state explain what was searched. */
  scopeContext?: string | null;
}
