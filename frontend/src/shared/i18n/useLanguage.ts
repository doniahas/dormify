import { useCallback } from 'react';
import { useAuth } from '../../features/auth/AuthContext';
import { directionFor, isRTL, pick } from './language';
import type { Dictionary, Language, TextDirection } from './types';

export interface LanguageState {
  language: Language;
  isHe: boolean;
  isRTL: boolean;
  /** The `dir` attribute value for the current language. */
  dir: TextDirection;
  setLanguage: (next: Language) => void;
  toggleLanguage: () => void;
  /** Selects the current language's strings from a dictionary. */
  t: <T>(dictionary: Dictionary<T>) => T;
}

/**
 * The interface language, read from AuthContext - which owns the state,
 * its localStorage persistence and the document-level lang/dir attributes
 * (the app shell remains the owner of `dir`). This hook only exposes it in
 * a typed, convenient form; it never duplicates the state.
 */
export function useLanguage(): LanguageState {
  const { language, setLanguage, toggleLanguage } = useAuth();

  const t = useCallback(
    <T,>(dictionary: Dictionary<T>): T => pick(dictionary, language),
    [language]
  );

  return {
    language,
    isHe: language === 'he',
    isRTL: isRTL(language),
    dir: directionFor(language),
    setLanguage,
    toggleLanguage,
    t,
  };
}
