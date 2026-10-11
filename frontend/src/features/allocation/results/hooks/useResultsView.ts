import { useState } from 'react';
import type { ResultsView } from '../model';

export interface ResultsViewState {
  activeView: ResultsView;
  setActiveView: (view: ResultsView) => void;
}

/** Which of the three views (assigned / unassigned / beds) the panel shows; assigned first. */
export function useResultsView(): ResultsViewState {
  const [activeView, setActiveView] = useState<ResultsView>('assigned');
  return { activeView, setActiveView };
}
