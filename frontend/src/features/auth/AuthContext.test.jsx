import React, { useState } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { createDeferred } from '../../shared/test/deferred';
import { AuthProvider, useAuth } from './AuthContext';

// The provider's collaborator is the API module, so the mock stops at that
// service boundary: everything below it (axios, interceptors, tokens) is
// covered separately and is deliberately not exercised here.
const sessionListeners = vi.hoisted(() => new Set());

vi.mock('../../shared/api/client', () => ({
  subscribeSessionExpired: vi.fn((listener) => {
    sessionListeners.add(listener);
    return vi.fn(() => sessionListeners.delete(listener));
  }),
}));

vi.mock('./api', () => ({
  authAPI: {
    restoreSession: vi.fn(),
    login: vi.fn(),
    logout: vi.fn(),
    getMe: vi.fn(),
  },
}));

import { authAPI } from './api';
import { subscribeSessionExpired } from '../../shared/api/client';

const CREDENTIALS = { email: 'dorm.staff@example.edu', password: 'correct-horse' };

// The generic message the provider returns for a rejected credential check.
const GENERIC_CREDENTIALS_ERROR = 'כתובת האימייל או הסיסמה שגויים';

// login() returns { success, user, error }; refreshUser() returns the user
// object or null. Both are flattened to one readable line so the assertions
// stay on the public return value rather than on provider internals.
const describeResult = (result) => {
  if (result === null) return 'null';
  if (result === undefined) return 'undefined';

  if (typeof result === 'object' && 'success' in result) {
    return `success=${result.success} user=${result.user?.email ?? 'none'} error=${result.error ?? 'none'}`;
  }

  if (typeof result === 'object') return `user=${result.email ?? 'none'}`;

  return String(result);
};

// A consumer that only reads what the context publicly exposes and calls its
// public methods. No private helper is imported and no React state is
// inspected directly.
function AuthProbe() {
  const { user, loading, error, login, logout, refreshUser, language, setLanguage } = useAuth();
  const [lastResult, setLastResult] = useState('none');

  return (
    <div>
      <p>{`loading: ${String(loading)}`}</p>
      <p>{`user: ${user ? user.email : 'none'}`}</p>
      <p>{`role: ${user?.role ?? 'none'}`}</p>
      <p>{`region: ${user ? String(user.normalizedRegionId) : 'none'}`}</p>
      <p>{`error: ${error ?? 'none'}`}</p>
      <p>{`language: ${language}`}</p>
      <p>{`result: ${lastResult}`}</p>

      <button
        type="button"
        onClick={async () => {
          setLastResult(describeResult(await login(CREDENTIALS.email, CREDENTIALS.password)));
        }}
      >
        run login
      </button>

      <button
        type="button"
        onClick={async () => {
          setLastResult(describeResult(await refreshUser()));
        }}
      >
        run refreshUser
      </button>

      <button
        type="button"
        onClick={async () => {
          await logout();
          setLastResult('logged out');
        }}
      >
        run logout
      </button>

      <button type="button" onClick={() => setLanguage('en')}>
        set language en
      </button>
    </div>
  );
}

const renderProvider = () =>
  render(
    <AuthProvider>
      <AuthProbe />
    </AuthProvider>
  );

const restoredPayload = (user) => ({ access: 'access-token-value', user });

beforeEach(() => {
  authAPI.restoreSession.mockResolvedValue(null);
  authAPI.login.mockResolvedValue(null);
  authAPI.logout.mockResolvedValue(undefined);
  authAPI.getMe.mockResolvedValue(null);
});

describe('AuthProvider session restoration', () => {
  it('clears a restored user on session expiration and unsubscribes on unmount', async () => {
    authAPI.restoreSession.mockResolvedValue(
      restoredPayload({ email: 'expired@example.edu', role: 'employee' }),
    );
    const { unmount } = renderProvider();
    expect(await screen.findByText('user: expired@example.edu')).toBeInTheDocument();

    act(() => { for (const listener of sessionListeners) listener(); });
    expect(screen.getByText('user: none')).toBeInTheDocument();
    expect(subscribeSessionExpired).toHaveBeenCalledTimes(1);
    const unsubscribe = subscribeSessionExpired.mock.results[0].value;
    unmount();
    expect(unsubscribe).toHaveBeenCalledTimes(1);
    expect(sessionListeners.size).toBe(0);
  });

  it('stays loading with no user while restoreSession is still pending', async () => {
    const restore = createDeferred();
    authAPI.restoreSession.mockReturnValue(restore.promise);

    renderProvider();

    expect(screen.getByText('loading: true')).toBeInTheDocument();
    expect(screen.getByText('user: none')).toBeInTheDocument();
    expect(screen.getByText('role: none')).toBeInTheDocument();

    await act(async () => {
      restore.resolve(null);
    });

    expect(screen.getByText('loading: false')).toBeInTheDocument();
    expect(screen.getByText('user: none')).toBeInTheDocument();
  });

  // The shipped authAPI.restoreSession catches its own errors and returns
  // null, so a rejection only reaches the provider's own catch branch. Both
  // paths are covered because both settle the boot gate.
  it.each([
    ['resolves null', () => authAPI.restoreSession.mockResolvedValue(null)],
    ['rejects', () => authAPI.restoreSession.mockRejectedValue(new Error('no session'))],
  ])('settles unauthenticated when restoreSession %s', async (_label, arrange) => {
    arrange();

    renderProvider();

    expect(await screen.findByText('loading: false')).toBeInTheDocument();
    expect(screen.getByText('user: none')).toBeInTheDocument();
    expect(screen.getByText('error: none')).toBeInTheDocument();
  });

  it('exposes the restored user and normalizes an object region', async () => {
    authAPI.restoreSession.mockResolvedValue(
      restoredPayload({
        email: 'restored@example.edu',
        role: 'region_boss',
        region: { id: 'haifa', name: 'Haifa' },
      })
    );

    renderProvider();

    expect(await screen.findByText('loading: false')).toBeInTheDocument();
    expect(screen.getByText('user: restored@example.edu')).toBeInTheDocument();
    expect(screen.getByText('role: region_boss')).toBeInTheDocument();
    expect(screen.getByText('region: haifa')).toBeInTheDocument();
  });
});

describe('AuthProvider login', () => {
  it('forwards the credentials and exposes the normalized user on success', async () => {
    const user = userEvent.setup();

    authAPI.login.mockResolvedValue({
      user: { email: CREDENTIALS.email, role: 'employee', region_id: 'south' },
    });

    renderProvider();
    expect(await screen.findByText('loading: false')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'run login' }));

    expect(authAPI.login).toHaveBeenCalledTimes(1);
    expect(authAPI.login).toHaveBeenCalledWith(CREDENTIALS.email, CREDENTIALS.password);

    expect(screen.getByText(`user: ${CREDENTIALS.email}`)).toBeInTheDocument();
    expect(screen.getByText('role: employee')).toBeInTheDocument();
    expect(screen.getByText('region: south')).toBeInTheDocument();
    expect(
      screen.getByText(`result: success=true user=${CREDENTIALS.email} error=none`)
    ).toBeInTheDocument();

    // The boot gate belongs to session restoration and must not be reused
    // for a submit, or the /login route would unmount the form mid-attempt.
    expect(screen.getByText('loading: false')).toBeInTheDocument();
  });

  it.each([401, 400])(
    'reports the generic credentials error and leaves no user for status %i',
    async (status) => {
      const user = userEvent.setup();

      authAPI.login.mockRejectedValue(Object.assign(new Error('Login failed'), { status }));

      renderProvider();
      expect(await screen.findByText('loading: false')).toBeInTheDocument();

      await user.click(screen.getByRole('button', { name: 'run login' }));

      expect(screen.getByText('user: none')).toBeInTheDocument();
      expect(screen.getByText(`error: ${GENERIC_CREDENTIALS_ERROR}`)).toBeInTheDocument();
      expect(
        screen.getByText(`result: success=false user=none error=${GENERIC_CREDENTIALS_ERROR}`)
      ).toBeInTheDocument();
    }
  );
});

describe('AuthProvider profile refresh and logout', () => {
  it('updates the user from getMe and keeps the previous user when getMe fails', async () => {
    const user = userEvent.setup();

    authAPI.restoreSession.mockResolvedValue(
      restoredPayload({ email: 'before@example.edu', role: 'employee' })
    );
    authAPI.getMe.mockResolvedValue({
      user: { email: 'after@example.edu', role: 'employee' },
    });

    renderProvider();
    expect(await screen.findByText('user: before@example.edu')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'run refreshUser' }));

    expect(screen.getByText('user: after@example.edu')).toBeInTheDocument();
    expect(screen.getByText('result: user=after@example.edu')).toBeInTheDocument();

    // Current contract: a failed profile refresh returns null and does NOT
    // log the user out. It is asserted here exactly as implemented.
    authAPI.getMe.mockRejectedValue(new Error('Failed to load current user'));

    await user.click(screen.getByRole('button', { name: 'run refreshUser' }));

    expect(screen.getByText('result: null')).toBeInTheDocument();
    expect(screen.getByText('user: after@example.edu')).toBeInTheDocument();
  });

  it('calls authAPI.logout and clears the user', async () => {
    const user = userEvent.setup();

    authAPI.restoreSession.mockResolvedValue(
      restoredPayload({ email: 'signed.in@example.edu', role: 'central_admin' })
    );

    renderProvider();
    expect(await screen.findByText('user: signed.in@example.edu')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'run logout' }));

    expect(authAPI.logout).toHaveBeenCalledTimes(1);
    expect(screen.getByText('user: none')).toBeInTheDocument();
    expect(screen.getByText('error: none')).toBeInTheDocument();
    expect(screen.getByText('result: logged out')).toBeInTheDocument();
  });
});

describe('AuthProvider language', () => {
  it('persists the language and applies the matching document direction', async () => {
    const user = userEvent.setup();

    renderProvider();
    expect(await screen.findByText('loading: false')).toBeInTheDocument();

    // No stored preference: the provider defaults to Hebrew and writes it.
    expect(screen.getByText('language: he')).toBeInTheDocument();
    expect(localStorage.getItem('dormify_language')).toBe('he');
    expect(document.documentElement.lang).toBe('he');
    expect(document.documentElement.dir).toBe('rtl');
    expect(document.body.dir).toBe('rtl');

    await user.click(screen.getByRole('button', { name: 'set language en' }));

    expect(screen.getByText('language: en')).toBeInTheDocument();
    expect(localStorage.getItem('dormify_language')).toBe('en');
    expect(document.documentElement.lang).toBe('en');
    expect(document.documentElement.dir).toBe('ltr');
    expect(document.body.dir).toBe('ltr');
  });
});
