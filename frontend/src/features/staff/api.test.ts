import { afterEach, describe, expect, it, vi } from 'vitest';
import MockAdapter from 'axios-mock-adapter';
import type { StaffApiError } from './api';

let activeMock: MockAdapter | undefined;
async function loadUsersApi({ apiUrl = '' }: { apiUrl?: string } = {}) {
  vi.resetModules();
  vi.stubEnv('VITE_API_URL', apiUrl);
  vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('Unexpected separate fetch transport')));
  const client = await import('../../shared/api/client');
  activeMock = new MockAdapter(client.api, { onNoMatch: 'throwException' });
  return {
    ...client,
    ...await import('../auth/api'),
    ...await import('./api'),
    mock: activeMock,
  };
}

afterEach(() => activeMock?.restore());

describe('staff API shared transport', () => {
  it('uses the canonical VITE_API_URL and sends a JSON request', async () => {
    const { api, mock, fetchStaffUsers } = await loadUsersApi({ apiUrl: 'https://staff.example.test/api' });
    mock.onGet('/api/staff-users/').replyOnce(200, []);
    await expect(fetchStaffUsers()).resolves.toEqual([]);
    expect(api.defaults.baseURL).toBe('https://staff.example.test');
    expect(mock.history.get[0].headers?.['Content-Type']).toBe('application/json');
    expect(mock.history.get[0].headers?.Authorization).toBeUndefined();
    expect(mock.history.get[0].withCredentials).toBe(true);
    expect(fetch).not.toHaveBeenCalled();
  });

  it('falls back to the page hostname backend base when the setting is unset', async () => {
    const { api, mock, fetchRegions } = await loadUsersApi();
    mock.onGet('/api/regions/').replyOnce(200, []);
    await expect(fetchRegions()).resolves.toEqual([]);
    expect(api.defaults.baseURL).toBe('http://localhost:8000');
  });

  it('reads and clears the access token held by the shared client', async () => {
    const { mock, authAPI, fetchStaffUsers } = await loadUsersApi();
    mock.onPost('/api/auth/login/').replyOnce(200, { access: 'access-1', user: {} });
    await authAPI.login('dorm.staff@example.edu', 'correct-horse');
    mock.onGet('/api/staff-users/').reply(200, []);
    await fetchStaffUsers();
    expect(mock.history.get[0].headers?.Authorization).toBe('Bearer access-1');
    mock.onPost('/api/auth/logout/').replyOnce(200);
    await authAPI.logout();
    await fetchStaffUsers();
    expect(mock.history.get[1].headers?.Authorization).toBeUndefined();
  });

  it('returns a list whether the body is an array, paginated, or neither', async () => {
    const { mock, fetchStaffUsers, fetchRegions } = await loadUsersApi();
    mock.onGet('/api/staff-users/').replyOnce(200, [{ id: 1 }]);
    mock.onGet('/api/regions/').replyOnce(200, { count: 1, results: [{ id: 2 }] });
    await expect(fetchStaffUsers()).resolves.toEqual([{ id: 1 }]);
    await expect(fetchRegions()).resolves.toEqual([{ id: 2 }]);
    mock.onGet('/api/staff-users/').replyOnce(200, { count: 0 });
    await expect(fetchStaffUsers()).resolves.toEqual([]);
  });

  it('posts a new staff user as JSON and treats an empty response as no content', async () => {
    const { mock, createStaffUser } = await loadUsersApi();
    const payload = { email: 'new.staff@example.edu', role: 'employee' };
    mock.onPost('/api/staff-users/').replyOnce(201, { id: 5, ...payload });
    await expect(createStaffUser(payload)).resolves.toEqual({ id: 5, ...payload });
    expect(mock.history.post[0].headers?.['Content-Type']).toBe('application/json');
    expect(JSON.parse(mock.history.post[0].data)).toEqual(payload);
    mock.onPost('/api/staff-users/').replyOnce(204);
    await expect(createStaffUser(payload)).resolves.toBeNull();
  });

  it('turns failed responses into errors carrying the status and body', async () => {
    const { mock, fetchStaffUsers, createStaffUser } = await loadUsersApi();
    const forbidden = { detail: 'You do not have permission to perform this action.' };
    mock.onGet('/api/staff-users/').replyOnce(403, forbidden);
    const denied: StaffApiError = await fetchStaffUsers().catch((err) => err);
    expect(denied).toBeInstanceOf(Error);
    expect(denied.message).toBe(forbidden.detail);
    expect(denied.status).toBe(403);
    expect(denied.data).toEqual(forbidden);
    mock.onPost('/api/staff-users/').replyOnce(400, { email: ['A user with this email already exists.'] });
    const duplicate: StaffApiError = await createStaffUser({ email: '', role: 'employee' }).catch((err) => err);
    expect(duplicate.message).toBe('A user with this email already exists.');
    expect(duplicate.status).toBe(400);
    mock.onGet('/api/staff-users/').replyOnce(500, '<html>failed</html>');
    const broken: StaffApiError = await fetchStaffUsers().catch((err) => err);
    expect(broken.message).toBe('The request could not be completed.');
    expect(broken.status).toBe(500);
    expect(broken.data).toBeNull();
  });

  it('replays a staff request through the shared refresh flow', async () => {
    const { mock, fetchStaffUsers, getAccessToken } = await loadUsersApi();
    mock.onGet('/api/staff-users/').replyOnce(401);
    mock.onPost('/api/auth/refresh/').replyOnce(200, { access: 'refreshed' });
    mock.onGet('/api/staff-users/').replyOnce(200, [{ id: 2 }]);
    await expect(fetchStaffUsers()).resolves.toEqual([{ id: 2 }]);
    expect(mock.history.post).toHaveLength(1);
    expect(mock.history.get).toHaveLength(2);
    expect(mock.history.get[1].headers?.Authorization).toBe('Bearer refreshed');
    expect(getAccessToken()).toBe('refreshed');
  });

  it('preserves the staff error contract and expires the session when refresh fails', async () => {
    const { mock, fetchStaffUsers, subscribeSessionExpired, getAccessToken } = await loadUsersApi();
    const expired = vi.fn();
    const unsubscribe = subscribeSessionExpired(expired);
    try {
      mock.onGet('/api/staff-users/').replyOnce(401, { detail: 'Session expired' });
      mock.onPost('/api/auth/refresh/').replyOnce(401);
      await expect(fetchStaffUsers()).rejects.toMatchObject({ message: 'Session expired', status: 401, data: { detail: 'Session expired' } });
      expect(expired).toHaveBeenCalledTimes(1);
      expect(getAccessToken()).toBeNull();
      expect(mock.history.get).toHaveLength(1);
    } finally { unsubscribe(); }
  });
});
