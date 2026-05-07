'use client';

import React, { createContext, useContext, useState, useEffect, useCallback, ReactNode } from 'react';
import { useRouter } from 'next/navigation';
import { api, ApiError, clearAuthTokens } from '@/lib/apiClient';

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
  const [user, setUser] = useState<User | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  
  // Загрузка пользователя
  const fetchCurrentUser = useCallback(async () => {
    try {
      const userData = await api.get<User>('/auth/me');
      setUser(userData);
      setToken('cookie-session');
    } catch (error) {
      if (!(error instanceof ApiError && error.status === 401)) {
        console.error('[Auth] Failed to fetch user:', error);
      }
      clearAuthTokens();
      setToken(null);
      setUser(null);
    } finally {
      setIsLoading(false);
    }
  }, []);
  
  // При загрузке проверяем токен
  useEffect(() => {
    void fetchCurrentUser();
  }, [fetchCurrentUser]);
  
  const login = async (email: string, password: string) => {
    await api.post('/auth/login', {
      body: { email, password },
      noAuth: true,
    });
    await fetchCurrentUser();
  };
  
  const register = async (
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
    await fetchCurrentUser();
  };
  
  const logout = useCallback(() => {
    void api.post('/auth/logout', { noAuth: true }).catch(() => undefined).finally(() => {
      clearAuthTokens();
      setToken(null);
      setUser(null);
      setIsLoading(false);
    });
  }, []);

  useEffect(() => {
    const handleAuthLogout = () => {
      logout();
    };

    window.addEventListener('auth:logout', handleAuthLogout);
    return () => window.removeEventListener('auth:logout', handleAuthLogout);
  }, [logout]);
  
  const updateProfile = async (data: { name?: string; settings?: Record<string, unknown> }) => {
    const updatedUser = await api.put<User>('/auth/me', { body: data });
    
    setUser(updatedUser);
  };
  
  // Обновить данные пользователя (для OAuth callback)
  const refreshUser = useCallback(async () => {
    await fetchCurrentUser();
  }, [fetchCurrentUser]);

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
