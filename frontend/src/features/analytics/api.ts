import { api, getErrorMessage } from "../../shared/api/client";
import type { Id } from "../../shared/api/contracts";
import type { AnalysisData } from "./types";

export const analysisAPI = {
  getData: async (regionId: Id | null = null): Promise<AnalysisData> => {
    try {
      const { data } = await api.get<AnalysisData>("/api/analysis/", {
        params: regionId ? { region: regionId } : {},
      });
      return data;
    } catch (err) {
      throw new Error(getErrorMessage(err, "Failed to load analysis data"));
    }
  },
};
