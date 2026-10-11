import { api, getErrorMessage } from "../../shared/api/client";
import type { HomeDashboard } from "./types";

export const homeAPI = {
  get: async (): Promise<HomeDashboard> => {
    try {
      const { data } = await api.get<HomeDashboard>("/api/home/");
      return data;
    } catch (err) {
      throw new Error(getErrorMessage(err, "Failed to load homepage data"));
    }
  },
};
