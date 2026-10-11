import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, fireEvent, screen, within } from '@testing-library/react';
import { useLocation } from 'react-router-dom';
import type MockAdapter from 'axios-mock-adapter';

import { renderWithProviders, type TestUser } from '../../shared/test/render';
import AllocationPage from './AllocationPage';

// The page talks to the backend only through its typed adapters, which sit
// on the shared axios client; every reply below is registered on that
// client's mock adapter, so the URLs and bodies asserted here are the ones
// the backend would receive. The real AuthProvider restores the session, so
// run permissions and the user's region come from the genuine role rules.

// The page's own cadences: run status every 3 s, the open preview every 5 s.
const STATUS_POLL_MS = 3000;
const PREVIEW_POLL_MS = 5000;

const REGION = { id: 'canada', name: 'מעונות קנדה' };
const RUN_ID = 41;

const centralAdmin: TestUser = {
  id: 9,
  email: 'staff@example.edu',
  role: 'central_admin',
  region: 'canada',
  region_name: 'מעונות קנדה',
};

const regionBoss: TestUser = {
  id: 10,
  email: 'boss@example.edu',
  role: 'region_boss',
  region: 'canada',
  region_name: 'מעונות קנדה',
};

const employee: TestUser = {
  id: 11,
  email: 'employee@example.edu',
  role: 'employee',
  region: 'canada',
  region_name: 'מעונות קנדה',
};

const INVENTORY = {
  single: { apartments: 10, rooms: 20, total_beds: 40, occupied_beds: 10, available_beds: 30 },
  couple: { apartments: 4, rooms: 4, total_beds: 8, occupied_beds: 8, available_beds: 0 },
  family: { apartments: 2, rooms: 4, total_beds: 8, occupied_beds: 2, available_beds: 6 },
};

const POPULATION = {
  imported_students: 50,
  excluded_accessibility: 3,
  excluded_leaving: 7,
  excluded_overlap: 1,
  excluded_total: 9,
  sent_to_solver: 41,
};

const SUMMARY_BEFORE_RUN = {
  total_students: 40,
  unassigned_students: 40,
  assigned_students: 0,
  available_beds: 60,
  region: REGION,
  inventory_by_type: INVENTORY,
  population_summary: POPULATION,
};

const SUMMARY_AFTER_RUN = {
  ...SUMMARY_BEFORE_RUN,
  unassigned_students: 2,
  assigned_students: 38,
  available_beds: 22,
};

const INBOX_PENDING = {
  id: 7,
  region: 'canada',
  region_name: 'מעונות קנדה',
  students_count: 25,
  status: 'pending',
  created_at: '2026-09-30T08:00:00Z',
};

const run = (status: string, extra: Record<string, unknown> = {}) => ({
  id: RUN_ID,
  region: 'canada',
  status,
  elapsed_search_seconds: 0,
  max_search_seconds: 500,
  remaining_search_seconds: 500,
  ...extra,
});

const snapshot = (sequence: number, students: string[]) => ({
  sequence,
  assigned_count: students.length,
  unassigned_count: 40 - students.length,
  solver_status: 'FEASIBLE',
  wall_time_seconds: 12,
  assignments: students.map((name, i) => ({
    student_db_id: i + 1,
    student_name: name,
    apartment_code: `105-${i + 1}`,
    room_code: 'A',
    bed_label: 'bed 1',
  })),
});

// The constraints payload the page sends with every run until the user
// changes a condition: critical constraints forced on at weight 0, the
// flexible preferences with their default weights.
const DEFAULT_EFFECTIVE_CONSTRAINTS = {
  sameGender:              { enabled: true, strict: true,  critical: true,  weight: 0 },
  priorityFirst:           { enabled: true, strict: true,  critical: true,  weight: 0 },
  roommatePositiveOnly:    { enabled: true, strict: true,  critical: true,  weight: 0 },
  ReligiousTogether:       { enabled: true, strict: true,  critical: true,  weight: 0 },
  sameReligion:            { enabled: true, strict: false, critical: false, weight: 6 },
  roommateMatch:           { enabled: true, strict: false, critical: false, weight: 8 },
  sectorMatching:          { enabled: true, strict: false, critical: false, weight: 7 },
  avoidYearMix_1_with_3_4: { enabled: true, strict: false, critical: false, weight: 4 },
  avoidAtudaimWithHasmaha: { enabled: true, strict: false, critical: false, weight: 4 },
};

const ACTIVE_RUN_URL = /^\/api\/allocation\/runs\/active\//;
const RUN_STATUS_URL = `/api/allocation/runs/${RUN_ID}/`;
const PREVIEW_URL = `/api/allocation/runs/${RUN_ID}/preview/`;

interface ApiOptions {
  /** The persistent summary reply. */
  summary?: unknown;
  /** The active-run reply for the summary's region. */
  activeRun?: unknown;
  /**
   * One-off replies (replyOnce sequences) for endpoints that also get a
   * persistent default below. The adapter matches handlers in registration
   * order, so these must be registered first to be consumed before the
   * default answers.
   */
  before?: (mock: MockAdapter) => void;
}

function mockAllocationApi(
  mock: MockAdapter,
  { summary = SUMMARY_BEFORE_RUN, activeRun = { run: null }, before }: ApiOptions = {}
) {
  before?.(mock);
  mock.onGet('/api/allocation/summary/').reply(200, summary);
  mock.onGet(ACTIVE_RUN_URL).reply(200, activeRun);
  mock.onGet('/api/inbox/latest/').reply(200, { inbox: null });
  mock.onPost('/api/allocation/start/').reply(200, { run_id: RUN_ID, run: run('queued') });
  mock.onGet(RUN_STATUS_URL).reply(200, { run: run('running') });
  mock.onPost(`/api/allocation/runs/${RUN_ID}/stop/`).reply(200, {});
  mock.onPost(`/api/allocation/runs/${RUN_ID}/stop-and-save/`).reply(200, {});
  mock.onDelete(`/api/allocation/runs/${RUN_ID}/delete/`).reply(200, {});
}

// The page is driven by its own intervals and toast timeouts, so every test
// runs on fake timers and advances them explicitly; real time still ticks
// underneath so Testing Library's own waiting keeps working.
async function advance(ms = 0) {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
  });
}

const pollOnce = () => advance(STATUS_POLL_MS);

const button = (label: string) => screen.getByText(label).closest('button') as HTMLButtonElement;
const queryButton = (label: string) => screen.queryByText(label)?.closest('button') ?? null;
const dialog = () => screen.getByRole('dialog');
const toast = () => screen.getByRole('alert');

const requests = (mock: MockAdapter, method: 'get' | 'post' | 'put' | 'delete', url: string | RegExp) =>
  mock.history[method].filter(({ url: u }) => (typeof url === 'string' ? u === url : url.test(u ?? '')));

const summaryCalls = (mock: MockAdapter) => requests(mock, 'get', '/api/allocation/summary/');
const statusCalls = (mock: MockAdapter) => requests(mock, 'get', RUN_STATUS_URL);
const startCalls = (mock: MockAdapter) => requests(mock, 'post', '/api/allocation/start/');
const startBody = (mock: MockAdapter, index = 0) => JSON.parse(startCalls(mock)[index].data as string) as Record<string, unknown>;

interface RenderOptions {
  language?: 'he' | 'en';
  user?: TestUser;
  mockApi?: (mock: MockAdapter) => void;
  routes?: Record<string, React.ReactNode>;
}

async function renderAllocationPage({
  language = 'en', user = centralAdmin, mockApi = mockAllocationApi, routes,
}: RenderOptions = {}) {
  const utils = await renderWithProviders(<AllocationPage />, {
    route: '/allocation', language, user, mockApi, routes,
  });
  await advance();
  return utils;
}

// Renders and waits until the summary has been shown (the Run button exists).
async function renderLoadedPage(options: RenderOptions = {}) {
  const utils = await renderAllocationPage(options);
  // "View Results" is offered whatever the run state, so it marks the
  // loaded page even when a live run is restored.
  const label = options.language === 'he' ? 'צפה בתוצאות' : 'View Results';
  expect(await screen.findByText(label, undefined, { timeout: 3000 })).toBeInTheDocument();
  return utils;
}

async function startRun(options: RenderOptions = {}) {
  const utils = await renderLoadedPage(options);
  fireEvent.click(button('Run Allocation'));
  await advance();
  return utils;
}

async function confirm() {
  fireEvent.click(within(dialog()).getByText('Confirm'));
  await advance();
}

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
});

afterEach(() => {
  vi.clearAllTimers();
  vi.useRealTimers();
});

describe('AllocationPage initial load', () => {
  it('shows the loading state, then the summary, the region and the inventory, and looks up the active run for the summary region', async () => {
    const { mock } = await renderAllocationPage();

    expect(await screen.findByText('Run Allocation', undefined, { timeout: 3000 })).toBeInTheDocument();
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Allocation');
    expect(screen.getByText('Not Started')).toBeInTheDocument();
    expect(screen.getByText('Canada Dormitories')).toBeInTheDocument();

    // The four stat tiles before any run: totals from the summary.
    expect(screen.getByText('Total Students').parentElement).toHaveTextContent('40');
    expect(screen.getByText('Allocated').parentElement).toHaveTextContent('0');
    expect(screen.getByText('Unallocated').parentElement).toHaveTextContent('40');
    expect(screen.getAllByText('Available Beds')[0].parentElement).toHaveTextContent('60');

    // Inventory rows, one per housing type, collapsed.
    expect(screen.getByText('Single Housing')).toBeInTheDocument();
    expect(screen.getByText('Couple Housing')).toBeInTheDocument();
    expect(screen.getByText('Family Housing')).toBeInTheDocument();

    // The active-run lookup is scoped to the summary's region; nothing is
    // polled while no run exists, and a central admin has no inbox.
    expect(requests(mock, 'get', ACTIVE_RUN_URL).map(({ url }) => url)).toEqual([
      '/api/allocation/runs/active/?region=canada',
    ]);
    expect(statusCalls(mock)).toHaveLength(0);
    expect(requests(mock, 'get', '/api/inbox/latest/')).toHaveLength(0);

    expect(queryButton('Cancel Run')).toBeNull();
    expect(queryButton('Stop & Save Result')).toBeNull();
    expect(queryButton('View Current Result')).toBeNull();
    expect(queryButton('Delete Results')).toBeNull();
    expect(button('View Results')).toBeEnabled();
  });

  it('shows the fatal error state when the summary cannot be loaded and retries on demand', async () => {
    const { mock } = await renderAllocationPage({
      mockApi: (m) => mockAllocationApi(m, {
        before: (b) => { b.onGet('/api/allocation/summary/').replyOnce(500, { detail: 'database unavailable' }); },
      }),
    });

    expect(await screen.findByText('Error loading data', undefined, { timeout: 3000 })).toBeInTheDocument();
    expect(screen.getByText('database unavailable')).toBeInTheDocument();
    expect(screen.queryByText('Run Allocation')).not.toBeInTheDocument();

    fireEvent.click(button('Try again'));
    await advance();

    expect(await screen.findByText('Run Allocation', undefined, { timeout: 3000 })).toBeInTheDocument();
    expect(summaryCalls(mock)).toHaveLength(2);
  });

  it('renders the Hebrew interface when the language is Hebrew', async () => {
    await renderLoadedPage({ language: 'he' });

    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('שיבוץ סטודנטים');
    expect(screen.getByText('לא הופעל')).toBeInTheDocument();
    expect(screen.getByText('מעונות קנדה')).toBeInTheDocument();
    expect(screen.getByText('סה״כ סטודנטים')).toBeInTheDocument();
    expect(screen.getByText('מלאי דיור לפי סוג')).toBeInTheDocument();
    expect(screen.getByText('תנאי ואילוצי שיבוץ')).toBeInTheDocument();
    expect(screen.getByText('זמן חיפוש מרבי')).toBeInTheDocument();
    expect(screen.getByText('צפה בתוצאות')).toBeInTheDocument();
  });

  it('shows the population summary and reveals the exclusion breakdown on demand', async () => {
    await renderLoadedPage();

    expect(screen.getByText('50 imported')).toBeInTheDocument();
    expect(screen.getByText('9 excluded')).toBeInTheDocument();
    expect(screen.getByText('41 sent to allocation')).toBeInTheDocument();
    expect(screen.queryByText('3 accessibility — handled manually')).not.toBeInTheDocument();

    const toggle = screen.getByRole('button', { name: 'Show details' });
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    fireEvent.click(toggle);

    expect(screen.getByRole('button', { name: 'Hide details' })).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByText('3 accessibility — handled manually')).toBeInTheDocument();
    expect(screen.getByText('7 leaving — do not take part in allocation')).toBeInTheDocument();
    expect(screen.getByText('1 in both groups')).toBeInTheDocument();
    expect(screen.getByText('total unique excluded: 9')).toBeInTheDocument();
  });

  it('expands an inventory row to its metrics and collapses it again', async () => {
    await renderLoadedPage();

    const row = screen.getByRole('button', { name: /Single Housing/ });
    expect(row).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByText('Occupied Beds')).not.toBeInTheDocument();

    fireEvent.click(row);
    expect(row).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByText('Apartments').parentElement).toHaveTextContent('10');
    expect(screen.getByText('Rooms').parentElement).toHaveTextContent('20');
    expect(screen.getByText('Total Beds').parentElement).toHaveTextContent('40');
    expect(screen.getByText('Occupied Beds').parentElement).toHaveTextContent('10');
    // 40 beds, 30 free: 25% occupied.
    expect(screen.getByText('Occupancy').parentElement).toHaveTextContent('25%');

    fireEvent.click(row);
    expect(row).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByText('Occupied Beds')).not.toBeInTheDocument();
  });

  it('disables the run when there are no unassigned students', async () => {
    await renderLoadedPage({
      mockApi: (m) => mockAllocationApi(m, {
        summary: { ...SUMMARY_BEFORE_RUN, unassigned_students: 0, assigned_students: 0 },
      }),
    });

    expect(button('Run Allocation')).toBeDisabled();
    expect(button('Run Allocation')).toHaveAttribute('title', 'No students to assign');
  });
});

describe('AllocationPage permissions and regions', () => {
  it('lets a region boss run the allocation for their own region and reads their inbox', async () => {
    const { mock } = await renderLoadedPage({
      user: regionBoss,
      mockApi: (m) => {
        mockAllocationApi(m);
        m.onGet('/api/inbox/latest/').reply(200, { inbox: INBOX_PENDING });
        m.onPut('/api/inbox/7/viewed/').reply(200, { inbox: { ...INBOX_PENDING, status: 'viewed' } });
      },
    });

    expect(button('Run Allocation')).toBeEnabled();
    expect(screen.queryByText('No permission to run allocation')).not.toBeInTheDocument();

    // The pending notice is shown and marked as viewed the moment it is read.
    expect(screen.getByText('Notification from Housing Office')).toBeInTheDocument();
    expect(screen.getByText('students received for allocation').previousElementSibling).toHaveTextContent('25');
    expect(screen.getByText('Pending')).toBeInTheDocument();
    expect(requests(mock, 'put', '/api/inbox/7/viewed/')).toHaveLength(1);

    fireEvent.click(button('Run Allocation'));
    await advance();

    // The run is started for the user's own region; the inbox item is
    // marked processed once the run has been accepted.
    expect(startBody(mock).region).toBe('canada');
    expect(requests(mock, 'put', '/api/inbox/7/processed/')).toHaveLength(1);
  });

  it('does not mark an already viewed inbox notice again', async () => {
    const { mock } = await renderLoadedPage({
      user: regionBoss,
      mockApi: (m) => {
        mockAllocationApi(m);
        m.onGet('/api/inbox/latest/').reply(200, { inbox: { ...INBOX_PENDING, status: 'viewed' } });
      },
    });

    expect(screen.getByText('Viewed')).toBeInTheDocument();
    expect(screen.queryByText('Pending')).not.toBeInTheDocument();
    expect(requests(mock, 'put', /\/api\/inbox\//)).toHaveLength(0);
  });

  it('denies the run to an employee, explains why, and keeps the conditions read-only', async () => {
    const { mock } = await renderLoadedPage({ user: employee });

    expect(button('Run Allocation')).toBeDisabled();
    expect(button('Run Allocation')).toHaveAttribute('title', 'No permission to run allocation');
    expect(screen.getByText('No permission to run allocation')).toBeInTheDocument();
    // The conditions are still shown; the lock notice sits below them.
    expect(screen.getByText('Critical Conditions')).toBeInTheDocument();
    expect(screen.getByText('Flexible Preferences')).toBeInTheDocument();
    expect(button('View Results')).toBeEnabled();

    fireEvent.click(button('Run Allocation'));
    await advance();
    expect(startCalls(mock)).toHaveLength(0);
  });

  it('shows the ANIR priority texts for the upper-dorms region', async () => {
    await renderLoadedPage({
      mockApi: (m) => mockAllocationApi(m, {
        summary: { ...SUMMARY_BEFORE_RUN, region: { id: 'gush-elyon', name: 'גוש עליון' } },
      }),
    });

    expect(screen.getByText('ANIR priority')).toBeInTheDocument();
    expect(screen.getByText('ANIR students get priority for Building 179 when available.')).toBeInTheDocument();
    expect(screen.queryByText('Priority students')).not.toBeInTheDocument();
  });
});

describe('AllocationPage start', () => {
  it('starts a run for the user region with the configured search time and constraints and shows it queued', async () => {
    const { mock } = await renderLoadedPage();

    expect(screen.getByText('Not Started')).toBeInTheDocument();
    expect(queryButton('Cancel Run')).toBeNull();
    expect(queryButton('Stop & Save Result')).toBeNull();
    expect(queryButton('View Current Result')).toBeNull();

    fireEvent.click(button('Run Allocation'));
    await advance();

    expect(startCalls(mock)).toHaveLength(1);
    expect(startBody(mock)).toEqual({
      region: 'canada',
      constraints: DEFAULT_EFFECTIVE_CONSTRAINTS,
      max_solver_seconds: 500,
    });

    expect(screen.getByText('Queued')).toBeInTheDocument();
    expect(button('Running...')).toBeDisabled();
    expect(button('View Current Result')).toBeEnabled();
    expect(button('Stop & Save Result')).toBeEnabled();
    expect(button('Cancel Run')).toBeEnabled();
    expect(screen.getByText('Allocation in Progress')).toBeInTheDocument();
    // The max-time card is hidden while the run is live.
    expect(screen.queryByLabelText('Maximum search time', { selector: 'input' })).not.toBeInTheDocument();

    // Status is first read one poll interval after the start, not before.
    expect(statusCalls(mock)).toHaveLength(0);
  });

  it('converts the chosen unit into seconds for the request', async () => {
    const { mock } = await renderLoadedPage();

    fireEvent.change(screen.getByLabelText('Maximum search time', { selector: 'input' }), {
      target: { value: '2' },
    });
    fireEvent.change(screen.getByLabelText('Maximum search time', { selector: 'select' }), {
      target: { value: 'minutes' },
    });
    fireEvent.click(button('Run Allocation'));
    await advance();

    expect(startBody(mock).max_solver_seconds).toBe(120);
  });

  it('rejects an invalid maximum search time without starting a run', async () => {
    const { mock } = await renderLoadedPage();

    fireEvent.change(screen.getByLabelText('Maximum search time', { selector: 'input' }), {
      target: { value: '0' },
    });
    fireEvent.click(button('Run Allocation'));
    await advance();

    expect(screen.getByText('Enter a valid search time')).toBeInTheDocument();
    expect(startCalls(mock)).toHaveLength(0);
    expect(screen.getByText('Not Started')).toBeInTheDocument();

    // Over ten hours is rejected too; editing the value clears the message.
    fireEvent.change(screen.getByLabelText('Maximum search time', { selector: 'input' }), {
      target: { value: '11' },
    });
    expect(screen.queryByText('Enter a valid search time')).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Maximum search time', { selector: 'select' }), {
      target: { value: 'hours' },
    });
    fireEvent.click(button('Run Allocation'));
    await advance();
    expect(screen.getByText('Maximum search time is 10 hours')).toBeInTheDocument();
    expect(startCalls(mock)).toHaveLength(0);
  });

  it('reports a rejected start and returns to the idle state without polling', async () => {
    const { mock } = await startRun({
      mockApi: (m) => {
        mockAllocationApi(m);
        m.onPost('/api/allocation/start/').reply(409, {
          detail: 'An allocation run is already active for this region',
        });
      },
    });

    expect(
      screen.getByText('An allocation run is already active for this region')
    ).toBeInTheDocument();
    expect(button('Run Allocation')).toBeEnabled();
    expect(screen.getByText('Not Started')).toBeInTheDocument();
    expect(queryButton('Cancel Run')).toBeNull();

    await advance(STATUS_POLL_MS * 2);
    expect(statusCalls(mock)).toHaveLength(0);

    // The inline alert can be dismissed.
    fireEvent.click(screen.getByText('An allocation run is already active for this region').nextElementSibling as HTMLElement);
    expect(screen.queryByText('An allocation run is already active for this region')).not.toBeInTheDocument();
  });
});

describe('AllocationPage status polling', () => {
  it('follows the run from running to completed, then shows the reloaded result and stops polling', async () => {
    const { mock } = await startRun({
      mockApi: (m) => mockAllocationApi(m, {
        summary: SUMMARY_AFTER_RUN,
        before: (b) => {
          b.onGet('/api/allocation/summary/').replyOnce(200, SUMMARY_BEFORE_RUN);
          b.onGet(RUN_STATUS_URL)
            .replyOnce(200, { run: run('running', { elapsed_search_seconds: 3 }) })
            .onGet(RUN_STATUS_URL).replyOnce(200, {
              run: run('completed', { elapsed_search_seconds: 6, completed_at: '2026-10-07T10:00:00Z' }),
              successful_assignments: 38,
              roommate_matches: 5,
              conflicts: 2,
              solver_status: 'OPTIMAL',
              optimality_proven: true,
            });
        },
      }),
    });

    await pollOnce();
    expect(statusCalls(mock)).toHaveLength(1);
    expect(screen.getByText('Running')).toBeInTheDocument();
    expect(button('Running...')).toBeDisabled();

    await pollOnce();
    expect(await screen.findByText('Completed', undefined, { timeout: 3000 })).toBeInTheDocument();

    // Completion reloads the page summary; the assigned count shown is the
    // stored allocation, alongside the run's own match and conflict counts.
    expect(summaryCalls(mock)).toHaveLength(2);
    expect(screen.getByText('Successfully Assigned').parentElement).toHaveTextContent('38');
    expect(screen.getByText('Roommate Matches').parentElement).toHaveTextContent('5');
    expect(screen.getByText('Conflicts').parentElement).toHaveTextContent('2');
    expect(screen.getByText(/^Run time:/)).toHaveTextContent('Run time: 0:06');

    expect(button('Run Allocation')).toBeEnabled();
    expect(button('Delete Results')).toBeEnabled();
    expect(queryButton('Cancel Run')).toBeNull();
    expect(queryButton('Stop & Save Result')).toBeNull();
    expect(queryButton('View Current Result')).toBeNull();

    await advance(STATUS_POLL_MS * 3);
    expect(statusCalls(mock)).toHaveLength(2);
  });

  it('keeps polling through a failed status read', async () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    const { mock } = await startRun({
      mockApi: (m) => mockAllocationApi(m, {
        before: (b) => {
          b.onGet(RUN_STATUS_URL)
            .replyOnce(500, { detail: 'Failed to get run status' })
            .onGet(RUN_STATUS_URL).replyOnce(200, { run: run('running') });
        },
      }),
    });

    await pollOnce();
    expect(warn).toHaveBeenCalled();
    expect(screen.getByText('Queued')).toBeInTheDocument();
    expect(button('Running...')).toBeDisabled();

    await pollOnce();
    expect(statusCalls(mock)).toHaveLength(2);
    expect(screen.getByText('Running')).toBeInTheDocument();
  });

  it('surfaces a failed run, returns to idle and stops polling', async () => {
    const { mock } = await startRun({
      mockApi: (m) => mockAllocationApi(m, {
        before: (b) => {
          b.onGet(RUN_STATUS_URL).replyOnce(200, {
            run: run('failed', { error_message: 'Solver failed: no feasible assignment' }),
          });
        },
      }),
    });
    await pollOnce();

    expect(toast()).toHaveTextContent('Solver failed: no feasible assignment');
    expect(screen.getByText('Not Started')).toBeInTheDocument();
    expect(button('Run Allocation')).toBeEnabled();
    expect(queryButton('Cancel Run')).toBeNull();
    expect(summaryCalls(mock)).toHaveLength(2);

    await advance(STATUS_POLL_MS * 2);
    expect(statusCalls(mock)).toHaveLength(1);

    // The toast hides itself after 4.5 s.
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('resumes a run that is already active when the page opens', async () => {
    const { mock } = await renderLoadedPage({
      mockApi: (m) => mockAllocationApi(m, {
        activeRun: { run: run('running', { elapsed_search_seconds: 30 }) },
      }),
    });

    expect(screen.getByText('Running')).toBeInTheDocument();
    expect(button('Running...')).toBeDisabled();
    expect(button('Cancel Run')).toBeEnabled();
    expect(button('Stop & Save Result')).toBeEnabled();
    expect(startCalls(mock)).toHaveLength(0);
    // Elapsed time and the bar are anchored to the backend's figures.
    expect(screen.getByText('0:30')).toBeInTheDocument();
    expect(screen.getByText('6%')).toBeInTheDocument();

    await pollOnce();
    expect(statusCalls(mock)).toHaveLength(1);
  });

  it('resumes a cancellation already in progress and settles once the run has stopped', async () => {
    const { mock } = await renderLoadedPage({
      mockApi: (m) => mockAllocationApi(m, {
        activeRun: { run: run('cancellation_requested') },
        before: (b) => { b.onGet(RUN_STATUS_URL).replyOnce(200, { run: run('stopped') }); },
      }),
    });

    expect(screen.getByText('Stopping')).toBeInTheDocument();
    // The run button, the stopping chip and the progress card all say so.
    expect(screen.getByRole('button', { name: 'Cancelling...' })).toBeDisabled();
    expect(screen.getAllByText('Cancelling...')).toHaveLength(3);
    expect(queryButton('Cancel Run')).toBeNull();
    expect(queryButton('Stop & Save Result')).toBeNull();

    await pollOnce();
    expect(toast()).toHaveTextContent('Allocation stopped');
    expect(screen.getByText('Not Started')).toBeInTheDocument();
    expect(summaryCalls(mock)).toHaveLength(2);
  });

  it('restores the stored result of a completed run while its assignments still exist', async () => {
    const { mock } = await renderLoadedPage({
      mockApi: (m) => {
        mockAllocationApi(m, { summary: SUMMARY_AFTER_RUN, activeRun: { run: run('completed') } });
        m.onGet(RUN_STATUS_URL).reply(200, {
          run: run('completed', { elapsed_search_seconds: 9, completed_at: '2026-10-07T10:00:00Z' }),
          roommate_matches: 4,
          successful_assignments: 38,
        });
      },
    });

    expect(statusCalls(mock)).toHaveLength(1);
    expect(screen.getByText('Completed')).toBeInTheDocument();
    expect(screen.getByText('Successfully Assigned').parentElement).toHaveTextContent('38');
    expect(screen.getByText('Roommate Matches').parentElement).toHaveTextContent('4');
    // Conflicts are the summary's unassigned count for a restored result.
    expect(screen.getByText('Conflicts').parentElement).toHaveTextContent('2');
    expect(button('Delete Results')).toBeEnabled();

    // A stored result is not a live run: nothing is polled.
    await advance(STATUS_POLL_MS * 2);
    expect(statusCalls(mock)).toHaveLength(1);
  });

  it('ignores a completed run whose results were deleted', async () => {
    const { mock } = await renderLoadedPage({
      mockApi: (m) => mockAllocationApi(m, { activeRun: { run: run('completed') } }),
    });

    expect(screen.getByText('Not Started')).toBeInTheDocument();
    expect(statusCalls(mock)).toHaveLength(0);
    expect(queryButton('Delete Results')).toBeNull();
  });
});

describe('AllocationPage current-result preview', () => {
  it('shows the current best result while running and offers, but does not force, a newer one', async () => {
    const { mock } = await startRun({
      mockApi: (m) => {
        mockAllocationApi(m);
        m.onGet(PREVIEW_URL)
          .replyOnce(200, { available: true, snapshot: snapshot(1, ['Ada Lovelace']) })
          .onGet(PREVIEW_URL).reply(200, {
            available: true,
            snapshot: snapshot(2, ['Ada Lovelace', 'Grace Hopper']),
          });
      },
    });

    fireEvent.click(button('View Current Result'));
    await advance();

    expect(requests(mock, 'get', PREVIEW_URL)).toHaveLength(1);
    expect(within(dialog()).getByText('Temporary Result')).toBeInTheDocument();
    expect(within(dialog()).getByText('Ada Lovelace')).toBeInTheDocument();
    expect(within(dialog()).getByText('Feasible (not yet proven optimal)')).toBeInTheDocument();
    expect(within(dialog()).getByText('Assigned').parentElement).toHaveTextContent('1');
    expect(within(dialog()).getByText('Unassigned').parentElement).toHaveTextContent('39');

    // The open preview refreshes itself silently; a newer snapshot is only
    // announced, and what the user is reading is left in place.
    await advance(PREVIEW_POLL_MS);
    expect(requests(mock, 'get', PREVIEW_URL)).toHaveLength(2);
    expect(within(dialog()).getByText('A newer result is available')).toBeInTheDocument();
    expect(within(dialog()).queryByText('Grace Hopper')).not.toBeInTheDocument();

    fireEvent.click(within(dialog()).getByText('Refresh Result'));
    await advance();

    expect(within(dialog()).getByText('Grace Hopper')).toBeInTheDocument();
    expect(within(dialog()).queryByText('A newer result is available')).not.toBeInTheDocument();

    // Viewing the current result never stops the solver.
    expect(requests(mock, 'post', /\/stop/)).toHaveLength(0);
    expect(button('Running...')).toBeDisabled();

    fireEvent.click(within(dialog()).getByLabelText('Close'));
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    await advance(PREVIEW_POLL_MS);
    expect(requests(mock, 'get', PREVIEW_URL)).toHaveLength(3);
  });

  it('explains when no feasible result exists yet', async () => {
    await startRun({
      mockApi: (m) => {
        mockAllocationApi(m);
        m.onGet(PREVIEW_URL).reply(200, { available: false, snapshot: null });
      },
    });

    fireEvent.click(button('View Current Result'));
    await advance();

    expect(
      within(dialog()).getByText('No feasible solution found yet. Try again shortly.')
    ).toBeInTheDocument();
  });

  it('shows the preview error when the snapshot cannot be read', async () => {
    await startRun({
      mockApi: (m) => {
        mockAllocationApi(m);
        m.onGet(PREVIEW_URL).reply(500, { detail: 'preview unavailable' });
      },
    });

    fireEvent.click(button('View Current Result'));
    await advance();

    expect(within(dialog()).getByText('preview unavailable')).toBeInTheDocument();
  });
});

describe('AllocationPage cancel run', () => {
  it('asks for confirmation and sends nothing when the user backs out', async () => {
    const { mock } = await startRun();

    fireEvent.click(button('Cancel Run'));
    await advance();

    expect(within(dialog()).getByText('Cancel Allocation Run')).toBeInTheDocument();
    expect(within(dialog()).getByText(/this does not save a result/)).toBeInTheDocument();

    fireEvent.click(within(dialog()).getByText('Cancel'));
    await advance();

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(requests(mock, 'post', `/api/allocation/runs/${RUN_ID}/stop/`)).toHaveLength(0);
    expect(button('Cancel Run')).toBeEnabled();
  });

  it('requests cancellation, shows the stopping state, then returns to idle once stopped', async () => {
    const { mock } = await startRun({
      mockApi: (m) => mockAllocationApi(m, {
        before: (b) => { b.onGet(RUN_STATUS_URL).replyOnce(200, { run: run('stopped') }); },
      }),
    });

    fireEvent.click(button('Cancel Run'));
    await advance();
    await confirm();

    expect(requests(mock, 'post', `/api/allocation/runs/${RUN_ID}/stop/`)).toHaveLength(1);
    expect(requests(mock, 'post', `/api/allocation/runs/${RUN_ID}/stop-and-save/`)).toHaveLength(0);
    expect(toast()).toHaveTextContent(
      'Cancellation requested. The run will stop shortly and partial data will be deleted.'
    );
    expect(screen.getByText('Stopping')).toBeInTheDocument();
    expect(queryButton('Cancel Run')).toBeNull();
    expect(queryButton('Stop & Save Result')).toBeNull();

    await pollOnce();

    expect(toast()).toHaveTextContent('Allocation stopped');
    expect(screen.getByText('Not Started')).toBeInTheDocument();
    expect(button('Run Allocation')).toBeEnabled();
    expect(summaryCalls(mock)).toHaveLength(2);
  });

  it('reports a failed cancellation and offers the stop controls again', async () => {
    await startRun({
      mockApi: (m) => {
        mockAllocationApi(m);
        m.onPost(`/api/allocation/runs/${RUN_ID}/stop/`).reply(409, { detail: 'Run is no longer active' });
      },
    });

    fireEvent.click(button('Cancel Run'));
    await advance();
    await confirm();

    expect(toast()).toHaveTextContent('Run is no longer active');
    expect(screen.getByText('Queued')).toBeInTheDocument();
    expect(button('Cancel Run')).toBeEnabled();
    expect(button('Stop & Save Result')).toBeEnabled();
  });
});

describe('AllocationPage stop and save', () => {
  it('requests stop-and-save, shows the saving state, then the kept result on completion', async () => {
    const { mock } = await startRun({
      mockApi: (m) => mockAllocationApi(m, {
        summary: SUMMARY_AFTER_RUN,
        before: (b) => {
          b.onGet('/api/allocation/summary/').replyOnce(200, SUMMARY_BEFORE_RUN);
          b.onGet(RUN_STATUS_URL)
            .replyOnce(200, { run: run('stop_and_save_requested') })
            .onGet(RUN_STATUS_URL).replyOnce(200, {
              run: run('completed', { elapsed_search_seconds: 9 }),
              successful_assignments: 38,
              roommate_matches: 4,
              conflicts: 2,
              stopped_early_by_user: true,
            });
        },
      }),
    });

    fireEvent.click(button('Stop & Save Result'));
    await advance();

    expect(
      within(dialog()).getByText(
        'Stop searching and keep the best result found so far? It may not be the most optimal possible solution.'
      )
    ).toBeInTheDocument();

    await confirm();

    expect(requests(mock, 'post', `/api/allocation/runs/${RUN_ID}/stop-and-save/`)).toHaveLength(1);
    expect(requests(mock, 'post', `/api/allocation/runs/${RUN_ID}/stop/`)).toHaveLength(0);
    expect(toast()).toHaveTextContent(
      'Stop & Save requested. The best result found will be kept.'
    );
    expect(screen.getByText('Stopping & saving')).toBeInTheDocument();
    expect(queryButton('Cancel Run')).toBeNull();
    expect(queryButton('Stop & Save Result')).toBeNull();

    await pollOnce();
    expect(screen.getByText('Stopping & saving')).toBeInTheDocument();

    await pollOnce();
    expect(await screen.findByText('Completed', undefined, { timeout: 3000 })).toBeInTheDocument();
    expect(toast()).toHaveTextContent(
      'Stop & Save requested. The best result found will be kept.'
    );
    expect(screen.getByText('Successfully Assigned').parentElement).toHaveTextContent('38');
    expect(button('Delete Results')).toBeEnabled();
  });
});

describe('AllocationPage delete results', () => {
  async function renderWithStoredResult(options: ApiOptions = {}, extraMocks?: (mock: MockAdapter) => void) {
    return renderLoadedPage({
      mockApi: (m) => {
        mockAllocationApi(m, { summary: SUMMARY_AFTER_RUN, activeRun: { run: run('completed') }, ...options });
        m.onGet(RUN_STATUS_URL).reply(200, { run: run('completed'), roommate_matches: 4 });
        extraMocks?.(m);
      },
    });
  }

  it('asks for confirmation, deletes the run results and reloads the summary', async () => {
    // The stored result is shown first; after the deletion the summary
    // reports no assignments again.
    const { mock } = await renderWithStoredResult({
      summary: SUMMARY_BEFORE_RUN,
      before: (b) => { b.onGet('/api/allocation/summary/').replyOnce(200, SUMMARY_AFTER_RUN); },
    });

    fireEvent.click(button('Delete Results'));
    await advance();
    expect(within(dialog()).getByText('Delete Allocation Results')).toBeInTheDocument();

    await confirm();

    expect(requests(mock, 'delete', `/api/allocation/runs/${RUN_ID}/delete/`)).toHaveLength(1);
    expect(toast()).toHaveTextContent('Allocation results deleted successfully');
    expect(summaryCalls(mock)).toHaveLength(2);
    expect(screen.getByText('Not Started')).toBeInTheDocument();
    expect(queryButton('Delete Results')).toBeNull();
    expect(screen.getByText('Total Students').parentElement).toHaveTextContent('40');
  });

  it('refuses to delete an approved allocation', async () => {
    const { mock } = await renderWithStoredResult({}, (m) => {
      m.onDelete(`/api/allocation/runs/${RUN_ID}/delete/`).reply(409, { detail: 'Run was approved' });
    });

    fireEvent.click(button('Delete Results'));
    await advance();
    await confirm();

    expect(toast()).toHaveTextContent('Approved allocations cannot be deleted');
    expect(summaryCalls(mock)).toHaveLength(1);
    expect(screen.getByText('Completed')).toBeInTheDocument();
    expect(button('Delete Results')).toBeEnabled();
  });
});

describe('AllocationPage conditions', () => {
  it('toggles a flexible preference, adjusts its weight, persists the configuration and sends it with the run', async () => {
    const { mock } = await renderLoadedPage();

    // Critical constraints are locked; they have no switch.
    expect(screen.getAllByText('Hard Constraint')).toHaveLength(4);
    expect(screen.getAllByRole('switch')).toHaveLength(5);

    const religionSwitch = screen.getByRole('switch', { name: 'Same religion in apartment: Active' });
    expect(religionSwitch).toHaveAttribute('aria-checked', 'true');
    fireEvent.click(religionSwitch);

    const offSwitch = screen.getByRole('switch', { name: 'Same religion in apartment: Inactive' });
    expect(offSwitch).toHaveAttribute('aria-checked', 'false');
    // A disabled preference loses its importance slider.
    expect(screen.queryByLabelText('Importance: Same religion in apartment')).not.toBeInTheDocument();

    const roommateSlider = screen.getByLabelText('Importance: Match roommate requests');
    expect(roommateSlider).toHaveValue('8');
    fireEvent.change(roommateSlider, { target: { value: '9' } });
    expect(screen.getByText('9/10')).toBeInTheDocument();

    const stored = JSON.parse(localStorage.getItem('dormify_allocation_constraints') ?? '{}');
    expect(stored.sameReligion).toEqual({ enabled: false, strict: false, critical: false, weight: 6 });
    expect(stored.roommateMatch).toEqual({ enabled: true, strict: false, critical: false, weight: 9 });

    fireEvent.click(button('Run Allocation'));
    await advance();

    expect(startBody(mock).constraints).toEqual({
      ...DEFAULT_EFFECTIVE_CONSTRAINTS,
      sameReligion: { enabled: false, strict: false, critical: false, weight: 6 },
      roommateMatch: { enabled: true, strict: false, critical: false, weight: 9 },
    });
  });

  it('restores a saved configuration on load', async () => {
    localStorage.setItem('dormify_allocation_constraints', JSON.stringify({
      sectorMatching: { enabled: false, weight: 2 },
      sameGender: { enabled: false },
    }));

    const { mock } = await renderLoadedPage();

    expect(screen.getByRole('switch', { name: 'Sector matching: Inactive' })).toHaveAttribute('aria-checked', 'false');

    fireEvent.click(button('Run Allocation'));
    await advance();

    const constraints = startBody(mock).constraints as Record<string, unknown>;
    expect(constraints.sectorMatching).toEqual({ enabled: false, strict: false, critical: false, weight: 2 });
    // A critical constraint can never be switched off, whatever was stored.
    expect(constraints.sameGender).toEqual({ enabled: true, strict: true, critical: true, weight: 0 });
  });
});

describe('AllocationPage navigation', () => {
  function ResultsProbe(): React.ReactElement {
    const { state } = useLocation();
    return <pre data-testid="results-state">{JSON.stringify(state)}</pre>;
  }

  it('opens the results page with the summary, region and constraints in the router state', async () => {
    const { currentPath } = await renderLoadedPage({
      routes: { '/allocation/results': <ResultsProbe /> },
    });

    fireEvent.click(button('View Results'));

    expect(currentPath()).toBe('/allocation/results');
    const state = JSON.parse(screen.getByTestId('results-state').textContent ?? '{}');
    expect(state.result).toBeNull();
    expect(state.generatedAt).toBeNull();
    expect(state.region).toEqual(REGION);
    expect(state.summary.total_students).toBe(40);
    expect(state.constraints).toEqual(DEFAULT_EFFECTIVE_CONSTRAINTS);
  });
});
