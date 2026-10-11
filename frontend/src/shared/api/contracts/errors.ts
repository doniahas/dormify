// Error bodies the API returns. See the ownership note in common.ts.
//
// The backend builds its hand-written error bodies through
// backend/api/contracts/errors.py (error_body / failure_body); DRF renders
// the rest. The shapes, by origin:
//
//   {detail: "..."}                       DRF exceptions: permission, 404, 405,
//                                         throttling, PermissionDenied raised
//                                         inside a serializer
//   {error: "..."}                        hand-written 400/403/404/409
//   {error: "...", errorEn: "..."}        bilingual variant (imports, inbox)
//   {error: "...", status: "..."}         state conflicts carrying the current
//                                         status (runs, batches) - sometimes
//                                         also run_id
//   {success: false, error: "...", ...}   "failure" envelope of the run and
//                                         what-if endpoints, optionally with
//                                         error_code / error_type / errorEn /
//                                         traceback / region / run_id / run
//   {error: {field: [...]}, errorHe}      login_view wraps serializer.errors
//                                         under `error`
//   {field, code, message}                structured inventory rule violations
//   {error, code, conflicting_numbers}    bulk inventory number conflicts
//   {error, detail}                       bulk inventory rollback
//   {feasible: false, buildings: [],      match-options 404 (student missing)
//    reason}
//   {non_field_errors: ["..."]}           serializer-level validation
//   {field_name: ["message", ...]}        field-level validation
//   a plain string, or an array of strings
//
// shared/api/client.ts flattens any of these into one readable message;
// shared/api/errors.ts (normalizeApiError) exposes the status, the code and
// the field errors alongside that message.

/** A validation message tree as DRF nests it. */
export type ValidationMessages =
  | string
  | ValidationMessages[]
  | { [field: string]: ValidationMessages };

/** DRF serializer errors: field name -> messages (non_field_errors included). */
export type FieldValidationErrors = { [field: string]: ValidationMessages };

/** DRF's own exception body (permission, not-found, method-not-allowed, throttling). */
export interface DetailErrorBody {
  detail: string;
}

/** A hand-written view error (api.contracts.errors.error_body). */
export interface ErrorBody {
  error: string;
  /** English twin of `error`, present on the bilingual endpoints only. */
  errorEn?: string;
  /** The record's current status on a state conflict (409). */
  status?: string;
  run_id?: number;
  [key: string]: unknown;
}

/** The failure envelope of the run / what-if endpoints (api.contracts.errors.failure_body). */
export interface FailureBody {
  success: false;
  error: string;
  errorEn?: string;
  error_code?: string;
  error_type?: string;
  /** Only when DEBUG is on. */
  traceback?: string;
  region?: string;
  run_id?: number;
  run?: Record<string, unknown>;
  [key: string]: unknown;
}

/** A structured rule violation (inventory create/update endpoints). */
export interface StructuredFieldError {
  field: string;
  code: string;
  message: string;
}

/** login_view's 401: the serializer errors under `error`, plus a Hebrew summary. */
export interface LoginErrorBody {
  error: FieldValidationErrors;
  errorHe?: string;
}

/** The union of error body shapes the frontend knows how to read. */
export interface ApiErrorBody {
  detail?: string;
  error?: string | FieldValidationErrors;
  errorEn?: string;
  errorHe?: string;
  error_code?: string;
  error_type?: string;
  message?: string;
  status?: string;
  success?: boolean;
  non_field_errors?: string[];
  field?: string;
  code?: string;
  [field: string]: unknown;
}

/**
 * The raw, field-keyed error dict attached to ApiError.fieldErrors so forms
 * can map messages onto their inputs. It is the whole JSON body as returned.
 */
export type FieldErrors = ApiErrorBody;
