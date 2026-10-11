import React from 'react';
import { ChevronDown, Home, Pencil, Plus, Power, PowerOff } from 'lucide-react';
import type { Apartment, Bed, Id, Room } from '../../../shared/api/contracts';
import { idOf } from '../../../shared/api/normalize';
import { cx } from '../../../shared/lib/classNames';
import type { BuildingsStrings } from '../BuildingsPage.strings';
import type { StructureActions } from './BuildingStructurePanel';
import { DetailRow, EmptyPanel, IconButton, OccupancyBadge, SectionHeader, StatusBadge } from './InventoryPrimitives';
import styles from './InventoryPanels.module.css';
import { RoomAccordion } from './RoomAccordion';

export interface ApartmentAccordionProps {
  t: BuildingsStrings;
  apartment: Apartment;
  isOpen: boolean;
  canManageInventory: boolean;
  canCreateBed: boolean;
  canDeleteBed: boolean;
  /** The open apartment's rooms after the search filter. */
  rooms: Room[];
  selectedRoomId: Id;
  roomBeds: Bed[];
  selectedBedId: Id;
  loadingBeds: boolean;
  actions: StructureActions;
}

/** One apartment row; expanded, it shows its details, availability action and rooms. */
export function ApartmentAccordion({
  t, apartment: apt, isOpen, canManageInventory, canCreateBed, canDeleteBed,
  rooms, selectedRoomId, roomBeds, selectedBedId, loadingBeds, actions,
}: ApartmentAccordionProps): React.ReactElement {
  return (
    <div className={cx(styles.accordionItem, isOpen && styles.isOpen, !apt.is_active && styles.isInactive)}>
      <div
        role="button"
        tabIndex={0}
        aria-expanded={isOpen}
        className={styles.accordionHeader}
        onClick={() => actions.onSelectApartment(apt.id)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            actions.onSelectApartment(apt.id);
          }
        }}
      >
        <ChevronDown size={14} className={cx(styles.chevron, isOpen && styles.isOpen)} />
        <Home size={15} />
        <span className={styles.accordionTitle}>
          {t.apartmentNumberLabel} {apt.number}
        </span>
        <span className={styles.accordionTag}>{t.categoryLabels[apt.category] || apt.category}</span>
        <span className={styles.accordionTag}>{t.apartmentTypeLabels[apt.apartment_type] || apt.apartment_type}</span>
        <span className={styles.accordionMeta}>
          {apt.actual_room_count} {t.roomsCount}
        </span>
        <OccupancyBadge occupied={apt.occupied_beds} total={apt.bed_count} />
        <StatusBadge active={apt.is_active} activeText={t.statusActive} inactiveText={t.statusInactive} />
        {canManageInventory && (
          <span className={styles.accordionRowAction} onClick={(e) => e.stopPropagation()}>
            <IconButton icon={Pencil} onClick={() => actions.onEditApartment(apt)} title={t.edit} />
          </span>
        )}
      </div>

      {isOpen && (
        <div className={styles.accordionBody}>
          <div className={styles.detailsStrip}>
            <DetailRow label={t.apartmentCapacityLabel} value={apt.apartment_capacity ?? '—'} />
            <DetailRow label={t.totalBedsLabel} value={apt.bed_count} />
            <DetailRow label={t.freeBedsLabel} value={apt.free_beds} />
            {!apt.is_active && <DetailRow label={t.inactiveReasonLabel} value={apt.inactive_reason_display || t.none} />}
            {canManageInventory && (
              <div className={styles.detailsStripActions}>
                {apt.is_active ? (
                  <button
                    type="button"
                    className="inv-dangerBtn"
                    onClick={() => actions.onAvailability('apartment', apt, 'inactivate')}
                  >
                    <PowerOff size={13} /> {t.deactivate}
                  </button>
                ) : (
                  <button
                    type="button"
                    className="inv-successBtn"
                    onClick={() => actions.onAvailability('apartment', apt, 'reactivate')}
                  >
                    <Power size={13} /> {t.activate}
                  </button>
                )}
              </div>
            )}
          </div>

          <SectionHeader
            title={t.roomsTable}
            count={rooms.length}
            action={
              canManageInventory && (
                <button type="button" className="inv-secondaryBtn" onClick={actions.onCreateRoom}>
                  <Plus size={13} /> {t.addRoom}
                </button>
              )
            }
          />

          {rooms.length === 0 ? (
            <EmptyPanel title={t.noRooms} />
          ) : (
            <div className={cx(styles.accordionList, styles.accordionListNested)}>
              {rooms.map((room) => (
                <RoomAccordion
                  key={room.id}
                  t={t}
                  room={room}
                  isOpen={idOf(selectedRoomId) === idOf(room.id)}
                  canManageInventory={canManageInventory}
                  canCreateBed={canCreateBed}
                  canDeleteBed={canDeleteBed}
                  roomBeds={roomBeds}
                  selectedBedId={selectedBedId}
                  loadingBeds={loadingBeds}
                  actions={actions}
                />
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
