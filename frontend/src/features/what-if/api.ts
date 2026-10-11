import { api, getErrorMessage } from "../../shared/api/client";
import type { Id } from "../../shared/api/contracts";
import type {
  AvailabilityChangeInput,
  AvailabilityConfirmInput,
  WhatIfConfirmation,
  WhatIfSimulation,
} from "./types";

export const whatIfAPI = {
  simulateBuildingInactivation: async (buildingIds: Id[]): Promise<WhatIfSimulation> => {
    try {
      const { data } = await api.post<WhatIfSimulation>(
        "/api/what-if/building-inactivation/simulate/",
        {
          building_ids: buildingIds,
        }
      );

      return data;
    } catch (err) {
      throw new Error(
        getErrorMessage(err, "Failed to simulate building inactivation")
      );
    }
  },

  confirmBuildingInactivation: async (
    buildingIds: Id[],
    reason = "Building inactivated"
  ): Promise<WhatIfConfirmation> => {
    try {
      const { data } = await api.post<WhatIfConfirmation>(
        "/api/what-if/building-inactivation/confirm/",
        {
          building_ids: buildingIds,
          reason,
          inactivate_buildings: true,
        }
      );

      return data;
    } catch (err) {
      throw new Error(
        getErrorMessage(err, "Failed to confirm building inactivation")
      );
    }
  },

  simulateAvailabilityChange: async ({
    targetType,
    targetIds,
    action = "inactivate",
  }: AvailabilityChangeInput): Promise<WhatIfSimulation> => {
    try {
      const { data } = await api.post<WhatIfSimulation>("/api/what-if/availability/simulate/", {
        target_type: targetType,
        target_ids: targetIds,
        action,
      });

      return data;
    } catch (err) {
      throw new Error(
        getErrorMessage(err, "Failed to simulate availability change")
      );
    }
  },

  confirmAvailabilityChange: async ({
    targetType,
    targetIds,
    action = "inactivate",
    reason = "Availability changed",
  }: AvailabilityConfirmInput): Promise<WhatIfConfirmation> => {
    try {
      const { data } = await api.post<WhatIfConfirmation>("/api/what-if/availability/confirm/", {
        target_type: targetType,
        target_ids: targetIds,
        action,
        reason,
      });

      return data;
    } catch (err) {
      throw new Error(
        getErrorMessage(err, "Failed to confirm availability change")
      );
    }
  },
};
