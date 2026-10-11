import React from 'react';
import { Lock, ShieldCheck, SlidersHorizontal } from 'lucide-react';
import { cx } from '../../../../shared/lib/classNames';
import { conditionText } from '../allocationRunHelpers';
import type { AllocationRunStrings } from '../AllocationPage.strings';
import type { ConstraintEntry, ConstraintKey, ConstraintSetting } from '../model';
import pageStyles from '../AllocationPage.module.css';
import styles from './AllocationConditions.module.css';

interface CriticalConditionCardProps {
  condKey: ConstraintKey;
  t: AllocationRunStrings;
  /** Overrides the dictionary key the texts are read from (the ANIR variant). */
  titleKey?: string;
  highlight: boolean;
}

function CriticalConditionCard({ condKey, t, titleKey, highlight }: CriticalConditionCardProps): React.ReactElement {
  const resolvedTitleKey = titleKey || condKey;
  const title = conditionText(t, resolvedTitleKey) || resolvedTitleKey;
  const desc = conditionText(t, `${resolvedTitleKey}Desc`);
  const desc2 = conditionText(t, `${resolvedTitleKey}Desc2`);

  return (
    <div className={cx(styles.apCondCard, styles.apCondCritical, highlight && styles.apCondHighlight)}>
      <div className={cx(styles.apCondIconWrap, styles.apCondIconCritical)}>
        <Lock size={13} />
      </div>
      <div className={styles.apCondBody}>
        <div className={styles.apCondName}>{title}</div>
        {desc && <div className={styles.apCondDesc}>{desc}</div>}
        {desc2 && <div className={cx(styles.apCondDesc, styles.apCondDesc2)}>{desc2}</div>}
        <div className={styles.apCondMeta}>
          <span className={cx(styles.apCondBadge, styles.apCondBadgeCritical)}>
            <ShieldCheck size={11} /> {t.hardConstraint}
          </span>
          <span className={styles.apCondAlways}>{t.alwaysApplied}</span>
        </div>
      </div>
    </div>
  );
}

interface FlexibleConditionCardProps {
  condKey: ConstraintKey;
  value: ConstraintSetting;
  t: AllocationRunStrings;
  onToggle: (key: ConstraintKey) => void;
  onWeightChange: (key: ConstraintKey, nextWeight: string) => void;
}

function FlexibleConditionCard({ condKey, value, t, onToggle, onWeightChange }: FlexibleConditionCardProps): React.ReactElement {
  const name = conditionText(t, condKey) || condKey;
  const desc = conditionText(t, `${condKey}Desc`);

  return (
    <div className={cx(styles.apCondCard, styles.apCondFlexible, !value.enabled && styles.apCondOff)}>
      <div className={styles.apCondFlexTop}>
        <div className={cx(styles.apCondIconWrap, styles.apCondIconFlex)}>
          <SlidersHorizontal size={13} />
        </div>
        <div className={styles.apCondBody}>
          <div className={styles.apCondName}>{name}</div>
          {desc && (
            <div className={styles.apCondDesc}>{desc}</div>
          )}
          <span className={cx(styles.apCondStatusChip, value.enabled && styles.apCondStatusOn)}>
            {value.enabled ? t.included : t.excluded}
          </span>
        </div>
        <button
          type="button"
          className={cx(styles.apSwitch, value.enabled && styles.apSwitchOn)}
          role="switch"
          aria-checked={value.enabled}
          aria-label={`${name}: ${value.enabled ? t.included : t.excluded}`}
          onClick={() => onToggle(condKey)}
        >
          <span className={styles.apSwitchThumb} />
        </button>
      </div>

      {value.enabled && (
        <div className={styles.apCondWeight}>
          <div className={styles.apCondWeightHeader}>
            <span className={styles.apCondWeightLbl}>{t.importance}</span>
            <span className={styles.apCondWeightVal}>{value.weight}/10</span>
          </div>
          <input
            type="range"
            min="0"
            max="10"
            step="1"
            value={value.weight}
            className={styles.apRange}
            aria-label={`${t.importance}: ${name}`}
            onChange={(e) => onWeightChange(condKey, e.target.value)}
          />
          <div className={styles.apRangeScale}>
            <span>0</span>
            <span>10</span>
          </div>
        </div>
      )}
    </div>
  );
}

export interface ConditionsCardProps {
  t: AllocationRunStrings;
  hardConstraints: ConstraintEntry[];
  optimizationPreferences: ConstraintEntry[];
  /** The upper-dorms region shows the ANIR texts on the priority card. */
  isUpperDorm: boolean;
  canRun: boolean;
  onToggle: (key: ConstraintKey) => void;
  onWeightChange: (key: ConstraintKey, nextWeight: string) => void;
}

/** "Allocation Conditions": the locked critical constraints and the weighted flexible preferences. */
export function ConditionsCard({
  t, hardConstraints, optimizationPreferences, isUpperDorm, canRun, onToggle, onWeightChange,
}: ConditionsCardProps): React.ReactElement {
  return (
    <div className={pageStyles.apCard}>
      <div className={pageStyles.apCardHeader}>
        <div className={pageStyles.apCardTitleRow}>
          <SlidersHorizontal size={16} />
          <h2 className={pageStyles.apCardTitle}>{t.conditionsTitle}</h2>
        </div>
      </div>

      {/* Critical Conditions */}
      <div className={styles.apCondSection}>
        <div className={cx(styles.apCondSectionHeader, styles.apCondColCritical)}>
          <ShieldCheck size={14} />
          <div>
            <div className={styles.apCondColTitle}>{t.criticalTitle}</div>
            <div className={styles.apCondColHint}>{t.criticalHint}</div>
          </div>
          <span className={styles.apCountBadge}>{hardConstraints.length}</span>
        </div>
        <div className={styles.apCondGrid2}>
          {hardConstraints.map(([key]) => (
            <CriticalConditionCard
              key={key}
              condKey={key}
              t={t}
              titleKey={key === 'priorityFirst' && isUpperDorm ? 'priorityFirstAnier' : undefined}
              highlight={key === 'priorityFirst'}
            />
          ))}
        </div>
      </div>

      {/* Flexible Preferences */}
      <div className={cx(styles.apCondSection, styles.apCondSectionDivider)}>
        <div className={cx(styles.apCondSectionHeader, styles.apCondColFlexible)}>
          <SlidersHorizontal size={14} />
          <div>
            <div className={styles.apCondColTitle}>{t.flexibleTitle}</div>
            <div className={styles.apCondColHint}>{t.flexibleHint}</div>
          </div>
          <span className={styles.apCountBadge}>{optimizationPreferences.length}</span>
        </div>
        <div className={styles.apCondGrid2}>
          {optimizationPreferences.map(([key, value]) => (
            <FlexibleConditionCard
              key={key}
              condKey={key}
              value={value}
              t={t}
              onToggle={onToggle}
              onWeightChange={onWeightChange}
            />
          ))}
        </div>
      </div>

      {!canRun && (
        <div className={styles.apLockNotice}>
          <Lock size={14} />
          <span>{t.noPermission}</span>
        </div>
      )}
    </div>
  );
}
