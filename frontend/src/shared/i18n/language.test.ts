import { describe, expect, it } from 'vitest';
import {
  LANGUAGE_STORAGE_KEY,
  defineDictionary,
  directionFor,
  normalizeLanguage,
  otherLanguage,
  pick,
  pickLabel,
  readStoredLanguage,
} from './language';

describe('language selection', () => {
  it('treats anything but "en" as Hebrew, the historical rule', () => {
    expect(normalizeLanguage('en')).toBe('en');
    expect(normalizeLanguage('he')).toBe('he');
    expect(normalizeLanguage('EN')).toBe('he');
    expect(normalizeLanguage(null)).toBe('he');
    expect(normalizeLanguage(undefined)).toBe('he');
  });

  it('derives direction and the toggle target', () => {
    expect(directionFor('he')).toBe('rtl');
    expect(directionFor('en')).toBe('ltr');
    expect(otherLanguage('he')).toBe('en');
    expect(otherLanguage('en')).toBe('he');
  });

  it('reads the persisted preference under the established storage key', () => {
    expect(LANGUAGE_STORAGE_KEY).toBe('dormify_language');
    expect(readStoredLanguage()).toBe('he');
    localStorage.setItem(LANGUAGE_STORAGE_KEY, 'en');
    expect(readStoredLanguage()).toBe('en');
  });
});

describe('dictionaries', () => {
  const strings = defineDictionary((p, language) => ({
    title: p('כותרת', 'Title'),
    count: (n: number) => p(`${n} פריטים`, `${n} items`),
    steps: [p('א', 'A'), p('ב', 'B')],
    code: language,
  }));

  it('builds both languages from one inline-pair builder', () => {
    expect(strings.he.title).toBe('כותרת');
    expect(strings.en.title).toBe('Title');
    expect(strings.he.steps).toEqual(['א', 'ב']);
    expect(strings.en.steps).toEqual(['A', 'B']);
    expect(strings.he.code).toBe('he');
    expect(strings.en.code).toBe('en');
  });

  it('keeps function-valued entries bound to their language', () => {
    expect(strings.he.count(3)).toBe('3 פריטים');
    expect(strings.en.count(3)).toBe('3 items');
  });

  it('selects one language from a dictionary or a label pair', () => {
    expect(pick(strings, 'en').title).toBe('Title');
    expect(pick(strings, 'he').title).toBe('כותרת');
    expect(pickLabel({ labelHe: 'סטודנטים', labelEn: 'Students' }, 'he')).toBe('סטודנטים');
    expect(pickLabel({ labelHe: 'סטודנטים', labelEn: 'Students' }, 'en')).toBe('Students');
  });
});
