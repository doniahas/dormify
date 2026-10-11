import React from 'react';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import type { Apartment, Bed, Building, DormType, Region, Room } from '../../../shared/api/contracts';
import type { Language } from '../../../shared/i18n';
import { localizeDormTypeName, localizeRegionName } from '../../../shared/lib/locationNames';
import type { BuildingsStrings } from '../BuildingsPage.strings';
import styles from '../BuildingsPage.module.css';

export interface InventoryBreadcrumbProps {
  t: BuildingsStrings;
  language: Language;
  selectedRegion: Region | null;
  selectedDormType: DormType | null;
  selectedBuilding: Building | null;
  selectedApartment: Apartment | null;
  selectedRoom: Room | null;
  selectedBed: Bed | null;
}

/** Inventory › region › dorm type › building › apartment › room › bed. */
export function InventoryBreadcrumb({
  t, language, selectedRegion, selectedDormType, selectedBuilding, selectedApartment, selectedRoom, selectedBed,
}: InventoryBreadcrumbProps): React.ReactElement {
  const BreadcrumbChevron = language === 'he' ? ChevronLeft : ChevronRight;
  return (
    <div className={styles.breadcrumb}>
      <span>{t.breadcrumbRoot}</span>
      {selectedRegion && (
        <>
          <BreadcrumbChevron size={13} />
          <span>{localizeRegionName(selectedRegion, language)}</span>
        </>
      )}
      {(selectedDormType || selectedBuilding) && (
        <>
          <BreadcrumbChevron size={13} />
          <span>
            {selectedBuilding
              ? localizeDormTypeName({ code: selectedBuilding.dorm_type_code, name: selectedBuilding.dorm_type_name }, language)
              : (selectedDormType ? localizeDormTypeName(selectedDormType, language) : '')}
          </span>
        </>
      )}
      {selectedBuilding && (
        <>
          <BreadcrumbChevron size={13} />
          <span className={styles.breadcrumbActive}>
            {t.buildingNumberLabel} {selectedBuilding.number}
          </span>
        </>
      )}
      {selectedApartment && (
        <>
          <BreadcrumbChevron size={13} />
          <span className={styles.breadcrumbActive}>
            {t.apartmentNumberLabel} {selectedApartment.number}
          </span>
        </>
      )}
      {selectedRoom && (
        <>
          <BreadcrumbChevron size={13} />
          <span className={styles.breadcrumbActive}>
            {t.colRoom} {selectedRoom.name}
          </span>
        </>
      )}
      {selectedBed && (
        <>
          <BreadcrumbChevron size={13} />
          <span className={styles.breadcrumbActive}>
            {t.colBed} {selectedBed.label}
          </span>
        </>
      )}
    </div>
  );
}
