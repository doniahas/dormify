// /api/staff-users/ (backend/accounts/serializers.py StaffUserSerializer).
// Unlike the rest of the API this serializer uses camelCase field names.
import type { UserRole } from '../../shared/api/contracts';

export interface StaffUser {
  id: number;
  name: string;
  email: string;
  role: UserRole;
  regionId: string | null;
  regionName: string | null;
  regionNameEn: string | null;
}

/** POST /api/staff-users/ body. `password` is write-only. */
export interface StaffUserPayload {
  name?: string;
  email: string;
  password?: string;
  role: UserRole | string;
  regionId?: string | null;
}
