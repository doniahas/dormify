import { defineDictionary } from '../../shared/i18n/language';
import { localizeGender } from '../../shared/lib/genderLabels';

// A location part (building / apartment / room) as the API carries it.
type Loc = string | number | null | undefined;

// ── Localization ─────────────────────────────────────────────
// Single translation dictionary for the whole page and every wizard/panel
// it renders - follows the same per-page t={he:{...},en:{...}} pattern used
// elsewhere in Dormify (see HomePage.js / WhatIfPage.js). Built once from
// the current language and threaded down as a prop rather than re-derived
// per component, so every string on this page stays in one place.
// Moved out of TransfersPage.jsx unchanged (R3): the inline p(he, en) pairs
// now build a typed he/en Dictionary through shared/i18n defineDictionary.
// The directional BackArrow/NextArrow icons stay with the wizard components
// (components/WizardChrome.tsx).
export const transfersStrings = defineDictionary((p) => {
  const loc3 = (b: Loc, a: Loc, r: Loc) => p(`בניין ${b} · דירה ${a} · חדר ${r}`, `Building ${b} · Apt ${a} · Room ${r}`);
  const loc3WithRegion = (region: Loc, b: Loc, a: Loc, r: Loc) => p(
    `${region ? `${region} · ` : ''}בניין ${b} · דירה ${a} · חדר ${r}`,
    `${region ? `${region} · ` : ''}Building ${b} · Apt ${a} · Room ${r}`
  );
  return {
    // ── Top bar ──
    pageTitle: p('בקשות מעבר', 'Transfer Requests'),
    pageSubtitle: p('ניהול ואישור בקשות שינוי מגורים של סטודנטים', 'Manage and approve student housing change requests'),
    refresh: p('רענון', 'Refresh'),
    newRequest: p('בקשה חדשה', 'New Request'),

    // ── Stat cards ──
    statTotal: p('סה"כ', 'Total'),
    statPending: p('ממתינות', 'Pending'),
    statApproved: p('אושרו', 'Approved'),
    statRejected: p('נדחו', 'Rejected'),

    // ── List toolbar ──
    searchPlaceholder: p('חיפוש...', 'Search...'),
    tabAll: p('הכל', 'All'),
    tabPending: p('ממתינות', 'Pending'),
    tabApproved: p('אושרו', 'Approved'),
    tabRejected: p('נדחו', 'Rejected'),
    requestTypeLabel: p('סוג בקשה', 'Request Type'),
    regionLabel: p('אזור', 'Region'),
    allRegions: p('כל האזורים', 'All Regions'),
    regionFilterTitle: p('סינון לפי אזור', 'Filter by region'),
    requestsCount: (n: number | string) => p(`${n} בקשות`, `${n} requests`),
    loadingRequests: p('טוען...', 'Loading...'),

    typeFilterAll: p('כל סוגי הבקשות', 'All request types'),
    typeFilterAddStudent: p('הוספת סטודנט', 'Add Student'),
    typeFilterRemoveStudent: p('הסרה ממעונות', 'Remove from Dorms'),
    typeFilterRoom: p('שינוי חדר', 'Room Transfer'),
    typeFilterApartment: p('מעבר דירה / אזור', 'Apartment / Region Transfer'),
    typeFilterSwap: p('חילוף סטודנטים', 'Student Swap'),
    typeFilterOther: p('בקשה אחרת', 'Other Request'),

    // ── Empty states ──
    emptyNoRequestsTitle: p('אין בקשות מעבר כרגע', 'No transfer requests yet'),
    emptyNoRequestsSub: p('בקשות חדשות שייווצרו יופיעו כאן', 'New requests will appear here'),
    emptyNoResultsTitle: p('לא נמצאו בקשות', 'No requests found'),
    emptyNoResultsSub: p('נסי לשנות את החיפוש או את הסינונים', 'Try changing the search or filters'),
    emptyDetailNoneTitle: p('אין בקשות להצגה', 'No requests to display'),
    emptyDetailNoneSub: p('כאשר תיווצר בקשת מעבר חדשה, פרטיה יוצגו כאן.', 'When a new transfer request is created, its details will appear here.'),
    emptyDetailPickTitle: p('בחרי בקשה מהרשימה', 'Select a request from the list'),
    emptyDetailPickSub: p('בחרי בקשה כדי לצפות בפרטים, בשיבוץ הנוכחי ובפעולות הזמינות.', 'Select a request to view its details, current placement and available actions.'),

    errLoad: p('שגיאה בטעינה', 'Failed to load'),
    errSubmit: p('שגיאה בשליחה', 'Failed to submit'),
    errGeneric: p('שגיאה', 'Error'),

    // ── Wizard shared chrome ──
    cancel: p('ביטול', 'Cancel'),
    back: p('חזרה', 'Back'),
    next: p('המשך', 'Next'),
    submit: p('שלח', 'Submit'),
    selectPlaceholder: p('בחר...', 'Select...'),
    studentSearchPlaceholder: p('חפש סטודנט משובץ...', 'Search assigned student...'),

    // ── New Request modal: type picker ──
    modalNewRequest: p('בקשה חדשה', 'New Request'),
    modalChooseType: p('בחר סוג בקשה', 'Choose Request Type'),
    modalBackToTypes: p('סוגי בקשות', 'Request Types'),
    typeAddStudentTitle: p('הוספת סטודנט', 'Add Student'),
    typeAddStudentSub: p('רישום סטודנט חדש למעונות', 'Register a new student to the dorms'),
    typeRemoveStudentTitle: p('הסרה ממעונות', 'Remove from Dorms'),
    typeRemoveStudentSub: p('הסרת סטודנט קיים', 'Remove an existing student'),
    typeTransferTitle: p('בקשת מעבר', 'Transfer Request'),
    typeTransferSub: p('חדר אחר, דירה אחרת או אזור אחר', 'Different room, apartment or region'),
    typeSwapTitle: p('חילוף בין סטודנטים', 'Student Swap'),
    typeSwapSub: p('שני סטודנטים מחליפים מקום', 'Two students swap places'),
    typeOtherTitle: p('בקשה אחרת', 'Other Request'),
    typeOtherSub: p('הארכת שהייה ועוד', 'Stay extension and more'),

    // ── AddStudentWizard ──
    addSteps: [p('פרטי סטודנט', 'Student Details'), p('העדפות דיור', 'Housing Preferences'), p('סיבה', 'Reason'), p('סיכום', 'Summary')],
    addStep0Title: p('פרטי הסטודנט החדש', 'New Student Details'),
    addStep1Title: p('העדפות דיור', 'Housing Preferences'),
    addStep2Title: p('סיבת הבקשה', 'Request Reason'),
    addStep3Title: p('סיכום לפני שליחה', 'Summary Before Submitting'),
    labelId: p('תעודת זהות', 'ID Number'),
    labelFirstName: p('שם פרטי', 'First Name'),
    labelLastName: p('שם משפחה', 'Last Name'),
    labelPhone: p('טלפון', 'Phone'),
    labelEmail: p('אימייל', 'Email'),
    labelCity: p('עיר', 'City'),
    labelGender: p('מגדר', 'Gender'),
    labelReligion: p('דת', 'Religion'),
    labelDormType: p('סוג מעון', 'Dorm Type'),
    labelReason: p('סיבה', 'Reason'),
    genderMale: p(localizeGender('male', 'he'), localizeGender('male', 'en')),
    genderFemale: p(localizeGender('female', 'he'), localizeGender('female', 'en')),
    religionJewish: p('יהודי', 'Jewish'),
    religionMuslim: p('מוסלמי', 'Muslim'),
    religionChristian: p('נוצרי', 'Christian'),
    religionDruze: p('דרוזי', 'Druze'),
    dormCouples: p('זוגות', 'Couples'),
    dormSingle: p('בודדים', 'Singles'),
    addReasonPlaceholder: p('הסבר מדוע הסטודנט זקוק למקום במעון...', 'Explain why the student needs a place in the dorms...'),
    summaryName: p('שם', 'Name'),
    summaryIdShort: p('ת.ז', 'ID'),
    summaryPhone: p('טלפון', 'Phone'),
    summaryEmail: p('אימייל', 'Email'),
    summaryCity: p('עיר', 'City'),
    summaryGender: p('מגדר', 'Gender'),
    summaryReligion: p('דת', 'Religion'),
    summaryDormType: p('סוג מעון', 'Dorm Type'),
    summaryReason: p('סיבה', 'Reason'),

    // ── RemoveWizard ──
    removeSteps: [p('בחר סטודנט', 'Select Student'), p('שיבוץ נוכחי', 'Current Placement'), p('סיבה', 'Reason'), p('אישור', 'Confirm')],
    removeStep0Title: p('בחר סטודנט להסרה', 'Select Student to Remove'),
    removeStep1Title: p('שיבוץ נוכחי', 'Current Placement'),
    removeStep2Title: p('סיבת ההסרה', 'Removal Reason'),
    removeStep3Title: p('אישור הסרה', 'Confirm Removal'),
    fieldBuilding: p('בניין', 'Building'),
    fieldApartment: p('דירה', 'Apartment'),
    fieldRoom: p('חדר', 'Room'),
    fieldBed: p('מיטה', 'Bed'),
    removeNote: p('לאחר האישור, המיטה תתפנה ופרטי הסטודנט יסומנו כלא פעיל.', 'Once confirmed, the bed will be freed and the student will be marked inactive.'),
    removeReasonPlaceholder: p('הסבר מדוע הסטודנט מוסר...', 'Explain why the student is being removed...'),
    summaryStudent: p('סטודנט', 'Student'),
    summaryPlacement: p('שיבוץ', 'Placement'),
    confirmRemoveBtn: p('אשר', 'Confirm'),
    loc3,

    // ── SwapWizard ──
    swapSteps: [p('סטודנט א׳', 'Student A'), p('סטודנט ב׳', 'Student B'), p('סיבה', 'Reason'), p('אישור', 'Confirm')],
    swapStep0Title: p('בחר סטודנט ראשון', 'Select First Student'),
    swapStep1Title: p('בחר סטודנט שני להחלפה', 'Select Second Student to Swap With'),
    swapStep2Title: p('סיבת החילוף', 'Swap Reason'),
    swapStep3Title: p('אישור חילוף', 'Confirm Swap'),
    swapDifferentStudents: p('יש לבחור שני סטודנטים שונים', 'Please select two different students'),
    swapReasonPlaceholder: p('הסבר מדוע מבוקש החילוף...', 'Explain why the swap is requested...'),
    summaryStudentA: p('סטודנט א׳', 'Student A'),
    summaryStudentB: p('סטודנט ב׳', 'Student B'),
    submitSwapBtn: p('שלח בקשת חילוף', 'Submit Swap Request'),

    // ── TransferWizard ──
    transferStepStudent: p('בחר סטודנט', 'Select Student'),
    transferStepScope: p('סוג מעבר', 'Transfer Type'),
    transferStepDetails: p('פרטים', 'Details'),
    transferStepOptions: p('אפשרויות', 'Options'),
    transferStepConfirm: p('אישור', 'Confirm'),
    transferStudentTitle: p('בחר סטודנט', 'Select Student'),
    transferScopeTitle: p('סוג המעבר', 'Transfer Type'),
    scopeSameApartment: p('בתוך אותה דירה', 'Within the same apartment'),
    scopeSameRegion: p('לדירה אחרת באותו אזור', 'Different apartment, same region'),
    scopeCrossRegion: p('לאזור אחר', 'To a different region'),
    scopeCentralOnlyTitle: p('רק מנהל מרכזי יכול ליצור מעבר לאזור אחר', 'Only a central admin can create a cross-region transfer'),
    targetRegionLabel: p('אזור יעד:', 'Target region:'),
    currentStudentRegionFallback: p('האזור הנוכחי של הסטודנט', "the student's current region"),
    hintSameApartment: p('מעבר לחדר/מיטה אחרת בתוך הדירה הנוכחית', 'Transfer to a different room/bed within the current apartment'),
    hintSameRegion: p('נבחר אוטומטית - האזור הנוכחי של הסטודנט', "Chosen automatically - the student's current region"),
    nonCentralNote: p(
      'משתמש אזורי רשאי לבצע מעברים בתוך האזור המורשה בלבד; מעבר לאזור אחר מוגש על ידי מנהל מרכזי',
      'A regional user may only make transfers within their authorized region; cross-region transfers are submitted by a central admin'
    ),
    destRegionLabel: p('אזור יעד', 'Target region'),
    searchRegionPlaceholder: p('חיפוש אזור...', 'Search region...'),
    noRegionsFound: p('לא נמצאו אזורים', 'No regions found'),
    currentRegionTag: p('(האזור הנוכחי)', '(current region)'),
    selectedLabel: p('נבחר:', 'Selected:'),
    detailsTitle: p('פרטי הבקשה', 'Request Details'),
    otherDescLabel: p('תיאור הבקשה', 'Request Description'),
    otherDescPlaceholder: p('תאר את הבקשה...', 'Describe the request...'),
    transferReasonPlaceholder: p('הסבר את סיבת הבקשה...', 'Explain the reason for the request...'),
    optionsTitle: p('אפשרויות שיבוץ', 'Assignment Options'),
    optionsSameApartmentHint: p('מוצגות מיטות פנויות בדירה הנוכחית בלבד', 'Only free beds in the current apartment are shown'),
    checkOptionsBtn: p('בדיקת אפשרויות שיבוץ', 'Check assignment options'),
    searchingEllipsis: p('מחפש...', 'Searching...'),
    confirmSummaryTitle: p('סיכום לפני שליחה', 'Summary Before Submitting'),
    summaryCurrentPlacement: p('שיבוץ נוכחי', 'Current Placement'),
    summaryTransferType: p('סוג מעבר', 'Transfer Type'),
    summaryTargetRegion: p('אזור יעד', 'Target Region'),
    summarySelectedTarget: p('יעד נבחר', 'Selected Target'),
    summaryDescription: p('תיאור', 'Description'),
    singlePlace: p('מקום יחיד', 'single place'),
    bedWord: p('מיטה', 'bed'),
    loc3WithRegion,

    // ── ActionPanel ──
actionsLabel: p('פעולות', 'Actions'),

deleteRequestBtn: p('מחק בקשה', 'Delete Request'),

deleteRequestConfirmText: (name: Loc) => p(
  `האם למחוק את הבקשה של ${name}? פעולה זו תמחק את הבקשה בלבד ולא את הסטודנט מהמערכת.`,
  `Delete the request for ${name}? This will delete only the request and not the student from the system.`
),

deleteRequestError: p(
  'שגיאה במחיקת הבקשה',
  'Failed to delete request'
),

pendingDestinationReviewNote: p(
  'בקשת ההעברה ממתינה לבדיקה ואישור על ידי אזור היעד',
  "The transfer request is awaiting review and approval by the destination region"
),

rejectPlaceholder: p(
  'סיבת הדחייה (אופציונלי)...',
  'Rejection reason (optional)...'
),

rejectBtn: p('דחה', 'Reject'),
approveRemoveBtn: p('אשר הסרה', 'Confirm Removal'),

    // ── DetailPane ──
    tlCreated: p('נוצרה', 'Created'),
    tlPendingApproval: p('ממתינה לאישור', 'Awaiting approval'),
    tlApprovalFallback: p('אישור', 'Approval'),
    sectionRequestRoute: p('מסלול הבקשה', 'Request Route'),
    sectionCurrentPlacement: p('שיבוץ נוכחי', 'Current Placement'),
    sectionRequestDetails: p('פרטי הבקשה', 'Request Details'),
    dpTypeLabel: p('סוג הבקשה:', 'Request type:'),
    kvTransferType: p('סוג מעבר', 'Transfer Type'),
    transferTypeCrossRegion: p('לאזור אחר', 'To a different region'),
    transferTypeSameApartment: p('בתוך אותה דירה', 'Within the same apartment'),
    transferTypeSameRegionDiffApt: p('לדירה אחרת באותו אזור', 'Different apartment, same region'),
    transferTypeFallback: p('מעבר בתוך האזור הנוכחי', 'Transfer within the current region'),
    kvSourceRegion: p('אזור מוצא', 'Source Region'),
    kvTargetRegion: p('אזור יעד', 'Target Region'),
    kvFinalPlacement: p('שיבוץ סופי', 'Final Placement'),
    kvSwapWith: p('מחליף/ה עם', 'Swapping with'),
    kvReason: p('סיבה', 'Reason'),
    kvDescription: p('תיאור', 'Description'),
    kvOpenedBy: p('נפתח ע"י', 'Opened by'),
    kvDate: p('תאריך', 'Date'),
    kvHandledBy: p('טופל ע"י', 'Handled by'),
    historyToggle: (n: number | string) => p(`היסטוריית שיבוצים (${n})`, `Placement history (${n})`),
    rejectionReasonLabel: p('סיבת הדחייה:', 'Rejection reason:'),
    dash: '—',

    // ── Request type / status labels (R4) ──
    // Previously the page's TYPE_CFG / STATUS_CFG tables carried these as
    // labelHe/labelEn pairs picked with `language === 'he' ? ... : ...`.
    typeLabelRoom: p('שינוי חדר', 'Room Transfer'),
    typeLabelApartment: p('מעבר מדירה', 'Apt Transfer'),
    typeLabelOther: p('בקשה אחרת', 'Other'),
    typeLabelAddStudent: p('הוספת סטודנט', 'Add Student'),
    typeLabelRemoveStudent: p('הסרה ממעונות', 'Remove Student'),
    typeLabelSwap: p('חילוף בין סטודנטים', 'Student Swap'),
    typeLabelRegionTransfer: p('העברה בין אזורים', 'Region Transfer'),
    // Cross-region transfers are stored as room/apartment + transfer_scope -
    // but must never be LABELED "מעבר מדירה"; the scope is the meaningful type.
    typeLabelCrossRegion: p('מעבר לאזור אחר', 'Cross-region Transfer'),
    statusPending: p('ממתינה', 'Pending'),
    statusApproved: p('אושרה', 'Approved'),
    statusRejected: p('נדחתה', 'Rejected'),
    statusCancelled: p('בוטלה', 'Cancelled'),

    // ── Keys the page reads that were never defined (R4) ──
    // TransfersPage.jsx rendered `T.<key>` for these, but no dictionary ever
    // declared them, so they rendered as nothing (undefined). They are kept
    // as empty strings so the page renders exactly as before; filling them
    // in is a product decision, not part of the decomposition.
    fieldRegion: '',
    approveSwapBtn: '',
    checkingEllipsis: '',
    checkAvailabilityBtn: '',
    recheckBtn: '',
    selectBedToApprove: '',
    assignNotePrefix: '',
    crossRegionFromPrefix: '',
    crossRegionFromSuffix: '',
    crossRegionHint: '',
    targetRegionColon: '',
  };
});

export type TransfersStrings = typeof transfersStrings.he;
