import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { act, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { createDeferred } from '../../shared/test/deferred';
import { AuthProvider, useAuth } from '../auth/AuthContext';
import UsersPage from './UsersPage';

// Two boundaries are mocked and nothing else. The staff-user service is
// replaced so the page's own behaviour is what is under test; its transport
// semantics are covered separately. The auth adapter is replaced so the real
// AuthProvider can restore a session, which keeps the page's access and
// region rules tied to the actual role and permission table.
vi.mock('./api', () => ({
  fetchStaffUsers: vi.fn(),
  fetchRegions: vi.fn(),
  createStaffUser: vi.fn(),
}));

vi.mock('../../shared/api/client', () => ({
  subscribeSessionExpired: vi.fn(() => () => {}),
}));

vi.mock('../auth/api', () => ({
  authAPI: {
    restoreSession: vi.fn(),
    login: vi.fn(),
    logout: vi.fn(),
    getMe: vi.fn(),
  },
}));

import { authAPI } from '../auth/api';
import {
  createStaffUser,
  fetchRegions,
  fetchStaffUsers,
} from './api';

const REGIONS = [
  { id: 'canada', name: 'מעונות קנדה' },
  { id: 'broshim', name: 'מעונות ברושים' },
];

// One region employee and one region-less central admin: between them they
// exercise both region-name paths the page implements.
const STAFF_USERS = [
  {
    id: 7,
    name: 'Ada Lovelace',
    email: 'ada@example.edu',
    role: 'employee',
    regionId: 'canada',
    regionName: 'מעונות קנדה',
  },
  {
    id: 2,
    name: 'Grace Hopper',
    email: 'grace@example.edu',
    role: 'central_admin',
    regionId: null,
  },
];

const signedInAs = (role) => ({
  id: 3,
  name: 'Dorm Staff',
  email: 'dorm.staff@example.edu',
  role,
  region: 'canada',
  region_name: 'מעונות קנדה',
});

// The application only ever mounts this page behind its authenticated-route
// guard, so the restored session is always in place before the page's first
// render. This mirrors that guard; without it the page would be mounted as a
// signed-out visitor first, which is a state it never sees in the app.
function WhenSignedIn({ children }) {
  const { loading, user } = useAuth();

  if (loading || !user) return <p>restoring session</p>;

  return children;
}

function renderUsersPage({ role = 'central_admin' } = {}) {
  authAPI.restoreSession.mockResolvedValue({
    access: 'access-1',
    user: signedInAs(role),
  });

  return render(
    <AuthProvider>
      <WhenSignedIn>
        <UsersPage language="en" />
      </WhenSignedIn>
    </AuthProvider>
  );
}

// Renders, waits for session restoration and the first load to settle, and
// returns the rendered table.
async function renderLoadedPage({ role = 'central_admin' } = {}) {
  const utils = renderUsersPage({ role });

  await screen.findByRole('table');

  return utils;
}

const dialog = () => within(screen.getByRole('dialog'));

beforeEach(() => {
  authAPI.restoreSession.mockResolvedValue(null);

  fetchStaffUsers.mockResolvedValue(STAFF_USERS);
  fetchRegions.mockResolvedValue(REGIONS);
  createStaffUser.mockResolvedValue(null);
});

describe('UsersPage staff list', () => {
  it('shows the loading state and no empty result while the fetch is pending', async () => {
    const pendingUsers = createDeferred();

    fetchStaffUsers.mockReturnValue(pendingUsers.promise);

    renderUsersPage();

    expect(
      await screen.findByRole('heading', { name: 'Loading users...' })
    ).toBeInTheDocument();

    // Nothing may claim there are no users while the answer is unknown.
    expect(screen.queryByText('There are no users yet')).not.toBeInTheDocument();
    expect(screen.queryByText('No matching users')).not.toBeInTheDocument();
    expect(screen.queryByRole('table')).not.toBeInTheDocument();

    await act(async () => {
      pendingUsers.resolve(STAFF_USERS);
    });

    expect(
      screen.queryByRole('heading', { name: 'Loading users...' })
    ).not.toBeInTheDocument();
    expect(screen.getByRole('table')).toBeInTheDocument();
  });

  it('renders the loaded staff users with their role and region labels', async () => {
    await renderLoadedPage();

    // Scoped to the table: the same role and region words also appear in the
    // filter controls above it.
    const table = within(screen.getByRole('table'));

    expect(table.getByText('Ada Lovelace')).toBeInTheDocument();
    expect(table.getByText('#7')).toBeInTheDocument();
    expect(
      table.getByRole('link', { name: 'ada@example.edu' })
    ).toHaveAttribute('href', 'mailto:ada@example.edu');
    expect(table.getByText('Employee')).toBeInTheDocument();
    expect(table.getByText('Canada Dormitories')).toBeInTheDocument();

    expect(table.getByText('Grace Hopper')).toBeInTheDocument();
    expect(table.getByText('Central Admin')).toBeInTheDocument();

    // A user with no region falls back to the page's all-regions wording.
    expect(table.getByText('All Regions')).toBeInTheDocument();
  });

  it('shows the empty state after a successful empty response', async () => {
    fetchStaffUsers.mockResolvedValue([]);
    fetchRegions.mockResolvedValue([]);

    renderUsersPage();

    expect(
      await screen.findByRole('heading', { name: 'There are no users yet' })
    ).toBeInTheDocument();
    expect(
      screen.getByText('Add the first user to start managing the system team.')
    ).toBeInTheDocument();
    expect(screen.queryByRole('table')).not.toBeInTheDocument();
  });

  it('reports a failed load and reloads when the retry control is used', async () => {
    const user = userEvent.setup();
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {});

    fetchStaffUsers.mockRejectedValueOnce(
      new Error('The staff users are unavailable.')
    );

    renderUsersPage();

    const alert = await screen.findByRole('alert');

    expect(
      within(alert).getByRole('heading', {
        name: 'The users could not be loaded.',
      })
    ).toBeInTheDocument();
    expect(
      within(alert).getByText('The staff users are unavailable.')
    ).toBeInTheDocument();
    expect(consoleError).toHaveBeenCalledWith(
      'Unable to load staff users:',
      expect.any(Error)
    );

    await user.click(within(alert).getByRole('button', { name: 'Try Again' }));

    expect(await screen.findByRole('table')).toBeInTheDocument();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    expect(fetchStaffUsers).toHaveBeenCalledTimes(2);

    consoleError.mockRestore();
  });

  it('denies the page to a role without user management and loads nothing', async () => {
    renderUsersPage({ role: 'employee' });

    expect(
      await screen.findByRole('heading', {
        name: 'You do not have permission to view this page.',
      })
    ).toBeInTheDocument();

    expect(fetchStaffUsers).not.toHaveBeenCalled();
    expect(fetchRegions).not.toHaveBeenCalled();
    expect(screen.queryByRole('button', { name: 'Add User' })).not.toBeInTheDocument();
  });
});

// These fill a real form field by field. Typing without the default
// inter-keystroke delay keeps them quick without changing what is typed or
// which events the page receives.
describe('UsersPage staff creation', () => {
  it('submits a new employee for a regional manager against their own region', async () => {
    const user = userEvent.setup({ delay: null });

    createStaffUser.mockResolvedValue({
      id: 11,
      name: 'New Person',
      email: 'new.staff@example.edu',
      role: 'employee',
      regionId: 'canada',
      regionName: 'מעונות קנדה',
    });

    await renderLoadedPage({ role: 'region_boss' });

    await user.click(screen.getByRole('button', { name: 'Add User' }));

    expect(
      dialog().getByText(
        'A regional manager can add employees to their own region only.'
      )
    ).toBeInTheDocument();

    // A regional manager may not choose either the role or the region: the
    // region is pre-filled from their own session.
    expect(dialog().getByLabelText('Role')).toBeDisabled();
    expect(dialog().getByLabelText('Region')).toBeDisabled();
    expect(dialog().getByLabelText('Region')).toHaveValue('canada');

    await user.type(dialog().getByLabelText('Full Name'), '  New Person  ');
    await user.type(
      dialog().getByLabelText('Email'),
      'New.Staff@Example.edu'
    );
    await user.type(
      dialog().getByLabelText('Temporary Password'),
      'temp-pass-12'
    );

    await user.click(dialog().getByRole('button', { name: 'Create User' }));

    expect(createStaffUser).toHaveBeenCalledTimes(1);
    expect(createStaffUser).toHaveBeenCalledWith({
      name: 'New Person',
      email: 'new.staff@example.edu',
      password: 'temp-pass-12',
      role: 'employee',
      regionId: 'canada',
    });

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(
      within(screen.getByRole('status')).getByText(
        'The user was added successfully.'
      )
    ).toBeInTheDocument();
    expect(
      within(screen.getByRole('table')).getByText('New Person')
    ).toBeInTheDocument();
  });

  it('rejects an address the page considers invalid without calling the service', async () => {
    const user = userEvent.setup({ delay: null });

    await renderLoadedPage({ role: 'central_admin' });

    await user.click(screen.getByRole('button', { name: 'Add User' }));

    await user.type(dialog().getByLabelText('Full Name'), 'New Person');
    await user.type(dialog().getByLabelText('Email'), 'staff@technion');
    await user.type(
      dialog().getByLabelText('Temporary Password'),
      'temp-pass-12'
    );
    await user.selectOptions(dialog().getByLabelText('Region'), 'canada');

    await user.click(dialog().getByRole('button', { name: 'Create User' }));

    expect(createStaffUser).not.toHaveBeenCalled();
    expect(
      within(dialog().getByRole('alert')).getByText(
        'Enter a valid email address.'
      )
    ).toBeInTheDocument();
    expect(screen.getByRole('dialog')).toBeInTheDocument();
  });

  it('keeps the form open and usable when the service rejects the new user', async () => {
    const user = userEvent.setup({ delay: null });
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {});

    createStaffUser.mockRejectedValue(
      new Error('A user with this email already exists.')
    );

    await renderLoadedPage({ role: 'region_boss' });

    await user.click(screen.getByRole('button', { name: 'Add User' }));

    await user.type(dialog().getByLabelText('Full Name'), 'New Person');
    await user.type(
      dialog().getByLabelText('Email'),
      'new.staff@example.edu'
    );
    await user.type(
      dialog().getByLabelText('Temporary Password'),
      'temp-pass-12'
    );

    await user.click(dialog().getByRole('button', { name: 'Create User' }));

    expect(createStaffUser).toHaveBeenCalledTimes(1);
    expect(
      within(dialog().getByRole('alert')).getByText(
        'A user with this email already exists.'
      )
    ).toBeInTheDocument();

    // The dialog stays open with the typed values and an enabled submit, so
    // the attempt can be corrected and repeated.
    expect(dialog().getByLabelText('Full Name')).toHaveValue('New Person');
    expect(dialog().getByRole('button', { name: 'Create User' })).toBeEnabled();
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
    expect(consoleError).toHaveBeenCalledWith(
      'Unable to create user:',
      expect.any(Error)
    );

    consoleError.mockRestore();
  });
});
