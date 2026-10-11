// What-if scenarios (backend/api/views/whatif.py, backend/api/domains/whatif).
// The simulation returns a before/after analysis plus the affected students;
// confirm applies the change and creates the follow-up transfer requests.
import type { Gender, HousingType, Id, Region, Religion, Religious, StudentCategory } from '../../shared/api/contracts';

/** parse_target_selection accepts exactly these (default 'building'). */
export type AvailabilityTargetType = 'building' | 'apartment' | 'room';
/** parse_availability_action accepts exactly these (default 'inactivate'). */
export type AvailabilityAction = 'inactivate' | 'reactivate';

export type WhatIfScenario = 'building_inactivation' | 'room_availability_change';

/** The capacity/occupancy picture of the region before and after the change. */
export type WhatIfAnalysisSnapshot = {
  total_students: number;
  assigned_students: number;
  unassigned_students: number;
  total_buildings: number;
  total_rooms: number;
  total_capacity: number;
  total_beds: number;
  occupied_beds: number;
  assigned_beds: number;
  available_beds: number;
  occupancy_rate: number;
};

export type WhatIfSummary = {
  affected_students_count: number;
  students_without_valid_placement: number;
  male_count: number;
  female_count: number;
  lost_apartments: number;
  lost_rooms: number;
  lost_capacity: number;
  lost_beds: number;
};

export type WhatIfBreakdownRow = { value: string | null; count: number };

export type WhatIfBreakdowns = Record<
  'gender' | 'requested_religion' | 'religious' | 'placement_sector' | 'category' | 'housing_type',
  WhatIfBreakdownRow[]
>;

export type WhatIfSelectedBuilding = {
  id: number;
  number: number | null;
  dorm_type_id: number | null;
  dorm_type_name: string | null;
  region_id: Region['id'] | null;
  region_name: string | null;
  is_active: boolean;
};

export type WhatIfSelectedTarget = {
  id: number;
  target_type: AvailabilityTargetType;
  label: string;
  room_id: number | null;
  room_name: string | null;
  apartment_id: number | null;
  apartment_number: string | null;
  building_id: number | null;
  building_number: number | null;
  dorm_type_id: number | null;
  dorm_type_name: string | null;
  region_id: Region['id'] | null;
  region_name: string | null;
  capacity: number | null;
  is_active: boolean;
};

export type WhatIfAffectedStudent = {
  assignment_id: number;
  student_db_id: number;
  student_id: string;
  business_partner_id: string;
  full_name: string;
  first_name: string;
  last_name: string;
  gender: Gender | string;
  requested_religion: Religion | string;
  religious: Religious | string;
  placement_sector: string;
  category: StudentCategory | string;
  housing_type: HousingType | null;
  gender_display: string;
  requested_religion_display: string;
  religious_display: string;
  is_priority: boolean;
  priority_reason: string;
  accepted_dorm_type_id: number | null;
  accepted_dorm_type_name: string | null;
  current_building_id: number;
  current_building_number: number | null;
  current_apartment_id: number;
  current_apartment_number: string;
  current_room_id: number;
  current_room_name: string;
  current_bed_id: number | null;
  current_bed_label: string | null;
  dorm_type_id: number | null;
  dorm_type_name: string | null;
  region_id: Region['id'] | null;
  region_name: string | null;
  status: 'needs_transfer' | string;
};

/** POST /api/what-if/building-inactivation/simulate/ and /api/what-if/availability/simulate/ (200). */
export interface WhatIfSimulation {
  success?: boolean;
  scenario?: WhatIfScenario;
  /** Building scenario only. */
  selected_buildings?: WhatIfSelectedBuilding[];
  /** Availability scenario only. */
  target_type?: AvailabilityTargetType;
  target_ids?: number[];
  selected_targets?: WhatIfSelectedTarget[];
  summary?: WhatIfSummary;
  breakdowns?: WhatIfBreakdowns;
  analysis_before?: WhatIfAnalysisSnapshot;
  analysis_after?: WhatIfAnalysisSnapshot;
  affected_students?: WhatIfAffectedStudent[];
  /** Failure bodies ({success: false, error, error_type}). */
  error?: string;
  error_type?: string;
  [key: string]: unknown;
}

/** POST /api/what-if/building-inactivation/confirm/ and /api/what-if/availability/confirm/ (200). */
export interface WhatIfConfirmation {
  success?: boolean;
  message?: string;
  affected_students_count?: number;
  /** Counts, not records. */
  created_requests?: number;
  skipped_existing_requests?: number;
  created_request_ids?: number[];
  /** Building confirm: whether the buildings were inactivated as part of the confirm. */
  inactivated_buildings?: boolean;
  selected_building_ids?: number[];
  /** Availability confirm. */
  action?: AvailabilityAction;
  target_type?: AvailabilityTargetType;
  target_ids?: number[];
  error?: string;
  error_type?: string;
  [key: string]: unknown;
}

export interface AvailabilityChangeInput {
  targetType: AvailabilityTargetType;
  targetIds: Id[];
  action?: AvailabilityAction;
}

export interface AvailabilityConfirmInput extends AvailabilityChangeInput {
  reason?: string;
}
