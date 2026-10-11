// The two interface languages. 'he' is the default and the only RTL one.
export type Language = 'he' | 'en';

export type TextDirection = 'rtl' | 'ltr';

/**
 * A complete set of strings in both languages. `he` and `en` must have the
 * same shape, so a key missing from one language is a type error rather
 * than an empty label at runtime.
 */
export type Dictionary<T> = Readonly<Record<Language, T>>;

/**
 * A single label carried as a Hebrew/English pair, as the navigation
 * tables (labelHe/labelEn) and some backend payloads express it.
 */
export interface BilingualLabel {
  labelHe: string;
  labelEn: string;
}

/**
 * Picks one language's text out of an inline pair. Dictionary builders
 * receive one of these per language (see defineDictionary).
 */
export type PairPicker = (he: string, en: string) => string;
