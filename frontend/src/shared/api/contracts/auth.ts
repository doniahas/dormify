// backend/api/serializers/auth.py and backend/api/views/auth.py
import type { IsoDateTime } from './common';

export type UserRole = 'central_admin' | 'region_boss' | 'employee';

/** UserSerializer - the authenticated user as /api/auth/me/ returns it. */
export interface AuthenticatedUser {
  id: number;
  email: string;
  username: string;
  first_name: string;
  last_name: string;
  full_name: string;
  role: UserRole;
  role_display: string;
  region: string | null;
  /** Omitted (not null) when the user has no region (central admin): dotted-source field without a default. */
  region_name?: string;
  phone: string;
  is_active: boolean;
  date_joined: IsoDateTime;
  is_central_admin: boolean;
  is_boss: boolean;
}

/** POST /api/auth/login/ success body. The refresh token is an HttpOnly cookie. */
export interface LoginResponse {
  message: string;
  messageEn: string;
  user: AuthenticatedUser;
  access: string;
}

/** POST /api/auth/refresh/ success body. */
export interface RefreshResponse {
  access: string;
  user: AuthenticatedUser;
}

/** GET /api/auth/me/ body. */
export interface MeResponse {
  user: AuthenticatedUser;
}

/** The in-memory session the auth adapter restores on app start. */
export interface AuthSession {
  access: string | null;
  user: AuthenticatedUser | null;
}
