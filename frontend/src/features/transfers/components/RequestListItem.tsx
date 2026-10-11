import React from 'react';
import { Hash } from 'lucide-react';
import { cx } from '../../../shared/lib/classNames';
import { fmtDateShort, fmtReqId, statusMetaFor, typeLabel, typeMetaFor } from '../transferHelpers';
import type { TransfersStrings } from '../TransfersPage.strings';
import type { StudentRequest } from '../types';
import styles from '../TransfersPage.module.css';
import { capitalize, statusIconFor, typeIconFor } from './RequestAtoms';

export interface RequestListItemProps {
  t: TransfersStrings;
  request: StudentRequest;
  selected: boolean;
  onClick: () => void;
}

/** One row of the request list (GitHub-Issues style). */
export function RequestListItem({ t, request, selected, onClick }: RequestListItemProps): React.ReactElement {
  const tc = typeMetaFor(request);
  const sc = statusMetaFor(request.status);
  const TI = typeIconFor(request);
  const SI = statusIconFor(request.status);
  const color = capitalize(tc.color);
  return (
    <button
      type="button"
      className={cx(styles.rqItem, styles[`rqItem${color}`], selected && styles.rqSel)}
      aria-pressed={selected}
      onClick={onClick}
    >
      <div className={styles.riTop}>
        <span className={styles.riId}><Hash size={9} />{fmtReqId(request)}</span>
        <SI size={12} className={styles[`si${capitalize(sc.color)}`]} />
      </div>
      <div className={styles.riStu}>
        <div className={cx(styles.riAva, styles[`riAva${color}`])}>{(request.student_name || '?')[0]}</div>
        <div className={styles.riInf}>
          <span className={styles.riName}>{request.student_name || t.dash}</span>
          <span className={cx(styles.riMeta, styles.mono)}>{request.student_id_number}</span>
        </div>
      </div>
      <div className={styles.riBot}>
        <span className={cx(styles.riType, styles[`riType${color}`])}><TI size={9} /> {typeLabel(t, tc)}</span>
        {request.current_region && <span className={styles.riRegion}>{request.current_region}</span>}
        <span className={styles.riDate}>{fmtDateShort(request.created_at)}</span>
      </div>
    </button>
  );
}
