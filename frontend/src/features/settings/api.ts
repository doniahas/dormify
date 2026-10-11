import { api, getErrorMessage } from "../../shared/api/client";
import type {
  AccountChangeResponse,
  ChangeEmailPayload,
  ChangePasswordPayload,
} from "./types";

export const settingsAPI = {
  changePassword: async (payload: ChangePasswordPayload): Promise<AccountChangeResponse> => {
    try {
      const body = {
        current_password:
          payload.current_password ?? payload.currentPassword,
        new_password:
          payload.new_password ?? payload.newPassword,
        confirm_password:
          payload.confirm_password ?? payload.confirmPassword,
      };

      const { data } = await api.put<AccountChangeResponse>("/api/auth/change-password/", body);
      return data;
    } catch (err) {
      throw new Error(getErrorMessage(err, "Failed to change password"));
    }
  },

  changeEmail: async (payload: ChangeEmailPayload): Promise<AccountChangeResponse> => {
    try {
      const body = {
        current_email:
          payload.current_email ?? payload.currentEmail,
        new_email:
          payload.new_email ?? payload.newEmail,
        confirm_email:
          payload.confirm_email ?? payload.confirmEmail,
        // G3-18: current-password re-authentication, required server-side.
        password: payload.password,
      };

      const { data } = await api.put<AccountChangeResponse>("/api/auth/change-email/", body);
      return data;
    } catch (err) {
      throw new Error(getErrorMessage(err, "Failed to change email"));
    }
  },
};
