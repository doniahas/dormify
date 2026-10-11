import {
  api,
  getErrorMessage,
  isRequestCancelled,
  throwApiError,
  type RequestOptions,
} from "../../shared/api/client";
import type {
  Id,
  ListResponse,
  Student,
  StudentSummary,
  StudentWritePayload,
} from "../../shared/api/contracts";
import { asArray } from "../../shared/api/normalize";
import type { StudentRequest } from "../transfers/types";
import type {
  AvailableBedsOptions,
  BedMatchOptions,
  PlacementResponse,
  StudentCounts,
  StudentFilterOptions,
  StudentListParams,
  StudentPage,
} from "./types";

// A list response that may be paginated, or a plain array, or - when the
// endpoint answers with a count envelope only - neither.
type CountableList = Partial<StudentPage> | StudentSummary[];

async function countStudents(params: StudentListParams | undefined): Promise<number> {
  let next: string | null = '/api/students/';
  let total = 0;
  const visited = new Set<string>();
  while (next) {
    if (visited.has(next)) throw new Error('Student pagination repeated a page');
    visited.add(next);
    const response: { data: CountableList } = await api.get<CountableList>(next, { params });
    const data = response.data;
    if (!Array.isArray(data) && Number.isInteger(data?.count) && (data.count as number) >= 0) {
      return data.count as number;
    }
    if (Array.isArray(data)) return total + data.length;
    if (!Array.isArray(data?.results)) throw new Error('Invalid student list response');
    total += data.results.length;
    next = data.next ?? null;
    params = undefined;
  }
  return total;
}

// Aborted requests are not failures; hooks test for them through the adapter
// so they never import the shared client directly.
export { isRequestCancelled };

export const studentsAPI = {
  getNextPage: async (url: string): Promise<StudentPage> => {
    const { data } = await api.get<StudentPage>(url);
    return data;
  },

  getStudents: async (
    params: StudentListParams = {},
    opts: RequestOptions = {}
  ): Promise<ListResponse<StudentSummary>> => {
    try {
      const { data } = await api.get<ListResponse<StudentSummary>>("/api/students/", {
        params,
        signal: opts.signal,
      });
      return data;
    } catch (err) {
      if (isRequestCancelled(err)) throw err;
      throw new Error(getErrorMessage(err, "Failed to load students"));
    }
  },

  getById: async (id: Id): Promise<Student> => {
    try {
      const { data } = await api.get<Student>(`/api/students/${id}/`);
      return data;
    } catch (err) {
      throw new Error(getErrorMessage(err, "Failed to load student"));
    }
  },

  getCounts: async (): Promise<StudentCounts> => {
    try {
      const { data } = await api.get<StudentCounts>("/api/students/counts/");
      return data;
    } catch (err) {
      console.warn("studentsAPI.getCounts failed, loading filtered totals:", errorText(err));
      // The server owns category and latest-run unassigned semantics.
      const [all, continuing, newStudents, transfer, leaving, unassigned] = await Promise.all([
        countStudents({}),
        countStudents({ category: 'continuing' }),
        countStudents({ category: 'new' }),
        countStudents({ category: 'transfer' }),
        countStudents({ category: 'leaving' }),
        countStudents({ status: 'unassigned' }),
      ]);
      return {
        all, continuing, new: newStudents, transfer, leaving, unassigned,
        total: all, all_students: all, total_students: all,
        staying: continuing, staying_students: continuing,
        new_students: newStudents, incoming: newStudents,
        transferring: transfer, transferring_students: transfer,
        leaving_students: leaving,
      };
    }
  },

  getFilterOptions: async (): Promise<StudentFilterOptions> => {
    try {
      const { data } = await api.get<StudentFilterOptions>("/api/students/filter-options/");
      return data;
    } catch (err) {
      console.warn(
        "studentsAPI.getFilterOptions failed:",
        responseData(err) || errorText(err)
      );
      return {};
    }
  },

  create: async (payload: StudentWritePayload): Promise<Student> => {
    try {
      const { data } = await api.post<Student>("/api/students/", payload);
      return data;
    } catch (err) {
      return throwApiError(err, "Failed to create student");
    }
  },

  update: async (id: Id, payload: StudentWritePayload): Promise<Student> => {
    try {
      const { data } = await api.patch<Student>(`/api/students/${id}/`, payload);
      return data;
    } catch (err) {
      return throwApiError(err, "Failed to update student");
    }
  },

  // Real matching engine, paginated by BUILDING (primary key). Returns
  // { feasible, reason, buildings: [building → apartments → rooms → beds],
  //   loaded_buildings, total_buildings, total_apartments, total_rooms,
  //   total_valid_beds, has_more, next_offset, counts, conflict_examples,
  //   data_integrity }.
  // Every returned building carries its COMPLETE apartment/room/bed
  // subtree (real Bed records only - browsing is strictly read-only and
  // never creates rows). limit/offset count buildings, not beds. Honors
  // the same hard constraints (gender, housing type, capacity, region,
  // active status) the backend enforces when the assignment is actually
  // made. regionId override is central-admin only (ignored server-side for
  // regional users).
  getAvailableBeds: async (studentId: Id, opts: AvailableBedsOptions = {}): Promise<BedMatchOptions> => {
    try {
      const { data } = await api.post<BedMatchOptions>("/api/requests/match-options/", {
        student_id: studentId,
        same_apartment: opts.sameApartment ?? null,
        region_id: opts.regionId ?? undefined,
        limit: opts.limit ?? 10,
        offset: opts.offset ?? 0,
      });
      return data;
    } catch (err) {
      throw new Error(getErrorMessage(err, "Failed to load available beds"));
    }
  },

  assignBed: async (studentId: Id, roomId: Id, bedId?: Id | null): Promise<PlacementResponse> => {
    try {
      const { data } = await api.post<PlacementResponse>("/api/room-assignments/assign/", {
        student_id: studentId,
        room_id: roomId,
        bed_id: bedId ?? undefined,
      });
      return data;
    } catch (err) {
      throw new Error(getErrorMessage(err, "Failed to assign bed"));
    }
  },

  reassignBed: async (studentId: Id, roomId: Id, bedId?: Id | null): Promise<PlacementResponse> => {
    try {
      const { data } = await api.post<PlacementResponse>("/api/room-assignments/move/", {
        student_id: studentId,
        room_id: roomId,
        bed_id: bedId ?? undefined,
      });
      return data;
    } catch (err) {
      throw new Error(getErrorMessage(err, "Failed to reassign bed"));
    }
  },

  unassignBed: async (studentId: Id): Promise<PlacementResponse> => {
    try {
      const { data } = await api.post<PlacementResponse>("/api/room-assignments/unassign/", {
        student_id: studentId,
      });
      return data;
    } catch (err) {
      throw new Error(getErrorMessage(err, "Failed to unassign bed"));
    }
  },

  getRequests: async (studentId: Id): Promise<StudentRequest[]> => {
    try {
      const { data } = await api.get<ListResponse<StudentRequest>>("/api/requests/", {
        params: { student: studentId },
      });
      return asArray<StudentRequest>(data);
    } catch (err) {
      throw new Error(getErrorMessage(err, "Failed to load student requests"));
    }
  },
};

const errorText = (err: unknown): string | undefined =>
  err instanceof Error ? err.message : undefined;

const responseData = (err: unknown): unknown =>
  typeof err === "object" && err !== null
    ? (err as { response?: { data?: unknown } }).response?.data
    : undefined;
