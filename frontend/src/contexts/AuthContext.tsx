'use client';

import React, { createContext, useContext, useEffect, useCallback, ReactNode } from 'react';
import { useRouter } from 'next/navigation';
import { useQueryClient } from '@tanstack/react-query';
import { api, clearAuthTokens } from '@/lib/apiClient';
import { useCurrentUserQuery, queryKeys } from '@/lib/queries';

// ==================== TYPES ====================

export interface User {
  id: number;
  email: string;
  name: string | null;
  is_active: boolean;
  is_admin: boolean;
  created_at: string;
  last_login: string | null;
  settings: Record<string, unknown>;
  oauth_provider?: string | null;
  registration_source?: string | null;
}

interface AuthContextType {
  user: User | null;
  token: string | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, name: string | undefined, pdConsent: boolean) => Promise<void>;
  logout: () => void;
  updateProfile: (data: { name?: string; settings?: Record<string, unknown> }) => Promise<void>;
  refreshUser: () => Promise<void>;
}

// ==================== CONTEXT ====================

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  // FE-07 (Sprint 5, Batch 4): user живёт в TanStack кеше через useCurrentUserQuery.
  // Все мутации (login/register/logout/updateProfile) инвалидируют queryKeys.auth.me
  // или явно прописывают свежие данные в кеш — это даёт single-source-of-truth
  // и дедупликацию запросов /auth/me между компонентами.
  const queryClient = useQueryClient();
  const userQuery = useCurrentUserQuery({
    // 401 = просто не авторизован, не retry (это норма для гостя).
    retry: false,
  });

  // `token` — legacy-поле для совместимости с компонентами, которые проверяют
  // его наличие как «есть сессия». Реальная сессия — httpOnly cookie.
  // Локальный User-тип шире, чем UserResponse (codegen), поэтому каст.
  const user = (userQuery.data as User | undefined) ?? null;
  const token = user ? 'cookie-session' : null;
  // Различаем «ещё не успели спросить» (loading) и «спросили, 401» (not authed).
  // isPending = первый запрос ещё в полёте; после первого ответа (success/error)
  // pending=false, и UI безопасно решает по user.
  const isLoading = userQuery.isPending;

  // Logout-mutation как функция (не useMutation — нет инвалидации UI-плана,
  // и сам по себе logout это «сброс кеша»; tanstack-мутация тут избыточна).
  const logout = useCallback(() => {
    void api.post('/auth/logout', { noAuth: true }).catch(() => undefined).finally(() => {
      clearAuthTokens();
      // Явно ставим user=null в кеш — компоненты, которые подписаны на
      // useCurrentUserQuery, мгновенно увидят гостевое состояние без сетевого
      // round-trip. Дальше invalidateQueries даст refetch при следующем mount.
      queryClient.setQueryData(queryKeys.auth.me(), null);
      queryClient.removeQueries({ queryKey: ['trades'] });
      queryClient.removeQueries({ queryKey: ['stats'] });
    });
  }, [queryClient]);

  const refetchCurrentUser = useCallback(async () => {
    await userQuery.refetch();
  }, [userQuery]);

  const login = useCallback(
    async (email: string, password: string) => {
      await api.post('/auth/login', {
        body: { email, password },
        noAuth: true,
      });
      // После логина — обновить user в кеше; trades/stats должны быть свежими
      // под новым пользователем, поэтому invalidate всего.
      await refetchCurrentUser();
      queryClient.invalidateQueries({ queryKey: ['trades'] });
      queryClient.invalidateQueries({ queryKey: ['stats'] });
    },
    [refetchCurrentUser, queryClient],
  );

  const register = useCallback(
    async (
      email: string,
      password: string,
      name: string | undefined,
      pdConsent: boolean,
    ) => {
      // 152-ФЗ: pd_consent обязателен — backend отклонит запрос без него.
      await api.post('/auth/register', {
        body: { email, password, name, pd_consent: pdConsent },
        noAuth: true,
      });
      await refetchCurrentUser();
      queryClient.invalidateQueries({ queryKey: ['trades'] });
      queryClient.invalidateQueries({ queryKey: ['stats'] });
    },
    [refetchCurrentUser, queryClient],
  );

  useEffect(() => {
    const handleAuthLogout = () => {
      logout();
    };

    window.addEventListener('auth:logout', handleAuthLogout);
    return () => window.removeEventListener('auth:logout', handleAuthLogout);
  }, [logout]);

  const updateProfile = useCallback(
    async (data: { name?: string; settings?: Record<string, unknown> }) => {
      const updatedUser = await api.put<User>('/auth/me', { body: data });
      // Прямо записываем ответ в кеш — useCurrentUserQuery увидит обновление
      // без лишнего GET /auth/me.
      queryClient.setQueryData(queryKeys.auth.me(), updatedUser);
    },
    [queryClient],
  );

  // refreshUser остаётся в API как именованный метод (OAuth callback дёргает).
  const refreshUser = useCallback(async () => {
    await refetchCurrentUser();
  }, [refetchCurrentUser]);

  useEffect(() => {
    const handleAuthLogin = () => {
      void refreshUser();
    };

    window.addEventListener('auth:login', handleAuthLogin);
    return () => window.removeEventListener('auth:login', handleAuthLogin);
  }, [refreshUser]);

  const value: AuthContextType = {
    user,
    token,
    isLoading,
    isAuthenticated: !!user,
    login,
    register,
    logout,
    updateProfile,
    refreshUser,
  };

  return (
    <AuthContext.Provider value={value}>
      {children}
    </AuthContext.Provider>
  );
}

// ==================== HOOK ====================

export function useAuth(): AuthContextType {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}

export function RequireAuth({ children }: { children: ReactNode }) {
  const { isAuthenticated, isLoading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!isLoading && !isAuthenticated) {
      router.replace('/login');
    }
  }, [isAuthenticated, isLoading, router]);

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="animate-spin h-8 w-8 border-2 border-accent border-t-transparent rounded-full" />
      </div>
    );
  }

  if (!isAuthenticated) {
    return null;
  }

  return <>{children}</>;
}

