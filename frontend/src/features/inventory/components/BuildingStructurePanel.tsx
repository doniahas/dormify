import React from 'react';
import { Building2, ChevronDown, Pencil, Plus, Power, PowerOff } from 'lucide-react';
import type { Apartment, Bed, Building, Id, Room } from '../../../shared/api/contracts';
import type { Language } from '../../../shared/i18n';
import { cx } from '../../../shared/lib/classNames';
import { localizeById, localizeDormTypeName } from '../../../shared/lib/locationNames';
import type { BuildingsStrings } from '../BuildingsPage.strings';
import pageStyles from '../BuildingsPage.module.css';
import type { AvailabilityAction, AvailabilityTargetType } from '../model';
import { ApartmentAccordion } from './ApartmentAccordion';
import { DetailRow, EmptyPanel, IconButton, SectionHeader, Spinner, StatusBadge } from './InventoryPrimitives';
import styles from './InventoryPanels.module.css';

/** What the structure panel (and the accordions inside it) can ask the page to do. */
export interface StructureActions {
  onEditBuilding: (building: Building) => void;
  onAvailability: (targetType: AvailabilityTargetType, target: Building | Apartment | Room, action: AvailabilityAction) => void;
  /** Opens the create-apartment editor under the selected building. */
  onCreateApartment: () => void;
  onEditApartment: (apartment: Apartment) => void;
  onSelectApartment: (apartmentId: Id) => void;
  /** Opens the create-room editor under the selected apartment. */
  onCreateRoom: () => void;
  onEditRoom: (room: Room) => void;
  onSelectRoom: (roomId: Id) => void;
  onSelectBed: (bedId: Id) => void;
  onEditBed: (bed: Bed) => void;
  onDeleteBed: (bed: Bed) => void;
}

export interface BuildingStructurePanelProps {
  t: BuildingsStrings;
  language: Language;
  selectedBuilding: Building | null;
  loadingStructure: boolean;
  buildingDetailsOpen: boolean;
  onToggleDetails: () => void;
  canManageInventory: boolean;
  canCreateBed: boolean;
  canDeleteBed: boolean;
  /** The selected building's apartments after the search filter. */
  apartments: Apartment[];
  selectedApartmentId: Id;
  /** The selected apartment's rooms after the search filter. */
  rooms: Room[];
  selectedRoomId: Id;
  roomBeds: Bed[];
  selectedBedId: Id;
  loadingBeds: boolean;
  actions: StructureActions;
}

/** The right panel: the selected building's summary bar, details and apartment accordion. */
export function BuildingStructurePanel({
  t, language, selectedBuilding, loadingStructure, buildingDetailsOpen, onToggleDetails,
  canManageInventory, canCreateBed, canDeleteBed,
  apartments, selectedApartmentId, rooms, selectedRoomId, roomBeds, selectedBedId, loadingBeds, actions,
}: BuildingStructurePanelProps): React.ReactElement {
  return (
    <div className={pageStyles.panel}>
      {!selectedBuilding ? (
        <EmptyPanel icon={Building2} title={t.selectBuildingTitle} hint={t.selectBuildingHint} />
      ) : loadingStructure ? (
        <div className={styles.centerInline}>
          <Spinner size={20} />
        </div>
      ) : (
        <>
          <div className={styles.summaryBar}>
            <div className={styles.summaryBarMain}>
              <Building2 size={17} />
              <div>
                <div className={styles.summaryBarTitle}>
                  {t.buildingNumberLabel} {selectedBuilding.number}
                </div>
                <div className={styles.summaryBarMeta}>{localizeDormTypeName({ code: selectedBuilding.dorm_type_code, name: selectedBuilding.dorm_type_name }, language)}</div>
              </div>
              <StatusBadge active={selectedBuilding.is_active} activeText={t.statusActive} inactiveText={t.statusInactive} />
            </div>
            <div className={styles.summaryBarActions}>
              <button type="button" className={styles.linkBtn} onClick={onToggleDetails} aria-expanded={buildingDetailsOpen}>
                {buildingDetailsOpen ? t.hideDetails : t.viewDetails}
                <ChevronDown size={13} className={cx(styles.chevron, buildingDetailsOpen && styles.isOpen)} />
              </button>
              {canManageInventory && (
                <>
                  <IconButton icon={Pencil} onClick={() => actions.onEditBuilding(selectedBuilding)} title={t.edit} />
                  {selectedBuilding.is_active ? (
                    <IconButton
                      icon={PowerOff}
                      tone="danger"
                      onClick={() => actions.onAvailability('building', selectedBuilding, 'inactivate')}
                      title={t.deactivate}
                    />
                  ) : (
                    <IconButton
                      icon={Power}
                      tone="success"
                      onClick={() => actions.onAvailability('building', selectedBuilding, 'reactivate')}
                      title={t.activate}
                    />
                  )}
                </>
              )}
            </div>
          </div>

          {buildingDetailsOpen && (
            <div className={styles.detailsStrip}>
              <DetailRow label={t.regionLabel} value={localizeById(selectedBuilding.region, selectedBuilding.region_name, language)} />
              <DetailRow
                label={t.genderRestrictionLabel}
                value={t.genderRestrictionLabels[selectedBuilding.gender_restriction] || t.noRestriction}
              />
              <DetailRow label={t.apartmentCountLabel} value={selectedBuilding.apartment_count} />
              <DetailRow label={t.roomCountLabel} value={selectedBuilding.room_count} />
              <DetailRow label={t.bedCountLabel} value={selectedBuilding.bed_count} />
              <DetailRow label={t.occupiedBedsLabel} value={selectedBuilding.occupied_beds} />
              <DetailRow label={t.freeBedsLabel} value={selectedBuilding.free_beds} />
            </div>
          )}

          <SectionHeader
            title={t.apartmentsTable}
            count={apartments.length}
            action={
              canManageInventory && (
                <button type="button" className="inv-secondaryBtn" onClick={actions.onCreateApartment}>
                  <Plus size={13} /> {t.addApartment}
                </button>
              )
            }
          />

          {apartments.length === 0 ? (
            <EmptyPanel title={t.noApartments} />
          ) : (
            <div className={styles.accordionList}>
              {apartments.map((apt) => (
                <ApartmentAccordion
                  key={apt.id}
                  t={t}
                  apartment={apt}
                  isOpen={String(selectedApartmentId) === String(apt.id)}
                  canManageInventory={canManageInventory}
                  canCreateBed={canCreateBed}
                  canDeleteBed={canDeleteBed}
                  rooms={rooms}
                  selectedRoomId={selectedRoomId}
                  roomBeds={roomBeds}
                  selectedBedId={selectedBedId}
                  loadingBeds={loadingBeds}
                  actions={actions}
                />
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}
