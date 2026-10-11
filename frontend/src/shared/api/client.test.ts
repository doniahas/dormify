import { afterEach, describe, expect, it, vi } from 'vitest';
import MockAdapter from 'axios-mock-adapter';

import { createDeferred } from '../test/deferred';
import type { ApiError } from './client';

// The client keeps the access token and the in-flight refresh in module
// state, and resolves its base URL once at import time. Every test therefore
// loads a fresh copy of the module and attaches the adapter to that copy's
// real axios instance, so the production interceptors stay in the chain and
// no state leaks between cases. onNoMatch makes an unexpected request fail
// loudly instead of escaping to the network.
let activeMock: MockAdapter | null = null;
const sessionUnsubscribers: Array<() => void> = [];

interface LoadApiOptions {
  apiUrl?: string;
  removedLegacyBase?: string;
}

async function loadApi({ apiUrl, removedLegacyBase }: LoadApiOptions = {}) {
  vi.resetModules();

  if (apiUrl !== undefined) {
    vi.stubEnv('VITE_API_URL', apiUrl);
  }
  // Test-only reference proving the removed alias is no longer read.
  if (removedLegacyBase !== undefined) {
    vi.stubEnv('VITE_API_BASE', removedLegacyBase);
  }

  const mod = {
    ...await import('./client'),
    ...await import('../../features/auth/api'),
    ...await import('../../features/students/api'),
  };
  activeMock = new MockAdapter(mod.api, { onNoMatch: 'throwException' });

  return { ...mod, mock: activeMock };
}

const EMAIL = 'dorm.staff@example.edu';
const PASSWORD = 'correct-horse';

// Loads the module and establishes a session the way the app does, then
// clears the request log so each test only sees its own traffic.
async function loadApiWithSession(access = 'access-1') {
  const ctx = await loadApi();

  ctx.mock.onPost('/api/auth/login/').replyOnce(200, { access, user: { email: EMAIL } });
  await ctx.authAPI.login(EMAIL, PASSWORD);
  ctx.mock.resetHistory();

  return ctx;
}

const requestsTo = (mock: MockAdapter, method: 'get' | 'post', url: string) =>
  mock.history[method].filter((request) => request.url === url);

afterEach(() => {
  for (const unsubscribe of sessionUnsubscribers.splice(0)) unsubscribe();
  if (activeMock) {
    activeMock.restore();
    activeMock = null;
  }
});

describe('api base URL', () => {
  it('uses the canonical VITE_API_URL when it is set', async () => {
    const { api, studentsAPI, mock } = await loadApi({
      apiUrl: 'https://dorms.example.test/api',
    });

    expect(api.defaults.baseURL).toBe('https://dorms.example.test');
    expect(api.defaults.withCredentials).toBe(true);

    mock.onGet('/api/students/').replyOnce(200, []);
    await studentsAPI.getStudents();

    expect(mock.history.get[0].baseURL).toBe('https://dorms.example.test');
  });

  it('falls back to the page origin on the backend port when it is unset', async () => {
    const { api } = await loadApi({ apiUrl: '' });

    // The page is served from http://localhost:3001 in this environment, so
    // the protocol and hostname are inherited and only the port is fixed.
    expect(api.defaults.baseURL).toBe('http://localhost:8000');
  });

  it('does not read the removed VITE_API_BASE alias', async () => {
    const { api } = await loadApi({
      apiUrl: '',
      removedLegacyBase: 'https://legacy.example.test',
    });

    expect(api.defaults.baseURL).toBe('http://localhost:8000');
  });
});

describe('api requests and the access token', () => {
  it('forwards query parameters and returns the response body', async () => {
    const { studentsAPI, mock } = await loadApi();
    const page = { count: 2, next: null, results: [{ id: 1 }, { id: 2 }] };

    mock.onGet('/api/students/').replyOnce(200, page);

    const data = await studentsAPI.getStudents({ status: 'unassigned', page: 1 });

    expect(data).toEqual(page);
    expect(mock.history.get).toHaveLength(1);
    expect(mock.history.get[0].url).toBe('/api/students/');
    expect(mock.history.get[0].params).toEqual({ status: 'unassigned', page: 1 });
  });

  it('sends no Authorization header before a session exists, and a Bearer token after login', async () => {
    const { api, authAPI, getAccessToken, mock } = await loadApi();

    mock.onGet('/api/students/').replyOnce(200, []);
    await api.get('/api/students/');

    expect(mock.history.get[0].headers?.Authorization).toBeUndefined();
    expect(getAccessToken()).toBeNull();

    mock
      .onPost('/api/auth/login/')
      .replyOnce(200, { access: 'access-1', user: { email: EMAIL } });

    const data = await authAPI.login(EMAIL, PASSWORD);

    expect(mock.history.post).toHaveLength(1);
    expect(mock.history.post[0].url).toBe('/api/auth/login/');
    expect(mock.history.post[0].method).toBe('post');
    expect(JSON.parse(mock.history.post[0].data)).toEqual({
      email: EMAIL,
      password: PASSWORD,
    });
    expect(data).toEqual({ access: 'access-1', user: { email: EMAIL } });
    expect(getAccessToken()).toBe('access-1');

    mock.onGet('/api/students/').replyOnce(200, []);
    await api.get('/api/students/');

    expect(mock.history.get[1].headers?.Authorization).toBe('Bearer access-1');

    // The access token is memory-only and the refresh token is an HttpOnly
    // cookie, so browser storage must stay untouched by the transport.
    expect(localStorage.length).toBe(0);
    expect(sessionStorage.length).toBe(0);
  });
});

describe('api session restoration', () => {
  it('restores a session from the refresh endpoint and keeps the access token', async () => {
    const { authAPI, getAccessToken, mock } = await loadApi();

    mock
      .onPost('/api/auth/refresh/')
      .replyOnce(200, { access: 'access-1', user: { email: EMAIL } });

    const restored = await authAPI.restoreSession();

    expect(restored).toEqual({ access: 'access-1', user: { email: EMAIL } });
    expect(getAccessToken()).toBe('access-1');
    expect(requestsTo(mock, 'post', '/api/auth/refresh/')).toHaveLength(1);
  });

  it('returns null and holds no token when there is no valid session', async () => {
    const { authAPI, getAccessToken, mock } = await loadApi();

    mock.onPost('/api/auth/refresh/').replyOnce(401);

    await expect(authAPI.restoreSession()).resolves.toBeNull();
    expect(getAccessToken()).toBeNull();

    // The refresh endpoint is excluded from the retry path, so a failed
    // restore must not trigger a second refresh.
    expect(requestsTo(mock, 'post', '/api/auth/refresh/')).toHaveLength(1);
  });
});

describe('api refresh and retry', () => {
  // These cover both halves of the contract: the requests that leave the
  // client, and the value the original caller finally receives. The second
  // half is not incidental - axios 1.13.3 discarded whatever a response
  // interceptor returned when it recovered from a rejection, so a successful
  // refresh and replay handed the caller its own request config instead of
  // the replayed body, silently emptying the screen at every token expiry.
  it('refreshes once and replays the original request with the new token', async () => {
    const { studentsAPI, getAccessToken, mock } = await loadApiWithSession();
    const page = { count: 1, next: null, results: [{ id: 1 }] };

    // The retry reuses the original request's config object and rewrites its
    // Authorization header, so the header the first attempt actually carried
    // has to be read while that attempt is being served.
    let firstAttemptAuth: unknown = null;

    mock.onGet('/api/students/').replyOnce((config) => {
      firstAttemptAuth = config.headers?.Authorization;
      return [401];
    });
    mock.onPost('/api/auth/refresh/').replyOnce(200, { access: 'access-2' });
    mock.onGet('/api/students/').replyOnce(200, page);

    const data = await studentsAPI.getStudents();

    // The replay is only useful if its response reaches the caller that was
    // interrupted by the 401.
    expect(data).toEqual(page);

    expect(requestsTo(mock, 'post', '/api/auth/refresh/')).toHaveLength(1);

    const studentCalls = requestsTo(mock, 'get', '/api/students/');
    expect(studentCalls).toHaveLength(2);
    expect(firstAttemptAuth).toBe('Bearer access-1');
    expect(studentCalls[1].headers?.Authorization).toBe('Bearer access-2');
    expect(getAccessToken()).toBe('access-2');
  });

  it('hands the replayed profile back to getMe after a refresh', async () => {
    const { authAPI, mock } = await loadApiWithSession();
    const profile = { user: { email: EMAIL, role: 'central_admin' } };

    mock.onGet('/api/auth/me/').replyOnce(401);
    mock.onPost('/api/auth/refresh/').replyOnce(200, { access: 'access-2' });
    mock.onGet('/api/auth/me/').replyOnce(200, profile);

    // This is the path AuthContext.refreshUser() runs on, and the most
    // user-visible one: a profile lost between the replay and the caller
    // signs a still-valid session out of the UI.
    await expect(authAPI.getMe()).resolves.toEqual(profile);

    const meCalls = requestsTo(mock, 'get', '/api/auth/me/');
    expect(meCalls).toHaveLength(2);
    expect(meCalls[1].headers?.Authorization).toBe('Bearer access-2');
    expect(requestsTo(mock, 'post', '/api/auth/refresh/')).toHaveLength(1);
  });

  it('replays a request at most once even while the endpoint keeps answering 401', async () => {
    const { studentsAPI, mock } = await loadApiWithSession();

    mock.onPost('/api/auth/refresh/').reply(200, { access: 'access-2' });
    mock.onGet('/api/students/').reply(401);

    await expect(studentsAPI.getStudents()).rejects.toThrow(/HTTP 401/);

    // Exactly one refresh and exactly one replay: the retry flag on the
    // original request is what stops this from looping.
    expect(requestsTo(mock, 'post', '/api/auth/refresh/')).toHaveLength(1);
    expect(requestsTo(mock, 'get', '/api/students/')).toHaveLength(2);
  });

  it('propagates the original error and drops the token when the refresh fails', async () => {
    const { authAPI, getAccessToken, mock } = await loadApiWithSession();

    mock.onGet('/api/auth/me/').replyOnce(401);
    mock.onPost('/api/auth/refresh/').replyOnce(401);

    await expect(authAPI.getMe()).rejects.toThrow(
      'Failed to load current user: HTTP 401 with empty/unknown body'
    );

    // This case checks the token and error contract; subscriber notification
    // and React state are covered by the session-expiration regressions.
    expect(getAccessToken()).toBeNull();
    expect(requestsTo(mock, 'get', '/api/auth/me/')).toHaveLength(1);
    expect(requestsTo(mock, 'post', '/api/auth/refresh/')).toHaveLength(1);
  });

  it('shares a single refresh between requests that fail together', async () => {
    const { api, mock } = await loadApiWithSession();

    // The refresh reply waits until both protected requests have been
    // rejected, so the concurrent case is reproduced without any timing
    // guess: whichever request arrives second must join the in-flight
    // refresh rather than starting its own.
    let unauthorized = 0;
    const bothRejected = createDeferred();

    const rejectOnce = (): [number] => {
      unauthorized += 1;
      if (unauthorized === 2) bothRejected.resolve();
      return [401];
    };

    mock.onGet('/api/students/').replyOnce(rejectOnce);
    mock.onGet('/api/buildings/').replyOnce(rejectOnce);

    mock.onPost('/api/auth/refresh/').reply(async () => {
      await bothRejected.promise;
      return [200, { access: 'access-2' }];
    });

    mock.onGet('/api/students/').replyOnce(200, { id: 'students' });
    mock.onGet('/api/buildings/').replyOnce(200, { id: 'buildings' });

    // Both callers get their own replayed body back - not each other's, and
    // not the request config the shared refresh was resumed from.
    const [students, buildings] = await Promise.all([
      api.get('/api/students/'),
      api.get('/api/buildings/'),
    ]);

    expect(students.data).toEqual({ id: 'students' });
    expect(buildings.data).toEqual({ id: 'buildings' });

    expect(requestsTo(mock, 'post', '/api/auth/refresh/')).toHaveLength(1);

    const studentCalls = requestsTo(mock, 'get', '/api/students/');
    const buildingCalls = requestsTo(mock, 'get', '/api/buildings/');
    expect(studentCalls).toHaveLength(2);
    expect(buildingCalls).toHaveLength(2);
    expect(studentCalls[1].headers?.Authorization).toBe('Bearer access-2');
    expect(buildingCalls[1].headers?.Authorization).toBe('Bearer access-2');
  });
});

describe('api session expiration', () => {
  it.each([1, 2])('notifies once when %i protected request(s) share a failed refresh', async (requestCount) => {
    const { studentsAPI, subscribeSessionExpired, getAccessToken, mock } = await loadApiWithSession();
    const expired = vi.fn();
    const otherListener = vi.fn();
    const removedListener = vi.fn();
    sessionUnsubscribers.push(subscribeSessionExpired(expired));
    sessionUnsubscribers.push(subscribeSessionExpired(otherListener));
    const unsubscribe = subscribeSessionExpired(removedListener);
    unsubscribe();

    let unauthorized = 0;
    const allRejected = createDeferred();
    mock.onGet('/api/students/').reply(() => {
      if (++unauthorized === requestCount) allRejected.resolve();
      return [401];
    });
    mock.onPost('/api/auth/refresh/').reply(async () => {
      await allRejected.promise;
      return [401];
    });

    const results = await Promise.allSettled(
      Array.from({ length: requestCount }, () => studentsAPI.getStudents()),
    );
    for (const result of results) {
      expect(result.status).toBe('rejected');
      expect((result as PromiseRejectedResult).reason.message).toBe('Failed to load students: HTTP 401 with empty/unknown body');
    }
    expect(requestsTo(mock, 'post', '/api/auth/refresh/')).toHaveLength(1);
    expect(requestsTo(mock, 'get', '/api/students/')).toHaveLength(requestCount);
    expect(getAccessToken()).toBeNull();
    expect(expired).toHaveBeenCalledTimes(1);
    expect(otherListener).toHaveBeenCalledTimes(1);
    expect(removedListener).not.toHaveBeenCalled();
  });

  it('keeps anonymous restore silent when the refresh endpoint returns 401', async () => {
    const { authAPI, subscribeSessionExpired, getAccessToken, mock } = await loadApi();
    const expired = vi.fn();
    sessionUnsubscribers.push(subscribeSessionExpired(expired));
    mock.onPost('/api/auth/refresh/').replyOnce(401);

    await expect(authAPI.restoreSession()).resolves.toBeNull();
    expect(getAccessToken()).toBeNull();
    expect(requestsTo(mock, 'post', '/api/auth/refresh/')).toHaveLength(1);
    expect(expired).not.toHaveBeenCalled();
  });

  it('does not refresh or replay a logout that returns 401', async () => {
    const { authAPI, subscribeSessionExpired, getAccessToken, mock } = await loadApiWithSession();
    mock.onPost('/api/auth/logout/').reply(401);
    mock.onPost('/api/auth/refresh/').reply(200, { access: 'unwanted-access' });
    await expect(authAPI.logout()).resolves.toBeUndefined();
    expect(requestsTo(mock, 'post', '/api/auth/refresh/')).toHaveLength(0);
    expect(requestsTo(mock, 'post', '/api/auth/logout/')).toHaveLength(1);
    expect(getAccessToken()).toBeNull();

    // A second explicit logout also stays silent for a registered listener.
    const expired = vi.fn();
    sessionUnsubscribers.push(subscribeSessionExpired(expired));
    await authAPI.logout();
    expect(expired).not.toHaveBeenCalled();
    expect(requestsTo(mock, 'post', '/api/auth/refresh/')).toHaveLength(0);
    expect(requestsTo(mock, 'post', '/api/auth/logout/')).toHaveLength(2);
  });

  it.each([{}, { access: '' }, { access: '   ' }, { access: {} }])(
    'ends active recovery when refresh returns 200 with unusable access: %j',
    async (body) => {
      const { studentsAPI, subscribeSessionExpired, getAccessToken, mock } = await loadApiWithSession();
      const expired = vi.fn();
      sessionUnsubscribers.push(subscribeSessionExpired(expired));
      mock.onGet('/api/students/').replyOnce(401);
      mock.onPost('/api/auth/refresh/').replyOnce(200, body);
      mock.onGet('/api/students/').replyOnce(200, { results: [{ id: 'must-not-replay' }] });

      await expect(studentsAPI.getStudents()).rejects.toThrow(/HTTP 401/);
      expect(requestsTo(mock, 'get', '/api/students/')).toHaveLength(1);
      expect(requestsTo(mock, 'post', '/api/auth/refresh/')).toHaveLength(1);
      expect(getAccessToken()).toBeNull();
      expect(expired).toHaveBeenCalledTimes(1);
    },
  );
});

describe('api profile and logout', () => {
  it('reads the current profile from the me endpoint', async () => {
    const { authAPI, mock } = await loadApiWithSession();
    const profile = { user: { email: EMAIL, role: 'central_admin' } };

    mock.onGet('/api/auth/me/').replyOnce(200, profile);

    await expect(authAPI.getMe()).resolves.toEqual(profile);
    expect(requestsTo(mock, 'get', '/api/auth/me/')).toHaveLength(1);
  });

  it('clears the access token on logout whether or not the server call succeeds', async () => {
    const { authAPI, getAccessToken, mock } = await loadApiWithSession();

    mock.onPost('/api/auth/logout/').replyOnce(200);

    await expect(authAPI.logout()).resolves.toBeUndefined();
    expect(requestsTo(mock, 'post', '/api/auth/logout/')).toHaveLength(1);
    expect(getAccessToken()).toBeNull();

    // Best effort: a failing logout call still leaves the client logged out.
    mock.onPost('/api/auth/login/').replyOnce(200, { access: 'access-3', user: {} });
    await authAPI.login(EMAIL, PASSWORD);
    expect(getAccessToken()).toBe('access-3');

    mock.onPost('/api/auth/logout/').replyOnce(500);

    await expect(authAPI.logout()).resolves.toBeUndefined();
    expect(getAccessToken()).toBeNull();
  });
});

describe('api error normalization', () => {
  it('keeps the status and the field errors of a structured backend response', async () => {
    const { studentsAPI, mock } = await loadApiWithSession();
    const fieldErrors = {
      student_id: ['already exists'],
      email: ['Enter a valid email address.'],
    };

    mock.onPost('/api/students/').replyOnce(400, fieldErrors);

    const error: ApiError = await studentsAPI.create({ student_id: '123' }).catch((err) => err);

    expect(error).toBeInstanceOf(Error);
    expect(error.message).toBe(
      'student_id: already exists; email: Enter a valid email address.'
    );
    expect(error.status).toBe(400);
    expect(error.fieldErrors).toEqual(fieldErrors);
  });

  it('never surfaces an HTML error page as a user-facing message', async () => {
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {});
    const { studentsAPI, mock } = await loadApiWithSession();

    mock
      .onPost('/api/students/')
      .replyOnce(500, '<!DOCTYPE html><html><body>Server Error</body></html>', {
        'Content-Type': 'text/html',
      });

    const error: Error = await studentsAPI.create({ student_id: '123' }).catch((err) => err);

    expect(error.message).toBe(
      'Failed to create student: HTTP 500 with empty/unknown body'
    );
    expect(error.message).not.toContain('<html');
    expect(consoleError).toHaveBeenCalled();

    consoleError.mockRestore();
  });

  it('reports an unreachable server as a readable message', async () => {
    const { studentsAPI, mock } = await loadApiWithSession();

    mock.onGet('/api/students/').networkError();

    const error: Error = await studentsAPI.getStudents().catch((err) => err);

    expect(error).toBeInstanceOf(Error);
    expect(error.message).toContain('Failed to load students');
    expect(error.message).toContain('no response from server');
  });

  it('rethrows a cancelled request instead of converting it to a generic error', async () => {
    const { studentsAPI, mock } = await loadApiWithSession();

    mock.onGet('/api/students/').reply(() => new Promise(() => {}));

    const controller = new AbortController();
    const pending = studentsAPI.getStudents({}, { signal: controller.signal });

    controller.abort();

    const error: { code?: string; name?: string } = await pending.catch((err) => err);

    expect(error.code).toBe('ERR_CANCELED');
    expect(error.name).toBe('CanceledError');
  });
});
