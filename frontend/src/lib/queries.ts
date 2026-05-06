/**
 * Готовые query/mutation хуки для основных endpoint'ов.
 *
 * Используй эти хуки в страницах вместо ручного `useEffect+useState+fetch`:
 * автоматическое кеширование между компонентами, dedup одинаковых запросов
 * в одном renderе, автоматический retry, abort при unmount.
 *
 * Пример:
 *   const { data: trades, isLoading } = useTradesQuery({ limit: 100 });
 *   const createTrade = useCreateTradeMutation();
 *   await createTrade.mutateAsync({ symbol: "SBER", ... });
 *
 * Migration roadmap (не делать всё сразу):
 *   1. Сначала перевести `/stats/` (самый дорогой endpoint).
 *   2. Потом `/trades/`.
 *   3. Замыкающие: `/auth/me`, `/blog/...`.
 */
import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseMutationOptions,
  type UseQueryOptions,
} from "@tanstack/react-query";

import { api } from "./apiClient";
import type {
  ImportResultResponse,
  Trade,
  TradeClose,
  TradeCreate,
  TradeUpdate,
  UserResponse,
} from "@/types/api";

// ──────────────────────────────────────────────
//  Query keys — иерархические, для точечной инвалидации
// ──────────────────────────────────────────────

export const queryKeys = {
  trades: {
    all: ["trades"] as const,
    list: (params?: Record<string, unknown>) => ["trades", "list", params] as const,
    detail: (id: number) => ["trades", "detail", id] as const,
    openPositions: () => ["trades", "open"] as const,
  },
  stats: {
    all: ["stats"] as const,
    summary: (params?: Record<string, unknown>) => ["stats", "summary", params] as const,
  },
  auth: {
    me: () => ["auth", "me"] as const,
  },
} as const;

// ──────────────────────────────────────────────
//  Trades
// ──────────────────────────────────────────────

interface TradesListParams {
  skip?: number;
  limit?: number;
}

export function useTradesQuery(
  params?: TradesListParams,
  options?: Omit<UseQueryOptions<Trade[]>, "queryKey" | "queryFn">,
) {
  return useQuery<Trade[]>({
    queryKey: queryKeys.trades.list(params as Record<string, unknown>),
    queryFn: () => api.get<Trade[]>("/trades/", { params: params as Record<string, string | number> }),
    ...options,
  });
}

export function useCreateTradeMutation(
  options?: UseMutationOptions<Trade, unknown, TradeCreate>,
) {
  const qc = useQueryClient();
  return useMutation<Trade, unknown, TradeCreate>({
    mutationFn: (body) => api.post<Trade>("/trades/", { body }),
    onSuccess: (...args) => {
      qc.invalidateQueries({ queryKey: queryKeys.trades.all });
      qc.invalidateQueries({ queryKey: queryKeys.stats.all });
      options?.onSuccess?.(...args);
    },
    ...options,
  });
}

export function useUpdateTradeMutation(
  options?: UseMutationOptions<Trade, unknown, { id: number; body: TradeUpdate }>,
) {
  const qc = useQueryClient();
  return useMutation<Trade, unknown, { id: number; body: TradeUpdate }>({
    mutationFn: ({ id, body }) => api.patch<Trade>(`/trades/${id}`, { body }),
    onSuccess: (...args) => {
      qc.invalidateQueries({ queryKey: queryKeys.trades.all });
      qc.invalidateQueries({ queryKey: queryKeys.stats.all });
      options?.onSuccess?.(...args);
    },
    ...options,
  });
}

export function useDeleteTradeMutation(
  options?: UseMutationOptions<{ message: string }, unknown, number>,
) {
  const qc = useQueryClient();
  return useMutation<{ message: string }, unknown, number>({
    mutationFn: (id) => api.delete<{ message: string }>(`/trades/${id}`),
    onSuccess: (...args) => {
      const [, id] = args;
      qc.invalidateQueries({ queryKey: queryKeys.trades.all });
      qc.invalidateQueries({ queryKey: queryKeys.stats.all });
      qc.removeQueries({ queryKey: queryKeys.trades.detail(id) });
      options?.onSuccess?.(...args);
    },
    ...options,
  });
}

export function useCloseTradeMutation(
  options?: UseMutationOptions<Trade, unknown, { id: number; body: TradeClose }>,
) {
  const qc = useQueryClient();
  return useMutation<Trade, unknown, { id: number; body: TradeClose }>({
    mutationFn: ({ id, body }) => api.patch<Trade>(`/trades/${id}/close`, { body }),
    onSuccess: (...args) => {
      qc.invalidateQueries({ queryKey: queryKeys.trades.all });
      qc.invalidateQueries({ queryKey: queryKeys.stats.all });
      options?.onSuccess?.(...args);
    },
    ...options,
  });
}

export function useImportTradesMutation(
  options?: UseMutationOptions<ImportResultResponse, unknown, FormData>,
) {
  const qc = useQueryClient();
  return useMutation<ImportResultResponse, unknown, FormData>({
    mutationFn: (formData) => api.upload<ImportResultResponse>("/trades/import", formData),
    onSuccess: (...args) => {
      qc.invalidateQueries({ queryKey: queryKeys.trades.all });
      qc.invalidateQueries({ queryKey: queryKeys.stats.all });
      options?.onSuccess?.(...args);
    },
    ...options,
  });
}

// ──────────────────────────────────────────────
//  Stats
// ──────────────────────────────────────────────

interface StatsParams {
  period?: string;
  start_date?: string;
  end_date?: string;
}

export function useStatsQuery<T = unknown>(
  params?: StatsParams,
  options?: Omit<UseQueryOptions<T>, "queryKey" | "queryFn">,
) {
  return useQuery<T>({
    queryKey: queryKeys.stats.summary(params as Record<string, unknown>),
    queryFn: () => api.get<T>("/stats/", { params: params as Record<string, string> }),
    // staleTime для статистики выше дефолтного: расчёт дорогой, обновление редкое
    staleTime: 60 * 1000,
    ...options,
  });
}

// ──────────────────────────────────────────────
//  Auth
// ──────────────────────────────────────────────

export function useCurrentUserQuery(
  options?: Omit<UseQueryOptions<UserResponse>, "queryKey" | "queryFn">,
) {
  return useQuery<UserResponse>({
    queryKey: queryKeys.auth.me(),
    queryFn: () => api.get<UserResponse>("/auth/me"),
    // Юзер живёт долго; revalidate раз в 5 минут хватит
    staleTime: 5 * 60 * 1000,
    ...options,
  });
}
