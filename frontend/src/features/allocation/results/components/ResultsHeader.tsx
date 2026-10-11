import React from 'react';
import { ArrowRight, Sparkles } from 'lucide-react';
import type { AllocationResultsStrings } from '../AllocationResultsPage.strings';
import styles from '../AllocationResultsPage.module.css';

export interface ResultsHeaderProps {
  t: AllocationResultsStrings;
  onBack: () => void;
}

/** The top bar: eyebrow, title, subtitle and the way back to the Allocation page. */
export function ResultsHeader({ t, onBack }: ResultsHeaderProps): React.ReactElement {
  return (
    <header className={styles.resultsTopbar}>
      <div>
        <div className={styles.eyebrow}>
          <Sparkles size={16} />
          <span>{t.runHighlights}</span>
        </div>

        <h1>{t.title}</h1>
        <p>{t.subtitle}</p>
      </div>

      <button
        type="button"
        className={styles.backButton}
        onClick={onBack}
      >
        <ArrowRight size={18} />
        <span>{t.backToAllocation}</span>
      </button>
    </header>
  );
}
