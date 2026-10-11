import { afterEach, describe, expect, it, vi } from 'vitest';
import MockAdapter from 'axios-mock-adapter';
import { api, type ApiError } from '../../shared/api/client';
import { allocationAPI, assistedAllocationAPI, inboxAPI } from './api';

const mock = new MockAdapter(api, { onNoMatch: 'throwException' });
afterEach(() => mock.reset());

describe('allocation run lifecycle endpoints', () => {
  it('starts a run with the region merged into the run options', async () => {
    const started = { run_id: 41, run: { id: 41, status: 'queued' } };
    mock.onPost('/api/allocation/start/').reply(201, started);

    await expect(
      allocationAPI.startRun(3, { constraints: { sameGender: { enabled: true } }, max_solver_seconds: 500 })
    ).resolves.toEqual(started);

    expect(JSON.parse(mock.history.post[0].data)).toEqual({
      region: 3,
      constraints: { sameGender: { enabled: true } },
      max_solver_seconds: 500,
    });
  });

  it('reads run status, the current-result preview and the active run of a region', async () => {
    mock.onGet('/api/allocation/runs/41/').reply(200, { run: { id: 41, status: 'running' } });
    mock.onGet('/api/allocation/runs/41/preview/').reply(200, { available: false, snapshot: null });
    mock.onGet('/api/allocation/runs/active/?region=3').reply(200, { run: null });

    await expect(allocationAPI.getRunStatus(41)).resolves.toEqual({ run: { id: 41, status: 'running' } });
    await expect(allocationAPI.getPreview(41)).resolves.toEqual({ available: false, snapshot: null });
    await expect(allocationAPI.getActiveRun(3)).resolves.toEqual({ run: null });
  });

  it('sends cancel and stop-and-save to their distinct endpoints', async () => {
    mock.onPost('/api/allocation/runs/41/stop/').reply(200, {});
    mock.onPost('/api/allocation/runs/41/stop-and-save/').reply(200, {});

    await allocationAPI.stopRun(41);
    await allocationAPI.stopAndSave(41);

    expect(mock.history.post.map(({ url }) => url)).toEqual([
      '/api/allocation/runs/41/stop/',
      '/api/allocation/runs/41/stop-and-save/',
    ]);
  });

  it('rejects with the backend explanation when a run cannot start', async () => {
    mock.onPost('/api/allocation/start/').reply(409, {
      detail: 'An allocation run is already active for this region',
    });

    await expect(allocationAPI.startRun(3)).rejects.toThrow(
      'An allocation run is already active for this region'
    );
  });
});

describe('inbox endpoints', () => {
  it('reads the latest inbox item and marks it viewed or processed by id', async () => {
    const inbox = { id: 5, status: 'pending', students_count: 12 };
    mock.onGet('/api/inbox/latest/').reply(200, { inbox });
    mock.onPut('/api/inbox/5/viewed/').reply(200, { inbox: { ...inbox, status: 'viewed' } });
    mock.onPut('/api/inbox/5/processed/').reply(200, { inbox: { ...inbox, status: 'processed' } });

    await expect(inboxAPI.getLatest()).resolves.toEqual({ inbox });
    await expect(inboxAPI.markViewed(5)).resolves.toEqual({ inbox: { ...inbox, status: 'viewed' } });
    await expect(inboxAPI.markProcessed(5)).resolves.toEqual({ inbox: { ...inbox, status: 'processed' } });
    expect(mock.history.put.map(({ url }) => url)).toEqual(['/api/inbox/5/viewed/', '/api/inbox/5/processed/']);
  });

  it('swallows a failed viewed-marker but reports a failed processed-marker', async () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    mock.onPut('/api/inbox/5/viewed/').reply(500);
    mock.onPut('/api/inbox/5/processed/').reply(409, { detail: 'Already processed' });

    await expect(inboxAPI.markViewed(5)).resolves.toBeNull();
    await expect(inboxAPI.markProcessed(5)).rejects.toThrow('Already processed');
    expect(warn).toHaveBeenCalledTimes(2);
  });
});

describe('assisted allocation endpoints', () => {
  it('reads the queue, detail and recommendations with their query parameters', async () => {
    mock.onGet('/api/assisted-allocation/queue/').reply(200, { students: [{ id: 1 }], counts: { unassigned: 1 } });
    mock.onGet('/api/assisted-allocation/students/1/detail/').reply(200, { student: { id: 1 } });
    mock.onGet('/api/assisted-allocation/students/1/recommendations/').reply(200, { candidates: [] });
    mock.onGet('/api/assisted-allocation/students/1/override-check/').reply(200, { requires_override: true, violations: ['gender'] });

    await expect(assistedAllocationAPI.getQueue({ region: 'canada', tab: 'unassigned' })).resolves.toEqual({
      students: [{ id: 1 }], counts: { unassigned: 1 },
    });
    await expect(assistedAllocationAPI.getStudentDetail(1)).resolves.toEqual({ student: { id: 1 } });
    await expect(assistedAllocationAPI.getRecommendations(1, { limit: 5 })).resolves.toEqual({ candidates: [] });
    await expect(assistedAllocationAPI.checkOverride(1, 9001)).resolves.toEqual({ requires_override: true, violations: ['gender'] });

    expect(mock.history.get.map(({ params }) => params)).toEqual([
      { region: 'canada', tab: 'unassigned' }, undefined, { limit: 5 }, { bed_id: 9001 },
    ]);
  });

  it('assigns and overrides through their endpoints and keeps structured errors as fieldErrors', async () => {
    mock.onPost('/api/assisted-allocation/students/1/assign/').reply(200, { assignment_id: 77, message: 'ok' });
    mock.onPost('/api/assisted-allocation/students/1/override/').reply(403, {
      error: 'Override requires a regional manager', violations: ['gender'],
    });

    await expect(assistedAllocationAPI.assign(1, 9001)).resolves.toEqual({ assignment_id: 77, message: 'ok' });
    expect(JSON.parse(mock.history.post[0].data)).toEqual({ bed_id: 9001 });

    const refused: ApiError = await assistedAllocationAPI.override(1, 9001, 'no other place').catch((err) => err);
    expect(refused.message).toBe('error: Override requires a regional manager; violations: gender');
    expect(refused.status).toBe(403);
    expect(refused.fieldErrors).toEqual({ error: 'Override requires a regional manager', violations: ['gender'] });
    expect(JSON.parse(mock.history.post[1].data)).toEqual({ bed_id: 9001, note: 'no other place' });
  });
});
