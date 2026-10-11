import React from 'react';
import { describe, expect, it } from 'vitest';
import { act, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useLocation } from 'react-router-dom';
import type MockAdapter from 'axios-mock-adapter';

import { createDeferred } from '../../shared/test/deferred';
import { renderWithProviders, type TestUser } from '../../shared/test/render';
import AllocationResultsPage from './AllocationResultsPage';

// The page talks to the backend only through its typed adapter, which sits
// on the shared axios client; every reply below is registered on that
// client's mock adapter, so the request URLs, parameters and bodies
// asserted here are the ones the backend would receive.

const regionBoss: TestUser = {
  id: 2,
  email: 'boss@example.edu',
  role: 'region_boss',
  region: 'canada',
  region_name: 'מעונות קנדה',
};

const emptyResults = {
  assignments: [],
  unassigned_students: [],
  available_beds: [],
  unassigned_analysis: [],
  count: 0,
  counts: {},
};

const ADA = {
  student_id: '200100300',
  student_name: 'Ada Lovelace',
  dorm_type: 'קנדה',
  building_number: 105,
  apartment_number: '3',
  room_number: 'B',
  bed_number: 2,
  gender: 'female',
  religion_display: 'יהודי',
  housing_type_display: 'יחיד',
  apartment_type_display: 'Standard',
  assignment_status: 'active',
  assigned_at: '2026-10-01T10:00:00Z',
};

const GRACE = {
  student_id: '200400500',
  student_name: 'Grace Hopper',
  dorm_type: 'קנדה',
  building_number: 105,
  apartment_number: '3',
  room_number: 'A',
  bed_number: 1,
  gender: 'female',
  assigned_at: '2026-10-02T10:00:00Z',
};

const LINUS = {
  student_id: '200600700',
  student_name: 'Linus Pauling',
  gender: 'male',
  housing_type_display: 'זוגי',
  accepted_dorm_type: 'קנדה',
  religion_display: 'יהודי',
  religious: 'secular',
  placement_sector_display: 'General',
  is_priority: true,
  special_statuses: ['medical'],
  unassigned_reason: 'No compatible bed',
};

const RESERVED_BED = {
  bed_id: 11,
  region: 'Canada',
  dorm_type: 'קנדה',
  building_number: 105,
  apartment_number: '3',
  room_number: 'B',
  bed_number: 1,
  apartment_type_display: 'Standard',
  apartment_category_display: 'Mixed',
  is_reserved: true,
};

const FREE_BED = {
  bed_id: 12,
  region: 'Canada',
  dorm_type: 'קנדה',
  building_number: 106,
  apartment_number: '1',
  room_number: 'A',
  bed_number: 1,
  is_reserved: false,
};

const ANALYSIS_GROUP = {
  accepted_dorm_type_id: 2,
  accepted_dorm_type_code: 'CAN',
  accepted_dorm_type_name: 'קנדה',
  gender: 'male',
  housing_type: 'double',
  housing_type_display: 'זוגי',
  student_count: 1,
  physically_free_beds_in_accepted_dorm: 2,
  compatible_free_beds: 0,
  inventory_breakdown: [{ free_beds: 2, category_display: 'Mixed', apartment_type_display: 'Standard' }],
  reason_code: 'HOUSING_TYPE_OR_GENDER_MISMATCH',
};

// The server's counts deliberately disagree with the row counts, so a tab
// total can only be satisfied by showing what the backend reported.
const LOADED_RESULTS = {
  assignments: [ADA, GRACE],
  unassigned_students: [LINUS],
  available_beds: [FREE_BED, RESERVED_BED],
  unassigned_analysis: [ANALYSIS_GROUP],
  counts: { assigned: 7, unassigned: 1, available_beds: 2 },
};

const AFTER_RETRY_RESULTS = {
  assignments: [ADA, GRACE, { ...LINUS, dorm_type: 'קנדה', building_number: 106, apartment_number: '1', room_number: 'A', bed_number: 1 }],
  unassigned_students: [],
  available_beds: [RESERVED_BED],
  // The analysis block (which carries the retry outcome) is only rendered
  // while the server sends analysis groups, so the refreshed reply keeps one.
  unassigned_analysis: [{ ...ANALYSIS_GROUP, student_count: 0 }],
  counts: { assigned: 8, unassigned: 0, available_beds: 1 },
};

const CANADA_STATE = { region: { id: 'canada', name: 'מעונות קנדה' } };

// The state AllocationPage hands over right after a run: the run's id is
// what scopes the retry-unassigned action.
const RUN_STATE = {
  ...CANADA_STATE,
  result: { run: { id: 77, completed_at: '2026-10-05T08:30:00Z' }, roommate_matches: 3 },
  generatedAt: '2026-10-05T08:31:00Z',
};

const RESULTS_URL = '/api/allocation/results/';

// Navigation to Buildings is observable only through the router's search.
function LocationSearch(): React.ReactElement {
  const { pathname, search } = useLocation();
  return <div data-testid="buildings-location">{pathname}{search}</div>;
}

interface RenderOptions {
  language?: 'he' | 'en';
  /** The router state; null renders the page as a cold visit with no state. */
  state?: Record<string, unknown> | null;
  results?: unknown;
  mockApi?: (mock: MockAdapter) => void;
}

function renderResults({
  language = 'en', state = CANADA_STATE, results = LOADED_RESULTS, mockApi,
}: RenderOptions = {}) {
  return renderWithProviders(<AllocationResultsPage />, {
    route: { pathname: '/allocation/results', state: state ?? undefined },
    language,
    user: regionBoss,
    routes: {
      '/allocation': <div>Allocation page</div>,
      '/buildings': <LocationSearch />,
    },
    mockApi: (mock) => {
      mock.onGet(RESULTS_URL).reply(200, results);
      mockApi?.(mock);
    },
  });
}

// Renders and waits for the first results reply to be shown.
async function renderLoaded(options?: RenderOptions) {
  const utils = await renderResults(options);
  await waitFor(() => expect(screen.queryByText('Loading results...')).not.toBeInTheDocument(), { timeout: 3000 });
  return utils;
}

const resultRequests = (mock: MockAdapter) => mock.history.get.filter(({ url }) => url === RESULTS_URL);

const viewTab = (label: string) => screen.getByRole('button', { name: new RegExp(label) });

const toggleRow = (label: RegExp) => screen.getByRole('button', { name: label });

// The page root carries the text direction of the interface language.
const pageRoot = () => screen.getByRole('heading', { level: 1 }).closest('[dir]');

describe('AllocationResultsPage smoke', () => {
  it('loads the saved results for the region carried in router state', async () => {
    const { mock } = await renderResults({ language: 'en', state: CANADA_STATE, results: emptyResults });

    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Allocation Results');

    await screen.findByText('No allocation results to display right now');

    const requests = resultRequests(mock);
    expect(requests).toHaveLength(1);
    expect(requests[0].params).toEqual({ region: 'canada' });
    expect(screen.getByRole('button', { name: /Back to Allocation/ })).toBeInTheDocument();
  });

  it('falls back to the user-scoped results when no region was handed over', async () => {
    const { mock } = await renderResults({ language: 'he', state: null, results: emptyResults });

    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('תוצאות השיבוץ');
    await screen.findByText('חזרה לעמוד השיבוץ');

    const requests = resultRequests(mock);
    expect(requests).toHaveLength(1);
    expect(requests[0].params).toEqual({});
  });
});

describe('AllocationResultsPage loading', () => {
  it('shows the loading state until the results reply arrives', async () => {
    const pending = createDeferred<unknown>();
    const { mock } = await renderResults({
      mockApi: (m) => {
        m.onGet(RESULTS_URL).reply(() => pending.promise.then((body) => [200, body]));
      },
    });

    expect(screen.getByText('Loading results...')).toBeInTheDocument();
    expect(screen.queryByText('No allocation results to display right now')).not.toBeInTheDocument();
    await waitFor(() => expect(resultRequests(mock)).toHaveLength(1));

    await act(async () => { pending.resolve(LOADED_RESULTS); });

    expect(await screen.findByText('קנדה')).toBeInTheDocument();
    expect(screen.queryByText('Loading results...')).not.toBeInTheDocument();
  });

  it('reads the region from the summary when only a summary was handed over', async () => {
    const { mock } = await renderLoaded({
      state: { summary: { region_id: 'broshim', latest_run: { id: 5, status: 'completed' } } },
    });

    expect(resultRequests(mock)[0].params).toEqual({ region: 'broshim' });
  });

  it('shows the failed load with its message and reloads on retry', async () => {
    let calls = 0;
    const { mock } = await renderResults({
      mockApi: (m) => {
        m.onGet(RESULTS_URL).reply(() => {
          calls += 1;
          return calls === 1 ? [500, { detail: 'database unavailable' }] : [200, LOADED_RESULTS];
        });
      },
    });

    expect(await screen.findByText('database unavailable', undefined, { timeout: 3000 })).toBeInTheDocument();
    expect(screen.queryByText('No allocation results to display right now')).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: /Retry/ }));

    expect(await screen.findByText('קנדה', undefined, { timeout: 3000 })).toBeInTheDocument();
    expect(resultRequests(mock)).toHaveLength(2);
    expect(screen.queryByText('database unavailable')).not.toBeInTheDocument();
  });

  it('shows every view empty when the server holds no results', async () => {
    await renderLoaded({ results: emptyResults });

    expect(screen.getByText('No allocation results to display right now')).toBeInTheDocument();
    expect(viewTab('Assigned Students')).toHaveTextContent('0');
    expect(viewTab('Unassigned Students')).toHaveTextContent('0');
    expect(viewTab('Available Beds')).toHaveTextContent('0');

    await userEvent.click(viewTab('Unassigned Students'));
    expect(screen.getByText('No unassigned students')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Retry unassigned students/ })).not.toBeInTheDocument();

    await userEvent.click(viewTab('Available Beds'));
    expect(screen.getByText('No available beds to display')).toBeInTheDocument();
  });
});

describe('AllocationResultsPage summary', () => {
  it('shows the server totals on the view tabs, not the row counts', async () => {
    await renderLoaded();

    expect(viewTab('Assigned Students')).toHaveTextContent('7');
    expect(viewTab('Unassigned Students')).toHaveTextContent('1');
    expect(viewTab('Available Beds')).toHaveTextContent('2');
  });

  it('dates the last allocation from the handed-over run, in the interface locale', async () => {
    await renderLoaded({ state: RUN_STATE });

    const expected = new Date('2026-10-05T08:30:00Z').toLocaleString('en-US');
    expect(screen.getByText('Last Allocation').nextElementSibling).toHaveTextContent(expected);
  });

  it('dates the last allocation from the newest assignment when no run is known', async () => {
    await renderLoaded();

    const expected = new Date('2026-10-02T10:00:00Z').toLocaleString('en-US');
    expect(screen.getByText('Last Allocation').nextElementSibling).toHaveTextContent(expected);
  });

  it('shows a dash when nothing dates the allocation', async () => {
    await renderLoaded({ results: emptyResults });

    expect(screen.getByText('Last Allocation').nextElementSibling).toHaveTextContent('-');
  });
});

describe('AllocationResultsPage view tabs', () => {
  it('starts on the assigned view and switches the panel on click', async () => {
    await renderLoaded();

    expect(viewTab('Assigned Students')).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByText('Detailed Assignments')).toBeInTheDocument();

    await userEvent.click(viewTab('Unassigned Students'));
    expect(viewTab('Unassigned Students')).toHaveAttribute('aria-pressed', 'true');
    expect(viewTab('Assigned Students')).toHaveAttribute('aria-pressed', 'false');
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Allocation Results');
    expect(screen.getByText('Linus Pauling')).toBeInTheDocument();

    await userEvent.click(viewTab('Available Beds'));
    expect(viewTab('Available Beds')).toHaveAttribute('aria-pressed', 'true');
    expect(screen.queryByText('Linus Pauling')).not.toBeInTheDocument();
    expect(screen.getAllByRole('row')).toHaveLength(3);
  });
});

describe('AllocationResultsPage assignments hierarchy', () => {
  it('groups the assignments dorm type -> building -> apartment -> room -> student, expanding on click', async () => {
    await renderLoaded();

    // Only the dorm type level is open-able at first; everything starts collapsed.
    // Free beds build the tree too: the bed in building 106 adds a second building.
    const dorm = toggleRow(/^קנדה/);
    expect(dorm).toHaveAttribute('aria-expanded', 'false');
    expect(dorm).toHaveTextContent('2 buildings');
    expect(dorm).toHaveTextContent('2 assigned');
    expect(dorm).toHaveTextContent('2 available beds');
    expect(screen.queryByText('Building 105')).not.toBeInTheDocument();

    await userEvent.click(dorm);
    expect(dorm).toHaveAttribute('aria-expanded', 'true');
    const building = toggleRow(/Building 105/);
    expect(building).toHaveTextContent('1 apartments');
    expect(building).toHaveTextContent('2 assigned');
    expect(building).toHaveTextContent('1 available beds');

    await userEvent.click(building);
    const apartment = toggleRow(/Apartment 3/);
    expect(apartment).toHaveTextContent('Standard');
    expect(apartment).toHaveTextContent('2 rooms');
    expect(apartment).toHaveTextContent('Available');

    await userEvent.click(apartment);
    // Rooms are numbered in order; A is full, B still has a free bed.
    const rooms = screen.getAllByRole('button', { name: /^Room / });
    expect(rooms.map((r) => r.textContent?.slice(0, 6))).toEqual(['Room A', 'Room B']);
    expect(toggleRow(/^Room A/)).toHaveTextContent('Full');
    expect(toggleRow(/^Room B/)).toHaveTextContent('Available');
    expect(toggleRow(/^Room B/)).toHaveTextContent('1 occupied beds');

    await userEvent.click(toggleRow(/^Room B/));
    expect(screen.getByText('Ada Lovelace')).toBeInTheDocument();
    expect(screen.getByText('Student ID: 200100300')).toBeInTheDocument();
    expect(screen.getByText('active')).toBeInTheDocument();
    expect(screen.getByText('Bed:').parentElement).toHaveTextContent('Bed: 2');
    expect(screen.getByText('Gender:').parentElement).toHaveTextContent('Gender: Woman');
    expect(screen.getByText('Religion:').parentElement).toHaveTextContent('Religion: יהודי');
    expect(screen.getByText('Housing Type:').parentElement).toHaveTextContent('Housing Type: יחיד');
    expect(screen.getByText('Available bed: 1')).toBeInTheDocument();
    expect(screen.queryByText('Grace Hopper')).not.toBeInTheDocument();

    // Collapsing the dorm type hides the whole subtree again.
    await userEvent.click(dorm);
    expect(dorm).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByText('Building 105')).not.toBeInTheDocument();
    expect(screen.queryByText('Ada Lovelace')).not.toBeInTheDocument();
  });

  it('lists a room with only free beds as empty, with its no-students note', async () => {
    await renderLoaded({ results: { ...LOADED_RESULTS, assignments: [ADA], available_beds: [FREE_BED] } });

    await userEvent.click(toggleRow(/^קנדה/));
    await userEvent.click(toggleRow(/Building 106/));
    expect(toggleRow(/Apartment 1/)).toHaveTextContent('Empty');
    await userEvent.click(toggleRow(/Apartment 1/));
    await userEvent.click(toggleRow(/^Room A/));

    expect(screen.getByText('No students assigned to this room')).toBeInTheDocument();
    expect(screen.getByText('Available bed: 1')).toBeInTheDocument();
  });
});

describe('AllocationResultsPage unassigned students', () => {
  it('lists the unassigned students with their analysis cards', async () => {
    await renderLoaded();
    await userEvent.click(viewTab('Unassigned Students'));

    const row = screen.getByText('Linus Pauling').closest('tr');
    expect(row).not.toBeNull();
    const cells = within(row as HTMLTableRowElement).getAllByRole('cell').map((c) => c.textContent);
    expect(cells).toEqual([
      'Linus Pauling', '200600700', 'Man', 'זוגי', 'קנדה', 'יהודי', 'secular', 'General', 'Yes', 'medical', 'No compatible bed',
    ]);

    expect(screen.getByText('Why weren’t some students assigned?')).toBeInTheDocument();
    expect(screen.getByText(/students unassigned/)).toHaveTextContent('1 students unassigned — זוגי · קנדה');
    expect(screen.getByText('2 physically free beds in this dorm type')).toBeInTheDocument();
    expect(screen.getByText('0 compatible free beds')).toBeInTheDocument();
    expect(screen.getByText('2 Mixed · Standard')).toBeInTheDocument();
    expect(screen.getByText(/There are no free beds matching their housing type and gender/)).toBeInTheDocument();
  });

  it('navigates to Buildings management scoped to the analysis group', async () => {
    await renderLoaded();
    await userEvent.click(viewTab('Unassigned Students'));

    await userEvent.click(screen.getByRole('button', { name: /Show relevant free beds/ }));

    const expected = new URLSearchParams({
      region: 'canada',
      dormTypeId: '2',
      dormTypeCode: 'CAN',
      dormTypeName: 'קנדה',
      gender: 'male',
      housingType: 'double',
      studentCount: '1',
      freeOnly: '1',
    }).toString();
    expect(screen.getByTestId('buildings-location')).toHaveTextContent(`/buildings?${expected}`);
  });

  it('offers no retry without a known run', async () => {
    await renderLoaded();
    await userEvent.click(viewTab('Unassigned Students'));

    const retry = screen.getByRole('button', { name: /Retry unassigned students/ });
    expect(retry).toBeDisabled();
    expect(retry).toHaveAttribute('title', 'No active allocation run found to retry');
  });

  it('retries the run after confirmation and re-reads the results', async () => {
    let resultCalls = 0;
    const { mock } = await renderLoaded({
      state: RUN_STATE,
      mockApi: (m) => {
        m.onGet(RESULTS_URL).reply(() => {
          resultCalls += 1;
          return [200, resultCalls === 1 ? LOADED_RESULTS : AFTER_RETRY_RESULTS];
        });
        m.onPost('/api/allocation/runs/77/retry-unassigned/').reply(200, {
          success: true,
          result: { successful_assignments: 1, retried_student_count: 1 },
        });
      },
    });
    await userEvent.click(viewTab('Unassigned Students'));

    await userEvent.click(screen.getByRole('button', { name: /Retry unassigned students/ }));
    const dialog = screen.getByRole('dialog');
    expect(dialog).toHaveTextContent('Retry Allocation');
    expect(dialog).toHaveTextContent(
      'This will retry allocating the 1 students left unassigned by the current run, against currently available inventory only. Existing assignments will not change. Continue?'
    );

    // "No" only closes the confirmation.
    await userEvent.click(within(dialog).getByRole('button', { name: 'No' }));
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(mock.history.post.filter(({ url }) => url?.includes('retry-unassigned'))).toHaveLength(0);

    await userEvent.click(screen.getByRole('button', { name: /Retry unassigned students/ }));
    await userEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Yes' }));

    expect(
      await screen.findByText('Retry complete: 1 of 1 students were just assigned.', undefined, { timeout: 3000 })
    ).toBeInTheDocument();
    const retryPosts = mock.history.post.filter(({ url }) => url === '/api/allocation/runs/77/retry-unassigned/');
    expect(retryPosts).toHaveLength(1);
    expect(JSON.parse(retryPosts[0].data as string)).toEqual({});
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();

    // The page re-read the saved results (for the same region) rather than editing locally.
    await waitFor(() => expect(resultRequests(mock)).toHaveLength(2), { timeout: 3000 });
    expect(resultRequests(mock)[1].params).toEqual({ region: 'canada' });
    expect(await screen.findByText('No unassigned students')).toBeInTheDocument();
    expect(screen.queryByText('Linus Pauling')).not.toBeInTheDocument();
    expect(viewTab('Assigned Students')).toHaveTextContent('8');
    expect(viewTab('Unassigned Students')).toHaveTextContent('0');
  });

  it('retries against the summary\'s latest completed run when no result was handed over', async () => {
    const { mock } = await renderLoaded({
      state: { ...CANADA_STATE, summary: { latest_run: { id: 5, status: 'completed' } } },
      mockApi: (m) => {
        m.onPost('/api/allocation/runs/5/retry-unassigned/').reply(200, {
          result: { successful_assignments: 0, retried_student_count: 1 },
        });
      },
    });
    await userEvent.click(viewTab('Unassigned Students'));

    await userEvent.click(screen.getByRole('button', { name: /Retry unassigned students/ }));
    await userEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Yes' }));

    expect(
      await screen.findByText('Retry complete: 0 of 1 students were just assigned.', undefined, { timeout: 3000 })
    ).toBeInTheDocument();
    expect(mock.history.post.filter(({ url }) => url === '/api/allocation/runs/5/retry-unassigned/')).toHaveLength(1);
  });

  it('keeps the confirmation open and reports a failed retry', async () => {
    const { mock } = await renderLoaded({
      state: RUN_STATE,
      mockApi: (m) => {
        m.onPost('/api/allocation/runs/77/retry-unassigned/').reply(500, { detail: 'solver is busy' });
      },
    });
    await userEvent.click(viewTab('Unassigned Students'));

    await userEvent.click(screen.getByRole('button', { name: /Retry unassigned students/ }));
    await userEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Yes' }));

    expect(await screen.findByText('solver is busy', undefined, { timeout: 3000 })).toBeInTheDocument();
    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(resultRequests(mock)).toHaveLength(1);
    expect(screen.getByText('Linus Pauling')).toBeInTheDocument();
  });
});

describe('AllocationResultsPage available beds', () => {
  it('lists the free beds in location order with their reserved state', async () => {
    await renderLoaded();
    await userEvent.click(viewTab('Available Beds'));

    const headers = screen.getAllByRole('columnheader').map((h) => h.textContent);
    expect(headers).toEqual(['', 'Dorm Type', 'Building', 'Apartment', 'Room', 'Bed', 'Apartment Type', 'Category', 'Reserved']);

    const rows = screen.getAllByRole('row').slice(1);
    const cellsOf = (row: HTMLElement) => within(row).getAllByRole('cell').map((c) => c.textContent);
    // Building 105 sorts before 106 whatever order the server sent.
    expect(cellsOf(rows[0])).toEqual(['Canada', 'קנדה', '105', '3', 'B', '1', 'Standard', 'Mixed', 'Yes']);
    expect(cellsOf(rows[1])).toEqual(['Canada', 'קנדה', '106', '1', 'A', '1', '-', '-', 'No']);
  });
});

describe('AllocationResultsPage navigation', () => {
  it('goes back to the Allocation page', async () => {
    const { currentPath } = await renderLoaded();

    await userEvent.click(screen.getByRole('button', { name: /Back to Allocation/ }));

    expect(currentPath()).toBe('/allocation');
    expect(screen.getByText('Allocation page')).toBeInTheDocument();
  });
});

describe('AllocationResultsPage language', () => {
  it('renders Hebrew copy right-to-left', async () => {
    await renderLoaded({ language: 'he' });

    expect(pageRoot()).toHaveAttribute('dir', 'rtl');
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('תוצאות השיבוץ');
    expect(screen.getByText('תוצאות מהמערכת')).toBeInTheDocument();
    expect(screen.getByText('שיבוצים מפורטים')).toBeInTheDocument();
    expect(viewTab('סטודנטים משובצים')).toHaveTextContent('7');
    expect(toggleRow(/^קנדה/)).toHaveTextContent('2 בניינים');

    await userEvent.click(viewTab('סטודנטים שלא שובצו'));
    expect(screen.getByText('למה חלק מהסטודנטים לא שובצו?')).toBeInTheDocument();
    const row = screen.getByText('Linus Pauling').closest('tr') as HTMLTableRowElement;
    expect(within(row).getAllByRole('cell')[2]).toHaveTextContent('גבר');
    expect(within(row).getAllByRole('cell')[8]).toHaveTextContent('כן');
    expect(screen.getByRole('button', { name: /נסה לשבץ שוב את הסטודנטים שלא שובצו/ })).toBeInTheDocument();
  });

  it('renders English copy left-to-right', async () => {
    await renderLoaded({ language: 'en' });

    expect(pageRoot()).toHaveAttribute('dir', 'ltr');
    expect(screen.getByText('System Results')).toBeInTheDocument();
    expect(screen.getByText('Saved allocation results according to the user region')).toBeInTheDocument();
  });
});
