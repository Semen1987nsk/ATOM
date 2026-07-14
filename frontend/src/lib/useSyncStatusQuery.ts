/**
 * FE-10 — shared poll-хук для /broker/sync-status.
 *
 * Раньше BrokerStatusBadge и SyncStatusIndicator каждый держали свой setInterval
 * на 30с — это два запроса в минуту вместо одного. TanStack Query с одним и тем же
 * queryKey автоматически дедуплицирует in-flight запросы и шерит кеш между компонентами.
 *
 * Backend response (/broker/sync-status) не имеет response_model, в OpenAPI это unknown.
 * Поэтому конкретные shape-типы остаются в компонентах-консьюмерах (BrokerStatusBadge
 * объявляет SyncStatusResponse, SyncStatusIndicator — SyncStatus). Хук просто
 * проксирует generic параметр — компонент специфицирует тип через `useSyncStatusQuery<MyShape>()`.
 */
import { useQuery } from '@tanstack/react-query';
import { api } from './apiClient';

export const syncStatusQueryKey = ['broker', 'sync-status'] as const;

interface UseSyncStatusOptions {
  /** Интервал поллинга, мс. Default 30_000 (раньше каждый компонент держал свой setInterval(30s)). */
  refetchInterval?: number;
  /** Можно отключить — например, на странице, где данные не нужны. */
  enabled?: boolean;
}

export function useSyncStatusQuery<T = unknown>(options?: UseSyncStatusOptions) {
  const refetchInterval = options?.refetchInterval ?? 30_000;
  return useQuery<T, Error>({
    queryKey: syncStatusQueryKey,
    queryFn: () => api.get<T>('/broker/sync-status'),
    refetchInterval,
    // staleTime = интервалу: пока «не пора», TanStack считает данные свежими и
    // отдаёт из кеша мгновенно (важно для второго компонента в header'е).
    staleTime: refetchInterval,
    enabled: options?.enabled ?? true,
  });
}
