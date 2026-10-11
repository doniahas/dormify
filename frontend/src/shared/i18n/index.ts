// Shared localization infrastructure (R3). Pages keep their existing
// per-page dictionaries; this module gives them one typed shape
// (Dictionary<T>), one builder for the inline-pair style (defineDictionary),
// one language-selection rule (normalizeLanguage / pick / pickLabel) and one
// hook (useLanguage) on top of AuthContext, which stays the owner of the
// language state, its persistence and the document direction.
export type {
  BilingualLabel,
  Dictionary,
  Language,
  PairPicker,
  TextDirection,
} from './types';
export {
  DEFAULT_LANGUAGE,
  LANGUAGE_STORAGE_KEY,
  defineDictionary,
  directionFor,
  isRTL,
  normalizeLanguage,
  otherLanguage,
  pick,
  pickLabel,
  readStoredLanguage,
} from './language';
export { useLanguage } from './useLanguage';
export type { LanguageState } from './useLanguage';
