import React from 'react';
import { AlertTriangle } from 'lucide-react';
import { cx } from '../../../../shared/lib/classNames';
import type { AllocationRunStrings } from '../AllocationPage.strings';
import type { MaxSolverUnit } from '../model';
import styles from '../AllocationPage.module.css';

export interface MaxSearchTimeCardProps {
  t: AllocationRunStrings;
  value: string;
  unit: MaxSolverUnit;
  error: string;
  disabled: boolean;
  onValueChange: (next: string) => void;
  onUnitChange: (next: MaxSolverUnit) => void;
}

/** "זמן חיפוש מרבי": the maximum search time (value + unit) a run is started with. */
export function MaxSearchTimeCard({
  t, value, unit, error, disabled, onValueChange, onUnitChange,
}: MaxSearchTimeCardProps): React.ReactElement {
  return (
    <div className={cx(styles.apCard, styles.apMaxtimeCard)}>
      <div className={styles.apMaxtimeRow}>
        <label className={styles.apMaxtimeLabel} htmlFor="ap-maxtime-value">
          {t.maxSearchTimeLabel}
        </label>
        <div className={styles.apMaxtimeInputs}>
          <input
            id="ap-maxtime-value"
            type="number"
            min="1"
            step="1"
            className={styles.apNumberInput}
            value={value}
            onChange={(e) => onValueChange(e.target.value)}
            disabled={disabled}
            aria-label={t.maxSearchTimeLabel}
          />
          <select
            className={styles.apUnitSelect}
            value={unit}
            onChange={(e) => onUnitChange(e.target.value as MaxSolverUnit)}
            disabled={disabled}
            aria-label={t.maxSearchTimeLabel}
          >
            <option value="seconds">{t.maxSearchTimeUnitSeconds}</option>
            <option value="minutes">{t.maxSearchTimeUnitMinutes}</option>
            <option value="hours">{t.maxSearchTimeUnitHours}</option>
          </select>
        </div>
      </div>
      {error ? (
        <div className={styles.apMaxtimeError}>
          <AlertTriangle size={13} />
          <span>{error}</span>
        </div>
      ) : (
        <p className={styles.apMaxtimeHint}>{t.maxSearchTimeHint}</p>
      )}
    </div>
  );
}
