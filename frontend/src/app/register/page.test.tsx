/**
 * B1 verification-first: страница регистрации на успешный ответ показывает
 * «Проверьте почту» и НЕ логинит / НЕ редиректит на дашборд.
 *
 * Контракт:
 *   (а) успешный register() → появляется состояние «Проверьте почту»,
 *       router.push('/') НЕ вызывается (юзер не залогинен).
 *   (б) ошибка register() → показывается ошибка, состояния «проверьте почту»
 *       нет, редиректа нет.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

const pushMock = vi.fn();
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: pushMock, replace: vi.fn() }),
}));

const registerMock = vi.fn();
const refreshUserMock = vi.fn();
vi.mock('@/contexts/AuthContext', () => ({
  useAuth: () => ({
    register: registerMock,
    refreshUser: refreshUserMock,
    isAuthenticated: false,
    isLoading: false,
  }),
}));

// OAuthButtons тянет apiClient — мокаем как no-op, чтобы не грузить сеть.
vi.mock('@/components/OAuthButtons', () => ({
  OAuthButtons: () => null,
}));

import RegisterPage from './page';

function fillValidForm() {
  fireEvent.change(screen.getByLabelText(/email/i), {
    target: { value: 'new@example.com' },
  });
  fireEvent.change(screen.getByLabelText('Пароль', { exact: true }), {
    target: { value: 'verylongpassword123' },
  });
  fireEvent.change(screen.getByLabelText(/подтвердите пароль/i), {
    target: { value: 'verylongpassword123' },
  });
  fireEvent.click(screen.getByRole('checkbox', { name: /персональных данных/i }));
}

describe('RegisterPage — verification-first (B1)', () => {
  beforeEach(() => {
    registerMock.mockReset();
    refreshUserMock.mockReset();
    pushMock.mockReset();
  });

  it('успешный register → показ «Проверьте почту», без редиректа на дашборд', async () => {
    registerMock.mockResolvedValueOnce(undefined);

    render(<RegisterPage />);
    fillValidForm();
    fireEvent.click(screen.getByRole('button', { name: /создать аккаунт/i }));

    await waitFor(() => {
      expect(screen.getByText(/проверьте почту/i)).toBeInTheDocument();
    });
    expect(pushMock).not.toHaveBeenCalled();
    expect(registerMock).toHaveBeenCalledWith(
      'new@example.com',
      'verylongpassword123',
      undefined,
      true,
    );
  });

  it('ошибка register → показ ошибки, без «Проверьте почту» и без редиректа', async () => {
    registerMock.mockRejectedValueOnce(new Error('Ошибка регистрации'));

    render(<RegisterPage />);
    fillValidForm();
    fireEvent.click(screen.getByRole('button', { name: /создать аккаунт/i }));

    await waitFor(() => {
      expect(screen.getByText(/ошибка регистрации/i)).toBeInTheDocument();
    });
    expect(screen.queryByText(/проверьте почту/i)).not.toBeInTheDocument();
    expect(pushMock).not.toHaveBeenCalled();
  });
});
