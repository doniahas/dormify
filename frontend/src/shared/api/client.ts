import axios, { type InternalAxiosRequestConfig } from "axios";
import type { FieldErrors } from "./contracts";

// VITE_API_URL is the single public API setting and includes the /api suffix.
// Endpoint adapters already supply /api/... paths, so normalize that suffix
// once for Axios. When unset, fall back to whatever hostname the frontend was
// loaded from (with the backend's port) instead of hardcoding "localhost" - so
// the app works the same via localhost or 127.0.0.1 without breaking the
// host-scoped cookies/CORS state used by authentication.
const configuredApiBase = import.meta.env.VITE_API_URL?.replace(/\/api\/?$/, "");
const API_BASE =
  configuredApiBase ||
  `${window.location.protocol}//${window.location.hostname}:8000`;

// G3-17: withCredentials is now required - the refresh token travels as an
// HttpOnly cookie (set by /api/auth/login/ and /api/auth/refresh/, read
// only by the backend), never as a value JS can see or persist. The access
// token below is kept in memory only.
export const api = axios.create({
  baseURL: API_BASE,
  withCredentials: true,
});

// G3-17: JWTs are no longer written to localStorage at all - the access
// token lives ONLY in this module-level variable (cleared on full page
// reload by design; restoreSession() below re-derives it from the
// HttpOnly refresh cookie on app start) and the refresh token never
// reaches JS in the first place. `dormify_user` / `dormify_language` are
// not tokens - a cached display-only profile and a UI preference,
// deliberately out of scope for this change.
let inMemoryAccessToken: string | null = null;

const setAccessToken = (token: string | null | undefined): void => {
  inMemoryAccessToken = token || null;
};

const getAccessToken = (): string | null => inMemoryAccessToken;

const clearStoredAuth = (): void => {
  setAccessToken(null);
};

/** Per-call options an adapter forwards to axios (cancellation only, today). */
export interface RequestOptions {
  signal?: AbortSignal;
}

type SessionExpiredListener = () => void;

const sessionExpiredListeners = new Set<SessionExpiredListener>();

export function subscribeSessionExpired(listener: SessionExpiredListener): () => void {
  sessionExpiredListeners.add(listener);
  return () => {
    sessionExpiredListeners.delete(listener);
  };
}

function emitSessionExpired(): void {
  for (const listener of sessionExpiredListeners) listener();
}

// The shape of the error objects this module reads. Axios errors match it;
// so does any plain Error, which simply has no `response`.
interface ErrorLike {
  response?: { status?: number; data?: unknown };
  code?: string;
  name?: string;
  message?: string;
}

const asErrorLike = (err: unknown): ErrorLike =>
  typeof err === "object" && err !== null ? (err as ErrorLike) : {};

const asRecord = (value: unknown): Record<string, unknown> | null =>
  typeof value === "object" && value !== null && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;

// Login/refresh bodies have carried the access token under several keys.
// Only a string is a usable token; anything else counts as "no token".
const pickAccessToken = (data: unknown): string | null => {
  const body = asRecord(data);
  if (!body) return null;
  const tokens = asRecord(body.tokens);
  const candidates = [
    body.access,
    body.access_token,
    body.token,
    body.jwt,
    tokens?.access,
    tokens?.access_token,
  ];
  for (const candidate of candidates) {
    if (candidate) return typeof candidate === "string" ? candidate : null;
  }
  return null;
};

// DRF error bodies come in several shapes: a plain string, {detail: "..."},
// {error: "..."}, {non_field_errors: [...]}, a plain array (raised via
// rest_framework.exceptions.ValidationError("message")), or the most common
// serializer shape {field_name: ["message", ...], other_field: [...]}.
// Flatten any of these into one readable string instead of falling through
// to a generic "empty/unknown body" message.
const flattenErrorValue = (value: unknown): string => {
  if (value === null || value === undefined) return "";
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);

  if (Array.isArray(value)) {
    return value.map((v) => flattenErrorValue(v)).filter(Boolean).join("; ");
  }

  if (typeof value === "object") {
    return Object.entries(value)
      .map(([key, v]) => {
        const msg = flattenErrorValue(v);
        if (!msg) return "";
        return key === "non_field_errors" || key === "detail" ? msg : `${key}: ${msg}`;
      })
      .filter(Boolean)
      .join("; ");
  }

  return String(value);
};

// Server errors (5xx from a crashed Django view, a proxy timeout page, etc.)
// often come back as a full HTML document rather than a DRF-rendered JSON
// body. That HTML must never be surfaced as a user-facing message — log it
// for debugging and fall through to the generic "empty/unknown body" case.
const isHtmlBody = (data: unknown): data is string =>
  typeof data === "string" && /^\s*<(!doctype html|html)/i.test(data);

const getErrorMessage = (err: unknown, fallback = "Request failed"): string => {
  const { response, code, message } = asErrorLike(err);
  const data = response?.data;
  const status = response?.status;

  if (isHtmlBody(data)) {
    console.error(`${fallback}: received HTML error body (HTTP ${status || "?"})`, data);
    return `${fallback}: HTTP ${status || "?"} with empty/unknown body`;
  }

  if (typeof data === "string" && data.trim()) {
    return data.length > 400
      ? `${status || ""} ${data.slice(0, 400)}…`
      : data;
  }

  if (data && typeof data === "object" && Object.keys(data).length) {
    const flattened = flattenErrorValue(data);
    if (flattened) return flattened;
  }

  if (Array.isArray(data) && data.length) {
    const flattened = flattenErrorValue(data);
    if (flattened) return flattened;
  }

  if (!response) {
    const codeSuffix = code ? ` [${code}]` : "";
    return `${fallback}: no response from server${codeSuffix} — ${
      message || "Network Error"
    }`;
  }

  return `${fallback}: HTTP ${status || "?"} with empty/unknown body`;
};

// An Error carrying the HTTP status and, when the backend returned a
// field-keyed dict (e.g. {"student_id": ["already exists"]}), that raw dict
// as `fieldErrors`, so callers can map errors to the right form field
// instead of only showing one flattened string.
export class ApiError extends Error {
  status: number | undefined;
  fieldErrors: FieldErrors | undefined;

  constructor(message: string, status?: number, fieldErrors?: FieldErrors) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.fieldErrors = fieldErrors;
  }
}

// Same message resolution as getErrorMessage, but thrown as an ApiError
// with `.status` and `.fieldErrors` attached.
const throwApiError = (err: unknown, fallback?: string): never => {
  const message = getErrorMessage(err, fallback);
  const { response } = asErrorLike(err);
  const fieldErrors = asRecord(response?.data) as FieldErrors | null;
  throw new ApiError(message, response?.status, fieldErrors ?? undefined);
};

// Aborted requests (AbortController / axios CanceledError) are not failures
// and must reach the caller unchanged rather than as a generic error.
export const isRequestCancelled = (err: unknown): boolean => {
  const { code, name } = asErrorLike(err);
  return code === "ERR_CANCELED" || name === "CanceledError";
};

api.interceptors.request.use(
  (config) => {
    const token = getAccessToken();

    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }

    return config;
  },
  (error) => Promise.reject(error)
);

// G3-16: a working refresh flow - a request that 401s because the
// short-lived access token expired mid-session is retried ONCE after a
// silent refresh (via the HttpOnly cookie, never a token this code can
// see). Concurrent 401s share a single in-flight refresh call instead of
// each firing their own (a burst of parallel requests failing together at
// token expiry is the common case, not the exception). The refresh and
// login endpoints are excluded to avoid looping; logout must never refresh.
const NO_REFRESH_RETRY_PATHS = ["/api/auth/login/", "/api/auth/refresh/", "/api/auth/logout/"];
let refreshInFlight: Promise<string> | null = null;

const isNoRefreshPath = (url = ""): boolean =>
  NO_REFRESH_RETRY_PATHS.some((path) => url.includes(path));

const performRefresh = (): Promise<string> => {
  if (!refreshInFlight) {
    refreshInFlight = api
      .post("/api/auth/refresh/")
      .then(({ data }) => {
        const access = pickAccessToken(data);
        if (typeof access !== "string" || !access.trim()) {
          throw new Error("Refresh succeeded but no usable access token was returned.");
        }
        setAccessToken(access);
        return access;
      })
      .catch((err: unknown) => {
        setAccessToken(null);
        // Notify once per shared recovery operation, not once per waiter.
        // Anonymous restore posts directly and never enters this operation.
        emitSessionExpired();
        throw err;
      })
      .finally(() => {
        refreshInFlight = null;
      });
  }
  return refreshInFlight;
};

// The retry flag lives on the request config so the replayed request is
// recognized and never refreshed a second time.
type RetriableRequestConfig = InternalAxiosRequestConfig & {
  _retriedAfterRefresh?: boolean;
};

api.interceptors.response.use(
  (response) => response,
  async (error: unknown) => {
    const original = axios.isAxiosError(error)
      ? (error.config as RetriableRequestConfig | undefined)
      : undefined;
    const status = asErrorLike(error).response?.status;

    if (
      status === 401 &&
      original &&
      !original._retriedAfterRefresh &&
      !isNoRefreshPath(original.url || "")
    ) {
      original._retriedAfterRefresh = true;
      try {
        const access = await performRefresh();
        if (access) {
          original.headers.Authorization = `Bearer ${access}`;
          return api(original);
        }
      } catch {
        // Shared recovery already cleared access and notified subscribers.
        // Preserve the original request's public 401 error contract.
      }
    }

    return Promise.reject(error);
  }
);


export { getAccessToken, setAccessToken, clearStoredAuth, pickAccessToken, getErrorMessage, throwApiError };
