'use client';

import { useState, useEffect } from 'react';
import { getApiUrl } from '@/lib/apiClient';

interface OAuthProvider {
  id: string;
  name: string;
}

interface OAuthUser {
  id: number;
  email: string;
  name?: string | null;
  oauth_provider?: string | null;
}

interface OAuthCallbackResponse {
  user: OAuthUser;
}

// Иконки провайдеров
const ProviderIcon = ({ provider }: { provider: string }) => {
  switch (provider) {
    case 'google':
      return (
        <svg viewBox="0 0 24 24" className="w-5 h-5" fill="currentColor">
          <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" fill="#4285F4"/>
          <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853"/>
          <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05"/>
          <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335"/>
        </svg>
      );
    case 'yandex':
      return (
        <svg viewBox="0 0 24 24" className="w-5 h-5" fill="currentColor">
          <path d="M2 12C2 6.48 6.48 2 12 2s10 4.48 10 10-4.48 10-10 10S2 17.52 2 12zm11.5-7h-2.24c-2.44 0-4.24 1.68-4.24 4.32 0 1.92 1.04 3.28 2.88 4.4L6.64 19h2.64l2.96-5.04v5.04h2.26V5z" fill="#FC3F1D"/>
        </svg>
      );
    case 'sber':
      return (
        <svg viewBox="0 0 24 24" className="w-5 h-5" fill="currentColor">
          <circle cx="12" cy="12" r="11" fill="#21A038"/>
          <path d="M12 4.5c-4.14 0-7.5 3.36-7.5 7.5 0 4.14 3.36 7.5 7.5 7.5 4.14 0 7.5-3.36 7.5-7.5" stroke="white" strokeWidth="1.5" fill="none"/>
          <path d="M12 7v5l3.5 2" stroke="white" strokeWidth="1.5" fill="none" strokeLinecap="round"/>
        </svg>
      );
    case 'tinkoff':
      return (
        <svg viewBox="0 0 24 24" className="w-5 h-5" fill="currentColor">
          <rect width="24" height="24" rx="4" fill="#FFDD2D"/>
          <path d="M7 8h10v2H7V8zm0 3h10v2H7v-2zm0 3h7v2H7v-2z" fill="#333"/>
        </svg>
      );
    default:
      return null;
  }
};

// Цвета кнопок
const getProviderStyles = (provider: string) => {
  switch (provider) {
    case 'google':
      return 'bg-white hover:bg-gray-50 text-gray-700 border border-gray-300';
    case 'yandex':
      return 'bg-[#FC3F1D] hover:bg-[#e03515] text-white';
    case 'sber':
      return 'bg-[#21A038] hover:bg-[#1a8a2e] text-white';
    case 'tinkoff':
      return 'bg-[#FFDD2D] hover:bg-[#f5d426] text-black';
    default:
      return 'bg-secondary hover:bg-secondary/80 text-foreground';
  }
};

interface OAuthButtonsProps {
  onSuccess?: (user: OAuthUser) => void;
  onError?: (error: string) => void;
}

export function OAuthButtons({ onSuccess, onError }: OAuthButtonsProps) {
  const [providers, setProviders] = useState<OAuthProvider[]>([]);
  const [loading, setLoading] = useState<string | null>(null);

  useEffect(() => {
    // Получаем список доступных провайдеров
    fetch(getApiUrl('/auth/oauth/providers'), { credentials: 'include' })
      .then(res => res.json())
      .then(data => setProviders(data))
      .catch(() => setProviders([]));
  }, []);

  useEffect(() => {
    // Обрабатываем OAuth callback
    const handleOAuthCallback = async () => {
      const params = new URLSearchParams(window.location.search);
      const code = params.get('code');
      const state = params.get('state');
      const provider = localStorage.getItem('oauth_provider');
      
      if (code && state && provider) {
        setLoading(provider);
        localStorage.removeItem('oauth_provider');
        
        try {
          const redirectUri = `${window.location.origin}${window.location.pathname}`;
          const response = await fetch(
            getApiUrl(`/auth/oauth/${provider}/callback?code=${code}&state=${state}&redirect_uri=${encodeURIComponent(redirectUri)}`),
            { method: 'POST', credentials: 'include' }
          );
          
          if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Ошибка авторизации');
          }
          
          const data: OAuthCallbackResponse = await response.json();
          window.dispatchEvent(new Event('auth:login'));
          
          // Очищаем URL от параметров OAuth
          window.history.replaceState({}, '', window.location.pathname);
          
          onSuccess?.(data.user);
        } catch (err) {
          onError?.(err instanceof Error ? err.message : 'Ошибка авторизации');
        } finally {
          setLoading(null);
        }
      }
    };
    
    handleOAuthCallback();
  }, [onSuccess, onError]);

  const handleOAuthLogin = async (providerId: string) => {
    setLoading(providerId);
    
    try {
      const redirectUri = `${window.location.origin}${window.location.pathname}`;
      const response = await fetch(
        getApiUrl(`/auth/oauth/${providerId}/authorize?redirect_uri=${encodeURIComponent(redirectUri)}`),
        { credentials: 'include' }
      );
      
      if (!response.ok) {
        throw new Error('Провайдер недоступен');
      }
      
      const data = await response.json();
      
      // Сохраняем провайдера для callback
      localStorage.setItem('oauth_provider', providerId);
      
      // Редиректим на страницу авторизации провайдера
      window.location.href = data.authorize_url;
    } catch (err) {
      setLoading(null);
      onError?.(err instanceof Error ? err.message : 'Ошибка');
    }
  };

  if (providers.length === 0) {
    return null;
  }

  return (
    <div className="space-y-3">
      <div className="relative">
        <div className="absolute inset-0 flex items-center">
          <div className="w-full border-t border-white/10" />
        </div>
        <div className="relative flex justify-center text-xs uppercase">
          <span className="px-2 bg-card text-muted-foreground">или войти через</span>
        </div>
      </div>
      
      <div className="grid gap-2">
        {providers.map((provider) => (
          <button
            key={provider.id}
            onClick={() => handleOAuthLogin(provider.id)}
            disabled={loading !== null}
            className={`w-full py-3 px-4 rounded-lg font-medium flex items-center justify-center gap-3 
                       transition-all disabled:opacity-50 disabled:cursor-not-allowed
                       ${getProviderStyles(provider.id)}`}
          >
            {loading === provider.id ? (
              <div className="w-5 h-5 border-2 border-current border-t-transparent rounded-full animate-spin" />
            ) : (
              <ProviderIcon provider={provider.id} />
            )}
            <span>Войти через {provider.name}</span>
          </button>
        ))}
      </div>
    </div>
  );
}
