import React from 'react';
import { AlertTriangle, ChevronDown, DoorOpen, Pencil, Plus, Power, PowerOff } from 'lucide-react';
import type { Bed, Id, Room } from '../../../shared/api/contracts';
import { cx } from '../../../shared/lib/classNames';
import type { BuildingsStrings } from '../BuildingsPage.strings';
import { BedTable } from './BedTable';
import type { StructureActions } from './BuildingStructurePanel';
import { DetailRow, EmptyPanel, IconButton, OccupancyBadge, SectionHeader, Spinner, StatusBadge } from './InventoryPrimitives';
import styles from './InventoryPanels.module.css';

export interface RoomAccordionProps {
  t: BuildingsStrings;
  room: Room;
  isOpen: boolean;
  canManageInventory: boolean;
  canCreateBed: boolean;
  canDeleteBed: boolean;
  roomBeds: Bed[];
  selectedBedId: Id;
  loadingBeds: boolean;
  actions: StructureActions;
}

/** One room row; expanded, it shows its details, availability action and bed table. */
export function RoomAccordion({
  t, room, isOpen: roomOpen, canManageInventory, canCreateBed, canDeleteBed,
  roomBeds, selectedBedId, loadingBeds, actions,
}: RoomAccordionProps): React.ReactElement {
  return (
    <div className={cx(styles.accordionItem, roomOpen && styles.isOpen, !room.is_active && styles.isInactive)}>
      <div
        role="button"
        tabIndex={0}
        aria-expanded={roomOpen}
        className={styles.accordionHeader}
        onClick={() => actions.onSelectRoom(room.id)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            actions.onSelectRoom(room.id);
          }
        }}
      >
        <ChevronDown size={14} className={cx(styles.chevron, roomOpen && styles.isOpen)} />
        <DoorOpen size={15} />
        <span className={styles.accordionTitle}>
          {t.colRoom} {room.name}
        </span>
        {room.has_missing_bed_records && (
          <span className={styles.warnIcon} title={t.bedRecordsMismatch}>
            <AlertTriangle size={12} />
          </span>
        )}
        <span className={styles.accordionMeta}>
          {t.capacityLabel}: {room.capacity}
        </span>
        <OccupancyBadge occupied={room.current_occupancy} total={room.capacity} />
        <StatusBadge active={room.is_active} activeText={t.statusActive} inactiveText={t.statusInactive} />
        {canManageInventory && (
          <span className={styles.accordionRowAction} onClick={(e) => e.stopPropagation()}>
            <IconButton icon={Pencil} onClick={() => actions.onEditRoom(room)} title={t.edit} />
          </span>
        )}
      </div>

      {roomOpen && (
        <div className={styles.accordionBody}>
          <div className={styles.detailsStrip}>
            <DetailRow label={t.availableBedsLabel} value={room.available_beds} />
            <DetailRow label={t.bedCountLabel} value={room.bed_count} />
            {canManageInventory && (
              <div className={styles.detailsStripActions}>
                {room.is_active ? (
                  <button
                    type="button"
                    className="inv-dangerBtn"
                    onClick={() => actions.onAvailability('room', room, 'inactivate')}
                  >
                    <PowerOff size={13} /> {t.deactivate}
                  </button>
                ) : (
                  <button
                    type="button"
                    className="inv-successBtn"
                    onClick={() => actions.onAvailability('room', room, 'reactivate')}
                  >
                    <Power size={13} /> {t.activate}
                  </button>
                )}
              </div>
            )}
          </div>
          {room.has_missing_bed_records && (
            <p className={styles.inspectorWarning}>
              <AlertTriangle size={13} /> {t.bedRecordsMismatch}
            </p>
          )}

          <SectionHeader
            title={t.bedsTable}
            count={roomBeds.length}
            action={
              canCreateBed && (
                <button type="button" className="inv-secondaryBtn">
                  <Plus size={13} /> {t.addBed}
                </button>
              )
            }
          />
          <div className={styles.tableWrap}>
            {loadingBeds ? (
              <div className={styles.centerInline}>
                <Spinner size={18} />
              </div>
            ) : roomBeds.length === 0 ? (
              <EmptyPanel title={t.noBeds} />
            ) : (
              <BedTable
                t={t}
                beds={roomBeds}
                selectedBedId={selectedBedId}
                canManageInventory={canManageInventory}
                canDeleteBed={canDeleteBed}
                onSelect={actions.onSelectBed}
                onEdit={actions.onEditBed}
                onDelete={actions.onDeleteBed}
              />
            )}
            <p className={styles.bedCapabilityNote}>{t.bedNoActionsSupported}</p>
          </div>
        </div>
      )}
    </div>
  );
}
