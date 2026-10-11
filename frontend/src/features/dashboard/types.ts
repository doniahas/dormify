// Payload of GET /api/home/ (backend/api/views/dashboard.py:home_dashboard).
// The dashboard is composed server-side with bilingual labels; the page
// renders the sections it receives.
import type {
  AllocationRun,
  ImportBatch,
  IsoDateTime,
  Region,
  RegionInbox,
  UserRole,
} from '../../shared/api/contracts';

export type HomeDashboardUser = {
  name: string;
  role: UserRole | string;
  role_display: string;
  region_id: Region['id'] | null;
  region_name: string | null;
};

export type HomeMetrics = {
  assigned_students: number;
  unassigned_students: number;
  occupancy_rate: number;
  available_beds: number;
  pending_requests: number;
};

export type HomeProcess = {
  latest_batch: ImportBatch | null;
  latest_inbox: RegionInbox | null;
  active_run: AllocationRun | null;
  latest_run: AllocationRun | null;
  has_completed_run: boolean;
};

export type WorkflowStepKey = 'upload' | 'data_review' | 'regional_processing' | 'allocation' | 'results_review';

export type WorkflowStep = {
  key: WorkflowStepKey;
  label_he: string;
  label_en: string;
  status: string;
};

export type PrimaryAction = {
  key: string;
  label_he: string;
  label_en: string;
  route: string;
};

export type AttentionItem = {
  id: string;
  severity: 'error' | 'warning' | 'info';
  icon: string;
  count: number;
  title_he: string;
  title_en: string;
  description_he: string;
  description_en: string;
  route: string;
};

export type RecentActivity = {
  id: string;
  type: 'upload' | 'allocation' | 'request';
  icon: string;
  status: string;
  title_he: string;
  title_en: string;
  subtitle_he: string;
  subtitle_en: string;
  timestamp: IsoDateTime | null;
  route: string;
};

export interface HomeDashboard {
  user?: HomeDashboardUser;
  /** 'system' for a central admin, 'region' otherwise. */
  scope?: 'system' | 'region';
  metrics?: HomeMetrics;
  process?: HomeProcess;
  workflow?: WorkflowStep[];
  situation_he?: string;
  situation_en?: string;
  primary_action?: PrimaryAction | null;
  attention_items?: AttentionItem[];
  recent_activity?: RecentActivity[];
  error?: string;
  errorEn?: string;
  [key: string]: unknown;
}
