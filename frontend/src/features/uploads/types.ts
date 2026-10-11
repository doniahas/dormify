// Excel import batches (backend/api/views/imports.py and the ingestion
// read models under backend/api/domains/imports). The ImportBatch record
// itself is shared (shared/api/contracts/operations.ts) because the home
// dashboard and the analysis page receive it too.
import type {
  ImportBatch,
  ImportBatchDeletion,
  ImportBatchKind,
  ImportBatchRegionBreakdown,
  ImportBatchResult,
  ImportBatchStatus,
  Region,
} from '../../shared/api/contracts';

export type {
  ImportBatch,
  ImportBatchDeletion,
  ImportBatchKind,
  ImportBatchRegionBreakdown,
  ImportBatchResult,
  ImportBatchStatus,
};

/** POST /api/upload/batches/init/ (201). */
export interface InitBatchResponse {
  batch_id: number;
  status: ImportBatchStatus | string;
  error?: string;
  errorEn?: string;
}

/**
 * stop / stop-and-delete / delete answer with the updated batch itself
 * (ImportBatchSerializer), not a bare status; the error keys belong to the
 * 409 bodies, which also carry the batch's current `status`.
 */
export type BatchActionResponse = ImportBatch & {
  error?: string;
  errorEn?: string;
};

/** One row of the upload reply's region_breakdown (per region the file touched). */
export type UploadRegionBreakdownRow = {
  region_id: Region['id'];
  region_name: string;
  count: number;
  created: number;
  updated: number;
};

/** Per-sheet counters of an upload (sheet_counts[<sheet name>]). */
export type UploadSheetCounts = {
  rows: number;
  created: number;
  updated: number;
  skipped: number;
  /** Main upload. */
  categories?: Record<string, number>;
  /** Additions upload. */
  positive_decisions?: number;
  non_positive_decisions?: number;
  existing_category_preserved?: number;
  housing_type_counts?: Record<string, number>;
  [key: string]: unknown;
};

/** POST /api/upload/excel/ (main file) and /api/upload/additions-excel/ (200). */
export interface UploadResponse {
  success?: boolean;
  /** True when the import was stopped by the operator before finishing. */
  stopped?: boolean;
  message?: string;
  messageEn?: string;
  batch_id?: number;
  total_students?: number;
  created?: number;
  updated?: number;
  skipped?: number;
  /** Main upload only: per student category. */
  category_counts?: Record<string, number>;
  /** Additions upload only. */
  existing_category_preserved?: number;
  housing_type_counts?: Record<string, number>;
  region_breakdown?: UploadRegionBreakdownRow[];
  sheet_counts?: Record<string, UploadSheetCounts>;
  skipped_by_reason?: Record<string, number>;
  /** Capped at 100 entries each. */
  warnings?: string[];
  errors?: string[];
  /**
   * Not part of the upload reply: the page merges ImportBatch.result into
   * its upload state after a delete action, which adds this record.
   */
  deletion?: ImportBatchDeletion;
  /** Error bodies (400/403/409) use these instead. */
  status?: string;
  error?: string;
  errorEn?: string;
  [key: string]: unknown;
}
