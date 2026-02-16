/**
 * Centralized API Client — единая точка для всех API-запросов.
 * 
 * Автоматически:
 * - Добавляет Bearer token из localStorage
 * - Обрабатывает 401 → refresh → retry
 * - Определяет правильный baseUrl (localhost / Codespaces)
 * - Логирует ошибки
 * 
 * Использование:
 *   import { api } from '@/lib/apiClient';
 *   const trades = await api.get<Trade[]>('/trades/');
 *   await api.post('/trades/', { body: tradeData });
 *   await api.patch(`/trades/${id}`, { body: updateData });
 *   await api.delete(`/trades/${id}`);
 */

// ==================== CONFIG ====================

const ACCESS_TOKEN_KEY = 'auth_token';
const REFRESH_TOKEN_KEY = 'refresh_token';
const TOKEN_EXPIRY_KEY = 'token_expiry';

function getApiBase(): string {
  if (typeof window !== 'undefined' && window.location.hostname.includes('github.dev')) {
    const codespaceName = window.location.hostname.split('-3000')[0];
    return `https://${codespaceName}-8000.app.github.dev`;
  }
  return process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
}

/** Public getter for components that need the base URL */
export function getApiUrl(path: string): string {
  return `${getApiBase()}${path}`;
}

// ==================== TOKEN MANAGEMENT ====================

function getAccessToken(): string | null {
  if (typeof window === 'undefined') return null;
  return localStorage.getItem(ACCESS_TOKEN_KEY);
}

function getRefreshToken(): string | null {
  if (typeof window === 'undefined') return null;
  return localStorage.getItem(REFRESH_TOKEN_KEY);
}

function isTokenExpired(): boolean {
  if (typeof window === 'undefined') return true;
  const expiry = localStorage.getItem(TOKEN_EXPIRY_KEY);
  if (!expiry) return true;
  return Date.now() > parseInt(expiry, 10);
}

function saveTokens(data: { access_token: string; refresh_token: string; expires_in: number }) {
  localStorage.setItem(ACCESS_TOKEN_KEY, data.access_token);
  localStorage.setItem(REFRESH_TOKEN_KEY, data.refresh_token);
  const expiryTime = Date.now() + (data.expires_in - 60) * 1000;
  localStorage.setItem(TOKEN_EXPIRY_KEY, expiryTime.toString());
}

function clearTokens() {
  localStorage.removeItem(ACCESS_TOKEN_KEY);
  localStorage.removeItem(REFRESH_TOKEN_KEY);
  localStorage.removeItem(TOKEN_EXPIRY_KEY);
  localStorage.removeItem('token'); // legacy OAuth key
}

// ==================== REFRESH LOGIC ====================

let refreshPromise: Promise<string | null> | null = null;

async function refreshAccessToken(): Promise<string | null> {
  // Deduplicate concurrent refresh calls
  if (refreshPromise) return refreshPromise;

  refreshPromise = (async () => {
    const refreshToken = getRefreshToken();
    if (!refreshToken) return null;

    try {
      const response = await fetch(`${getApiBase()}/auth/refresh`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token: refreshToken }),
      });

      if (!response.ok) {
        clearTokens();
        return null;
      }

      const tokens = await response.json();
      saveTokens(tokens);
      return tokens.access_token as string;
    } catch {
      clearTokens();
      return null;
    } finally {
      refreshPromise = null;
    }
  })();

  return refreshPromise;
}

async function getValidToken(): Promise<string | null> {
  const token = getAccessToken();
  if (!token) return null;
  if (isTokenExpired()) return refreshAccessToken();
  return token;
}

// ==================== CORE FETCH ====================

export interface ApiRequestOptions {
  body?: unknown;
  headers?: Record<string, string>;
  params?: Record<string, string | number | boolean | undefined | null>;
  /** Skip auth header (for public endpoints like login/register) */
  noAuth?: boolean;
  /** Don't parse response as JSON */
  rawResponse?: boolean;
  signal?: AbortSignal;
}

export class ApiError extends Error {
  status: number;
  detail: string;

  constructor(status: number, detail: string) {
    super(detail);
    this.name = 'ApiError';
    this.status = status;
    this.detail = detail;
  }
}

async function request<T>(
  method: string,
  path: string,
  options: ApiRequestOptions = {}
): Promise<T> {
  const { body, headers: extraHeaders, params, noAuth, rawResponse, signal } = options;

  // Build URL with query params
  let url = `${getApiBase()}${path}`;
  if (params) {
    const searchParams = new URLSearchParams();
    for (const [key, value] of Object.entries(params)) {
      if (value !== undefined && value !== null) {
        searchParams.append(key, String(value));
      }
    }
    const qs = searchParams.toString();
    if (qs) url += `?${qs}`;
  }

  // Build headers
  const headers: Record<string, string> = { ...extraHeaders };

  if (body && !(body instanceof FormData)) {
    headers['Content-Type'] = 'application/json';
  }

  // Auto-attach auth token
  if (!noAuth) {
    const token = await getValidToken();
    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }
  }

  const fetchOptions: RequestInit = {
    method,
    headers,
    signal,
  };

  if (body !== undefined) {
    fetchOptions.body = body instanceof FormData ? body : JSON.stringify(body);
  }

  let response = await fetch(url, fetchOptions);

  // Auto-retry on 401 (token may have expired between check and request)
  if (response.status === 401 && !noAuth) {
    const newToken = await refreshAccessToken();
    if (newToken) {
      headers['Authorization'] = `Bearer ${newToken}`;
      response = await fetch(url, { ...fetchOptions, headers });
    }
  }

  // Handle still-401 after refresh
  if (response.status === 401) {
    clearTokens();
    // Dispatch event so AuthContext can react and redirect to login
    if (typeof window !== 'undefined') {
      window.dispatchEvent(new Event('auth:logout'));
    }
    // Return a never-resolving promise instead of throwing.
    // The auth:logout event handles the redirect — throwing would cause
    // unhandled error overlays in every component with pending requests.
    return new Promise<T>(() => {});
  }

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({ detail: 'Ошибка сервера' }));
    throw new ApiError(response.status, errorData.detail || `HTTP ${response.status}`);
  }

  if (rawResponse) return response as unknown as T;
  
  // Handle empty responses (204 No Content, etc.)
  const text = await response.text();
  if (!text) return undefined as unknown as T;
  return JSON.parse(text) as T;
}

// ==================== PUBLIC API ====================

export const api = {
  get: <T = unknown>(path: string, options?: ApiRequestOptions) =>
    request<T>('GET', path, options),

  post: <T = unknown>(path: string, options?: ApiRequestOptions) =>
    request<T>('POST', path, options),

  put: <T = unknown>(path: string, options?: ApiRequestOptions) =>
    request<T>('PUT', path, options),

  patch: <T = unknown>(path: string, options?: ApiRequestOptions) =>
    request<T>('PATCH', path, options),

  delete: <T = unknown>(path: string, options?: ApiRequestOptions) =>
    request<T>('DELETE', path, options),

  /** Upload a file (multipart/form-data) — do NOT set Content-Type manually */
  upload: <T = unknown>(path: string, formData: FormData, options?: Omit<ApiRequestOptions, 'body'>) =>
    request<T>('POST', path, { ...options, body: formData }),
};

export default api;
