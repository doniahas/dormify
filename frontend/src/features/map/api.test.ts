import { afterEach, beforeEach, expect, it } from 'vitest';
import MockAdapter from 'axios-mock-adapter';
import { api } from '../../shared/api/client';
import { getMapData } from './api';

let mock: MockAdapter;
beforeEach(() => { mock = new MockAdapter(api, { onNoMatch: 'throwException' }); });
afterEach(() => mock.restore());

it('loads the map aggregate from the analysis endpoint with a single request', async () => {
  const data = { summary: { total_beds: 25 }, buildings: [] };
  mock.onGet('/api/analysis/').reply(200, data);
  await expect(getMapData()).resolves.toEqual(data);
  expect(mock.history.get.map(({ url }) => url)).toEqual(['/api/analysis/']);
});

it('never probes the retired compatibility paths, even when a backend still serves them', async () => {
  // Regression guard for the removal of the /api/analysis-data/ and
  // /api/analysis_data/ fallbacks: the map must not issue them before (or
  // instead of) the supported endpoint.
  mock.onGet('/api/analysis-data/').reply(200, { summary: { total_beds: 1 } });
  mock.onGet('/api/analysis_data/').reply(200, { summary: { total_beds: 2 } });
  mock.onGet('/api/analysis/').reply(200, { summary: { total_beds: 3 } });
  await expect(getMapData()).resolves.toEqual({ summary: { total_beds: 3 } });
  expect(mock.history.get.map(({ url }) => url)).toEqual(['/api/analysis/']);
});

it('keeps an empty successful response as an empty map payload', async () => {
  mock.onGet('/api/analysis/').reply(200, null);
  await expect(getMapData()).resolves.toEqual({});
  expect(mock.history.get).toHaveLength(1);
});

it('propagates the failure for the map error display without retrying elsewhere', async () => {
  mock.onGet('/api/analysis/').reply(503, { detail: 'Unavailable' });
  await expect(getMapData()).rejects.toMatchObject({ response: { status: 503, data: { detail: 'Unavailable' } } });
  expect(mock.history.get.map(({ url }) => url)).toEqual(['/api/analysis/']);
});
