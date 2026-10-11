import type {
  BilingualLabel,
  Dictionary,
  Language,
  PairPicker,
  TextDirection,
} from './types';

export const DEFAULT_LANGUAGE: Language = 'he';

/** localStorage key the language preference has always been persisted under. */
export const LANGUAGE_STORAGE_KEY = 'dormify_language';

/** Anything that is not exactly 'en' is Hebrew - the historical rule. */
export function normalizeLanguage(value: unknown): Language {
  return value === 'en' ? 'en' : DEFAULT_LANGUAGE;
}

export function isRTL(language: Language): boolean {
  return language === 'he';
}

export function directionFor(language: Language): TextDirection {
  return isRTL(language) ? 'rtl' : 'ltr';
}

export function otherLanguage(language: Language): Language {
  return language === 'he' ? 'en' : 'he';
}

/**
 * Reads the persisted preference. Returns the default when storage is
 * unavailable (privacy modes, sandboxed frames) rather than throwing.
 */
export function readStoredLanguage(): Language {
  try {
    return normalizeLanguage(localStorage.getItem(LANGUAGE_STORAGE_KEY));
  } catch {
    return DEFAULT_LANGUAGE;
  }
}

/** Selects one language's strings from a dictionary. */
export function pick<T>(dictionary: Dictionary<T>, language: Language): T {
  return dictionary[language];
}

/** Selects one side of a labelHe/labelEn pair. */
export function pickLabel(label: BilingualLabel, language: Language): string {
  return language === 'he' ? label.labelHe : label.labelEn;
}

/**
 * Builds a Dictionary from a function written in the inline-pair style
 * (`p('עברית', 'English')`) that several pages already use: the builder
 * runs once per language with a picker that keeps that language's side.
 * Entries may be functions (`count: (n) => p(`${n} בקשות`, `${n} requests`)`),
 * which then close over the right language, and the builder also receives
 * the language itself for entries that need it explicitly.
 */
export function defineDictionary<T>(
  build: (p: PairPicker, language: Language) => T
): Dictionary<T> {
  return {
    he: build((he) => he, 'he'),
    en: build((_he, en) => en, 'en'),
  };
}
