import { afterEach, expect, it } from 'vitest';
import MockAdapter from 'axios-mock-adapter';
import { api } from '../../shared/api/client';
import { analysisAPI } from './api';

const mock = new MockAdapter(api, { onNoMatch: 'throwException' });
afterEach(() => mock.reset());

it('returns the analysis payload and scopes it to a region only when one is given', async () => {
  const payload = { summary: { total_students: 12 }, occupancy_data: [] };
  mock.onGet('/api/analysis/').reply(200, payload);

  await expect(analysisAPI.getData()).resolves.toEqual(payload);
  await expect(analysisAPI.getData('canada')).resolves.toEqual(payload);

  expect(mock.history.get.map(({ params }) => params)).toEqual([{}, { region: 'canada' }]);
});

it('normalizes a failure into a readable error for the page', async () => {
  mock.onGet('/api/analysis/').reply(403, { detail: 'Region not permitted' });

  await expect(analysisAPI.getData('mizrah')).rejects.toThrow('Region not permitted');

  mock.onGet('/api/analysis/').networkError();
  await expect(analysisAPI.getData()).rejects.toThrow(/Failed to load analysis data: no response from server/);
});
