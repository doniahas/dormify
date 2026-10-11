import React from 'react';
import { Building2, Plus } from 'lucide-react';
import type { Building, Id } from '../../../shared/api/contracts';
import { idOf } from '../../../shared/api/normalize';
import { cx } from '../../../shared/lib/classNames';
import type { BuildingsStrings } from '../BuildingsPage.strings';
import pageStyles from '../BuildingsPage.module.css';
import { EmptyPanel, IconButton, OccupancyBadge, SectionHeader, StatusBadge } from './InventoryPrimitives';
import styles from './InventoryPanels.module.css';

export interface BuildingNavigatorProps {
  t: BuildingsStrings;
  /** The buildings after the filters. */
  buildings: Building[];
  selectedBuildingId: Id;
  canManageInventory: boolean;
  canAddBuilding: boolean;
  onAddBuilding: () => void;
  onSelect: (buildingId: Id) => void;
}

/** The left panel: the filtered building list with its counters and status. */
export function BuildingNavigator({
  t, buildings, selectedBuildingId, canManageInventory, canAddBuilding, onAddBuilding, onSelect,
}: BuildingNavigatorProps): React.ReactElement {
  return (
    <div className={pageStyles.panel}>
      <SectionHeader
        title={t.navigatorTitle}
        count={buildings.length}
        action={
          canManageInventory && (
            <IconButton icon={Plus} onClick={onAddBuilding} title={t.addBuilding} disabled={!canAddBuilding} />
          )
        }
      />
      <div className={styles.buildingList}>
        {buildings.length === 0 ? (
          <EmptyPanel icon={Building2} title={t.noBuildings} />
        ) : (
          buildings.map((building) => {
            const selected = idOf(selectedBuildingId) === idOf(building.id);
            return (
              <button
                key={building.id}
                type="button"
                className={cx(styles.buildingItem, selected && styles.isSelected, !building.is_active && styles.isInactive)}
                aria-pressed={selected}
                onClick={() => onSelect(building.id)}
              >
                <div className={styles.buildingItemTop}>
                  <span className={styles.buildingItemNumber}>
                    {t.buildingNumberLabel} {building.number}
                  </span>
                  <StatusBadge active={building.is_active} activeText={t.statusActive} inactiveText={t.statusInactive} />
                </div>
                <div className={styles.buildingItemMeta}>{building.dorm_type_name}</div>
                <div className={styles.buildingItemCounts}>
                  {building.apartment_count} {t.apartmentsCount} · {building.room_count} {t.roomsCount} · {building.bed_count} {t.bedsCount}
                </div>
                <div className={styles.buildingItemBottom}>
                  <OccupancyBadge occupied={building.occupied_beds} total={building.bed_count} label={t.occupiedShort} />
                  {building.gender_restriction && (
                    <span className={styles.genderTag}>{t.genderRestrictionLabels[building.gender_restriction]}</span>
                  )}
                </div>
              </button>
            );
          })
        )}
      </div>
    </div>
  );
}
