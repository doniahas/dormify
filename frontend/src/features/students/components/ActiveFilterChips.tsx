import React from 'react';
import { X } from 'lucide-react';
import { sameId } from '../../../shared/api/normalize';
import type { Language } from '../../../shared/i18n';
import { localizeGender } from '../../../shared/lib/genderLabels';
import { localizeRegionName } from '../../../shared/lib/locationNames';
import type { StudentFilters } from '../model';
import type { StudentsStrings } from '../StudentsPage.strings';
import type { StudentFilterOptions } from '../types';
import styles from '../StudentsPage.module.css';

export interface ActiveFilterChipsProps {
  t: StudentsStrings;
  language: Language;
  filters: StudentFilters;
  filterOptions: StudentFilterOptions | null;
  onRemove: (key: keyof StudentFilters, value: string) => void;
  onClearAll: () => void;
}

/** One removable chip per drawer selection, plus "Clear all". */
export function ActiveFilterChips({
  t, language, filters, filterOptions, onRemove, onClearAll,
}: ActiveFilterChipsProps): React.ReactElement {
  const regionName = (regionId: string): string => {
    const region = filterOptions?.regions?.find((r) => sameId(r.id, regionId));
    return region ? localizeRegionName(region, language) : regionId;
  };
  const buildingName = (buildingId: string): string => {
    const building = filterOptions?.buildings?.find((b) => sameId(b.id, buildingId));
    return t.buildingChip(building ? building.name : buildingId);
  };
  const religionName = (value: string): string =>
    (filterOptions?.religions || []).find((r) => r.id === value)?.name || value;

  return (
    <div className={styles.activeFilterChips}>
      {filters.genders.map((v) => (
        <span key={v} className={styles.filterChip}>
          {localizeGender(v, language) || v}
          <button type="button" onClick={() => onRemove('genders', v)}><X size={12} /></button>
        </span>
      ))}
      {filters.religions.map((v) => (
        <span key={v} className={styles.filterChip}>
          {religionName(v)}
          <button type="button" onClick={() => onRemove('religions', v)}><X size={12} /></button>
        </span>
      ))}
      {filters.assignmentStatuses.map((v) => (
        <span key={v} className={styles.filterChip}>{v === 'assigned' ? t.chipAssigned : t.chipUnassigned}
          <button type="button" onClick={() => onRemove('assignmentStatuses', v)}><X size={12} /></button>
        </span>
      ))}
      {filters.regions.map((regionId) => (
        <span key={regionId} className={styles.filterChip}>{regionName(regionId)}
          <button type="button" onClick={() => onRemove('regions', regionId)}><X size={12} /></button>
        </span>
      ))}
      {filters.buildings.map((buildingId) => (
        <span key={buildingId} className={styles.filterChip}>{buildingName(buildingId)}
          <button type="button" onClick={() => onRemove('buildings', buildingId)}><X size={12} /></button>
        </span>
      ))}
      <button type="button" className={styles.clearAllChip} onClick={onClearAll}>{t.clearAll}</button>
    </div>
  );
}
