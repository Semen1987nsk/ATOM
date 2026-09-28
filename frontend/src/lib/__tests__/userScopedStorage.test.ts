import { describe, it, expect, beforeEach } from 'vitest';
import { clearUserScopedState, USER_SCOPED_STORAGE_KEYS } from '../userScopedStorage';

describe('clearUserScopedState', () => {
  beforeEach(() => localStorage.clear());

  it('removes only user-scoped keys, keeps device-global ones', () => {
    // user-scoped (must be removed)
    localStorage.setItem('tradingSettings', JSON.stringify({ tradesStartTradeSymbol: 'GLDRUBF' }));
    localStorage.setItem('empirik_journal_filters_v1', JSON.stringify({ search: 'SBER', setupId: 5 }));
    localStorage.setItem('empirik_reconciliation_banner_dismissed_until', '2026-01-01T00:00:00Z');
    // device-global (must survive — clearing these would be a regression)
    localStorage.setItem('empirik.cookie_consent.v1', '{"version":"v1"}');
    localStorage.setItem('language', 'en');
    localStorage.setItem('empirik:sidebar-collapsed', 'true');
    localStorage.setItem('empirik_history_columns', '["a","b"]');
    localStorage.setItem('empirik_history_view_mode', 'flat');
    localStorage.setItem('empirik_history_sort', 'opened_at');
    localStorage.setItem('empirik_position_journal_columns_v2', '["x"]');
    localStorage.setItem('collapsible:dashboard-advanced', '1');

    clearUserScopedState();

    expect(localStorage.getItem('tradingSettings')).toBeNull();
    expect(localStorage.getItem('empirik_journal_filters_v1')).toBeNull();
    expect(localStorage.getItem('empirik_reconciliation_banner_dismissed_until')).toBeNull();

    expect(localStorage.getItem('empirik.cookie_consent.v1')).not.toBeNull();
    expect(localStorage.getItem('language')).toBe('en');
    expect(localStorage.getItem('empirik:sidebar-collapsed')).toBe('true');
    expect(localStorage.getItem('empirik_history_columns')).not.toBeNull();
    expect(localStorage.getItem('empirik_history_view_mode')).toBe('flat');
    expect(localStorage.getItem('empirik_history_sort')).toBe('opened_at');
    expect(localStorage.getItem('empirik_position_journal_columns_v2')).not.toBeNull();
    expect(localStorage.getItem('collapsible:dashboard-advanced')).toBe('1');
  });

  it('includes the GLDRUBF-bug key (tradingSettings)', () => {
    expect(USER_SCOPED_STORAGE_KEYS).toContain('tradingSettings');
  });

  it('does not throw when the keys are absent', () => {
    expect(() => clearUserScopedState()).not.toThrow();
  });
});
