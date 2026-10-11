import React from 'react';
import { Info } from 'lucide-react';
import type { DormType } from '../../../shared/api/contracts';
import type { Language } from '../../../shared/i18n';
import type { BuildingsStrings } from '../BuildingsPage.strings';
import { dormTypeLabelText } from '../inventoryHelpers';
import type {
  ApartmentFormValues,
  BedFormValues,
  BuildingFormValues,
  EditorContext,
  EditorDataPatch,
  EditorMode,
  RoomFormValues,
} from '../model';
import styles from './InventoryDialogs.module.css';
import { FormField, ModalSection, ReadOnlyField, StatusBadge } from './InventoryPrimitives';

// The four forms of the editor modal. Field ids are the ones the page always
// rendered; the grids, sections and read-only fields use the global modal
// chrome (BuildingsPage.global.css) shared with BuildingSetupWizard.jsx.

export interface BuildingFieldsProps {
  t: BuildingsStrings;
  language: Language;
  mode: EditorMode;
  data: BuildingFormValues;
  ctx: EditorContext;
  dormTypesInRegion: DormType[];
  onPatch: (patch: EditorDataPatch) => void;
}

export function BuildingFields({ t, language, mode, data, ctx, dormTypesInRegion, onPatch }: BuildingFieldsProps): React.ReactElement {
  return (
    <>
      <ModalSection title={t.sectionGeneralInfo}>
        <div className="inv-modalGrid">
          <FormField label={t.buildingNumberLabel} htmlFor="inv-b-number">
            <input
              id="inv-b-number"
              type="number"
              value={data.number}
              onChange={(e) => onPatch({ number: e.target.value })}
            />
          </FormField>
          <FormField label={t.dormTypeLabel} htmlFor="inv-b-dormtype">
            <select
              id="inv-b-dormtype"
              value={data.dorm_type}
              onChange={(e) => onPatch({ dorm_type: e.target.value })}
            >
              <option value="">—</option>
              {dormTypesInRegion.map((dt) => (
                <option key={dt.id} value={dt.id}>
                  {dormTypeLabelText(dt, language)}
                </option>
              ))}
            </select>
          </FormField>
        </div>
      </ModalSection>

      <ModalSection title={t.sectionAllocationConfig}>
        <div className="inv-modalGrid is-single">
          <FormField label={t.genderRestrictionLabel} htmlFor="inv-b-restriction" hint={t.genderRestrictionHint}>
            <select
              id="inv-b-restriction"
              value={data.gender_restriction}
              onChange={(e) => onPatch({ gender_restriction: e.target.value })}
            >
              <option value="">{t.noRestriction}</option>
              <option value="male">{t.genderRestrictionLabels.male}</option>
              <option value="female">{t.genderRestrictionLabels.female}</option>
            </select>
          </FormField>
        </div>
      </ModalSection>

      {mode === 'edit' && (
        <ModalSection title={t.sectionStatus}>
          <div className={styles.statusRow}>
            <StatusBadge active={ctx.building?.is_active} activeText={t.statusActive} inactiveText={t.statusInactive} />
          </div>
          <div className="inv-infoCallout">
            <Info size={14} />
            <span>{t.availabilityManagedSeparately}</span>
          </div>
        </ModalSection>
      )}
    </>
  );
}

export interface ApartmentFieldsProps {
  t: BuildingsStrings;
  mode: EditorMode;
  data: ApartmentFormValues;
  ctx: EditorContext;
  onPatch: (patch: EditorDataPatch) => void;
}

export function ApartmentFields({ t, mode, data, ctx, onPatch }: ApartmentFieldsProps): React.ReactElement {
  const building = ctx.building;
  const record = ctx.apartmentRecord;
  return (
    <>
      <ModalSection title={t.sectionGeneralInfo}>
        <div className="inv-modalGrid">
          <FormField label={t.apartmentNumberLabel} htmlFor="inv-a-number">
            <input
              id="inv-a-number"
              value={data.number}
              onChange={(e) => onPatch({ number: e.target.value })}
            />
          </FormField>
          <ReadOnlyField
            label={t.parentBuildingLabel}
            value={building ? `${t.buildingNumberLabel} ${building.number}` : '—'}
          />
          <ReadOnlyField label={t.dormTypeLabel} value={building?.dorm_type_name || '—'} />
        </div>
      </ModalSection>

      <ModalSection title={t.sectionApartmentClassification}>
        <div className="inv-modalGrid">
          <FormField label={t.genderCategoryLabel} htmlFor="inv-a-category">
            <select
              id="inv-a-category"
              value={data.category}
              onChange={(e) => onPatch({ category: e.target.value })}
            >
              <option value="male">{t.categoryLabels.male}</option>
              <option value="female">{t.categoryLabels.female}</option>
              <option value="mixed">{t.categoryLabels.mixed}</option>
            </select>
          </FormField>
          <FormField label={t.housingTypeLabel} htmlFor="inv-a-type">
            <select
              id="inv-a-type"
              value={data.apartment_type}
              onChange={(e) => onPatch({ apartment_type: e.target.value })}
            >
              <option value="single">{t.apartmentTypeLabels.single}</option>
              <option value="couple">{t.apartmentTypeLabels.couple}</option>
              <option value="family">{t.apartmentTypeLabels.family}</option>
            </select>
          </FormField>
        </div>
      </ModalSection>

      <ModalSection title={t.sectionCapacityConfig}>
        <div className="inv-modalGrid">
          <FormField label={t.plannedRoomCountLabel} htmlFor="inv-a-roomcount">
            <input
              id="inv-a-roomcount"
              type="number"
              value={data.room_count}
              onChange={(e) => onPatch({ room_count: e.target.value })}
            />
          </FormField>
          <FormField label={t.apartmentCapacityLabel} htmlFor="inv-a-capacity">
            <input
              id="inv-a-capacity"
              type="number"
              value={data.apartment_capacity}
              onChange={(e) => onPatch({ apartment_capacity: e.target.value })}
            />
          </FormField>
        </div>
        {record && (
          <div className="inv-summaryRow">
            <div className="inv-summaryItem">
              <span>{t.actualRoomCountLabel}</span>
              <strong>{record.actual_room_count}</strong>
            </div>
            <div className="inv-summaryItem">
              <span>{t.totalBedsLabel}</span>
              <strong>{record.bed_count}</strong>
            </div>
            <div className="inv-summaryItem">
              <span>{t.occupiedBedsLabel}</span>
              <strong>{record.occupied_beds}</strong>
            </div>
            <div className="inv-summaryItem">
              <span>{t.freeBedsLabel}</span>
              <strong>{record.free_beds}</strong>
            </div>
          </div>
        )}
      </ModalSection>

      {mode === 'edit' && (
        <ModalSection title={t.sectionAvailabilityInfo}>
          <div className={styles.statusRow}>
            <StatusBadge active={record?.is_active} activeText={t.statusActive} inactiveText={t.statusInactive} />
          </div>
          {record && !record.is_active && (
            <ReadOnlyField label={t.inactiveReasonLabel} value={record.inactive_reason_display || t.none} />
          )}
          <div className="inv-infoCallout">
            <Info size={14} />
            <span>{t.availabilityManagedSeparately}</span>
          </div>
        </ModalSection>
      )}
    </>
  );
}

export interface RoomFieldsProps {
  t: BuildingsStrings;
  mode: EditorMode;
  data: RoomFormValues;
  ctx: EditorContext;
  onPatch: (patch: EditorDataPatch) => void;
}

export function RoomFields({ t, mode, data, ctx, onPatch }: RoomFieldsProps): React.ReactElement {
  const record = ctx.roomRecord;
  return (
    <>
      <ModalSection title={t.sectionGeneralInfo}>
        <div className="inv-modalGrid">
          <FormField label={t.roomNameLabel} htmlFor="inv-r-name">
            <input
              id="inv-r-name"
              value={data.name}
              onChange={(e) => onPatch({ name: e.target.value })}
            />
          </FormField>
          <FormField label={t.capacityLabel} htmlFor="inv-r-capacity">
            <input
              id="inv-r-capacity"
              type="number"
              value={data.capacity}
              onChange={(e) => onPatch({ capacity: e.target.value })}
            />
          </FormField>
        </div>
        {record && (
          <div className="inv-summaryRow">
            <div className="inv-summaryItem">
              <span>{t.occupancyLabel}</span>
              <strong>{record.current_occupancy}</strong>
            </div>
            <div className="inv-summaryItem">
              <span>{t.availableBedsLabel}</span>
              <strong>{record.available_beds}</strong>
            </div>
            <div className="inv-summaryItem">
              <span>{t.bedCountLabel}</span>
              <strong>{record.bed_count}</strong>
            </div>
          </div>
        )}
      </ModalSection>

      {mode === 'edit' && (
        <ModalSection title={t.sectionAvailabilityInfo}>
          <div className={styles.statusRow}>
            <StatusBadge active={record?.is_active} activeText={t.statusActive} inactiveText={t.statusInactive} />
          </div>
          <div className="inv-infoCallout">
            <Info size={14} />
            <span>{t.availabilityManagedSeparately}</span>
          </div>
        </ModalSection>
      )}
    </>
  );
}

export interface BedFieldsProps {
  t: BuildingsStrings;
  data: BedFormValues;
  ctx: EditorContext;
  onPatch: (patch: EditorDataPatch) => void;
}

export function BedFields({ t, data, ctx, onPatch }: BedFieldsProps): React.ReactElement {
  return (
    <ModalSection title={t.sectionGeneralInfo}>
      <div className="inv-modalGrid is-single">
        <FormField label={t.bedLabelField} htmlFor="inv-bed-label">
          <input
            id="inv-bed-label"
            value={data.label}
            onChange={(e) => onPatch({ label: e.target.value })}
          />
        </FormField>
      </div>
      <div className="inv-modalGrid">
        <ReadOnlyField label={t.parentRoomLabel} value={ctx.room?.name} />
        <ReadOnlyField label={t.parentApartmentLabel} value={ctx.apartment?.number} />
        <ReadOnlyField label={t.buildingNumberLabel} value={ctx.building?.number} />
        <ReadOnlyField label={t.availabilityLabel} value={ctx.bedRecord?.is_occupied ? t.occupied : t.available} />
      </div>
    </ModalSection>
  );
}
