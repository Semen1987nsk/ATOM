import { describe, it, expect, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import type { ReactNode } from 'react';
import { SettingsProvider, useSettings } from '@/contexts/SettingsContext';
import { clearUserScopedState } from '@/lib/userScopedStorage';

const wrapper = ({ children }: { children: ReactNode }) => (
  <SettingsProvider>{children}</SettingsProvider>
);

describe('theme persistence (device-scoped)', () => {
  beforeEach(() => localStorage.clear());

  it('updateSettings пишет theme в device-ключ empirik.theme и он переживает logout', () => {
    const { result } = renderHook(() => useSettings(), { wrapper });
    act(() => { result.current.updateSettings({ theme: 'light' }); });
    // (1) тема ушла в device-ключ, а не только в user-scoped tradingSettings
    expect(localStorage.getItem('empirik.theme')).toBe('light');
    // (2) logout (смена владельца) её не стирает
    clearUserScopedState();
    expect(localStorage.getItem('empirik.theme')).toBe('light');
  });
});
