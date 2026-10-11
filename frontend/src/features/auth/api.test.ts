import { afterEach, describe, expect, it } from 'vitest';
import MockAdapter from 'axios-mock-adapter';
import { api, getAccessToken, setAccessToken, type ApiError } from '../../shared/api/client';
import { authAPI } from './api';

// The session-level behaviour (refresh, replay, expiry notification) is
// covered by shared/api/client.test.ts; these cases pin the adapter's own
// contract: what it stores, what it returns and how it fails.
const mock = new MockAdapter(api, { onNoMatch: 'throwException' });
afterEach(() => {
  mock.reset();
  setAccessToken(null);
});

const user = { id: 1, email: 'dorm.staff@example.edu', role: 'employee' };

describe('login', () => {
  it('stores the access token and returns the full body', async () => {
    const body = { message: 'ok', messageEn: 'ok', access: 'access-1', user };
    mock.onPost('/api/auth/login/').reply(200, body);

    await expect(authAPI.login(user.email, 'correct-horse')).resolves.toEqual(body);
    expect(getAccessToken()).toBe('access-1');
  });

  it('fails as an ApiError with the status and the field errors of a rejected login', async () => {
    mock.onPost('/api/auth/login/').reply(401, { error: { non_field_errors: ['Invalid credentials'] }, errorHe: 'אימייל או סיסמה שגויים' });

    const error: ApiError = await authAPI.login(user.email, 'wrong').catch((err) => err);

    expect(error.message).toBe('error: Invalid credentials; errorHe: אימייל או סיסמה שגויים');
    expect(error.status).toBe(401);
    expect(error.fieldErrors).toEqual({ error: { non_field_errors: ['Invalid credentials'] }, errorHe: 'אימייל או סיסמה שגויים' });
    expect(getAccessToken()).toBeNull();
  });

  it('refuses a 200 that carries no usable access token', async () => {
    mock.onPost('/api/auth/login/').reply(200, { user });

    await expect(authAPI.login(user.email, 'correct-horse')).rejects.toThrow(
      'Login failed: no response from server — Login succeeded but no access token was returned.'
    );
    expect(getAccessToken()).toBeNull();
  });
});

describe('session restore and profile', () => {
  it('returns the restored session, tolerating a body without a user', async () => {
    mock.onPost('/api/auth/refresh/').replyOnce(200, { access: 'access-2', user });
    await expect(authAPI.restoreSession()).resolves.toEqual({ access: 'access-2', user });
    expect(getAccessToken()).toBe('access-2');

    mock.onPost('/api/auth/refresh/').replyOnce(200, { access: 'access-3' });
    await expect(authAPI.restoreSession()).resolves.toEqual({ access: 'access-3', user: null });
  });

  it('clears the token only when the profile request is unauthorized', async () => {
    setAccessToken('stale');
    mock.onGet('/api/auth/me/').replyOnce(500);
    await expect(authAPI.getMe()).rejects.toThrow('Failed to load current user: HTTP 500 with empty/unknown body');
    expect(getAccessToken()).toBe('stale');

    // The refresh is attempted once by the shared client; when it fails the
    // adapter's own 401 handling drops whatever token was left.
    mock.onGet('/api/auth/me/').replyOnce(401);
    mock.onPost('/api/auth/refresh/').replyOnce(401);
    await expect(authAPI.getMe()).rejects.toThrow(/HTTP 401/);
    expect(getAccessToken()).toBeNull();
  });
});
