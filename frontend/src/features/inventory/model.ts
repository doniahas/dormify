// UI-level types owned by the Buildings (inventory) feature: the filter
// values, the create/edit editor state and its form values, the availability
// and bed-delete dialogs, the summary metrics and the setup wizard's props.
// Wire types stay in shared/api/contracts and ./types.ts.
import type { Apartment, Bed, Building, DormType, Id, Region, Room } from '../../shared/api/contracts';
import type { Language } from '../../shared/i18n';
import type { BuildingsStrings } from './BuildingsPage.strings';

/** The active/inactive list filter above the navigator. */
export type InventoryStatusFilter = 'active' | 'inactive' | 'all';

/** The entity an editor modal or an availability dialog acts on. */
export type InventoryEntityType = 'building' | 'apartment' | 'room' | 'bed';

export type EditorMode = 'create' | 'edit';

/**
 * A numeric input's value as the editor holds it: the record's number when
 * the form opened, or the raw text typed since (an empty string clears it).
 */
export type NumericInput = number | string;

export interface BuildingFormValues {
  number: NumericInput;
  /** The dorm type PK, or '' for the placeholder option. */
  dorm_type: NumericInput;
  gender_restriction: string;
}

export interface ApartmentFormValues {
  number: string;
  category: string;
  apartment_type: string;
  room_count: NumericInput;
  /** '' means "not set" and is sent as null. */
  apartment_capacity: NumericInput;
  inactive_reason: string;
}

export interface RoomFormValues {
  name: string;
  capacity: NumericInput;
}

export interface BedFormValues {
  label: string;
}

interface EditorBase<T extends InventoryEntityType, D> {
  type: T;
  mode: EditorMode;
  /** The record being edited; null while creating. */
  id: Id | null;
  /** The parent the record belongs to (building for an apartment, apartment for a room, room for a bed). */
  parentId: Id | null;
  data: D;
  saving: boolean;
  error: string;
}

export type BuildingEditor = EditorBase<'building', BuildingFormValues>;
export type ApartmentEditor = EditorBase<'apartment', ApartmentFormValues>;
export type RoomEditor = EditorBase<'room', RoomFormValues>;
export type BedEditor = EditorBase<'bed', BedFormValues>;

/** The create/edit modal's state: one entity at a time, or closed (null). */
export type InventoryEditor = BuildingEditor | ApartmentEditor | RoomEditor | BedEditor;

/** A partial update of whichever form is open. */
export type EditorDataPatch = Partial<BuildingFormValues & ApartmentFormValues & RoomFormValues & BedFormValues>;

/**
 * The records the editor modal shows alongside the form: the building,
 * apartment and room the entity sits under, and (in edit mode) the record
 * itself for its live counters.
 */
export interface EditorContext {
  building: Building | null;
  apartment: Apartment | null;
  room: Room | null;
  apartmentRecord: Apartment | null;
  roomRecord: Room | null;
  bedRecord: Bed | null;
}

export type AvailabilityTargetType = 'building' | 'apartment' | 'room';
export type AvailabilityAction = 'inactivate' | 'reactivate';

/** The what-if simulation summary the deactivation dialog renders. */
export type AvailabilityImpact = {
  lost_apartments?: number;
  lost_rooms?: number;
  lost_beds?: number;
  affected_students_count?: number;
};

export interface AvailabilityDialogState {
  targetType: AvailabilityTargetType;
  targetId: Id;
  /** "Building number 10", "Apartment number 3", "Room name/number B". */
  label: string;
  action: AvailabilityAction;
  impact: AvailabilityImpact | null | undefined;
  loadingImpact: boolean;
  reason: string;
  note: string;
  saving: boolean;
  error: string;
}

export interface DeleteBedDialogState {
  id: Id;
  label: string;
  occupied: boolean;
  saving: boolean;
  error: string;
}

/** The six counters of the summary strip. */
export interface InventorySummaryMetrics {
  buildings: number;
  apartments: number;
  rooms: number;
  beds: number;
  occupied: number;
  free: number;
}

export type CategoryLabels = BuildingsStrings['categoryLabels'];
export type ApartmentTypeLabels = BuildingsStrings['apartmentTypeLabels'];
export type GenderRestrictionLabels = BuildingsStrings['genderRestrictionLabels'];
export type DeactivationReasonOption = BuildingsStrings['deactivationReasons'][number];

/** The selectable catalog of the current region, as the breadcrumb and editors read it. */
export interface RegionSelection {
  selectedRegion: Region | null;
  selectedDormType: DormType | null;
}

/**
 * The contract between the page and BuildingSetupWizard.jsx (a JS child that
 * keeps its own markup and styles). `onClose` receives the created building
 * when the wizard is dismissed after a successful create, otherwise nothing.
 */
export interface BuildingSetupWizardProps {
  language: Language;
  dormTypesInRegion: DormType[];
  defaultDormTypeId: Id | '';
  regionName: string;
  categoryLabels: CategoryLabels;
  apartmentTypeLabels: ApartmentTypeLabels;
  genderRestrictionLabels: GenderRestrictionLabels;
  onClose: (building?: Building | null) => void;
  onCompleted: (building: Building) => void;
}
