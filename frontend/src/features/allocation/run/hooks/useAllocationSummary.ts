import { useCallback, useState } from 'react';
import { allocationAPI, inboxAPI } from '../../api';
import { describeError, inboxItemId, safeInbox, safeSummary } from '../allocationRunHelpers';
import type { AllocationRunStrings } from '../AllocationPage.strings';
import type { InboxItemView, SummaryView } from '../model';

export interface AllocationSummaryOptions {
  /** Central admins have no region inbox; the notice is only read for regional staff. */
  central: boolean;
  t: AllocationRunStrings;
}

export interface AllocationSummaryState {
  /** True until the first summary reply (the page shows its loading state). */
  loading: boolean;
  /** The last load error; fatal without a summary, an inline alert with one. */
  error: string | null;
  setError: (message: string | null) => void;
  summary: SummaryView | null;
  inboxItem: InboxItemView | null;
  /** Re-reads the summary and (for regional staff) the latest inbox item; resolves with the summary. */
  loadPage: () => Promise<SummaryView | null>;
}

/**
 * The page data: the allocation summary (students, beds, inventory,
 * population) and, for regional users, the latest inbox notice - which is
 * marked as viewed the moment it is shown while still pending.
 */
export function useAllocationSummary({ central, t }: AllocationSummaryOptions): AllocationSummaryState {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [summary, setSummary] = useState<SummaryView | null>(null);
  const [inboxItem, setInboxItem] = useState<InboxItemView | null>(null);

  const loadPage = useCallback(async (): Promise<SummaryView | null> => {
    setLoading(true);
    setError(null);
    let normalizedSummary: SummaryView | null = null;

    try {
      const summaryRaw = await allocationAPI.getSummary();
      normalizedSummary = safeSummary(summaryRaw, t.malformedSummary);
      setSummary(normalizedSummary);

      if (!central) {
        try {
          const inboxRaw = await inboxAPI.getLatest();
          const inbox = safeInbox(inboxRaw);
          if (inbox) {
            setInboxItem(inbox);
            const inboxId = inboxItemId(inbox);
            if (inbox.status === 'pending' && inboxId) {
              Promise.resolve(inboxAPI.markViewed(inboxId)).catch(() => {});
            }
          } else {
            setInboxItem(null);
          }
        } catch {
          setInboxItem(null);
        }
      } else {
        setInboxItem(null);
      }
    } catch (err) {
      setError(describeError(err, t.unknownError));
    } finally {
      setLoading(false);
    }

    return normalizedSummary;
  }, [central, t.malformedSummary, t.unknownError]);

  return { loading, error, setError, summary, inboxItem, loadPage };
}
