import { useCallback, useEffect, useState } from 'react';
import { studentsAPI } from '../api';
import type { StudentTabCounts } from '../model';

const ZERO_COUNTS: StudentTabCounts = {
  all: 0, new: 0, continuing: 0, transfer: 0, leaving: 0, unassigned: 0,
};

export interface StudentCountsState {
  counts: StudentTabCounts;
  /** Re-reads the totals (after a create, an update or a placement). */
  reload: () => Promise<void>;
}

/** The per-tab totals shown on the stat cards, loaded once and on demand. */
export function useStudentCounts(): StudentCountsState {
  const [counts, setCounts] = useState<StudentTabCounts>(ZERO_COUNTS);

  const reload = useCallback(async () => {
    try {
      const data = await studentsAPI.getCounts();
      setCounts({
        all: data.all ?? 0,
        new: data.new ?? 0,
        continuing: data.continuing ?? 0,
        transfer: data.transfer ?? 0,
        leaving: data.leaving ?? 0,
        unassigned: data.unassigned ?? 0,
      });
    } catch (err) {
      console.error('Failed to load counts:', err);
    }
  }, []);

  useEffect(() => { void reload(); }, [reload]);

  return { counts, reload };
}
