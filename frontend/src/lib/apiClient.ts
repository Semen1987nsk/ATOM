/**
 * Centralized API Client — единая точка для всех API-запросов.
 *
 * Автоматически:
 * - Использует httpOnly cookie-based auth
 * - Обрабатывает 401 → refresh cookie → retry
 * - Определяет правильный baseUrl (localhost / Codespaces)
 */

function getApiBase(): string {
  if (typeof window !== 'undefined' && window.location.hostname.includes('github.dev')) {
    const codespaceName = window.location.hostname.split('-3000')[0];
    return `https://${codespaceName}-8000.app.github.dev`;
  }
  return process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
}

const CSRF_COOKIE_NAME = 'atom_csrf_token';
const CSRF_HEADER_NAME = 'X-CSRF-Token';

export function getApiUrl(path: string): string {
  return `${getApiBase()}${path}`;
}

export function clearAuthTokens() {
  if (typeof window === 'undefined') return;
  localStorage.removeItem('auth_token');
  localStorage.removeItem('refresh_token');
  localStorage.removeItem('token_expiry');
  localStorage.removeItem('token');
}

function getCookie(name: string): string | null {
  if (typeof document === 'undefined') return null;

  const cookie = document.cookie
    .split('; ')
    .find((item) => item.startsWith(`${name}=`));

  if (!cookie) return null;
  return decodeURIComponent(cookie.split('=').slice(1).join('='));
}

function getCsrfToken(): string | null {
  return getCookie(CSRF_COOKIE_NAME);
}

function isUnsafeMethod(method: string): boolean {
  return !['GET', 'HEAD', 'OPTIONS', 'TRACE'].includes(method.toUpperCase());
}

let refreshPromise: Promise<boolean> | null = null;

export async function refreshAccessToken(): Promise<boolean> {
  if (refreshPromise) return refreshPromise;

  refreshPromise = (async () => {
    try {
      const headers: Record<string, string> = {};
      const csrfToken = getCsrfToken();
      if (csrfToken) {
        headers[CSRF_HEADER_NAME] = csrfToken;
      }

      const response = await fetch(`${getApiBase()}/auth/refresh`, {
        method: 'POST',
        credentials: 'include',
        headers,
      });

      if (!response.ok) {
        clearAuthTokens();
        return false;
      }

      return true;
    } catch {
      clearAuthTokens();
      return false;
    } finally {
      refreshPromise = null;
    }
  })();

  return refreshPromise;
}

export interface ApiRequestOptions {
  body?: unknown;
  headers?: Record<string, string>;
  params?: Record<string, string | number | boolean | undefined | null>;
  noAuth?: boolean;
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

  const headers: Record<string, string> = { ...extraHeaders };
  if (body && !(body instanceof FormData)) {
    headers['Content-Type'] = 'application/json';
  }

  if (isUnsafeMethod(method)) {
    const csrfToken = getCsrfToken();
    if (csrfToken) {
      headers[CSRF_HEADER_NAME] = csrfToken;
    }
  }

  const fetchOptions: RequestInit = {
    method,
    headers,
    signal,
    credentials: 'include',
  };

  if (body !== undefined) {
    fetchOptions.body = body instanceof FormData ? body : JSON.stringify(body);
  }

  let response = await fetch(url, fetchOptions);

  if (response.status === 401 && !noAuth) {
    const refreshed = await refreshAccessToken();
    if (refreshed) {
      response = await fetch(url, fetchOptions);
    }
  }

  if (response.status === 401) {
    clearAuthTokens();
    if (typeof window !== 'undefined') {
      window.dispatchEvent(new Event('auth:logout'));
    }
    throw new ApiError(401, 'Сессия истекла. Войдите снова.');
  }

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({ detail: 'Ошибка сервера' }));
    throw new ApiError(response.status, errorData.detail || `HTTP ${response.status}`);
  }

  if (rawResponse) return response as unknown as T;

  const text = await response.text();
  if (!text) return null as T;
  try {
    return JSON.parse(text) as T;
  } catch {
    return text as unknown as T;
  }
}

export const api = {
  get: <T = unknown>(path: string, options?: ApiRequestOptions) => request<T>('GET', path, options),
  post: <T = unknown>(path: string, options?: ApiRequestOptions) => request<T>('POST', path, options),
  put: <T = unknown>(path: string, options?: ApiRequestOptions) => request<T>('PUT', path, options),
  patch: <T = unknown>(path: string, options?: ApiRequestOptions) => request<T>('PATCH', path, options),
  delete: <T = unknown>(path: string, options?: ApiRequestOptions) => request<T>('DELETE', path, options),
  upload: <T = unknown>(path: string, formData: FormData, options?: Omit<ApiRequestOptions, 'body'>) =>
    request<T>('POST', path, { ...options, body: formData }),
};

export default api;
