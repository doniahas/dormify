import React from 'react';
import { describe, expect, it, vi } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type MockAdapter from 'axios-mock-adapter';

import { renderWithProviders, type TestUser } from '../../shared/test/render';
import StudentsPage from './StudentsPage';

// Bed assignment and reassignment ("move") are reached from a student's
// detail view on this page; the inventory (Buildings) page edits buildings,
// apartments, rooms and beds but does not place students.

vi.mock('./FiltersDrawer', () => ({ default: () => null }));

// The bed picker is replaced by the narrowest stand-in that still exercises
// the contract this page owns: it receives the buildings the page loaded and
// hands back a selection built by the picker's real selection helper. What
// the real picker renders internally is NOT covered here.
vi.mock('../allocation/BedMatchPicker', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../allocation/BedMatchPicker')>();

  type Bed = { bed_id: number; bed_label: string };
  type Room = { room_name: string; beds: Bed[] };
  type Apartment = { rooms: Room[] };
  type Building = { apartments: Apartment[] };

  return {
    ...actual,
    default: ({ buildings, onSelectBed, onLoadMore, hasMore }: {
      buildings: Building[];
      onSelectBed: (selection: unknown) => void;
      onLoadMore: () => void;
      hasMore: boolean;
    }) => (
      <div>
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

const centralAdmin: TestUser = {
  id: 9,
  email: 'staff@example.edu',
  role: 'central_admin',
  region: 'canada',
  region_name: 'מעונות קנדה',
};

const GRACE = {
  id: 2,
  student_id: '200400500',
  first_name: 'Grace',
  last_name: 'Hopper',
  category: 'continuing',
  region_id: 'canada',
  is_assigned: false,
};

const ADA = {
  id: 1,
  student_id: '200100300',
  first_name: 'Ada',
  last_name: 'Lovelace',
  category: 'new',
  region_id: 'canada',
  is_assigned: true,
  assigned_building_number: 105,
  assigned_apartment_number: 3,
  assigned_room_name: 'B',
  current_bed_label: 'bed 2',
};

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

const AVAILABLE_BEDS = {
  buildings: [building(110, 9001)],
  total_valid_beds: 1,
  total_buildings: 1,
  total_apartments: 1,
  total_rooms: 1,
  has_more: false,
};

const FILTER_OPTIONS = {
  is_central_admin: true,
  regions: [
    { id: 'canada', name: 'מעונות קנדה' },
    { id: 'broshim', name: 'ברושים' },
  ],
  buildings: [], dorm_types: [], apartments: [], rooms: [], religions: [], housing_types: [],
};

// The modal's own copy is Hebrew regardless of the page language.
const MODAL_TITLE_ASSIGN = 'שיבוץ מיטה';
const MODAL_TITLE_REASSIGN = 'שיבוץ מיטה מחדש';
const SUBMIT_WITHOUT_SELECTION = 'בחר מיטה תחילה';

const UI_TIMEOUT = { timeout: 3000 };

const button = (label: string) => screen.getByText(label).closest('button')!;

function mockApi(mock: MockAdapter) {
  mock.onGet('/api/students/counts/').reply(200, { all: 2, unassigned: 1 });
  mock.onGet('/api/students/filter-options/').reply(200, FILTER_OPTIONS);
  mock.onGet('/api/regions/').reply(200, FILTER_OPTIONS.regions);
  mock.onGet('/api/students/').reply(200, { count: 2, next: null, previous: null, results: [GRACE, ADA] });
  mock.onGet('/api/students/1/').reply(200, ADA);
  mock.onGet('/api/students/2/').reply(200, GRACE);
  mock.onGet('/api/requests/').reply(200, []);
  mock.onPost('/api/requests/match-options/').reply(200, AVAILABLE_BEDS);
}

async function renderLoadedPage(extraMocks?: (mock: MockAdapter) => void) {
  const user = userEvent.setup();
  const utils = await renderWithProviders(<StudentsPage />, {
    route: '/students',
    language: 'en',
    user: centralAdmin,
    mockApi: (mock) => {
      mockApi(mock);
      extraMocks?.(mock);
    },
  });
  await screen.findByText('Grace Hopper', undefined, UI_TIMEOUT);
  return { ...utils, user };
}

const matchRequests = (mock: MockAdapter) =>
  mock.history.post.filter(({ url }) => url === '/api/requests/match-options/');

// Opens the student's detail view and then the bed modal from it, returning
// the modal's submit control (located while it still asks for a selection).
async function openBedModal(
  user: ReturnType<typeof userEvent.setup>,
  { name, action, title }: { name: string; action: string; title: string }
) {
  await user.click(screen.getByText(name));
  await user.click(await screen.findByText(action, undefined, UI_TIMEOUT));
  await screen.findByText(title, { selector: 'h3' }, UI_TIMEOUT);

  const submit = button(SUBMIT_WITHOUT_SELECTION);
  expect(submit).toBeDisabled();

  return submit;
}

describe('StudentsPage bed assignment', () => {
  it('assigns an unassigned student to the selected bed, then refreshes the student', async () => {
    const { user, mock } = await renderLoadedPage((m) => {
      m.onPost('/api/room-assignments/assign/').reply(200, { success: true });
    });
    const submit = await openBedModal(user, {
      name: 'Grace Hopper',
      action: 'Assign Bed',
      title: MODAL_TITLE_ASSIGN,
    });

    // The search starts from the first building page in the student's own region.
    expect(JSON.parse(matchRequests(mock)[0].data)).toEqual({
      student_id: GRACE.id, same_apartment: null, limit: 10, offset: 0,
    });

    await user.click(screen.getByText('pick bed 1 in room A'));
    expect(submit).toBeEnabled();
    expect(submit).toHaveTextContent('שבץ למיטה 1 בחדר A, דירה 7, בניין 110');

    await user.click(submit);

    const assign = mock.history.post.filter(({ url }) => url === '/api/room-assignments/assign/');
    expect(assign).toHaveLength(1);
    expect(JSON.parse(assign[0].data)).toEqual({ student_id: GRACE.id, room_id: 610, bed_id: 9001 });
    expect(mock.history.post.filter(({ url }) => url === '/api/room-assignments/move/')).toHaveLength(0);
    expect(
      await screen.findByText('Student assigned successfully!', undefined, UI_TIMEOUT)
    ).toBeInTheDocument();
    expect(submit).toBeDisabled();

    // After the confirmation is shown the modal closes on its own and the
    // student and the page counts are read again from the backend.
    const getByIdCalls = mock.history.get.filter(({ url }) => url === '/api/students/2/').length;
    const countCalls = mock.history.get.filter(({ url }) => url === '/api/students/counts/').length;
    await waitFor(
      () => expect(screen.queryByText(MODAL_TITLE_ASSIGN, { selector: 'h3' })).not.toBeInTheDocument(),
      UI_TIMEOUT
    );
    await waitFor(
      () => expect(mock.history.get.filter(({ url }) => url === '/api/students/2/')).toHaveLength(getByIdCalls + 1),
      UI_TIMEOUT
    );
    await waitFor(
      () => expect(mock.history.get.filter(({ url }) => url === '/api/students/counts/')).toHaveLength(countCalls + 1),
      UI_TIMEOUT
    );
  }, 15000);

  it('moves an assigned student to the selected bed through reassignment', async () => {
    const { user, mock } = await renderLoadedPage((m) => {
      m.onPost('/api/room-assignments/move/').reply(200, { success: true });
    });
    const submit = await openBedModal(user, {
      name: 'Ada Lovelace',
      action: 'Reassign Bed',
      title: MODAL_TITLE_REASSIGN,
    });

    // The current placement is shown and kept until the move succeeds.
    expect(
      screen.getByText('שיבוץ נוכחי: בניין 105 → דירה 3 → חדר B → מיטה bed 2')
    ).toBeInTheDocument();

    await user.click(screen.getByText('pick bed 1 in room A'));
    expect(submit).toHaveTextContent('שבץ מחדש למיטה 1 בחדר A, דירה 7, בניין 110');

    await user.click(submit);

    const move = mock.history.post.filter(({ url }) => url === '/api/room-assignments/move/');
    expect(move).toHaveLength(1);
    expect(JSON.parse(move[0].data)).toEqual({ student_id: ADA.id, room_id: 610, bed_id: 9001 });
    expect(mock.history.post.filter(({ url }) => url === '/api/room-assignments/assign/')).toHaveLength(0);
    expect(
      await screen.findByText('Student assigned successfully!', undefined, UI_TIMEOUT)
    ).toBeInTheDocument();
  }, 15000);

  it('keeps the modal open with the error when the assignment is refused', async () => {
    const { user } = await renderLoadedPage((m) => {
      m.onPost('/api/room-assignments/assign/').reply(400, { detail: 'Bed 9001 is already occupied' });
    });
    const submit = await openBedModal(user, {
      name: 'Grace Hopper',
      action: 'Assign Bed',
      title: MODAL_TITLE_ASSIGN,
    });

    await user.click(screen.getByText('pick bed 1 in room A'));
    await user.click(submit);

    expect(
      await screen.findByText('Bed 9001 is already occupied', undefined, UI_TIMEOUT)
    ).toBeInTheDocument();
    expect(screen.queryByText('Student assigned successfully!')).not.toBeInTheDocument();
    expect(screen.getByText(MODAL_TITLE_ASSIGN, { selector: 'h3' })).toBeInTheDocument();
    await waitFor(() => expect(submit).toBeEnabled(), UI_TIMEOUT);
  }, 15000);

  it('lets a central admin search another region and appends further buildings', async () => {
    const { user, mock } = await renderLoadedPage((m) => {
      m.onPost('/api/requests/match-options/').reply(({ data }) => {
        const body = JSON.parse(data);
        if (body.region_id === 'broshim') {
          return [200, { ...AVAILABLE_BEDS, has_more: body.offset === 0, buildings: [building(body.offset === 0 ? 210 : 220, body.offset === 0 ? 9003 : 9004)] }];
        }
        return [200, AVAILABLE_BEDS];
      });
    });
    await openBedModal(user, { name: 'Grace Hopper', action: 'Assign Bed', title: MODAL_TITLE_ASSIGN });
    expect(screen.getByText('pick bed 1 in room A')).toBeInTheDocument();

    const regionSelect = screen.getByDisplayValue(/Canada Dormitories/);
    await user.selectOptions(regionSelect, 'broshim');

    expect(await screen.findByText('pick bed 3 in room A', undefined, UI_TIMEOUT)).toBeInTheDocument();
    expect(screen.queryByText('pick bed 1 in room A')).not.toBeInTheDocument();
    expect(JSON.parse(matchRequests(mock)[1].data)).toMatchObject({ student_id: GRACE.id, region_id: 'broshim', offset: 0 });

    // "Load more" asks for the next building page in the same region and
    // keeps what is already shown.
    await user.click(screen.getByText('load more buildings'));
    expect(await screen.findByText('pick bed 4 in room A', undefined, UI_TIMEOUT)).toBeInTheDocument();
    expect(screen.getByText('pick bed 3 in room A')).toBeInTheDocument();
    expect(JSON.parse(matchRequests(mock)[2].data)).toMatchObject({ region_id: 'broshim', offset: 1 });
  }, 15000);

  it('shows one blocking message with an edit shortcut when the student record is incomplete', async () => {
    const { user } = await renderLoadedPage((m) => {
      m.onPost('/api/requests/match-options/').reply(200, {
        feasible: false,
        blocking_field: 'housing_type',
        reason: 'Student has no housing type',
        buildings: [],
      });
    });
    await openBedModal(user, { name: 'Grace Hopper', action: 'Assign Bed', title: MODAL_TITLE_ASSIGN });

    expect(await screen.findByText('Assignment blocked', undefined, UI_TIMEOUT)).toBeInTheDocument();
    expect(screen.getByText('Student has no housing type')).toBeInTheDocument();

    // The shortcut (the modal's own button, not the hero's) swaps the bed
    // modal for the student form.
    const shortcuts = screen.getAllByRole('button', { name: /Edit Student Details/ });
    await user.click(shortcuts[shortcuts.length - 1]);
    expect(await screen.findByRole('heading', { name: 'Edit Student' })).toBeInTheDocument();
    expect(screen.queryByText(MODAL_TITLE_ASSIGN, { selector: 'h3' })).not.toBeInTheDocument();
  }, 15000);
});
