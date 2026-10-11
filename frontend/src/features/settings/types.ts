// Account self-service payloads (backend/api/views/auth.py change_password_view
// and change_email_view). The adapter accepts either the backend's snake_case
// names or the form's camelCase names and always sends snake_case.
import type { AuthenticatedUser } from '../../shared/api/contracts';

export interface ChangePasswordPayload {
  current_password?: string;
  currentPassword?: string;
  new_password?: string;
  newPassword?: string;
  confirm_password?: string;
  confirmPassword?: string;
}

export interface ChangeEmailPayload {
  current_email?: string;
  currentEmail?: string;
  new_email?: string;
  newEmail?: string;
  confirm_email?: string;
  confirmEmail?: string;
  /** G3-18: current-password re-authentication, required server-side. */
  password: string;
}

export interface AccountChangeResponse {
  success: boolean;
  message?: string;
  error?: string;
  /** change-email returns the updated profile. */
  user?: AuthenticatedUser;
}
