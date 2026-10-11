import type { AxiosResponse } from "axios";
import { api } from "../../shared/api/client";
import type { Id } from "../../shared/api/contracts";

// Report endpoints stream an .xlsx workbook. The whole response is returned
// (not just the body) so the page can read the blob and trigger a download;
// failures propagate as axios errors for the page's own error display.
export type ReportDownload = Promise<AxiosResponse<Blob>>;

const regionParams = (regionId: Id | null): { region_id?: Id } =>
  regionId ? { region_id: regionId } : {};

export const reportsAPI = {
  downloadDormifyReport: async (): ReportDownload => {
    return api.get<Blob>('/api/reports/dormify-report/', { responseType: 'blob' });
  },

  // Legacy: kept for backward compat
  downloadStudentAllocationReport: async (): ReportDownload => {
    return api.get<Blob>('/api/reports/student-allocation-report/', { responseType: 'blob' });
  },

  downloadStudentActionsReport: async (regionId: Id | null = null): ReportDownload => {
    const params = regionParams(regionId);
    return api.get<Blob>('/api/reports/student-actions-report/', { responseType: 'blob', params });
  },

  downloadCapacityReport: async (regionId: Id | null = null): ReportDownload => {
    const params = regionParams(regionId);
    return api.get<Blob>('/api/reports/capacity-report/', { responseType: 'blob', params });
  },

  downloadManualReviewReport: async (regionId: Id | null = null): ReportDownload => {
    const params = regionParams(regionId);
    return api.get<Blob>('/api/reports/manual-review-report/', { responseType: 'blob', params });
  },
};
