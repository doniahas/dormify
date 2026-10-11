// Small, shared normalizers for the API shapes that vary from endpoint to
// endpoint: list vs. pagination envelope, string vs. numeric ids, and the
// continuation URL of a paginated response. Pages keep their own local
// helpers until R4; adapters use these.
import type { Id, ListResponse, Paginated } from './contracts';

function isPaginated<T>(data: unknown): data is Paginated<T> {
  return (
    typeof data === 'object' &&
    data !== null &&
    Array.isArray((data as { results?: unknown }).results)
  );
}

/**
 * Returns the items of a list response whether the view paginated it or
 * answered with a plain array. Anything else (null, an error body, a count
 * envelope without results) becomes an empty list.
 */
export function asArray<T>(data: ListResponse<T> | null | undefined | unknown): T[] {
  if (Array.isArray(data)) return data as T[];
  if (isPaginated<T>(data)) return data.results;
  return [];
}

/**
 * Normalizes an id for comparison or use as a map key. Backend ids are
 * numbers for most models but strings for Region, and URL/query parameters
 * always arrive as strings, so comparisons go through the string form.
 */
export function idOf(value: Id | null | undefined): string {
  return value === null || value === undefined ? '' : String(value);
}

/** Two ids are the same when their normalized forms match. */
export function sameId(a: Id | null | undefined, b: Id | null | undefined): boolean {
  const left = idOf(a);
  return left !== '' && left === idOf(b);
}

/**
 * The `next` link of a pagination envelope is absolute. The shared axios
 * client already carries the base URL, so only the path and query are kept.
 */
export function continuationPath(next: string | null | undefined): string | null {
  if (!next) return null;
  try {
    const url = new URL(next);
    return `${url.pathname}${url.search}`;
  } catch {
    return next;
  }
}
