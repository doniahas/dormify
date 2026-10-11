import { afterEach, expect, it } from 'vitest';
import MockAdapter from 'axios-mock-adapter';
import { api } from '../../shared/api/client';
import { homeAPI } from './api';

const mock = new MockAdapter(api, { onNoMatch: 'throwException' });
afterEach(() => mock.reset());

it('returns the composed dashboard payload untouched', async () => {
  const payload = {
    metrics: { total_students: 40 },
    attention_items: [{ kind: 'unassigned', count: 3 }],
    situation_he: 'הכל תקין',
    situation_en: 'All clear',
  };
  mock.onGet('/api/home/').reply(200, payload);

  await expect(homeAPI.get()).resolves.toEqual(payload);
  expect(mock.history.get.map(({ url }) => url)).toEqual(['/api/home/']);
});

it('surfaces the backend explanation, falling back to the generic message', async () => {
  mock.onGet('/api/home/').replyOnce(500, { error: 'שגיאה בטעינת לוח הבקרה', errorEn: 'Dashboard failed' });
  await expect(homeAPI.get()).rejects.toThrow('error: שגיאה בטעינת לוח הבקרה; errorEn: Dashboard failed');

  mock.onGet('/api/home/').replyOnce(502);
  await expect(homeAPI.get()).rejects.toThrow('Failed to load homepage data: HTTP 502 with empty/unknown body');
});
