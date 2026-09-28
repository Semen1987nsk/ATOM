/**
 * S1-06c: password-login 2FA UI.
 *
 * Whole-branch review нашёл CRITICAL-разрыв: backend enforce'ит TOTP на
 * POST /auth/login (S1-06), но форма логина не умела спрашивать код —
 * password-юзер с включённой 2FA не мог войти вообще.
 *
 * Контракт:
 *   (а) ответ "2FA required" (ApiError.totpRequired=true) → появляется поле
 *       ввода 6-значного кода вместо обычной ошибки.
 *   (б) повторный submit шлёт totp_code третьим аргументом в login().
 *   (в) обычный 401 "неверный пароль" (totpRequired не задан) → поле кода
 *       НЕ появляется, показывается голая ошибка.
 *   (г) неверный код → ошибка, юзер остаётся на шаге ввода кода (email/
 *       пароль не сбрасываются).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

const pushMock = vi.fn();
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: pushMock, replace: vi.fn() }),
}));

const loginMock = vi.fn();
const refreshUserMock = vi.fn();
vi.mock('@/contexts/AuthContext', () => ({
  useAuth: () => ({
    login: loginMock,
    refreshUser: refreshUserMock,
    isAuthenticated: false,
    isLoading: false,
  }),
}));

vi.mock('@/lib/apiClient', () => ({
  ApiError: class ApiError extends Error {
    status: number;
    detail: string;
    totpRequired?: boolean;
    constructor(status: number, detail: string, requestId?: string, totpRequired?: boolean) {
      super(detail);
      this.status = status;
      this.detail = detail;
      this.totpRequired = totpRequired;
    }
  },
  getApiUrl: (path: string) => `http://localhost:8000${path}`,
}));

import LoginPage from './page';
import { ApiError } from '@/lib/apiClient';

describe('LoginPage — 2FA code step', () => {
  beforeEach(() => {
    loginMock.mockReset();
    refreshUserMock.mockReset();
    pushMock.mockReset();
  });

  function fillEmailPassword() {
    fireEvent.change(screen.getByLabelText(/email/i), { target: { value: 'a@b.com' } });
    fireEvent.change(screen.getByLabelText('Пароль', { exact: true }), {
      target: { value: 'password12345' },
    });
  }

  it('показывает поле ввода TOTP-кода, когда login() бросает totpRequired=true', async () => {
    loginMock.mockRejectedValueOnce(
      new ApiError(401, 'Требуется код двухфакторной аутентификации', undefined, true),
    );

    render(<LoginPage />);
    fillEmailPassword();
    fireEvent.click(screen.getByRole('button', { name: /войти/i }));

    await waitFor(() => {
      expect(screen.getByLabelText(/код.*(2fa|двухфактор)|totp/i)).toBeInTheDocument();
    });
  });

  it('повторный submit шлёт totp_code третьим аргументом в login()', async () => {
    loginMock.mockRejectedValueOnce(
      new ApiError(401, 'Требуется код двухфакторной аутентификации', undefined, true),
    );
    loginMock.mockResolvedValueOnce(undefined);

    render(<LoginPage />);
    fillEmailPassword();
    fireEvent.click(screen.getByRole('button', { name: /войти/i }));

    const codeInput = await screen.findByLabelText(/код.*(2fa|двухфактор)|totp/i);
    fireEvent.change(codeInput, { target: { value: '123456' } });

    const submitButtons = screen.getAllByRole('button', { name: /войти|подтвердить/i });
    fireEvent.click(submitButtons[submitButtons.length - 1]);

    await waitFor(() => {
      expect(loginMock).toHaveBeenLastCalledWith('a@b.com', 'password12345', '123456');
    });
  });

  it('обычный 401 "неверный пароль" НЕ показывает поле кода', async () => {
    loginMock.mockRejectedValueOnce(new ApiError(401, 'Неверный email или пароль'));

    render(<LoginPage />);
    fillEmailPassword();
    fireEvent.click(screen.getByRole('button', { name: /войти/i }));

    await waitFor(() => {
      expect(screen.getByText(/неверный email или пароль/i)).toBeInTheDocument();
    });
    expect(screen.queryByLabelText(/код.*(2fa|двухфактор)|totp/i)).not.toBeInTheDocument();
  });

  it('неверный код на втором шаге — ошибка, email/пароль не сбрасываются', async () => {
    loginMock.mockRejectedValueOnce(
      new ApiError(401, 'Требуется код двухфакторной аутентификации', undefined, true),
    );
    loginMock.mockRejectedValueOnce(
      new ApiError(401, 'Требуется код двухфакторной аутентификации', undefined, true),
    );

    render(<LoginPage />);
    fillEmailPassword();
    fireEvent.click(screen.getByRole('button', { name: /войти/i }));

    const codeInput = await screen.findByLabelText(/код.*(2fa|двухфактор)|totp/i);
    fireEvent.change(codeInput, { target: { value: '000000' } });
    const submitButtons = screen.getAllByRole('button', { name: /войти|подтвердить/i });
    fireEvent.click(submitButtons[submitButtons.length - 1]);

    await waitFor(() => {
      expect(loginMock).toHaveBeenCalledTimes(2);
    });
    // остались на шаге ввода кода
    expect(screen.getByLabelText(/код.*(2fa|двухфактор)|totp/i)).toBeInTheDocument();
  });
});
