// Types owned by the auth feature: the value AuthContext provides and the
// user object it normalizes. AuthContext.jsx stays JavaScript in R3; the
// JSDoc annotation on its context object points at AuthContextValue so
// TypeScript consumers (shared/i18n/useLanguage.ts, tests) see a typed API.
import type { Dispatch, SetStateAction } from 'react';
import type { AuthenticatedUser, Id } from '../../shared/api/contracts';
import type { Language } from '../../shared/i18n/types';

/**
 * The user as AuthContext keeps it: the serialized user plus the region id
 * resolved from whichever field carried it. Index signature because
 * normalizeUser spreads whatever the backend returned.
 */
export interface AuthUser extends Partial<AuthenticatedUser> {
  normalizedRegionId: Id | null;
  [key: string]: unknown;
}

export interface LoginResult {
  success: boolean;
  user?: AuthUser;
  error?: string;
}

/** Any object a transfer-permission helper can read region ids from. */
export type TransferLike = Record<string, unknown> | null | undefined;

export type RegionRef = Id | Record<string, unknown> | null | undefined;

export interface AuthContextValue {
  user: AuthUser | null;
  loading: boolean;
  error: string | null;
  login: (email: string, password: string) => Promise<LoginResult>;
  logout: () => Promise<void>;
  refreshUser: () => Promise<AuthUser | null>;

  language: Language;
  setLanguage: (next: Language) => void;
  toggleLanguage: () => void;
  isRTL: boolean;

  PERMISSIONS: Readonly<Record<string, string>>;
  hasPermission: (permission: string) => boolean;

  isCentralAdmin: () => boolean;
  isRegionBoss: () => boolean;
  isEmployee: () => boolean;

  getUserRegion: () => Id | null;
  getUserRegionId: () => Id | null;

  canAccessRegion: (regionId: RegionRef) => boolean;
  canEditRegion: (regionId: RegionRef) => boolean;

  canManageUsers: () => boolean;
  canManageUsersInRegion: (regionId: RegionRef) => boolean;

  canRunAllocation: () => boolean;
  canRunAllocationForRegion: (regionId: RegionRef) => boolean;

  canApproveTransfer: (transfer: TransferLike) => boolean;
  isCrossRegionTransfer: (transfer: TransferLike) => boolean;
  isWithinMyRegionTransfer: (transfer: TransferLike) => boolean;
  getTransferFromRegion: (transfer: TransferLike) => Id | null;
  getTransferToRegion: (transfer: TransferLike) => Id | null;

  canUploadExcel: () => boolean;
  canAssignPriority: () => boolean;
  canAssistAllocation: () => boolean;
  canOverrideAllocation: () => boolean;
}

/** Narrow alias so JSDoc in AuthContext.jsx can name the setter type. */
export type SetLanguage = Dispatch<SetStateAction<Language>>;
