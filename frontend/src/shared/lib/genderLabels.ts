// ---------------------------------------------------------------------
// Centralized display-name localization for student gender.
//
// WHY THIS FILE EXISTS
// The backend stores/returns the student `gender` field as the raw enum
// values 'male' / 'female' (see Student.Gender in backend/api/models.py),
// and several endpoints additionally return a `gender_display` field via
// Django's get_gender_display() - which is a FIXED Hebrew string ('זכר' /
// 'נקבה') regardless of the app's current language. Neither of those is
// what the UI should show: the raw value is a wire value, not a label,
// and gender_display never follows the language toggle. This file is the
// single place that maps the raw enum value to the correct user-facing
// label for the current language, following the same convention as
// shared/lib/locationNames.ts - never re-derive this mapping independently
// in a page/component.
//
// HOW TO USE THIS IN A NEW COMPONENT
//   import { localizeGender } from './genderLabels';
//   localizeGender(student.gender, language) // 'male'/'female' + 'he'/'en'
//
// DISPLAY ONLY - the returned string is for RENDERING ONLY. Always keep
// sending/filtering on the raw 'male'/'female' value, never on this
// return value (same rule as locationNames.ts).
// ---------------------------------------------------------------------
import type { Gender } from '../api/contracts';
import type { Language } from '../i18n/types';

const GENDER_LABEL_HE: Readonly<Record<Gender, string>> = { male: 'גבר', female: 'אישה' };
const GENDER_LABEL_EN: Readonly<Record<Gender, string>> = { male: 'Man', female: 'Woman' };

const isKnownGender = (value: string): value is Gender =>
  value === 'male' || value === 'female';

// value: the raw backend enum ('male' | 'female' | '' | null | undefined).
// Unknown/empty values pass through unchanged (never blank out real data,
// never throw) rather than being silently dropped.
export function localizeGender(
  value: string | null | undefined,
  language: Language | string | null | undefined
): string {
  if (!value) return '';
  const table = language === 'he' ? GENDER_LABEL_HE : GENDER_LABEL_EN;
  return isKnownGender(value) ? table[value] : value;
}
