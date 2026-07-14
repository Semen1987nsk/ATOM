/**
 * S4-15: logout() должен резолвиться ТОЛЬКО после того, как
 * api.post('/auth/logout') завершился — иначе handleLogout делает
 * window.location.href до того, как сервер отозвал jti/очистил cookies,
 * и навигация абортирует in-flight fetch.
 */
import { describe, it, expect, vi } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';

// Управляемый deferred на api.post: держим сеть «в полёте», пока сами не резолвим.
// vi.mock фактор хойстится к верху файла — весь state, на который он ссылается,
// должен быть создан внутри vi.hoisted, иначе ReferenceError (TDZ).
const { postSpy, deferred } = vi.hoisted(() => {
  const deferred: { resolve: () => void } = { resolve: () => undefined };
  const postSpy = vi.fn(() => new Promise<void>((r) => { deferred.resolve = r; }));
  return { postSpy, deferred };
});
vi.mock('@/lib/apiClient', () => ({
  api: { post: postSpy, get: vi.fn(async () => null) },
  clearAuthTokens: vi.fn(),
}));

import { AuthProvider, useAuth } from '@/contexts/AuthContext';

const wrapper = ({ children }: { children: ReactNode }) => (
  <QueryClientProvider client={new QueryClient()}>
    <AuthProvider>{children}</AuthProvider>
  </QueryClientProvider>
);

describe('logout awaitable', () => {
  it('resolves only after api.post(/auth/logout) settles', async () => {
    const { result } = renderHook(() => useAuth(), { wrapper });
    let settled = false;
    await act(async () => {
      const p = Promise.resolve(result.current.logout()).then(() => { settled = true; });
      await Promise.resolve();            // дать микротаскам прокрутиться
      expect(settled).toBe(false);        // сеть ещё «в полёте» → logout НЕ завершён
      deferred.resolve();                 // отпускаем api.post
      await p;
    });
    expect(settled).toBe(true);
    expect(postSpy).toHaveBeenCalledWith('/auth/logout', { noAuth: true });
  });
});
