/**
 * FE-12 (Sprint 5, Batch 8): AuthContext smoke-тесты.
 *
 * Не повторяем покрытие apiClient (refresh-retry, CSRF — это отдельный тест).
 * Здесь — про публичный контракт контекста:
 *   1. Гость = user:null + isAuthenticated:false после первого ответа /auth/me 401.
 *   2. Успешный /auth/me → user заполнен, isAuthenticated:true.
 *   3. logout() очищает кеш, диспатчит сетевой POST /auth/logout, ставит user=null.
 *
 * api мокаем целиком (vi.mock), чтобы не дёргать настоящий fetch.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import React from 'react';

import { ApiError } from '@/lib/apiClient';

// Mocks ДО импорта контекста.
const apiGetMock = vi.fn();
const apiPostMock = vi.fn();
vi.mock('@/lib/apiClient', async () => {
  const actual = await vi.importActual<typeof import('@/lib/apiClient')>('@/lib/apiClient');
  return {
    ...actual,
    api: {
      get: (...args: unknown[]) => apiGetMock(...args),
      post: (...args: unknown[]) => apiPostMock(...args),
      put: vi.fn(),
      patch: vi.fn(),
      delete: vi.fn(),
      upload: vi.fn(),
    },
    clearAuthTokens: vi.fn(),
  };
});

// next/navigation тоже мокаем — useRouter в jsdom не работает из коробки.
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => '/',
  useSearchParams: () => new URLSearchParams(),
}));

import { AuthProvider, useAuth } from '../AuthContext';

function makeWrapper() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return function Wrapper({ children }: { children: React.ReactNode }) {
    return (
      <QueryClientProvider client={qc}>
        <AuthProvider>{children}</AuthProvider>
      </QueryClientProvider>
    );
  };
}

describe('AuthContext', () => {
  beforeEach(() => {
    apiGetMock.mockReset();
    apiPostMock.mockReset();
  });

  it('гость: /auth/me возвращает 401 → user=null, isAuthenticated=false', async () => {
    apiGetMock.mockRejectedValueOnce(new ApiError(401, 'Unauthorized'));

    const { result } = renderHook(() => useAuth(), { wrapper: makeWrapper() });

    // Дожидаемся, пока первый запрос завершится (isPending=false).
    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    expect(result.current.user).toBeNull();
    expect(result.current.isAuthenticated).toBe(false);
    expect(result.current.token).toBeNull();
  });

  it('успешный /auth/me → user заполнен, isAuthenticated=true', async () => {
    apiGetMock.mockResolvedValueOnce({
      id: 1,
      email: 'me@example.com',
      name: 'Me',
      is_active: true,
      is_admin: false,
      created_at: '2026-01-01T00:00:00Z',
      last_login: null,
      settings: {},
    });

    const { result } = renderHook(() => useAuth(), { wrapper: makeWrapper() });

    await waitFor(() => {
      expect(result.current.isAuthenticated).toBe(true);
    });

    expect(result.current.user?.email).toBe('me@example.com');
    expect(result.current.token).toBe('cookie-session');
  });

  it('logout() вызывает POST /auth/logout и обнуляет user в кеше', async () => {
    apiGetMock.mockResolvedValueOnce({
      id: 1,
      email: 'me@example.com',
      name: null,
      is_active: true,
      is_admin: false,
      created_at: '2026-01-01T00:00:00Z',
      last_login: null,
      settings: {},
    });
    apiPostMock.mockResolvedValueOnce(undefined);

    const { result } = renderHook(() => useAuth(), { wrapper: makeWrapper() });

    await waitFor(() => expect(result.current.isAuthenticated).toBe(true));

    await act(async () => {
      result.current.logout();
      // Дать промису внутри logout добежать (api.post → finally → setQueryData).
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(apiPostMock).toHaveBeenCalledWith(
      '/auth/logout',
      expect.objectContaining({ noAuth: true }),
    );

    await waitFor(() => {
      expect(result.current.user).toBeNull();
      expect(result.current.isAuthenticated).toBe(false);
    });
  });
});

describe('AuthContext — cross-user state leak guard', () => {
  const userB = {
    id: 2,
    email: 'b@example.com',
    name: null,
    is_active: true,
    is_admin: false,
    created_at: '2026-01-01T00:00:00Z',
    last_login: null,
    settings: {},
  };

  beforeEach(() => {
    apiGetMock.mockReset();
    apiPostMock.mockReset();
    localStorage.clear();
  });

  it('purges previous user state when a DIFFERENT user resolves on mount (the GLDRUBF bug)', async () => {
    // Состояние прошлого юзера (A = id 1), оставшееся на этом устройстве:
    localStorage.setItem('empirik:last_user_id', '1');
    localStorage.setItem(
      'tradingSettings',
      JSON.stringify({ tradesStartTradeSymbol: 'GLDRUBF', tradesStartDate: '2025-10-21' }),
    );
    localStorage.setItem('empirik_journal_filters_v1', JSON.stringify({ search: 'SBER' }));
    // device-преференсы — обязаны выжить (иначе регресс):
    localStorage.setItem('empirik.cookie_consent.v1', '{"version":"v1"}');
    localStorage.setItem('language', 'en');
    localStorage.setItem('empirik:sidebar-collapsed', 'true');
    localStorage.setItem('empirik_history_sort', 'opened_at');

    const onChanged = vi.fn();
    window.addEventListener('auth:user-changed', onChanged);

    // /auth/me резолвит ДРУГОГО пользователя (B = id 2). mockResolvedValue (не Once)
    // — устойчиво к фоновому refetch, который React Query делает после clear().
    apiGetMock.mockResolvedValue(userB);

    const { result } = renderHook(() => useAuth(), { wrapper: makeWrapper() });
    await waitFor(() => expect(result.current.isAuthenticated).toBe(true));

    // user-scoped очищено:
    expect(localStorage.getItem('tradingSettings')).toBeNull();
    expect(localStorage.getItem('empirik_journal_filters_v1')).toBeNull();
    // device-преференсы сохранены:
    expect(localStorage.getItem('empirik.cookie_consent.v1')).not.toBeNull();
    expect(localStorage.getItem('language')).toBe('en');
    expect(localStorage.getItem('empirik:sidebar-collapsed')).toBe('true');
    expect(localStorage.getItem('empirik_history_sort')).toBe('opened_at');
    // владелец обновлён + событие сброса разослано контекстам:
    expect(localStorage.getItem('empirik:last_user_id')).toBe('2');
    expect(onChanged).toHaveBeenCalled();

    window.removeEventListener('auth:user-changed', onChanged);
  });

  it('keeps state when the SAME user returns (no purge, prefs preserved)', async () => {
    localStorage.setItem('empirik:last_user_id', '2');
    localStorage.setItem('tradingSettings', JSON.stringify({ tradesStartTradeSymbol: 'GLDRUBF' }));
    const onChanged = vi.fn();
    window.addEventListener('auth:user-changed', onChanged);

    apiGetMock.mockResolvedValue(userB); // id 2 == владелец
    const { result } = renderHook(() => useAuth(), { wrapper: makeWrapper() });
    await waitFor(() => expect(result.current.isAuthenticated).toBe(true));

    expect(localStorage.getItem('tradingSettings')).not.toBeNull();
    expect(onChanged).not.toHaveBeenCalled();
    window.removeEventListener('auth:user-changed', onChanged);
  });

  it('guest mount does not purge device prefs or crash', async () => {
    localStorage.setItem('language', 'ru');
    apiGetMock.mockRejectedValue(new ApiError(401, 'Unauthorized'));
    const { result } = renderHook(() => useAuth(), { wrapper: makeWrapper() });
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(localStorage.getItem('language')).toBe('ru');
  });

  it('purges on logout transition (A→null): owner был, теперь гость 401', async () => {
    // Прошлый владелец (id 2) + его состояние; на /auth/me теперь 401 (вышел).
    localStorage.setItem('empirik:last_user_id', '2');
    localStorage.setItem('tradingSettings', JSON.stringify({ tradesStartTradeSymbol: 'GLDRUBF' }));
    localStorage.setItem('language', 'en'); // device pref — обязан выжить
    const onChanged = vi.fn();
    window.addEventListener('auth:user-changed', onChanged);

    apiGetMock.mockRejectedValue(new ApiError(401, 'Unauthorized'));

    const { result } = renderHook(() => useAuth(), { wrapper: makeWrapper() });
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(localStorage.getItem('tradingSettings')).toBeNull(); // user-scoped вычищено
    expect(localStorage.getItem('language')).toBe('en'); // device pref цел
    expect(localStorage.getItem('empirik:last_user_id')).toBeNull(); // владелец сброшен (null)
    expect(onChanged).toHaveBeenCalled();
    window.removeEventListener('auth:user-changed', onChanged);
  });
});
