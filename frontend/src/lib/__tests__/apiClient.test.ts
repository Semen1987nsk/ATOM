/**
 * FE-12 (Sprint 5, Batch 8): unit-тесты apiClient.
 *
 * Покрываем критические пути:
 * - ApiError.toUserMessage() с/без requestId;
 * - 408 при таймауте fetchWithTimeout;
 * - 401 → refresh → retry;
 * - 401 на не-auth-endpoint без refresh-куки → logout + dispatchEvent;
 * - CSRF-токен добавляется в headers для POST/PUT/DELETE и НЕ добавляется для GET.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

import { ApiError, getApiUrl } from '../apiClient';

// Каждый тест ремонтирует apiClient, чтобы не делиться `refreshPromise` и
// прочим module-state между сценариями. Иначе один тест с pending-refresh
// "просачивается" в другой.
async function loadApi() {
  vi.resetModules();
  const mod = await import('../apiClient');
  return mod;
}

// Хелпер: фейковый Response c JSON-телом и опциональным X-Request-ID.
function mockJsonResponse(
  status: number,
  body: unknown,
  options: { requestId?: string } = {},
): Response {
  const headers = new Headers({ 'content-type': 'application/json' });
  if (options.requestId) headers.set('X-Request-ID', options.requestId);
  return new Response(JSON.stringify(body), { status, headers });
}

describe('ApiError', () => {
  it('toUserMessage без requestId возвращает только detail', () => {
    const err = new ApiError(500, 'Server error');
    expect(err.toUserMessage()).toBe('Server error');
  });

  it('toUserMessage с requestId дописывает первые 8 символов', () => {
    const err = new ApiError(500, 'Server error', 'req-12345678-tail');
    expect(err.toUserMessage()).toBe('Server error (id: req-1234)');
  });

  it('сохраняет status/detail/requestId в полях', () => {
    const err = new ApiError(404, 'Not found', 'abc-123');
    expect(err.status).toBe(404);
    expect(err.detail).toBe('Not found');
    expect(err.requestId).toBe('abc-123');
  });
});

describe('apiClient — таймаут', () => {
  beforeEach(() => {
    // Полностью изолируем document.cookie между тестами.
    Object.defineProperty(document, 'cookie', {
      configurable: true,
      get: () => '',
      set: () => undefined,
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('зависший fetch конвертируется в ApiError(408)', async () => {
    const { api } = await loadApi();

    // fetchWithTimeout abort'ит запрос через 15s по умолчанию. Имитируем fetch,
    // который реагирует на abort и режектит signal.reason (это и есть путь
    // TimeoutError → ApiError(408)). vi.useFakeTimers() прокручиваем дальше
    // дефолта.
    vi.useFakeTimers();
    const fetchSpy = vi.spyOn(global, 'fetch').mockImplementation(
      (_input, init) =>
        new Promise((_resolve, reject) => {
          init?.signal?.addEventListener(
            'abort',
            () => reject(init.signal!.reason),
            { once: true },
          );
        }),
    );

    const promise = api.get('/test');
    // Ловим неотловленную ошибку, чтобы Node не падал в "unhandledRejection"
    // в момент advance таймеров.
    promise.catch(() => undefined);
    await vi.advanceTimersByTimeAsync(20_000);
    await expect(promise).rejects.toMatchObject({
      name: 'ApiError',
      status: 408,
    });

    expect(fetchSpy).toHaveBeenCalledTimes(1);
    vi.useRealTimers();
  });
});

describe('apiClient — 401 refresh-retry', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('401 на обычном запросе → refresh успешный → retry возвращает данные', async () => {
    const { api } = await loadApi();

    const fetchSpy = vi.spyOn(global, 'fetch');
    // Запрос #1: оригинальный GET /me → 401.
    // Запрос #2: POST /auth/refresh → 200 (refresh успешен).
    // Запрос #3: повтор GET /me → 200 с данными.
    fetchSpy
      .mockResolvedValueOnce(mockJsonResponse(401, { detail: 'token expired' }))
      .mockResolvedValueOnce(mockJsonResponse(200, { ok: true }))
      .mockResolvedValueOnce(mockJsonResponse(200, { id: 42, email: 'u@x' }));

    const result = await api.get<{ id: number; email: string }>('/me');

    expect(result).toEqual({ id: 42, email: 'u@x' });
    expect(fetchSpy).toHaveBeenCalledTimes(3);
    // Второй вызов — refresh.
    expect(fetchSpy.mock.calls[1]?.[0]).toMatch(/\/auth\/refresh$/);
  });

  it('401 на /auth/login НЕ триггерит refresh (auth endpoint), ApiError("Неверный email или пароль")', async () => {
    const { api } = await loadApi();

    const fetchSpy = vi.spyOn(global, 'fetch');
    fetchSpy.mockResolvedValueOnce(mockJsonResponse(401, {}));

    await expect(
      api.post('/auth/login', { body: { email: 'a', password: 'b' }, noAuth: true }),
    ).rejects.toMatchObject({
      name: 'ApiError',
      status: 401,
      detail: 'Неверный email или пароль',
    });

    // Refresh не должен был вызваться.
    expect(fetchSpy).toHaveBeenCalledTimes(1);
  });

  it('401 → refresh упал → выкидываем auth:logout event и ApiError(401)', async () => {
    const { api } = await loadApi();

    const fetchSpy = vi.spyOn(global, 'fetch');
    // Запрос #1: GET /me → 401.
    // Запрос #2: POST /auth/refresh → 401 (refresh-кука истекла).
    // Третьего вызова не должно быть.
    fetchSpy
      .mockResolvedValueOnce(mockJsonResponse(401, { detail: 'expired' }))
      .mockResolvedValueOnce(mockJsonResponse(401, {}));

    const logoutHandler = vi.fn();
    window.addEventListener('auth:logout', logoutHandler);

    try {
      await expect(api.get('/me')).rejects.toMatchObject({
        name: 'ApiError',
        status: 401,
      });
    } finally {
      window.removeEventListener('auth:logout', logoutHandler);
    }

    expect(logoutHandler).toHaveBeenCalledTimes(1);
    expect(fetchSpy).toHaveBeenCalledTimes(2);
  });
});

describe('apiClient — CSRF', () => {
  afterEach(() => {
    vi.restoreAllMocks();
    // Снимаем cookie-override, оставленный отдельными тестами.
    Object.defineProperty(document, 'cookie', {
      configurable: true,
      get: () => '',
      set: () => undefined,
    });
  });

  function stubCookie(value: string) {
    Object.defineProperty(document, 'cookie', {
      configurable: true,
      get: () => value,
      set: () => undefined,
    });
  }

  it('POST добавляет X-CSRF-Token из cookie atom_csrf_token', async () => {
    const { api } = await loadApi();
    stubCookie('atom_csrf_token=token-abc-123; other=foo');

    const fetchSpy = vi.spyOn(global, 'fetch');
    fetchSpy.mockResolvedValueOnce(mockJsonResponse(200, { ok: true }));

    await api.post('/trades', { body: { symbol: 'SBER' } });

    const init = fetchSpy.mock.calls[0]?.[1] as RequestInit | undefined;
    const headers = init?.headers as Record<string, string> | undefined;
    expect(headers?.['X-CSRF-Token']).toBe('token-abc-123');
    // Заодно проверим Content-Type для body=object.
    expect(headers?.['Content-Type']).toBe('application/json');
  });

  it('GET НЕ добавляет X-CSRF-Token (safe-method)', async () => {
    const { api } = await loadApi();
    stubCookie('atom_csrf_token=token-abc-123');

    const fetchSpy = vi.spyOn(global, 'fetch');
    fetchSpy.mockResolvedValueOnce(mockJsonResponse(200, []));

    await api.get('/trades/');

    const init = fetchSpy.mock.calls[0]?.[1] as RequestInit | undefined;
    const headers = init?.headers as Record<string, string> | undefined;
    expect(headers?.['X-CSRF-Token']).toBeUndefined();
  });
});

describe('apiClient — requestId pass-through', () => {
  afterEach(() => vi.restoreAllMocks());

  it('X-Request-ID из 500-ответа попадает в ApiError.requestId', async () => {
    const { api } = await loadApi();

    vi.spyOn(global, 'fetch').mockResolvedValueOnce(
      mockJsonResponse(500, { detail: 'boom' }, { requestId: 'req-xyz-0001' }),
    );

    await expect(api.get('/test')).rejects.toMatchObject({
      status: 500,
      detail: 'boom',
      requestId: 'req-xyz-0001',
    });
  });
});

describe('apiClient — S1-06c: detail dict (2FA) vs detail array (422 validation)', () => {
  afterEach(() => vi.restoreAllMocks());

  it('422 с массивом detail (FastAPI validation errors) НЕ схлопывается в generic "HTTP 422"', async () => {
    const { api } = await loadApi();

    // typeof [] === 'object' — регресс-ловушка: массив не должен матчиться
    // под detail-object ветку (там ожидается {message, totp_required}).
    const validationErrors = [
      { loc: ['body', 'email'], msg: 'field required', type: 'value_error.missing' },
    ];
    vi.spyOn(global, 'fetch').mockResolvedValueOnce(
      mockJsonResponse(422, { detail: validationErrors }),
    );

    let caught: { status?: number; detail?: unknown; totpRequired?: boolean } | undefined;
    try {
      await api.get('/test');
    } catch (e) {
      caught = e as typeof caught;
    }

    expect(caught).toBeDefined();
    expect(caught?.status).toBe(422);
    expect(caught?.detail).not.toBe('HTTP 422');
    // S3-20: массив pydantic-ошибок нормализуется в строку msg-ов (join '; '),
    // а не пробрасывается сырым массивом (→ "[object Object]" при интерполяции).
    expect(caught?.detail).toBe('field required');
    expect(caught?.totpRequired).toBeUndefined();
  });

  it('401 с dict detail ({message, totp_required}) по-прежнему разворачивает totpRequired', async () => {
    const { api } = await loadApi();

    vi.spyOn(global, 'fetch').mockResolvedValueOnce(
      mockJsonResponse(401, {
        detail: { message: 'Требуется код 2FA', totp_required: true },
      }),
    );

    await expect(
      api.post('/auth/login', { body: { email: 'a', password: 'b' }, noAuth: true }),
    ).rejects.toMatchObject({
      status: 401,
      detail: 'Требуется код 2FA',
      totpRequired: true,
    });
  });

  it('обычный строковый detail работает как раньше', async () => {
    const { api } = await loadApi();

    vi.spyOn(global, 'fetch').mockResolvedValueOnce(
      mockJsonResponse(400, { detail: 'Некорректный запрос' }),
    );

    await expect(api.get('/test')).rejects.toMatchObject({
      status: 400,
      detail: 'Некорректный запрос',
      totpRequired: undefined,
    });
  });
});

// Блокер релиза B: getApiBase() решает, куда браузер шлёт ВСЕ запросы (request<T>,
// refreshAccessToken, скриншоты, OAuth). В проде base зашивается на этапе
// `npm run build`; если бы он остался 'http://localhost:8000', весь прод-фронт был
// бы нерабочим. Целевая архитектура — same-origin: nginx проксирует /api/* →
// backend, поэтому в развёрнутом окружении base обязан быть относительным '/api'.
describe('getApiUrl — базовый URL по окружению (blocker B)', () => {
  const realLocation = window.location;

  // Явно задаём поля, которые реально читает getApiBase (hostname), плюс
  // protocol/origin/href — чтобы стаб был самодостаточен, а не хрупкий
  // {...realLocation} (jsdom кладёт члены Location на прототип, спред их не копирует).
  function setHostname(hostname: string): void {
    Object.defineProperty(window, 'location', {
      configurable: true,
      writable: true,
      value: {
        hostname,
        protocol: 'https:',
        origin: `https://${hostname}`,
        href: `https://${hostname}/`,
      },
    });
  }

  afterEach(() => {
    Object.defineProperty(window, 'location', {
      configurable: true,
      writable: true,
      value: realLocation,
    });
    vi.unstubAllEnvs();
  });

  it('в проде (развёрнутый хост, base не задан) строит same-origin /api путь', () => {
    setHostname('polistata.ru');
    vi.stubEnv('NEXT_PUBLIC_API_URL', '');
    expect(getApiUrl('/trades')).toBe('/api/trades');
  });

  it('same-origin работает и для другого prod-домена (домен-агностично)', () => {
    setHostname('empirik.app');
    vi.stubEnv('NEXT_PUBLIC_API_URL', '');
    expect(getApiUrl('/payments/subscription')).toBe('/api/payments/subscription');
  });

  it('в dev (localhost) идёт напрямую на бэкенд :8000 — фронт и бэк на разных origin', () => {
    setHostname('localhost');
    vi.stubEnv('NEXT_PUBLIC_API_URL', '');
    expect(getApiUrl('/trades')).toBe('http://localhost:8000/trades');
  });

  it('127.0.0.1 трактуется как dev, а не как прод', () => {
    setHostname('127.0.0.1');
    vi.stubEnv('NEXT_PUBLIC_API_URL', '');
    expect(getApiUrl('/trades')).toBe('http://localhost:8000/trades');
  });

  it('NEXT_PUBLIC_API_URL переопределяет base в проде (напр. отдельный api-хост)', () => {
    setHostname('polistata.ru');
    vi.stubEnv('NEXT_PUBLIC_API_URL', 'https://api.polistata.ru');
    expect(getApiUrl('/trades')).toBe('https://api.polistata.ru/trades');
  });

  it('NEXT_PUBLIC_API_URL переопределяет base и на localhost (та же env-ветка)', () => {
    setHostname('localhost');
    vi.stubEnv('NEXT_PUBLIC_API_URL', 'http://localhost:9000');
    expect(getApiUrl('/trades')).toBe('http://localhost:9000/trades');
  });

  it('Codespaces маппит порт 3000→8000 (регресс не сломан)', () => {
    setHostname('friendly-space-3000.app.github.dev');
    vi.stubEnv('NEXT_PUBLIC_API_URL', '');
    expect(getApiUrl('/trades')).toBe('https://friendly-space-8000.app.github.dev/trades');
  });
});
