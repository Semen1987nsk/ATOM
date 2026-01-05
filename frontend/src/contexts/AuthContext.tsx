'use client';

import React, { createContext, useContext, useState, useEffect, ReactNode } from 'react';

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
  register: (email: string, password: string, name?: string) => Promise<void>;
  logout: () => void;
  updateProfile: (data: { name?: string; settings?: Record<string, unknown> }) => Promise<void>;
  refreshUser: () => Promise<void>;
}

// ==================== API ====================

function getApiBase(): string {
  if (typeof window !== 'undefined' && window.location.hostname.includes('github.dev')) {
    const codespaceName = window.location.hostname.split('-3000')[0];
    return `https://${codespaceName}-8000.app.github.dev`;
  }
  return process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
}

async function apiRequest<T>(
  endpoint: string, 
  options: RequestInit = {},
  token?: string | null,
  throwOn401: boolean = true
): Promise<T> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...options.headers as Record<string, string>,
  };
  
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }
  
  const response = await fetch(`${getApiBase()}${endpoint}`, {
    ...options,
    headers,
  });
  
  if (!response.ok) {
    // Для 401 можем тихо вернуть null вместо ошибки
    if (response.status === 401 && !throwOn401) {
      return null as T;
    }
    const error = await response.json().catch(() => ({ detail: 'Ошибка сервера' }));
    throw new Error(error.detail || 'Ошибка запроса');
  }
  
  return response.json();
}

// ==================== CONTEXT ====================

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  
  // При загрузке проверяем токен в localStorage
  useEffect(() => {
    const savedToken = localStorage.getItem('auth_token');
    if (savedToken) {
      setToken(savedToken);
      // Проверяем валидность токена
      fetchCurrentUser(savedToken);
    } else {
      setIsLoading(false);
    }
  }, []);
  
  const fetchCurrentUser = async (authToken: string) => {
    try {
      console.log('[Auth] Fetching current user with token:', authToken.substring(0, 20) + '...');
      // throwOn401: false — не выбрасываем ошибку для 401, просто возвращаем null
      const userData = await apiRequest<User | null>('/auth/me', {}, authToken, false);
      if (userData) {
        console.log('[Auth] User data received:', userData);
        setUser(userData);
        setToken(authToken);
      } else {
        console.log('[Auth] Token invalid, clearing');
        localStorage.removeItem('auth_token');
        setToken(null);
        setUser(null);
      }
    } catch (error) {
      console.error('[Auth] Failed to fetch user:', error);
      // Токен невалидный — очищаем
      localStorage.removeItem('auth_token');
      setToken(null);
      setUser(null);
    } finally {
      setIsLoading(false);
    }
  };
  
  const login = async (email: string, password: string) => {
    console.log('[Auth] Attempting login for:', email);
    const response = await apiRequest<{ access_token: string }>('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    });
    
    console.log('[Auth] Login successful, got token');
    localStorage.setItem('auth_token', response.access_token);
    setToken(response.access_token);
    await fetchCurrentUser(response.access_token);
    console.log('[Auth] User fetched successfully');
  };
  
  const register = async (email: string, password: string, name?: string) => {
    const response = await apiRequest<{ access_token: string }>('/auth/register', {
      method: 'POST',
      body: JSON.stringify({ email, password, name }),
    });
    
    localStorage.setItem('auth_token', response.access_token);
    setToken(response.access_token);
    await fetchCurrentUser(response.access_token);
  };
  
  const logout = () => {
    localStorage.removeItem('auth_token');
    setToken(null);
    setUser(null);
  };
  
  const updateProfile = async (data: { name?: string; settings?: Record<string, unknown> }) => {
    if (!token) throw new Error('Не авторизован');
    
    const updatedUser = await apiRequest<User>('/auth/me', {
      method: 'PUT',
      body: JSON.stringify(data),
    }, token);
    
    setUser(updatedUser);
  };
  
  // Обновить данные пользователя (для OAuth callback)
  const refreshUser = async () => {
    const savedToken = localStorage.getItem('auth_token') || localStorage.getItem('token');
    if (savedToken) {
      localStorage.setItem('auth_token', savedToken); // Нормализуем ключ
      localStorage.removeItem('token'); // Удаляем старый ключ от OAuth
      await fetchCurrentUser(savedToken);
    }
  };
  
  // Проверяем OAuth token при загрузке
  useEffect(() => {
    const oauthToken = localStorage.getItem('token');
    if (oauthToken && !token) {
      localStorage.setItem('auth_token', oauthToken);
      localStorage.removeItem('token');
      fetchCurrentUser(oauthToken);
    }
  }, [token]);
  
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

// ==================== HELPER COMPONENTS ====================

export function RequireAuth({ children }: { children: ReactNode }) {
  const { isAuthenticated, isLoading } = useAuth();
  
  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="animate-spin h-8 w-8 border-2 border-accent border-t-transparent rounded-full" />
      </div>
    );
  }
  
  if (!isAuthenticated) {
    // Редирект на логин
    if (typeof window !== 'undefined') {
      window.location.href = '/login';
    }
    return null;
  }
  
  return <>{children}</>;
}
