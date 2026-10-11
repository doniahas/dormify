import React from 'react';
import { describe, expect, it } from 'vitest';
import { act, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { createDeferred } from '../shared/test/deferred';
import { renderWithProviders, type TestUser } from '../shared/test/render';
import type { UserRole } from '../shared/api/contracts';
import type { Language } from '../shared/i18n/types';
import Sidebar from './Sidebar';

// The real AuthProvider supplies the capability helpers, so the navigation
// assertions below are tied to the actual role and permission table instead
// of to a hand-written copy of it. Only the HTTP boundary is mocked: the
// session is restored through the shared client from a mocked refresh
// reply, exactly as the app does on load.
const userForRole = (role: UserRole): TestUser => ({
  id: 3,
  name: 'Dorm Staff',
  email: 'dorm.staff@example.edu',
  role,
  region: 'canada',
  region_name: 'מעונות קנדה',
});

// Reading the rendered links once and mapping label to destination keeps
// these assertions on the user-facing contract - the visible label and where
// it leads - while resolving the navigation a single time per assertion.
function navDestinations() {
  return Object.fromEntries(
    screen
      .getAllByRole('link')
      .map((link) => [link.textContent, link.getAttribute('href')])
  );
}

function navLink(label: string) {
  const match = screen
    .getAllByRole('link')
    .find((link) => link.textContent === label);

  if (!match) {
    throw new Error(`No sidebar destination is labelled "${label}"`);
  }

  return match;
}

interface SidebarOptions {
  role?: UserRole;
  language?: Language;
  initialPath?: string;
  onLogout?: () => Promise<void>;
}

async function renderSidebar({
  role = 'central_admin',
  language = 'en',
  initialPath = '/dashboard',
  onLogout,
}: SidebarOptions = {}) {
  const utils = await renderWithProviders(
    <Sidebar collapsed={false} onToggle={() => {}} language={language} />,
    {
      route: initialPath,
      language,
      user: userForRole(role),
      routes: {
        '/dashboard': <p>dashboard route</p>,
        '/students': <p>students route</p>,
        '/login': <p>login route</p>,
      },
      mockApi: (mock) => {
        mock.onPost('/api/auth/logout/').reply(async () => {
          await onLogout?.();
          return [200, { success: true }];
        });
      },
    }
  );

  // Session restoration settles before any assertion, so the capability
  // helpers reflect the restored user rather than the signed-out defaults.
  await screen.findByText('Dorm Staff');

  return utils;
}

describe('Sidebar navigation', () => {
  it('renders the shared destinations with their current routes', async () => {
    await renderSidebar();

    // A representative slice of the navigation, not every entry: these are
    // the destinations every signed-in role is meant to reach.
    expect(navDestinations()).toMatchObject({
      Home: '/dashboard',
      Students: '/students',
      'Buildings and Rooms': '/buildings',
      'Transfer Requests': '/transfers',
      Reports: '/reports',
    });
  });

  it('moves the router to the destination that was clicked', async () => {
    const user = userEvent.setup();

    const { currentPath } = await renderSidebar({ initialPath: '/dashboard' });

    expect(currentPath()).toBe('/dashboard');

    await user.click(navLink('Students'));

    expect(currentPath()).toBe('/students');
    expect(screen.getByText('students route')).toBeInTheDocument();
  });

  it('marks only the destination matching the current route as active', async () => {
    await renderSidebar({ initialPath: '/students' });

    const current = navLink('Students');
    const other = navLink('Reports');

    // aria-current is the accessible signal; the class is what the current
    // implementation styles the active row with. Both are asserted so a
    // change to either one is visible here.
    expect(current).toHaveAttribute('aria-current', 'page');
    expect(current).toHaveClass('active');

    expect(other).not.toHaveAttribute('aria-current');
    expect(other).not.toHaveClass('active');
  });

  it('offers each role only the destinations its permissions allow', async () => {
    const matrix: Array<{ role: UserRole; visible: string[] }> = [
      { role: 'central_admin', visible: ['Upload File', 'Employee Information'] },
      { role: 'region_boss', visible: ['Employee Information'] },
      { role: 'employee', visible: [] },
    ];

    const restricted = ['Upload File', 'Employee Information'];

    for (const { role, visible } of matrix) {
      const { unmount } = await renderSidebar({ role });

      const destinations = navDestinations();

      // Common destinations stay available to every role.
      expect(destinations).toMatchObject({
        Students: '/students',
        'Manual Allocation': '/assisted-allocation',
      });

      for (const label of restricted) {
        if (visible.includes(label)) {
          expect(destinations).toHaveProperty(label);
        } else {
          expect(destinations).not.toHaveProperty(label);
        }
      }

      unmount();
    }
  });

  it('renders its own labels and region badge in the selected language', async () => {
    const { unmount } = await renderSidebar({ language: 'en' });

    expect(navDestinations()).toMatchObject({ Students: '/students' });
    expect(screen.getByText('Canada Dormitories')).toBeInTheDocument();
    expect(screen.getByText('Central Admin')).toBeInTheDocument();

    unmount();

    await renderSidebar({ language: 'he' });

    expect(navDestinations()).toMatchObject({ 'סטודנטים': '/students' });
    expect(screen.getByText('מעונות קנדה')).toBeInTheDocument();
    expect(screen.getByText('מנהל מרכזי')).toBeInTheDocument();
  });

  it('waits for logout to finish before leaving for the login page', async () => {
    const user = userEvent.setup();
    const pendingLogout = createDeferred();

    // The revocation request does not answer until the test releases it.
    const { mock, currentPath } = await renderSidebar({
      initialPath: '/dashboard',
      onLogout: () => pendingLogout.promise,
    });

    await user.click(screen.getByRole('button', { name: 'Logout' }));

    // The revocation call is still in flight, so the session must not be
    // abandoned yet.
    await screen.findByText('Dorm Staff');
    expect(mock.history.post.filter(({ url }) => url === '/api/auth/logout/')).toHaveLength(1);
    expect(currentPath()).toBe('/dashboard');

    await act(async () => {
      pendingLogout.resolve();
    });

    await screen.findByText('login route');
    expect(currentPath()).toBe('/login');
  });
});
