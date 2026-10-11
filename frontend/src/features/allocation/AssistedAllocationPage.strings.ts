import { defineDictionary } from '../../shared/i18n/language';
import { localizeGender } from '../../shared/lib/genderLabels';

// A location part (building / apartment / room) as the API carries it.
type Loc = string | number | null | undefined;

// ── Localization ─────────────────────────────────────────────
// Single translation dictionary for the whole page, following the same
// per-page t={he:{...},en:{...}} pattern used elsewhere in Dormify (see
// HomePage.js / TransfersPage.js). Renamed user-facing feature name:
// "שיבוץ מסייע"/"Assisted Allocation" -> "שיבוץ ידני"/"Manual Allocation".
// Moved out of AssistedAllocationPage.jsx unchanged (R3): the inline p(he, en)
// pairs now build a typed he/en Dictionary through shared/i18n defineDictionary.
export const assistedAllocationStrings = defineDictionary((p, language) => {
  return {
    pageTitle: p('שיבוץ ידני', 'Manual Allocation'),
    pageSubtitle: p('נגישות, סטודנטים לא משובצים ושיבוץ בסיוע הצוות', 'Accessibility, unassigned students and staff-assisted placement'),
    allRegions: p('כל האזורים', 'All Regions'),
    metricTransferring: p('בהעברה', 'Transferring'),

    badgeAccessibility: p('נגישות', 'Accessibility'),
    badgeResolved: p('טופל', 'Resolved'),
    badgeUnassigned: p('לא משובץ', 'Unassigned'),
    badgeTransferPending: p('בהעברה', 'Transferring'),

    locBuildingApt: (b: Loc, a: Loc) => p(`בניין ${b ?? ''} · דירה ${a ?? ''}`, `Building ${b ?? ''} · Apt ${a ?? ''}`),
    locBuilding: (b: Loc) => p(`בניין ${b ?? ''}`, `Building ${b ?? ''}`),
    loc3WithRegion: (region: Loc, b: Loc, a: Loc, r: Loc) => p(
      `${region ? `${region} · ` : ''}בניין ${b ?? ''} · דירה ${a ?? ''} · חדר ${r ?? ''}`,
      `${region ? `${region} · ` : ''}Building ${b ?? ''} · Apt ${a ?? ''} · Room ${r ?? ''}`,
    ),
    alreadyPlacedTitle: p('הסטודנט/ית כבר משובץ/ת', 'Student is already placed'),
    bedsWillFree: (n: number | string) => p(`${n} מיטות יתפנו`, `${n} beds will free up`),
    suitsStudentsInQueue: (n: number | string) => p(`מתאים ל־${n} סטודנטים בתור`, `Suits ${n} students in queue`),
    relevantToSelected: p('רלוונטי לסטודנט/ית הנבחר/ת', 'Relevant to the selected student'),
    changeConfigBtn: p('שינוי הגדרה', 'Change configuration'),
    adminRequiredForConfig: p('נדרש מנהל לשינוי הגדרת דירה', 'An admin is required to change the apartment configuration'),

    selectionTitle: p('השיבוץ שנבחר', 'Selected assignment'),
    clear: p('נקה', 'Clear'),
    selStudent: p('סטודנט/ית:', 'Student:'),
    selBuilding: p('בניין:', 'Building:'),
    selApartment: p('דירה:', 'Apartment:'),
    selRoom: p('חדר:', 'Room:'),
    selBed: p('מיטה:', 'Bed:'),
    singlePlace: p('מקום יחיד', 'Single place'),
    overrideRulesTitle: p('חריגה מכללי השיבוץ', 'Override of assignment rules'),
    overrideReasonLabel: p('סיבת החריגה', 'Override reason'),
    overrideReasonPlaceholder: p('לדוגמה: אין מקום אחר תואם באזור', 'e.g. no other matching place in the region'),
    overridePermissionDenied: p(
      'שיבוץ בחריגה דורש הרשאת מנהל אזור או מנהל מרכזי.',
      'Overriding a placement rule requires a regional manager or central admin.'
    ),
    confirmOverrideBtn: p('אישור שיבוץ בחריגה', 'Confirm assignment with override'),
    confirmAssignBtn: p('אישור שיבוץ', 'Confirm assignment'),
    cancel: p('ביטול', 'Cancel'),

    searchPlaceholder: p('חיפוש לפי שם / ת.ז...', 'Search by name / ID...'),
    allGenders: p('כל המגדרים', 'All genders'),
    genderMale: p(localizeGender('male', 'he'), localizeGender('male', 'en')),
    genderFemale: p(localizeGender('female', 'he'), localizeGender('female', 'en')),
    // Derives the localized gender label from the RAW backend enum value
    // ('male'/'female') rather than trusting the backend's gender_display
    // field, which is a fixed Hebrew string regardless of app language.
    genderOf: (rawGender: string | null | undefined) => localizeGender(rawGender, language),
    queueLoadError: p('לא ניתן לטעון את תור השיבוץ כרגע', 'Unable to load the assignment queue right now'),
    emptyAccessibilityDone: p('כל שיבוצי הנגישות הושלמו', 'All accessibility placements are complete'),
    emptyUnassignedDone: p('כל הסטודנטים באזור שובצו', 'All students in the region have been assigned'),
    emptyResolvedNone: p('אין פעולות שיבוץ שבוצעו עדיין', 'No assignment actions performed yet'),
    emptyNeedsPlacementNone: p('אין סטודנטים הממתינים לטיפול', 'No students awaiting placement'),
    emptyTransferPendingNone: p('אין בקשות העברה ממתינות', 'No pending transfer requests'),
    detailLoadError: p('שגיאה בטעינת פרטי הסטודנט', "Failed to load the student's details"),
    selectStudentPrompt: p('בחרו סטודנט מהרשימה כדי להתחיל', 'Select a student from the list to begin'),
    recLoadError: p('שגיאה בטעינת אפשרויות שיבוץ', 'Failed to load assignment options'),

    factId: p('ת.ז', 'ID'),
    factGender: p('מגדר', 'Gender'),
    factReligion: p('דת', 'Religion'),
    factRegion: p('אזור', 'Region'),
    factDormType: p('סוג מעונות', 'Dorm Type'),
    factHousingType: p('סוג דיור', 'Housing Type'),
    priorityLabel: p('עדיפות', 'Priority'),
    accessibilityLabel: p('נגישות', 'Accessibility'),
    roommateRequestLabel: p('בקשת שותף:', 'Roommate request:'),
    reasonFallbackTitle: p('לא נמצא שיבוץ מתאים', 'No matching assignment found'),
    freeBedsSuffix: p('פנויות', 'free'),

    tierAssignmentOptionsTitle: p('אפשרויות שיבוץ', 'Assignment options'),
    tierConfigChangeTitle: p('אפשרויות לשינוי הגדרת דירה', 'Apartment configuration change options'),
    tierConfigHint: p(
      'לפעמים המלאי קיים, אך הגדרת דירה/בניין מונעת שיבוץ — שינוי ההגדרה יפתח מיטות לשיבוץ ויחשב מחדש את האפשרויות',
      'Sometimes the inventory exists, but an apartment/building configuration blocks assignment - changing it will open beds for assignment and recompute the options'
    ),
    unsafeConfigNote: p(
      'קיימות מיטות פנויות נוספות בדירות מאוכלסות, ולכן לא ניתן לשנות את הגדרתן',
      'Additional free beds exist in occupied apartments, so their configuration cannot be changed'
    ),
    tierTransferTitle: p('שליחה להעברה', 'Send for transfer'),
    transferHintNoCandidates: p(
      'לא נמצא שיבוץ מתאים בסוג המעונות שאושר לסטודנט/ית — ניתן לשלוח בקשת העברה לבדיקת אפשרויות נוספות',
      "No matching assignment was found in the student's accepted dorm type - a transfer request can be sent to check further options"
    ),
    transferHintDefault: p(
      'אין פתרון מתאים בסוג המעונות שאושר לסטודנט/ית? ניתן לשלוח בקשת העברה לבדיקה מחוץ לסוג המעונות הנוכחי',
      "No matching solution in the student's accepted dorm type? A transfer request can be sent to check outside the current dorm type"
    ),
    createTransferBtn: p('יצירת בקשת העברה', 'Create transfer request'),
    historyTitle: p('היסטוריית פעולות', 'Action History'),

    configDialogTitle: p('שינוי הגדרת דירה', 'Change Apartment Configuration'),
    configDialogConfirmLabel: p('אישור שינוי', 'Confirm Change'),
    configBedsWillFree: (n: number | string) => p(`${n} מיטות יתפנו לשיבוץ`, `${n} beds will free up for assignment`),

    transferDialogTitle: p('בקשת העברה לאזור אחר', 'Transfer Request to Another Region'),
    transferDialogConfirmLabel: p('שליחת בקשה', 'Send Request'),
    transferRegionLabel: p('אזור יעד', 'Destination region'),
    transferRegionPlaceholder: p('בחר/י אזור יעד', 'Select a destination region'),
    transferReasonLabel: p('סיבה', 'Reason'),
    transferReasonPlaceholder: p('לדוגמה: אין מקום פנוי באזור התואם לסטודנט', "e.g. no free place in the student's matching region"),
    errNeedRegion: p('יש לבחור אזור יעד', 'A destination region is required'),
    errNeedReason: p('יש להזין סיבה', 'A reason is required'),
    loadingEllipsis: p('טוען...', 'Loading...'),
    errLoadTargetRegions: p('לא ניתן לטעון את אזורי היעד', 'Could not load the destination regions'),
    noTargetRegionsFound: p('לא נמצאו אזורי יעד זמינים להעברה', 'No destination regions are available for transfer'),

    successOverrideAssigned: p('השיבוץ בוצע בחריגה', 'Assignment completed with an override'),
    successAssigned: p('הסטודנט שובץ בהצלחה', 'The student was assigned successfully'),
    errAssignFailed: p('השיבוץ נכשל', 'Assignment failed'),
    successConfigUpdated: p('הגדרת הדירה עודכנה', 'Apartment configuration updated'),
    errConfigUpdateFailed: p('עדכון ההגדרה נכשל', 'Configuration update failed'),
    successTransferSent: p('בקשת ההעברה נשלחה וממתינה לאישור', 'Transfer request sent and is now pending approval'),
    errTransferFailed: p('שליחת הבקשה נכשלה', 'Failed to send the request'),

    activeTransferTitle: p('בקשת העברה פעילה', 'Active Transfer Request'),
    tsStatus: p('סטטוס', 'Status'),
    tsSourceRegion: p('אזור מקור', 'Source region'),
    tsTargetRegion: p('אזור יעד', 'Target region'),
    tsReason: p('סיבה', 'Reason'),
    tsSentAt: p('נשלח בתאריך', 'Submitted on'),
    tsSentBy: p('נשלח על ידי', 'Submitted by'),
    tsHandledBy: p('טופל על ידי', 'Handled by'),
    tsHandledAt: p('תאריך טיפול', 'Handled on'),
    cancelTransferBtn: p('ביטול בקשת העברה', 'Cancel Transfer Request'),
    cancelTransferDialogTitle: p('ביטול בקשת העברה', 'Cancel Transfer Request'),
    cancelTransferDialogConfirmLabel: p('ביטול הבקשה', 'Cancel Request'),
    cancelTransferDialogBody: p(
      'הבקשה תבוטל והסטודנט/ית יחזור/תחזור לטיפול מקומי רגיל באזור הנוכחי. הפעולה אינה מבטלת שיבוץ שכבר בוצע.',
      "The request will be cancelled and the student will return to the normal local queue in the current region. This does not undo an assignment that has already been completed."
    ),
    successTransferCancelled: p('בקשת ההעברה בוטלה', 'Transfer request cancelled'),
    errTransferCancelFailed: p('ביטול הבקשה נכשל', 'Failed to cancel the request'),
  };
});

export type AssistedAllocationStrings = typeof assistedAllocationStrings.he;
