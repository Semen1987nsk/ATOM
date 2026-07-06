/**
 * Centralized API Client — единая точка для всех API-запросов.
 *
 * Автоматически:
 * - Использует httpOnly cookie-based auth
 * - Обрабатывает 401 → refresh cookie → retry
 * - Определяет правильный baseUrl (localhost / Codespaces)
 * - Ставит таймаут на каждый запрос (зависший бэкенд → ошибка, не вечный спиннер)
 */

import { fetchWithTimeout, TimeoutError } from './fetchWithTimeout';

function getApiBase(): string {
  if (typeof window !== 'undefined') {
    const { hostname } = window.location;

    // Codespaces: бэкенд живёт на соседнем порту 8000.
    if (hostname.includes('github.dev')) {
      const codespaceName = hostname.split('-3000')[0];
      return `https://${codespaceName}-8000.app.github.dev`;
    }

    // Локальная разработка: фронт на :3000/:3001, бэкенд на :8000 — другой
    // origin, поэтому нужен абсолютный URL.
    if (hostname === 'localhost' || hostname === '127.0.0.1') {
      return process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
    }

    // Прод / любой развёрнутый хост: same-origin. nginx проксирует /api/* на
    // backend (см. nginx/conf.d), поэтому относительный '/api' уходит на origin
    // страницы по её же схеме (https) — домен-агностично (переживает ребренд),
    // без коллизий с фронт-роутами (/blog), с автоматической отправкой
    // httpOnly-cookie. NEXT_PUBLIC_API_URL остаётся override (напр. api.*-хост).
    return process.env.NEXT_PUBLIC_API_URL || '/api';
  }

  // SSR / сборка (нет window): явный env, иначе localhost как последний резерв.
  // Намеренно совпадает с dev-веткой выше — не «дедуплицировать» слиянием с
  // прод-веткой: ветки различны по смыслу (dev/SSR-origin vs same-origin /api).
  return process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
}

const CSRF_COOKIE_NAME = 'atom_csrf_token';
const CSRF_HEADER_NAME = 'X-CSRF-Token';

export function getApiUrl(path: string): string {
  return `${getApiBase()}${path}`;
}

/**
 * ⚠️ Auth-токены живут в httpOnly cookies (см. backend/auth_service.py).
 * Эта функция ТОЛЬКО очищает legacy-ghosts из localStorage, оставшиеся
 * от старой версии приложения. Никогда не добавляйте сюда .setItem(...) —
 * хранение токенов в localStorage = XSS-эксфильтрация в одну строку.
 */
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

      const response = await fetchWithTimeout(`${getApiBase()}/auth/refresh`, {
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
  // PR 26 Scenario #68: X-Request-ID из ответа сервера. Юзер может скопировать
  // в support email/чат, и мы найдём в логах за секунду что произошло.
  requestId?: string;
  // S1-06c: машиночитаемый сигнал "нужен TOTP-код" (backend detail — dict
  // {message, totp_required: true} на POST /auth/login). Робастная замена
  // brittle-match по тексту detail — тот локализуем и может меняться.
  totpRequired?: boolean;

  constructor(status: number, detail: string, requestId?: string, totpRequired?: boolean) {
    super(detail);
    this.name = 'ApiError';
    this.status = status;
    this.detail = detail;
    this.requestId = requestId;
    this.totpRequired = totpRequired;
  }

  /** Сообщение для toast'а с request_id (если есть). */
  toUserMessage(): string {
    if (this.requestId) {
      return `${this.detail} (id: ${this.requestId.slice(0, 8)})`;
    }
    return this.detail;
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

  // Любой запрос с таймаутом: зависший бэкенд → ApiError(408), а не вечное
  // ожидание (страница покажет ошибку/повтор вместо бесконечного скелетона).
  const doFetch = async (): Promise<Response> => {
    try {
      return await fetchWithTimeout(url, fetchOptions);
    } catch (e) {
      if (e instanceof TimeoutError) {
        throw new ApiError(408, 'Сервер не отвечает. Попробуйте ещё раз.');
      }
      throw e;
    }
  };

  let response = await doFetch();

  // Auth-эндпоинты (login/register/refresh) сами «являются» аутентификацией —
  // если они вернули 401, refresh-retry бессмысленен и приводит к ложному
  // "Сессия истекла" вместо реального "Неверный email или пароль".
  const isAuthEndpoint = path.startsWith('/auth/login')
    || path.startsWith('/auth/register')
    || path.startsWith('/auth/refresh');

  if (response.status === 401 && !noAuth && !isAuthEndpoint) {
    const refreshed = await refreshAccessToken();
    if (refreshed) {
      response = await doFetch();
    }
  }

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({ detail: undefined }));
    // S1-06c: detail иногда приходит dict-ом ({message, totp_required} —
    // см. POST /auth/login при 2FA-required), а не строкой. Разворачиваем
    // message для отображения, totp_required — отдельным полем ApiError.
    const rawDetail = errorData.detail;
    // FastAPI 422 кладёт detail массивом [{loc,msg,type}] — иначе toUserMessage
    // интерполирует его как "[object Object]" (S3-20).
    const detailMessageRaw = Array.isArray(rawDetail)
      ? rawDetail.map((d: { msg?: string }) => d?.msg ?? String(d)).join('; ')
      : rawDetail;
    const isDetailObject = detailMessageRaw !== null && typeof detailMessageRaw === 'object';
    const detailMessage = isDetailObject ? detailMessageRaw.message : detailMessageRaw;
    const totpRequired = isDetailObject ? detailMessageRaw.totp_required === true : undefined;

    const detail = detailMessage
      || (response.status === 401
        ? (isAuthEndpoint
            ? 'Неверный email или пароль'
            : 'Сессия истекла. Войдите снова.')
        : `HTTP ${response.status}`);

    // Только для ПОСТ-аутентификационных 401 (а не для login/register) —
    // выкидываем юзера, чистим cookies, оповещаем приложение.
    if (response.status === 401 && !isAuthEndpoint) {
      clearAuthTokens();
      if (typeof window !== 'undefined') {
        window.dispatchEvent(new Event('auth:logout'));
      }
    }

    // PR 26 Scenario #68: пробрасываем X-Request-ID в ApiError для toast'а
    const requestId = response.headers.get('X-Request-ID') ?? undefined;
    throw new ApiError(response.status, detail, requestId, totpRequired);
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
