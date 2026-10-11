// Compile-time pins of the wire types: each assertion mirrors a backend
// contract test (backend/api/tests/contracts/) so a type that drifts from
// the serializer or the view builder fails `npm run typecheck` here.
import { describe, expectTypeOf, it } from 'vitest';
import type { AllocationRun, AuthenticatedUser, Building, ImportBatch, ImportBatchRegionBreakdown, RegionInbox, Student, StudentSummary } from './index';
import type { AllocationResults, AssistedQueue, MatchApartmentNode, MatchTree, RunDetail, RunPreview, SyncRunResult } from '../../../features/allocation/types';
import type { AnalysisData } from '../../../features/analytics/types';
import type { HomeDashboard } from '../../../features/dashboard/types';
import type { BulkCreateInventoryPayload } from '../../../features/inventory/types';
import type { BedMatchOptions } from '../../../features/students/types';
import type { BatchActionResponse, UploadResponse, UploadSheetCounts } from '../../../features/uploads/types';
import type { WhatIfConfirmation, WhatIfSimulation } from '../../../features/what-if/types';

describe('shared operations contracts', () => {
  it('pin the serializer field types', () => {
    expectTypeOf<AllocationRun['status']>().toEqualTypeOf<
      'queued' | 'running' | 'cancellation_requested' | 'stop_and_save_requested' | 'stopped' | 'completed' | 'failed' | 'deleted' | 'approved'
    >();
    expectTypeOf<AllocationRun['max_search_seconds']>().toEqualTypeOf<number | null>();
    expectTypeOf<RegionInbox['batch_filename']>().toEqualTypeOf<string | null>();
    expectTypeOf<ImportBatch['region_breakdown']>().toEqualTypeOf<ImportBatchRegionBreakdown[]>();
    expectTypeOf<ImportBatchRegionBreakdown>().toHaveProperty('status');
    expectTypeOf<ImportBatchRegionBreakdown>().toHaveProperty('region_id');
  });
});

describe('omitted-vs-null contracts (verified against captured backend bodies)', () => {
  it('Student detail omits the assigned_* fields while unassigned and has no list-only current_* columns', () => {
    expectTypeOf<Student['assigned_room_id']>().toEqualTypeOf<number | undefined>();
    expectTypeOf<Student['assigned_room_name']>().toEqualTypeOf<string | undefined>();
    expectTypeOf<Student['assigned_building_number']>().toEqualTypeOf<number | null | undefined>();
    expectTypeOf<Student['assigned_apartment_number']>().toEqualTypeOf<string | undefined>();
    expectTypeOf<Student>().not.toHaveProperty('current_building');
    expectTypeOf<StudentSummary['current_building']>().toEqualTypeOf<number | null>();
  });

  it('dorm-type-sourced fields are omitted for a student without an accepted dorm type', () => {
    expectTypeOf<StudentSummary['accepted_dorm_type_name']>().toEqualTypeOf<string | undefined>();
    expectTypeOf<StudentSummary['accepted_dorm_type_code']>().toEqualTypeOf<number | null | undefined>();
  });

  it('region_name is omitted for a user without a region; nullable model fields stay nullable', () => {
    expectTypeOf<AuthenticatedUser['region_name']>().toEqualTypeOf<string | undefined>();
    expectTypeOf<Building['number']>().toEqualTypeOf<number | null>();
    expectTypeOf<Building['dorm_type_code']>().toEqualTypeOf<number | null>();
  });
});

describe('feature contracts', () => {
  it('batch actions answer with the batch itself', () => {
    expectTypeOf<BatchActionResponse['id']>().toEqualTypeOf<number>();
    expectTypeOf<BatchActionResponse['region_breakdown']>().toEqualTypeOf<ImportBatchRegionBreakdown[]>();
    expectTypeOf<NonNullable<UploadResponse['region_breakdown']>[number]>().toHaveProperty('created');
    expectTypeOf<UploadResponse['stopped']>().toEqualTypeOf<boolean | undefined>();
  });

  it('what-if replies carry a scenario name and numeric counters', () => {
    expectTypeOf<WhatIfSimulation['scenario']>().toEqualTypeOf<'building_inactivation' | 'room_availability_change' | undefined>();
    expectTypeOf<WhatIfConfirmation['created_requests']>().toEqualTypeOf<number | undefined>();
    expectTypeOf<WhatIfConfirmation['inactivated_buildings']>().toEqualTypeOf<boolean | undefined>();
    expectTypeOf<WhatIfConfirmation['action']>().toEqualTypeOf<'inactivate' | 'reactivate' | undefined>();
  });

  it('dashboard scope is a string literal and the sections are typed', () => {
    expectTypeOf<HomeDashboard['scope']>().toEqualTypeOf<'system' | 'region' | undefined>();
    expectTypeOf<NonNullable<HomeDashboard['workflow']>[number]['key']>().toEqualTypeOf<
      'upload' | 'data_review' | 'regional_processing' | 'allocation' | 'results_review'
    >();
    expectTypeOf<NonNullable<HomeDashboard['process']>['latest_run']>().toEqualTypeOf<AllocationRun | null>();
  });

  it('allocation reads keep their row shapes', () => {
    expectTypeOf<NonNullable<AllocationResults['counts']>>().toEqualTypeOf<{ assigned: number; unassigned: number; available_beds: number }>();
    expectTypeOf<NonNullable<AllocationResults['unassigned_analysis']>[number]['inventory_breakdown'][number]>().toHaveProperty('free_beds');
    expectTypeOf<RunDetail['conflicts']>().toEqualTypeOf<number | undefined>();
    expectTypeOf<NonNullable<RunPreview['snapshot']>['sequence']>().toEqualTypeOf<number>();
    expectTypeOf<AssistedQueue['students'][number]['disability_percent']>().toEqualTypeOf<string | null>();
  });

  it('ranking reasons are {code, label} objects and assisted trees are unpaged', () => {
    expectTypeOf<MatchApartmentNode['matched_reasons'][number]>().toEqualTypeOf<{ code: string; label: string }>();
    expectTypeOf<MatchTree['limit']>().toEqualTypeOf<number | null | undefined>();
    expectTypeOf<SyncRunResult['students_with_no_feasible_beds']>().toEqualTypeOf<number[]>();
  });

  it('upload sheet counts are per-sheet records', () => {
    expectTypeOf<NonNullable<UploadResponse['sheet_counts']>[string]>().toEqualTypeOf<UploadSheetCounts>();
    expectTypeOf<UploadSheetCounts['rows']>().toEqualTypeOf<number>();
  });

  it('the match tree pages buildings and the bulk payload uses apartment_groups', () => {
    expectTypeOf<BedMatchOptions['next_offset']>().toEqualTypeOf<number | null | undefined>();
    expectTypeOf<NonNullable<BedMatchOptions['buildings']>[number]['apartments'][number]['rooms'][number]['beds'][number]['is_selectable']>().toEqualTypeOf<boolean>();
    expectTypeOf<BulkCreateInventoryPayload>().toHaveProperty('apartment_groups');
    expectTypeOf<NonNullable<AnalysisData['students_by_gender']>[number]>().toEqualTypeOf<{ gender: string | null } & { count: number }>();
  });
});
