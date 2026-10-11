// Operational records more than one feature reads: allocation runs, region
// inbox items and Excel import batches (backend/api/serializers/operations.py:
// AllocationRunSerializer, RegionInboxSerializer, ImportBatchSerializer).
// The allocation page, the uploads page, the home dashboard and the analysis
// page all receive these rows, so they live here rather than in one feature.
import type { IsoDateTime } from './common';
import type { Region } from './organization';

export type AllocationRunStatus =
  | 'queued'
  | 'running'
  | 'cancellation_requested'
  | 'stop_and_save_requested'
  | 'stopped'
  | 'completed'
  | 'failed'
  | 'deleted'
  | 'approved';

/** AllocationRunSerializer. */
export interface AllocationRun {
  id: number;
  region: Region['id'];
  region_name: string;
  run_by: number | null;
  run_by_name: string | null;
  status: AllocationRunStatus;
  status_display: string;
  students_processed: number;
  successful_assignments: number;
  roommate_matches: number;
  conflicts: number;
  max_search_seconds: number | null;
  search_started_at: IsoDateTime | null;
  elapsed_search_seconds: number;
  remaining_search_seconds: number | null;
  started_at: IsoDateTime;
  completed_at: IsoDateTime | null;
  error_message: string;
}

export type RegionInboxStatus = 'pending' | 'viewed' | 'processed' | 'superseded';

/** RegionInboxSerializer. */
export interface RegionInbox {
  id: number;
  region: Region['id'];
  region_name: string;
  batch: number | null;
  batch_filename: string | null;
  batch_created_at: IsoDateTime | null;
  students_count: number;
  status: RegionInboxStatus;
  status_display: string;
  message: string;
  created_at: IsoDateTime;
  viewed_at: IsoDateTime | null;
  processed_at: IsoDateTime | null;
}

export type ImportBatchKind = 'main' | 'additions';

export type ImportBatchStatus =
  | 'pending'
  | 'processing'
  | 'cancellation_requested'
  | 'stop_and_delete_requested'
  | 'stopped'
  | 'completed'
  | 'failed';

/** One row of ImportBatchSerializer.region_breakdown (one per RegionInbox). */
export interface ImportBatchRegionBreakdown {
  region_id: Region['id'];
  region_name: string;
  count: number;
  status: RegionInboxStatus;
}

/** The `deletion` record the delete / stop-and-delete actions store on ImportBatch.result. */
export interface ImportBatchDeletion {
  requested: boolean;
  deleted_count: number;
  protected_count: number;
  protected_students: Array<Record<string, unknown>>;
  performed_at: IsoDateTime | null;
}

/**
 * ImportBatch.result: the upload outcome as stored when the import finished
 * (the same keys as the upload reply, see features/uploads/types.ts), plus
 * `deletion` once a delete action ran. Null until the import produced one.
 */
export interface ImportBatchResult {
  deletion?: ImportBatchDeletion;
  [key: string]: unknown;
}

/** ImportBatchSerializer - also the body of GET /api/upload/batches/<id>/status/ and of the batch actions. */
export interface ImportBatch {
  id: number;
  uploaded_by: number | null;
  uploaded_by_name: string;
  kind: ImportBatchKind;
  filename: string;
  total_students: number;
  status: ImportBatchStatus;
  status_display: string;
  error_message: string;
  created_at: IsoDateTime;
  started_at: IsoDateTime | null;
  finished_at: IsoDateTime | null;
  total_rows: number;
  processed_rows: number;
  result: ImportBatchResult | null;
  region_breakdown: ImportBatchRegionBreakdown[];
}
