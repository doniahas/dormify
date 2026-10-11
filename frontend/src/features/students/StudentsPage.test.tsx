import React from 'react';
import { describe, expect, it, vi } from 'vitest';
import { act, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type MockAdapter from 'axios-mock-adapter';

import { createDeferred } from '../../shared/test/deferred';
import { renderWithProviders, type TestUser } from '../../shared/test/render';
import StudentsPage from './StudentsPage';

// The page talks to the backend only through its typed adapters, which sit
// on the shared axios client; every reply below is registered on that
// client's mock adapter, so the request URLs and parameters asserted here
// are the ones the backend would receive.

// The drawer is replaced by the narrowest stand-in that still exercises the
// contract this page owns: it receives the current filters and hands back a
// new set. What the real drawer renders internally is NOT covered here.
vi.mock('./FiltersDrawer', () => ({
  default: ({ filters, onFiltersChange }: {
    filters: Record<string, string[]>;
    onFiltersChange: (next: Record<string, string[]>) => void;
  }) => (
    <button
      type="button"
      onClick={() => onFiltersChange({ ...filters, genders: ['male'], regions: ['canada'] })}
    >
      apply gender filter
    </button>
  ),
}));

const centralAdmin: TestUser = {
  id: 9,
  email: 'staff@example.edu',
  role: 'central_admin',
  region: 'canada',
  region_name: 'מעונות קנדה',
};

const regionalEmployee: TestUser = {
  id: 10,
  email: 'employee@example.edu',
  role: 'employee',
  region: 'canada',
  region_name: 'מעונות קנדה',
};

const COUNTS = { all: 57, new: 4, continuing: 30, transfer: 3, leaving: 2, unassigned: 12 };

const ADA = {
  id: 1,
  student_id: '200100300',
  first_name: 'Ada',
  last_name: 'Lovelace',
  phone: '050-1112222',
  category: 'new',
  is_assigned: true,
};

const GRACE = {
  id: 2,
  student_id: '200400500',
  first_name: 'Grace',
  last_name: 'Hopper',
  category: 'continuing',
  is_assigned: false,
};

const LINUS = {
  id: 3,
  student_id: '200600700',
  first_name: 'Linus',
  last_name: 'Pauling',
  category: 'new',
  is_assigned: true,
};

const ADA_DETAIL = {
  ...ADA,
  email: 'ada@example.com',
  city: 'Haifa',
  gender: 'female',
  region_id: 'canada',
  region_name: 'מעונות קנדה',
  housing_type: 'יחיד',
  accepted_dorm_type: 2,
  accepted_dorm_type_name: 'קנדה',
  assigned_building_number: 105,
  assigned_apartment_number: '3',
  assigned_room_name: 'B',
  current_bed_label: 'bed 2',
  roommate_request_1: 'Mary Somerville',
  is_priority: true,
  priority_reason: 'Accessibility',
};

const GRACE_DETAIL = {
  ...GRACE,
  email: '',
  city: '',
  gender: 'female',
  region_id: 'canada',
  housing_type: '',
};

const ADA_REQUESTS = [
  { id: 71, request_type: 'room', request_type_display: 'שינוי חדר', status: 'pending', status_display: 'ממתינה', created_at: '2026-10-01T10:00:00Z' },
];

// A first page that is deliberately shorter than the server-side total, so
// the count the page reports can never be satisfied by counting rows.
const PAGE_ONE = {
  count: 57,
  next: 'http://backend.test/api/students/?page=2',
  previous: null,
  results: [ADA, GRACE],
};

const PAGE_TWO = { count: 57, next: null, previous: null, results: [LINUS] };

const EMPTY_PAGE = { count: 0, next: null, previous: null, results: [] };

const FILTER_OPTIONS = {
  is_central_admin: true,
  regions: [{ id: 'canada', name: 'מעונות קנדה' }],
  buildings: [{ id: 5, name: '105' }],
  dorm_types: [{ id: 2, name: 'קנדה', region_id: 'canada', region_name: 'מעונות קנדה' }],
  apartments: [],
  rooms: [],
  religions: [{ id: 'Jewish', name: 'יהודי' }],
  housing_types: [{ id: 'יחיד', name: 'יחיד' }],
};

const REGIONS = [
  { id: 'canada', name: 'מעונות קנדה' },
  { id: 'broshim', name: 'ברושים' },
];

function mockStudentsApi(mock: MockAdapter, { page = PAGE_ONE }: { page?: unknown } = {}) {
  mock.onGet('/api/students/counts/').reply(200, COUNTS);
  mock.onGet('/api/students/filter-options/').reply(200, FILTER_OPTIONS);
  mock.onGet('/api/regions/').reply(200, REGIONS);
  mock.onGet('/api/students/').reply(200, page);
  mock.onGet('http://backend.test/api/students/?page=2').reply(200, PAGE_TWO);
  mock.onGet('/api/students/1/').reply(200, ADA_DETAIL);
  mock.onGet('/api/students/2/').reply(200, GRACE_DETAIL);
  mock.onGet('/api/requests/').reply(({ params }) => [200, params?.student === 1 ? ADA_REQUESTS : []]);
}

const tab = (label: string) => screen.getByRole('button', { name: new RegExp(`^${label}\\b`) });

const loadMoreButton = () =>
  screen.queryByText('Load more students')?.closest('button') ?? null;

// The skeleton list publishes its pending state as aria-busy.
const busyList = () => document.querySelector('[aria-busy="true"]');

const searchBox = () =>
  screen.getByPlaceholderText('Search by name, ID, or phone...');

// The list request is issued behind the page's own 300 ms debounce, so every
// assertion about it waits for the request itself rather than for a duration.
const listRequests = (mock: MockAdapter) =>
  mock.history.get.filter(({ url }) => url === '/api/students/');

const listParams = (mock: MockAdapter, index: number) => listRequests(mock)[index].params ?? {};

const waitForListCalls = (mock: MockAdapter, n: number) =>
  waitFor(() => expect(listRequests(mock)).toHaveLength(n), { timeout: 3000 });

interface RenderOptions {
  route?: string;
  language?: 'he' | 'en';
  user?: TestUser;
  mockApi?: (mock: MockAdapter) => void;
}

function renderStudentsPage({
  route = '/students', language = 'en', user = centralAdmin, mockApi = mockStudentsApi,
}: RenderOptions = {}) {
  return renderWithProviders(<StudentsPage />, { route, language, user, mockApi });
}

// Renders and waits for the first list response to be rendered.
async function renderLoadedPage(options?: RenderOptions) {
  const utils = await renderStudentsPage(options);
  await screen.findByText('Ada Lovelace', undefined, { timeout: 3000 });
  return utils;
}

describe('StudentsPage list loading', () => {
  it('shows a busy list before the first request, then the genuine empty result', async () => {
    const pending = createDeferred<unknown>();
    const { mock } = await renderStudentsPage({
      mockApi: (m) => {
        mockStudentsApi(m);
        m.onGet('/api/students/').reply(() => pending.promise.then((page) => [200, page]));
      },
    });

    expect(searchBox()).toBeInTheDocument();
    expect(listRequests(mock)).toHaveLength(0);
    expect(screen.queryByText('No students found')).not.toBeInTheDocument();
    expect(busyList()).not.toBeNull();

    await waitForListCalls(mock, 1);
    await act(async () => { pending.resolve(EMPTY_PAGE); });
    expect(await screen.findByText('No students found')).toBeInTheDocument();
    expect(busyList()).toBeNull();
  });

  it('renders the returned students and reports the server total, not the row count', async () => {
    const { mock } = await renderLoadedPage();

    expect(screen.getByText('Ada Lovelace')).toBeInTheDocument();
    expect(screen.getByText('200100300')).toBeInTheDocument();
    expect(screen.getByText('Grace Hopper')).toBeInTheDocument();
    expect(screen.getByText('200400500')).toBeInTheDocument();

    // Two rows are loaded but the backend reported 57 matches; the page must
    // show the server-side count rather than the length of what it holds.
    expect(screen.getByText('57 results')).toBeInTheDocument();

    // The stat cards show the per-tab totals from the counts endpoint.
    expect(tab('All Students')).toHaveTextContent('57');
    expect(tab('Unassigned')).toHaveTextContent('12');

    // The first request carries no tab, search or filter parameter.
    expect(listParams(mock, 0)).toEqual({});
  });

  it('shows the empty state after a successful empty response', async () => {
    const { mock } = await renderStudentsPage({
      mockApi: (m) => mockStudentsApi(m, { page: EMPTY_PAGE }),
    });

    await waitForListCalls(mock, 1);
    expect(await screen.findByText('No students found')).toBeInTheDocument();
    expect(
      screen.getByText('Try a different search term or select another status')
    ).toBeInTheDocument();
    expect(screen.queryByText('Ada Lovelace')).not.toBeInTheDocument();
    expect(busyList()).toBeNull();
    expect(screen.getByText('0 results')).toBeInTheDocument();
  });

  it('surfaces a failed list request without falling back to the empty state', async () => {
    await renderStudentsPage({
      mockApi: (m) => {
        mockStudentsApi(m);
        m.onGet('/api/students/').reply(500, { detail: 'database unavailable' });
      },
    });

    expect(
      await screen.findByText('database unavailable', undefined, { timeout: 3000 })
    ).toBeInTheDocument();

    // An error is not "no results": the empty card and its clear-filters
    // prompt stay away, and the page stays usable rather than unmounting.
    expect(screen.queryByText('No students found')).not.toBeInTheDocument();
    expect(screen.getByText('Search or filter students by status')).toBeInTheDocument();
    expect(searchBox()).toBeInTheDocument();
    expect(tab('All Students')).toBeInTheDocument();
  });

  it('renders the Hebrew interface when the language is Hebrew', async () => {
    await renderStudentsPage({ language: 'he' });

    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('סטודנטים');
    expect(screen.getByText('חיפוש או סינון סטודנטים לפי סטטוס')).toBeInTheDocument();
    expect(screen.getByPlaceholderText('חפש לפי שם, ת.ז או טלפון...')).toBeInTheDocument();
    // The tab cards keep their English primary label and add the Hebrew one.
    expect(tab('All Students')).toHaveTextContent('כל הסטודנטים');
    expect(await screen.findByText('Ada Lovelace', undefined, { timeout: 3000 })).toBeInTheDocument();
    expect(screen.getByText('57 תוצאות')).toBeInTheDocument();
    expect(screen.getByText('טען עוד סטודנטים')).toBeInTheDocument();
  });
});

describe('StudentsPage pagination', () => {
  it('appends the next page and keeps the rows already loaded', async () => {
    const user = userEvent.setup();
    const { mock } = await renderLoadedPage();

    await user.click(loadMoreButton()!);

    expect(await screen.findByText('Linus Pauling')).toBeInTheDocument();
    expect(mock.history.get.filter(({ url }) => url === 'http://backend.test/api/students/?page=2')).toHaveLength(1);

    // The first page is still on screen - the next page was appended, not
    // swapped in - and the reported total is unchanged.
    expect(screen.getByText('Ada Lovelace')).toBeInTheDocument();
    expect(screen.getByText('Grace Hopper')).toBeInTheDocument();
    expect(screen.getByText('57 results')).toBeInTheDocument();

    // The exhausted page carries no further link, so the control retires.
    expect(loadMoreButton()).toBeNull();

    // Appending must not re-issue the list request.
    expect(listRequests(mock)).toHaveLength(1);
  });

  it('restarts from the first page when the status tab changes', async () => {
    const user = userEvent.setup();
    const { mock } = await renderLoadedPage();

    await user.click(loadMoreButton()!);
    expect(await screen.findByText('Linus Pauling')).toBeInTheDocument();

    mock.onGet('/api/students/').reply(200, { count: 4, next: null, previous: null, results: [GRACE] });

    await user.click(tab('New'));
    await waitForListCalls(mock, 2);

    // The appended second page is discarded rather than carried over.
    await waitFor(() =>
      expect(screen.queryByText('Linus Pauling')).not.toBeInTheDocument()
    );
    expect(screen.queryByText('Ada Lovelace')).not.toBeInTheDocument();
    expect(screen.getByText('Grace Hopper')).toBeInTheDocument();
    expect(screen.getByText('4 results')).toBeInTheDocument();

    // No page-2 link on the fresh result, so no further append is offered.
    expect(loadMoreButton()).toBeNull();
  });
});

describe('StudentsPage query parameters', () => {
  it('opens on the tab named in the URL and asks for that status', async () => {
    const { mock } = await renderLoadedPage({ route: '/students?tab=unassigned' });

    // Unassigned is the one tab that maps onto status rather than category.
    expect(listParams(mock, 0)).toEqual({ status: 'unassigned' });
    expect(tab('Unassigned')).toHaveAttribute('aria-pressed', 'true');
    expect(tab('All Students')).toHaveAttribute('aria-pressed', 'false');
  });

  it('asks for a category when a category tab is selected', async () => {
    const user = userEvent.setup();
    const { mock } = await renderLoadedPage();

    expect(listParams(mock, 0)).toEqual({});

    await user.click(tab('New'));
    await waitForListCalls(mock, 2);

    expect(listParams(mock, 1)).toEqual({ category: 'new' });
    expect(tab('New')).toHaveAttribute('aria-pressed', 'true');
  });

  it('sends a search term only once it is long enough, and only once per pause', async () => {
    const user = userEvent.setup({ delay: null });
    const { mock } = await renderLoadedPage();

    // A single character is below the page's threshold, so the request is
    // repeated without any search term rather than being skipped.
    await user.type(searchBox(), 'a');
    await waitForListCalls(mock, 2);
    expect(listParams(mock, 1)).toEqual({});

    await user.type(searchBox(), 'da');
    await waitForListCalls(mock, 3);

    expect(listParams(mock, 2)).toEqual({ search: 'ada' });

    // Three keystrokes produced two additional requests rather than three:
    // the characters typed together were coalesced by the debounce.
    expect(listRequests(mock)).toHaveLength(3);
    expect(searchBox()).toHaveValue('ada');
  });

  it('maps chosen filters onto the query parameters the backend expects and shows them as chips', async () => {
    const user = userEvent.setup();
    const { mock } = await renderLoadedPage();

    await user.click(screen.getByText('apply gender filter'));
    await waitForListCalls(mock, 2);

    // The page translates its own filter state into the backend's parameter
    // names; the raw drawer keys are never sent.
    expect(listParams(mock, 1)).toEqual({ gender: 'male', region: 'canada' });

    // Each selection is shown as a chip, localized where a name is known.
    expect(screen.getByText('Man')).toBeInTheDocument();
    expect(screen.getByText('Canada Dormitories')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Filters/ })).toHaveTextContent('2');

    await user.click(screen.getByText('Clear all'));
    await waitForListCalls(mock, 3);
    expect(listParams(mock, 2)).toEqual({});
    expect(screen.queryByText('Man')).not.toBeInTheDocument();
  });
});

describe('StudentsPage stale responses', () => {
  it('abandons the in-flight request when a newer one starts and keeps the newer result', async () => {
    const user = userEvent.setup({ delay: null });
    const first = createDeferred<unknown>();
    let replies = 0;

    const { mock } = await renderStudentsPage({
      mockApi: (m) => {
        mockStudentsApi(m);
        m.onGet('/api/students/').reply(() => {
          replies += 1;
          if (replies === 1) return first.promise.then((page) => [200, page]);
          return [200, { count: 1, next: null, previous: null, results: [LINUS] }];
        });
      },
    });

    await waitForListCalls(mock, 1);
    const firstSignal = listRequests(mock)[0].signal as AbortSignal;
    expect(firstSignal.aborted).toBe(false);

    await user.type(searchBox(), 'linus');
    await waitForListCalls(mock, 2);

    // The first request was abandoned as soon as the newer one began.
    expect(firstSignal.aborted).toBe(true);

    expect(
      await screen.findByText('Linus Pauling', undefined, { timeout: 3000 })
    ).toBeInTheDocument();

    // A late reply to the abandoned request must not replace the newer list.
    await act(async () => { first.resolve(PAGE_ONE); });
    expect(screen.getByText('Linus Pauling')).toBeInTheDocument();
    expect(screen.queryByText('Ada Lovelace')).not.toBeInTheDocument();
    expect(screen.queryByText('No students found')).not.toBeInTheDocument();
    expect(screen.getByText('1 result')).toBeInTheDocument();
  });
});

describe('StudentsPage detail view', () => {
  it('opens a student, loads the full record and the requests filed for it, and returns to the list', async () => {
    const user = userEvent.setup();
    const { mock } = await renderLoadedPage();

    await user.click(screen.getByText('Ada Lovelace'));

    expect(await screen.findByText('Current Assignment')).toBeInTheDocument();
    expect(mock.history.get.filter(({ url }) => url === '/api/students/1/')).toHaveLength(1);
    const requestCalls = mock.history.get.filter(({ url }) => url === '/api/requests/');
    expect(requestCalls).toHaveLength(1);
    expect(requestCalls[0].params).toEqual({ student: 1 });

    // Contact, housing and personal details from the full record.
    expect(screen.getByText('ada@example.com')).toBeInTheDocument();
    expect(screen.getByText('Haifa')).toBeInTheDocument();
    expect(screen.getAllByText('bed 2').length).toBeGreaterThan(0);
    expect(screen.getByText('Woman')).toBeInTheDocument();
    expect(screen.getByText('Mary Somerville')).toBeInTheDocument();
    expect(screen.getByText('Accessibility')).toBeInTheDocument();
    expect(await screen.findByText(/שינוי חדר — ממתינה/)).toBeInTheDocument();

    // The list chrome is hidden while the detail view is open.
    expect(screen.queryByPlaceholderText('Search by name, ID, or phone...')).not.toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /Back to list/ }));
    expect(screen.getByText('Grace Hopper')).toBeInTheDocument();
    expect(searchBox()).toBeInTheDocument();
    // Returning does not re-issue the list request.
    expect(listRequests(mock)).toHaveLength(1);
  });

  it('offers a bed assignment to an unassigned student and a request to an assigned one', async () => {
    const user = userEvent.setup();
    await renderLoadedPage();

    await user.click(screen.getByText('Grace Hopper'));
    expect(await screen.findByRole('button', { name: /Assign Bed/ })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Add Request/ })).not.toBeInTheDocument();
    expect(screen.getByText('Student is not currently assigned to a room')).toBeInTheDocument();
    // A missing housing type is flagged on the housing card.
    expect(screen.getByText('Missing')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /Back to list/ }));
    await user.click(screen.getByText('Ada Lovelace'));
    expect(await screen.findByRole('button', { name: /Reassign Bed/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Add Request/ })).toBeInTheDocument();
  });
});

describe('StudentsPage add request', () => {
  async function openRequestModal(user: ReturnType<typeof userEvent.setup>) {
    await user.click(screen.getByText('Ada Lovelace'));
    await user.click(await screen.findByRole('button', { name: /Add Request/ }));
    return screen.getByRole('heading', { name: 'New Request' }).closest('div')!.parentElement!.parentElement!;
  }

  it('submits a same-region transfer with the backend field mapping and refreshes the request list', async () => {
    const user = userEvent.setup();
    const { mock } = await renderLoadedPage();
    mock.onPost('/api/requests/').reply(201, { id: 99 });

    const modal = openRequestModal(user);
    const dialog = within(await modal);

    const submit = dialog.getByRole('button', { name: /Submit Request/ });
    expect(submit).toBeDisabled();

    await user.click(dialog.getByRole('button', { name: 'Different apartment, same region' }));
    await user.type(dialog.getByPlaceholderText('Explain the reason for this request...'), 'Closer to the faculty');
    expect(submit).toBeEnabled();

    await user.click(submit);

    expect(await screen.findByText('Request submitted successfully')).toBeInTheDocument();
    expect(mock.history.post.filter(({ url }) => url === '/api/requests/')).toHaveLength(1);
    expect(JSON.parse(mock.history.post.find(({ url }) => url === '/api/requests/')!.data)).toEqual({
      student: 1,
      request_type: 'apartment',
      reason: 'Closer to the faculty',
      same_apartment: false,
      transfer_scope: 'same_region',
      destination_regions: [],
    });
    // The student's request list is read again after the submission.
    await waitFor(() =>
      expect(mock.history.get.filter(({ url }) => url === '/api/requests/')).toHaveLength(2)
    );
  });

  it('requires a target region for a cross-region transfer and sends the chosen region PK', async () => {
    const user = userEvent.setup();
    const { mock } = await renderLoadedPage();
    mock.onPost('/api/requests/').reply(201, { id: 100 });

    const dialog = within(await openRequestModal(user));

    await user.click(dialog.getByRole('button', { name: 'Move to another region' }));
    await user.type(dialog.getByPlaceholderText('Explain the reason for this request...'), 'Moving labs');
    expect(dialog.getAllByText('Please select a target region').length).toBeGreaterThan(0);
    expect(dialog.getByRole('button', { name: /Submit Request/ })).toBeDisabled();

    await user.click(await dialog.findByRole('button', { name: /Broshim/ }));
    await user.click(dialog.getByRole('button', { name: /Submit Request/ }));

    await screen.findByText('Request submitted successfully');
    expect(JSON.parse(mock.history.post.find(({ url }) => url === '/api/requests/')!.data)).toMatchObject({
      request_type: 'apartment',
      same_apartment: null,
      transfer_scope: 'cross_region',
      destination_regions: ['broshim'],
    });
  });

  it('keeps cross-region transfers out of reach of a regional employee', async () => {
    const user = userEvent.setup();
    await renderLoadedPage({ user: regionalEmployee });

    const dialog = within(await openRequestModal(user));

    expect(dialog.getByRole('button', { name: 'Move to another region' })).toBeDisabled();
    expect(dialog.getByText(/Regional users are limited to their own region/)).toBeInTheDocument();
    expect(dialog.getByText('מעונות קנדה')).toBeInTheDocument();
  });

  it('shows the backend error and keeps the modal open when the request is refused', async () => {
    const user = userEvent.setup();
    const { mock } = await renderLoadedPage();
    mock.onPost('/api/requests/').reply(400, { reason: ['A pending request already exists'] });

    const dialog = within(await openRequestModal(user));
    await user.click(dialog.getByRole('button', { name: 'Within the same apartment' }));
    await user.type(dialog.getByPlaceholderText('Explain the reason for this request...'), 'Noise');
    await user.click(dialog.getByRole('button', { name: /Submit Request/ }));

    expect(await screen.findByText('reason: A pending request already exists')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'New Request' })).toBeInTheDocument();
  });
});

describe('StudentsPage add and edit student', () => {
  it('refuses to save without the required fields', async () => {
    const user = userEvent.setup();
    const { mock } = await renderLoadedPage();

    await user.click(screen.getByRole('button', { name: /Add Student/ }));
    expect(await screen.findByRole('heading', { name: 'Add New Student' })).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Save Student' }));
    expect(await screen.findByText('Please fill all required fields.')).toBeInTheDocument();
    expect(mock.history.post).toHaveLength(1); // the session refresh only
  });

  it('creates the student with the trimmed form payload and re-reads the list and the totals', async () => {
    const user = userEvent.setup();
    const { mock } = await renderLoadedPage();
    mock.onPost('/api/students/').reply(201, { ...ADA_DETAIL, id: 4, student_id: '900000000' });

    await user.click(screen.getByRole('button', { name: /Add Student/ }));
    await screen.findByRole('heading', { name: 'Add New Student' });

    await user.type(screen.getByLabelText(/Student ID/), ' 900000000 ');
    await user.type(screen.getByLabelText(/First name/), 'Tim');
    await user.type(screen.getByLabelText(/Last name/), 'Berners-Lee');
    // The dorm type list opens only once a region is chosen.
    expect(screen.getByLabelText(/Dorm Type/)).toBeDisabled();
    await user.selectOptions(screen.getByLabelText(/Region/), 'canada');
    await user.selectOptions(screen.getByLabelText(/Gender/), 'male');
    await user.selectOptions(screen.getByLabelText(/Dorm Type/), '2');
    await user.selectOptions(screen.getByLabelText(/Housing Type/), 'יחיד');

    const listCallsBefore = listRequests(mock).length;
    const countCallsBefore = mock.history.get.filter(({ url }) => url === '/api/students/counts/').length;

    await user.click(screen.getByRole('button', { name: 'Save Student' }));

    expect(await screen.findByText('Student added successfully.')).toBeInTheDocument();
    const created = mock.history.post.find(({ url }) => url === '/api/students/')!;
    expect(JSON.parse(created.data)).toEqual({
      student_id: '900000000',
      first_name: 'Tim',
      last_name: 'Berners-Lee',
      phone: '',
      email: '',
      city: '',
      gender: 'male',
      requested_religion: 'not_specified',
      accepted_dorm_type: '2',
      housing_type: 'יחיד',
      category: 'new',
    });
    await waitFor(() => expect(listRequests(mock).length).toBe(listCallsBefore + 1));
    await waitFor(() =>
      expect(mock.history.get.filter(({ url }) => url === '/api/students/counts/').length).toBe(countCallsBefore + 1)
    );
    // The modal closes itself after the confirmation.
    await waitFor(
      () => expect(screen.queryByRole('heading', { name: 'Add New Student' })).not.toBeInTheDocument(),
      { timeout: 3000 }
    );
  });

  it('maps backend field errors onto the form fields', async () => {
    const user = userEvent.setup();
    const { mock } = await renderLoadedPage();
    mock.onPost('/api/students/').reply(400, { student_id: ['student with this student id already exists.'] });

    await user.click(screen.getByRole('button', { name: /Add Student/ }));
    await screen.findByRole('heading', { name: 'Add New Student' });
    await user.type(screen.getByLabelText(/Student ID/), '200100300');
    await user.type(screen.getByLabelText(/First name/), 'Ada');
    await user.type(screen.getByLabelText(/Last name/), 'Lovelace');
    await user.selectOptions(screen.getByLabelText(/Region/), 'canada');
    await user.selectOptions(screen.getByLabelText(/Gender/), 'female');
    await user.selectOptions(screen.getByLabelText(/Dorm Type/), '2');
    await user.selectOptions(screen.getByLabelText(/Housing Type/), 'יחיד');
    await user.click(screen.getByRole('button', { name: 'Save Student' }));

    expect(
      await screen.findByText('student with this student id already exists.')
    ).toBeInTheDocument();
    expect(screen.getByText('student_id: student with this student id already exists.')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Add New Student' })).toBeInTheDocument();
  });

  it('edits a student from the detail view with a PATCH and shows the saved record', async () => {
    const user = userEvent.setup();
    const { mock } = await renderLoadedPage();
    mock.onPatch('/api/students/1/').reply(200, { ...ADA_DETAIL, city: 'Tel Aviv' });

    await user.click(screen.getByText('Ada Lovelace'));
    await user.click(await screen.findByRole('button', { name: /Edit Student Details/ }));
    expect(await screen.findByRole('heading', { name: 'Edit Student' })).toBeInTheDocument();

    // The student number is fixed; the rest is pre-filled from the record.
    expect(screen.getByLabelText(/Student ID/)).toBeDisabled();
    expect(screen.getByLabelText(/Student ID/)).toHaveValue('200100300');
    expect(screen.getByLabelText(/First name/)).toHaveValue('Ada');
    expect(screen.getByLabelText(/Region/)).toHaveValue('canada');
    expect(screen.getByLabelText(/Dorm Type/)).toHaveValue('2');

    await user.clear(screen.getByLabelText(/City/));
    await user.type(screen.getByLabelText(/City/), 'Tel Aviv');
    await user.click(screen.getByRole('button', { name: 'Save Changes' }));

    expect(await screen.findByText('Student details updated successfully.')).toBeInTheDocument();
    const patch = mock.history.patch.find(({ url }) => url === '/api/students/1/')!;
    expect(JSON.parse(patch.data)).toEqual({
      first_name: 'Ada',
      last_name: 'Lovelace',
      phone: '050-1112222',
      email: 'ada@example.com',
      city: 'Tel Aviv',
      gender: 'female',
      requested_religion: 'not_specified',
      accepted_dorm_type: '2',
      housing_type: 'יחיד',
      category: 'new',
    });
    // The detail view shows the saved record once the modal has closed.
    await waitFor(
      () => expect(screen.queryByRole('heading', { name: 'Edit Student' })).not.toBeInTheDocument(),
      { timeout: 3000 }
    );
    expect(screen.getByText('Tel Aviv')).toBeInTheDocument();
  });

  it('locks a regional employee to their own region in the student form', async () => {
    const user = userEvent.setup();
    await renderLoadedPage({ user: regionalEmployee });

    await user.click(screen.getByRole('button', { name: /Add Student/ }));
    await screen.findByRole('heading', { name: 'Add New Student' });

    expect(screen.queryByLabelText(/Region/)).not.toBeInTheDocument();
    expect(screen.getByText('מעונות קנדה')).toBeInTheDocument();
    // Without a region to pick, the dorm types are offered directly.
    expect(screen.getByLabelText(/Dorm Type/)).toBeEnabled();
  });
});
