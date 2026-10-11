"""
Excel import workflows: the status-report ("דוח שיבוץ") import and the
additions ("מתווספים") import.

Each workflow takes an already-claimed PROCESSING ImportBatch and an
opened workbook, walks every sheet row by row (persisting progress and
honouring stop / stop-and-delete requests between rows), notifies the
affected regions' inboxes, records the result on the batch and returns
the result payload. On an unexpected failure the batch is marked FAILED
and the exception propagates to the caller.
"""

import traceback

import pandas as pd
from django.utils import timezone

from ...db_connection import refresh_db_connection
from ...models import ImportBatch, RegionInbox, Student
from .batches import IMPORT_BATCH_STOP_STATUSES, delete_students_created_by_batch
from .parsing import (
    additions_housing_bucket,
    build_student_payload_from_row,
    classify_allocation_group_bucket,
    gender_value_is_valid_for_import,
    get_additions_decision_dorm_code,
    get_additions_decision_status,
    get_alias_value,
    get_decision_dorm_name,
    get_or_create_dorm_type_from_excel,
    is_additions_positive_decision,
    is_blank,
    normalize_additions_housing_type,
    parse_category,
    parse_gender_from_housing_type,
    safe_str,
)

REQUIRED_COLUMNS = ['ת"ז ישראלית', 'שם פרטי', 'שם משפחה']

# Housing types whose rows must never be skipped for a missing gender: the
# Student.gender column has to accept NULL/blank for them.
_GENDERLESS_HOUSING_TYPES = {
    Student.HousingType.COUPLE,
    Student.HousingType.FAMILY,
    Student.HousingType.SINGLE_IN_APARTMENT,
}

# If a student appears in more than one status-report sheet, the stronger
# category wins.
_CATEGORY_PRIORITY = {
    Student.StudentCategory.CONTINUING: 1,
    Student.StudentCategory.NEW: 2,
    Student.StudentCategory.TRANSFER: 3,
    Student.StudentCategory.LEAVING: 4,
}


class _ImportRun:
    """Per-upload bookkeeping shared by both import kinds."""

    def __init__(self, batch):
        self.batch = batch

        self.created_count = 0
        self.updated_count = 0
        self.skipped_count = 0

        self.errors = []
        self.warnings = []
        self.region_counts = {}
        self.sheet_counts = {}
        self.skipped_by_reason = {}

        self.processed_rows = 0
        self.total_rows = 0
        self.stop_requested = False
        self.requested_stop_status = None

        self._dorm_inventory_cache = {}

    def dorm_has_active_inventory(self, dorm_type):
        if dorm_type is None:
            return False
        if dorm_type.pk not in self._dorm_inventory_cache:
            self._dorm_inventory_cache[dorm_type.pk] = dorm_type.buildings.filter(
                is_active=True
            ).exists()
        return self._dorm_inventory_cache[dorm_type.pk]

    def add_skip(self, reason, amount=1):
        self.skipped_count += amount
        self.skipped_by_reason[reason] = self.skipped_by_reason.get(reason, 0) + amount

    def add_region_count(self, region, created=False, updated=False):
        if not region:
            return

        if region.id not in self.region_counts:
            self.region_counts[region.id] = {
                'region': region,
                'count': 0,
                'created': 0,
                'updated': 0,
            }

        self.region_counts[region.id]['count'] += 1

        if created:
            self.region_counts[region.id]['created'] += 1

        if updated:
            self.region_counts[region.id]['updated'] += 1

    def read_sheet(self, excel_file, sheet_name):
        """Read one sheet, normalize its headers and record its row count."""
        df = pd.read_excel(excel_file, sheet_name=sheet_name)
        df.columns = [safe_str(col) for col in df.columns]

        self.total_rows += len(df)
        ImportBatch.objects.filter(pk=self.batch.id).update(total_rows=self.total_rows)
        return df

    def skip_sheet_missing_columns(self, sheet_name, df):
        """Skip a whole sheet lacking a required column; True when skipped."""
        missing_required = [col for col in REQUIRED_COLUMNS if col not in df.columns]
        if not missing_required:
            return False

        self.add_skip('missing_required_columns', len(df))
        self.sheet_counts[sheet_name]['skipped'] += len(df)
        self.errors.append(
            f"Sheet '{sheet_name}' missing required columns: {', '.join(missing_required)}"
        )
        return True

    def skip_row(self, sheet_name, reason, message):
        self.add_skip(reason)
        self.sheet_counts[sheet_name]['skipped'] += 1
        if message is not None:
            self.errors.append(message)

    def row_done(self):
        """
        The single choke point where a row's outcome is guaranteed decided:
        persists progress, then reports True when a stop was requested so
        the caller exits the row loop cleanly.
        """
        self.processed_rows += 1
        ImportBatch.objects.filter(pk=self.batch.id).update(processed_rows=self.processed_rows)

        live_status = ImportBatch.objects.filter(pk=self.batch.id).values_list(
            'status', flat=True
        ).first()
        if live_status in IMPORT_BATCH_STOP_STATUSES:
            self.stop_requested = True
            self.requested_stop_status = live_status
            return True
        return False

    def existing_student(self, student_id):
        return Student.objects.filter(student_id=student_id).select_related(
            'accepted_dorm_type',
            'accepted_dorm_type__region'
        ).first()

    def create_student(self, student_payload):
        Student.objects.create(
            batch=self.batch,
            created_in_batch=self.batch,
            **student_payload
        )

    def notify_regions(self, message_for_count):
        """
        Supersede each affected region's still-open inbox items and post a
        fresh PENDING item for this batch; returns the region breakdown.
        """
        refresh_db_connection()

        for region_id in self.region_counts.keys():
            RegionInbox.objects.filter(
                region_id=region_id,
                status__in=[
                    RegionInbox.Status.PENDING,
                    RegionInbox.Status.VIEWED,
                ]
            ).update(status=RegionInbox.Status.SUPERSEDED)

        region_breakdown = []

        for region_id, data in self.region_counts.items():
            refresh_db_connection()

            RegionInbox.objects.create(
                region_id=region_id,
                batch_id=self.batch.id,
                students_count=data['count'],
                status=RegionInbox.Status.PENDING,
                message=message_for_count(data['count']),
            )

            region_breakdown.append({
                'region_id': region_id,
                'region_name': data['region'].name,
                'count': data['count'],
                'created': data['created'],
                'updated': data['updated'],
            })

        return region_breakdown

    def finalize(self, result_payload, total_imported):
        """Record the terminal outcome (STOPPED or COMPLETED) on the batch."""
        refresh_db_connection()

        if self.stop_requested:
            if self.requested_stop_status == ImportBatch.Status.STOP_AND_DELETE_REQUESTED:
                result_payload['deletion'] = delete_students_created_by_batch(self.batch)

            ImportBatch.objects.filter(pk=self.batch.id).update(
                total_students=total_imported,
                status=ImportBatch.Status.STOPPED,
                finished_at=timezone.now(),
                error_message='',
                result=result_payload,
            )
        else:
            ImportBatch.objects.filter(pk=self.batch.id).update(
                total_students=total_imported,
                status=ImportBatch.Status.COMPLETED,
                finished_at=timezone.now(),
                error_message='',
                result=result_payload,
            )

    def mark_failed(self, exc):
        try:
            refresh_db_connection()
            ImportBatch.objects.filter(pk=self.batch.id).update(
                status=ImportBatch.Status.FAILED,
                error_message=str(exc)[:2000],
                finished_at=timezone.now(),
            )
        except Exception:
            traceback.print_exc()


def _update_existing_student(existing, student_payload, batch, *, protected_fields):
    """
    Update an existing student carefully: never clear existing values when
    the Excel cell is blank, never replace accepted_dorm_type with None,
    and never touch ``protected_fields``.
    """
    for key, value in student_payload.items():
        if key in protected_fields:
            continue

        if key == 'accepted_dorm_type':
            if value is not None:
                setattr(existing, key, value)
            continue

        # Preserve existing data if the Excel value is empty.
        if is_blank(value):
            continue

        setattr(existing, key, value)

    existing.batch = batch
    existing.save()


def _stopped_messages(stop_requested, done_he, done_en):
    return (
        'עיבוד הקובץ נעצר לבקשת המשתמש' if stop_requested else done_he,
        'File processing was stopped by request' if stop_requested else done_en,
    )


# ---------------------------------------------------------------------------
# Status report import ("דוח שיבוץ": נשארים / מעברים / נכנסים חדשים / עוזבים)
# ---------------------------------------------------------------------------

def run_status_report_import(batch, excel_file):
    """
    Import the status report workbook into ``batch`` (already PROCESSING).

    - No students are deleted.
    - Leaving students are imported with category=LEAVING.
    - Students are not skipped because of non-positive decision status.
    - Students are not skipped because accepted_dorm_type could not be resolved.
    - Existing students are updated carefully without clearing existing
      values when the Excel cell is empty; category and batch always update.

    Returns the result payload (also persisted on the batch). On failure the
    batch is marked FAILED and the exception propagates.
    """
    run = _ImportRun(batch)

    try:
        category_counts = {
            'new': 0,
            'continuing': 0,
            'transfer': 0,
            'leaving': 0,
        }

        # Import-summary buckets derived from the allocation-group column,
        # for logging only — never persisted on the Student model.
        allocation_group_bucket_counts = {
            'staying': 0,
            'new': 0,
            'accessibility': 0,
            'other': 0,
        }

        imported_student_category_priority = {}

        def import_row(sheet_name, idx, row):
            student_id = safe_str(get_alias_value(row, 'student_id'))

            if not student_id:
                run.skip_row(
                    sheet_name, 'missing_student_id',
                    f"Sheet '{sheet_name}', row {idx + 2}: missing student_id",
                )
                return

            existing = run.existing_student(student_id)

            student_payload = build_student_payload_from_row(
                row,
                existing_student=existing,
                sheet_name=sheet_name,
            )

            normalized_housing_type = student_payload.get('housing_type')
            if not existing and not gender_value_is_valid_for_import(
                student_payload.get('gender'),
                normalized_housing_type,
            ):
                if normalized_housing_type in _GENDERLESS_HOUSING_TYPES:
                    raise ValueError(
                        'Student.gender must allow NULL/blank for Z3/Z4/Z6. '
                        'Apply the nullable-gender migration before importing.'
                    )

                run.skip_row(
                    sheet_name, 'missing_gender_for_unknown_housing_type',
                    f"Sheet '{sheet_name}', row {idx + 2}, student {student_id}: "
                    "gender and housing type could not be resolved.",
                )
                return

            student_category = student_payload.get('category') or parse_category('', sheet_name=sheet_name)
            student_payload['category'] = student_category

            # Handle duplicate students inside the same uploaded Excel.
            new_priority = _CATEGORY_PRIORITY.get(student_category, 0)
            old_priority = imported_student_category_priority.get(student_id)

            if old_priority is not None and new_priority < old_priority:
                # Do not allow a weaker sheet to overwrite a stronger category.
                if existing:
                    student_payload['category'] = existing.category

                run.warnings.append(
                    f"Student {student_id} appeared again in sheet '{sheet_name}' "
                    f"with weaker category '{student_category}'. Category was not overwritten."
                )
            else:
                imported_student_category_priority[student_id] = new_priority

            accepted_dorm_type = student_payload.get('accepted_dorm_type')
            target_region = accepted_dorm_type.region if accepted_dorm_type else None

            # In this status-report import, we do NOT skip students if dorm type is missing.
            # This is especially important for leaving students.
            if accepted_dorm_type is None:
                run.warnings.append(
                    f"Student {student_id}: accepted_dorm_type could not be resolved. "
                    f"Student was imported anyway."
                )

            if accepted_dorm_type is not None and target_region is None:
                run.warnings.append(
                    f"Student {student_id}: dorm type '{accepted_dorm_type.name}' has no region. "
                    f"Student was imported anyway."
                )

            if accepted_dorm_type is not None and not run.dorm_has_active_inventory(accepted_dorm_type):
                run.warnings.append(
                    f"Student {student_id}: official dorm code {accepted_dorm_type.code} "
                    "currently has no active building inventory. The decision was preserved, "
                    "but allocation may have no feasible room for this student."
                )

            if existing:
                # Always update category and batch; everything else only
                # when the Excel cell carries a value.
                _update_existing_student(
                    existing, student_payload, batch, protected_fields={'student_id'},
                )

                run.updated_count += 1
                run.sheet_counts[sheet_name]['updated'] += 1

                if target_region:
                    run.add_region_count(target_region, updated=True)

            else:
                run.create_student(student_payload)

                run.created_count += 1
                run.sheet_counts[sheet_name]['created'] += 1

                if target_region:
                    run.add_region_count(target_region, created=True)

            final_category = student_payload.get('category')

            if final_category in category_counts:
                category_counts[final_category] += 1

            if final_category in run.sheet_counts[sheet_name]['categories']:
                run.sheet_counts[sheet_name]['categories'][final_category] += 1

            allocation_group_bucket = classify_allocation_group_bucket(
                student_payload.get('allocation_group', '')
            )
            allocation_group_bucket_counts[allocation_group_bucket] += 1

        for sheet_name in excel_file.sheet_names:
            df = run.read_sheet(excel_file, sheet_name)

            run.sheet_counts[sheet_name] = {
                'rows': len(df),
                'created': 0,
                'updated': 0,
                'skipped': 0,
                'categories': {
                    'new': 0,
                    'continuing': 0,
                    'transfer': 0,
                    'leaving': 0,
                }
            }

            if run.skip_sheet_missing_columns(sheet_name, df):
                continue

            for idx, row in df.iterrows():
                try:
                    import_row(sheet_name, idx, row)
                except Exception as e:
                    run.skip_row(
                        sheet_name, 'row_exception',
                        f"Sheet '{sheet_name}', row {idx + 2}: "
                        f"{e.__class__.__name__}: {str(e)}",
                    )
                finally:
                    # A `break` here overrides any pending return/exception
                    # path from the try/except above (standard finally
                    # semantics) and exits the row loop cleanly.
                    if run.row_done():
                        break

            if run.stop_requested:
                break

        region_breakdown = run.notify_regions(
            lambda count: (
                f'התקבל דוח שיבוץ עם {count} סטודנטים באזור זה. '
                f'הדוח כולל נשארים, מעברים, נכנסים חדשים ועוזבים.'
            )
        )

        total_imported = run.created_count + run.updated_count

        # Sent to the solver = everyone except LEAVING and accessibility
        # students, mirroring the exclusion in run_allocation/
        # _execute_allocation_background.
        final_students_for_solver = (
            total_imported
            - category_counts['leaving']
            - allocation_group_bucket_counts['accessibility']
        )
        print(
            ">>> upload_excel allocation-group summary: "
            f"total={total_imported}, "
            f"staying={allocation_group_bucket_counts['staying']}, "
            f"new={allocation_group_bucket_counts['new']}, "
            f"accessibility_excluded={allocation_group_bucket_counts['accessibility']}, "
            f"other={allocation_group_bucket_counts['other']}, "
            f"final_sent_to_solver={final_students_for_solver}",
            flush=True,
        )

        message, message_en = _stopped_messages(
            run.stop_requested,
            'דוח השיבוץ הועלה ועובד בהצלחה',
            'Status report uploaded and processed successfully',
        )

        result_payload = {
            'success': True,
            'stopped': run.stop_requested,
            'message': message,
            'messageEn': message_en,
            'batch_id': batch.id,
            'total_students': total_imported,
            'created': run.created_count,
            'updated': run.updated_count,
            'skipped': run.skipped_count,
            'category_counts': category_counts,
            'region_breakdown': region_breakdown,
            'sheet_counts': run.sheet_counts,
            'skipped_by_reason': run.skipped_by_reason,
            'warnings': run.warnings[:100],
            'errors': run.errors[:100],
        }

        run.finalize(result_payload, total_imported)
        return result_payload

    except Exception as exc:
        traceback.print_exc()
        run.mark_failed(exc)
        raise


# ---------------------------------------------------------------------------
# Additions import ("מתווספים")
# ---------------------------------------------------------------------------

_ADDITIONS_PROTECTED_FIELDS = {
    'student_id',
    'category',
    'assigned_room',
    'current_address',
    'current_dorm_type',
    'move_in_date',
    'move_out_date',
}


def _empty_housing_type_counts():
    return {
        'single_male': 0,
        'single_female': 0,
        'single_mixed': 0,
        'couple': 0,
        'family': 0,
        'unknown': 0,
    }


def run_additions_import(batch, excel_file):
    """
    Import the additions workbook into ``batch`` (already PROCESSING).

    - Import only positive decisions.
    - Import all supported Z1/Z2/Z3/Z4/Z6 housing types.
    - Route each student by the authoritative numeric DormType.code.
    - An existing student gets enrichment fields only: category,
      assigned_room and BedAssignment are never touched.
    - A new student is created as category=NEW.

    Returns the result payload (also persisted on the batch). On failure the
    batch is marked FAILED and the exception propagates.
    """
    run = _ImportRun(batch)

    try:
        existing_category_preserved_count = 0
        housing_type_counts = _empty_housing_type_counts()

        def import_row(sheet_name, idx, row):
            nonlocal existing_category_preserved_count

            student_id = safe_str(get_alias_value(row, 'student_id'))

            if not student_id:
                run.skip_row(
                    sheet_name, 'missing_student_id',
                    f"Sheet '{sheet_name}', row {idx + 2}: missing student_id",
                )
                return

            decision_status = get_additions_decision_status(row)

            if not is_additions_positive_decision(row):
                run.skip_row(sheet_name, 'non_positive_decision', None)
                run.sheet_counts[sheet_name]['non_positive_decisions'] += 1
                return

            run.sheet_counts[sheet_name]['positive_decisions'] += 1

            existing = run.existing_student(student_id)

            student_payload = build_student_payload_from_row(
                row,
                existing_student=existing,
                sheet_name=sheet_name,
            )

            # Normalize the additions file's official Z1/Z2/Z3/Z4/Z6 housing
            # values using the same canonical model choices.
            normalized_housing_type = normalize_additions_housing_type(row)
            housing_bucket = additions_housing_bucket(normalized_housing_type)

            student_payload['housing_type'] = normalized_housing_type
            resolved_gender = parse_gender_from_housing_type(
                normalized_housing_type,
                tenant_type=get_alias_value(row, 'tenant_type', default=''),
                explicit_gender=get_alias_value(row, 'gender', default=''),
                existing_student=existing,
            )
            student_payload['gender'] = resolved_gender

            if not existing and not gender_value_is_valid_for_import(
                resolved_gender,
                normalized_housing_type,
            ):
                if normalized_housing_type in _GENDERLESS_HOUSING_TYPES:
                    raise ValueError(
                        'Student.gender must allow NULL/blank for Z3/Z4/Z6. '
                        'Apply the nullable-gender migration before importing.'
                    )

                run.skip_row(
                    sheet_name, 'missing_gender_for_unknown_housing_type',
                    f"Sheet '{sheet_name}', row {idx + 2}, student {student_id}: "
                    "gender and housing type could not be resolved.",
                )
                return

            if housing_bucket == 'unknown':
                run.warnings.append(
                    f"Sheet '{sheet_name}', row {idx + 2}, student {student_id}: "
                    f"unknown housing type. description='"
                    f"{safe_str(get_alias_value(row, 'housing_type', default=''))}', "
                    f"tenant_code='"
                    f"{safe_str(get_alias_value(row, 'tenant_type', default=''))}'"
                )

            # The additions file does not define continuing/transfer/leaving:
            # new students become NEW, existing students keep their category.
            if existing:
                student_payload['category'] = existing.category
            else:
                student_payload['category'] = Student.StudentCategory.NEW

            # Resolve dorm type using the correct additions dorm code.
            additions_dorm_code = get_additions_decision_dorm_code(row)
            additions_dorm_name = get_decision_dorm_name(row)

            accepted_dorm_type = get_or_create_dorm_type_from_excel(
                dorm_code=additions_dorm_code,
                dorm_name=additions_dorm_name
            )

            if accepted_dorm_type is not None:
                student_payload['accepted_dorm_type'] = accepted_dorm_type
            else:
                # The numeric decision code is authoritative. Never replace
                # it with the descriptive/name column (for example קנדה).
                student_payload.pop('accepted_dorm_type', None)

                if existing:
                    run.warnings.append(
                        f"Student {student_id}: official dorm decision code "
                        f"'{additions_dorm_code}' could not be resolved. "
                        "The existing accepted_dorm_type was preserved and "
                        "no name fallback was used."
                    )

            target_region = accepted_dorm_type.region if accepted_dorm_type else None

            # For a new student, we need accepted_dorm_type to know where to route them.
            if not existing and accepted_dorm_type is None:
                run.skip_row(
                    sheet_name, 'could_not_resolve_dorm_type',
                    f"Student {student_id}: positive decision but could not resolve dorm type. "
                    f"decision_status='{decision_status}', "
                    f"additions_dorm_code='{additions_dorm_code}', "
                    f"additions_dorm_name='{additions_dorm_name}'",
                )
                return

            if accepted_dorm_type is not None and target_region is None:
                run.skip_row(
                    sheet_name, 'dorm_type_without_region',
                    f"Student {student_id}: dorm type '{accepted_dorm_type.name}' has no region",
                )
                return

            if accepted_dorm_type is not None and not run.dorm_has_active_inventory(accepted_dorm_type):
                run.warnings.append(
                    f"Student {student_id}: official dorm code {accepted_dorm_type.code} "
                    "currently has no active building inventory. The decision was preserved, "
                    "but allocation may have no feasible room for this student."
                )

            if existing:
                old_category = existing.category

                _update_existing_student(
                    existing, student_payload, batch,
                    protected_fields=_ADDITIONS_PROTECTED_FIELDS,
                )

                # Extra safety: category must not change for existing students.
                if existing.category != old_category:
                    existing.category = old_category
                    existing.save(update_fields=['category'])

                run.updated_count += 1
                run.sheet_counts[sheet_name]['updated'] += 1
                run.sheet_counts[sheet_name]['existing_category_preserved'] += 1
                existing_category_preserved_count += 1

                if target_region:
                    run.add_region_count(target_region, updated=True)

            else:
                run.create_student(student_payload)

                run.created_count += 1
                run.sheet_counts[sheet_name]['created'] += 1

                if target_region:
                    run.add_region_count(target_region, created=True)

            # Count only rows that were actually persisted. This keeps
            # the upload report aligned with the database.
            housing_type_counts[housing_bucket] += 1
            run.sheet_counts[sheet_name]['housing_type_counts'][housing_bucket] += 1

        for sheet_name in excel_file.sheet_names:
            df = run.read_sheet(excel_file, sheet_name)

            run.sheet_counts[sheet_name] = {
                'rows': len(df),
                'created': 0,
                'updated': 0,
                'skipped': 0,
                'positive_decisions': 0,
                'non_positive_decisions': 0,
                'existing_category_preserved': 0,
                'housing_type_counts': _empty_housing_type_counts(),
            }

            if run.skip_sheet_missing_columns(sheet_name, df):
                continue

            for idx, row in df.iterrows():
                try:
                    import_row(sheet_name, idx, row)
                except Exception as e:
                    run.skip_row(
                        sheet_name, 'row_exception',
                        f"Sheet '{sheet_name}', row {idx + 2}: "
                        f"{e.__class__.__name__}: {str(e)}",
                    )
                finally:
                    # See run_status_report_import for why `finally` is the
                    # single correct choke point here.
                    if run.row_done():
                        break

            if run.stop_requested:
                break

        region_breakdown = run.notify_regions(
            lambda count: (
                f'התקבל קובץ מתווספים עם {count} סטודנטים באזור זה. '
                f'הקובץ מוסיף סטודנטים עם החלטה חיובית ומשלים מידע לסטודנטים קיימים.'
            )
        )

        total_imported = run.created_count + run.updated_count

        message, message_en = _stopped_messages(
            run.stop_requested,
            'קובץ המתווספים הועלה ועובד בהצלחה',
            'Additions file uploaded and processed successfully',
        )

        result_payload = {
            'success': True,
            'stopped': run.stop_requested,
            'message': message,
            'messageEn': message_en,
            'batch_id': batch.id,
            'total_students': total_imported,
            'created': run.created_count,
            'updated': run.updated_count,
            'skipped': run.skipped_count,
            'existing_category_preserved': existing_category_preserved_count,
            'housing_type_counts': housing_type_counts,
            'region_breakdown': region_breakdown,
            'sheet_counts': run.sheet_counts,
            'skipped_by_reason': run.skipped_by_reason,
            'warnings': run.warnings[:100],
            'errors': run.errors[:100],
        }

        run.finalize(result_payload, total_imported)
        return result_payload

    except Exception as exc:
        traceback.print_exc()
        run.mark_failed(exc)
        raise
