/**
 * Server-only API клиент для Server Components / Server Actions.
 *
 * Помечен server-only автоматически: импортирует `next/headers`, который
 * выкинет ошибку, если файл случайно попадёт в Client-bundle. Пакет
 * `server-only` не подключён, чтобы не плодить зависимости.
 *
 * Зачем отдельный клиент (вместо `apiClient.ts`):
 *   - apiClient.ts читает `document.cookie` и слушает `window.dispatchEvent`,
 *     чего на сервере просто нет — он сломается на любом Server Component.
 *   - На сервере httpOnly-куки доступны через `next/headers`, и их нужно
 *     явно проброcить в исходящий fetch к FastAPI (Next/Node не делает
 *     этого автоматически — `credentials: 'include'` тут не работает).
 *
 * Что прокидываем:
 *   - `atom_access_token`  — основной access JWT, в httpOnly-cookie
 *   - `atom_refresh_token` — refresh JWT (на случай если бекенд решит
 *     ротировать его прямо при GET — мы его не используем, но не теряем)
 *   - `atom_csrf_token`    — CSRF; для GET/HEAD не нужен, но добавляем
 *     в заголовок для unsafe-методов (post/patch/put/delete)
 *
 * Имена куков синхронизированы с `backend/config.py`:
 *   ACCESS_TOKEN_COOKIE_NAME=atom_access_token
 *   REFRESH_TOKEN_COOKIE_NAME=atom_refresh_token
 *   CSRF_COOKIE_NAME=atom_csrf_token
 */

import { cookies } from 'next/headers';

import { fetchWithTimeout, TimeoutError } from './fetchWithTimeout';

const ACCESS_COOKIE = 'atom_access_token';
const REFRESH_COOKIE = 'atom_refresh_token';
const CSRF_COOKIE = 'atom_csrf_token';
const CSRF_HEADER = 'X-CSRF-Token';

const FORWARDED_COOKIES: readonly string[] = [
  ACCESS_COOKIE,
  REFRESH_COOKIE,
  CSRF_COOKIE,
];

function getBackendBase(): string {
  return process.env.BACKEND_URL ?? 'http://localhost:8000';
}

export class ServerApiError extends Error {
  readonly status: number;
  readonly detail: string;

  constructor(status: number, detail: string) {
    super(`ServerApi ${status}: ${detail}`);
    this.name = 'ServerApiError';
    this.status = status;
    this.detail = detail;
  }
}

type CacheOption = RequestCache;

type NextFetchOptions = {
  revalidate?: number | false;
  tags?: readonly string[];
};

export interface ServerApiOptions {
  /** Стандартный fetch cache mode. По умолчанию `no-store` — это безопасный
   * default для personalized финансовых данных (stats, trades). */
  cache?: CacheOption;
  /** Next.js-специфичные опции кэша (revalidate / tags). Нельзя комбинировать
   * с `cache: 'no-store'`. */
  next?: NextFetchOptions;
  /** Дополнительные заголовки. */
  headers?: Record<string, string>;
  /** Тело запроса (для post/put/patch/delete). */
  body?: unknown;
  /** Если true — вернёт сырой Response. Полезно для скачиваний. */
  rawResponse?: boolean;
  /** AbortSignal — например, чтобы прервать долгий fetch при таймауте. */
  signal?: AbortSignal;
}

async function buildCookieHeader(): Promise<string> {
  // В Next 16 cookies() — async (возвращает Promise<ReadonlyRequestCookies>).
  const cookieStore = await cookies();
  const parts: string[] = [];
  for (const name of FORWARDED_COOKIES) {
    const c = cookieStore.get(name);
    if (c?.value) {
      parts.push(`${name}=${c.value}`);
    }
  }
  return parts.join('; ');
}

async function buildCsrfHeader(): Promise<string | null> {
  const cookieStore = await cookies();
  return cookieStore.get(CSRF_COOKIE)?.value ?? null;
}

function isUnsafeMethod(method: string): boolean {
  return !['GET', 'HEAD', 'OPTIONS', 'TRACE'].includes(method.toUpperCase());
}

async function request<T>(
  method: string,
  path: string,
  options: ServerApiOptions = {},
): Promise<T> {
  const url = `${getBackendBase()}${path}`;
  const cookieHeader = await buildCookieHeader();

  const headers: Record<string, string> = {
    Accept: 'application/json',
    ...options.headers,
  };
  if (cookieHeader) {
    headers.Cookie = cookieHeader;
  }
  if (options.body !== undefined && !(options.body instanceof FormData)) {
    headers['Content-Type'] = 'application/json';
  }
  if (isUnsafeMethod(method)) {
    const csrf = await buildCsrfHeader();
    if (csrf) {
      headers[CSRF_HEADER] = csrf;
    }
  }

  const init: RequestInit & { next?: NextFetchOptions } = {
    method,
    headers,
    signal: options.signal,
  };

  // cache и next.revalidate взаимоисключающие в Next.js. Пользователь
  // должен передать либо одно, либо другое — здесь приоритет у явного next,
  // если он задан, иначе ставим cache (по умолчанию no-store).
  if (options.next !== undefined) {
    init.next = {
      ...(options.next.revalidate !== undefined ? { revalidate: options.next.revalidate } : {}),
      ...(options.next.tags !== undefined ? { tags: [...options.next.tags] } : {}),
    };
  } else {
    init.cache = options.cache ?? 'no-store';
  }

  if (options.body !== undefined) {
    init.body = options.body instanceof FormData ? options.body : JSON.stringify(options.body);
  }

  let response: Response;
  try {
    // Таймаут на SSR-fetch: зависший бэкенд не должен держать рендер страницы
    // открытым бесконечно (иначе Server Component висит вместо ошибки).
    response = await fetchWithTimeout(url, init);
  } catch (e) {
    if (e instanceof TimeoutError) {
      throw new ServerApiError(408, 'Бэкенд не ответил вовремя');
    }
    throw e;
  }

  if (!response.ok) {
    let detail = `HTTP ${response.status}`;
    try {
      const errorJson = (await response.json()) as { detail?: unknown };
      if (typeof errorJson.detail === 'string') {
        detail = errorJson.detail;
      }
    } catch {
      // body не JSON — оставляем дефолтный detail
    }
    throw new ServerApiError(response.status, detail);
  }

  if (options.rawResponse) {
    return response as unknown as T;
  }

  const text = await response.text();
  if (!text) {
    return null as T;
  }
  try {
    return JSON.parse(text) as T;
  } catch {
    return text as unknown as T;
  }
}

export const serverApi = {
  get: <T = unknown>(path: string, options?: ServerApiOptions): Promise<T> =>
    request<T>('GET', path, options),
  post: <T = unknown>(path: string, options?: ServerApiOptions): Promise<T> =>
    request<T>('POST', path, options),
  put: <T = unknown>(path: string, options?: ServerApiOptions): Promise<T> =>
    request<T>('PUT', path, options),
  patch: <T = unknown>(path: string, options?: ServerApiOptions): Promise<T> =>
    request<T>('PATCH', path, options),
  delete: <T = unknown>(path: string, options?: ServerApiOptions): Promise<T> =>
    request<T>('DELETE', path, options),
};

export default serverApi;
