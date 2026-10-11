from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from ..domains.analytics.queries import build_home_dashboard_read_model
from ..models import AllocationRun, ImportBatch, RegionInbox
from ..serializers import (
    AllocationRunSerializer, ImportBatchSerializer, RegionInboxSerializer,
)
from ..contracts.errors import error_response

_HOME_REQUEST_TYPE_LABELS_EN = {
    'add_student': 'Add student',
    'remove_student': 'Remove student',
    'room': 'Room change',
    'apartment': 'Apartment transfer',
    'swap': 'Student swap',
    'region_transfer': 'Region transfer',
    'other': 'Other request',
}


def _home_action(key, label_he, label_en, route):
    return {'key': key, 'label_he': label_he, 'label_en': label_en, 'route': route}


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def home_dashboard(request):
    """
    Aggregated, read-only data for the post-login operational homepage.

    central_admin gets a system-wide view; region_boss/employee get their
    own region's view (server-side enforced, mirrors the scoping already
    used by statistics/allocation_summary/list_batches/region_inbox).
    """
    user = request.user
    is_admin = user.is_central_admin
    can_upload = is_admin
    can_run_allocation = user.is_boss
    can_review_requests = user.is_boss

    if is_admin:
        region = None
    else:
        region = user.region
        if not region:
            return error_response(status.HTTP_400_BAD_REQUEST, 'המשתמש אינו משויך לאזור', error_en='User is not assigned to a region')

    home_data = build_home_dashboard_read_model(region, is_admin)
    assigned_students = home_data['assigned_students']
    unassigned_students = home_data['unassigned_students']
    occupancy_rate = home_data['occupancy_rate']
    available_beds = home_data['available_beds']
    pending_requests = home_data['pending_requests']
    latest_batch = home_data['latest_batch']
    latest_inbox = home_data['latest_inbox']
    active_run = home_data['active_run']
    latest_run = home_data['latest_run']
    has_completed_run = home_data['has_completed_run']
    latest_run_failed = home_data['latest_run_failed']
    pending_inbox_count = home_data['pending_inbox_count']
    regions_high_occupancy_count = home_data['regions_high_occupancy_count']
    regions_with_failed_latest = home_data['regions_with_failed_latest']
    priority_students_pending = home_data['priority_students_pending']
    stage_upload = home_data['stage_upload']
    stage_review = home_data['stage_review']
    stage_processing = home_data['stage_processing']
    stage_allocation = home_data['stage_allocation']
    stage_results = home_data['stage_results']

    workflow = [
        {'key': 'upload', 'label_he': 'העלאת קובץ', 'label_en': 'File upload', 'status': stage_upload},
        {'key': 'data_review', 'label_he': 'סקירת נתונים', 'label_en': 'Data review', 'status': stage_review},
        {'key': 'regional_processing', 'label_he': 'עיבוד אזורי', 'label_en': 'Regional processing', 'status': stage_processing},
        {'key': 'allocation', 'label_he': 'שיבוץ', 'label_en': 'Allocation', 'status': stage_allocation},
        {'key': 'results_review', 'label_he': 'סקירת תוצאות', 'label_en': 'Results review', 'status': stage_results},
    ]

    # ---- Situation sentence ----
    if stage_upload == 'attention' or stage_allocation == 'attention':
        situation_he = 'יש נושאים שדורשים את תשומת ליבכם בתהליך השיבוץ הנוכחי'
        situation_en = 'There are issues in the current allocation process that need your attention'
    elif stage_allocation == 'active':
        situation_he = 'תהליך השיבוץ פעיל כרגע'
        situation_en = 'The allocation process is currently running'
    elif stage_review == 'active' or stage_processing == 'active':
        situation_he = 'ישנם נתוני סטודנטים חדשים הממתינים לסקירה'
        situation_en = 'New student data is waiting for review'
    elif stage_results == 'completed':
        situation_he = 'תהליך השיבוץ הנוכחי הושלם ואין נושאים פתוחים'
        situation_en = 'The current allocation process is complete with no open issues'
    else:
        situation_he = 'הכל מתנהל כסדרו כרגע'
        situation_en = 'Everything is on track right now'

    # ---- Primary action (respects what this role can actually do) ----
    primary_action = None

    if latest_batch is not None and latest_batch.status == ImportBatch.Status.FAILED and can_upload:
        primary_action = _home_action('upload_retry', 'העלאת הקובץ נכשלה - נסו שוב', 'Upload failed — try again', '/upload')
    elif latest_batch is None and can_upload:
        primary_action = _home_action('upload', 'העלאת קובץ סטודנטים', 'Upload student file', '/upload')
    elif active_run is not None:
        primary_action = _home_action('view_active', 'צפייה בשיבוץ הפעיל', 'View active allocation', '/allocation')
    elif region is not None and latest_inbox is not None and latest_inbox.status == RegionInbox.Status.PENDING:
        primary_action = (
            _home_action('review_data', 'סקירת נתוני האזור', 'Review regional data', '/allocation')
            if can_run_allocation else
            _home_action('view_region_status', 'צפייה בסטטוס האזור', 'View regional status', '/allocation')
        )
    elif latest_run_failed and can_run_allocation:
        primary_action = _home_action('retry_allocation', 'הרצת השיבוץ נכשלה - נסו שוב', 'Allocation failed — retry', '/allocation')
    elif region is not None and not has_completed_run and latest_inbox is not None \
            and latest_inbox.status in (RegionInbox.Status.VIEWED, RegionInbox.Status.PROCESSED):
        primary_action = (
            _home_action('run_allocation', 'הרצת שיבוץ', 'Run allocation', '/allocation')
            if can_run_allocation else
            _home_action('view_region_status', 'צפייה בסטטוס האזור', 'View regional status', '/allocation')
        )
    elif has_completed_run and unassigned_students > 0:
        primary_action = _home_action(
            'review_unassigned',
            'סקירת סטודנטים ללא שיבוץ',
            'Review unassigned students',
            '/students?tab=unassigned'
        )
    elif pending_requests > 0:
        primary_action = (
            _home_action('review_requests', 'סקירת בקשות ממתינות', 'Review pending requests', '/transfers')
            if can_review_requests else
            _home_action('view_requests', 'צפייה בבקשות', 'View requests', '/transfers')
        )
    elif has_completed_run:
        primary_action = _home_action('review_results', 'צפייה בתוצאות השיבוץ', 'View allocation results', '/allocation/results')

    # ---- Attention items ----
    attention_items = []

    if unassigned_students > 0:
        attention_items.append({
            'id': 'unassigned-students', 'severity': 'warning', 'icon': 'users', 'count': unassigned_students,
            'title_he': 'סטודנטים ללא שיבוץ', 'title_en': 'Unassigned students',
            'description_he': f'{unassigned_students} סטודנטים ממתינים לשיבוץ לחדר',
            'description_en': f'{unassigned_students} students are waiting for a room assignment',
            'route': '/students?tab=unassigned',
        })

    if pending_requests > 0:
        attention_items.append({
            'id': 'pending-requests', 'severity': 'warning', 'icon': 'arrow-left-right', 'count': pending_requests,
            'title_he': 'בקשות ממתינות לטיפול', 'title_en': 'Pending requests',
            'description_he': f'{pending_requests} בקשות סטודנטים ממתינות לטיפול',
            'description_en': f'{pending_requests} student requests await review',
            'route': '/transfers',
        })

    if latest_batch is not None and latest_batch.status == ImportBatch.Status.FAILED and can_upload:
        attention_items.append({
            'id': 'upload-failed', 'severity': 'error', 'icon': 'upload', 'count': None,
            'title_he': 'העלאת קובץ נכשלה', 'title_en': 'File upload failed',
            'description_he': latest_batch.error_message or 'ההעלאה האחרונה נכשלה, נסו שוב',
            'description_en': latest_batch.error_message or 'The latest upload failed, please try again',
            'route': '/upload',
        })

    if latest_run_failed and can_run_allocation:
        attention_items.append({
            'id': 'allocation-failed', 'severity': 'error', 'icon': 'shuffle', 'count': None,
            'title_he': 'הרצת השיבוץ האחרונה נכשלה', 'title_en': 'Latest allocation run failed',
            'description_he': latest_run.error_message or 'נסו להריץ שיבוץ מחדש',
            'description_en': latest_run.error_message or 'Try running the allocation again',
            'route': '/allocation',
        })

    if active_run is not None:
        attention_items.append({
            'id': 'allocation-running', 'severity': 'info', 'icon': 'clock', 'count': None,
            'title_he': 'שיבוץ פעיל כעת', 'title_en': 'Allocation currently running',
            'description_he': 'תהליך השיבוץ באזור שלכם פעיל כרגע',
            'description_en': 'An allocation run is currently in progress',
            'route': '/allocation',
        })

    if region is not None and latest_inbox is not None and latest_inbox.status in (
        RegionInbox.Status.PENDING, RegionInbox.Status.VIEWED
    ):
        attention_items.append({
            'id': 'inbox-not-processed', 'severity': 'warning', 'icon': 'inbox', 'count': latest_inbox.students_count,
            'title_he': 'נתוני סטודנטים חדשים ממתינים', 'title_en': 'New student data awaiting processing',
            'description_he': f'{latest_inbox.students_count} סטודנטים חדשים התקבלו וטרם טופלו',
            'description_en': f'{latest_inbox.students_count} new students received and not yet processed',
            'route': '/allocation',
        })

    if is_admin and pending_inbox_count > 0:
        # NOTE: this item is intentionally NOT rendered by the frontend
        # dashboard anymore (see HomePage.js) - the Central Admin "regions
        # with unviewed new data" card was replaced by the clickable
        # 'regions-high-occupancy' card below. It is kept here, unchanged,
        # purely so this endpoint keeps returning pending_inbox_count for
        # backend regression coverage (see the G1-06 consolidated-groupby
        # correctness test in api/tests/performance/test_home_dashboard_performance.py,
        # which has no other way to observe this system-wide number).
        attention_items.append({
            'id': 'regions-pending-review', 'severity': 'warning', 'icon': 'inbox', 'count': pending_inbox_count,
            'title_he': 'אזורים עם נתונים חדשים שטרם נצפו', 'title_en': 'Regions with unviewed new data',
            'description_he': f'{pending_inbox_count} אזורים טרם צפו בנתוני הסטודנטים החדשים שלהם',
            'description_en': f'{pending_inbox_count} regions have not yet viewed their new student data',
            'route': None,
        })

    if is_admin and regions_high_occupancy_count > 0:
        attention_items.append({
            'id': 'regions-high-occupancy', 'severity': 'warning', 'icon': 'percent', 'count': regions_high_occupancy_count,
            'title_he': 'אזורים בתפוסה גבוהה', 'title_en': 'High-occupancy regions',
            'description_he': f'{regions_high_occupancy_count} אזורים נמצאים בתפוסה של 90% ומעלה',
            'description_en': f'{regions_high_occupancy_count} regions are at 90% occupancy or higher',
            'route': '/analysis',
        })

    if is_admin and regions_with_failed_latest > 0:
        attention_items.append({
            'id': 'regions-failed-allocation', 'severity': 'error', 'icon': 'shuffle', 'count': regions_with_failed_latest,
            'title_he': 'אזורים עם הרצת שיבוץ שנכשלה', 'title_en': 'Regions with a failed allocation run',
            'description_he': f'{regions_with_failed_latest} אזורים עם הרצת השיבוץ האחרונה שלהם נכשלה',
            'description_en': f'{regions_with_failed_latest} regions have a failed latest allocation run',
            'route': None,
        })

    if is_admin and priority_students_pending > 0:
        attention_items.append({
            'id': 'priority-students', 'severity': 'info', 'icon': 'star', 'count': priority_students_pending,
            'title_he': 'סטודנטים בעדיפות ללא שיבוץ', 'title_en': 'Priority students without assignment',
            'description_he': f'{priority_students_pending} סטודנטים בעדיפות ממתינים לשיבוץ',
            'description_en': f'{priority_students_pending} priority students are waiting for assignment',
            'route': '/priority',
        })

    severity_order = {'error': 0, 'warning': 1, 'info': 2}
    attention_items.sort(key=lambda item: severity_order.get(item['severity'], 3))

    # ---- Recent activity (uploads + allocation runs + student requests) ----
    recent_activity = []

    for b in home_data['recent_batches']:
        recent_activity.append({
            'id': f'batch-{b.id}', 'type': 'upload', 'icon': 'upload', 'status': b.status,
            'title_he': f'קובץ הועלה: {b.filename}', 'title_en': f'File uploaded: {b.filename}',
            'subtitle_he': f'{b.total_students} סטודנטים', 'subtitle_en': f'{b.total_students} students',
            'timestamp': b.created_at.isoformat() if b.created_at else None,
            'route': '/upload' if is_admin else '/allocation',
        })

    completed_like = {AllocationRun.Status.COMPLETED, AllocationRun.Status.APPROVED}
    for r in home_data['recent_runs']:
        r_time = r.completed_at or r.started_at
        recent_activity.append({
            'id': f'run-{r.id}', 'type': 'allocation', 'icon': 'shuffle', 'status': r.status,
            'title_he': f'הרצת שיבוץ - {r.region.name}', 'title_en': f'Allocation run - {r.region.name}',
            'subtitle_he': f'{r.successful_assignments} שיבוצים מוצלחים', 'subtitle_en': f'{r.successful_assignments} successful assignments',
            'timestamp': r_time.isoformat() if r_time else None,
            'route': '/allocation/results' if r.status in completed_like else '/allocation',
        })

    for sr in home_data['recent_requests']:
        student_label = sr.student.full_name if sr.student else (sr.student_data or {}).get('first_name', '') or ''
        type_he = sr.get_request_type_display()
        type_en = _HOME_REQUEST_TYPE_LABELS_EN.get(sr.request_type, sr.request_type)
        recent_activity.append({
            'id': f'request-{sr.id}', 'type': 'request', 'icon': 'file-text', 'status': sr.status,
            'title_he': f'{type_he} - {student_label}'.strip(' -') if student_label else type_he,
            'title_en': f'{type_en} - {student_label}'.strip(' -') if student_label else type_en,
            'subtitle_he': (sr.reason or '')[:80], 'subtitle_en': (sr.reason or '')[:80],
            'timestamp': sr.created_at.isoformat() if sr.created_at else None,
            'route': '/transfers',
        })

    recent_activity_by_id = {item['id']: item for item in recent_activity}
    recent_activity = [
        recent_activity_by_id[item_id]
        for item_id in home_data['recent_activity_order']
    ]

    return Response({
        'user': {
            'name': user.get_full_name() or user.email,
            'role': user.role,
            'role_display': user.get_role_display(),
            'region_id': region.id if region else None,
            'region_name': region.name if region else None,
        },
        'scope': 'system' if region is None else 'region',
        'metrics': {
            'assigned_students': assigned_students,
            'unassigned_students': unassigned_students,
            'occupancy_rate': occupancy_rate,
            'available_beds': available_beds,
            'pending_requests': pending_requests,
        },
        'process': {
            'latest_batch': ImportBatchSerializer(latest_batch).data if latest_batch else None,
            'latest_inbox': RegionInboxSerializer(latest_inbox).data if latest_inbox else None,
            'active_run': AllocationRunSerializer(active_run).data if active_run else None,
            'latest_run': AllocationRunSerializer(latest_run).data if latest_run else None,
            'has_completed_run': has_completed_run,
        },
        'workflow': workflow,
        'situation_he': situation_he,
        'situation_en': situation_en,
        'primary_action': primary_action,
        'attention_items': attention_items,
        'recent_activity': recent_activity,
    })
