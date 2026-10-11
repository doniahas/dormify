import { api, getErrorMessage, throwApiError } from "../../shared/api/client";
import type { Id } from "../../shared/api/contracts";
import type {
  ActiveRunResponse,
  AllocationConditions,
  AllocationHistory,
  AllocationResults,
  AllocationRunPayload,
  AllocationStatus,
  AllocationSummary,
  AssistedAssignResponse,
  AssistedQueue,
  AssistedQueueParams,
  AssistedRecommendationParams,
  AssistedRecommendations,
  AssistedStudentDetail,
  InboxResponse,
  OverrideCheck,
  RunActionResponse,
  RunDetail,
  RunPreview,
  RunResultResponse,
  StartRunResponse,
} from "./types";

export const allocationAPI = {
  getSummary: async (): Promise<AllocationSummary> => {
    try {
      const { data } = await api.get<AllocationSummary>("/api/allocation/summary/");
      return data;
    } catch (err) {
      throw new Error(getErrorMessage(err, "Failed to load allocation summary"));
    }
  },

  run: async (regionId: Id, payload: AllocationRunPayload = {}): Promise<RunResultResponse> => {
    try {
      const body = { region: regionId, ...payload };
      const { data } = await api.post<RunResultResponse>("/api/allocation/run/", body);
      return data;
    } catch (err) {
      throw new Error(getErrorMessage(err, "Allocation run failed"));
    }
  },

  startRun: async (regionId: Id, payload: AllocationRunPayload = {}): Promise<StartRunResponse> => {
    try {
      const body = { region: regionId, ...payload };
      const { data } = await api.post<StartRunResponse>("/api/allocation/start/", body);
      return data;
    } catch (err) {
      throw new Error(getErrorMessage(err, "Failed to start allocation run"));
    }
  },

  getRunStatus: async (runId: Id): Promise<RunDetail> => {
    try {
      const { data } = await api.get<RunDetail>(`/api/allocation/runs/${runId}/`);
      return data;
    } catch (err) {
      throw new Error(getErrorMessage(err, "Failed to get run status"));
    }
  },

  stopRun: async (runId: Id): Promise<RunActionResponse> => {
    try {
      const { data } = await api.post<RunActionResponse>(`/api/allocation/runs/${runId}/stop/`);
      return data;
    } catch (err) {
      throw new Error(getErrorMessage(err, "Failed to stop allocation run"));
    }
  },

  // "צפה בתוצאה הנוכחית" - lightweight read of the current best-feasible
  // snapshot while a run is still RUNNING. Never stops the solver, never
  // creates BedAssignment rows - see backend get_allocation_run_preview.
  getPreview: async (runId: Id): Promise<RunPreview> => {
    try {
      const { data } = await api.get<RunPreview>(`/api/allocation/runs/${runId}/preview/`);
      return data;
    } catch (err) {
      throw new Error(getErrorMessage(err, "Failed to get current result preview"));
    }
  },

  // "עצור ושמור תוצאה" - interrupts the solver and keeps the best
  // feasible result found so far, distinct from stopRun ("בטל הרצה"),
  // which discards any partial work.
  stopAndSave: async (runId: Id): Promise<RunActionResponse> => {
    try {
      const { data } = await api.post<RunActionResponse>(`/api/allocation/runs/${runId}/stop-and-save/`);
      return data;
    } catch (err) {
      throw new Error(getErrorMessage(err, "Failed to stop and save allocation run"));
    }
  },

  deleteResults: async (runId: Id): Promise<RunActionResponse> => {
    try {
      const { data } = await api.delete<RunActionResponse>(`/api/allocation/runs/${runId}/delete/`);
      return data;
    } catch (err) {
      throw new Error(getErrorMessage(err, "Failed to delete allocation results"));
    }
  },

  retryUnassigned: async (runId: Id, payload: AllocationRunPayload = {}): Promise<RunResultResponse> => {
    try {
      const { data } = await api.post<RunResultResponse>(
        `/api/allocation/runs/${runId}/retry-unassigned/`,
        payload
      );
      return data;
    } catch (err) {
      throw new Error(getErrorMessage(err, "Failed to retry unassigned students"));
    }
  },

  getActiveRun: async (regionId: Id | null = null): Promise<ActiveRunResponse> => {
    try {
      const url = regionId
        ? `/api/allocation/runs/active/?region=${regionId}`
        : "/api/allocation/runs/active/";
      const { data } = await api.get<ActiveRunResponse>(url);
      return data;
    } catch (err) {
      throw new Error(getErrorMessage(err, "Failed to get active run"));
    }
  },

  history: async (): Promise<AllocationHistory> => {
    try {
      const { data } = await api.get<AllocationHistory>("/api/allocation/history/");
      return data;
    } catch (err) {
      throw new Error(getErrorMessage(err, "Failed to load allocation history"));
    }
  },

  getResults: async (regionId: Id | null = null): Promise<AllocationResults> => {
    try {
      const { data } = await api.get<AllocationResults>("/api/allocation/results/", {
        params: regionId ? { region: regionId } : {},
      });

      return data;
    } catch (err) {
      throw new Error(getErrorMessage(err, "Failed to load allocation results"));
    }
  },

  results: async (regionId: Id | null = null): Promise<AllocationResults> => {
    try {
      const { data } = await api.get<AllocationResults>("/api/allocation/results/", {
        params: regionId ? { region: regionId } : {},
      });
      return data;
    } catch (err) {
      throw new Error(getErrorMessage(err, "Failed to load allocation results"));
    }
  },

  getConditions: async (regionId: Id | null = null): Promise<AllocationConditions> => {
    try {
      const url = regionId
        ? `/api/allocation/conditions/?region=${regionId}`
        : "/api/allocation/conditions/";
      const { data } = await api.get<AllocationConditions>(url);
      return data;
    } catch (err) {
      throw new Error(getErrorMessage(err, "Failed to load allocation conditions"));
    }
  },

  updateConditions: async (
    conditions: Record<string, unknown>,
    regionId: Id | null = null
  ): Promise<AllocationConditions> => {
    try {
      const payload = regionId ? { conditions, region: regionId } : { conditions };
      const { data } = await api.put<AllocationConditions>("/api/allocation/conditions/", payload);
      return data;
    } catch (err) {
      throw new Error(getErrorMessage(err, "Failed to update allocation conditions"));
    }
  },

  getStatus: async (regionId: Id | null = null): Promise<AllocationStatus> => {
    try {
      const url = regionId
        ? `/api/allocation/status/?region=${regionId}`
        : "/api/allocation/status/";
      const { data } = await api.get<AllocationStatus>(url);
      return data;
    } catch (err) {
      throw new Error(getErrorMessage(err, "Failed to get allocation status"));
    }
  },
};

const warnDetail = (err: unknown): unknown => {
  if (typeof err === "object" && err !== null) {
    const { response, message } = err as { response?: { data?: unknown }; message?: string };
    return response?.data || message;
  }
  return err;
};

export const inboxAPI = {
  getLatest: async (): Promise<InboxResponse> => {
    try {
      const { data } = await api.get<InboxResponse>("/api/inbox/latest/");
      return data;
    } catch (err) {
      throw new Error(getErrorMessage(err, "Failed to load inbox"));
    }
  },

  markViewed: async (id: Id): Promise<InboxResponse | null> => {
    try {
      const { data } = await api.put<InboxResponse>(`/api/inbox/${id}/viewed/`);
      return data;
    } catch (err) {
      console.warn(
        `markViewed failed for inbox item ${id}:`,
        warnDetail(err)
      );
      return null;
    }
  },

  markProcessed: async (id: Id): Promise<InboxResponse> => {
    try {
      const { data } = await api.put<InboxResponse>(`/api/inbox/${id}/processed/`);
      return data;
    } catch (err) {
      console.warn(
        `markProcessed failed for inbox item ${id}:`,
        warnDetail(err)
      );

      throw new Error(
        getErrorMessage(err, "Failed to mark inbox item as processed")
      );
    }
  },
};

export const assistedAllocationAPI = {
  getQueue: async (params: AssistedQueueParams = {}): Promise<AssistedQueue> => {
    try {
      const { data } = await api.get<AssistedQueue>("/api/assisted-allocation/queue/", { params });
      return data;
    } catch (err) {
      return throwApiError(err, "Failed to load assisted allocation queue");
    }
  },
  getStudentDetail: async (studentId: Id): Promise<AssistedStudentDetail> => {
    try {
      const { data } = await api.get<AssistedStudentDetail>(
        `/api/assisted-allocation/students/${studentId}/detail/`
      );
      return data;
    } catch (err) {
      return throwApiError(err, "Failed to load student detail");
    }
  },
  getRecommendations: async (
    studentId: Id,
    params: AssistedRecommendationParams = {}
  ): Promise<AssistedRecommendations> => {
    try {
      const { data } = await api.get<AssistedRecommendations>(
        `/api/assisted-allocation/students/${studentId}/recommendations/`,
        { params }
      );
      return data;
    } catch (err) {
      return throwApiError(err, "Failed to load recommendations");
    }
  },
  checkOverride: async (studentId: Id, bedId: Id): Promise<OverrideCheck> => {
    try {
      const { data } = await api.get<OverrideCheck>(
        `/api/assisted-allocation/students/${studentId}/override-check/`,
        { params: { bed_id: bedId } }
      );
      return data;
    } catch (err) {
      return throwApiError(err, "Failed to check override");
    }
  },
  assign: async (studentId: Id, bedId: Id): Promise<AssistedAssignResponse> => {
    try {
      const { data } = await api.post<AssistedAssignResponse>(
        `/api/assisted-allocation/students/${studentId}/assign/`,
        { bed_id: bedId }
      );
      return data;
    } catch (err) {
      return throwApiError(err, "Failed to assign student");
    }
  },
  override: async (studentId: Id, bedId: Id, note: string): Promise<AssistedAssignResponse> => {
    try {
      const { data } = await api.post<AssistedAssignResponse>(
        `/api/assisted-allocation/students/${studentId}/override/`,
        { bed_id: bedId, note }
      );
      return data;
    } catch (err) {
      return throwApiError(err, "Failed to assign student with override");
    }
  },
};
