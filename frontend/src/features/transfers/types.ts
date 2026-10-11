// Student requests and transfers (backend/api/serializers/workflows.py and
// backend/api/views/transfers.py).
import type { Id, IsoDateTime } from '../../shared/api/contracts';
import type { BedMatchOptions } from '../students/types';

export type RequestType =
  | 'add_student'
  | 'remove_student'
  | 'room'
  | 'apartment'
  | 'swap'
  | 'region_transfer'
  | 'other';
export type RequestStatus = 'pending' | 'approved' | 'rejected' | 'cancelled';
export type RequestPriority = 'low' | 'normal' | 'high' | 'urgent';
export type TransferScope = 'same_region' | 'cross_region';
export type TransferStatus = 'pending' | 'approved' | 'rejected';

/** One entry of StudentRequestSerializer.placement_history (newest first). */
export interface PlacementHistoryEntry {
  region: string | null;
  building: number | null;
  apartment: string | null;
  room: string | null;
  status: string;
  assigned_at: IsoDateTime | null;
  ended_at: IsoDateTime | null;
}

/** StudentRequestSerializer. */
export interface StudentRequest {
  id: number;
  /** StudentRequest.request_number is nullable (POST /api/requests/ assigns REQ-...). */
  request_number: string | null;
  request_type: RequestType;
  request_type_display: string;
  reason: string;
  status: RequestStatus;
  status_display: string;
  priority: RequestPriority;
  priority_display: string;
  other_description: string;
  same_apartment: boolean | null;
  removal_notes: string;
  removal_reason: string;
  student: number | null;
  student_name: string | null;
  student_id_number: string | null;
  student_phone: string | null;
  student_data: Record<string, unknown> | null;
  target_room: number | null;
  target_room_name: string | null;
  target_building_number: number | null;
  target_apartment_number: string | null;
  swap_with_student: number | null;
  swap_with_student_name: string | null;
  swap_with_student_id_number: string | null;
  target_region: string | null;
  target_region_name: string | null;
  transfer_scope: TransferScope | null;
  transfer_scope_display: string | null;
  source_region: string | null;
  source_region_name: string | null;
  destination_regions: string[];
  destination_region_names: string[];
  current_assignment_snapshot: Record<string, unknown> | null;
  final_assignment: number | null;
  final_bed_label: string | null;
  current_region: string | null;
  current_building: number | null;
  current_apartment: string | null;
  current_room: string | null;
  current_bed: string | null;
  placement_history: PlacementHistoryEntry[];
  requested_by: number | null;
  requested_by_name: string | null;
  reviewed_by: number | null;
  reviewed_by_name: string | null;
  reviewed_at: IsoDateTime | null;
  rejection_reason: string;
  created_at: IsoDateTime;
  updated_at: IsoDateTime;
}

/** Writable subset accepted by POST /api/requests/. */
export type StudentRequestPayload = Partial<
  Pick<
    StudentRequest,
    | 'request_type'
    | 'reason'
    | 'priority'
    | 'other_description'
    | 'same_apartment'
    | 'removal_notes'
    | 'removal_reason'
    | 'student'
    | 'student_data'
    | 'target_room'
    | 'swap_with_student'
    | 'target_region'
    | 'transfer_scope'
    | 'destination_regions'
  >
> & { [key: string]: unknown };

/** PUT /api/requests/<id>/approve/ body: the chosen target, when one applies. */
export interface ApproveRequestPayload {
  target_room?: Id;
  bed_id?: Id;
  [key: string]: unknown;
}

/** TransferSerializer. */
export interface Transfer {
  id: number;
  student: number;
  student_name: string;
  student_id_number: string;
  from_room: number | null;
  from_room_name: string | null;
  from_building_number: number | null;
  from_apartment_number: string | null;
  to_room: number | null;
  to_room_name: string | null;
  to_building_number: number | null;
  to_apartment_number: string | null;
  reason: string;
  status: TransferStatus;
  status_display: string;
  requested_by: number | null;
  requested_by_name: string | null;
  requested_by_region_name: string | null;
  reviewed_by: number | null;
  reviewed_by_name: string | null;
  reviewed_at: IsoDateTime | null;
  rejection_reason: string;
  movement_request: number | null;
  created_at: IsoDateTime;
  updated_at: IsoDateTime;
}

/** Query parameters of GET /api/requests/. */
export interface RequestListParams {
  status?: RequestStatus | string;
  request_type?: RequestType | string;
  student?: Id;
  region?: Id;
  page?: number;
  [key: string]: string | number | boolean | null | undefined;
}

/** Decision/action envelopes of the request and transfer endpoints. */
export interface RequestActionResponse {
  message?: string;
  detail?: string;
  error?: string;
  request?: StudentRequest;
  [key: string]: unknown;
}

export interface TransferActionResponse {
  message?: string;
  error?: string;
  transfer?: Transfer;
  [key: string]: unknown;
}

/** GET /api/requests/<id>/feasibility/ - same hierarchical shape as match-options. */
export type FeasibilityResult = BedMatchOptions;

export interface FeasibilityOptions {
  limit?: number;
  offset?: number;
  signal?: AbortSignal;
}

export interface FeasibilityForStudentOptions extends FeasibilityOptions {
  regionId?: Id;
  transferScope?: TransferScope;
  regionIds?: Id[];
}
