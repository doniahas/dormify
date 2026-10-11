// Pure helpers of the Buildings feature: filtering and summarising the
// inventory tree, the editor forms and their validation, the exact backend
// payloads the page has always sent, and the editor's context lines. No
// React, no I/O (the one adapter reference is a capability probe).
import type {
  Apartment,
  Bed,
  Building,
  DormType,
  FieldErrors,
  Id,
  Region,
  Room,
} from '../../shared/api/contracts';
import { idOf, sameId } from '../../shared/api/normalize';
import type { Language } from '../../shared/i18n';
import { localizeById, localizeDormTypeName, localizeRegionName } from '../../shared/lib/locationNames';
import { dormInventoryAPI } from './api';
import type { BuildingsStrings } from './BuildingsPage.strings';
import type {
  ApartmentFormValues,
  AvailabilityDialogState,
  AvailabilityTargetType,
  BedFormValues,
  BuildingFormValues,
  EditorContext,
  InventoryEditor,
  InventoryStatusFilter,
  InventorySummaryMetrics,
  RoomFormValues,
} from './model';
import type { ApartmentPayload, BedPayload, BuildingPayload, RoomPayload } from './types';

export function normalizeText(value: unknown): string {
  return String(value ?? '').toLowerCase().trim();
}

// A dorm type carries its region as `region`; `region_id` is read first for
// the older serializer shape the page always tolerated.
type DormTypeWithRegionId = DormType & { region_id?: Id | null };

export function getRegionIdFromDormType(dormType: DormType | null | undefined): string {
  const dt = dormType as DormTypeWithRegionId | null | undefined;
  return idOf(dt?.region_id ?? dt?.region);
}

/** The dorm types of the selected region; every dorm type while no region is selected. */
export function dormTypesForRegion(dormTypes: DormType[], selectedRegionId: Id): DormType[] {
  if (!selectedRegionId) return dormTypes;
  return dormTypes.filter((dt) => getRegionIdFromDormType(dt) === idOf(selectedRegionId));
}

/** The navigator list: dorm type, active/inactive and search filters, sorted by number. */
export function filterBuildings(
  buildings: Building[],
  selectedDormTypeId: string,
  statusFilter: InventoryStatusFilter,
  searchQuery: string
): Building[] {
  let list = buildings;

  if (selectedDormTypeId !== 'all') {
    list = list.filter((b) => idOf(b.dorm_type) === idOf(selectedDormTypeId));
  }
  if (statusFilter !== 'all') {
    const wantActive = statusFilter === 'active';
    list = list.filter((b) => Boolean(b.is_active) === wantActive);
  }
  const q = normalizeText(searchQuery);
  if (q) {
    list = list.filter((b) => [b.number, b.dorm_type_name, b.region_name].join(' ').toLowerCase().includes(q));
  }
  return [...list].sort((a, b) => (a.number ?? 0) - (b.number ?? 0));
}

export function filterApartments(apartments: Apartment[], searchQuery: string): Apartment[] {
  const q = normalizeText(searchQuery);
  if (!q) return apartments;
  return apartments.filter((a) => String(a.number ?? '').toLowerCase().includes(q));
}

export function roomsForApartment(rooms: Room[], selectedApartmentId: Id, searchQuery: string): Room[] {
  let list = rooms.filter((r) => idOf(r.apartment) === idOf(selectedApartmentId));
  const q = normalizeText(searchQuery);
  if (q) list = list.filter((r) => String(r.name ?? '').toLowerCase().includes(q));
  return list;
}

type BuildingCounter = 'apartment_count' | 'room_count' | 'bed_count' | 'occupied_beds' | 'free_beds';

/**
 * The summary strip is scoped to region + selected dorm type, independent
 * of the active/inactive list filter (active-only for the 5 capacity
 * metrics, since inactive inventory is out of solver scope; the building
 * count includes both so the numbers stay internally consistent with what
 * staff see in the navigator when status = "all").
 */
export function summarizeBuildings(buildings: Building[], selectedDormTypeId: string): InventorySummaryMetrics {
  const scoped = selectedDormTypeId === 'all' ? buildings : buildings.filter((b) => idOf(b.dorm_type) === idOf(selectedDormTypeId));
  const active = scoped.filter((b) => b.is_active);
  const sum = (field: BuildingCounter): number => active.reduce((acc, b) => acc + (Number(b[field]) || 0), 0);
  return {
    buildings: scoped.length,
    apartments: sum('apartment_count'),
    rooms: sum('room_count'),
    beds: sum('bed_count'),
    occupied: sum('occupied_beds'),
    free: sum('free_beds'),
  };
}

export interface InitialRegionInput {
  regionsList: Region[];
  /** The ?region= query parameter, if any. */
  urlRegion: string | null;
  userRegionId: string;
  canViewAllRegions: boolean;
}

/**
 * The region the page opens on: the user's own region (or the first of the
 * catalog), overridden by a ?region= deep link only when that region exists
 * and the user may view it.
 */
export function resolveInitialRegionId({ regionsList, urlRegion, userRegionId, canViewAllRegions }: InitialRegionInput): string {
  let resolvedRegionId = idOf(userRegionId || regionsList[0]?.id);
  if (urlRegion) {
    const exists =
      regionsList.some((r) => idOf(r.id) === idOf(urlRegion)) &&
      (canViewAllRegions || idOf(urlRegion) === idOf(userRegionId));
    if (exists) resolvedRegionId = idOf(urlRegion);
  }
  return resolvedRegionId;
}

export function composeReason(reason: string, note: string): string {
  return [reason, note].filter(Boolean).join(' — ');
}

/** "Building number 10" / "Apartment number 3" / "Room name/number B" for the availability dialog title. */
export function entityLabel(
  targetType: AvailabilityTargetType,
  target: Building | Apartment | Room,
  t: BuildingsStrings
): string {
  if (targetType === 'building') return `${t.buildingNumberLabel} ${target.number}`;
  if (targetType === 'apartment') return `${t.apartmentNumberLabel} ${target.number}`;
  return `${t.roomNameLabel} ${'name' in target ? target.name : ''}`;
}

/** The reason text sent with an availability change. */
export function availabilityReasonText(dialog: AvailabilityDialogState, t: BuildingsStrings): string {
  if (dialog.action !== 'inactivate') return t.reactivatedReason;
  const chosen = t.deactivationReasons.find((r) => r.value === dialog.reason)?.label || dialog.reason;
  return composeReason(chosen, dialog.note);
}

/** "<localized dorm type name> (<code>)" for the dorm type selects. */
export function dormTypeLabelText(dt: DormType | null | undefined, language: Language): string {
  return dt ? `${localizeDormTypeName(dt, language)}${dt.code ? ` (${dt.code})` : ''}` : '';
}

// ── Editor forms ──────────────────────────────────────────────

export function buildingFormFrom(building: Building): BuildingFormValues {
  return {
    number: building.number ?? '',
    dorm_type: building.dorm_type ?? '',
    gender_restriction: building.gender_restriction ?? '',
  };
}

export function newApartmentForm(): ApartmentFormValues {
  return { number: '', category: 'mixed', apartment_type: 'single', room_count: 1, apartment_capacity: '', inactive_reason: '' };
}

export function apartmentFormFrom(apartment: Apartment): ApartmentFormValues {
  return {
    number: apartment.number ?? '',
    category: apartment.category ?? 'mixed',
    apartment_type: apartment.apartment_type ?? 'single',
    room_count: apartment.room_count ?? 1,
    apartment_capacity: apartment.apartment_capacity ?? '',
    inactive_reason: apartment.inactive_reason ?? '',
  };
}

export function newRoomForm(): RoomFormValues {
  return { name: '', capacity: 1 };
}

export function roomFormFrom(room: Room): RoomFormValues {
  return { name: room.name ?? '', capacity: room.capacity ?? 1 };
}

export function bedFormFrom(bed: Bed): BedFormValues {
  return { label: bed.label ?? '' };
}

/** The first validation message of the open editor, or '' when it may be saved. */
export function validateEditor(editor: InventoryEditor | null, t: BuildingsStrings): string {
  if (!editor) return '';
  if (editor.type === 'building') {
    if (editor.data.number === '' || editor.data.number === null || Number.isNaN(Number(editor.data.number))) {
      return t.validationBuildingNumberRequired;
    }
    if (!editor.data.dorm_type) return t.validationDormTypeRequired;
  } else if (editor.type === 'apartment') {
    if (!String(editor.data.number ?? '').trim()) return t.validationApartmentNumberRequired;
    if (editor.data.room_count === '' || Number.isNaN(Number(editor.data.room_count)) || Number(editor.data.room_count) < 0) {
      return t.validationRoomCountInvalid;
    }
    if (editor.data.apartment_capacity !== '' && editor.data.apartment_capacity !== null) {
      if (Number.isNaN(Number(editor.data.apartment_capacity)) || Number(editor.data.apartment_capacity) < 0) {
        return t.validationCapacityInvalid;
      }
    }
  } else if (editor.type === 'room') {
    if (!String(editor.data.name ?? '').trim()) return t.validationRoomNameRequired;
    if (editor.data.capacity === '' || Number.isNaN(Number(editor.data.capacity)) || Number(editor.data.capacity) <= 0) {
      return t.validationRoomCapacityInvalid;
    }
  } else if (editor.type === 'bed') {
    if (!String(editor.data.label ?? '').trim()) return t.validationBedLabelRequired;
  }
  return '';
}

// The bodies below are assembled as records: the selects hand back ids as
// strings (or the record's own number when untouched) and the page has
// always sent them as-is - DRF resolves the PK either way - while the typed
// payloads spell those fields as numbers.

export function buildBuildingPayload(data: BuildingFormValues): BuildingPayload {
  const payload: Record<string, unknown> = {
    number: Number(data.number),
    dorm_type: data.dorm_type || null,
    gender_restriction: data.gender_restriction || '',
  };
  return payload as BuildingPayload;
}

/** `building` is sent only on create, after the apartment's own fields. */
export function buildApartmentPayload(data: ApartmentFormValues, building?: Id | null): ApartmentPayload {
  const payload: Record<string, unknown> = {
    number: data.number,
    category: data.category,
    apartment_type: data.apartment_type,
    room_count: Number(data.room_count) || 0,
    apartment_capacity: data.apartment_capacity === '' ? null : Number(data.apartment_capacity),
    inactive_reason: data.inactive_reason || '',
  };
  if (building !== undefined) payload.building = building;
  return payload as ApartmentPayload;
}

/** `apartment` is sent only on create. */
export function buildRoomPayload(data: RoomFormValues, apartment?: Id | null): RoomPayload {
  const payload: Record<string, unknown> = { name: data.name, capacity: Number(data.capacity) || 0 };
  if (apartment !== undefined) payload.apartment = apartment;
  return payload as RoomPayload;
}

export function buildBedPayload(data: BedFormValues): BedPayload {
  return { label: data.label };
}

export function editorTitle(editor: InventoryEditor | null, t: BuildingsStrings): string {
  if (!editor) return '';
  if (editor.type === 'building') return editor.mode === 'create' ? t.drawerCreateBuilding : t.drawerEditBuilding;
  if (editor.type === 'apartment') return editor.mode === 'create' ? t.drawerCreateApartment : t.drawerEditApartment;
  if (editor.type === 'room') return editor.mode === 'create' ? t.drawerCreateRoom : t.drawerEditRoom;
  return t.drawerEditBed;
}

export interface EditorContextSource {
  buildings: Building[];
  apartments: Apartment[];
  rooms: Room[];
  beds: Bed[];
  selectedBuilding: Building | null;
  selectedApartment: Apartment | null;
  selectedRoom: Room | null;
  selectedBed: Bed | null;
}

const EMPTY_EDITOR_CONTEXT: EditorContext = {
  building: null, apartment: null, room: null, apartmentRecord: null, roomRecord: null, bedRecord: null,
};

/**
 * The records around the open editor: each level is looked up by id and
 * falls back to the current selection (the record the editor was opened
 * from is always the selected one or a child of it).
 */
export function resolveEditorContext(editor: InventoryEditor | null, src: EditorContextSource): EditorContext {
  if (!editor) return EMPTY_EDITOR_CONTEXT;
  const findBuilding = (id: Id | null | undefined): Building | null =>
    src.buildings.find((b) => sameId(b.id, id)) || src.selectedBuilding;
  const findApartment = (id: Id | null | undefined): Apartment | null =>
    src.apartments.find((a) => sameId(a.id, id)) || src.selectedApartment;
  const findRoom = (id: Id | null | undefined): Room | null =>
    src.rooms.find((r) => sameId(r.id, id)) || src.selectedRoom;

  if (editor.type === 'building') {
    return { ...EMPTY_EDITOR_CONTEXT, building: findBuilding(editor.id) };
  }
  if (editor.type === 'apartment') {
    return {
      ...EMPTY_EDITOR_CONTEXT,
      building: findBuilding(editor.parentId),
      apartmentRecord: editor.mode === 'edit' ? findApartment(editor.id) : null,
    };
  }
  if (editor.type === 'room') {
    const apartment = findApartment(editor.parentId);
    return {
      ...EMPTY_EDITOR_CONTEXT,
      apartment,
      building: apartment ? findBuilding(apartment.building) : null,
      roomRecord: editor.mode === 'edit' ? findRoom(editor.id) : null,
    };
  }
  const room = findRoom(editor.parentId);
  const apartment = room ? findApartment(room.apartment) : null;
  return {
    ...EMPTY_EDITOR_CONTEXT,
    room,
    apartment,
    building: apartment ? findBuilding(apartment.building) : null,
    bedRecord: src.beds.find((bd) => sameId(bd.id, editor.id)) || src.selectedBed,
  };
}

export interface EditorContextLineInput {
  t: BuildingsStrings;
  language: Language;
  selectedDormType: DormType | null;
  selectedRegion: Region | null;
}

/** The subtitle under the editor title: where the entity sits in the tree. */
export function editorContextLine(
  editor: InventoryEditor | null,
  ctx: EditorContext,
  { t, language, selectedDormType, selectedRegion }: EditorContextLineInput
): string {
  if (!editor) return '';
  if (editor.type === 'building') {
    if (editor.mode === 'edit' && ctx.building) {
      return [
        localizeDormTypeName({ code: ctx.building.dorm_type_code, name: ctx.building.dorm_type_name }, language),
        localizeById(ctx.building.region, ctx.building.region_name, language),
      ].filter(Boolean).join(' • ');
    }
    if (editor.mode === 'create') {
      return [
        selectedDormType ? localizeDormTypeName(selectedDormType, language) : null,
        selectedRegion ? localizeRegionName(selectedRegion, language) : null,
      ].filter(Boolean).join(' • ');
    }
    return '';
  }
  if (editor.type === 'apartment') {
    const buildingLabel = ctx.building ? `${t.buildingNumberLabel} ${ctx.building.number}` : '';
    return editor.mode === 'edit'
      ? [`${t.apartmentNumberLabel} ${editor.data.number}`, buildingLabel].filter(Boolean).join(' • ')
      : buildingLabel;
  }
  if (editor.type === 'room') {
    const apartmentLabel = ctx.apartment ? `${t.apartmentNumberLabel} ${ctx.apartment.number}` : '';
    const buildingLabel = ctx.building ? `${t.buildingNumberLabel} ${ctx.building.number}` : '';
    return [apartmentLabel, buildingLabel].filter(Boolean).join(' • ');
  }
  const roomLabel = ctx.room ? `${t.parentRoomLabel} ${ctx.room.name}` : '';
  const apartmentLabel = ctx.apartment ? `${t.apartmentNumberLabel} ${ctx.apartment.number}` : '';
  const buildingLabel = ctx.building ? `${t.buildingNumberLabel} ${ctx.building.number}` : '';
  return [roomLabel, apartmentLabel, buildingLabel].filter(Boolean).join(' • ');
}

// ── Errors ────────────────────────────────────────────────────

/** Error text for a thrown value, with the page's historical fallbacks. */
export function errorMessage(err: unknown, fallback: string): string {
  return err instanceof Error && err.message ? err.message : fallback;
}

/** The field-keyed error body an ApiError carries, if any. */
function fieldErrorsOf(err: unknown): FieldErrors | null {
  if (typeof err === 'object' && err !== null && 'fieldErrors' in err) {
    const errors = (err as { fieldErrors?: unknown }).fieldErrors;
    if (typeof errors === 'object' && errors !== null) return errors as FieldErrors;
  }
  return null;
}

/**
 * The editor alert text: a structured rule violation's own message
 * ({field, code, message}) first, then the error's message, then the fallback.
 */
export function editorErrorMessage(err: unknown, fallback: string): string {
  const structured = fieldErrorsOf(err)?.message;
  if (typeof structured === 'string' && structured) return structured;
  return errorMessage(err, fallback);
}

// ── Per-bed write capabilities ────────────────────────────────
// The page has always probed the adapter for the per-bed operations it may
// grow (create / delete / set availability). The adapter has none today, so
// the add/delete bed controls stay hidden and the capability note shows.

const bedOperations = dormInventoryAPI as Record<string, unknown>;

export const BED_API_CAPABILITIES = {
  create: typeof bedOperations.createBed === 'function',
  delete: typeof bedOperations.deleteBed === 'function',
  setAvailability: typeof bedOperations.setBedAvailability === 'function',
} as const;

/** Deletes a bed through the adapter's deleteBed, when it exists. */
export async function deleteBedViaApi(id: Id): Promise<void> {
  const deleteBed = bedOperations.deleteBed;
  if (typeof deleteBed !== 'function') throw new Error('deleteBed is not supported');
  await (deleteBed as (bedId: Id) => Promise<unknown>)(id);
}
