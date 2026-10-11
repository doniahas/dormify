import React from 'react';
import { AlertTriangle, Bell, Calendar, Check, Mail } from 'lucide-react';
import { cx } from '../../../../shared/lib/classNames';
import { formatInboxDate } from '../allocationRunHelpers';
import type { AllocationRunStrings } from '../AllocationPage.strings';
import type { InboxItemView } from '../model';
import styles from '../AllocationPage.module.css';

export interface InboxNoticeProps {
  t: AllocationRunStrings;
  inboxItem: InboxItemView;
}

/** The compact "students received for allocation" notice for regional staff. */
export function InboxNotice({ t, inboxItem }: InboxNoticeProps): React.ReactElement {
  const isPending = inboxItem.status === 'pending';
  return (
    <div className={styles.apInboxNotice}>
      <div className={styles.apInboxIconWrap}>
        <Bell size={15} />
      </div>
      <div className={styles.apInboxBody}>
        <span className={styles.apInboxTitle}>{t.notification}</span>
        <div className={styles.apInboxDetail}>
          <Mail size={12} />
          <strong>{Number(inboxItem.students_count) || 0}</strong>
          <span>{t.receivedStudents}</span>
          <span className={styles.apInboxMetaSep}>·</span>
          <Calendar size={12} />
          <span>{formatInboxDate(inboxItem.created_at, t.dateLocale)}</span>
        </div>
      </div>
      <span className={cx(styles.apInboxStatus, isPending && styles.apInboxPending)}>
        {isPending
          ? <><AlertTriangle size={12} /> {t.pending}</>
          : <><Check size={12} /> {t.viewed}</>
        }
      </span>
    </div>
  );
}
