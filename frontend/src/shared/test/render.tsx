import React, { type ReactElement, type ReactNode } from 'react';
import { render, screen, waitFor, type RenderResult } from '@testing-library/react';
import { MemoryRouter, Route, Routes, useLocation, type InitialEntry } from 'react-router-dom';
import MockAdapter from 'axios-mock-adapter';
import { afterEach } from 'vitest';

import { api } from '../api/client';
import type { AuthenticatedUser } from '../api/contracts';
import { AuthProvider, useAuth } from '../../features/auth/AuthContext';
import { LANGUAGE_STORAGE_KEY } from '../i18n/language';
import type { Language } from '../i18n/types';

/**
 * The user a test signs in as. UserSerializer fields are typed; anything
 * else the real backend might add (or an older screen still reads) is
 * allowed through the index signature.
 */
export type TestUser = Partial<AuthenticatedUser> & Record<string, unknown>;

export interface RenderWithProvidersOptions {
  /** Initial router entry: a path, or a location object carrying `state`. */
  route?: InitialEntry;
  /**
   * Mounts the element as a <Route> at this pattern instead of rendering it
   * unconditionally - for components that read useParams().
   */
  path?: string;
  /** Additional routes, as pattern -> element, e.g. a destination to navigate to. */
  routes?: Record<string, ReactNode>;
  /** The signed-in user, restored through /api/auth/refresh/; null renders anonymously. */
  user?: TestUser | null;
  /** The persisted interface language; AuthProvider reads it from localStorage. */
  language?: Language;
  /** Registers API replies on the mock adapter before anything renders. */
  mockApi?: (mock: MockAdapter) => void;
}

export interface RenderWithProvidersResult extends RenderResult {
  /** The adapter attached to the shared axios client for this render. */
  mock: MockAdapter;
  /** The router's current pathname. */
  currentPath: () => string;
  /** The user the session was restored with. */
  user: TestUser | null;
}

const CURRENT_PATH_ID = 'test-current-path';
const SESSION_ID = 'test-session-state';

export const TEST_ACCESS_TOKEN = 'test-access-token';

// The adapter is attached to the real shared client, so the production
// interceptors (bearer header, refresh/replay) stay in the chain. Exactly one
// adapter exists per test; the hook below detaches it after each test.
let activeMock: MockAdapter | null = null;

function attachMock(): MockAdapter {
  activeMock?.restore();
  activeMock = new MockAdapter(api, { onNoMatch: 'throwException' });
  return activeMock;
}

afterEach(() => {
  activeMock?.restore();
  activeMock = null;
});

// Navigation is observable only from the router.
function CurrentPath(): ReactElement {
  const { pathname } = useLocation();
  return <span hidden data-testid={CURRENT_PATH_ID}>{pathname}</span>;
}

// Mirrors the app shell: ProtectedLayout renders nothing but a loading
// marker until AuthProvider has restored (or failed to restore) the session,
// so a page never mounts before the capability helpers reflect the user.
function SessionGate({ children }: { children: ReactNode }): ReactElement {
  const { loading, user } = useAuth();
  if (loading) return <span hidden data-testid={SESSION_ID}>loading</span>;
  return (
    <>
      <span hidden data-testid={SESSION_ID}>{user ? 'signed-in' : 'anonymous'}</span>
      {children}
    </>
  );
}

/**
 * Renders `ui` inside the real AuthProvider and a MemoryRouter, with the
 * session restored from a mocked /api/auth/refresh/ reply, and resolves once
 * the session has settled - the same moment the app shell lets a page mount.
 */
export async function renderWithProviders(
  ui: ReactElement,
  {
    route = '/',
    path,
    routes = {},
    user = null,
    language = 'he',
    mockApi,
  }: RenderWithProvidersOptions = {}
): Promise<RenderWithProvidersResult> {
  localStorage.setItem(LANGUAGE_STORAGE_KEY, language);

  const mock = attachMock();
  if (user) {
    mock.onPost('/api/auth/refresh/').reply(200, { access: TEST_ACCESS_TOKEN, user });
  } else {
    mock.onPost('/api/auth/refresh/').reply(401, { error: 'no session' });
  }
  mockApi?.(mock);

  const utils = render(
    <AuthProvider>
      <MemoryRouter initialEntries={[route]}>
        <SessionGate>
          {path ? null : ui}
          <Routes>
            {path ? <Route path={path} element={ui} /> : null}
            {Object.entries(routes).map(([pattern, element]) => (
              <Route key={pattern} path={pattern} element={element} />
            ))}
          </Routes>
        </SessionGate>
        <CurrentPath />
      </MemoryRouter>
    </AuthProvider>
  );

  await waitFor(() => {
    expectSettled(screen.getByTestId(SESSION_ID).textContent);
  });

  return {
    ...utils,
    mock,
    user,
    currentPath: () => screen.getByTestId(CURRENT_PATH_ID).textContent ?? '',
  };
}

function expectSettled(state: string | null): void {
  if (state === 'loading') {
    throw new Error('session restoration has not settled yet');
  }
}
