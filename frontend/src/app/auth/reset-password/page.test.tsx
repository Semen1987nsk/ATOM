import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

vi.mock('next/navigation', () => ({
  useSearchParams: () => new URLSearchParams('token=tok123'),
  useRouter: () => ({ push: vi.fn() }),
}));

const post = vi.fn().mockResolvedValue({});
vi.mock('@/lib/apiClient', () => ({
  api: { post: (...a: unknown[]) => post(...a) },
  ApiError: class ApiError extends Error {
    status: number;
    constructor(status: number, message: string) {
      super(message);
      this.status = status;
    }
  },
}));

import ResetPasswordPage from './page';

describe('ResetPasswordPage', () => {
  beforeEach(() => {
    post.mockClear();
  });

  it('шлёт new_password и token в /auth/password-reset/confirm', async () => {
    render(<ResetPasswordPage />);
    const inputs = screen.getAllByLabelText(/пароль/i);
    fireEvent.change(inputs[0], { target: { value: 'newpassword1234' } });
    fireEvent.change(inputs[1], { target: { value: 'newpassword1234' } });
    fireEvent.click(screen.getByRole('button', { name: /сохранить|сбросить|обновить/i }));
    await waitFor(() =>
      expect(post).toHaveBeenCalledWith('/auth/password-reset/confirm', {
        body: { token: 'tok123', new_password: 'newpassword1234' },
        noAuth: true,
      }),
    );
  });

  it('показывает ошибку при несовпадении паролей', async () => {
    render(<ResetPasswordPage />);
    const inputs = screen.getAllByLabelText(/пароль/i);
    fireEvent.change(inputs[0], { target: { value: 'newpassword1234' } });
    fireEvent.change(inputs[1], { target: { value: 'other12345678' } });
    fireEvent.click(screen.getByRole('button', { name: /сохранить|сбросить|обновить/i }));
    await waitFor(() => expect(screen.getByText(/не совпадают/i)).toBeInTheDocument());
    expect(post).not.toHaveBeenCalled();
  });
});
