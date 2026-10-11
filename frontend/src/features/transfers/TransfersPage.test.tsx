import React from 'react';
import { describe, expect, it, vi } from 'vitest';
import { act, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type MockAdapter from 'axios-mock-adapter';

import { createDeferred } from '../../shared/test/deferred';
import { renderWithProviders, type TestUser } from '../../shared/test/render';
import TransfersPage from './TransfersPage';

// The page talks to the backend only through its typed adapters, which sit
// on the shared axios client; every reply below is registered on that
// client's mock adapter, so the request URLs, parameters and bodies
// asserted here are the ones the backend would receive.

// The bed picker is replaced by the narrowest stand-in that still exercises
// the contract this page owns: it receives the buildings the page loaded and
// hands back a selection built by the picker's real selection helper, and
// it surfaces the paging/error/scope props the page passes. What the real
// picker renders internally is NOT covered here.
vi.mock('../allocation/BedMatchPicker', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../allocation/BedMatchPicker')>();

  type Bed = { bed_id: number; bed_label: string };
  type Room = { room_name: string; beds: Bed[] };
  type Apartment = { rooms: Room[] };
  type Building = { apartments: Apartment[] };

  return {
    ...actual,
    default: ({ buildings, onSelectBed, onLoadMore, hasMore, loading, loadMoreError, scopeContext }: {
      buildings: Building[];
      onSelectBed: (selection: unknown) => void;
      onLoadMore: () => void;
      hasMore: boolean;
      loading?: boolean;
      loadMoreError?: string;
      scopeContext?: string | null;
    }) => (
      <div>
        {loading && <span>picker loading</span>}
        {scopeContext && <span>{`picker scope ${scopeContext}`}</span>}
        {loadMoreError && <span>{`picker error ${loadMoreError}`}</span>}
        {buildings.flatMap((building) =>
          building.apartments.flatMap((apartment) =>
            apartment.rooms.flatMap((room) =>
              room.beds.map((bed) => (
                <button
                  key={bed.bed_id}
                  type="button"
                  onClick={() =>
                    onSelectBed(actual.buildBedSelection(building, apartment, room, bed))
                  }
                >
                  {`pick ${bed.bed_label} in room ${room.room_name}`}
                </button>
              ))
            )
          )
        )}
        {hasMore && <button type="button" onClick={onLoadMore}>load more buildings</button>}
      </div>
    ),
  };
});

// The student search is replaced by a stand-in that offers the fixtures
// below as candidates, applying the filter the wizard passes, so the
// wizards' pick -> payload contract is exercised without the real debounced
// lookup (covered by StudentSearch.test.jsx).
const searchFixtures = vi.hoisted(() => ({ students: [] as Array<Record<string, unknown>> }));

vi.mock('../students/StudentSearch', () => ({
  default: ({ onPick, filter, placeholder }: {
    onPick: (student: Record<string, unknown>) => void;
    filter?: (student: Record<string, unknown>) => boolean;
    placeholder?: string;
  }) => (
    <div>
      <input placeholder={placeholder} readOnly />
      {searchFixtures.students.filter((s) => (filter ? filter(s) : true)).map((s) => (
        <button key={String(s.id)} type="button" onClick={() => onPick(s)}>
          {`pick ${String(s.full_name)}`}
        </button>
      ))}
    </div>
  ),
}));

const regionBoss: TestUser = {
  id: 9,
  email: 'boss@example.edu',
  role: 'region_boss',
  region: 'canada',
  region_name: 'מעונות קנדה',
};

const centralAdmin: TestUser = {
  id: 10,
  email: 'staff@example.edu',
  role: 'central_admin',
  region: 'canada',
  region_name: 'מעונות קנדה',
};

const REMOVAL = {
  id: 11,
  request_number: 'REQ-2026-000011',
  request_type: 'remove_student',
  status: 'pending',
  student_name: 'Ada Lovelace',
  student_id_number: '200100300',
  reason: 'Leaving the dorms at the end of the semester',
  requested_by_name: 'Dorm Staff',
  created_at: '2026-09-01T10:00:00Z',
};

const SWAP = {
  id: 12,
  request_number: 'REQ-2026-000012',
  request_type: 'swap',
  status: 'pending',
  student_name: 'Grace Hopper',
  student_id_number: '200400500',
  swap_with_student_name: 'Linus Pauling',
  swap_with_student_id_number: '200600700',
  reason: 'Both students asked to trade rooms',
  requested_by_name: 'Dorm Staff',
  created_at: '2026-09-02T10:00:00Z',
};

const TRANSFER = {
  id: 13,
  request_number: 'REQ-2026-000013',
  request_type: 'apartment',
  same_apartment: false,
  transfer_scope: 'same_region',
  source_region_name: 'מעונות קנדה',
  status: 'pending',
  student_name: 'Linus Pauling',
  student_id_number: '200600700',
  student_phone: '050-1112222',
  current_region: 'מעונות קנדה',
  current_building: 105,
  current_apartment: '3',
  current_room: 'B',
  current_bed: 'bed 2',
  reason: 'Closer to the faculty',
  requested_by_name: 'Dorm Staff',
  created_at: '2026-09-03T10:00:00Z',
};

const ADD_STUDENT = {
  id: 14,
  request_number: 'REQ-2026-000014',
  request_type: 'add_student',
  status: 'pending',
  student_name: 'Mary Somerville',
  student_id_number: '200800900',
  reason: 'New arrival',
  requested_by_name: 'Dorm Staff',
  created_at: '2026-09-04T10:00:00Z',
};

const REGION_TRANSFER = {
  id: 15,
  request_number: 'REQ-2026-000015',
  request_type: 'region_transfer',
  target_region: 'broshim',
  target_region_name: 'ברושים',
  status: 'pending',
  student_name: 'Emmy Noether',
  student_id_number: '200900100',
  reason: 'Moving faculties',
  requested_by_name: 'Dorm Staff',
  created_at: '2026-09-05T10:00:00Z',
};

const APPROVED = {
  id: 16,
  request_number: 'REQ-2026-000016',
  request_type: 'room',
  same_apartment: true,
  transfer_scope: 'same_region',
  status: 'approved',
  student_name: 'Alan Turing',
  student_id_number: '200300400',
  reason: 'Quieter room',
  requested_by_name: 'Dorm Staff',
  reviewed_by_name: 'Region Boss',
  reviewed_at: '2026-09-07T09:00:00Z',
  target_room_name: 'A',
  target_building_number: 105,
  target_apartment_number: '3',
  final_bed_label: 'bed 1',
  placement_history: [
    { region: 'Canada', building: 105, apartment: '3', room: 'B', assigned_at: '2026-01-10T10:00:00Z', ended_at: '2026-09-07T09:00:00Z' },
  ],
  created_at: '2026-09-06T10:00:00Z',
};

const ALL_REQUESTS = [REMOVAL, SWAP, TRANSFER, ADD_STUDENT, REGION_TRANSFER, APPROVED];

const REGIONS = [
  { id: 'canada', name: 'מעונות קנדה' },
  { id: 'broshim', name: 'ברושים' },
];

const ADA_STUDENT = {
  id: 2,
  student_id: '200100300',
  first_name: 'Ada',
  last_name: 'Lovelace',
  full_name: 'Ada Lovelace',
  is_assigned: true,
  current_building: 105,
  current_apartment: '3',
  current_room: 'B',
  current_bed: 'bed 2',
};

const GRACE_STUDENT = {
  id: 3,
  student_id: '200400500',
  first_name: 'Grace',
  last_name: 'Hopper',
  full_name: 'Grace Hopper',
  is_assigned: true,
  current_building: 110,
  current_apartment: '7',
  current_room: 'A',
  current_bed: 'bed 1',
};

const UNASSIGNED_STUDENT = {
  id: 4,
  student_id: '200700800',
  first_name: 'Rosalind',
  last_name: 'Franklin',
  full_name: 'Rosalind Franklin',
  is_assigned: false,
};

searchFixtures.students = [ADA_STUDENT, GRACE_STUDENT, UNASSIGNED_STUDENT];

const building = (number: number, bedId: number) => ({
  building_id: number,
  building_number: number,
  building_name: `Building ${number}`,
  region_name: 'Canada',
  apartments: [
    {
      apartment_id: number * 10,
      apartment_number: 7,
      rooms: [
        {
          room_id: 500 + number,
          room_name: 'A',
          capacity: 2,
          occupied_beds_count: 1,
          available_beds_count: 1,
          beds: [{ bed_id: bedId, bed_label: `bed ${bedId - 9000}`, is_selectable: true, is_occupied: false }],
        },
      ],
    },
  ],
});

const FEASIBLE = {
  feasible: true,
  buildings: [building(110, 9001)],
  search_regions: [{ id: 'canada', name: 'מעונות קנדה' }],
  total_valid_beds: 1,
  total_buildings: 2,
  total_apartments: 1,
  total_rooms: 1,
  has_more: true,
};

const FEASIBLE_PAGE_TWO = {
  feasible: true,
  buildings: [building(120, 9002)],
  search_regions: [{ id: 'canada', name: 'מעונות קנדה' }],
  total_valid_beds: 2,
  total_buildings: 2,
  total_apartments: 2,
  total_rooms: 2,
  has_more: false,
};

// The page always fetches every status and filters on the client, so the
// list reloaded after a decision is the backend's answer, not a local edit.
const reviewed = (request: Record<string, unknown>, extra: Record<string, unknown>) => ({
  ...request,
  reviewed_by_name: 'Region Boss',
  reviewed_at: '2026-09-03T09:00:00Z',
  ...extra,
});

const UI_TIMEOUT = { timeout: 3000 };
const WORKFLOW_TIMEOUT_MS = 15000;

const button = (label: string) => screen.getByText(label).closest('button')!;
const queryButton = (label: string) => screen.queryByText(label)?.closest('button') ?? null;
const statusTab = (label: string) => screen.getByText(label, { selector: 'button' });
const listCount = () => screen.getByText(/^\d+ requests$/);
// A stat card's accessible name is its count followed by its label.
const statCard = (label: string) => screen.getByRole('button', { name: new RegExp(`^\\d+\\s*${label}$`) });
const dialog = () => screen.getByRole('dialog');
// The type picker's cards (their titles also appear in the type filter and on list rows).
const typeCard = (title: string) => within(dialog()).getByText(title, { selector: 'span' }).closest('button')!;
const wizardButton = (name: string) => within(dialog()).getByRole('button', { name });
// A wizard summary row's value (the step bar may carry the same label as a bare span).
const summaryValue = (label: string) =>
  within(dialog()).getAllByText(label).map((el) => el.nextElementSibling).find((el) => el !== null)!;

const listRequests = (mock: MockAdapter) => mock.history.get.filter(({ url }) => url === '/api/requests/');
const posts = (mock: MockAdapter, url: string) => mock.history.post.filter((r) => r.url === url);
const puts = (mock: MockAdapter, url: string) => mock.history.put.filter((r) => r.url === url);

interface RenderOptions {
  user?: TestUser;
  language?: 'he' | 'en';
  requests?: unknown[];
  mockApi?: (mock: MockAdapter) => void;
}

function mockRequestsApi(mock: MockAdapter, requests: unknown[]) {
  mock.onGet('/api/requests/').reply(200, requests);
  mock.onGet('/api/regions/').reply(200, REGIONS);
  mock.onGet('/api/students/2/').reply(200, { ...ADA_STUDENT, region_id: 'canada', region_name: 'מעונות קנדה' });
  mock.onGet('/api/students/3/').reply(200, { ...GRACE_STUDENT, region_id: 'canada', region_name: 'מעונות קנדה' });
}

function renderPage({ user = regionBoss, language = 'en', requests = [REMOVAL, SWAP], mockApi }: RenderOptions = {}) {
  return renderWithProviders(<TransfersPage />, {
    route: '/transfers',
    language,
    user,
    mockApi: (mock) => {
      mockRequestsApi(mock, requests);
      mockApi?.(mock);
    },
  });
}

async function renderLoadedPage(options?: RenderOptions) {
  const user = userEvent.setup();
  const utils = await renderPage(options);
  await screen.findByText('Ada Lovelace', undefined, UI_TIMEOUT);
  return { ...utils, user };
}

async function openRequest(user: ReturnType<typeof userEvent.setup>, studentName: string) {
  await user.click(screen.getByText(studentName).closest('button')!);
  await screen.findByRole('heading', { name: studentName }, UI_TIMEOUT);
}

describe('TransfersPage list', () => {
  it('shows the loading state, then the requests, their totals and the pick prompt', async () => {
    // The list request is held unresolved by the test, so the page cannot
    // leave its loading state until `pending` is resolved below. The page
    // enters that state from its mount effect, which React flushes after
    // the session gate's commit, so the assertions await it instead of
    // assuming it has already happened when renderPage() returns.
    const pending = createDeferred<unknown>();
    const { mock } = await renderPage({
      requests: ALL_REQUESTS,
      mockApi: (m) => {
        m.onGet('/api/requests/').reply(() => pending.promise.then((body) => [200, body]));
      },
    });

    expect(await screen.findByText('Loading...')).toBeInTheDocument();
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Transfer Requests');
    await waitFor(() => expect(listRequests(mock)).toHaveLength(1));
    expect(listRequests(mock)[0].params).toEqual({});
    // Still pending: the loading state is observed while the request is open.
    expect(screen.getByText('Loading...')).toBeInTheDocument();
    expect(screen.queryByText('Ada Lovelace')).not.toBeInTheDocument();

    await act(async () => { pending.resolve(ALL_REQUESTS); });

    expect(await screen.findByText('Ada Lovelace')).toBeInTheDocument();
    expect(screen.queryByText('Loading...')).not.toBeInTheDocument();
    expect(listCount()).toHaveTextContent('6 requests');

    // The stat cards count every loaded request by status.
    expect(statCard('Total')).toHaveTextContent('6');
    expect(statCard('Pending')).toHaveTextContent('5');
    expect(statCard('Approved')).toHaveTextContent('1');
    expect(statCard('Rejected')).toHaveTextContent('0');
    expect(statCard('Total')).toHaveAttribute('aria-pressed', 'true');

    // Each row carries its number, type label and date; the detail pane
    // waits for a selection.
    expect(screen.getByText('REQ-2026-000013')).toBeInTheDocument();
    expect(screen.getByText('Apt Transfer')).toBeInTheDocument();
    expect(screen.getByText('Remove Student')).toBeInTheDocument();
    expect(screen.getByText('Select a request from the list')).toBeInTheDocument();

    // A regional user never sees the region filter and never loads regions.
    expect(screen.queryByTitle('Filter by region')).not.toBeInTheDocument();
    expect(mock.history.get.filter(({ url }) => url === '/api/regions/')).toHaveLength(0);
  });

  it('shows the empty states when there are no requests at all', async () => {
    // The empty list is delivered by the test, not by timing: the request is
    // held open until the page has issued it, then resolved inside act(),
    // which flushes the resulting state update and render before returning.
    // The empty state is therefore asserted synchronously, with no wait that
    // a slow runner could outlast.
    const pending = createDeferred<unknown[]>();
    const { mock } = await renderPage({
      requests: [],
      mockApi: (m) => {
        m.onGet('/api/requests/').reply(() => pending.promise.then((body) => [200, body]));
      },
    });

    await waitFor(() => expect(listRequests(mock)).toHaveLength(1), UI_TIMEOUT);
    expect(screen.queryByText('No transfer requests yet')).not.toBeInTheDocument();

    await act(async () => { pending.resolve([]); });

    expect(screen.getByText('No transfer requests yet')).toBeInTheDocument();
    expect(screen.getByText('New requests will appear here')).toBeInTheDocument();
    expect(screen.getByText('No requests to display')).toBeInTheDocument();
    expect(listCount()).toHaveTextContent('0 requests');
  });

  it('surfaces a failed list request without an empty state', async () => {
    await renderPage({
      mockApi: (m) => {
        m.onGet('/api/requests/').reply(500, { detail: 'database unavailable' });
      },
    });

    expect(await screen.findByText('database unavailable', undefined, UI_TIMEOUT)).toBeInTheDocument();
    // The page stays usable: the toolbar and the (empty) panes remain.
    expect(screen.getByPlaceholderText('Search...')).toBeInTheDocument();
    expect(listCount()).toHaveTextContent('0 requests');
    expect(screen.getByText('No requests to display')).toBeInTheDocument();
  });

  it('filters by status tab and by request type, clearing the selection', async () => {
    const { user } = await renderLoadedPage({ requests: ALL_REQUESTS });
    await openRequest(user, 'Ada Lovelace');

    await user.click(statusTab('Approved'));
    expect(listCount()).toHaveTextContent('1 requests');
    expect(screen.getByText('Alan Turing')).toBeInTheDocument();
    expect(screen.queryByText('Ada Lovelace')).not.toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Ada Lovelace' })).not.toBeInTheDocument();
    expect(statusTab('Approved')).toHaveAttribute('aria-pressed', 'true');
    expect(statCard('Approved')).toHaveAttribute('aria-pressed', 'true');

    await user.click(statusTab('All'));
    await openRequest(user, 'Grace Hopper');
    await user.selectOptions(screen.getByDisplayValue('All request types'), 'add_student');
    expect(listCount()).toHaveTextContent('1 requests');
    expect(screen.getByText('Mary Somerville')).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Grace Hopper' })).not.toBeInTheDocument();

    // A stat card selects its status and resets the type filter.
    await user.click(statCard('Pending'));
    expect(screen.getByDisplayValue('All request types')).toBeInTheDocument();
    expect(listCount()).toHaveTextContent('5 requests');

    // The "no results" empty state differs from the "no requests" one.
    await user.click(statCard('Rejected'));
    expect(screen.getByText('No requests found')).toBeInTheDocument();
    expect(screen.getByText('Try changing the search or filters')).toBeInTheDocument();
  });

  it('searches by student name, id number and request number', async () => {
    const { user } = await renderLoadedPage({ requests: ALL_REQUESTS });
    const search = screen.getByPlaceholderText('Search...');

    await user.type(search, 'grace');
    expect(listCount()).toHaveTextContent('1 requests');
    expect(screen.getByText('Grace Hopper')).toBeInTheDocument();

    await user.clear(search);
    await user.type(search, '2006007');
    expect(listCount()).toHaveTextContent('1 requests');
    expect(screen.getByText('Linus Pauling')).toBeInTheDocument();

    await user.clear(search);
    await user.type(search, 'req-2026-000016');
    expect(listCount()).toHaveTextContent('1 requests');
    expect(screen.getByText('Alan Turing')).toBeInTheDocument();

    // The clear button next to the box resets the search.
    const clear = search.parentElement!.querySelector('button')!;
    await user.click(clear);
    expect(search).toHaveValue('');
    expect(listCount()).toHaveTextContent('6 requests');
  });

  it('lets a central admin filter by region, which is the one filter sent to the backend', async () => {
    const { user, mock } = await renderLoadedPage({ user: centralAdmin });

    const regionSelect = await screen.findByTitle('Filter by region', undefined, UI_TIMEOUT);
    await waitFor(() => expect(within(regionSelect).getByText('ברושים')).toBeInTheDocument(), UI_TIMEOUT);
    expect(listRequests(mock)[0].params).toEqual({});

    await user.selectOptions(regionSelect, 'broshim');
    await waitFor(() => expect(listRequests(mock)).toHaveLength(2), UI_TIMEOUT);
    expect(listRequests(mock)[1].params).toEqual({ region: 'broshim' });

    await user.selectOptions(regionSelect, 'all');
    await waitFor(() => expect(listRequests(mock)).toHaveLength(3), UI_TIMEOUT);
    expect(listRequests(mock)[2].params).toEqual({});
  });

  it('reloads the list from the refresh button', async () => {
    const { user, mock } = await renderLoadedPage();
    await user.click(screen.getByTitle('Refresh'));
    await waitFor(() => expect(listRequests(mock)).toHaveLength(2), UI_TIMEOUT);
  });

  it('renders the Hebrew interface when the language is Hebrew', async () => {
    await renderPage({ language: 'he', requests: ALL_REQUESTS });

    const heading = screen.getByRole('heading', { level: 1 });
    expect(heading).toHaveTextContent('בקשות מעבר');
    expect(heading.closest('[dir]')).toHaveAttribute('dir', 'rtl');
    expect(await screen.findByText('Ada Lovelace', undefined, UI_TIMEOUT)).toBeInTheDocument();
    expect(screen.getByText('6 בקשות')).toBeInTheDocument();
    expect(screen.getByText('הכל', { selector: 'button' })).toBeInTheDocument();
    expect(screen.getByText('מעבר מדירה', { selector: 'span' })).toBeInTheDocument();
    expect(screen.getByText('הסרה ממעונות', { selector: 'span' })).toBeInTheDocument();
    expect(screen.getByText('בחרי בקשה מהרשימה')).toBeInTheDocument();
    expect(screen.getByPlaceholderText('חיפוש...')).toBeInTheDocument();
  });
});

describe('TransfersPage request details', () => {
  it('shows the route, placement, details and type of a pending transfer', async () => {
    const { user } = await renderLoadedPage({ requests: ALL_REQUESTS });
    await openRequest(user, 'Linus Pauling');

    expect(screen.getByText('Request type:').nextElementSibling).toHaveTextContent('Apt Transfer');
    expect(screen.getByText('Awaiting approval')).toBeInTheDocument();
    expect(screen.getByText('Current Placement')).toBeInTheDocument();
    expect(screen.getByText('105')).toBeInTheDocument();
    expect(screen.getByText('Transfer Type').nextElementSibling).toHaveTextContent('Different apartment, same region');
    expect(screen.getByText('Source Region').nextElementSibling).toHaveTextContent('מעונות קנדה');
    expect(screen.getByText('Closer to the faculty')).toBeInTheDocument();
    expect(screen.getByText('Opened by').nextElementSibling).toHaveTextContent('Dorm Staff');
    expect(button('Delete Request')).toBeEnabled();
  });

  it('shows the final placement and the placement history of an approved request', async () => {
    const { user } = await renderLoadedPage({ requests: ALL_REQUESTS });
    await openRequest(user, 'Alan Turing');

    expect(screen.getByText('Final Placement').nextElementSibling).toHaveTextContent('Building 105 · Apt 3 · Room A · bed 1');
    expect(screen.getByText('Handled by').nextElementSibling).toHaveTextContent('Region Boss');
    expect(screen.queryByText('Actions')).not.toBeInTheDocument();
    expect(queryButton('Delete Request')).toBeNull();

    const toggle = button('Placement history (1)');
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    await user.click(toggle);
    expect(toggle).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByText('Canada')).toBeInTheDocument();
    expect(screen.getByText('Building 105 · Apt 3 · Room B')).toBeInTheDocument();
  });
});

describe('TransfersPage request review', () => {
  it('approves a pending removal and shows it moving from Pending to Approved', async () => {
    const pending = createDeferred<void>();
    const { user, mock } = await renderLoadedPage({
      mockApi: (m) => {
        m.onPut('/api/requests/11/approve/').reply(() => pending.promise.then(() => [200, {}]));
      },
    });
    expect(listRequests(mock)[0].params).toEqual({});

    await openRequest(user, 'Ada Lovelace');
    await user.click(button('Confirm Removal'));

    await waitFor(() => expect(puts(mock, '/api/requests/11/approve/')).toHaveLength(1), UI_TIMEOUT);
    expect(JSON.parse(puts(mock, '/api/requests/11/approve/')[0].data)).toEqual({});
    // While the decision is in flight the action cannot be sent twice.
    expect(button('Confirm Removal')).toBeDisabled();

    mock.onGet('/api/requests/').reply(200, [reviewed(REMOVAL, { status: 'approved' }), SWAP]);
    await act(async () => { pending.resolve(); });

    // The list is reloaded from the backend and the decided request no
    // longer offers any action.
    await waitFor(() => expect(listRequests(mock)).toHaveLength(2), UI_TIMEOUT);
    await waitFor(() => expect(queryButton('Confirm Removal')).toBeNull(), UI_TIMEOUT);
    expect(queryButton('Reject')).toBeNull();
    expect(screen.getByText('Region Boss')).toBeInTheDocument();

    await user.click(statusTab('Pending'));
    expect(listCount()).toHaveTextContent('1 requests');
    expect(screen.queryByText('Ada Lovelace')).not.toBeInTheDocument();
    expect(screen.getByText('Grace Hopper')).toBeInTheDocument();

    await user.click(statusTab('Approved'));
    expect(listCount()).toHaveTextContent('1 requests');
    expect(screen.getByText('Ada Lovelace')).toBeInTheDocument();
  }, WORKFLOW_TIMEOUT_MS);

  it('rejects a pending request with the typed reason and shows that reason afterwards', async () => {
    const { user, mock } = await renderLoadedPage({
      mockApi: (m) => {
        m.onPut('/api/requests/11/reject/').reply(200, {});
      },
    });
    await openRequest(user, 'Ada Lovelace');

    await user.click(button('Reject'));
    await user.click(screen.getByPlaceholderText('Rejection reason (optional)...'));
    await user.paste('Student is staying another semester');

    mock.onGet('/api/requests/').reply(200, [
      reviewed(REMOVAL, { status: 'rejected', rejection_reason: 'Student is staying another semester' }),
      SWAP,
    ]);
    await user.click(button('Reject'));

    await waitFor(() => expect(puts(mock, '/api/requests/11/reject/')).toHaveLength(1), UI_TIMEOUT);
    expect(JSON.parse(puts(mock, '/api/requests/11/reject/')[0].data)).toEqual({ reason: 'Student is staying another semester' });
    expect(puts(mock, '/api/requests/11/approve/')).toHaveLength(0);

    expect(await screen.findByText('Rejection reason:', undefined, UI_TIMEOUT)).toBeInTheDocument();
    expect(screen.getByText('Student is staying another semester')).toBeInTheDocument();
    expect(queryButton('Confirm Removal')).toBeNull();

    await user.click(statusTab('Rejected'));
    expect(listCount()).toHaveTextContent('1 requests');
  }, WORKFLOW_TIMEOUT_MS);

  it('keeps the request pending and reports the error when approval fails', async () => {
    const alert = vi.spyOn(window, 'alert').mockImplementation(() => {});
    const { user, mock } = await renderLoadedPage({
      mockApi: (m) => {
        m.onPut('/api/requests/11/approve/').reply(400, { detail: 'Student has no active assignment' });
      },
    });
    await openRequest(user, 'Ada Lovelace');
    await user.click(button('Confirm Removal'));

    await waitFor(() => expect(alert).toHaveBeenCalledWith('Student has no active assignment'), UI_TIMEOUT);
    expect(listRequests(mock)).toHaveLength(1);
    await waitFor(() => expect(button('Confirm Removal')).toBeEnabled(), UI_TIMEOUT);
    expect(button('Reject')).toBeEnabled();
  }, WORKFLOW_TIMEOUT_MS);

  it('approves a pending student swap without a target bed', async () => {
    const { user, mock } = await renderLoadedPage({
      mockApi: (m) => {
        m.onPut('/api/requests/12/approve/').reply(200, {});
      },
    });
    await openRequest(user, 'Grace Hopper');

    expect(screen.getByText('Linus Pauling (200600700)')).toBeInTheDocument();

    // The swap approval control renders without a text label (its
    // dictionary entry is empty, as it always was), so it is located as the
    // action panel's only control besides Reject. Its label is deliberately
    // not asserted here.
    const actions = screen.getByText('Actions').parentElement!;
    const reject = within(actions).getByText('Reject').closest('button');
    const others = within(actions).getAllByRole('button').filter((control) => control !== reject);
    expect(others).toHaveLength(1);

    mock.onGet('/api/requests/').reply(200, [REMOVAL, reviewed(SWAP, { status: 'approved' })]);
    await user.click(others[0]);

    await waitFor(() => expect(puts(mock, '/api/requests/12/approve/')).toHaveLength(1), UI_TIMEOUT);
    expect(JSON.parse(puts(mock, '/api/requests/12/approve/')[0].data)).toEqual({});
    await waitFor(() => expect(listRequests(mock)).toHaveLength(2), UI_TIMEOUT);
    await waitFor(() => expect(screen.queryByText('Actions')).not.toBeInTheDocument(), UI_TIMEOUT);
  }, WORKFLOW_TIMEOUT_MS);

  it('deletes a request only after confirmation and drops it from the list', async () => {
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false);
    const { user, mock } = await renderLoadedPage({
      mockApi: (m) => {
        m.onDelete('/api/requests/11/').reply(204);
      },
    });
    await openRequest(user, 'Ada Lovelace');

    await user.click(button('Delete Request'));
    expect(confirm).toHaveBeenCalledWith(
      'Delete the request for Ada Lovelace? This will delete only the request and not the student from the system.'
    );
    expect(mock.history.delete).toHaveLength(0);
    expect(screen.getByRole('heading', { name: 'Ada Lovelace' })).toBeInTheDocument();

    confirm.mockReturnValue(true);
    await user.click(button('Delete Request'));
    await waitFor(() => expect(mock.history.delete.filter((r) => r.url === '/api/requests/11/')).toHaveLength(1), UI_TIMEOUT);

    // Removed locally - no reload - and the detail pane is cleared.
    await waitFor(() => expect(screen.queryByText('Ada Lovelace')).not.toBeInTheDocument(), UI_TIMEOUT);
    expect(screen.getByText('Select a request from the list')).toBeInTheDocument();
    expect(listCount()).toHaveTextContent('1 requests');
    expect(listRequests(mock)).toHaveLength(1);
  }, WORKFLOW_TIMEOUT_MS);

  it('reports a failed delete and keeps the request', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    const alert = vi.spyOn(window, 'alert').mockImplementation(() => {});
    const { user } = await renderLoadedPage({
      mockApi: (m) => {
        m.onDelete('/api/requests/11/').reply(403, { detail: 'Only the requester may delete this request' });
      },
    });
    await openRequest(user, 'Ada Lovelace');
    await user.click(button('Delete Request'));

    await waitFor(() => expect(alert).toHaveBeenCalledWith('Only the requester may delete this request'), UI_TIMEOUT);
    expect(screen.getByRole('heading', { name: 'Ada Lovelace' })).toBeInTheDocument();
    await waitFor(() => expect(button('Delete Request')).toBeEnabled(), UI_TIMEOUT);
  }, WORKFLOW_TIMEOUT_MS);

  it('checks the feasibility of a transfer, pages further buildings and approves with the picked bed', async () => {
    const { user, mock } = await renderLoadedPage({
      requests: ALL_REQUESTS,
      mockApi: (m) => {
        m.onGet('/api/requests/13/feasibility/').reply(({ params }) =>
          [200, params?.offset === 0 ? FEASIBLE : FEASIBLE_PAGE_TWO]);
        m.onPut('/api/requests/13/approve/').reply(200, {});
      },
    });
    await openRequest(user, 'Linus Pauling');

    // Before the check only the (label-less) check control and Reject exist.
    const actions = screen.getByText('Actions').parentElement!;
    const reject = within(actions).getByText('Reject').closest('button');
    const [check] = within(actions).getAllByRole('button').filter((c) => c !== reject);
    await user.click(check);

    const feasCalls = () => mock.history.get.filter(({ url }) => url === '/api/requests/13/feasibility/');
    await waitFor(() => expect(feasCalls()).toHaveLength(1), UI_TIMEOUT);
    expect(feasCalls()[0].params).toEqual({ limit: 10, offset: 0 });

    expect(await screen.findByText('pick bed 1 in room A', undefined, UI_TIMEOUT)).toBeInTheDocument();
    // The searched region and the stored scope reach the picker.
    expect(within(actions).getByText('מעונות קנדה', { selector: 'strong' })).toBeInTheDocument();
    expect(screen.getByText('picker scope same_region')).toBeInTheDocument();

    // "Load more" asks for the next building page (offset = buildings
    // loaded) and keeps what is already shown.
    await user.click(screen.getByText('load more buildings'));
    expect(await screen.findByText('pick bed 2 in room A', undefined, UI_TIMEOUT)).toBeInTheDocument();
    expect(screen.getByText('pick bed 1 in room A')).toBeInTheDocument();
    expect(feasCalls()[1].params).toEqual({ limit: 10, offset: 1 });
    expect(screen.queryByText('load more buildings')).not.toBeInTheDocument();

    await user.click(screen.getByText('pick bed 1 in room A'));
    expect(screen.getByText(/Building 110 · Apt 7 · Room A · bed 1 \(Canada\)/)).toBeInTheDocument();
    const approve = button('Assign to bed 1 in room A, apt 7, building 110');
    expect(approve).toBeEnabled();

    mock.onGet('/api/requests/').reply(200, ALL_REQUESTS.map((r) => (r.id === 13 ? reviewed(r, { status: 'approved' }) : r)));
    await user.click(approve);

    await waitFor(() => expect(puts(mock, '/api/requests/13/approve/')).toHaveLength(1), UI_TIMEOUT);
    expect(JSON.parse(puts(mock, '/api/requests/13/approve/')[0].data)).toEqual({ target_room: 610, bed_id: 9001 });
    await waitFor(() => expect(screen.queryByText('Actions')).not.toBeInTheDocument(), UI_TIMEOUT);
  }, WORKFLOW_TIMEOUT_MS);

  it('keeps the loaded results and shows the error when a further feasibility page fails', async () => {
    const { user } = await renderLoadedPage({
      requests: ALL_REQUESTS,
      mockApi: (m) => {
        m.onGet('/api/requests/13/feasibility/').reply(({ params }) =>
          (params?.offset === 0 ? [200, FEASIBLE] : [500, { detail: 'matching service timed out' }]));
      },
    });
    await openRequest(user, 'Linus Pauling');
    const actions = screen.getByText('Actions').parentElement!;
    const reject = within(actions).getByText('Reject').closest('button');
    const [check] = within(actions).getAllByRole('button').filter((c) => c !== reject);
    await user.click(check);

    await user.click(await screen.findByText('load more buildings', undefined, UI_TIMEOUT));
    expect(await screen.findByText('picker error matching service timed out', undefined, UI_TIMEOUT)).toBeInTheDocument();
    expect(screen.getByText('pick bed 1 in room A')).toBeInTheDocument();
  }, WORKFLOW_TIMEOUT_MS);

  it('loads the bed options of an add-student request once and approves with the picked bed', async () => {
    const { user, mock } = await renderLoadedPage({
      requests: ALL_REQUESTS,
      mockApi: (m) => {
        m.onGet('/api/requests/14/feasibility/').reply(200, { ...FEASIBLE, has_more: false });
        m.onPut('/api/requests/14/approve/').reply(200, {});
      },
    });
    await openRequest(user, 'Mary Somerville');

    const bedCalls = () => mock.history.get.filter(({ url }) => url === '/api/requests/14/feasibility/');
    await waitFor(() => expect(bedCalls()).toHaveLength(1), UI_TIMEOUT);
    expect(bedCalls()[0].params).toEqual({ limit: 10, offset: 0 });
    expect(await screen.findByText('pick bed 1 in room A', undefined, UI_TIMEOUT)).toBeInTheDocument();

    // Until a bed is picked the approval is disabled (and label-less).
    const actions = screen.getByText('Actions').parentElement!;
    const reject = within(actions).getByText('Reject').closest('button');
    const [approveBefore] = within(actions).getAllByRole('button')
      .filter((c) => c !== reject && !c.textContent?.startsWith('pick'));
    expect(approveBefore).toBeDisabled();

    await user.click(screen.getByText('pick bed 1 in room A'));
    expect(screen.getByText(/Building 110 · Apt 7 · Room A · bed 1/)).toBeInTheDocument();

    // Re-selecting the request does not fetch the options again.
    await openRequest(user, 'Ada Lovelace');
    await openRequest(user, 'Mary Somerville');
    expect(bedCalls()).toHaveLength(1);
    expect(screen.getByText(/Building 110 · Apt 7 · Room A · bed 1/)).toBeInTheDocument();

    mock.onGet('/api/requests/').reply(200, ALL_REQUESTS.map((r) => (r.id === 14 ? reviewed(r, { status: 'approved' }) : r)));
    await user.click(button('Assign to bed 1 in room A, apt 7, building 110'));
    await waitFor(() => expect(puts(mock, '/api/requests/14/approve/')).toHaveLength(1), UI_TIMEOUT);
    expect(JSON.parse(puts(mock, '/api/requests/14/approve/')[0].data)).toEqual({ target_room: 610, bed_id: 9001 });
  }, WORKFLOW_TIMEOUT_MS);

  it('shows the destination-review note to a regional boss of another region and the actions to a central admin', async () => {
    const { user, unmount } = await renderLoadedPage({ requests: ALL_REQUESTS });
    await openRequest(user, 'Emmy Noether');
    expect(screen.getByText('The transfer request is awaiting review and approval by the destination region')).toBeInTheDocument();
    expect(queryButton('Reject')).toBeNull();
    unmount();

    const admin = await renderLoadedPage({ user: centralAdmin, requests: ALL_REQUESTS });
    await openRequest(admin.user, 'Emmy Noether');
    expect(screen.queryByText('The transfer request is awaiting review and approval by the destination region')).not.toBeInTheDocument();
    expect(button('Reject')).toBeEnabled();
  }, WORKFLOW_TIMEOUT_MS);
});

describe('TransfersPage new request', () => {
  async function openModal(user: ReturnType<typeof userEvent.setup>) {
    await user.click(button('New Request'));
    await screen.findByRole('heading', { name: 'Choose Request Type' });
  }

  const createdRequests = (mock: MockAdapter) => posts(mock, '/api/requests/').map((r) => JSON.parse(r.data));

  it('offers the five request types and returns to the picker', async () => {
    const { user } = await renderLoadedPage();
    await openModal(user);

    for (const title of ['Add Student', 'Remove from Dorms', 'Transfer Request', 'Student Swap', 'Other Request']) {
      expect(typeCard(title)).toBeInTheDocument();
    }

    await user.click(typeCard('Add Student'));
    expect(screen.getByRole('heading', { name: 'New Request' })).toBeInTheDocument();
    expect(screen.getByText('New Student Details')).toBeInTheDocument();

    await user.click(wizardButton('Request Types'));
    expect(screen.getByRole('heading', { name: 'Choose Request Type' })).toBeInTheDocument();

    await user.click(within(dialog()).getByLabelText('Cancel'));
    expect(screen.queryByRole('heading', { name: 'Choose Request Type' })).not.toBeInTheDocument();
  });

  it('files an add-student request with the student data from the wizard', async () => {
    const { user, mock } = await renderLoadedPage({
      mockApi: (m) => { m.onPost('/api/requests/').reply(201, { id: 99 }); },
    });
    await openModal(user);
    await user.click(typeCard('Add Student'));

    const next = () => wizardButton('Next');
    expect(next()).toBeDisabled();
    await user.type(screen.getByPlaceholderText('ID Number'), '300100200');
    await user.type(screen.getByPlaceholderText('First Name'), 'Mary');
    await user.type(screen.getByPlaceholderText('Last Name'), 'Somerville');
    await user.type(screen.getByPlaceholderText('Phone'), '050-9998887');
    expect(screen.getByText('1/4')).toBeInTheDocument();
    await user.click(next());

    expect(screen.getByText('Housing Preferences', { selector: 'h3' })).toBeInTheDocument();
    expect(next()).toBeDisabled();
    const [gender, religion, dormType] = within(dialog()).getAllByRole('combobox');
    await user.selectOptions(gender, 'female');
    await user.selectOptions(religion, 'Jewish');
    await user.selectOptions(dormType, 'single');
    await user.click(next());

    expect(next()).toBeDisabled();
    await user.type(screen.getByPlaceholderText('Explain why the student needs a place in the dorms...'), 'Arrives next week');
    await user.click(next());

    expect(screen.getByText('Summary Before Submitting')).toBeInTheDocument();
    expect(screen.getByText('Mary Somerville')).toBeInTheDocument();
    expect(screen.getByText('Woman')).toBeInTheDocument();
    await user.click(wizardButton('Submit'));

    await waitFor(() => expect(createdRequests(mock)).toHaveLength(1), UI_TIMEOUT);
    expect(createdRequests(mock)[0]).toEqual({
      request_type: 'add_student',
      reason: 'Arrives next week',
      student_data: {
        student_id: '300100200', first_name: 'Mary', last_name: 'Somerville',
        phone: '050-9998887', email: '', city: '', gender: 'female', religion: 'Jewish', dorm_type: 'single',
      },
    });
    // The modal closes and the list is re-read.
    await waitFor(() => expect(screen.queryByRole('heading', { name: 'New Request' })).not.toBeInTheDocument(), UI_TIMEOUT);
    await waitFor(() => expect(listRequests(mock)).toHaveLength(2), UI_TIMEOUT);
  }, WORKFLOW_TIMEOUT_MS);

  it('files a removal request for the picked assigned student', async () => {
    const { user, mock } = await renderLoadedPage({
      mockApi: (m) => { m.onPost('/api/requests/').reply(201, { id: 99 }); },
    });
    await openModal(user);
    await user.click(typeCard('Remove from Dorms'));

    // Only assigned students are offered.
    expect(screen.getByPlaceholderText('Search assigned student...')).toBeInTheDocument();
    expect(screen.queryByText('pick Rosalind Franklin')).not.toBeInTheDocument();
    expect(wizardButton('Next')).toBeDisabled();
    await user.click(screen.getByText('pick Ada Lovelace'));
    expect(within(dialog()).getByText('Ada Lovelace')).toBeInTheDocument();
    await user.click(wizardButton('Next'));

    expect(screen.getByText('Current Placement', { selector: 'h3' })).toBeInTheDocument();
    expect(screen.getByText('Once confirmed, the bed will be freed and the student will be marked inactive.')).toBeInTheDocument();
    await user.click(wizardButton('Next'));

    await user.type(screen.getByPlaceholderText('Explain why the student is being removed...'), 'Graduated');
    await user.click(wizardButton('Next'));
    expect(screen.getByText('Building 105 · Apt 3 · Room B')).toBeInTheDocument();
    await user.click(wizardButton('Confirm'));

    await waitFor(() => expect(createdRequests(mock)).toHaveLength(1), UI_TIMEOUT);
    expect(createdRequests(mock)[0]).toEqual({ student: 2, reason: 'Graduated', request_type: 'remove_student' });
  }, WORKFLOW_TIMEOUT_MS);

  it('files a swap request between two different assigned students', async () => {
    const { user, mock } = await renderLoadedPage({
      mockApi: (m) => { m.onPost('/api/requests/').reply(201, { id: 99 }); },
    });
    await openModal(user);
    await user.click(typeCard('Student Swap'));

    await user.click(screen.getByText('pick Ada Lovelace'));
    await user.click(wizardButton('Next'));

    // The first student is excluded from the second pick.
    expect(screen.queryByText('pick Ada Lovelace')).not.toBeInTheDocument();
    await user.click(screen.getByText('pick Grace Hopper'));
    await user.click(wizardButton('Next'));

    await user.type(screen.getByPlaceholderText('Explain why the swap is requested...'), 'Both agreed');
    await user.click(wizardButton('Next'));
    expect(screen.getByText(/Ada Lovelace · Building 105 · Apt 3 · Room B/)).toBeInTheDocument();
    expect(screen.getByText(/Grace Hopper · Building 110 · Apt 7 · Room A/)).toBeInTheDocument();
    await user.click(wizardButton('Submit Swap Request'));

    await waitFor(() => expect(createdRequests(mock)).toHaveLength(1), UI_TIMEOUT);
    expect(createdRequests(mock)[0]).toEqual({ student: 2, swap_with_student: 3, reason: 'Both agreed', request_type: 'swap' });
  }, WORKFLOW_TIMEOUT_MS);

  it('files a same-region transfer for a regional boss, who cannot pick another region', async () => {
    const { user, mock } = await renderLoadedPage({
      mockApi: (m) => {
        m.onPost('/api/requests/match-options/').reply(200, { ...FEASIBLE, has_more: false });
        m.onPost('/api/requests/').reply(201, { id: 99 });
      },
    });
    await openModal(user);
    await user.click(typeCard('Transfer Request'));

    await user.click(screen.getByText('pick Ada Lovelace'));
    // The slim search row has no region, so the full record is read for the label.
    await waitFor(() => expect(mock.history.get.filter(({ url }) => url === '/api/students/2/')).toHaveLength(1), UI_TIMEOUT);
    expect(await within(dialog()).findByText('מעונות קנדה', { selector: 'strong' }, UI_TIMEOUT)).toBeInTheDocument();
    await user.click(wizardButton('Next'));

    const crossRegion = wizardButton('To a different region');
    expect(crossRegion).toBeDisabled();
    expect(crossRegion).toHaveAttribute('title', 'Only a central admin can create a cross-region transfer');
    expect(screen.getByText(/A regional user may only make transfers within their authorized region/)).toBeInTheDocument();
    expect(wizardButton('Next')).toBeDisabled();
    await user.click(wizardButton('Different apartment, same region'));
    expect(screen.getByText('Target region:')).toBeInTheDocument();
    expect(screen.getByText("Chosen automatically - the student's current region")).toBeInTheDocument();
    await user.click(wizardButton('Next'));

    await user.type(screen.getByPlaceholderText('Explain the reason for the request...'), 'Closer to the lab');
    await user.click(wizardButton('Next'));

    expect(screen.getByText('Assignment Options')).toBeInTheDocument();
    await user.click(wizardButton('Check assignment options'));
    await waitFor(() => expect(posts(mock, '/api/requests/match-options/')).toHaveLength(1), UI_TIMEOUT);
    expect(JSON.parse(posts(mock, '/api/requests/match-options/')[0].data)).toEqual({
      student_id: 2, request_type: 'apartment', same_apartment: false, transfer_scope: 'same_region', limit: 10, offset: 0,
    });
    expect(await screen.findByText('picker scope same_region', undefined, UI_TIMEOUT)).toBeInTheDocument();
    expect(wizardButton('Next')).toBeDisabled();
    await user.click(screen.getByText('pick bed 1 in room A'));
    await user.click(wizardButton('Next'));

    expect(summaryValue('Transfer Type')).toHaveTextContent('Different apartment, same region');
    expect(summaryValue('Selected Target')).toHaveTextContent('Canada · Building 110 · Apt 7 · Room A · bed 1');
    await user.click(wizardButton('Submit'));

    await waitFor(() => expect(createdRequests(mock)).toHaveLength(1), UI_TIMEOUT);
    expect(createdRequests(mock)[0]).toEqual({
      student: 2, request_type: 'apartment', reason: 'Closer to the lab', other_description: '',
      same_apartment: false, target_room: 610, transfer_scope: 'same_region', destination_regions: [],
    });
  }, WORKFLOW_TIMEOUT_MS);

  it('files a cross-region transfer for a central admin with the chosen destination region', async () => {
    const { user, mock } = await renderLoadedPage({
      user: centralAdmin,
      mockApi: (m) => {
        m.onPost('/api/requests/match-options/').reply(200, {
          ...FEASIBLE, has_more: false, search_regions: [{ id: 'broshim', name: 'ברושים' }],
        });
        m.onPost('/api/requests/').reply(201, { id: 99 });
      },
    });
    await openModal(user);
    await user.click(typeCard('Transfer Request'));
    await user.click(screen.getByText('pick Grace Hopper'));
    await user.click(wizardButton('Next'));

    const crossRegion = wizardButton('To a different region');
    expect(crossRegion).toBeEnabled();
    await user.click(crossRegion);
    expect(wizardButton('Next')).toBeDisabled();

    // The destination list is searchable; the search narrows it.
    expect(within(dialog()).getByLabelText(/מעונות קנדה/)).toBeInTheDocument();
    await user.type(screen.getByPlaceholderText('Search region...'), 'ברו');
    expect(within(dialog()).queryByLabelText(/מעונות קנדה/)).not.toBeInTheDocument();
    await user.click(within(dialog()).getByLabelText('ברושים'));
    expect(screen.getByText('Selected:').querySelector('strong')).toHaveTextContent('ברושים');
    await user.click(wizardButton('Next'));

    await user.type(screen.getByPlaceholderText('Explain the reason for the request...'), 'Moving faculties');
    await user.click(wizardButton('Next'));

    await user.click(wizardButton('Check assignment options'));
    await waitFor(() => expect(posts(mock, '/api/requests/match-options/')).toHaveLength(1), UI_TIMEOUT);
    expect(JSON.parse(posts(mock, '/api/requests/match-options/')[0].data)).toEqual({
      student_id: 3, request_type: 'apartment', same_apartment: null, transfer_scope: 'cross_region',
      region_ids: ['broshim'], limit: 10, offset: 0,
    });
    expect(await screen.findByText('picker scope cross_region', undefined, UI_TIMEOUT)).toBeInTheDocument();
    await user.click(screen.getByText('pick bed 1 in room A'));
    await user.click(wizardButton('Next'));

    expect(summaryValue('Transfer Type')).toHaveTextContent('To a different region');
    expect(summaryValue('Target Region')).toHaveTextContent('ברושים');
    await user.click(wizardButton('Submit'));

    await waitFor(() => expect(createdRequests(mock)).toHaveLength(1), UI_TIMEOUT);
    expect(createdRequests(mock)[0]).toEqual({
      student: 3, request_type: 'apartment', reason: 'Moving faculties', other_description: '',
      same_apartment: null, target_room: 610, transfer_scope: 'cross_region', destination_regions: ['broshim'],
    });
  }, WORKFLOW_TIMEOUT_MS);

  it('discards fetched options when the transfer scope changes, and pages the preview by building', async () => {
    const { user, mock } = await renderLoadedPage({
      mockApi: (m) => {
        m.onPost('/api/requests/match-options/').reply(({ data }) =>
          [200, JSON.parse(data).offset === 0 ? FEASIBLE : FEASIBLE_PAGE_TWO]);
      },
    });
    await openModal(user);
    await user.click(typeCard('Transfer Request'));
    await user.click(screen.getByText('pick Ada Lovelace'));
    await user.click(wizardButton('Next'));
    await user.click(wizardButton('Within the same apartment'));
    await user.click(wizardButton('Next'));
    await user.type(screen.getByPlaceholderText('Explain the reason for the request...'), 'Noise');
    await user.click(wizardButton('Next'));

    await user.click(wizardButton('Check assignment options'));
    expect(await screen.findByText('pick bed 1 in room A', undefined, UI_TIMEOUT)).toBeInTheDocument();
    expect(JSON.parse(posts(mock, '/api/requests/match-options/')[0].data)).toMatchObject({
      request_type: 'room', same_apartment: true, transfer_scope: 'same_region',
    });
    expect(screen.getByText('Only free beds in the current apartment are shown')).toBeInTheDocument();

    // The preview's "load more" repeats the same search at the next offset
    // and appends the result.
    await user.click(screen.getByText('load more buildings'));
    expect(await screen.findByText('pick bed 2 in room A', undefined, UI_TIMEOUT)).toBeInTheDocument();
    expect(screen.getByText('pick bed 1 in room A')).toBeInTheDocument();
    expect(JSON.parse(posts(mock, '/api/requests/match-options/')[1].data)).toMatchObject({
      request_type: 'room', same_apartment: true, transfer_scope: 'same_region', offset: 1,
    });

    // Changing the scope invalidates what was fetched.
    await user.click(wizardButton('Back'));
    await user.click(wizardButton('Back'));
    await user.click(wizardButton('Different apartment, same region'));
    await user.click(wizardButton('Next'));
    await user.click(wizardButton('Next'));
    expect(screen.queryByText('pick bed 1 in room A')).not.toBeInTheDocument();
    expect(wizardButton('Check assignment options')).toBeInTheDocument();
  }, WORKFLOW_TIMEOUT_MS);

  it('files an "other" request with its description in three steps', async () => {
    const { user, mock } = await renderLoadedPage({
      mockApi: (m) => { m.onPost('/api/requests/').reply(201, { id: 99 }); },
    });
    await openModal(user);
    await user.click(typeCard('Other Request'));
    expect(screen.getByText('1/3')).toBeInTheDocument();

    await user.click(screen.getByText('pick Ada Lovelace'));
    await user.click(wizardButton('Next'));
    await user.type(screen.getByPlaceholderText('Describe the request...'), 'Stay extension');
    await user.type(screen.getByPlaceholderText('Explain the reason for the request...'), 'Summer course');
    await user.click(wizardButton('Next'));
    expect(summaryValue('Description')).toHaveTextContent('Stay extension');
    await user.click(wizardButton('Submit'));

    await waitFor(() => expect(createdRequests(mock)).toHaveLength(1), UI_TIMEOUT);
    expect(createdRequests(mock)[0]).toEqual({
      student: 2, request_type: 'other', reason: 'Summer course', other_description: 'Stay extension', same_apartment: null,
    });
  }, WORKFLOW_TIMEOUT_MS);

  it('shows the backend error inside the wizard and keeps the modal open', async () => {
    const { user, mock } = await renderLoadedPage({
      mockApi: (m) => { m.onPost('/api/requests/').reply(400, { detail: 'Student already has a pending request' }); },
    });
    await openModal(user);
    await user.click(typeCard('Remove from Dorms'));
    await user.click(screen.getByText('pick Ada Lovelace'));
    await user.click(wizardButton('Next'));
    await user.click(wizardButton('Next'));
    await user.type(screen.getByPlaceholderText('Explain why the student is being removed...'), 'Graduated');
    await user.click(wizardButton('Next'));
    await user.click(wizardButton('Confirm'));

    expect(await screen.findByText('Student already has a pending request', undefined, UI_TIMEOUT)).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'New Request' })).toBeInTheDocument();
    expect(listRequests(mock)).toHaveLength(1);
    await waitFor(() => expect(wizardButton('Confirm')).toBeEnabled(), UI_TIMEOUT);
  }, WORKFLOW_TIMEOUT_MS);

  it('renders the wizard chrome in Hebrew', async () => {
    const user = userEvent.setup();
    await renderPage({ language: 'he' });
    await screen.findByText('Ada Lovelace', undefined, UI_TIMEOUT);
    await user.click(button('בקשה חדשה'));
    expect(await screen.findByRole('heading', { name: 'בחר סוג בקשה' })).toBeInTheDocument();
    await user.click(typeCard('הוספת סטודנט'));
    expect(screen.getByText('פרטי הסטודנט החדש')).toBeInTheDocument();
    // The close control and the footer's cancel share the label.
    expect(within(dialog()).getAllByRole('button', { name: 'ביטול' })).toHaveLength(2);
    expect(wizardButton('המשך')).toBeDisabled();
  });
});
