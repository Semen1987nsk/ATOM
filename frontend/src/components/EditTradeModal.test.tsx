import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

const patch = vi.fn().mockResolvedValue({});
vi.mock('@/lib/apiClient', () => ({
  api: { patch: (...a: unknown[]) => patch(...a) },
  ApiError: class ApiError extends Error {},
}));
vi.mock('@/contexts/ToastContext', () => ({ useToast: () => ({ success: vi.fn(), error: vi.fn() }) }));

import { EditTradeModal } from './EditTradeModal';

const syncTrade = {
  id: 42, symbol: 'SBER', direction: 'long', entry_price: 300, quantity: 10,
  entry_at: '2026-01-01T10:00:00Z', leverage: 1, commission: 0, swap: 0,
  confidence: null, tags: [], screenshot_url: null,
} as never;

describe('EditTradeModal', () => {
  it('шлёт confidence как null (не пустую строку) для sync-сделки без confidence', async () => {
    render(<EditTradeModal isOpen onClose={() => {}} onSuccess={() => {}} trade={syncTrade} />);
    fireEvent.click(screen.getByRole('button', { name: /обновить сделку/i }));
    await waitFor(() => expect(patch).toHaveBeenCalled());
    const body = patch.mock.calls[0][1].body;
    expect(body.confidence).toBeNull();
  });

  it('слайдер confidence ограничен диапазоном 1-5', () => {
    render(<EditTradeModal isOpen onClose={() => {}} onSuccess={() => {}} trade={syncTrade} />);
    const slider = screen.getByRole('slider') as HTMLInputElement;
    expect(slider.min).toBe('1');
    expect(slider.max).toBe('5');
  });
});
