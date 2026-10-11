// Shared wire-level shapes that are not tied to one resource.
//
// OWNERSHIP: these types describe the JSON the Django REST Framework API
// serializes - never the ORM models. The source of truth is
// backend/api/serializers/*.py (and the explicit Response({...}) dicts in
// backend/api/views/*.py); when a serializer changes, the matching type here
// changes with it. There is no generated OpenAPI schema: the types are
// hand-maintained and deliberately describe only what the frontend reads.

/** A numeric primary key or a string key such as Region.id. */
export type Id = number | string;

/** ISO-8601 timestamp as serialized by DRF (e.g. "2026-10-07T08:15:30Z"). */
export type IsoDateTime = string;

/** ISO-8601 calendar date as serialized by DRF (e.g. "2026-10-07"). */
export type IsoDate = string;

/** DRF PageNumberPagination envelope. `next`/`previous` are absolute URLs. */
export interface Paginated<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

/**
 * List endpoints answer either with a pagination envelope or, when
 * pagination is disabled for the view, with a plain array. Adapters that
 * must return a list normalize this with shared/api/normalize.ts.
 */
export type ListResponse<T> = Paginated<T> | T[];

/**
 * Bilingual text pairs as some backend payloads carry them
 * (e.g. the dashboard's situation_he/situation_en).
 */
export interface BilingualText {
  he: string;
  en: string;
}

/** The success envelope several action endpoints use. */
export interface MessageResponse {
  success?: boolean;
  message?: string;
  messageEn?: string;
}
