import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn() }),
}));

const post = vi.fn().mockResolvedValue({ message: 'Если такой email зарегистрирован, мы выслали ссылку.' });
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

import ForgotPasswordPage from './page';

describe('ForgotPasswordPage', () => {
  beforeEach(() => {
    post.mockClear();
  });

  it('шлёт email в /auth/password-reset/request и показывает подтверждение', async () => {
    render(<ForgotPasswordPage />);
    const emailInput = screen.getByLabelText(/email/i);
    fireEvent.change(emailInput, { target: { value: 'user@example.com' } });
    fireEvent.click(screen.getByRole('button', { name: /отправить|восстановить/i }));

    await waitFor(() =>
      expect(post).toHaveBeenCalledWith('/auth/password-reset/request', {
        body: { email: 'user@example.com' },
        noAuth: true,
      }),
    );
    await waitFor(() => expect(screen.getByText(/проверьте почту/i)).toBeInTheDocument());
  });
});
