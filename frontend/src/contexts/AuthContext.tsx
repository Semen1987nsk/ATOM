'use client';

import React, { createContext, useContext, useState, useEffect, useCallback, useRef, ReactNode } from 'react';

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

interface TokenPair {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
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

// ==================== STORAGE KEYS ====================

const ACCESS_TOKEN_KEY = 'auth_token';
const REFRESH_TOKEN_KEY = 'refresh_token';
const TOKEN_EXPIRY_KEY = 'token_expiry';

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

// ==================== TOKEN HELPERS ====================

function saveTokens(tokens: TokenPair) {
  localStorage.setItem(ACCESS_TOKEN_KEY, tokens.access_token);
  localStorage.setItem(REFRESH_TOKEN_KEY, tokens.refresh_token);
  
  // Сохраняем время истечения (с запасом 1 минута)
  const expiryTime = Date.now() + (tokens.expires_in - 60) * 1000;
  localStorage.setItem(TOKEN_EXPIRY_KEY, expiryTime.toString());
}

function clearTokens() {
  localStorage.removeItem(ACCESS_TOKEN_KEY);
  localStorage.removeItem(REFRESH_TOKEN_KEY);
  localStorage.removeItem(TOKEN_EXPIRY_KEY);
  // Также очищаем старый ключ от OAuth
  localStorage.removeItem('token');
}

function getAccessToken(): string | null {
  return localStorage.getItem(ACCESS_TOKEN_KEY);
}

function getRefreshToken(): string | null {
  return localStorage.getItem(REFRESH_TOKEN_KEY);
}

function isTokenExpired(): boolean {
  const expiry = localStorage.getItem(TOKEN_EXPIRY_KEY);
  if (!expiry) return true;
  return Date.now() > parseInt(expiry, 10);
}

// ==================== CONTEXT ====================

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  
  // Ref для предотвращения множественных refresh запросов
  const isRefreshing = useRef(false);
  const refreshPromise = useRef<Promise<string | null> | null>(null);
  
  // Функция обновления токенов
  const refreshTokens = useCallback(async (): Promise<string | null> => {
    // Если уже идёт обновление, ждём его завершения
    if (isRefreshing.current && refreshPromise.current) {
      return refreshPromise.current;
    }
    
    const refreshToken = getRefreshToken();
    if (!refreshToken) {
      return null;
    }
    
    isRefreshing.current = true;
    
    refreshPromise.current = (async () => {
      try {
        console.log('[Auth] Refreshing tokens...');
        const response = await apiRequest<TokenPair>('/auth/refresh', {
          method: 'POST',
          body: JSON.stringify({ refresh_token: refreshToken }),
        });
        
        saveTokens(response);
        setToken(response.access_token);
        console.log('[Auth] Tokens refreshed successfully');
        return response.access_token;
      } catch (error) {
        console.error('[Auth] Failed to refresh tokens:', error);
        clearTokens();
        setToken(null);
        setUser(null);
        return null;
      } finally {
        isRefreshing.current = false;
        refreshPromise.current = null;
      }
    })();
    
    return refreshPromise.current;
  }, []);
  
  // Функция для получения валидного токена
  const getValidToken = useCallback(async (): Promise<string | null> => {
    const accessToken = getAccessToken();
    
    if (!accessToken) {
      return null;
    }
    
    // Если токен истёк, обновляем
    if (isTokenExpired()) {
      return refreshTokens();
    }
    
    return accessToken;
  }, [refreshTokens]);
  
  // Загрузка пользователя
  const fetchCurrentUser = useCallback(async (authToken: string) => {
    try {
      console.log('[Auth] Fetching current user...');
      const userData = await apiRequest<User | null>('/auth/me', {}, authToken, false);
      
      if (userData) {
        console.log('[Auth] User data received:', userData.email);
        setUser(userData);
        setToken(authToken);
      } else {
        // Токен невалидный, пробуем обновить
        const newToken = await refreshTokens();
        if (newToken) {
          const retryUserData = await apiRequest<User | null>('/auth/me', {}, newToken, false);
          if (retryUserData) {
            setUser(retryUserData);
            return;
          }
        }
        // Если всё равно не получилось — очищаем
        clearTokens();
        setToken(null);
        setUser(null);
      }
    } catch (error) {
      console.error('[Auth] Failed to fetch user:', error);
      clearTokens();
      setToken(null);
      setUser(null);
    } finally {
      setIsLoading(false);
    }
  }, [refreshTokens]);
  
  // При загрузке проверяем токен
  useEffect(() => {
    const initAuth = async () => {
      const accessToken = await getValidToken();
      if (accessToken) {
        await fetchCurrentUser(accessToken);
      } else {
        setIsLoading(false);
      }
    };
    
    initAuth();
  }, [fetchCurrentUser, getValidToken]);
  
  // Автоматическое обновление токена за 1 минуту до истечения
  useEffect(() => {
    if (!token) return;
    
    const checkAndRefresh = () => {
      const expiry = localStorage.getItem(TOKEN_EXPIRY_KEY);
      if (!expiry) return;
      
      const timeLeft = parseInt(expiry, 10) - Date.now();
      
      // Обновляем за 1 минуту до истечения
      if (timeLeft > 0 && timeLeft < 60 * 1000) {
        refreshTokens();
      }
    };
    
    // Проверяем каждые 30 секунд
    const interval = setInterval(checkAndRefresh, 30 * 1000);
    
    return () => clearInterval(interval);
  }, [token, refreshTokens]);
  
  const login = async (email: string, password: string) => {
    console.log('[Auth] Attempting login for:', email);
    const response = await apiRequest<TokenPair>('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    });
    
    console.log('[Auth] Login successful');
    saveTokens(response);
    setToken(response.access_token);
    await fetchCurrentUser(response.access_token);
  };
  
  const register = async (email: string, password: string, name?: string) => {
    console.log('[Auth] Attempting registration for:', email);
    const response = await apiRequest<TokenPair>('/auth/register', {
      method: 'POST',
      body: JSON.stringify({ email, password, name }),
    });
    
    console.log('[Auth] Registration successful');
    saveTokens(response);
    setToken(response.access_token);
    await fetchCurrentUser(response.access_token);
  };
  
  const logout = () => {
    console.log('[Auth] Logging out');
    clearTokens();
    setToken(null);
    setUser(null);
  };
  
  const updateProfile = async (data: { name?: string; settings?: Record<string, unknown> }) => {
    const validToken = await getValidToken();
    if (!validToken) throw new Error('Не авторизован');
    
    const updatedUser = await apiRequest<User>('/auth/me', {
      method: 'PUT',
      body: JSON.stringify(data),
    }, validToken);
    
    setUser(updatedUser);
  };
  
  // Обновить данные пользователя (для OAuth callback)
  const refreshUser = async () => {
    // Проверяем старый ключ от OAuth
    const oauthToken = localStorage.getItem('token');
    if (oauthToken) {
      // OAuth возвращает только access_token, сохраняем его
      localStorage.setItem(ACCESS_TOKEN_KEY, oauthToken);
      localStorage.removeItem('token');
      await fetchCurrentUser(oauthToken);
      return;
    }
    
    const validToken = await getValidToken();
    if (validToken) {
      await fetchCurrentUser(validToken);
    }
  };
  
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
