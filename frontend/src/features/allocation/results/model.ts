// UI-level types owned by the Allocation Results page: the router state the
// Allocation page hands over, the saved results as the page holds them, the
// rows of the three views and the dorm -> building -> apartment -> room
// hierarchy built from them. Wire types stay in ../types.ts.
import type { Id, IsoDateTime } from '../../../shared/api/contracts';

/** The three views of the results panel. */
export type ResultsView = 'assigned' | 'unassigned' | 'beds';

/** A location part (building / apartment / room / bed) as the API carries it. */
export type LocationValue = string | number | null | undefined;

/**
 * Anything that carries a location: an assignment or an available bed. The
 * backend has used several field names over time, so every alias is read
 * (see getBuilding/getApartment/getRoom/getBed in the helpers).
 */
export interface LocatedItem {
  dorm_type?: string | null;
  building_number?: LocationValue;
  building_name?: LocationValue;
  building?: LocationValue;
  apartment_number?: LocationValue;
  apartment?: LocationValue;
  room_number?: LocationValue;
  room_name?: LocationValue;
  room?: LocationValue;
  bed_number?: LocationValue;
  bed_label?: LocationValue;
  bed?: LocationValue;
  apartment_type?: string | null;
  apartment_type_display?: string | null;
  apartment_category?: string | null;
  apartment_category_display?: string | null;
  [key: string]: unknown;
}

/** One saved assignment (a student placed in a bed). */
export interface AssignmentRow extends LocatedItem {
  student_id?: LocationValue;
  student_name?: string | null;
  full_name?: string | null;
  assignment_status?: string | null;
  status?: string | null;
  gender?: string | null;
  religion_display?: string | null;
  religion?: string | null;
  requested_religion?: string | null;
  housing_type_display?: string | null;
  housing_type?: string | null;
  assigned_at?: IsoDateTime | null;
}

/** One student the run left unassigned. */
export interface UnassignedStudentRow {
  student_id?: LocationValue;
  student_name?: string | null;
  full_name?: string | null;
  gender?: string | null;
  gender_display?: string | null;
  housing_type_display?: string | null;
  housing_type?: string | null;
  accepted_dorm_type?: string | null;
  religion_display?: string | null;
  requested_religion?: string | null;
  religion?: string | null;
  religious?: string | null;
  placement_sector_display?: string | null;
  placement_sector?: string | null;
  sector?: string | null;
  is_priority?: boolean | null;
  special_statuses?: unknown;
  unassigned_reason?: string | null;
  [key: string]: unknown;
}

/** One bed still free after the run. */
export interface AvailableBedRow extends LocatedItem {
  bed_id?: Id | null;
  region?: string | null;
  is_reserved?: boolean | null;
}

/** One line of an analysis group's free-inventory breakdown. */
export interface InventoryBreakdownItem {
  free_beds?: number | string | null;
  category?: string | null;
  category_display?: string | null;
  apartment_type?: string | null;
  apartment_type_display?: string | null;
}

/** Why a group of students (same accepted dorm type, gender and housing type) stayed unassigned. */
export interface UnassignedAnalysisGroup {
  accepted_dorm_type_id?: Id | null;
  accepted_dorm_type_code?: string | number | null;
  accepted_dorm_type_name?: string | null;
  gender?: string | null;
  housing_type?: string | null;
  housing_type_display?: string | null;
  student_count?: number | string | null;
  physically_free_beds_in_accepted_dorm?: number | string | null;
  compatible_free_beds?: number | string | null;
  inventory_breakdown?: InventoryBreakdownItem[] | null;
  reason_code?: string | null;
  [key: string]: unknown;
}

/** The three totals shown on the view tabs. */
export interface ResultsCounts {
  assigned: number;
  unassigned: number;
  available_beds: number;
}

/** The run a result refers to, as far as this page reads it. */
export interface ResultsRun {
  id?: Id | null;
  status?: string | null;
  completed_at?: IsoDateTime | null;
  started_at?: IsoDateTime | null;
  [key: string]: unknown;
}

/**
 * The result the Allocation page hands over through router state (its
 * synchronous run reply), or the results as this page holds them after
 * loading the saved ones from the server.
 */
export interface ResultsData {
  assignments?: unknown;
  unassigned_students?: unknown;
  available_beds?: unknown;
  unassigned_analysis?: unknown;
  counts?: Partial<ResultsCounts> | null;
  successful_assignments?: number | null;
  roommate_matches?: number | null;
  conflicts?: number | null;
  run?: ResultsRun | null;
  [key: string]: unknown;
}

/** The region as the Allocation page's summary carries it. */
export interface ResultsRegion {
  id?: Id | null;
  name?: string | null;
  [key: string]: unknown;
}

/** The allocation summary handed over through router state, as far as this page reads it. */
export interface ResultsSummary {
  region?: ResultsRegion | null;
  region_id?: Id | null;
  latest_run?: ResultsRun | null;
  [key: string]: unknown;
}

/** location.state as AllocationPage.handleViewResults sets it; every field is optional. */
export interface ResultsRouteState {
  result?: ResultsData | null;
  summary?: ResultsSummary | null;
  region?: ResultsRegion | null;
  generatedAt?: string | null;
}

/** Dorm type -> building -> apartment -> room, each level with its own assignments and free beds. */
export interface RoomNode {
  name: string;
  assignments: AssignmentRow[];
  availableBeds: AvailableBedRow[];
}

export interface ApartmentNode {
  number: string;
  apartmentType: string;
  apartmentTypeDisplay: string;
  apartmentCategory: string;
  apartmentCategoryDisplay: string;
  assignments: AssignmentRow[];
  availableBeds: AvailableBedRow[];
  rooms: Record<string, RoomNode>;
}

export interface BuildingNode {
  number: string;
  assignments: AssignmentRow[];
  availableBeds: AvailableBedRow[];
  apartments: Record<string, ApartmentNode>;
}

export interface DormTypeNode {
  name: string;
  assignments: AssignmentRow[];
  availableBeds: AvailableBedRow[];
  buildings: Record<string, BuildingNode>;
}

export type AllocationHierarchy = Record<string, DormTypeNode>;

/** Which hierarchy rows are expanded, keyed by the row's path key. */
export type OpenMap = Record<string, boolean>;

/** The occupancy chip of an apartment or a room. */
export type AvailabilityState = 'empty' | 'available' | 'full';
