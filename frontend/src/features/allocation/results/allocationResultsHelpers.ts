// Pure helpers of the Allocation Results page: location readers, the sort
// order, the dorm -> building -> apartment -> room hierarchy, the derivation
// of the saved results into what the views render, and the exact navigation
// parameters the page has always sent. No React, no I/O.
import type { Id } from '../../../shared/api/contracts';
import type { Language } from '../../../shared/i18n';
import type { AllocationResults, RunResultResponse } from '../types';
import type {
  AllocationHierarchy,
  ApartmentNode,
  AssignmentRow,
  AvailabilityState,
  AvailableBedRow,
  BuildingNode,
  DormTypeNode,
  LocatedItem,
  LocationValue,
  ResultsCounts,
  ResultsData,
  ResultsRegion,
  ResultsSummary,
  RoomNode,
  UnassignedAnalysisGroup,
  UnassignedStudentRow,
} from './model';

/* =========================================================
   General helpers
   ========================================================= */

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null;

/** The first present, non-empty value among the given keys ('' when none). */
export function getValue(item: Record<string, unknown> | null | undefined, keys: string[]): LocationValue {
  for (const key of keys) {
    const value = item?.[key];

    if (value !== undefined && value !== null && value !== '') {
      return value as LocationValue;
    }
  }

  return '';
}

/** The first run of digits in a value, as a number (0 when there is none). */
export function extractNumber(value: unknown): number {
  if (value === undefined || value === null) {
    return 0;
  }

  const match = String(value).match(/\d+/);
  return match ? Number.parseInt(match[0], 10) : 0;
}

export const getBuilding = (item: LocatedItem | null | undefined): LocationValue =>
  getValue(item, ['building_number', 'building_name', 'building']);

export const getApartment = (item: LocatedItem | null | undefined): LocationValue =>
  getValue(item, ['apartment_number', 'apartment']);

export const getRoom = (item: LocatedItem | null | undefined): LocationValue =>
  getValue(item, ['room_number', 'room_name', 'room']);

export const getBed = (item: LocatedItem | null | undefined): LocationValue =>
  getValue(item, ['bed_number', 'bed_label', 'bed']);

/** Dorm type (Hebrew collation), then building, apartment, room and bed by their numbers. */
export function sortByLocation<T extends LocatedItem>(items: T[]): T[] {
  return [...items].sort((a, b) => {
    const dormTypeComparison = String(a?.dorm_type || '').localeCompare(
      String(b?.dorm_type || ''),
      'he',
      { numeric: true }
    );

    if (dormTypeComparison !== 0) {
      return dormTypeComparison;
    }

    const buildingComparison = extractNumber(getBuilding(a)) - extractNumber(getBuilding(b));

    if (buildingComparison !== 0) {
      return buildingComparison;
    }

    const apartmentComparison = extractNumber(getApartment(a)) - extractNumber(getApartment(b));

    if (apartmentComparison !== 0) {
      return apartmentComparison;
    }

    const roomComparison = extractNumber(getRoom(a)) - extractNumber(getRoom(b));

    if (roomComparison !== 0) {
      return roomComparison;
    }

    return extractNumber(getBed(a)) - extractNumber(getBed(b));
  });
}

/** The entries of a keyed map, sorted by key (numerically, or by Hebrew collation). */
export function sortEntries<T>(
  object: Record<string, T> | null | undefined,
  numeric = false
): Array<[string, T]> {
  return Object.entries(object || {}).sort(([keyA], [keyB]) => {
    if (numeric) {
      return extractNumber(keyA) - extractNumber(keyB);
    }

    return String(keyA).localeCompare(String(keyB), 'he', { numeric: true });
  });
}

/* =========================================================
   Hierarchy construction
   Dorm type → Building → Apartment → Room
   ========================================================= */

// The hierarchy keys of an item that carries no dorm type / building /
// apartment / room. They are data keys (rendered as the row titles), fixed
// in Hebrew regardless of the interface language, as they always were.
export const NO_DORM_TYPE_LABEL = 'ללא סוג מעונות';
export const NO_BUILDING_LABEL = 'ללא בניין';
export const NO_APARTMENT_LABEL = 'ללא דירה';
export const NO_ROOM_LABEL = 'ללא חדר';

const createDormTypeNode = (name: string): DormTypeNode => ({
  name,
  assignments: [],
  availableBeds: [],
  buildings: {},
});

const createBuildingNode = (number: string): BuildingNode => ({
  number,
  assignments: [],
  availableBeds: [],
  apartments: {},
});

const createApartmentNode = (number: string): ApartmentNode => ({
  number,
  apartmentType: '',
  apartmentTypeDisplay: '',
  apartmentCategory: '',
  apartmentCategoryDisplay: '',
  assignments: [],
  availableBeds: [],
  rooms: {},
});

const createRoomNode = (name: string): RoomNode => ({
  name,
  assignments: [],
  availableBeds: [],
});

interface HierarchyPath {
  dormNode: DormTypeNode;
  buildingNode: BuildingNode;
  apartmentNode: ApartmentNode;
  roomNode: RoomNode;
}

/**
 * Groups the assignments and the free beds by dorm type, building,
 * apartment and room (each level keeps its own flat lists, so every row can
 * show its counts), in location order. The apartment's type/category is
 * taken from the first item seen in it.
 */
export function buildAllocationHierarchy(
  assignments: AssignmentRow[],
  availableBeds: AvailableBedRow[]
): AllocationHierarchy {
  const hierarchy: AllocationHierarchy = {};

  const ensurePath = (item: LocatedItem): HierarchyPath => {
    const dormTypeName = item?.dorm_type || NO_DORM_TYPE_LABEL;
    const buildingNumber = String(getBuilding(item) || NO_BUILDING_LABEL);
    const apartmentNumber = String(getApartment(item) || NO_APARTMENT_LABEL);
    const roomName = String(getRoom(item) || NO_ROOM_LABEL);

    if (!hierarchy[dormTypeName]) {
      hierarchy[dormTypeName] = createDormTypeNode(dormTypeName);
    }

    const dormNode = hierarchy[dormTypeName];

    if (!dormNode.buildings[buildingNumber]) {
      dormNode.buildings[buildingNumber] = createBuildingNode(buildingNumber);
    }

    const buildingNode = dormNode.buildings[buildingNumber];

    if (!buildingNode.apartments[apartmentNumber]) {
      buildingNode.apartments[apartmentNumber] = createApartmentNode(apartmentNumber);
    }

    const apartmentNode = buildingNode.apartments[apartmentNumber];

    if (!apartmentNode.apartmentType) {
      apartmentNode.apartmentType = item?.apartment_type || '';
      apartmentNode.apartmentTypeDisplay = item?.apartment_type_display || item?.apartment_type || '';
      apartmentNode.apartmentCategory = item?.apartment_category || '';
      apartmentNode.apartmentCategoryDisplay =
        item?.apartment_category_display || item?.apartment_category || '';
    }

    if (!apartmentNode.rooms[roomName]) {
      apartmentNode.rooms[roomName] = createRoomNode(roomName);
    }

    return {
      dormNode,
      buildingNode,
      apartmentNode,
      roomNode: apartmentNode.rooms[roomName],
    };
  };

  sortByLocation(assignments).forEach((assignment) => {
    const { dormNode, buildingNode, apartmentNode, roomNode } = ensurePath(assignment);

    dormNode.assignments.push(assignment);
    buildingNode.assignments.push(assignment);
    apartmentNode.assignments.push(assignment);
    roomNode.assignments.push(assignment);
  });

  sortByLocation(availableBeds).forEach((bed) => {
    const { dormNode, buildingNode, apartmentNode, roomNode } = ensurePath(bed);

    dormNode.availableBeds.push(bed);
    buildingNode.availableBeds.push(bed);
    apartmentNode.availableBeds.push(bed);
    roomNode.availableBeds.push(bed);
  });

  return hierarchy;
}

/* =========================================================
   Results derivation
   ========================================================= */

/** What the page shows before anything was loaded or handed over. */
export const EMPTY_RESULTS: ResultsData = {
  assignments: [],
  unassigned_students: [],
  available_beds: [],
  unassigned_analysis: [],
  counts: {
    assigned: 0,
    unassigned: 0,
    available_beds: 0,
  },
  successful_assignments: 0,
  roommate_matches: 0,
  conflicts: 0,
};

/** A list field of a result: the array as sent, or [] for anything else. */
export function asRows<T>(value: unknown): T[] {
  return Array.isArray(value) ? (value as T[]) : [];
}

/**
 * The adapter already returns the response body; a body wrapped in a `data`
 * envelope is unwrapped, as the page has always done (`raw?.data || raw`).
 */
export function unwrapResults(raw: AllocationResults | RunResultResponse | null | undefined): Record<string, unknown> {
  if (!isRecord(raw)) return {};
  const inner = raw.data;
  if (inner) return isRecord(inner) ? inner : {};
  return raw;
}

/** The region the saved results are read for, in the page's historical precedence. */
export function regionIdFrom(
  region: ResultsRegion | null | undefined,
  summary: ResultsSummary | null | undefined
): Id | null {
  return region?.id || summary?.region?.id || summary?.region_id || null;
}

/** The saved results as the page holds them after a load, on top of the handed-over result. */
export function resultsFromServer(
  data: Record<string, unknown>,
  routeResult: ResultsData | null
): ResultsData {
  const assignmentsFromDb = asRows<AssignmentRow>(data?.assignments);
  const unassignedFromDb = asRows<UnassignedStudentRow>(data?.unassigned_students);
  const availableBedsFromDb = asRows<AvailableBedRow>(data?.available_beds);
  const unassignedAnalysisFromDb = asRows<UnassignedAnalysisGroup>(data?.unassigned_analysis);
  const rawCounts = isRecord(data?.counts) ? data.counts : undefined;

  const counts: ResultsCounts = {
    assigned: Number(rawCounts?.assigned ?? data?.count ?? assignmentsFromDb.length) || 0,
    unassigned: Number(rawCounts?.unassigned ?? unassignedFromDb.length) || 0,
    available_beds: Number(rawCounts?.available_beds ?? availableBedsFromDb.length) || 0,
  };

  return {
    ...(routeResult || {}),
    assignments: assignmentsFromDb,
    unassigned_students: unassignedFromDb,
    available_beds: availableBedsFromDb,
    unassigned_analysis: unassignedAnalysisFromDb,
    counts,
    successful_assignments: counts.assigned,
    roommate_matches: Number(routeResult?.roommate_matches) || 0,
    conflicts: counts.unassigned,
  };
}

/**
 * The results re-read after a retry: each list is replaced only when the
 * server sent one, and the counts only when it sent them.
 */
export function mergeRefreshedResults(previous: ResultsData, refreshed: Record<string, unknown>): ResultsData {
  const refreshedCounts = refreshed?.counts;
  return {
    ...previous,
    assignments: Array.isArray(refreshed?.assignments) ? refreshed.assignments : previous.assignments,
    unassigned_students: Array.isArray(refreshed?.unassigned_students)
      ? refreshed.unassigned_students
      : previous.unassigned_students,
    available_beds: Array.isArray(refreshed?.available_beds)
      ? refreshed.available_beds
      : previous.available_beds,
    unassigned_analysis: Array.isArray(refreshed?.unassigned_analysis)
      ? refreshed.unassigned_analysis
      : previous.unassigned_analysis,
    counts: (isRecord(refreshedCounts) ? refreshedCounts : null) || previous.counts,
  };
}

/** The three tab totals: the server's counts, else the run's totals, else the list lengths. */
export function deriveCounts(
  result: ResultsData,
  assignments: AssignmentRow[],
  unassignedStudents: UnassignedStudentRow[],
  availableBeds: AvailableBedRow[]
): ResultsCounts {
  return {
    assigned: Number(result?.counts?.assigned ?? result?.successful_assignments ?? assignments.length) || 0,
    unassigned: Number(result?.counts?.unassigned ?? result?.conflicts ?? unassignedStudents.length) || 0,
    available_beds: Number(result?.counts?.available_beds ?? availableBeds.length) || 0,
  };
}

/**
 * The run this results page is showing - needed to scope the retry-
 * unassigned action to exactly this run's original population. Available
 * when navigated here from AllocationPage (routeResult.run); falls back to
 * the region's latest COMPLETED run if the summary was also passed along.
 * If neither is available (e.g. a cold direct visit to this URL), retry is
 * simply not offered rather than guessing.
 */
export function currentRunIdFrom(
  routeResult: ResultsData | null,
  summary: ResultsSummary | null
): Id | null {
  return (
    routeResult?.run?.id ||
    (summary?.latest_run?.status === 'completed' ? summary?.latest_run?.id : null) ||
    null
  );
}

/** The most recent valid assigned_at among the assignments, or null. */
export function latestAssignmentDate(assignments: AssignmentRow[]): Date | null {
  return assignments.reduce<Date | null>((latestDate, assignment) => {
    if (!assignment?.assigned_at) {
      return latestDate;
    }

    const currentDate = new Date(assignment.assigned_at);

    if (Number.isNaN(currentDate.getTime())) {
      return latestDate;
    }

    if (!latestDate || currentDate > latestDate) {
      return currentDate;
    }

    return latestDate;
  }, null);
}

/** When the last allocation happened, in the page's historical precedence. */
export function lastAllocationDate(
  result: ResultsData,
  summary: ResultsSummary | null,
  assignments: AssignmentRow[],
  generatedAt: string | null
): string | Date | null {
  return (
    result?.run?.completed_at ||
    summary?.latest_run?.completed_at ||
    result?.run?.started_at ||
    summary?.latest_run?.started_at ||
    latestAssignmentDate(assignments) ||
    generatedAt ||
    null
  );
}

/** The last-allocation date in the he-IL / en-US locale, '-' when unknown. */
export function formatLastAllocationDate(date: string | Date | null, language: Language): string {
  return date ? new Date(date).toLocaleString(language === 'he' ? 'he-IL' : 'en-US') : '-';
}

/* =========================================================
   View helpers
   ========================================================= */

/** Empty (free beds, nobody placed), available (free beds left) or full. */
export function availabilityState(assignedCount: number, availableCount: number): AvailabilityState {
  if (assignedCount === 0 && availableCount > 0) {
    return 'empty';
  }

  if (availableCount > 0) {
    return 'available';
  }

  return 'full';
}

export type ReasonTextKey =
  | 'reasonNoAcceptedDormType'
  | 'reasonNoPhysicalFreeBeds'
  | 'reasonHousingGenderMismatch'
  | 'reasonBuildingGenderRestriction'
  | 'reasonReligionOrOccupant'
  | 'reasonOtherHardConstraint';

/** The dictionary key explaining an analysis group's reason code (null for an unknown code). */
export function reasonTextKey(reasonCode: string | null | undefined): ReasonTextKey | null {
  switch (reasonCode) {
    case 'NO_ACCEPTED_DORM_TYPE':
      return 'reasonNoAcceptedDormType';
    case 'NO_PHYSICAL_FREE_BEDS_IN_ACCEPTED_DORM':
      return 'reasonNoPhysicalFreeBeds';
    case 'HOUSING_TYPE_OR_GENDER_MISMATCH':
      return 'reasonHousingGenderMismatch';
    case 'BUILDING_GENDER_RESTRICTION':
      return 'reasonBuildingGenderRestriction';
    case 'RELIGION_OR_EXISTING_OCCUPANT_INCOMPATIBILITY':
      return 'reasonReligionOrOccupant';
    case 'OTHER_HARD_CONSTRAINT_CONFLICT':
      return 'reasonOtherHardConstraint';
    default:
      return null;
  }
}

/**
 * The Buildings-management query for an analysis group, pre-scoped to its
 * accepted dorm type/region where feasible (region + dorm type map directly
 * onto existing Buildings-page filters); apartment type/category/gender are
 * passed as informational query params only - Buildings does not
 * auto-filter by them, since doing so reliably would require fetching every
 * apartment up front, and this stays informational rather than implying an
 * exact filter that isn't really applied.
 */
export function buildBuildingsSearch(regionId: Id | null | undefined, group: UnassignedAnalysisGroup): string {
  const params = new URLSearchParams();
  if (regionId) params.set('region', String(regionId));
  // dormTypeId is the real DormType primary key - BuildingsPage filters
  // selectedDormTypeId against dormType.id, not dormType.code, so the PK
  // is what actually pre-selects the filter. dormTypeCode is kept only
  // as an informational extra (e.g. for display), never for filtering.
  if (group?.accepted_dorm_type_id !== null && group?.accepted_dorm_type_id !== undefined) {
    params.set('dormTypeId', String(group.accepted_dorm_type_id));
  }
  if (group?.accepted_dorm_type_code !== null && group?.accepted_dorm_type_code !== undefined) {
    params.set('dormTypeCode', String(group.accepted_dorm_type_code));
  }
  if (group?.accepted_dorm_type_name) params.set('dormTypeName', group.accepted_dorm_type_name);
  if (group?.gender) params.set('gender', group.gender);
  if (group?.housing_type) params.set('housingType', group.housing_type);
  if (group?.student_count !== null && group?.student_count !== undefined) {
    params.set('studentCount', String(group.student_count));
  }
  params.set('freeOnly', '1');
  return params.toString();
}

/** The retry reply's totals: how many were retried and how many are now placed. */
export function retryOutcome(response: RunResultResponse): { assignedNow: number; retried: number } {
  const data = unwrapResults(response);
  const retryResult = isRecord(data?.result) ? data.result : {};
  return {
    assignedNow: Number(retryResult.successful_assignments) || 0,
    retried: Number(retryResult.retried_student_count) || 0,
  };
}

/**
 * Error text for a thrown value, with the page's historical precedence: the
 * backend's `error` field, then the message, then the fallback.
 */
export function errorMessage(err: unknown, fallback: string): string {
  if (isRecord(err)) {
    const response = err.response;
    if (isRecord(response) && isRecord(response.data)) {
      const serverError = response.data.error;
      if (typeof serverError === 'string' && serverError) return serverError;
    }
    const message = err.message;
    if (typeof message === 'string' && message) return message;
  }
  return fallback;
}
