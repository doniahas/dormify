import { api, getErrorMessage, isRequestCancelled } from "../../shared/api/client";
import type { Id, ListResponse, Region } from "../../shared/api/contracts";
import { asArray } from "../../shared/api/normalize";
import type {
  ApproveRequestPayload,
  FeasibilityForStudentOptions,
  FeasibilityOptions,
  FeasibilityResult,
  RequestActionResponse,
  RequestListParams,
  RequestType,
  StudentRequest,
  StudentRequestPayload,
  Transfer,
  TransferActionResponse,
} from "./types";

// Aborted requests are not failures; hooks test for them through the adapter
// so they never import the shared client directly.
export { isRequestCancelled };

export const transfersAPI = {
  getAll: async (): Promise<ListResponse<Transfer>> => {
    try {
      const { data } = await api.get<ListResponse<Transfer>>("/api/transfers/");
      return data;
    } catch (err) {
      throw new Error(getErrorMessage(err, "Failed to load transfers"));
    }
  },

  approve: async (id: Id): Promise<TransferActionResponse> => {
    try {
      const { data } = await api.put<TransferActionResponse>(`/api/transfers/${id}/approve/`);
      return data;
    } catch (err) {
      throw new Error(getErrorMessage(err, "Failed to approve transfer"));
    }
  },

  reject: async (id: Id, reason = ""): Promise<TransferActionResponse> => {
    try {
      const { data } = await api.put<TransferActionResponse>(`/api/transfers/${id}/reject/`, {
        reason,
      });
      return data;
    } catch (err) {
      throw new Error(getErrorMessage(err, "Failed to reject transfer"));
    }
  },
};

export const requestsAPI = {
  getAll: async (params: RequestListParams = {}): Promise<ListResponse<StudentRequest>> => {
    try {
      const { data } = await api.get<ListResponse<StudentRequest>>("/api/requests/", { params });
      return data;
    } catch (err) {
      throw new Error(getErrorMessage(err, "Failed to load requests"));
    }
  },

  create: async (payload: StudentRequestPayload): Promise<StudentRequest> => {
    try {
      const { data } = await api.post<StudentRequest>("/api/requests/", payload);
      return data;
    } catch (err) {
      throw new Error(getErrorMessage(err, "Failed to create request"));
    }
  },

  approve: async (id: Id, payload: ApproveRequestPayload = {}): Promise<RequestActionResponse> => {
    try {
      const { data } = await api.put<RequestActionResponse>(`/api/requests/${id}/approve/`, payload);
      return data;
    } catch (err) {
      throw new Error(getErrorMessage(err, "Failed to approve request"));
    }
  },

  reject: async (id: Id, reason = ""): Promise<RequestActionResponse> => {
    try {
      const { data } = await api.put<RequestActionResponse>(`/api/requests/${id}/reject/`, {
        reason,
      });
      return data;
    } catch (err) {
      throw new Error(getErrorMessage(err, "Failed to reject request"));
    }
  },

  delete: async (id: Id): Promise<RequestActionResponse | undefined> => {
    try {
      const { data } = await api.delete<RequestActionResponse | undefined>(`/api/requests/${id}/`);
      return data;
    } catch (err) {
      throw new Error(getErrorMessage(err, "Failed to delete request"));
    }
  },

  // Withdraw the caller's own still-pending request (distinct from reject:
  // that's a reviewer's decision, this is the requesting side changing its
  // mind before any reviewer acted).
  cancel: async (id: Id): Promise<RequestActionResponse> => {
    try {
      const { data } = await api.put<RequestActionResponse>(`/api/requests/${id}/cancel/`, {});
      return data;
    } catch (err) {
      throw new Error(getErrorMessage(err, "Failed to cancel request"));
    }
  },

  // Feasibility for an already-created (pending) request - used both for
  // room/apartment transfer requests and for add_student requests (the
  // backend computes matches from the request's stored student/student_data).
  // Same building-paged hierarchical shape as getAvailableBeds; limit/offset
  // count buildings.
  checkFeasibility: async (id: Id, opts: FeasibilityOptions = {}): Promise<FeasibilityResult> => {
    try {
      const { data } = await api.get<FeasibilityResult>(`/api/requests/${id}/feasibility/`, {
        params: { limit: opts.limit ?? 10, offset: opts.offset ?? 0 },
        signal: opts.signal,
      });
      return data;
    } catch (err) {
      if (isRequestCancelled(err)) throw err;
      throw new Error(getErrorMessage(err, "Failed to check feasibility"));
    }
  },

  // Feasibility preview before a request exists yet (used by the "check
  // available options" step while composing a new room/apartment request).
  checkFeasibilityForStudent: async (
    studentId: Id,
    requestType: RequestType | string,
    sameApartment: boolean | null = null,
    opts: FeasibilityForStudentOptions = {}
  ): Promise<FeasibilityResult> => {
    try {
      const { data } = await api.post<FeasibilityResult>("/api/requests/match-options/", {
        student_id: studentId,
        request_type: requestType,
        same_apartment: sameApartment,
        region_id: opts.regionId ?? undefined,
        // Transfer scope: 'same_region' searches the student's current
        // region automatically; 'cross_region' searches exactly the
        // destination regions the central admin selected (regional users
        // are rejected server-side with 403).
        transfer_scope: opts.transferScope ?? undefined,
        region_ids: opts.regionIds ?? undefined,
        limit: opts.limit ?? 10,
        offset: opts.offset ?? 0,
      }, { signal: opts.signal });
      return data;
    } catch (err) {
      if (isRequestCancelled(err)) throw err;
      throw new Error(getErrorMessage(err, "Failed to check feasibility"));
    }
  },

  getAddStudentBeds: async (id: Id, opts: FeasibilityOptions = {}): Promise<FeasibilityResult> => {
    try {
      const { data } = await api.get<FeasibilityResult>(`/api/requests/${id}/feasibility/`, {
        params: { limit: opts.limit ?? 10, offset: opts.offset ?? 0 },
        signal: opts.signal,
      });
      return data;
    } catch (err) {
      if (isRequestCancelled(err)) throw err;
      throw new Error(getErrorMessage(err, "Failed to load available beds"));
    }
  },

  // Regions a region_transfer request may name as target_region. Not
  // regionsAPI.getAll() - that endpoint scopes a non-central user to only
  // their own region, which would leave a regional employee unable to see
  // any other region to request a transfer to.
  getTransferTargetRegions: async (): Promise<Region[]> => {
    try {
      const { data } = await api.get<ListResponse<Region>>("/api/requests/transfer-target-regions/");
      return asArray<Region>(data);
    } catch (err) {
      throw new Error(getErrorMessage(err, "Failed to load transfer destination regions"));
    }
  },
};
