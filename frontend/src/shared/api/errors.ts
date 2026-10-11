// One normalized view of anything a feature adapter or the shared client can
// throw: the axios error itself, the ApiError thrown by throwApiError, or the
// plain Error most adapters wrap getErrorMessage() into.
//
// The `message` is the text a screen shows today for the same value: for a
// raw axios error it is getErrorMessage(err); for an ApiError or an adapter's
// wrapped Error it is err.message (which already holds the getErrorMessage()
// text - re-flattening it would double-prefix); for a thrown string it is the
// string. So a screen that switches from reading err.message to
// normalizeApiError(err).message shows the same words. Everything else
// (status, code, field errors, the raw body) is additional, typed access to
// what the backend actually sent.
import { ApiError, getErrorMessage, isRequestCancelled } from './client';
import type { ApiErrorBody, FieldValidationErrors, StructuredFieldError } from './contracts';

export type ApiErrorKind =
  /** The request was aborted by the caller; not a failure. */
  | 'cancelled'
  /** No HTTP response at all (offline, refused, timed out). */
  | 'network'
  /** The backend answered with an error status. */
  | 'http'
  /** A thrown value with no transport information (an adapter's wrapped Error). */
  | 'unknown';

export interface NormalizedApiError {
  kind: ApiErrorKind;
  /** HTTP status, when a response was received. */
  status: number | null;
  /**
   * The user-facing text the screen shows today (see the header). Note the
   * client's historical quirk: a bare {error: "..."} body flattens to
   * "error: ..." (only `detail` and `non_field_errors` drop their key).
   */
  message: string;
  /** The backend's own sentence (`error`, `detail` or `message` of the body), without that prefix. */
  serverMessage: string | null;
  /** The backend's English twin of the message (`errorEn`), when it sent one. */
  messageEn: string | null;
  /** `error_code`, `error_type` or `code` of the body, when it carries one. */
  code: string | null;
  /** The record's current status on a state conflict (`status` next to `error`). */
  conflictStatus: string | null;
  /** The JSON body as received, when it was an object. */
  body: ApiErrorBody | null;
  /** The body when it is a DRF field-keyed validation dict. */
  fieldErrors: FieldValidationErrors | null;
  /** The body when it is an inventory {field, code, message} violation. */
  structured: StructuredFieldError | null;
}

interface ErrorLike {
  response?: { status?: number; data?: unknown };
  code?: string;
  message?: string;
  isAxiosError?: boolean;
  request?: unknown;
}

const asErrorLike = (err: unknown): ErrorLike =>
  typeof err === 'object' && err !== null ? (err as ErrorLike) : {};

const asRecord = (value: unknown): Record<string, unknown> | null =>
  typeof value === 'object' && value !== null && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;

/** Keys that mark a body as a message envelope rather than a field-error dict. */
const ENVELOPE_KEYS = ['detail', 'error', 'message', 'success', 'field', 'feasible'];

const isFieldErrorDict = (body: Record<string, unknown>): body is FieldValidationErrors => {
  const keys = Object.keys(body);
  if (!keys.length) return false;
  if (ENVELOPE_KEYS.some((key) => key in body)) return false;
  return keys.every((key) => {
    const value = body[key];
    return typeof value === 'string' || Array.isArray(value) || asRecord(value) !== null;
  });
};

const isStructured = (body: Record<string, unknown>): body is StructuredFieldError & Record<string, unknown> =>
  typeof body.field === 'string' && typeof body.code === 'string' && typeof body.message === 'string';

const pickString = (body: Record<string, unknown> | null, ...keys: string[]): string | null => {
  if (!body) return null;
  for (const key of keys) {
    const value = body[key];
    if (typeof value === 'string' && value) return value;
  }
  return null;
};

export const isApiError = (err: unknown): err is ApiError => err instanceof ApiError;

/** Normalize a thrown value into the shape above. Never throws. */
export function normalizeApiError(err: unknown, fallback = 'Request failed'): NormalizedApiError {
  const like = asErrorLike(err);
  const response = like.response;
  const body = asRecord(response?.data);

  if (isApiError(err)) {
    const apiBody = asRecord(err.fieldErrors);
    return {
      kind: err.status !== undefined ? 'http' : 'unknown',
      status: err.status ?? null,
      message: err.message,
      serverMessage: pickString(apiBody, 'error', 'detail', 'message'),
      messageEn: pickString(apiBody, 'errorEn'),
      code: pickString(apiBody, 'error_code', 'error_type', 'code'),
      conflictStatus: pickString(apiBody, 'status'),
      body: (apiBody as ApiErrorBody | null) ?? null,
      fieldErrors: apiBody && isFieldErrorDict(apiBody) ? apiBody : null,
      structured: apiBody && isStructured(apiBody) ? { field: apiBody.field, code: apiBody.code, message: apiBody.message } : null,
    };
  }

  if (isRequestCancelled(err)) {
    return {
      kind: 'cancelled', status: null, message: like.message || 'Request cancelled', serverMessage: null,
      messageEn: null, code: null, conflictStatus: null, body: null, fieldErrors: null, structured: null,
    };
  }

  if (response) {
    return {
      kind: 'http',
      status: typeof response.status === 'number' ? response.status : null,
      message: getErrorMessage(err, fallback),
      serverMessage: pickString(body, 'error', 'detail', 'message'),
      messageEn: pickString(body, 'errorEn'),
      code: pickString(body, 'error_code', 'error_type', 'code'),
      conflictStatus: pickString(body, 'status'),
      body: (body as ApiErrorBody | null) ?? null,
      fieldErrors: body && isFieldErrorDict(body) ? body : null,
      structured: body && isStructured(body) ? { field: body.field, code: body.code, message: body.message } : null,
    };
  }

  const transportFailure = like.isAxiosError === true || like.request !== undefined || like.code !== undefined;
  let message: string;
  if (typeof err === 'string') message = err;
  else if (!transportFailure && typeof like.message === 'string' && like.message) message = like.message;
  else message = getErrorMessage(err, fallback);
  return {
    kind: transportFailure ? 'network' : 'unknown',
    status: null,
    message,
    serverMessage: null,
    messageEn: null,
    code: null,
    conflictStatus: null,
    body: null,
    fieldErrors: null,
    structured: null,
  };
}

/** The HTTP status of a thrown value, or null when none was received. */
export const errorStatus = (err: unknown): number | null => normalizeApiError(err).status;

/** The backend error code of a thrown value, or null. */
export const errorCode = (err: unknown): string | null => normalizeApiError(err).code;
