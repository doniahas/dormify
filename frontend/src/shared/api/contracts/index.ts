// Typed API contracts shared across features. See README.md in this folder
// for what belongs here and what stays feature-owned.
export type {
  BilingualText,
  Id,
  IsoDate,
  IsoDateTime,
  ListResponse,
  MessageResponse,
  Paginated,
} from './common';
export type {
  ApiErrorBody,
  DetailErrorBody,
  ErrorBody,
  FailureBody,
  FieldErrors,
  FieldValidationErrors,
  LoginErrorBody,
  StructuredFieldError,
  ValidationMessages,
} from './errors';
export type {
  AllocationRun,
  AllocationRunStatus,
  ImportBatch,
  ImportBatchDeletion,
  ImportBatchKind,
  ImportBatchRegionBreakdown,
  ImportBatchResult,
  ImportBatchStatus,
  RegionInbox,
  RegionInboxStatus,
} from './operations';
export type { DormType, Region } from './organization';
export type {
  Apartment,
  ApartmentCategory,
  ApartmentType,
  Bed,
  Building,
  GenderRestriction,
  InactiveReason,
  Room,
} from './inventory';
export type {
  Gender,
  HousingType,
  Religion,
  Religious,
  Student,
  StudentCategory,
  StudentSummary,
  StudentWritePayload,
} from './students';
export type {
  AuthenticatedUser,
  AuthSession,
  LoginResponse,
  MeResponse,
  RefreshResponse,
  UserRole,
} from './auth';
