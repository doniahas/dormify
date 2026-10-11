import React from 'react';
import { cx } from '../../../../shared/lib/classNames';
import type { AllocationResultsStrings } from '../AllocationResultsPage.strings';
import { getApartment, getBed, getBuilding, getRoom, sortByLocation } from '../allocationResultsHelpers';
import type { AvailableBedRow } from '../model';
import { EmptyState } from './ResultsStates';
import styles from './ResultsTables.module.css';

export interface AvailableBedsTableProps {
  t: AllocationResultsStrings;
  beds: AvailableBedRow[];
}

/** The beds still free after the run, in location order, with their reserved flag. */
export function AvailableBedsTable({ t, beds }: AvailableBedsTableProps): React.ReactElement {
  if (beds.length === 0) {
    return <EmptyState text={t.noAvailableBeds} />;
  }

  return (
    <div className={styles.tableWrap}>
      <table className={cx(styles.resultsTable, styles.bedsTable)}>
        <thead>
          <tr>
            <th>{t.region}</th>
            <th>{t.dormType}</th>
            <th>{t.building}</th>
            <th>{t.apartment}</th>
            <th>{t.room}</th>
            <th>{t.bed}</th>
            <th>{t.apartmentType}</th>
            <th>{t.category}</th>
            <th>{t.reserved}</th>
          </tr>
        </thead>

        <tbody>
          {sortByLocation(beds).map((bed, index) => (
            <tr key={`${bed?.bed_id || 'bed'}-${index}`}>
              <td>{bed?.region || '-'}</td>
              <td>{bed?.dorm_type || '-'}</td>
              <td>{getBuilding(bed) || '-'}</td>
              <td>{getApartment(bed) || '-'}</td>
              <td>{getRoom(bed) || '-'}</td>
              <td>{getBed(bed) || '-'}</td>

              <td>
                {bed?.apartment_type_display || bed?.apartment_type || '-'}
              </td>

              <td>
                {bed?.apartment_category_display || bed?.apartment_category || '-'}
              </td>

              <td>
                <span className={cx(styles.booleanChip, bed?.is_reserved && styles.reserved)}>
                  {bed?.is_reserved ? t.yes : t.no}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
