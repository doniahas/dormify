import { afterEach, describe, expect, it } from 'vitest';
import MockAdapter from 'axios-mock-adapter';
import { api } from '../../shared/api/client';
import { settingsAPI } from './api';

const mock = new MockAdapter(api, { onNoMatch: 'throwException' });
afterEach(() => mock.reset());

const putBody = (index = 0) => JSON.parse(mock.history.put[index].data);

describe('password change', () => {
  it('accepts the form field names and sends the backend ones', async () => {
    mock.onPut('/api/auth/change-password/').reply(200, { success: true, message: 'הסיסמה עודכנה בהצלחה' });

    await expect(
      settingsAPI.changePassword({ currentPassword: 'old', newPassword: 'new-pass-1', confirmPassword: 'new-pass-1' })
    ).resolves.toEqual({ success: true, message: 'הסיסמה עודכנה בהצלחה' });

    expect(putBody()).toEqual({ current_password: 'old', new_password: 'new-pass-1', confirm_password: 'new-pass-1' });
  });

  it('passes backend field names through unchanged and reports the backend reason', async () => {
    mock.onPut('/api/auth/change-password/').reply(400, { success: false, error: 'הסיסמה הנוכחית אינה נכונה' });

    await expect(
      settingsAPI.changePassword({ current_password: 'bad', new_password: 'n', confirm_password: 'n' })
    ).rejects.toThrow('error: הסיסמה הנוכחית אינה נכונה');

    expect(putBody()).toEqual({ current_password: 'bad', new_password: 'n', confirm_password: 'n' });
  });
});

describe('email change', () => {
  it('always includes the re-authentication password', async () => {
    const updated = { success: true, user: { id: 1, email: 'new@example.edu' } };
    mock.onPut('/api/auth/change-email/').reply(200, updated);

    await expect(
      settingsAPI.changeEmail({
        currentEmail: 'old@example.edu',
        newEmail: 'new@example.edu',
        confirmEmail: 'new@example.edu',
        password: 'correct-horse',
      })
    ).resolves.toEqual(updated);

    expect(putBody()).toEqual({
      current_email: 'old@example.edu',
      new_email: 'new@example.edu',
      confirm_email: 'new@example.edu',
      password: 'correct-horse',
    });
  });

  it('falls back to the generic message when the server gives none', async () => {
    mock.onPut('/api/auth/change-email/').reply(500);

    await expect(
      settingsAPI.changeEmail({ newEmail: 'x@example.edu', password: 'p' })
    ).rejects.toThrow('Failed to change email: HTTP 500 with empty/unknown body');
  });
});
