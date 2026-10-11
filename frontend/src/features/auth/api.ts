import { api, getAccessToken, setAccessToken, clearStoredAuth, pickAccessToken, getErrorMessage, throwApiError } from "../../shared/api/client";
import type { AuthSession, LoginResponse, MeResponse, RefreshResponse } from "../../shared/api/contracts";

export const authAPI = {
  login: async (email: string, password: string): Promise<LoginResponse> => {
    try {
      const { data } = await api.post<LoginResponse>("/api/auth/login/", {
        email,
        password,
      });

      const access = pickAccessToken(data);

      if (!access) {
        throw new Error("Login succeeded but no access token was returned.");
      }

      setAccessToken(access);

      return data;
    } catch (err) {
      return throwApiError(err, "Login failed");
    }
  },

  // G3-14/G3-16/G3-17: called on app start to restore a session purely
  // from the HttpOnly refresh cookie - no token is ever read from
  // localStorage. Returns { access, user } on success, or null if there is
  // no valid session (first visit, expired/blacklisted refresh token,
  // logged out elsewhere).
  restoreSession: async (): Promise<AuthSession | null> => {
    try {
      const { data } = await api.post<RefreshResponse>("/api/auth/refresh/");
      const access = pickAccessToken(data);
      setAccessToken(access);
      return { access, user: data?.user || null };
    } catch {
      setAccessToken(null);
      return null;
    }
  },

  getMe: async (): Promise<MeResponse> => {
    try {
      const { data } = await api.get<MeResponse>("/api/auth/me/");
      return data;
    } catch (err) {
      if (axiosStatus(err) === 401) {
        clearStoredAuth();
      }

      throw new Error(getErrorMessage(err, "Failed to load current user"));
    }
  },

  // G3-14: actually revokes the refresh token server-side (blacklists it)
  // instead of only clearing client-side state. Best-effort: even if the
  // network call fails, the in-memory access token is cleared regardless,
  // so the frontend always ends up logged out.
  logout: async (): Promise<void> => {
    try {
      await api.post("/api/auth/logout/");
    } catch {
      // Already logged out / no valid session server-side - not fatal,
      // the client-side state is cleared below either way.
    } finally {
      clearStoredAuth();
    }
  },
};

const axiosStatus = (err: unknown): number | undefined =>
  typeof err === "object" && err !== null
    ? (err as { response?: { status?: number } }).response?.status
    : undefined;

export const debugAuthAPI = { getAccessToken, clearStoredAuth };
