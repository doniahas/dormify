import React from 'react';
import { Pencil, Trash2 } from 'lucide-react';
import type { Bed, Id } from '../../../shared/api/contracts';
import { idOf } from '../../../shared/api/normalize';
import { cx } from '../../../shared/lib/classNames';
import type { BuildingsStrings } from '../BuildingsPage.strings';
import { IconButton } from './InventoryPrimitives';
import styles from './InventoryPanels.module.css';

export interface BedTableProps {
  t: BuildingsStrings;
  beds: Bed[];
  selectedBedId: Id;
  canManageInventory: boolean;
  /** Only when the adapter offers deleteBed (it does not today). */
  canDeleteBed: boolean;
  onSelect: (bedId: Id) => void;
  onEdit: (bed: Bed) => void;
  onDelete: (bed: Bed) => void;
}

/** The beds of the open room: label, availability and the per-bed actions. */
export function BedTable({
  t, beds, selectedBedId, canManageInventory, canDeleteBed, onSelect, onEdit, onDelete,
}: BedTableProps): React.ReactElement {
  return (
    <table className={styles.table}>
      <thead>
        <tr>
          <th>{t.colBed}</th>
          <th>{t.colAvailability}</th>
          <th>{t.colActions}</th>
        </tr>
      </thead>
      <tbody>
        {beds.map((bed) => {
          const selected = idOf(selectedBedId) === idOf(bed.id);
          return (
            <tr
              key={bed.id}
              className={cx(selected && styles.isSelected)}
              aria-selected={selected}
              onClick={() => onSelect(bed.id)}
            >
              <td>{bed.label}</td>
              <td>
                <span className={cx(styles.availabilityTag, bed.is_occupied ? styles.isOccupied : styles.isAvailable)}>
                  {bed.is_occupied ? t.occupied : t.available}
                </span>
              </td>
              <td onClick={(e) => e.stopPropagation()}>
                {canManageInventory && (
                  <IconButton icon={Pencil} onClick={() => onEdit(bed)} title={t.edit} />
                )}
                {canDeleteBed && (
                  <IconButton
                    icon={Trash2}
                    tone="danger"
                    onClick={() => onDelete(bed)}
                    title={t.deleteAction}
                    disabled={bed.is_occupied}
                  />
                )}
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
