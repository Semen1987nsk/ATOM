/**
 * useApiQuery — минимальный хук-обёртка над apiClient с AbortController,
 * deduplication, и стандартными loading/error состояниями.
 *
 * Создан как drop-in вместо ручных useEffect+useState+fetch паттернов
 * в page.tsx и history/page.tsx. Полностью идемпотентен: если deps не
 * изменились — повторный запрос не отправится.
 *
 * Ограничения (осознанно):
 * - Без кеша между компонентами (для этого нужен TanStack Query / SWR).
 * - Без retry / staleTime.
 *
 * Когда не использовать: для мутаций (POST/PATCH/DELETE) — там ручной api.post().
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { ApiError, api, ApiRequestOptions } from './apiClient';

export interface UseApiQueryState<T> {
  data: T | null;
  isLoading: boolean;
  error: ApiError | null;
  refetch: () => void;
}

export interface UseApiQueryOptions extends Omit<ApiRequestOptions, 'signal'> {
  /** Если false — запрос не запускается. Используй для условных запросов. */
  enabled?: boolean;
}

/**
 * Загружает данные с GET-эндпоинта, автоматически отменяя in-flight
 * запрос при unmount или смене path/deps.
 *
 * @param path API-путь (без baseUrl)
 * @param deps массив зависимостей в стиле useEffect — при их смене запрос перезапускается
 * @param options заголовки, query-параметры, enabled-флаг
 *
 * @example
 *   const { data, isLoading, error, refetch } = useApiQuery<Trade[]>(
 *     '/trades/',
 *     [accountId],
 *     { params: { account_id: accountId } }
 *   );
 */
export function useApiQuery<T>(
  path: string,
  deps: React.DependencyList = [],
  options: UseApiQueryOptions = {}
): UseApiQueryState<T> {
  const { enabled = true, ...requestOptions } = options;
  const [data, setData] = useState<T | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(enabled);
  const [error, setError] = useState<ApiError | null>(null);
  const [refetchTick, setRefetchTick] = useState(0);

  // Стабильная ссылка на options через ref — иначе deps превращается в нестабильные.
  const optionsRef = useRef(requestOptions);
  optionsRef.current = requestOptions;

  const refetch = useCallback(() => setRefetchTick((t) => t + 1), []);

  useEffect(() => {
    if (!enabled) {
      setIsLoading(false);
      return;
    }

    const controller = new AbortController();
    setIsLoading(true);
    setError(null);

    api
      .get<T>(path, { ...optionsRef.current, signal: controller.signal })
      .then((result) => {
        // Пропускаем результат, если запрос был отменён до завершения.
        if (controller.signal.aborted) return;
        setData(result);
        setIsLoading(false);
      })
      .catch((err: unknown) => {
        // AbortError — нормальный путь cleanup, не ошибка для UI.
        if (controller.signal.aborted) return;
        if (err instanceof Error && err.name === 'AbortError') return;
        const apiErr =
          err instanceof ApiError
            ? err
            : new ApiError(0, err instanceof Error ? err.message : 'Network error');
        setError(apiErr);
        setIsLoading(false);
      });

    return () => {
      // Cleanup: отменяем in-flight запрос. Защищает от race conditions,
      // когда юзер быстро меняет фильтры и старый ответ перезаписывает новый.
      controller.abort();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path, enabled, refetchTick, ...deps]);

  return { data, isLoading, error, refetch };
}
