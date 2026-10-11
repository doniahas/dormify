import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { act, fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';

import { createDeferred } from '../../shared/test/deferred';
import { AuthProvider } from './AuthContext';
import LoginPage from './LoginPage';

// The real AuthProvider is used so the page is exercised against the actual
// login contract (result shape and error text included); only the service
// boundary below the provider is mocked.
vi.mock('../../shared/api/client', () => ({
  subscribeSessionExpired: vi.fn(() => () => {}),
}));

vi.mock('./api', () => ({
  authAPI: {
    restoreSession: vi.fn(),
    login: vi.fn(),
    logout: vi.fn(),
    getMe: vi.fn(),
  },
}));

import { authAPI } from './api';

const EMAIL = 'dorm.staff@example.edu';
const PASSWORD = 'correct-horse';

// The page navigates through useNavigate, so the destination is observable
// only from the router.
function CurrentPath() {
  const { pathname } = useLocation();

  return <p>{`current path: ${pathname}`}</p>;
}

async function renderLoginPage({ language = 'en' } = {}) {
  const utils = render(
    <AuthProvider>
      <MemoryRouter initialEntries={['/login']}>
        <Routes>
          <Route
            path="/login"
            element={<LoginPage language={language} onLanguageToggle={() => {}} />}
          />
          <Route path="/dashboard" element={<p>dashboard route</p>} />
        </Routes>
        <CurrentPath />
      </MemoryRouter>
    </AuthProvider>
  );

  // Let the provider's boot-time session restoration settle before the test
  // interacts with the form.
  await act(async () => {});

  return utils;
}

const emailField = () => screen.getByLabelText('Email Address');
const passwordField = () => screen.getByLabelText('Password');
const submitButton = () => screen.getByRole('button', { name: 'Login' });

beforeEach(() => {
  authAPI.restoreSession.mockResolvedValue(null);
  authAPI.login.mockResolvedValue({ user: { email: EMAIL, role: 'employee' } });
  authAPI.logout.mockResolvedValue(undefined);
  authAPI.getMe.mockResolvedValue(null);
});

describe('LoginPage copyright footer', () => {
  it.each([
    ['Hebrew', 'he', 'rtl'],
    ['English', 'en', 'ltr'],
  ])('isolates the copyright line as left-to-right text in the %s layout', async (_label, language, pageDirection) => {
    const { container } = await renderLoginPage({ language });

    // The page itself follows the UI language, but the Latin copyright line
    // is an isolated LTR run so it never renders as "... 2026 ©" on the
    // Hebrew page (the order observed before the fix).
    expect(container.querySelector('.login-wrapper')).toHaveAttribute('dir', pageDirection);

    const footer = screen.getByText('© 2026 Dormify Project Contributors');
    expect(footer).toHaveAttribute('dir', 'ltr');
    expect(footer.textContent.trim()).toBe('© 2026 Dormify Project Contributors');
  });
});

describe('LoginPage client-side validation', () => {
  it.each([
    ['the form is empty', '', '', 'Please enter an email address'],
    ['the email is malformed', 'dorm.staff.technion', PASSWORD, 'The email address is invalid'],
  ])('blocks the login request when %s', async (_label, email, password, message) => {
    const user = userEvent.setup();

    await renderLoginPage();

    if (email) await user.type(emailField(), email);
    if (password) await user.type(passwordField(), password);

    await user.click(submitButton());

    expect(screen.getByRole('alert')).toHaveTextContent(message);
    expect(authAPI.login).not.toHaveBeenCalled();
    expect(screen.getByText('current path: /login')).toBeInTheDocument();
  });
});

describe('LoginPage submission', () => {
  it('sends no surrounding whitespace in the email when the field is padded', async () => {
    const user = userEvent.setup();

    await renderLoginPage();

    await user.type(emailField(), `  ${EMAIL}  `);
    await user.type(passwordField(), PASSWORD);

    // Two guards produce this contract, and only their combined result is
    // observable here: an <input type="email"> runs the HTML value
    // sanitization algorithm (leading/trailing whitespace is stripped by
    // the control itself, in jsdom and in browsers alike), and handleSubmit
    // additionally trims before calling login. Typed padding therefore
    // never reaches component state, so this test protects the end-to-end
    // contract rather than the trim() call on its own.
    expect(emailField()).toHaveValue(EMAIL);

    await user.click(submitButton());

    expect(authAPI.login).toHaveBeenCalledTimes(1);
    expect(authAPI.login).toHaveBeenCalledWith(EMAIL, PASSWORD);
  });

  it('ignores a second submission while the first one is still pending', async () => {
    const user = userEvent.setup();
    const pendingLogin = createDeferred();
    authAPI.login.mockReturnValue(pendingLogin.promise);

    const { container } = await renderLoginPage();

    await user.type(emailField(), EMAIL);
    await user.type(passwordField(), PASSWORD);
    await user.click(submitButton());

    const pendingButton = screen.getByRole('button', { name: 'Logging in...' });
    expect(pendingButton).toBeDisabled();

    // Both realistic repeat paths: clicking the button again, and the form
    // receiving another submit event (what Enter in a field produces).
    await user.click(pendingButton);
    fireEvent.submit(container.querySelector('form'));

    expect(authAPI.login).toHaveBeenCalledTimes(1);
    expect(screen.getByRole('button', { name: 'Logging in...' })).toBeDisabled();
    expect(screen.getByText('current path: /login')).toBeInTheDocument();

    await act(async () => {
      pendingLogin.resolve({ user: { email: EMAIL, role: 'employee' } });
    });

    expect(authAPI.login).toHaveBeenCalledTimes(1);
  });

  it('keeps the form usable and shows the error after a failed login', async () => {
    const user = userEvent.setup();
    authAPI.login.mockRejectedValue(Object.assign(new Error('Login failed'), { status: 401 }));

    await renderLoginPage();

    await user.type(emailField(), EMAIL);
    await user.type(passwordField(), 'wrong-password');
    await user.click(submitButton());

    // The provider produces this generic message for a rejected credential
    // check and does not localize it for the page's language prop. This is
    // the current contract, asserted as-is.
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'כתובת האימייל או הסיסמה שגויים'
    );

    expect(emailField()).toHaveValue(EMAIL);
    expect(submitButton()).toBeEnabled();
    expect(screen.getByText('current path: /login')).toBeInTheDocument();
    expect(screen.queryByText('dashboard route')).not.toBeInTheDocument();
  });

  it('navigates to the dashboard after a successful login', async () => {
    const user = userEvent.setup();

    await renderLoginPage();

    await user.type(emailField(), EMAIL);
    await user.type(passwordField(), PASSWORD);
    await user.click(submitButton());

    expect(await screen.findByText('current path: /dashboard')).toBeInTheDocument();
    expect(screen.getByText('dashboard route')).toBeInTheDocument();
  });
});
