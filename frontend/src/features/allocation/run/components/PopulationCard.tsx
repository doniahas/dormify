import React from 'react';
import { cx } from '../../../../shared/lib/classNames';
import type { AllocationRunStrings } from '../AllocationPage.strings';
import type { PopulationSummaryView } from '../model';
import styles from '../AllocationPage.module.css';

export interface PopulationCardProps {
  t: AllocationRunStrings;
  population: PopulationSummaryView;
  showDetails: boolean;
  onToggleDetails: () => void;
}

/** The compact population summary: imported -> excluded -> sent to the solver. */
export function PopulationCard({ t, population, showDetails, onToggleDetails }: PopulationCardProps): React.ReactElement {
  const {
    imported_students, excluded_accessibility, excluded_leaving,
    excluded_overlap, excluded_total, sent_to_solver, assigned, unassigned,
  } = population;

  return (
    <div className={styles.apPopulationCard}>
      <div className={styles.apPopulationRow}>
        <span className={cx(styles.apPopulationChip, styles.apPopulationChipBlue)}>
          {imported_students} {t.populationImported}
        </span>
        <span className={styles.apPopulationArrow}>→</span>
        <span className={cx(styles.apPopulationChip, styles.apPopulationChipAmber)}>
          {excluded_total} {t.populationExcluded}
        </span>
        <span className={styles.apPopulationArrow}>→</span>
        <span className={cx(styles.apPopulationChip, styles.apPopulationChipGreen)}>
          {sent_to_solver} {t.populationSentToSolver}
        </span>

        {excluded_total > 0 && (
          <button
            type="button"
            className={styles.apPopulationToggle}
            onClick={onToggleDetails}
            aria-expanded={showDetails}
          >
            {showDetails ? t.populationHideDetails : t.populationShowDetails}
          </button>
        )}
      </div>

      {showDetails && excluded_total > 0 && (
        <ul className={styles.apPopulationDetails}>
          <li>{excluded_accessibility} {t.populationExcludedAccessibility}</li>
          <li>{excluded_leaving} {t.populationExcludedLeaving}</li>
          {excluded_overlap > 0 && (
            <li>{excluded_overlap} {t.populationExcludedOverlap}</li>
          )}
          <li className={styles.apPopulationDetailsTotal}>
            {t.populationExcludedTotalUnique}: {excluded_total}
          </li>
        </ul>
      )}

      {typeof assigned === 'number' && typeof unassigned === 'number' && (
        <div className={styles.apPopulationProcessed}>
          {sent_to_solver} {t.populationProcessed} = {assigned} {t.populationAssignedWord} + {unassigned} {t.populationUnassignedWord}
        </div>
      )}
    </div>
  );
}
