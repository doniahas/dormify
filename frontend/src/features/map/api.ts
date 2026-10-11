import { api } from "../../shared/api/client";
import type { AnalysisData } from "../analytics/types";

// The map renders the same aggregate the Data Analysis page does, from the
// one analysis endpoint the backend serves. An empty successful body is
// treated as an empty payload so the page can show its empty state.
export async function getMapData(): Promise<AnalysisData> {
  const res = await api.get<AnalysisData | null>("/api/analysis/");
  return res?.data || ({} as AnalysisData);
}
