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
 */
import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/apiClient";
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

  const [stats, setStats] = useState<AnalysisStats | null>(null);
  const [loading, setLoading] = useState(true);

  const fetchStats = useCallback(async () => {
    if (!user) {
      setStats(null);
      setLoading(false);
      return;
    }
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (settings.tradesStartTradeId) {
        params.append("start_trade_id", settings.tradesStartTradeId.toString());
      } else if (settings.tradesStartDate) {
        params.append("period", "custom");
        params.append("start_date", settings.tradesStartDate);
      } else if (filters.period !== "all") {
        params.append("period", filters.period);
        if (filters.period === "custom" && filters.startDate) {
          params.append("start_date", filters.startDate);
          if (filters.endDate) params.append("end_date", filters.endDate);
        }
      }
      if (filters.tag) params.append("tag", filters.tag);
      if (filters.limit) params.append("limit", filters.limit.toString());
      if (settings.maeCalculationMethod) {
        params.append("mae_method", settings.maeCalculationMethod);
      }
      const url = "/stats/" + (params.toString() ? "?" + params.toString() : "");
      const data = await api.get<AnalysisStats>(url);
      setStats(data);
    } catch (err) {
      console.error("useAnalysisStats failed", err);
      setStats(null);
    } finally {
      setLoading(false);
    }
  }, [user, filters, settings.maeCalculationMethod, settings.tradesStartDate, settings.tradesStartTradeId]);

  useEffect(() => {
    fetchStats();
  }, [fetchStats]);

  return { stats, loading, refetch: fetchStats };
}
