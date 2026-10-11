import { defineDictionary } from '../../../shared/i18n/language';

// ── Localization ─────────────────────────────────────────────
// The Allocation Results page dictionary. Moved out of
// AllocationResultsPage.jsx unchanged (R4): the inline {he: {...}, en: {...}}
// object now builds a typed he/en Dictionary through shared/i18n
// defineDictionary, so a key missing from one language is a type error.
export const allocationResultsStrings = defineDictionary((p) => ({
  title: p('תוצאות השיבוץ', 'Allocation Results'),
  subtitle: p(
    'תוצאות השיבוץ השמורות במערכת לפי אזור המשתמש',
    'Saved allocation results according to the user region'
  ),
  backToAllocation: p('חזרה לעמוד השיבוץ', 'Back to Allocation'),
  lastAllocationAt: p('מועד השיבוץ האחרון', 'Last Allocation'),
  runHighlights: p('תוצאות מהמערכת', 'System Results'),

  assignedStudentsView: p('סטודנטים משובצים', 'Assigned Students'),
  unassignedStudentsView: p('סטודנטים שלא שובצו', 'Unassigned Students'),
  availableBedsView: p('מיטות פנויות', 'Available Beds'),

  assignmentsTitle: p('שיבוצים מפורטים', 'Detailed Assignments'),
  unassignedTitle: p('סטודנטים שלא שובצו', 'Unassigned Students'),
  availableBedsTitle: p('מיטות שנשארו פנויות', 'Available Beds'),

  noAssignmentsTable: p('אין כרגע תוצאות שיבוץ להצגה', 'No allocation results to display right now'),
  noUnassignedStudents: p('אין סטודנטים שלא שובצו', 'No unassigned students'),
  noAvailableBeds: p('אין מיטות פנויות להצגה', 'No available beds to display'),

  student: p('סטודנט', 'Student'),
  studentId: p('מספר סטודנט', 'Student ID'),
  gender: p('מגדר', 'Gender'),
  housingType: p('סוג דיור', 'Housing Type'),
  acceptedDormType: p('סוג מעונות מאושר', 'Accepted Dorm Type'),
  religion: p('דת', 'Religion'),
  religiousLevel: p('דתיות', 'Religious Preference'),
  sector: p('מגזר', 'Sector'),
  priority: p('עדיפות', 'Priority'),
  specialStatuses: p('סטטוסים מיוחדים', 'Special Statuses'),
  reason: p('סיבה', 'Reason'),

  // Unassigned analysis (why weren't students assigned)
  unassignedAnalysisTitle: p('למה חלק מהסטודנטים לא שובצו?', 'Why weren’t some students assigned?'),
  studentsUnassignedLabel: p('סטודנטים לא שובצו', 'students unassigned'),
  physicallyFreeBedsLabel: p('מיטות פנויות פיזית במתחם', 'physically free beds in this dorm type'),
  compatibleFreeBedsLabel: p('מיטות מתאימות', 'compatible free beds'),
  inventoryBreakdownLabel: p('פירוט מלאי פנוי', 'free inventory breakdown'),
  possibleActionLabel: p('פעולה אפשרית', 'Possible action'),
  goToBuildings: p('עבור לניהול מבנים', 'Go to Buildings management'),
  showRelevantBeds: p('הצג מיטות פנויות רלוונטיות', 'Show relevant free beds'),
  reasonNoAcceptedDormType: p(
    'לסטודנטים אלו אין סוג מעונות מאושר רשום.',
    'These students have no accepted dorm type on record.'
  ),
  reasonNoPhysicalFreeBeds: p(
    'אין מיטות פנויות פיזית בסוג המעונות המאושר שלהם.',
    'There are no physically free beds in their accepted dorm type.'
  ),
  reasonHousingGenderMismatch: p(
    'אין מיטות פנויות בסוג הדיור והמגדר המתאימים להם. ניתן לשקול שינוי סיווג של דירות פנויות מסוג אחר, ולאחר מכן לנסות שוב לשבץ את הסטודנטים שלא שובצו.',
    'There are no free beds matching their housing type and gender. Consider reclassifying suitable empty apartments of another type, then retry allocation for the unassigned students.'
  ),
  reasonBuildingGenderRestriction: p(
    'המיטות הפנויות נמצאות בבניינים עם הגבלת מגדר שאינה תואמת.',
    'The free beds are in buildings with a non-matching gender restriction.'
  ),
  reasonReligionOrOccupant: p(
    'המיטות הפנויות אינן תואמות מבחינת דת/דתיות עם הדיירים הקיימים, או שיש אילוץ ברמת החדר.',
    'The free beds are incompatible on religion/religious grounds with existing occupants, or a room-level constraint applies.'
  ),
  reasonOtherHardConstraint: p(
    'קיימות מיטות פנויות שנראות תואמות, אך הסטודנטים עדיין לא שובצו — ייתכן שיש אילוץ נוסף (למשל בקשת שותפים הדדית, או תחרות על אותן מיטות עם סטודנטים אחרים) שמונע שיבוץ אוטומטי. יש לבדוק ידנית.',
    'Compatible free beds appear to exist, yet these students are still unassigned — there may be an additional constraint (e.g. a mutual roommate request, or contention with other students for the same beds) preventing automatic placement. Manual review is recommended.'
  ),
  retryUnassigned: p('נסה לשבץ שוב את הסטודנטים שלא שובצו', 'Retry unassigned students'),
  retryUnassignedConfirmTitle: p('ניסיון שיבוץ חוזר', 'Retry Allocation'),
  retryUnassignedConfirmBody: (count: number) => p(
    `הפעולה תנסה לשבץ מחדש ${count} סטודנטים שלא שובצו בהרצה הנוכחית, כנגד המלאי הפנוי הנוכחי בלבד. שיבוצים קיימים לא ישתנו. להמשיך?`,
    `This will retry allocating the ${count} students left unassigned by the current run, against currently available inventory only. Existing assignments will not change. Continue?`
  ),
  retryUnassignedSuccess: (assignedNow: number, retried: number) => p(
    `הניסיון הושלם: ${assignedNow} מתוך ${retried} סטודנטים שובצו כעת.`,
    `Retry complete: ${assignedNow} of ${retried} students were just assigned.`
  ),
  retrying: p('מנסה לשבץ מחדש...', 'Retrying allocation...'),
  retryError: p('שגיאה בניסיון השיבוץ החוזר', 'Failed to retry unassigned students'),
  noRunToRetry: p('לא נמצאה הרצת שיבוץ פעילה לניסיון חוזר', 'No active allocation run found to retry'),

  dormType: p('סוג מעונות', 'Dorm Type'),
  apartmentType: p('סוג דירה', 'Apartment Type'),
  category: p('קטגוריה', 'Category'),
  reserved: p('שמורה', 'Reserved'),

  building: p('בניין', 'Building'),
  apartment: p('דירה', 'Apartment'),
  room: p('חדר', 'Room'),
  bed: p('מיטה', 'Bed'),
  status: p('סטטוס', 'Status'),

  buildingsCount: p('בניינים', 'buildings'),
  apartmentsCount: p('דירות', 'apartments'),
  roomsCount: p('חדרים', 'rooms'),
  assignedCount: p('משובצים', 'assigned'),
  availableBedsCount: p('מיטות פנויות', 'available beds'),
  occupiedBedsCount: p('מיטות תפוסות', 'occupied beds'),

  full: p('מלא', 'Full'),
  hasAvailability: p('יש מקום פנוי', 'Available'),
  empty: p('ריק', 'Empty'),

  availableBed: p('מיטה פנויה', 'Available bed'),
  noStudentsInRoom: p('אין סטודנטים משובצים בחדר זה', 'No students assigned to this room'),

  yes: p('כן', 'Yes'),
  no: p('לא', 'No'),

  loadingResults: p('טוען תוצאות...', 'Loading results...'),
  errorLoadingResults: p('שגיאה בטעינת תוצאות השיבוץ', 'Error loading allocation results'),
  retryLoadResults: p('נסה שוב', 'Retry'),

  // ── Not in the original dictionary ──
  // The available-beds table has always rendered `t.region` as its first
  // column header, but the inline dictionary never declared that key, so
  // the header rendered empty in both languages. The empty entry keeps the
  // page rendering exactly as before; it is a candidate for p('אזור', 'Region').
  region: '',
}));

export type AllocationResultsStrings = typeof allocationResultsStrings.he;
