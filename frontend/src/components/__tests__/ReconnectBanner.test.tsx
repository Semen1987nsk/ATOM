import { render, screen, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { ReconnectBanner } from '../ReconnectBanner';
import { api } from '@/lib/apiClient';

vi.mock('@/lib/apiClient', () => ({ api: { get: vi.fn() } }));

describe('ReconnectBanner', () => {
  beforeEach(() => vi.clearAllMocks());

  it('НЕ показывает баннер для намеренной деактивации user_request', async () => {
    (api.get as ReturnType<typeof vi.fn>).mockResolvedValue([
      { id: 1, broker: 'tinkoff', is_active: false, last_sync_status: null,
        last_sync_error: 'deactivated: user_request' },
    ]);
    const { container } = render(<ReconnectBanner />);
    await waitFor(() => expect(api.get).toHaveBeenCalled());
    expect(container.textContent).not.toContain('Требуется переподключение');
  });

  it('показывает баннер для реального отзыва токена', async () => {
    (api.get as ReturnType<typeof vi.fn>).mockResolvedValue([
      { id: 2, broker: 'tinkoff', is_active: false, last_sync_status: 'error',
        last_sync_error: 'deactivated: token_invalid' },
    ]);
    render(<ReconnectBanner />);
    await waitFor(() =>
      expect(screen.getByText('Требуется переподключение брокера')).toBeInTheDocument());
  });
});
