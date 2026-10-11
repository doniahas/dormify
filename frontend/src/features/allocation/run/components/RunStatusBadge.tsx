import React from 'react';
import { cx } from '../../../../shared/lib/classNames';
import type { AllocationRunStrings } from '../AllocationPage.strings';
import type { RunStatusKey } from '../model';
import styles from '../AllocationPage.module.css';

interface BadgeConfig {
  label: string;
  cls: string;
  dot: boolean;
  pulse?: boolean;
}

function badgeConfig(statusKey: RunStatusKey, t: AllocationRunStrings): BadgeConfig {
  const notStarted: BadgeConfig = { label: t.statusNotStarted, cls: styles.badgeGray, dot: false };
  const config: Partial<Record<RunStatusKey, BadgeConfig>> = {
    not_started: notStarted,
    queued:      { label: t.statusQueued,      cls: styles.badgeBlue, dot: true },
    running:     { label: t.statusRunning,     cls: styles.badgeBlue, dot: true, pulse: true },
    cancellation_requested: { label: t.statusStopping, cls: styles.badgeAmber, dot: true, pulse: true },
    stop_and_save_requested: { label: t.statusStopSaveRequested, cls: styles.badgeAmber, dot: true, pulse: true },
    stopped:     { label: t.statusStopped,    cls: styles.badgeGray, dot: false },
    completed:   { label: t.statusCompleted,  cls: styles.badgeGreen, dot: false },
    failed:      { label: t.statusFailed,     cls: styles.badgeRed, dot: false },
    deleted:     { label: t.statusDeleted,    cls: styles.badgeGray, dot: false },
  };
  return config[statusKey] || notStarted;
}

export interface RunStatusBadgeProps {
  statusKey: RunStatusKey;
  t: AllocationRunStrings;
}

/** The run status pill in the header (pulsing dot while the run is live). */
export function RunStatusBadge({ statusKey, t }: RunStatusBadgeProps): React.ReactElement {
  const c = badgeConfig(statusKey, t);
  return (
    <span className={cx(styles.apStatusBadge, c.cls)}>
      {c.dot && <span className={cx(styles.apBadgeDot, c.pulse && styles.apBadgeDotPulse)} />}
      {c.label}
    </span>
  );
}
