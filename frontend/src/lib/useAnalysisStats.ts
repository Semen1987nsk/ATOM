"use client";
/**
 * useAnalysisStats — общий хук для страниц /analysis/*
 *
 * Раньше дашборд тащил гигантский /stats/ ответ и сам же раздавал куски в
 * AIInsights/Tags-панели. Теперь панели живут на отдельных страницах и
 * каждая фетчит ровно то, что показывает.
 *
 * Хук берёт текущие фильтры (period/tag/...) + глобальные настройки
 * (tradesStartDate, tradesStartTradeId, maeCalculationMethod) и собирает URL
 * один-в-один как на старом дашборде — так что бекендный кэш переиспользуется.
 *
 * FE-07 (Sprint 5, Batch 4): хук делегирует фетч TanStack Query — кеш и dedup
 * автоматические, retry при сетевом сбое. `useStatsQuery` готовый из queries.ts
 * не подошёл, потому что поддерживает только period/start_date/end_date,
 * а здесь нужны ещё tag/limit/mae_method/start_trade_id, поэтому собран
 * прямой useQuery с queryKeys.stats.summary (полный набор params в ключе).
 */
import { useCallback, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, ApiError } from "@/lib/apiClient";
import { queryKeys } from "@/lib/queries";
import type { Filters } from "@/components/FilterPanel";
import { useSettings } from "@/contexts/SettingsContext";
import { useAuth } from "@/contexts/AuthContext";

export interface AnalysisStats {
  total_trades: number;
  optimal_f: number;
  tag_stats: Array<{ tag: string; pnl: number; win_rate: number; count: number }>;
  mae_mfe_analysis?: {
    avg_mae_pct: number;
    avg_mfe_pct: number;
    avg_efficiency: number;
    trades_analyzed: number;
    recommendations: Array<string | { type: string; icon: string; text: string }>;
  };
}

export function useAnalysisStats(filters: Filters) {
  const { user } = useAuth();
  const { settings } = useSettings();

  // params собираются один-в-один как раньше — backend-кеш по querystring
  // должен переиспользоваться вместе с дашбордом.
  const queryParams = useMemo(() => {
    const params: Record<string, string> = {};
    if (settings.tradesStartTradeId) {
      params.start_trade_id = settings.tradesStartTradeId.toString();
    } else if (settings.tradesStartDate) {
      params.period = "custom";
      params.start_date = settings.tradesStartDate;
    } else if (filters.period !== "all") {
      params.period = filters.period;
      if (filters.period === "custom" && filters.startDate) {
        params.start_date = filters.startDate;
        if (filters.endDate) params.end_date = filters.endDate;
      }
    }
    if (filters.tag) params.tag = filters.tag;
    if (filters.limit) params.limit = filters.limit.toString();
    if (settings.maeCalculationMethod) {
      params.mae_method = settings.maeCalculationMethod;
    }
    return params;
  }, [
    filters.period,
    filters.startDate,
    filters.endDate,
    filters.tag,
    filters.limit,
    settings.tradesStartDate,
    settings.tradesStartTradeId,
    settings.maeCalculationMethod,
  ]);

  const query = useQuery<AnalysisStats>({
    queryKey: queryKeys.stats.summary(queryParams),
    queryFn: () => api.get<AnalysisStats>("/stats/", { params: queryParams }),
    enabled: !!user,
    // staleTime для дорогого расчёта — как в useStatsQuery
    staleTime: 60 * 1000,
  });

  const refetch = useCallback(() => {
    void query.refetch();
  }, [query]);

  return {
    stats: user ? query.data ?? null : null,
    // Когда user=null, query disabled — UI должен показать «нет данных», а не спиннер.
    loading: user ? query.isLoading : false,
    error: (query.error as ApiError | Error | null) ?? null,
    refetch,
  };
}
