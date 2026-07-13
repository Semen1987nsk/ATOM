import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

const get = vi.fn().mockResolvedValue({ trades: [{ id: 1, symbol: 'SBER', direction: 'LONG', entry_at: '2026-01-01T10:00:00Z', exit_at: '2026-01-02T10:00:00Z', entry_price: 100, exit_price: 110, pnl: 1234.5, net_pnl: 1234.5, has_early_exit: false, max_missed_pct: 0, worst_period: null, analysis: {} }] });
vi.mock('@/lib/apiClient', () => ({
  api: { get: (...a: unknown[]) => get(...a), post: vi.fn() },
}));
vi.mock('@/contexts/SettingsContext', () => ({
  useSettings: () => ({ formatCurrency: (amount: number) => `$${Math.abs(amount).toFixed(2)}` }),
}));

import { PostExitCard } from './PostExitCard';

describe('PostExitCard', () => {
  it('форматирует P&L в списке сделок через formatCurrency (не хардкод ₽)', async () => {
    render(<PostExitCard tradesCount={5} />);
    fireEvent.click(screen.getByRole('button', { name: /все сделки/i }));
    await waitFor(() => expect(screen.getByText('$1234.50')).toBeInTheDocument());
  });
});
