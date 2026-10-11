import React from 'react';
import { Search, X } from 'lucide-react';
import type { DormType, Id, Region } from '../../../shared/api/contracts';
import type { Language } from '../../../shared/i18n';
import { localizeRegionName } from '../../../shared/lib/locationNames';
import type { BuildingsStrings } from '../BuildingsPage.strings';
import styles from '../BuildingsPage.module.css';
import { dormTypeLabelText } from '../inventoryHelpers';
import type { InventoryStatusFilter } from '../model';

export interface InventoryFilterBarProps {
  t: BuildingsStrings;
  language: Language;
  regions: Region[];
  selectedRegionId: Id;
  /** Only central admins and region bosses may switch region. */
  canChangeRegion: boolean;
  onRegionChange: (regionId: string) => void;
  dormTypesInRegion: DormType[];
  selectedDormTypeId: string;
  onDormTypeChange: (dormTypeId: string) => void;
  statusFilter: InventoryStatusFilter;
  onStatusChange: (status: InventoryStatusFilter) => void;
  searchQuery: string;
  onSearchChange: (query: string) => void;
}

/** Region, dorm type and status selects plus the search box. */
export function InventoryFilterBar({
  t, language, regions, selectedRegionId, canChangeRegion, onRegionChange,
  dormTypesInRegion, selectedDormTypeId, onDormTypeChange,
  statusFilter, onStatusChange, searchQuery, onSearchChange,
}: InventoryFilterBarProps): React.ReactElement {
  return (
    <div className={styles.filterBar}>
      <div className={styles.filterField}>
        <label>{t.chooseRegion}</label>
        <select value={selectedRegionId} disabled={!canChangeRegion} onChange={(e) => onRegionChange(e.target.value)}>
          {regions.map((region) => (
            <option key={region.id} value={region.id}>
              {localizeRegionName(region, language)}
            </option>
          ))}
        </select>
      </div>
      <div className={styles.filterField}>
        <label>{t.chooseDormType}</label>
        <select value={selectedDormTypeId} onChange={(e) => onDormTypeChange(e.target.value)}>
          <option value="all">{t.allDormTypes}</option>
          {dormTypesInRegion.map((dt) => (
            <option key={dt.id} value={dt.id}>
              {dormTypeLabelText(dt, language)}
            </option>
          ))}
        </select>
      </div>
      <div className={styles.filterField}>
        <label>{t.status}</label>
        <select value={statusFilter} onChange={(e) => onStatusChange(e.target.value as InventoryStatusFilter)}>
          <option value="active">{t.statusActive}</option>
          <option value="inactive">{t.statusInactive}</option>
          <option value="all">{t.statusAll}</option>
        </select>
      </div>
      <div className={styles.filterSearch}>
        <Search size={15} />
        <input value={searchQuery} onChange={(e) => onSearchChange(e.target.value)} placeholder={t.search} />
        {searchQuery && (
          <button type="button" onClick={() => onSearchChange('')} aria-label="clear">
            <X size={14} />
          </button>
        )}
      </div>
    </div>
  );
}
