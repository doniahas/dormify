import React from 'react';
import { describe, expect, it, vi } from 'vitest';
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type MockAdapter from 'axios-mock-adapter';

import type { Apartment, Bed, Building, DormType, Region, Room } from '../../shared/api/contracts';
import { createDeferred } from '../../shared/test/deferred';
import { renderWithProviders, type TestUser } from '../../shared/test/render';
import BuildingsPage from './BuildingsPage';
import type { BuildingSetupWizardProps } from './model';

// The page talks to the backend only through its typed adapters, which sit
// on the shared axios client; every reply below is registered on that
// client's mock adapter, so the request URLs, parameters and bodies
// asserted here are the ones the backend would receive.

// The setup wizard is replaced by the narrowest stand-in that still
// exercises the contract this page owns: it shows what it received and
// hands a created building back through onCompleted / onClose. What the
// real wizard renders internally is NOT covered here.
vi.mock('./BuildingSetupWizard', () => ({
  default: ({ regionName, defaultDormTypeId, dormTypesInRegion, onCompleted, onClose }: BuildingSetupWizardProps) => (
    <div>
      <span>
        {`wizard for ${regionName} default ${defaultDormTypeId || 'none'} types ${dormTypesInRegion.map((d) => d.id).join(',')}`}
      </span>
      <button type="button" onClick={() => onCompleted(NEW_BUILDING)}>wizard done</button>
      <button type="button" onClick={() => onClose()}>wizard cancel</button>
    </div>
  ),
}));

const centralAdmin: TestUser = {
  id: 1,
  email: 'admin@example.edu',
  role: 'central_admin',
  region: null,
  // UserSerializer omits region_name (no null) for a user without a region.
};

const regionBoss: TestUser = {
  id: 2,
  email: 'boss@example.edu',
  role: 'region_boss',
  region: 'canada',
  region_name: 'מעונות קנדה',
};

const employee: TestUser = {
  id: 3,
  email: 'employee@example.edu',
  role: 'employee',
  region: 'canada',
  region_name: 'מעונות קנדה',
};

const regions: Region[] = [
  { id: 'canada', name: 'מעונות קנדה' },
  { id: 'broshim', name: 'מעונות ברושים' },
];

const dormTypes: DormType[] = [
  { id: 2, code: 2, name: 'קנדה', region: 'canada', region_name: 'מעונות קנדה' },
  { id: 17, code: 17, name: 'ברושים', region: 'broshim', region_name: 'מעונות ברושים' },
];

const BUILDING_10: Building = {
  id: 1, number: 10, dorm_type: 2, dorm_type_name: 'קנדה', dorm_type_code: 2,
  region: 'canada', region_name: 'מעונות קנדה', is_active: true,
  gender_restriction: 'male', gender_restriction_display: 'בנים בלבד',
  apartment_count: 4, room_count: 8, bed_count: 16, occupied_beds: 9, free_beds: 7,
};

const BUILDING_11_INACTIVE: Building = {
  ...BUILDING_10, id: 2, number: 11, is_active: false, gender_restriction: '', gender_restriction_display: '',
  apartment_count: 2, room_count: 4, bed_count: 8, occupied_beds: 0, free_beds: 8,
};

const BUILDING_20_BROSHIM: Building = {
  ...BUILDING_10, id: 5, number: 20, dorm_type: 17, dorm_type_name: 'ברושים', dorm_type_code: 17,
  region: 'broshim', region_name: 'מעונות ברושים', gender_restriction: '', gender_restriction_display: '',
};

const NEW_BUILDING: Building = { ...BUILDING_10, id: 3, number: 12, apartment_count: 0, room_count: 0, bed_count: 0, occupied_beds: 0, free_beds: 0 };

const buildings: Building[] = [BUILDING_10, BUILDING_11_INACTIVE];

const APARTMENT_1: Apartment = {
  id: 1, building: 1, building_number: 10, number: '1', category: 'male', category_display: 'זכר',
  apartment_type: 'single', apartment_type_display: 'רווקים', room_count: 2, actual_room_count: 2,
  apartment_capacity: 4, bed_count: 4, occupied_beds: 1, free_beds: 3, is_active: true,
  inactive_reason: '', inactive_reason_display: '', region: 'canada', region_name: 'מעונות קנדה', dorm_type: 'קנדה',
};

const APARTMENT_2_INACTIVE: Apartment = {
  ...APARTMENT_1, id: 2, number: '2', category: 'mixed', apartment_type: 'couple', is_active: false,
  inactive_reason: 'maintenance', inactive_reason_display: 'תחזוקה', actual_room_count: 1,
};

const ROOM_A: Room = {
  id: 1, apartment: 1, apartment_number: '1', building_number: 10, region: 'canada', region_name: 'מעונות קנדה',
  name: 'A', number: 'A', capacity: 2, bed_count: 2, current_occupancy: 1, available_beds: 1,
  is_full: false, is_active: true, has_missing_bed_records: false,
};

const ROOM_B_MISMATCH: Room = { ...ROOM_A, id: 2, name: 'B', number: 'B', has_missing_bed_records: true };

const ROOM_C_APT2: Room = { ...ROOM_A, id: 3, apartment: 2, apartment_number: '2', name: 'C', number: 'C' };

const BED_A1: Bed = { id: 1, label: 'A-1', room: 1, room_name: 'A', apartment_number: '1', building_number: 10, is_occupied: true };
const BED_A2: Bed = { ...BED_A1, id: 2, label: 'A-2', is_occupied: false };

const IMPACT = { summary: { lost_apartments: 4, lost_rooms: 8, lost_beds: 16, affected_students_count: 9 } };

interface ApiOptions {
  apartments?: Apartment[];
  rooms?: Room[];
  beds?: Bed[];
}

function mockInventoryApi(mock: MockAdapter, {
  apartments = [APARTMENT_1, APARTMENT_2_INACTIVE],
  rooms = [ROOM_A, ROOM_B_MISMATCH, ROOM_C_APT2],
  beds = [BED_A1, BED_A2],
}: ApiOptions = {}) {
  mock.onGet('/api/regions/').reply(200, regions);
  mock.onGet('/api/dorm-types/').reply(200, { count: 2, next: null, previous: null, results: dormTypes });
  mock.onGet('/api/buildings/').reply(({ params }) => [200, params?.region === 'broshim' ? [BUILDING_20_BROSHIM] : buildings]);
  mock.onGet('/api/apartments/').reply(200, apartments);
  mock.onGet('/api/rooms/').reply(200, rooms);
  mock.onGet('/api/beds/').reply(200, beds);
  mock.onPost('/api/what-if/availability/simulate/').reply(200, IMPACT);
  mock.onPost('/api/what-if/availability/confirm/').reply(200, { success: true });
  mock.onPatch(/\/api\/buildings\/\d+\//).reply(200, BUILDING_10);
  mock.onPost('/api/apartments/').reply(201, { ...APARTMENT_1, id: 9 });
  mock.onPatch(/\/api\/apartments\/\d+\//).reply(200, APARTMENT_1);
  mock.onPost('/api/rooms/').reply(201, { ...ROOM_A, id: 9 });
  mock.onPatch(/\/api\/rooms\/\d+\//).reply(200, ROOM_A);
  mock.onPatch(/\/api\/beds\/\d+\//).reply(200, BED_A2);
}

interface RenderOptions {
  route?: string;
  language?: 'he' | 'en';
  user?: TestUser;
  mockApi?: (mock: MockAdapter) => void;
}

function renderBuildings({
  route = '/buildings', language = 'en', user = centralAdmin, mockApi = mockInventoryApi,
}: RenderOptions = {}) {
  return renderWithProviders(<BuildingsPage />, { route, language, user, mockApi });
}

// Renders and waits for the first building list to show.
async function renderLoadedPage(options?: RenderOptions, loaded: RegExp = /Building number 10/) {
  const utils = await renderBuildings(options);
  await screen.findByRole('button', { name: loaded }, { timeout: 3000 });
  return utils;
}

const requestsTo = (mock: MockAdapter, method: 'get' | 'post' | 'patch', url: string) =>
  mock.history[method].filter((r) => r.url === url);

const body = (request: { data?: string }) => JSON.parse(request.data ?? '{}');

const buildingButton = (number: number) => screen.getByRole('button', { name: new RegExp(`Building number ${number}`) });
// An accordion header's accessible name runs its inline children together
// ("Apartment number 1MaleSingle..."), so the lookups anchor on the prefix.
const apartmentHeader = (number: string) => screen.getByRole('button', { name: new RegExp(`^Apartment number ${number}(?!\\d)`) });
const roomHeader = (name: string) => screen.getByRole('button', { name: new RegExp(`^Room ${name}`) });

async function openBuilding(mock: MockAdapter, number = 10) {
  const user = userEvent.setup();
  await user.click(buildingButton(number));
  await waitFor(() => expect(requestsTo(mock, 'get', '/api/apartments/')).toHaveLength(1), { timeout: 3000 });
  await screen.findByText('Apartment number 1', undefined, { timeout: 3000 });
  return user;
}

describe('BuildingsPage smoke', () => {
  it('loads the catalog for the first region and lists its buildings', async () => {
    const { mock } = await renderBuildings({ user: { ...centralAdmin }, mockApi: (m) => {
      m.onGet('/api/regions/').reply(200, [regions[0]]);
      m.onGet('/api/dorm-types/').reply(200, { count: 1, next: null, previous: null, results: [dormTypes[0]] });
      m.onGet('/api/buildings/').reply(200, [BUILDING_10]);
    } });

    // The page shows only a spinner until the catalog and buildings arrive.
    expect(await screen.findByRole('heading', { level: 1 })).toHaveTextContent('Buildings & Dormitory Inventory');
    await screen.findByText(/Building number\s+10/);

    // The region resolved from the catalog drives the building query.
    const buildingRequests = mock.history.get.filter(({ url }) => url === '/api/buildings/');
    expect(buildingRequests).toHaveLength(1);
    expect(buildingRequests[0].params).toEqual({ region: 'canada', is_active: 'all' });
    // Breadcrumb and region selector both show the localized region name.
    expect(screen.getByDisplayValue('Canada Dormitories')).toBeInTheDocument();
    expect(screen.getAllByText('Canada Dormitories').length).toBeGreaterThan(1);
  });

  it('renders in Hebrew with the localized region name and empty state', async () => {
    await renderBuildings({ language: 'he', mockApi: (m) => {
      m.onGet('/api/regions/').reply(200, [regions[0]]);
      m.onGet('/api/dorm-types/').reply(200, { count: 1, next: null, previous: null, results: [dormTypes[0]] });
      m.onGet('/api/buildings/').reply(200, []);
    } });

    expect(await screen.findByRole('heading', { level: 1 })).toHaveTextContent('ניהול מבנים ומלאי מעונות');
    await screen.findByText('לא נמצאו בניינים');
    expect(screen.getAllByText('מעונות קנדה').length).toBeGreaterThan(0);
  });
});

describe('BuildingsPage loading and region scope', () => {
  it('shows only a busy spinner until the catalog arrives', async () => {
    const pending = createDeferred<Region[]>();
    await renderBuildings({
      mockApi: (m) => {
        mockInventoryApi(m);
        m.onGet('/api/regions/').reply(() => pending.promise.then((list) => [200, list]));
      },
    });

    expect(document.querySelector('[aria-busy="true"]')).not.toBeNull();
    expect(screen.queryByRole('heading', { level: 1 })).toBeNull();

    pending.resolve(regions);
    await screen.findByRole('heading', { level: 1 }, { timeout: 3000 });
    expect(document.querySelector('[aria-busy="true"]')).toBeNull();
  });

  it('switching region queries that region, resets the dorm type filter and the selection', async () => {
    const { mock } = await renderLoadedPage();
    const user = await openBuilding(mock);
    await user.selectOptions(screen.getByDisplayValue('All dorm types'), '2');
    expect(screen.getByDisplayValue('Canada (2)')).toBeInTheDocument();

    await user.selectOptions(screen.getByDisplayValue('Canada Dormitories'), 'broshim');

    await screen.findByRole('button', { name: /Building number 20/ }, { timeout: 3000 });
    const buildingRequests = requestsTo(mock, 'get', '/api/buildings/');
    expect(buildingRequests[buildingRequests.length - 1].params).toEqual({ region: 'broshim', is_active: 'all' });
    // The dorm type list now belongs to the new region and the filter is back to "all".
    expect(screen.getByDisplayValue('All dorm types')).toBeInTheDocument();
    expect(screen.getByRole('option', { name: 'Broshim (17)' })).toBeInTheDocument();
    expect(screen.queryByRole('option', { name: 'Canada (2)' })).toBeNull();
    // The previously selected building is gone from the structure panel.
    expect(screen.getByText('Select a building')).toBeInTheDocument();
    expect(screen.getAllByText('Broshim Dormitories').length).toBeGreaterThan(1);
  });

  it('a ?region=&building= deep link opens that region with the building pre-selected', async () => {
    const { mock } = await renderBuildings({ route: '/buildings?region=broshim&building=5&dormTypeId=17' });

    await screen.findByText('Apartment number 1', undefined, { timeout: 3000 });
    expect(requestsTo(mock, 'get', '/api/buildings/')[0].params).toEqual({ region: 'broshim', is_active: 'all' });
    expect(requestsTo(mock, 'get', '/api/apartments/')[0].params).toEqual({ building: '5', is_active: 'all' });
    expect(requestsTo(mock, 'get', '/api/rooms/')[0].params).toEqual({ building: '5', is_active: 'all' });
    expect(screen.getByDisplayValue('Broshim (17)')).toBeInTheDocument();
    expect(buildingButton(20)).toHaveAttribute('aria-pressed', 'true');
  });

  it('an employee stays in their own region, cannot switch it and only looks', async () => {
    const { mock } = await renderLoadedPage({ user: employee, route: '/buildings?region=broshim' });

    // The deep link to another region is ignored for a regional employee.
    expect(requestsTo(mock, 'get', '/api/buildings/')[0].params).toEqual({ region: 'canada', is_active: 'all' });
    expect(screen.getByDisplayValue('Canada Dormitories')).toBeDisabled();
    expect(screen.getByText('View-only')).toBeInTheDocument();
    expect(screen.queryAllByRole('button', { name: /Add building/ })).toHaveLength(0);

    await openBuilding(mock);
    expect(screen.queryByRole('button', { name: 'Edit' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Deactivate' })).toBeNull();
    expect(screen.queryByRole('button', { name: /Add apartment/ })).toBeNull();
  });

  it('a region boss manages inventory and may open another region', async () => {
    const { mock } = await renderLoadedPage({ user: regionBoss });

    expect(screen.queryByText('View-only')).toBeNull();
    // Both the header button and the navigator's icon button add a building.
    expect(screen.getAllByRole('button', { name: /Add building/ })).toHaveLength(2);
    expect(screen.getAllByRole('button', { name: /Add building/ })[0]).toBeEnabled();
    expect(screen.getByDisplayValue('Canada Dormitories')).toBeEnabled();

    await openBuilding(mock);
    expect(screen.getByRole('button', { name: 'Deactivate' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Add apartment/ })).toBeInTheDocument();
  });

  it('shows a dismissible page error when the buildings fail to load', async () => {
    await renderBuildings({
      mockApi: (m) => {
        mockInventoryApi(m);
        m.onGet('/api/buildings/').reply(500, { detail: 'inventory service unavailable' });
      },
    });

    await screen.findByText('inventory service unavailable', undefined, { timeout: 3000 });
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: 'close' }));
    expect(screen.queryByText('inventory service unavailable')).toBeNull();
    expect(screen.getByText('No buildings found')).toBeInTheDocument();
  });

  it('refresh re-reads the buildings and the selected building structure', async () => {
    const { mock } = await renderLoadedPage();
    const user = await openBuilding(mock);

    await user.click(screen.getByRole('button', { name: 'Refresh' }));

    await waitFor(() => expect(requestsTo(mock, 'get', '/api/buildings/')).toHaveLength(2), { timeout: 3000 });
    await waitFor(() => expect(requestsTo(mock, 'get', '/api/apartments/')).toHaveLength(2), { timeout: 3000 });
    expect(requestsTo(mock, 'get', '/api/apartments/')[1].params).toEqual({ building: 1, is_active: 'all' });
  });
});

describe('BuildingsPage filters and summary', () => {
  it('lists active buildings by default; the status filter reveals the inactive ones', async () => {
    await renderLoadedPage();
    const user = userEvent.setup();

    expect(screen.queryByRole('button', { name: /Building number 11/ })).toBeNull();
    expect(screen.getByText('Buildings (1)')).toBeInTheDocument();

    await user.selectOptions(screen.getByDisplayValue('Active'), 'all');
    expect(screen.getByRole('button', { name: /Building number 11/ })).toBeInTheDocument();
    expect(screen.getByText('Buildings (2)')).toBeInTheDocument();

    await user.selectOptions(screen.getByDisplayValue('All'), 'inactive');
    expect(screen.queryByRole('button', { name: /Building number 10/ })).toBeNull();
    expect(screen.getByRole('button', { name: /Building number 11/ })).toBeInTheDocument();
  });

  it('search narrows the navigator and can be cleared', async () => {
    await renderLoadedPage();
    const user = userEvent.setup();
    await user.selectOptions(screen.getByDisplayValue('Active'), 'all');

    await user.type(screen.getByPlaceholderText('Search building, apartment, or room...'), '11');
    expect(screen.queryByRole('button', { name: /Building number 10/ })).toBeNull();
    expect(screen.getByRole('button', { name: /Building number 11/ })).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'clear' }));
    expect(screen.getByRole('button', { name: /Building number 10/ })).toBeInTheDocument();
  });

  it('the summary strip counts every building of the scope but only active capacity', async () => {
    await renderLoadedPage();

    const metric = (label: string) => screen.getByText(label).previousSibling?.textContent;
    expect(metric('Buildings')).toBe('2');
    expect(metric('Apartments')).toBe('4');
    expect(metric('Rooms')).toBe('8');
    expect(metric('Beds')).toBe('16');
    expect(metric('Occupied beds')).toBe('9');
    expect(metric('Free beds')).toBe('7');
  });

  it('shows the building counters, status and gender restriction on each navigator item', async () => {
    await renderLoadedPage();
    const item = buildingButton(10);
    expect(within(item).getByText('4 apartments · 8 rooms · 16 beds')).toBeInTheDocument();
    expect(within(item).getByText('9 / 16 occupied')).toBeInTheDocument();
    expect(within(item).getByText('Active')).toBeInTheDocument();
    expect(within(item).getByText('Male only')).toBeInTheDocument();
  });
});

describe('BuildingsPage structure navigation', () => {
  it('selecting a building loads its apartments and rooms; selecting it again collapses it', async () => {
    const { mock } = await renderLoadedPage();
    const user = await openBuilding(mock);

    expect(requestsTo(mock, 'get', '/api/apartments/')[0].params).toEqual({ building: 1, is_active: 'all' });
    expect(requestsTo(mock, 'get', '/api/rooms/')[0].params).toEqual({ building: 1, is_active: 'all' });
    expect(buildingButton(10)).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByText('Apartments (2)')).toBeInTheDocument();
    const header = apartmentHeader('1');
    expect(within(header).getByText('Male')).toBeInTheDocument();
    expect(within(header).getByText('Single')).toBeInTheDocument();
    expect(within(header).getByText('2 rooms')).toBeInTheDocument();
    expect(within(header).getByText('1 / 4')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'View details' }));
    expect(screen.getByText('Canada Dormitories', { selector: 'strong' })).toBeInTheDocument();
    expect(screen.getByText('Hide details')).toBeInTheDocument();

    await user.click(buildingButton(10));
    expect(screen.getByText('Select a building')).toBeInTheDocument();
    expect(buildingButton(10)).toHaveAttribute('aria-pressed', 'false');
  });

  it('expanding an apartment shows its rooms; expanding a room fetches its beds', async () => {
    const { mock } = await renderLoadedPage();
    const user = await openBuilding(mock);

    await user.click(apartmentHeader('1'));
    expect(screen.getByText('Rooms (2)')).toBeInTheDocument();
    expect(roomHeader('A')).toBeInTheDocument();
    expect(roomHeader('B')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /^Room C/ })).toBeNull();
    expect(screen.getByTitle('There is a mismatch between room capacity and bed records in the database')).toBeInTheDocument();

    await user.click(roomHeader('A'));
    await screen.findByText('A-1', undefined, { timeout: 3000 });
    expect(requestsTo(mock, 'get', '/api/beds/')[0].params).toEqual({ room: 1 });
    expect(screen.getByText('Beds (2)')).toBeInTheDocument();
    const rows = screen.getAllByRole('row').slice(1);
    expect(within(rows[0]).getByText('Occupied')).toBeInTheDocument();
    expect(within(rows[1]).getByText('Available')).toBeInTheDocument();
    expect(screen.getByText(/only the bed label can be edited/)).toBeInTheDocument();
    // No per-bed add/delete controls: the adapter has no such operations.
    expect(screen.queryByRole('button', { name: /Add bed/ })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Delete' })).toBeNull();

    await user.click(rows[1]);
    expect(rows[1]).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByText('Bed A-2')).toBeInTheDocument();
  });

  it('an inactive apartment shows its inactive reason and an Activate action', async () => {
    const { mock } = await renderLoadedPage();
    const user = await openBuilding(mock);

    await user.click(apartmentHeader('2'));
    expect(screen.getByText('Inactive reason').nextSibling).toHaveTextContent('תחזוקה');
    expect(screen.getByRole('button', { name: 'Activate' })).toBeInTheDocument();
    // The only Deactivate left is the (active) building's own action.
    expect(screen.getAllByRole('button', { name: 'Deactivate' })).toHaveLength(1);
  });

  it('shows the empty states of a bare building, apartment and room', async () => {
    const { mock } = await renderLoadedPage({ mockApi: (m) => mockInventoryApi(m, { apartments: [APARTMENT_1], rooms: [ROOM_A], beds: [] }) });
    const user = await openBuilding(mock);

    await user.click(apartmentHeader('1'));
    await user.click(roomHeader('A'));
    await screen.findByText('No beds in this room', undefined, { timeout: 3000 });

    await user.selectOptions(screen.getByDisplayValue('Canada Dormitories'), 'broshim');
    await screen.findByRole('button', { name: /Building number 20/ }, { timeout: 3000 });
    m2(mock);
    await user.click(buildingButton(20));
    await screen.findByText('No apartments in this building', undefined, { timeout: 3000 });
  });
});

// The second building of the empty-state test has nothing under it.
function m2(mock: MockAdapter) {
  mock.onGet('/api/apartments/').reply(200, []);
  mock.onGet('/api/rooms/').reply(200, []);
}

describe('BuildingsPage editors', () => {
  it('edits a building: pre-filled form, PATCH payload, then a refresh of the scope', async () => {
    const { mock } = await renderLoadedPage();
    const user = await openBuilding(mock);

    // The building's own Edit comes first; the apartment rows carry theirs.
    await user.click(screen.getAllByRole('button', { name: 'Edit' })[0]);
    const dialog = screen.getByRole('dialog');
    expect(within(dialog).getByText('Edit building')).toBeInTheDocument();
    expect(within(dialog).getByText('Canada • Canada Dormitories')).toBeInTheDocument();
    expect(screen.getByLabelText('Building number')).toHaveValue(10);
    expect(screen.getByLabelText('Dorm type')).toHaveValue('2');
    expect(screen.getByLabelText('Gender restriction')).toHaveValue('male');
    expect(within(dialog).getByText('Availability is managed separately through the Activate / Deactivate action.')).toBeInTheDocument();

    await user.selectOptions(screen.getByLabelText('Gender restriction'), 'female');
    await user.click(screen.getByRole('button', { name: 'Save' }));

    await waitFor(() => expect(mock.history.patch).toHaveLength(1), { timeout: 3000 });
    expect(mock.history.patch[0].url).toBe('/api/buildings/1/');
    expect(body(mock.history.patch[0])).toEqual({ number: 10, dorm_type: 2, gender_restriction: 'female' });
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull(), { timeout: 3000 });
    await waitFor(() => expect(requestsTo(mock, 'get', '/api/buildings/')).toHaveLength(2), { timeout: 3000 });
    expect(requestsTo(mock, 'get', '/api/apartments/')).toHaveLength(2);
  });

  it('refuses to save a building without a number', async () => {
    const { mock } = await renderLoadedPage();
    const user = await openBuilding(mock);

    // The building's own Edit comes first; the apartment rows carry theirs.
    await user.click(screen.getAllByRole('button', { name: 'Edit' })[0]);
    await user.clear(screen.getByLabelText('Building number'));
    await user.click(screen.getByRole('button', { name: 'Save' }));

    expect(await screen.findByText('Building number is required')).toBeInTheDocument();
    expect(mock.history.patch).toHaveLength(0);
    expect(screen.getByRole('dialog')).toBeInTheDocument();
  });

  it('creates an apartment under the selected building with the exact payload', async () => {
    const { mock } = await renderLoadedPage();
    const user = await openBuilding(mock);

    await user.click(screen.getByRole('button', { name: /Add apartment/ }));
    const dialog = screen.getByRole('dialog');
    expect(within(dialog).getByText('New apartment')).toBeInTheDocument();
    // The context line and the read-only parent field both name the building.
    expect(within(dialog).getAllByText('Building number 10')).toHaveLength(2);

    await user.type(screen.getByLabelText('Apartment number'), '7');
    await user.selectOptions(screen.getByLabelText('Category (gender)'), 'female');
    await user.selectOptions(screen.getByLabelText('Housing type'), 'couple');
    await user.clear(screen.getByLabelText('Planned rooms'));
    await user.type(screen.getByLabelText('Planned rooms'), '3');
    await user.click(screen.getByRole('button', { name: 'Create' }));

    await waitFor(() => expect(requestsTo(mock, 'post', '/api/apartments/')).toHaveLength(1), { timeout: 3000 });
    expect(body(requestsTo(mock, 'post', '/api/apartments/')[0])).toEqual({
      number: '7',
      category: 'female',
      apartment_type: 'couple',
      room_count: 3,
      apartment_capacity: null,
      inactive_reason: '',
      building: 1,
    });
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull(), { timeout: 3000 });
    // The page then re-reads the scope (buildings + the building's structure).
    await waitFor(() => expect(requestsTo(mock, 'get', '/api/buildings/')).toHaveLength(2), { timeout: 3000 });
    await waitFor(() => expect(requestsTo(mock, 'get', '/api/apartments/').length).toBeGreaterThanOrEqual(2), { timeout: 3000 });
  });

  it('shows a structured rule violation from the backend inside the editor', async () => {
    const { mock } = await renderLoadedPage({
      mockApi: (m) => {
        mockInventoryApi(m);
        m.onPost('/api/apartments/').reply(400, {
          field: 'number', code: 'duplicate_number', message: 'Apartment number 1 already exists in building 10',
        });
      },
    });
    const user = await openBuilding(mock);

    await user.click(screen.getByRole('button', { name: /Add apartment/ }));
    await user.type(screen.getByLabelText('Apartment number'), '1');
    await user.click(screen.getByRole('button', { name: 'Create' }));

    expect(await screen.findByText('Apartment number 1 already exists in building 10', undefined, { timeout: 3000 })).toBeInTheDocument();
    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Create' })).toBeEnabled();
  });

  it('validates the apartment form before posting', async () => {
    const { mock } = await renderLoadedPage();
    const user = await openBuilding(mock);

    await user.click(screen.getByRole('button', { name: /Add apartment/ }));
    await user.click(screen.getByRole('button', { name: 'Create' }));
    expect(await screen.findByText('Apartment number is required')).toBeInTheDocument();

    await user.type(screen.getByLabelText('Apartment number'), '7');
    await user.type(screen.getByLabelText('Apartment capacity'), '-1');
    await user.click(screen.getByRole('button', { name: 'Create' }));
    expect(await screen.findByText('Enter a valid capacity')).toBeInTheDocument();
    expect(requestsTo(mock, 'post', '/api/apartments/')).toHaveLength(0);
  });

  it('creates a room under the open apartment and edits an existing one', async () => {
    const { mock } = await renderLoadedPage();
    const user = await openBuilding(mock);
    await user.click(apartmentHeader('1'));

    await user.click(screen.getByRole('button', { name: /Add room/ }));
    expect(within(screen.getByRole('dialog')).getByText('New room')).toBeInTheDocument();
    expect(within(screen.getByRole('dialog')).getByText('Apartment number 1 • Building number 10')).toBeInTheDocument();
    await user.type(screen.getByLabelText('Room name/number'), 'C');
    await user.clear(screen.getByLabelText('Capacity'));
    await user.type(screen.getByLabelText('Capacity'), '2');
    await user.click(screen.getByRole('button', { name: 'Create' }));

    await waitFor(() => expect(requestsTo(mock, 'post', '/api/rooms/')).toHaveLength(1), { timeout: 3000 });
    expect(body(requestsTo(mock, 'post', '/api/rooms/')[0])).toEqual({ name: 'C', capacity: 2, apartment: 1 });
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull(), { timeout: 3000 });

    await user.click(within(roomHeader('A')).getByRole('button', { name: 'Edit' }));
    expect(within(screen.getByRole('dialog')).getByText('Edit room')).toBeInTheDocument();
    expect(screen.getByLabelText('Room name/number')).toHaveValue('A');
    await user.clear(screen.getByLabelText('Capacity'));
    await user.type(screen.getByLabelText('Capacity'), '3');
    await user.click(screen.getByRole('button', { name: 'Save' }));

    await waitFor(() => expect(mock.history.patch).toHaveLength(1), { timeout: 3000 });
    expect(mock.history.patch[0].url).toBe('/api/rooms/1/');
    expect(body(mock.history.patch[0])).toEqual({ name: 'A', capacity: 3 });
  });

  it('refuses a room without a positive capacity', async () => {
    const { mock } = await renderLoadedPage();
    const user = await openBuilding(mock);
    await user.click(apartmentHeader('1'));
    await user.click(screen.getByRole('button', { name: /Add room/ }));
    await user.type(screen.getByLabelText('Room name/number'), 'C');
    await user.clear(screen.getByLabelText('Capacity'));
    await user.type(screen.getByLabelText('Capacity'), '0');
    await user.click(screen.getByRole('button', { name: 'Create' }));

    expect(await screen.findByText('Enter a valid positive capacity')).toBeInTheDocument();
    expect(requestsTo(mock, 'post', '/api/rooms/')).toHaveLength(0);
  });

  it('edits a bed label and re-reads the room beds', async () => {
    const { mock } = await renderLoadedPage();
    const user = await openBuilding(mock);
    await user.click(apartmentHeader('1'));
    await user.click(roomHeader('A'));
    await screen.findByText('A-2', undefined, { timeout: 3000 });

    const row = screen.getByText('A-2').closest('tr') as HTMLElement;
    await user.click(within(row).getByRole('button', { name: 'Edit' }));
    const dialog = screen.getByRole('dialog');
    expect(within(dialog).getByText('Edit bed')).toBeInTheDocument();
    expect(within(dialog).getByText('Room A • Apartment number 1 • Building number 10')).toBeInTheDocument();
    expect(within(dialog).getByText('Available')).toBeInTheDocument();
    await user.type(screen.getByLabelText('Bed label'), 'b');
    await user.click(screen.getByRole('button', { name: 'Save' }));

    await waitFor(() => expect(mock.history.patch).toHaveLength(1), { timeout: 3000 });
    expect(mock.history.patch[0].url).toBe('/api/beds/2/');
    expect(body(mock.history.patch[0])).toEqual({ label: 'A-2b' });
    await waitFor(() => expect(requestsTo(mock, 'get', '/api/beds/')).toHaveLength(2), { timeout: 3000 });
  });
});

describe('BuildingsPage availability workflow', () => {
  it('deactivating a building simulates the impact, requires a reason and sends the composed reason', async () => {
    const { mock } = await renderLoadedPage();
    const user = await openBuilding(mock);

    await user.click(screen.getByRole('button', { name: 'Deactivate' }));
    expect(screen.getByRole('heading', { name: 'Deactivate Building number 10' })).toBeInTheDocument();
    await screen.findByText('Affected apartments', undefined, { timeout: 3000 });
    expect(body(requestsTo(mock, 'post', '/api/what-if/availability/simulate/')[0])).toEqual({
      target_type: 'building', target_ids: [1], action: 'inactivate',
    });
    expect(screen.getByText('Affected apartments').nextSibling).toHaveTextContent('4');
    expect(screen.getByText('Students with an active assignment').nextSibling).toHaveTextContent('9');
    expect(screen.getByText(/Automatic allocation will stop using this inventory/)).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Confirm and proceed' }));
    expect(screen.getByText('A reason is required')).toBeInTheDocument();
    expect(requestsTo(mock, 'post', '/api/what-if/availability/confirm/')).toHaveLength(0);

    await user.selectOptions(screen.getByLabelText('Reason'), 'maintenance');
    await user.type(screen.getByLabelText('Additional note (optional)'), 'roof repair');
    await user.click(screen.getByRole('button', { name: 'Confirm and proceed' }));

    await waitFor(() => expect(requestsTo(mock, 'post', '/api/what-if/availability/confirm/')).toHaveLength(1), { timeout: 3000 });
    expect(body(requestsTo(mock, 'post', '/api/what-if/availability/confirm/')[0])).toEqual({
      target_type: 'building', target_ids: [1], action: 'inactivate', reason: 'Maintenance — roof repair',
    });
    await waitFor(() => expect(screen.queryByText('Deactivation impact')).toBeNull(), { timeout: 3000 });
    await waitFor(() => expect(requestsTo(mock, 'get', '/api/buildings/')).toHaveLength(2), { timeout: 3000 });
  });

  it('reactivating an apartment skips the simulation and sends the fixed reason', async () => {
    const { mock } = await renderLoadedPage();
    const user = await openBuilding(mock);
    await user.click(apartmentHeader('2'));

    await user.click(screen.getByRole('button', { name: /Activate/ }));
    expect(screen.getByRole('heading', { name: 'Activate Apartment number 2' })).toBeInTheDocument();
    expect(screen.getByText('Reactivate?')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Confirm and proceed' }));

    await waitFor(() => expect(requestsTo(mock, 'post', '/api/what-if/availability/confirm/')).toHaveLength(1), { timeout: 3000 });
    expect(requestsTo(mock, 'post', '/api/what-if/availability/simulate/')).toHaveLength(0);
    expect(body(requestsTo(mock, 'post', '/api/what-if/availability/confirm/')[0])).toEqual({
      target_type: 'apartment', target_ids: [2], action: 'reactivate', reason: 'Reactivated via inventory management',
    });
  });

  it('shows the confirm failure inside the dialog and keeps it open', async () => {
    const { mock } = await renderLoadedPage({
      mockApi: (m) => {
        mockInventoryApi(m);
        m.onPost('/api/what-if/availability/confirm/').reply(409, { error: 'students are still assigned' });
      },
    });
    const user = await openBuilding(mock);
    await user.click(apartmentHeader('1'));
    await user.click(roomHeader('A'));
    await screen.findByText('A-1', undefined, { timeout: 3000 });

    await user.click(screen.getAllByRole('button', { name: /Deactivate/ })[2]);
    expect(screen.getByRole('heading', { name: 'Deactivate Room name/number A' })).toBeInTheDocument();
    await screen.findByText('Affected rooms', undefined, { timeout: 3000 });
    await user.selectOptions(screen.getByLabelText('Reason'), 'other');
    await user.click(screen.getByRole('button', { name: 'Confirm and proceed' }));

    expect(await screen.findByText(/students are still assigned/, undefined, { timeout: 3000 })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Deactivate Room name/number A' })).toBeInTheDocument();
    expect(body(requestsTo(mock, 'post', '/api/what-if/availability/confirm/')[0])).toMatchObject({
      target_type: 'room', target_ids: [1], reason: 'Other',
    });
  });
});

describe('BuildingsPage setup wizard', () => {
  it('opens the wizard with the region context and selects the building it created', async () => {
    const { mock } = await renderLoadedPage();
    const user = userEvent.setup();
    await user.selectOptions(screen.getByDisplayValue('All dorm types'), '2');

    await user.click(screen.getAllByRole('button', { name: /Add building/ })[0]);
    expect(screen.getByText('wizard for Canada Dormitories default 2 types 2')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'wizard done' }));

    await waitFor(() => expect(requestsTo(mock, 'get', '/api/buildings/')).toHaveLength(2), { timeout: 3000 });
    await waitFor(() => expect(requestsTo(mock, 'get', '/api/apartments/')).toHaveLength(1), { timeout: 3000 });
    expect(requestsTo(mock, 'get', '/api/apartments/')[0].params).toEqual({ building: 3, is_active: 'all' });
    expect(screen.queryByText(/wizard for/)).toBeNull();
  });

  it('cancelling the wizard changes nothing', async () => {
    const { mock } = await renderLoadedPage();
    const user = userEvent.setup();
    await user.click(screen.getAllByRole('button', { name: /Add building/ })[0]);
    await user.click(screen.getByRole('button', { name: 'wizard cancel' }));

    expect(screen.queryByText(/wizard for/)).toBeNull();
    expect(requestsTo(mock, 'get', '/api/buildings/')).toHaveLength(1);
  });
});

describe('BuildingsPage in Hebrew', () => {
  it('renders the Hebrew labels right-to-left', async () => {
    const { mock } = await renderLoadedPage({ language: 'he' }, /מספר בניין 10/);

    expect(screen.getByRole('heading', { level: 1 }).closest('[dir]')).toHaveAttribute('dir', 'rtl');
    expect(screen.getAllByRole('button', { name: /הוסף בניין/ })).toHaveLength(2);
    expect(screen.getByText('מספר בניין 10')).toBeInTheDocument();
    expect(screen.getByDisplayValue('מעונות קנדה')).toBeInTheDocument();
    expect(screen.getByRole('option', { name: 'קנדה (2)' })).toBeInTheDocument();
    expect(screen.getByText('4 דירות · 8 חדרים · 16 מיטות')).toBeInTheDocument();
    expect(screen.getByText('בנים בלבד')).toBeInTheDocument();

    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: /מספר בניין 10/ }));
    await screen.findByText('מספר דירה 1', undefined, { timeout: 3000 });
    expect(requestsTo(mock, 'get', '/api/apartments/')[0].params).toEqual({ building: 1, is_active: 'all' });
    expect(screen.getByText('זכר')).toBeInTheDocument();
    expect(screen.getByText('רווקים/ות')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'השבת' })).toBeInTheDocument();
  });
});
