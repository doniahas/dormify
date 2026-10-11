import { useCallback, useMemo, useState } from 'react';
import { DEFAULT_SOLVER_SECONDS, maxSolverSeconds, validateMaxSolverTime } from '../allocationRunHelpers';
import type { AllocationRunStrings } from '../AllocationPage.strings';
import type { MaxSolverUnit } from '../model';

export interface MaxSolverTimeState {
  /** The raw input text. */
  value: string;
  unit: MaxSolverUnit;
  error: string;
  setError: (message: string) => void;
  /** Updates the input and clears a shown error. */
  changeValue: (next: string) => void;
  changeUnit: (next: MaxSolverUnit) => void;
  /** The validation message for the current input, '' when valid. */
  validate: () => string;
  /** The value in seconds (the max_solver_seconds payload), null when not positive. */
  seconds: number | null;
}

/** The "maximum search time" input (value + unit) with its validation. */
export function useMaxSolverTime(t: AllocationRunStrings): MaxSolverTimeState {
  const [value, setValue] = useState(String(DEFAULT_SOLVER_SECONDS));
  const [unit, setUnit] = useState<MaxSolverUnit>('seconds');
  const [error, setError] = useState('');

  const changeValue = useCallback((next: string) => {
    setValue(next);
    setError((current) => (current ? '' : current));
  }, []);

  const changeUnit = useCallback((next: MaxSolverUnit) => {
    setUnit(next);
    setError((current) => (current ? '' : current));
  }, []);

  const validate = useCallback(() => validateMaxSolverTime(value, unit, t), [value, unit, t]);

  const seconds = useMemo(() => maxSolverSeconds(value, unit), [value, unit]);

  return { value, unit, error, setError, changeValue, changeUnit, validate, seconds };
}
