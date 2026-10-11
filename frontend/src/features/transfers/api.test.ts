import { afterEach, describe, expect, it } from 'vitest';
import MockAdapter from 'axios-mock-adapter';
import { api } from '../../shared/api/client';
import { requestsAPI, transfersAPI } from './api';

const mock = new MockAdapter(api, { onNoMatch: 'throwException' });
afterEach(() => mock.reset());

describe('request review endpoints', () => {
  it('approves with the chosen target bed, or with an empty payload when none applies', async () => {
    mock.onPut('/api/requests/11/approve/').reply(200, { id: 11, status: 'approved' });
    mock.onPut('/api/requests/12/approve/').reply(200, { id: 12, status: 'approved' });

    await expect(
      requestsAPI.approve(11, { target_room: 501, bed_id: 9001 })
    ).resolves.toEqual({ id: 11, status: 'approved' });
    await requestsAPI.approve(12);

    expect(mock.history.put.map(({ url, data }) => [url, JSON.parse(data)])).toEqual([
      ['/api/requests/11/approve/', { target_room: 501, bed_id: 9001 }],
      ['/api/requests/12/approve/', {}],
    ]);
  });

  it('rejects with the typed reason', async () => {
    mock.onPut('/api/requests/11/reject/').reply(200, { id: 11, status: 'rejected' });

    await requestsAPI.reject(11, 'Student is staying another semester');

    expect(JSON.parse(mock.history.put[0].data)).toEqual({
      reason: 'Student is staying another semester',
    });
  });

  it('rejects with the backend explanation when a decision is refused', async () => {
    mock.onPut('/api/requests/11/approve/').reply(400, {
      detail: 'Student has no active assignment',
    });

    await expect(requestsAPI.approve(11)).rejects.toThrow('Student has no active assignment');
  });
});

describe('request list, feasibility and target regions', () => {
  it('lists requests with filters and returns the raw list shape', async () => {
    const page = { count: 1, next: null, previous: null, results: [{ id: 11, status: 'pending' }] };
    mock.onGet('/api/requests/').reply(200, page);

    await expect(requestsAPI.getAll({ status: 'pending' })).resolves.toEqual(page);
    expect(mock.history.get[0].params).toEqual({ status: 'pending' });
  });

  it('pages feasibility by building and forwards the abort signal', async () => {
    mock.onGet('/api/requests/11/feasibility/').reply(200, { feasible: true, buildings: [], has_more: false });
    const controller = new AbortController();

    await expect(requestsAPI.checkFeasibility(11, { limit: 5, offset: 10, signal: controller.signal })).resolves.toEqual({
      feasible: true, buildings: [], has_more: false,
    });
    expect(mock.history.get[0].params).toEqual({ limit: 5, offset: 10 });
    expect(mock.history.get[0].signal).toBe(controller.signal);
  });

  it('rethrows a cancelled feasibility check instead of converting it to a generic error', async () => {
    mock.onPost('/api/requests/match-options/').reply(() => new Promise(() => {}));
    const controller = new AbortController();

    const pending = requestsAPI.checkFeasibilityForStudent(2, 'room', null, { signal: controller.signal });
    controller.abort();

    await expect(pending).rejects.toMatchObject({ code: 'ERR_CANCELED' });
  });

  it('sends the transfer scope fields of a cross-region preview', async () => {
    mock.onPost('/api/requests/match-options/').reply(200, { feasible: false, reason: 'No beds' });

    await requestsAPI.checkFeasibilityForStudent(2, 'apartment', false, {
      transferScope: 'cross_region', regionIds: ['mizrah', 'broshim'], limit: 3,
    });

    expect(JSON.parse(mock.history.post[0].data)).toEqual({
      student_id: 2, request_type: 'apartment', same_apartment: false,
      transfer_scope: 'cross_region', region_ids: ['mizrah', 'broshim'], limit: 3, offset: 0,
    });
  });

  it('returns transfer target regions as a list whether paginated or not', async () => {
    mock.onGet('/api/requests/transfer-target-regions/').replyOnce(200, { results: [{ id: 'canada' }] });
    await expect(requestsAPI.getTransferTargetRegions()).resolves.toEqual([{ id: 'canada' }]);
    mock.onGet('/api/requests/transfer-target-regions/').replyOnce(200, [{ id: 'mizrah' }]);
    await expect(requestsAPI.getTransferTargetRegions()).resolves.toEqual([{ id: 'mizrah' }]);
  });
});

describe('legacy transfer endpoints', () => {
  it('lists, approves and rejects transfers with the typed reason', async () => {
    mock.onGet('/api/transfers/').reply(200, [{ id: 4, status: 'pending' }]);
    mock.onPut('/api/transfers/4/approve/').reply(200, { message: 'ok', transfer: { id: 4, status: 'approved' } });
    mock.onPut('/api/transfers/4/reject/').reply(200, { message: 'ok', transfer: { id: 4, status: 'rejected' } });

    await expect(transfersAPI.getAll()).resolves.toEqual([{ id: 4, status: 'pending' }]);
    await expect(transfersAPI.approve(4)).resolves.toMatchObject({ transfer: { status: 'approved' } });
    await transfersAPI.reject(4, 'Student is staying');

    expect(mock.history.put.map(({ url, data }) => [url, data === undefined ? undefined : JSON.parse(data)])).toEqual([
      ['/api/transfers/4/approve/', undefined],
      ['/api/transfers/4/reject/', { reason: 'Student is staying' }],
    ]);
  });

  it('rejects with the backend explanation when a transfer cannot be approved', async () => {
    mock.onPut('/api/transfers/4/approve/').reply(400, { error: 'Target bed is occupied' });
    await expect(transfersAPI.approve(4)).rejects.toThrow('error: Target bed is occupied');
  });
});
