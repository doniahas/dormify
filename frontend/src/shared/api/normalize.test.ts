import { describe, expect, it } from 'vitest';
import { asArray, continuationPath, idOf, sameId } from './normalize';

describe('asArray', () => {
  it('returns a plain array as is and unwraps a pagination envelope', () => {
    const items = [{ id: 1 }, { id: 2 }];
    expect(asArray(items)).toBe(items);
    expect(asArray({ count: 2, next: null, previous: null, results: items })).toBe(items);
  });

  it('turns anything else into an empty list', () => {
    expect(asArray(null)).toEqual([]);
    expect(asArray(undefined)).toEqual([]);
    expect(asArray({ count: 0 })).toEqual([]);
    expect(asArray({ detail: 'not a list' })).toEqual([]);
  });
});

describe('idOf and sameId', () => {
  it('compares numeric and string ids through their string form', () => {
    expect(idOf(12)).toBe('12');
    expect(idOf('canada')).toBe('canada');
    expect(idOf(null)).toBe('');
    expect(idOf(undefined)).toBe('');
    expect(sameId(12, '12')).toBe(true);
    expect(sameId('canada', 'canada')).toBe(true);
    expect(sameId(12, 13)).toBe(false);
  });

  it('never treats two missing ids as the same id', () => {
    expect(sameId(null, undefined)).toBe(false);
    expect(sameId('', '')).toBe(false);
  });
});

describe('continuationPath', () => {
  it('keeps only the path and query of an absolute next link', () => {
    expect(continuationPath('https://example.test/api/buildings/?page=2&region=canada')).toBe(
      '/api/buildings/?page=2&region=canada'
    );
  });

  it('passes a relative link through and ends on a missing one', () => {
    expect(continuationPath('/api/buildings/?page=3')).toBe('/api/buildings/?page=3');
    expect(continuationPath(null)).toBeNull();
    expect(continuationPath(undefined)).toBeNull();
    expect(continuationPath('')).toBeNull();
  });
});
