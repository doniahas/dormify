"""Analytics read-model queries and aggregation."""

import re

from django.db.models import Count, IntegerField, OuterRef, Q, Subquery, Sum
from django.db.models.functions import Coalesce

from ..allocation.orchestration import _population_summary_for_region
from ..imports.parsing import EXCEL_DORM_NAME_TO_OFFICIAL_CODE, safe_int, safe_str
from ...models import (
    AllocationRun,
    Apartment,
    Bed,
    BedAssignment,
    Building,
    DormType,
    ImportBatch,
    Region,
    RegionInbox,
    Room,
    Student,
    StudentRequest,
    Transfer,
)


def _annotate_analysis_building_occupancy(buildings_qs, rooms_qs, assignments_qs):
    """
    Queryset-level replacement for the three per-building queries
    analysis_data()'s occupancy_data loop used to run once per building row
    (measured baseline: 3 extra SQL queries per building,
    `total_queries = 31 + 3*N`; the analysis performance tests now pin a
    flat query count that must not scale with building count):

      - building_capacity: sum(building_rooms_qs.values_list('capacity', flat=True))
      - building_assigned_beds: assignments_qs.filter(...).values('bed_id').distinct().count()
      - rooms_count: building_rooms_qs.count()

    Same technique already used and verified for Buildings (BLD-01) /
    Apartments (BLD-02) / Rooms (BLD-03) / Beds (BLD-04) via
    _annotate_building_inventory_counts / _annotate_apartment_inventory_counts
    above: each aggregate is an INDEPENDENT correlated subquery (Subquery +
    OuterRef, grouped by the target FK), not several Count()/Sum()
    annotations combined in one annotate() call on joined relations - this
    deliberately avoids the classic Django multi-aggregate JOIN-
    multiplication trap, where combining e.g. a Sum() over rooms and a
    Count() over assignments in the same annotate() would silently inflate
    both by the cross-joined row count of the other relation. Each subquery
    below is independently grouped/evaluated per building and runs inside
    the single `buildings_qs` SQL statement, so results are mathematically
    identical to running the original three queries once per building -
    just computed once, in one round trip, instead of 3*N times.

    `rooms_qs` and `assignments_qs` are passed in exactly as
    analysis_data() already built them (including its is_active and
    region scoping) - this function only adds the
    `apartment__building=OuterRef('pk')` /
    `bed__room__apartment__building=OuterRef('pk')` correlation on top,
    reproducing `building_rooms_qs = rooms_qs.filter(apartment__building=building)`
    and `assignments_qs.filter(bed__room__apartment__building=building)`
    field-for-field. Filtering semantics are therefore preserved exactly,
    with no re-interpretation of what counts as "active"/in-region:
    - _capacity: sum of Room.capacity for rooms matching the caller's
      rooms_qs (active room, active apartment, active building, optional
      region) under this building. NULL (no matching rooms) -> 0, matching
      the original `sum(empty values_list)` which is 0, never None.
    - _rooms_count: count of that same room set - same filter as
      _capacity, count instead of sum, matching the original
      `building_rooms_qs.count()` using the identical `building_rooms_qs`.
    - _assigned_beds: distinct bed count from the caller's assignments_qs
      (ACTIVE status, active room/apartment/building, optional region)
      under this building - matches the original
      `.values('bed_id').distinct().count()` exactly, including the
      distinct-bed semantics.
    """
    capacity_and_rooms_sq = rooms_qs.filter(
        apartment__building=OuterRef('pk'),
    ).order_by().values('apartment__building').annotate(
        cap=Sum('capacity'),
    ).values('cap')

    rooms_count_sq = rooms_qs.filter(
        apartment__building=OuterRef('pk'),
    ).order_by().values('apartment__building').annotate(
        c=Count('id'),
    ).values('c')

    assigned_beds_sq = assignments_qs.filter(
        bed__room__apartment__building=OuterRef('pk'),
    ).order_by().values('bed__room__apartment__building').annotate(
        c=Count('bed_id', distinct=True),
    ).values('c')

    return buildings_qs.annotate(
        _capacity=Coalesce(Subquery(capacity_and_rooms_sq, output_field=IntegerField()), 0),
        _rooms_count=Coalesce(Subquery(rooms_count_sq, output_field=IntegerField()), 0),
        _assigned_beds=Coalesce(Subquery(assigned_beds_sq, output_field=IntegerField()), 0),
    )


def build_analysis_read_model(region):
    students_qs = Student.objects.all()

    rooms_qs = Room.objects.filter(
        is_active=True,
        apartment__is_active=True,
        apartment__building__is_active=True,
    )

    buildings_qs = Building.objects.filter(
        is_active=True
    ).select_related(
        'dorm_type',
        'dorm_type__region'
    )

    assignments_qs = BedAssignment.objects.filter(
        status=BedAssignment.Status.ACTIVE,
        bed__room__is_active=True,
        bed__room__apartment__is_active=True,
        bed__room__apartment__building__is_active=True,
    )

    transfers_qs = Transfer.objects.all()
    runs_qs = AllocationRun.objects.all()

    if region:
        students_qs = students_qs.filter(
            accepted_dorm_type__region=region
        )
        rooms_qs = rooms_qs.filter(
            apartment__building__dorm_type__region=region
        )
        buildings_qs = buildings_qs.filter(
            dorm_type__region=region
        )
        assignments_qs = assignments_qs.filter(
            bed__room__apartment__building__dorm_type__region=region
        )
        transfers_qs = transfers_qs.filter(
            Q(from_room__apartment__building__dorm_type__region=region) |
            Q(to_room__apartment__building__dorm_type__region=region)
        )
        runs_qs = runs_qs.filter(region=region)

    total_students = students_qs.count()
    assignment_student_bed_pairs = list(
        assignments_qs.values('student_id', 'bed_id')
    )
    assigned_student_ids = {row['student_id'] for row in assignment_student_bed_pairs}
    assigned_students = len(assigned_student_ids)
    unassigned_students = max(total_students - assigned_students, 0)

    allocatable_students_qs = students_qs.exclude(
        category=Student.StudentCategory.LEAVING
    ).exclude(accessibility_flag=True)
    priority_students = allocatable_students_qs.filter(is_priority=True).count()

    room_aggregate = rooms_qs.aggregate(total_capacity=Sum('capacity'), total_rooms=Count('id'))
    total_capacity = room_aggregate['total_capacity'] or 0
    total_rooms = room_aggregate['total_rooms'] or 0

    assigned_beds = len({row['bed_id'] for row in assignment_student_bed_pairs})
    available_beds = max(total_capacity - assigned_beds, 0)

    occupancy_rate = 0
    if total_capacity > 0:
        occupancy_rate = round((assigned_beds / total_capacity) * 100, 2)

    total_buildings = buildings_qs.count()

    if region:
        all_buildings_count = Building.objects.filter(
            dorm_type__region=region
        ).count()
        inactive_buildings_count = Building.objects.filter(
            dorm_type__region=region,
            is_active=False
        ).count()
    else:
        all_buildings_count = Building.objects.count()
        inactive_buildings_count = Building.objects.filter(is_active=False).count()

    transfers_by_status = list(
        transfers_qs
        .values('status')
        .annotate(count=Count('id'))
        .order_by('status')
    )
    total_transfers = sum(row['count'] for row in transfers_by_status)
    pending_transfers = next(
        (row['count'] for row in transfers_by_status if row['status'] == Transfer.Status.PENDING),
        0,
    )

    latest_run = runs_qs.select_related('run_by', 'region').order_by('-started_at').first()

    requests_qs = StudentRequest.objects.filter(status=StudentRequest.Status.PENDING)
    if region:
        requests_qs = requests_qs.filter(
            Q(requested_by__region_id=region.id) |
            Q(student__accepted_dorm_type__region_id=region.id) |
            Q(target_room__apartment__building__dorm_type__region_id=region.id)
        ).distinct()

    pending_requests_by_type = list(
        requests_qs
        .values('request_type')
        .annotate(count=Count('id'))
        .order_by('-count')
    )
    pending_requests = sum(row['count'] for row in pending_requests_by_type)

    priority_unassigned_students = allocatable_students_qs.filter(
        is_priority=True
    ).exclude(
        id__in=assignments_qs.values('student_id')
    ).count()

    if region is None:
        latest_batch = ImportBatch.objects.select_related('uploaded_by').order_by('-created_at').first()
    else:
        batch_ids = RegionInbox.objects.filter(region=region).values_list('batch_id', flat=True)
        latest_batch = ImportBatch.objects.filter(
            id__in=batch_ids
        ).select_related('uploaded_by').order_by('-created_at').first()

    students_by_gender = list(
        students_qs
        .values('gender')
        .annotate(count=Count('id'))
        .order_by('gender')
    )
    students_by_religion = list(
        students_qs
        .values('requested_religion')
        .annotate(count=Count('id'))
        .order_by('requested_religion')
    )
    students_by_religious = list(
        students_qs
        .values('religious')
        .annotate(count=Count('id'))
        .order_by('religious')
    )
    students_by_category = list(
        students_qs
        .values('category')
        .annotate(count=Count('id'))
        .order_by('category')
    )
    students_by_housing = list(
        students_qs
        .values('housing_type')
        .annotate(count=Count('id'))
        .order_by('housing_type')
    )

    def _normalize_for_region_match(value):
        return re.sub(r'\s+', '', safe_str(value)).lower()

    dorm_types_for_region = DormType.objects.select_related('region').all()
    region_by_dorm_name = {}
    region_by_dorm_code = {}

    for dorm_type in dorm_types_for_region:
        if not dorm_type.region:
            continue
        if dorm_type.name:
            region_by_dorm_name[_normalize_for_region_match(dorm_type.name)] = dorm_type.region.name
        if dorm_type.code is not None:
            region_by_dorm_code[str(dorm_type.code)] = dorm_type.region.name

    def _resolve_region_name_from_student_text(value):
        raw_value = safe_str(value)
        if not raw_value:
            return None
        normalized_value = _normalize_for_region_match(raw_value)
        code_int = safe_int(raw_value, default=None)
        if code_int is not None:
            region_name = region_by_dorm_code.get(str(code_int))
            if region_name:
                return region_name
        region_name = region_by_dorm_name.get(normalized_value)
        if region_name:
            return region_name
        alias_code = EXCEL_DORM_NAME_TO_OFFICIAL_CODE.get(normalized_value)
        if alias_code is not None:
            region_name = region_by_dorm_code.get(str(alias_code))
            if region_name:
                return region_name
        for dorm_name_normalized, region_name in region_by_dorm_name.items():
            if dorm_name_normalized and dorm_name_normalized in normalized_value:
                return region_name
        for alias_name_normalized, alias_code in EXCEL_DORM_NAME_TO_OFFICIAL_CODE.items():
            if alias_name_normalized and alias_name_normalized in normalized_value:
                region_name = region_by_dorm_code.get(str(alias_code))
                if region_name:
                    return region_name
        return None

    students_by_region_counts = {}
    students_by_region_demand = {}

    for student in students_qs.select_related(
            'accepted_dorm_type',
            'accepted_dorm_type__region',
    ):
        region_name = None
        if student.accepted_dorm_type and student.accepted_dorm_type.region:
            region_name = student.accepted_dorm_type.region.name
        if not region_name:
            region_name = _resolve_region_name_from_student_text(student.current_dorm_type)
        if not region_name:
            region_name = _resolve_region_name_from_student_text(student.current_address)
        if not region_name:
            continue

        students_by_region_counts[region_name] = students_by_region_counts.get(region_name, 0) + 1
        demand_bucket = students_by_region_demand.setdefault(
            region_name, {'total': 0, 'assigned': 0}
        )
        demand_bucket['total'] += 1
        if student.id in assigned_student_ids:
            demand_bucket['assigned'] += 1

    region_name_to_id = {r.name: r.id for r in Region.objects.all()}

    unassigned_by_region = [
        {
            'region': region_name,
            'region_id': region_name_to_id.get(region_name, ''),
            'total_students': bucket['total'],
            'assigned_students': bucket['assigned'],
            'unassigned_students': max(bucket['total'] - bucket['assigned'], 0),
        }
        for region_name, bucket in sorted(
            students_by_region_demand.items(),
            key=lambda item: item[0]
        )
    ]

    students_by_region = [
        {
            'region': region_name,
            'count': count,
        }
        for region_name, count in sorted(
            students_by_region_counts.items(),
            key=lambda item: item[0]
        )
    ]

    transfers_by_type = list(
        transfers_qs
        .values('movement_request__movement_type')
        .annotate(count=Count('id'))
        .order_by('movement_request__movement_type')
    )

    occupancy_data = []
    occupancy_buildings_qs = _annotate_analysis_building_occupancy(
        buildings_qs, rooms_qs, assignments_qs
    )

    for building in occupancy_buildings_qs.order_by(
        'dorm_type__region__name',
        'dorm_type__name',
        'number'
    ):
        building_capacity = building._capacity
        building_assigned_beds = building._assigned_beds
        building_available_beds = max(
            building_capacity - building_assigned_beds,
            0
        )
        building_occupancy_rate = 0
        if building_capacity > 0:
            building_occupancy_rate = round(
                (building_assigned_beds / building_capacity) * 100,
                2
            )
        dorm_type = building.dorm_type
        dorm_region = dorm_type.region if dorm_type else None
        occupancy_data.append({
            'building_id': building.id,
            'building': f'{dorm_type.name if dorm_type else ""} - בניין {building.number}',
            'building_number': building.number,
            'dorm_type': dorm_type.name if dorm_type else '',
            'region': dorm_region.name if dorm_region else '',
            'region_id': dorm_region.id if dorm_region else '',
            'rooms_count': building._rooms_count,
            'total_beds': building_capacity,
            'assigned': building_assigned_beds,
            'available_beds': building_available_beds,
            'occupancy_rate': building_occupancy_rate,
        })

    return {
        'summary': {
            'total_students': total_students,
            'assigned_students': assigned_students,
            'unassigned_students': unassigned_students,
            'priority_students': priority_students,
            'total_buildings': all_buildings_count,
            'active_buildings': total_buildings,
            'inactive_buildings': inactive_buildings_count,
            'total_rooms': total_rooms,
            'total_capacity': total_capacity,
            'total_beds': total_capacity,
            'assigned_beds': assigned_beds,
            'occupied_beds': assigned_beds,
            'available_beds': available_beds,
            'occupancy_rate': occupancy_rate,
            'total_transfers': total_transfers,
            'pending_transfers': pending_transfers,
            'pending_requests': pending_requests,
            'priority_unassigned_students': priority_unassigned_students,
        },
        'students_by_gender': students_by_gender,
        'students_by_religion': students_by_religion,
        'students_by_religious': students_by_religious,
        'students_by_category': students_by_category,
        'students_by_housing': students_by_housing,
        'students_by_region': students_by_region,
        'unassigned_by_region': unassigned_by_region,
        'occupancy_data': occupancy_data,
        'transfers_by_status': transfers_by_status,
        'transfers_by_type': transfers_by_type,
        'pending_requests_by_type': pending_requests_by_type,
        'latest_run': latest_run,
        'latest_batch': latest_batch,
    }


def build_statistics_read_model(region):
    if region is None:
        students = Student.objects.all()
        buildings = Building.objects.filter(is_active=True)
        rooms = Room.objects.filter(
            is_active=True,
            apartment__is_active=True,
            apartment__building__is_active=True,
        )
        active_assignments = BedAssignment.objects.filter(
            status=BedAssignment.Status.ACTIVE,
            bed__room__is_active=True,
            bed__room__apartment__is_active=True,
            bed__room__apartment__building__is_active=True,
        )
        transfers = Transfer.objects.filter(status=Transfer.Status.PENDING)
    else:
        students = Student.objects.filter(
            accepted_dorm_type__region=region
        )
        buildings = Building.objects.filter(
            dorm_type__region=region,
            is_active=True
        )
        rooms = Room.objects.filter(
            apartment__building__dorm_type__region=region,
            is_active=True,
            apartment__is_active=True,
            apartment__building__is_active=True,
        )
        active_assignments = BedAssignment.objects.filter(
            status=BedAssignment.Status.ACTIVE,
            bed__room__apartment__building__dorm_type__region=region,
            bed__room__is_active=True,
            bed__room__apartment__is_active=True,
            bed__room__apartment__building__is_active=True,
        )
        transfers = Transfer.objects.filter(
            Q(from_room__apartment__building__dorm_type__region=region) |
            Q(to_room__apartment__building__dorm_type__region=region),
            status=Transfer.Status.PENDING
        )

    total_capacity = sum(rooms.values_list('capacity', flat=True))
    if region is None:
        total_buildings_count = Building.objects.count()
        inactive_buildings_count = Building.objects.filter(is_active=False).count()
    else:
        total_buildings_count = Building.objects.filter(
            dorm_type__region=region
        ).count()
        inactive_buildings_count = Building.objects.filter(
            dorm_type__region=region,
            is_active=False
        ).count()

    occupied_beds = active_assignments.values('bed_id').distinct().count()
    assigned_students = active_assignments.values('student_id').distinct().count()

    unassigned_students = max(students.count() - assigned_students, 0)
    available_beds = max(total_capacity - occupied_beds, 0)

    occupancy_rate = 0
    if total_capacity > 0:
        occupancy_rate = round((occupied_beds / total_capacity) * 100)

    allocatable_students = students.exclude(
        category=Student.StudentCategory.LEAVING
    ).exclude(accessibility_flag=True)

    return {
        'total_students': students.count(),
        'assigned_students': assigned_students,
        'unassigned_students': unassigned_students,
        'priority_students': allocatable_students.filter(is_priority=True).count(),
        'total_buildings': total_buildings_count,
        'active_buildings': buildings.count(),
        'inactive_buildings': inactive_buildings_count,
        'total_rooms': rooms.count(),
        'total_capacity': total_capacity,
        'occupied_beds': occupied_beds,
        'available_beds': available_beds,
        'occupancy_rate': occupancy_rate,
        'pending_transfers': transfers.count(),
    }


def build_home_dashboard_read_model(region, is_admin):
    if region is None:
        students_qs = Student.objects.all()
        rooms_qs = Room.objects.filter(
            is_active=True, apartment__is_active=True, apartment__building__is_active=True,
        )
        active_assignments_qs = BedAssignment.objects.filter(
            status=BedAssignment.Status.ACTIVE,
            bed__room__is_active=True,
            bed__room__apartment__is_active=True,
            bed__room__apartment__building__is_active=True,
        )
    else:
        students_qs = Student.objects.filter(accepted_dorm_type__region=region)
        rooms_qs = Room.objects.filter(
            apartment__building__dorm_type__region=region,
            is_active=True, apartment__is_active=True, apartment__building__is_active=True,
        )
        active_assignments_qs = BedAssignment.objects.filter(
            status=BedAssignment.Status.ACTIVE,
            bed__room__apartment__building__dorm_type__region=region,
            bed__room__is_active=True,
            bed__room__apartment__is_active=True,
            bed__room__apartment__building__is_active=True,
        )

    allocatable_qs = students_qs.exclude(
        category=Student.StudentCategory.LEAVING
    ).exclude(accessibility_flag=True)

    assigned_students = allocatable_qs.filter(assigned_room__isnull=False).count()
    unassigned_students = allocatable_qs.filter(assigned_room__isnull=True).count()

    region_capacity = {}
    region_occupied_beds = {}
    if region is None:
        room_rows = rooms_qs.values('apartment__building__dorm_type__region_id').annotate(
            cap=Sum('capacity')
        )
        total_capacity = 0
        for row in room_rows:
            cap = row['cap'] or 0
            total_capacity += cap
            region_capacity[row['apartment__building__dorm_type__region_id']] = cap

        assignment_rows = active_assignments_qs.values(
            'bed__room__apartment__building__dorm_type__region_id', 'bed_id'
        ).distinct()
        region_bed_ids = {}
        for row in assignment_rows:
            region_bed_ids.setdefault(
                row['bed__room__apartment__building__dorm_type__region_id'], set()
            ).add(row['bed_id'])
        occupied_beds = sum(len(beds) for beds in region_bed_ids.values())
        region_occupied_beds = {rid: len(beds) for rid, beds in region_bed_ids.items()}
    else:
        total_capacity = sum(rooms_qs.values_list('capacity', flat=True))
        occupied_beds = active_assignments_qs.values('bed_id').distinct().count()

    available_beds = max(total_capacity - occupied_beds, 0)
    occupancy_rate = round((occupied_beds / total_capacity) * 100) if total_capacity else 0

    high_occupancy_threshold = 90
    regions_high_occupancy_count = 0
    for region_id, capacity in region_capacity.items():
        if not region_id or capacity <= 0:
            continue
        occupied = region_occupied_beds.get(region_id, 0)
        if (occupied / capacity) * 100 >= high_occupancy_threshold:
            regions_high_occupancy_count += 1

    priority_students_pending = 0
    if is_admin:
        priority_students_pending = allocatable_qs.filter(
            is_priority=True, assigned_room__isnull=True
        ).count()

    def _scope_requests(qs):
        if region is None:
            return qs
        return qs.filter(
            Q(requested_by__region_id=region.id) |
            Q(student__accepted_dorm_type__region_id=region.id) |
            Q(target_room__apartment__building__dorm_type__region_id=region.id)
        ).distinct()

    pending_requests = _scope_requests(
        StudentRequest.objects.filter(status=StudentRequest.Status.PENDING)
    ).count()

    if is_admin:
        latest_batch = ImportBatch.objects.select_related('uploaded_by').order_by('-created_at').first()
    else:
        batch_ids = RegionInbox.objects.filter(region=region).values_list('batch_id', flat=True)
        latest_batch = ImportBatch.objects.filter(
            id__in=batch_ids
        ).select_related('uploaded_by').order_by('-created_at').first()

    latest_inbox = None
    pending_inbox_count = 0
    viewed_inbox_count = 0
    if region is not None:
        latest_inbox = RegionInbox.objects.select_related('batch', 'region').filter(
            region=region
        ).order_by('-created_at').first()
        pending_inbox_count = 1 if latest_inbox and latest_inbox.status == RegionInbox.Status.PENDING else 0
        viewed_inbox_count = 1 if latest_inbox and latest_inbox.status == RegionInbox.Status.VIEWED else 0
    else:
        inbox_status_counts = {
            row['status']: row['c']
            for row in RegionInbox.objects.values('status').annotate(c=Count('id'))
        }
        pending_inbox_count = inbox_status_counts.get(RegionInbox.Status.PENDING, 0)
        viewed_inbox_count = inbox_status_counts.get(RegionInbox.Status.VIEWED, 0)

    run_qs = AllocationRun.objects.select_related('region', 'run_by')
    if region is not None:
        run_qs = run_qs.filter(region=region)

    active_run = run_qs.filter(status__in=[
        AllocationRun.Status.QUEUED,
        AllocationRun.Status.RUNNING,
        AllocationRun.Status.CANCELLATION_REQUESTED,
    ]).order_by('-started_at').first()
    latest_run = run_qs.order_by('-started_at').first()
    completed_like = {AllocationRun.Status.COMPLETED, AllocationRun.Status.APPROVED}
    has_completed_run = run_qs.filter(status__in=completed_like).exists()
    latest_run_failed = bool(latest_run and latest_run.status == AllocationRun.Status.FAILED)

    regions_with_active_run = 0
    regions_with_failed_latest = 0
    if region is None:
        latest_status_by_region = {}
        for row in AllocationRun.objects.order_by('region_id', '-started_at').values('region_id', 'status'):
            latest_status_by_region.setdefault(row['region_id'], row['status'])
        active_like = {
            AllocationRun.Status.QUEUED,
            AllocationRun.Status.RUNNING,
            AllocationRun.Status.CANCELLATION_REQUESTED,
        }
        regions_with_active_run = sum(1 for s in latest_status_by_region.values() if s in active_like)
        regions_with_failed_latest = sum(
            1 for s in latest_status_by_region.values() if s == AllocationRun.Status.FAILED
        )

    if latest_batch is None:
        stage_upload = 'active'
    elif latest_batch.status == ImportBatch.Status.FAILED:
        stage_upload = 'attention'
    else:
        stage_upload = 'completed'

    if region is not None:
        if latest_inbox is None:
            stage_review, stage_processing = 'waiting', 'waiting'
        elif latest_inbox.status == RegionInbox.Status.PENDING:
            stage_review, stage_processing = 'active', 'waiting'
        elif latest_inbox.status == RegionInbox.Status.VIEWED:
            stage_review, stage_processing = 'completed', 'active'
        else:
            stage_review, stage_processing = 'completed', 'completed'
    else:
        if pending_inbox_count > 0:
            stage_review = 'active'
            stage_processing = 'active' if viewed_inbox_count > 0 else 'waiting'
        elif viewed_inbox_count > 0:
            stage_review, stage_processing = 'completed', 'active'
        elif latest_batch is not None:
            stage_review, stage_processing = 'completed', 'completed'
        else:
            stage_review, stage_processing = 'waiting', 'waiting'

    if active_run is not None or regions_with_active_run > 0:
        stage_allocation = 'active'
    elif latest_run_failed or regions_with_failed_latest > 0:
        stage_allocation = 'attention'
    elif not has_completed_run:
        stage_allocation = 'waiting'
    else:
        stage_allocation = 'completed'

    if not has_completed_run:
        stage_results = 'waiting'
    elif unassigned_students > 0:
        stage_results = 'attention'
    else:
        stage_results = 'completed'

    batch_qs = (
        ImportBatch.objects.select_related('uploaded_by')
        if is_admin else
        ImportBatch.objects.filter(id__in=RegionInbox.objects.filter(region=region).values_list('batch_id', flat=True))
    )
    recent_batches = list(batch_qs.order_by('-created_at')[:3])
    recent_runs = list(run_qs.order_by('-started_at')[:3])
    recent_requests_qs = _scope_requests(
        StudentRequest.objects.select_related('student', 'requested_by')
    ).order_by('-created_at')[:5]
    recent_requests = list(recent_requests_qs)
    recent_activity_sources = [
        ('batch', item.id, item.created_at)
        for item in recent_batches
    ]
    recent_activity_sources.extend(
        ('run', item.id, item.completed_at or item.started_at)
        for item in recent_runs
    )
    recent_activity_sources.extend(
        ('request', item.id, item.created_at)
        for item in recent_requests
    )
    recent_activity_sources = [item for item in recent_activity_sources if item[2]]
    recent_activity_sources.sort(key=lambda item: item[2].isoformat(), reverse=True)
    recent_activity_sources = recent_activity_sources[:8]

    return {
        'assigned_students': assigned_students,
        'unassigned_students': unassigned_students,
        'occupancy_rate': occupancy_rate,
        'available_beds': available_beds,
        'pending_requests': pending_requests,
        'latest_batch': latest_batch,
        'latest_inbox': latest_inbox,
        'active_run': active_run,
        'latest_run': latest_run,
        'has_completed_run': has_completed_run,
        'latest_run_failed': latest_run_failed,
        'pending_inbox_count': pending_inbox_count,
        'regions_high_occupancy_count': regions_high_occupancy_count,
        'regions_with_failed_latest': regions_with_failed_latest,
        'priority_students_pending': priority_students_pending,
        'stage_upload': stage_upload,
        'stage_review': stage_review,
        'stage_processing': stage_processing,
        'stage_allocation': stage_allocation,
        'stage_results': stage_results,
        'recent_batches': recent_batches,
        'recent_runs': recent_runs,
        'recent_requests': recent_requests,
        'recent_activity_order': [
            f'{source_type}-{source_id}'
            for source_type, source_id, _ in recent_activity_sources
        ],
    }


def build_allocation_summary_read_model(region):
    """
    The AllocationPage summary for one region: allocatable population
    counts, housing-type / category breakdowns, inventory by apartment
    type, the pre-run population summary, and the latest inbox item and
    run (model instances, serialized by the view).
    """
    all_students_qs = Student.objects.filter(
        accepted_dorm_type__region=region
    )

    # Pre-run preview of the population summary shown on AllocationPage
    # between upload and clicking "run allocation" — scoped strictly to
    # this region, never a global Student count. sent_to_solver here is
    # an estimate of what a default run would submit right now (eligible
    # and not yet assigned); once a real run exists, its persisted
    # diagnostics.population_summary (exposed via get_allocation_run_detail)
    # is the authoritative figure for that specific run.
    population_summary = _population_summary_for_region(region)

    # Keep the summary's actionable counts aligned with run_allocation:
    # students who are leaving, or who are accessibility/disability cases
    # handled manually by the dorm office, are reported in the breakdown
    # but are never offered to the solver.
    allocatable_students_qs = all_students_qs.exclude(
        category=Student.StudentCategory.LEAVING
    ).exclude(accessibility_flag=True)

    total_students = allocatable_students_qs.count()

    active_assigned_student_ids = BedAssignment.objects.filter(
        status=BedAssignment.Status.ACTIVE,
        student__accepted_dorm_type__region=region,
        bed__room__is_active=True,
        bed__room__apartment__is_active=True,
        bed__room__apartment__building__is_active=True,
    ).values_list(
        'student_id',
        flat=True,
    ).distinct()

    assigned_students = allocatable_students_qs.filter(
        id__in=active_assigned_student_ids
    ).count()

    students_for_allocation_qs = allocatable_students_qs.exclude(
        id__in=active_assigned_student_ids
    )

    unassigned_students = students_for_allocation_qs.count()
    priority_students = allocatable_students_qs.filter(
        is_priority=True
    ).count()

    known_housing_types = [
        Student.HousingType.SINGLE_MALE,
        Student.HousingType.SINGLE_FEMALE,
        Student.HousingType.SINGLE_IN_APARTMENT,
        Student.HousingType.COUPLE,
        Student.HousingType.FAMILY,
    ]

    students_by_housing_type = {
        'single_male': students_for_allocation_qs.filter(
            housing_type=Student.HousingType.SINGLE_MALE
        ).count(),
        'single_female': students_for_allocation_qs.filter(
            housing_type=Student.HousingType.SINGLE_FEMALE
        ).count(),
        'single_mixed': students_for_allocation_qs.filter(
            housing_type=Student.HousingType.SINGLE_IN_APARTMENT
        ).count(),
        'couple': students_for_allocation_qs.filter(
            housing_type=Student.HousingType.COUPLE
        ).count(),
        'family': students_for_allocation_qs.filter(
            housing_type=Student.HousingType.FAMILY
        ).count(),
        'unknown': students_for_allocation_qs.filter(
            Q(housing_type__isnull=True)
            | Q(housing_type='')
            | ~Q(housing_type__in=known_housing_types)
        ).count(),
    }

    students_by_category = {
        'new': all_students_qs.filter(
            category=Student.StudentCategory.NEW
        ).count(),
        'continuing': all_students_qs.filter(
            category=Student.StudentCategory.CONTINUING
        ).count(),
        'transfer': all_students_qs.filter(
            category=Student.StudentCategory.TRANSFER
        ).count(),
        'leaving': all_students_qs.filter(
            category=Student.StudentCategory.LEAVING
        ).count(),
    }

    apartments_qs = Apartment.objects.filter(
        building__dorm_type__region=region,
        is_active=True,
        building__is_active=True,
    )

    rooms_qs = Room.objects.filter(
        apartment__building__dorm_type__region=region,
        is_active=True,
        apartment__is_active=True,
        apartment__building__is_active=True,
    )

    total_capacity = sum(rooms_qs.values_list('capacity', flat=True))

    active_beds_qs = Bed.objects.filter(
        room__apartment__building__dorm_type__region=region,
        room__is_active=True,
        room__apartment__is_active=True,
        room__apartment__building__is_active=True,
    )

    active_assignments_qs = BedAssignment.objects.filter(
        status=BedAssignment.Status.ACTIVE,
        bed__room__apartment__building__dorm_type__region=region,
        bed__room__is_active=True,
        bed__room__apartment__is_active=True,
        bed__room__apartment__building__is_active=True,
    )

    total_beds = active_beds_qs.count()
    occupied_beds = active_assignments_qs.values(
        'bed_id'
    ).distinct().count()

    def inventory_bucket(apartment_type):
        type_apartments = apartments_qs.filter(
            apartment_type=apartment_type
        )
        type_rooms = rooms_qs.filter(
            apartment__apartment_type=apartment_type
        )
        type_beds = active_beds_qs.filter(
            room__apartment__apartment_type=apartment_type
        )
        type_assignments = active_assignments_qs.filter(
            bed__room__apartment__apartment_type=apartment_type
        )

        type_total_beds = type_beds.count()
        type_occupied_beds = type_assignments.values(
            'bed_id'
        ).distinct().count()

        return {
            'apartments': type_apartments.count(),
            'rooms': type_rooms.count(),
            'total_beds': type_total_beds,
            'occupied_beds': type_occupied_beds,
            'available_beds': max(
                type_total_beds - type_occupied_beds,
                0,
            ),
        }

    inventory_by_type = {
        'single': inventory_bucket(
            Apartment.ApartmentType.SINGLE
        ),
        'couple': inventory_bucket(
            Apartment.ApartmentType.COUPLE
        ),
        'family': inventory_bucket(
            Apartment.ApartmentType.FAMILY
        ),
    }

    if total_beds > 0:
        available_beds = max(total_beds - occupied_beds, 0)
        denominator = total_beds
    else:
        available_beds = max(total_capacity - occupied_beds, 0)
        denominator = total_capacity

    occupancy_rate = 0
    if denominator > 0:
        occupancy_rate = round((occupied_beds / denominator) * 100, 2)

    latest_inbox = RegionInbox.objects.filter(
        region=region,
        status__in=[RegionInbox.Status.PENDING, RegionInbox.Status.VIEWED]
    ).select_related('batch').order_by('-created_at').first()

    latest_run = AllocationRun.objects.filter(
        region=region
    ).select_related('run_by').order_by('-started_at').first()

    return {
        'total_students': total_students,
        'unassigned_students': unassigned_students,
        'assigned_students': assigned_students,
        'available_beds': available_beds,
        'priority_students': priority_students,
        'total_capacity': total_capacity,
        'occupancy_rate': occupancy_rate,
        'students_by_category': students_by_category,
        'students_by_housing_type': students_by_housing_type,
        'inventory_by_type': inventory_by_type,
        'population_summary': population_summary,
        'latest_inbox': latest_inbox,
        'latest_run': latest_run,
    }
