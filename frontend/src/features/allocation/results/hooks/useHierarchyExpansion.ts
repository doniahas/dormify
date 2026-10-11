import { useCallback, useState } from 'react';
import type { OpenMap } from '../model';

export type HierarchyLevel = 'dormTypes' | 'buildings' | 'apartments' | 'rooms';

export interface HierarchyExpansionState {
  /** Which rows are open at each level, keyed by the row's path key. */
  open: Record<HierarchyLevel, OpenMap>;
  toggle: (level: HierarchyLevel, key: string) => void;
}

/**
 * The expand/collapse state of the assignments hierarchy, one map per
 * level. Keys are path keys (`dorm`, `dorm::building`, ...), so a building
 * opened under one dorm type stays independent of a same-numbered one
 * elsewhere. Everything starts collapsed.
 */
export function useHierarchyExpansion(): HierarchyExpansionState {
  const [open, setOpen] = useState<Record<HierarchyLevel, OpenMap>>({
    dormTypes: {},
    buildings: {},
    apartments: {},
    rooms: {},
  });

  const toggle = useCallback((level: HierarchyLevel, key: string) => {
    setOpen((previous) => ({
      ...previous,
      [level]: {
        ...previous[level],
        [key]: !previous[level][key],
      },
    }));
  }, []);

  return { open, toggle };
}
