// Payload of GET /api/analysis/ (backend/api/views/analytics.py:analysis_data,
// built by backend/api/domains/analytics/queries.py). Also served under the
// compatibility paths the map feature probes.
import type { AllocationRun, ImportBatch, Region } from '../../shared/api/contracts';

export type AnalysisRegion = {
  id: Region['id'];
  name: string;
};

/** A `.values(<field>).annotate(count=...)` row: the grouped value plus its count. */
export type CountRow<K extends string> = { [P in K]: string | null } & { count: number };

export type AnalysisSummary = {
  total_students: number;
  assigned_students: number;
  unassigned_students: number;
  priority_students: number;
  total_buildings: number;
  active_buildings: number;
  inactive_buildings: number;
  total_rooms: number;
  total_capacity: number;
  total_beds: number;
  assigned_beds: number;
  occupied_beds: number;
  available_beds: number;
  occupancy_rate: number;
  total_transfers: number;
  pending_transfers: number;
  pending_requests: number;
  priority_unassigned_students: number;
};

export type OccupancyRow = {
  building_id: number;
  building: string;
  building_number: number | null;
  dorm_type: string;
  region: string;
  region_id: Region['id'] | '';
  rooms_count: number;
  total_beds: number;
  assigned: number;
  available_beds: number;
  occupancy_rate: number;
};

export interface AnalysisData {
  /** null for a central admin viewing the whole system. */
  region?: AnalysisRegion | null;
  summary?: AnalysisSummary;
  students_by_gender?: CountRow<'gender'>[];
  students_by_religion?: CountRow<'requested_religion'>[];
  students_by_religious?: CountRow<'religious'>[];
  students_by_category?: CountRow<'category'>[];
  students_by_housing?: CountRow<'housing_type'>[];
  students_by_region?: Array<Record<string, unknown>>;
  unassigned_by_region?: Array<Record<string, unknown>>;
  occupancy_data?: OccupancyRow[];
  transfers_by_status?: CountRow<'status'>[];
  transfers_by_type?: Array<Record<string, unknown>>;
  pending_requests_by_type?: CountRow<'request_type'>[];
  latest_run?: AllocationRun | null;
  latest_batch?: ImportBatch | null;
  error?: string;
  [key: string]: unknown;
}
