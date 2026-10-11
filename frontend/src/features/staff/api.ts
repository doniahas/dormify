import type { AxiosRequestConfig } from 'axios';
import { api } from '../../shared/api/client';
import type { ApiErrorBody, ListResponse, Region } from '../../shared/api/contracts';
import { asArray } from '../../shared/api/normalize';
import type { StaffUser, StaffUserPayload } from './types';

// The staff page's own error contract: the first readable message from the
// body, plus the raw status and body for the form to inspect.
export class StaffApiError extends Error {
  status: number;
  data: ApiErrorBody | null;

  constructor(message: string, status: number, data: ApiErrorBody | null) {
    super(message);
    this.name = 'StaffApiError';
    this.status = status;
    this.data = data;
  }
}

function parseResponse(data: unknown): unknown {
  if (typeof data !== 'string') return data ?? null;
  try { return JSON.parse(data); } catch { return null; }
}

const firstMessage = (value: unknown): string | undefined =>
  Array.isArray(value) && typeof value[0] === 'string' ? value[0] : undefined;

async function apiRequest<T>(url: string, options: AxiosRequestConfig = {}): Promise<T | null> {
  try {
    const response = await api.request<T>({
      url,
      ...options,
      headers: { 'Content-Type': 'application/json' },
      transformResponse: [parseResponse],
    });
    return response.status === 204 ? null : response.data;
  } catch (cause) {
    const response = (cause as { response?: { status: number; data: unknown } }).response;
    if (!response) throw cause;
    const data = (typeof response.data === 'object' ? response.data : null) as ApiErrorBody | null;
    const message =
      (typeof data?.detail === 'string' ? data.detail : undefined) ||
      firstMessage(data?.email) ||
      firstMessage(data?.role) ||
      firstMessage(data?.regionId) ||
      firstMessage(data?.non_field_errors) ||
      'The request could not be completed.';
    throw new StaffApiError(message, response.status, data);
  }
}

export async function fetchStaffUsers(): Promise<StaffUser[]> {
  const data = await apiRequest<ListResponse<StaffUser>>('/api/staff-users/');
  return asArray<StaffUser>(data);
}

export async function fetchRegions(): Promise<Region[]> {
  const data = await apiRequest<ListResponse<Region>>('/api/regions/');
  return asArray<Region>(data);
}

export async function createStaffUser(userData: StaffUserPayload): Promise<StaffUser | null> {
  return apiRequest<StaffUser>('/api/staff-users/', {
    method: 'POST',
    data: userData,
  });
}
