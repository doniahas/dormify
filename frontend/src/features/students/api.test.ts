import { afterEach, describe, expect, it, vi } from 'vitest';
import type { AxiosRequestConfig } from 'axios';
import MockAdapter from 'axios-mock-adapter';
import { api } from '../../shared/api/client';
import { studentsAPI } from './api';

type ReplyHandler = (config: AxiosRequestConfig) => [number, unknown?];

let mock: MockAdapter;
function fallback(handler: ReplyHandler) {
  mock = new MockAdapter(api, { onNoMatch: 'throwException' });
  vi.spyOn(console, 'warn').mockImplementation(() => {});
  mock.onGet('/api/students/counts/').replyOnce(503);
  mock.onGet('/api/students/').reply(handler);
}
afterEach(() => mock?.restore());

it('loads the exact server continuation URL without changing the student page payload', async () => {
  mock = new MockAdapter(api, { onNoMatch: 'throwException' });
  const url = 'http://backend.test/api/students/?page=2&gender=male';
  const page = { results: [{ id: 9 }], next: null, count: 21 };
  mock.onGet(url).reply(200, page);
  await expect(studentsAPI.getNextPage(url)).resolves.toEqual(page);
  expect(mock.history.get.map(({ url }) => url)).toEqual([url]);
});

it('keeps continuation failures available to the student page', async () => {
  mock = new MockAdapter(api, { onNoMatch: 'throwException' });
  mock.onGet('/api/students/?page=2').reply(503);
  await expect(studentsAPI.getNextPage('/api/students/?page=2')).rejects.toMatchObject({ response: { status: 503 } });
});

describe('student count fallback', () => {
  it('returns the authoritative count response without loading student lists', async () => {
    mock = new MockAdapter(api, { onNoMatch: 'throwException' });
    const counts = { all: 84, continuing: 40, new: 20, transfer: 14, leaving: 10, unassigned: 7 };
    mock.onGet('/api/students/counts/').replyOnce(200, counts);
    await expect(studentsAPI.getCounts()).resolves.toEqual(counts);
    expect(mock.history.get).toHaveLength(1);
  });

  it('uses server totals and category/status filters instead of first-page length or assignment flags', async () => {
    const counts: Record<string, number> = { all: 84, continuing: 40, new: 20, transfer: 14, leaving: 10, unassigned: 7 };
    fallback(({ params = {} }) => [200, {
      count: counts[params.category || params.status || 'all'],
      next: '/api/students/?page=2',
      results: [{ category: 'ממשיכים', is_assigned: false }],
    }]);
    await expect(studentsAPI.getCounts()).resolves.toMatchObject(counts);
    expect(mock.history.get.slice(1).map(({ params }) => params)).toEqual(expect.arrayContaining([
      {}, { category: 'continuing' }, { category: 'new' }, { category: 'transfer' }, { category: 'leaving' }, { status: 'unassigned' },
    ]));
    expect(mock.history.get).toHaveLength(7);
  });

  it('counts complete unpaginated responses without interpreting translated labels', async () => {
    fallback(({ params = {} }) => [200, params.status ? [{ id: 2 }] : [{ category: 'עזיבה' }, { category: 'חדש' }]]);
    await expect(studentsAPI.getCounts()).resolves.toMatchObject({ all: 2, continuing: 2, new: 2, transfer: 2, leaving: 2, unassigned: 1 });
  });

  it('follows pagination when a list response has no count', async () => {
    fallback(({ params = {} }) => [200, params.category || params.status ? [] : { results: [{ id: 1 }], next: '/api/students/?page=2' }]);
    mock.onGet('/api/students/?page=2').replyOnce(200, { results: [{ id: 2 }, { id: 3 }], next: null });
    await expect(studentsAPI.getCounts()).resolves.toMatchObject({ all: 3, new: 0, unassigned: 0 });
  });

  it('rejects a failed fallback rather than presenting fabricated zero totals', async () => {
    fallback(() => [503, { detail: 'Unavailable' }]);
    await expect(studentsAPI.getCounts()).rejects.toThrow();
  });

  it('rejects malformed list responses rather than reporting an empty population', async () => {
    fallback(() => [200, { detail: 'not a list' }]);
    await expect(studentsAPI.getCounts()).rejects.toThrow();
  });
});
