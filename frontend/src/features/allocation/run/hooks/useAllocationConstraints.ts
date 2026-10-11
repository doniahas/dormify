import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  ALLOCATION_CONSTRAINTS_STORAGE_KEY,
  DEFAULT_CONSTRAINTS,
  buildEffectiveConfig,
  mergeStoredConstraints,
  splitConstraints,
  toggleConstraint,
  withConstraintWeight,
} from '../allocationRunHelpers';
import type { ConstraintEntry, ConstraintKey, ConstraintSet, EffectiveConstraintConfig } from '../model';

export interface AllocationConstraintsState {
  constraints: ConstraintSet;
  /** The critical constraints (always applied; shown locked). */
  hardConstraints: ConstraintEntry[];
  /** The flexible preferences (toggle + weight). */
  optimizationPreferences: ConstraintEntry[];
  /** The `constraints` payload a run is started with. */
  effectiveConfig: EffectiveConstraintConfig;
  toggleConstraintEnabled: (key: ConstraintKey) => void;
  setConstraintWeight: (key: ConstraintKey, nextWeight: string | number) => void;
}

/**
 * The allocation conditions as the user configures them: restored from
 * localStorage (merged over the defaults) on mount and persisted on every
 * change. Critical constraints cannot be toggled or weighted. This is only
 * the configuration carried to the backend; the constraints' meaning lives
 * in the solver.
 */
export function useAllocationConstraints(): AllocationConstraintsState {
  const [constraints, setConstraints] = useState<ConstraintSet>(() => {
    try {
      const savedConstraints = localStorage.getItem(ALLOCATION_CONSTRAINTS_STORAGE_KEY);

      if (!savedConstraints) {
        return DEFAULT_CONSTRAINTS;
      }

      return mergeStoredConstraints(JSON.parse(savedConstraints));
    } catch (error) {
      console.warn(
        'Failed to load saved allocation constraints:',
        error
      );

      return DEFAULT_CONSTRAINTS;
    }
  });

  useEffect(() => {
    try {
      localStorage.setItem(
        ALLOCATION_CONSTRAINTS_STORAGE_KEY,
        JSON.stringify(constraints)
      );
    } catch (error) {
      console.warn(
        'Failed to save allocation constraints:',
        error
      );
    }
  }, [constraints]);

  const toggleConstraintEnabled = useCallback((key: ConstraintKey) => {
    setConstraints((prev) => toggleConstraint(prev, key));
  }, []);

  const setConstraintWeight = useCallback((key: ConstraintKey, nextWeight: string | number) => {
    setConstraints((prev) => withConstraintWeight(prev, key, nextWeight));
  }, []);

  const { hard: hardConstraints, flexible: optimizationPreferences } = useMemo(
    () => splitConstraints(constraints),
    [constraints]
  );
  const effectiveConfig = useMemo(() => buildEffectiveConfig(constraints), [constraints]);

  return {
    constraints,
    hardConstraints,
    optimizationPreferences,
    effectiveConfig,
    toggleConstraintEnabled,
    setConstraintWeight,
  };
}
