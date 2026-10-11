import { afterEach, describe, expect, it } from 'vitest';
import MockAdapter from 'axios-mock-adapter';
import { api, type ApiError } from '../../shared/api/client';
import { dormInventoryAPI, getAllInventoryPages, getInventoryCatalog, regionsAPI } from './api';

const mock = new MockAdapter(api);
afterEach(() => mock.reset());

it('keeps catalog response shapes for the inventory page to normalize', async () => {
  mock.onGet('/api/regions/').reply(200, { results: [{ id: 1 }] });
  mock.onGet('/api/dorm-types/').reply(200, [{ id: 2 }]);
  await expect(getInventoryCatalog()).resolves.toEqual({
    regions: { results: [{ id: 1 }] }, dormTypes: [{ id: 2 }],
  });
});

it('loads every inventory page through the shared client using continuation path and query', async () => {
  mock.onGet('/api/buildings/').reply(200, {
    results: [{ id: 1 }], next: 'https://example.test/api/buildings/?page=2',
  });
  mock.onGet('/api/buildings/?page=2').reply(200, { results: [{ id: 2 }], next: null });
  await expect(getAllInventoryPages('/api/buildings/')).resolves.toEqual([{ id: 1 }, { id: 2 }]);
  expect(mock.history.get.map(({ url }) => url)).toEqual(['/api/buildings/', '/api/buildings/?page=2']);
});

it('preserves complete unpaginated inventory responses', async () => {
  mock.onGet('/api/rooms/').reply(200, [{ id: 3 }]);
  await expect(getAllInventoryPages('/api/rooms/')).resolves.toEqual([{ id: 3 }]);
});

it('propagates catalog and pagination failures to their owning pages', async () => {
  mock.onGet('/api/regions/').reply(503);
  mock.onGet('/api/dorm-types/').reply(200, []);
  await expect(getInventoryCatalog()).rejects.toMatchObject({ response: { status: 503 } });
  mock.onGet('/api/apartments/').reply(503);
  await expect(getAllInventoryPages('/api/apartments/')).rejects.toMatchObject({ response: { status: 503 } });
});

describe('dormitory structure endpoints', () => {
  it('passes list filters through and returns the raw list shape for the page to normalize', async () => {
    mock.onGet('/api/buildings/').reply(200, { count: 1, next: null, previous: null, results: [{ id: 1, number: 10 }] });
    mock.onGet('/api/rooms/').reply(200, [{ id: 3, name: '3A' }]);

    await expect(dormInventoryAPI.getBuildings({ region: 'canada', is_active: 'all' })).resolves.toEqual({
      count: 1, next: null, previous: null, results: [{ id: 1, number: 10 }],
    });
    await expect(dormInventoryAPI.getRooms({ building: 1 })).resolves.toEqual([{ id: 3, name: '3A' }]);
    expect(mock.history.get.map(({ params }) => params)).toEqual([{ region: 'canada', is_active: 'all' }, { building: 1 }]);
  });

  it('creates and updates entities through their endpoints', async () => {
    mock.onPost('/api/apartments/').reply(201, { id: 20, number: '4' });
    mock.onPatch('/api/beds/9/').reply(200, { id: 9, label: 'B' });

    await expect(dormInventoryAPI.createApartment({ building: 1, number: '4', category: 'mixed' })).resolves.toEqual({ id: 20, number: '4' });
    await expect(dormInventoryAPI.updateBed(9, { label: 'B' })).resolves.toEqual({ id: 9, label: 'B' });
    expect(JSON.parse(mock.history.post[0].data)).toEqual({ building: 1, number: '4', category: 'mixed' });
    expect(JSON.parse(mock.history.patch[0].data)).toEqual({ label: 'B' });
  });

  it('keeps structured rule violations as fieldErrors on the thrown error', async () => {
    mock.onPatch('/api/rooms/3/').reply(400, {
      field: 'capacity', code: 'occupied', message: 'Room has 2 occupants',
    });

    const refused: ApiError = await dormInventoryAPI.updateRoom(3, { capacity: 1 }).catch((err) => err);

    expect(refused.message).toBe('field: capacity; code: occupied; message: Room has 2 occupants');
    expect(refused.status).toBe(400);
    expect(refused.fieldErrors).toEqual({ field: 'capacity', code: 'occupied', message: 'Room has 2 occupants' });
  });
});

it('returns regions as a list whether the view paginated them or not', async () => {
  mock.onGet('/api/regions/').replyOnce(200, { results: [{ id: 'canada', name: 'מעונות קנדה' }] });
  await expect(regionsAPI.getAll()).resolves.toEqual([{ id: 'canada', name: 'מעונות קנדה' }]);

  mock.onGet('/api/regions/').replyOnce(200, [{ id: 'mizrah', name: 'מעונות מזרח' }]);
  await expect(regionsAPI.getAll()).resolves.toEqual([{ id: 'mizrah', name: 'מעונות מזרח' }]);

  mock.onGet('/api/regions/').replyOnce(503, { detail: 'Unavailable' });
  await expect(regionsAPI.getAll()).rejects.toThrow('Unavailable');
});

describe('bulk inventory creation contract', () => {
  it('sends apartment_groups as the wizard builds them and returns the created counts', async () => {
    const payload = {
      apartment_groups: [{ category: 'male', apartment_type: 'single', apartment_capacity: 2, numbers: ['11', '12'], room_groups: [{ capacity: 2, count: 1 }] }],
    };
    const created = { success: true, building_id: 3, created_apartments: 2, created_rooms: 2, created_beds: 4 };
    mock.onPost('/api/buildings/3/bulk-create-inventory/').reply(201, created);

    await expect(dormInventoryAPI.bulkCreateInventory(3, payload)).resolves.toEqual(created);
    expect(JSON.parse(mock.history.post[0].data)).toEqual(payload);
  });
});
