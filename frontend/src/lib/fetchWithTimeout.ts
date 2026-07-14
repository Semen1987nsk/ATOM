/**
 * fetch() с дефолтным таймаутом.
 *
 * Зачем: ни `apiClient`, ни `serverApiClient` не ставили таймаут на fetch.
 * Если бэкенд подвисал (например, зависший uvicorn --reload воркер держит
 * сокет открытым, но не отвечает), промис fetch не резолвился НИКОГДА —
 * страница висела на скелетоне вечно, без ошибки и без восстановления.
 * Таймаут превращает «вечное ожидание» в явную ошибку, которую UI может
 * показать и предложить повтор.
 */

export const DEFAULT_TIMEOUT_MS = 15000;

export class TimeoutError extends Error {
  readonly timeoutMs: number;

  constructor(timeoutMs: number) {
    super(`Request timed out after ${timeoutMs}ms`);
    this.name = 'TimeoutError';
    this.timeoutMs = timeoutMs;
  }
}

export async function fetchWithTimeout(
  input: string | URL | Request,
  init: RequestInit = {},
  timeoutMs: number = DEFAULT_TIMEOUT_MS,
  fetchImpl: typeof fetch = fetch,
): Promise<Response> {
  const controller = new AbortController();
  let timedOut = false;
  const timer = setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, timeoutMs);

  // Composing с caller-signal: abort любого из двух прерывает запрос.
  // Без caller-signal обходимся без AbortSignal.any (меньше требований к рантайму).
  const signal = init.signal
    ? AbortSignal.any([init.signal, controller.signal])
    : controller.signal;

  try {
    return await fetchImpl(input, { ...init, signal });
  } catch (err) {
    // Таймаут отличаем от пользовательской отмены: если сработал наш таймер,
    // а caller-signal не аборчен — это таймаут.
    if (timedOut && !init.signal?.aborted) {
      throw new TimeoutError(timeoutMs);
    }
    throw err;
  } finally {
    clearTimeout(timer);
  }
}
