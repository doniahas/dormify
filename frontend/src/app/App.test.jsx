import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { createDeferred } from '../shared/test/deferred';
import App from './App';

// App owns AuthProvider and BrowserRouter, so it is rendered as-is and the
// initial location is chosen through the real history API. Only the leaves
// are replaced: every page and both shell components become markers, so the
// route topology, the guard and the redirects stay real while the test does
// not have to satisfy fifteen unrelated page dependencies.
vi.mock('../shared/api/client', () => ({
  subscribeSessionExpired: vi.fn(() => () => {}),
}));

vi.mock('../features/auth/api', () => ({
  authAPI: {
    restoreSession: vi.fn(),
    login: vi.fn(),
    logout: vi.fn(),
    getMe: vi.fn(),
  },
}));

vi.mock('./Header', () => ({
  default: ({ language, onLanguageToggle }) => (
    <>
      <p>app header</p>
      <p>{`shell language: ${language}`}</p>
      <button onClick={onLanguageToggle}>toggle application language</button>
    </>
  ),
}));
vi.mock('./Sidebar', () => ({ default: () => <p>app sidebar</p> }));

vi.mock('../features/auth/LoginPage', () => ({ default: () => <p>login page</p> }));
vi.mock('../features/dashboard/HomePage', () => ({ default: () => <p>dashboard page</p> }));
vi.mock('../features/students/StudentsPage', () => ({ default: () => <p>students page</p> }));
vi.mock('../features/analytics/AnalysisPage', () => ({ default: () => <p>analysis page</p> }));
vi.mock('../features/inventory/BuildingsPage', () => ({ default: () => <p>buildings page</p> }));
vi.mock('../features/uploads/UploadPage', () => ({ default: () => <p>upload page</p> }));
vi.mock('../features/allocation/AssistedAllocationPage', () => ({
  default: () => <p>assisted allocation page</p>,
}));
vi.mock('../features/allocation/AllocationPage', () => ({ default: () => <p>allocation page</p> }));
vi.mock('../features/allocation/AllocationResultsPage', () => ({
  default: () => <p>allocation results page</p>,
}));
vi.mock('../features/transfers/TransfersPage', () => ({ default: () => <p>transfers page</p> }));
vi.mock('../features/reports/ReportsPage', () => ({ default: () => <p>reports page</p> }));
vi.mock('../features/staff/UsersPage', () => ({ default: () => <p>users page</p> }));
vi.mock('../features/settings/SettingsPage', () => ({ default: () => <p>settings page</p> }));
vi.mock('../features/map/MapPage', () => ({ default: () => <p>map page</p> }));
vi.mock('../features/what-if/WhatIfPage', () => ({ default: () => <p>what if page</p> }));

import { authAPI } from '../features/auth/api';

const authenticatedSession = () => ({
  access: 'access-token-value',
  user: { email: 'staff@example.edu', role: 'central_admin', region: { id: 'haifa' } },
});

const startAt = (path) => {
  window.history.replaceState(null, '', path);
};

beforeEach(() => {
  authAPI.restoreSession.mockResolvedValue(null);
});

describe('App protected routing', () => {
  it('wires the shell and its toggle to the persisted provider language', async () => {
    const user = userEvent.setup();
    localStorage.setItem('dormify_language', 'en');
    authAPI.restoreSession.mockResolvedValue(authenticatedSession());
    startAt('/students');
    render(<App />);

    expect(await screen.findByText('students page')).toBeInTheDocument();
    expect(screen.getByText('shell language: en')).toBeInTheDocument();
    expect(document.documentElement.lang).toBe('en');
    expect(document.documentElement.dir).toBe('ltr');
    expect(document.body.dir).toBe('ltr');

    await user.click(screen.getByRole('button', { name: 'toggle application language' }));
    expect(screen.getByText('shell language: he')).toBeInTheDocument();
    expect(localStorage.getItem('dormify_language')).toBe('he');
    expect(document.documentElement.lang).toBe('he');
    expect(document.documentElement.dir).toBe('rtl');
    expect(document.body.dir).toBe('rtl');
  });

  it('holds a protected route on the loading gate until restoration settles', async () => {
    const restore = createDeferred();
    authAPI.restoreSession.mockReturnValue(restore.promise);

    startAt('/students');
    render(<App />);

    expect(screen.getByText('Loading...')).toBeInTheDocument();
    expect(screen.queryByText('students page')).not.toBeInTheDocument();
    expect(screen.queryByText('login page')).not.toBeInTheDocument();
    expect(window.location.pathname).toBe('/students');

    await act(async () => {
      restore.resolve(null);
    });

    expect(screen.queryByText('Loading...')).not.toBeInTheDocument();
    expect(window.location.pathname).toBe('/login');
  });

  it('redirects an anonymous visitor from a protected route to the login page', async () => {
    authAPI.restoreSession.mockResolvedValue(null);

    startAt('/students');
    render(<App />);

    expect(await screen.findByText('login page')).toBeInTheDocument();
    expect(window.location.pathname).toBe('/login');
    expect(screen.queryByText('students page')).not.toBeInTheDocument();
  });

  it('lets a restored user stay on the requested protected route', async () => {
    authAPI.restoreSession.mockResolvedValue(authenticatedSession());

    startAt('/students');
    render(<App />);

    expect(await screen.findByText('students page')).toBeInTheDocument();
    expect(window.location.pathname).toBe('/students');

    // The protected shell, not a bare route element.
    expect(screen.getByText('app header')).toBeInTheDocument();
    expect(screen.getByText('app sidebar')).toBeInTheDocument();
  });

  it('redirects a restored user away from the login page to the dashboard', async () => {
    authAPI.restoreSession.mockResolvedValue(authenticatedSession());

    startAt('/login');
    render(<App />);

    expect(await screen.findByText('dashboard page')).toBeInTheDocument();
    expect(window.location.pathname).toBe('/dashboard');
    expect(screen.queryByText('login page')).not.toBeInTheDocument();
  });

  it('keeps the /system-overview alias pointing at the analysis page', async () => {
    authAPI.restoreSession.mockResolvedValue(authenticatedSession());

    startAt('/system-overview');
    render(<App />);

    expect(await screen.findByText('analysis page')).toBeInTheDocument();
    expect(window.location.pathname).toBe('/analysis');
  });
});
