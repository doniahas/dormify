import { afterEach, expect, it } from 'vitest';
import MockAdapter from 'axios-mock-adapter';
import { api } from '../../shared/api/client';
import { reportsAPI } from './api';

const mock = new MockAdapter(api, { onNoMatch: 'throwException' });
afterEach(() => mock.reset());

it('requests each workbook as a blob and hands the whole response to the page', async () => {
  const workbook = new Blob(['PK'], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' });
  mock.onGet('/api/reports/dormify-report/').reply(200, workbook);
  mock.onGet('/api/reports/capacity-report/').reply(200, workbook);

  const full = await reportsAPI.downloadDormifyReport();
  const capacity = await reportsAPI.downloadCapacityReport('canada');

  expect(full.status).toBe(200);
  expect(full.data).toBe(workbook);
  expect(capacity.data).toBe(workbook);
  expect(mock.history.get.map(({ url, responseType, params }) => [url, responseType, params])).toEqual([
    ['/api/reports/dormify-report/', 'blob', undefined],
    ['/api/reports/capacity-report/', 'blob', { region_id: 'canada' }],
  ]);
});

it('sends no region filter when none is chosen', async () => {
  mock.onGet('/api/reports/student-actions-report/').reply(200, new Blob());
  mock.onGet('/api/reports/manual-review-report/').reply(200, new Blob());

  await reportsAPI.downloadStudentActionsReport();
  await reportsAPI.downloadManualReviewReport(null);

  expect(mock.history.get.map(({ params }) => params)).toEqual([{}, {}]);
});

it('propagates failures as axios errors for the page to explain', async () => {
  mock.onGet('/api/reports/student-allocation-report/').reply(403, { error: 'Forbidden' });

  await expect(reportsAPI.downloadStudentAllocationReport()).rejects.toMatchObject({
    response: { status: 403, data: { error: 'Forbidden' } },
  });
});
