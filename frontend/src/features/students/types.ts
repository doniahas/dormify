// Student-feature payloads beyond the shared Student contracts
// (backend/api/views/students.py, placement.py and transfers.py match_options).
import type { Id, IsoDateTime, Paginated, Region, StudentSummary } from '../../shared/api/contracts';
import type { MatchTree } from '../allocation/types';
import type { TransferScope } from '../transfers/types';

/** Query parameters of GET /api/students/ (filters, search, paging). */
export interface StudentListParams {
  page?: number;
  search?: string;
  category?: string;
  status?: string;
  gender?: string;
  region?: Id;
  dorm_type?: Id;
  building?: Id;
  apartment?: Id;
  room?: Id;
  ordering?: string;
  [key: string]: string | number | boolean | null | undefined;
}

export type StudentPage = Paginated<StudentSummary>;

/**
 * GET /api/students/counts/. The authoritative response carries the six
 * category totals; the adapter's fallback adds the legacy alias keys older
 * screens still read.
 */
export interface StudentCounts {
  all: number;
  continuing: number;
  new: number;
  transfer: number;
  leaving: number;
  unassigned: number;
  total?: number;
  all_students?: number;
  total_students?: number;
  staying?: number;
  staying_students?: number;
  new_students?: number;
  incoming?: number;
  transferring?: number;
  transferring_students?: number;
  leaving_students?: number;
}

/** One {id, name} choice of GET /api/students/filter-options/. */
export interface StudentFilterOption {
  id: Id;
  name: string;
}

/** A dorm-type choice also carries the region it belongs to. */
export interface DormTypeFilterOption extends StudentFilterOption {
  region_id: string | null;
  region_name: string | null;
}

/**
 * GET /api/students/filter-options/ (students.filter_options). Every list is
 * {id, name} pairs; dorm types add their region so the drawer and the
 * student forms can scope them to a chosen region.
 */
export interface StudentFilterOptions {
  is_central_admin?: boolean;
  regions?: StudentFilterOption[];
  buildings?: StudentFilterOption[];
  dorm_types?: DormTypeFilterOption[];
  apartments?: StudentFilterOption[];
  rooms?: StudentFilterOption[];
  religions?: StudentFilterOption[];
  housing_types?: StudentFilterOption[];
  [key: string]: unknown;
}

/** Options of studentsAPI.getAvailableBeds (POST /api/requests/match-options/). */
export interface AvailableBedsOptions {
  sameApartment?: boolean | null;
  regionId?: Id;
  limit?: number;
  offset?: number;
}

/** A region the matching engine searched (match-options `search_regions`). */
export interface SearchRegion {
  id: Region['id'];
  name: string;
}

/**
 * POST /api/requests/match-options/ (students.match_options): the paged
 * match tree (MatchTree) plus the feasibility verdict. A 404 for a missing
 * student answers {feasible: false, buildings: [], reason}; a blocked student
 * answers 200 with feasible=false, `reason` and `blocking_field`; a scope
 * rejection answers 400 with feasible=false and `reason`.
 */
export type BedMatchOptions = Partial<MatchTree> & {
  feasible?: boolean;
  reason?: string | null;
  blocking_field?: string | null;
  search_regions?: SearchRegion[];
  transfer_scope?: TransferScope | string | null;
  detail?: string;
  [key: string]: unknown;
};

/** Room-assignment actions (backend/api/views/placement.py). */
export interface PlacementResponse {
  success?: boolean;
  message?: string;
  assignment_id?: number;
  student_id?: Id;
  room_id?: Id;
  bed_id?: Id;
  error?: string;
  [key: string]: unknown;
}

export interface PlacementTimestamped {
  created_at?: IsoDateTime;
}
