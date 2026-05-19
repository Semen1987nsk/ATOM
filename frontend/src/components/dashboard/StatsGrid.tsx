'use client';

import { useState } from 'react';
import { Activity, TrendingUp, TrendingDown, Target, Zap, AlertTriangle,
         GitGraph, BarChart3, Flame, Scale, Shield, Wallet, Gauge } from 'lucide-react';
import { StatsCard } from '@/components/StatsCard';
import { CostsBreakdownCard } from '@/components/dashboard/CostsBreakdownCard';
import { PnLHealthBadge } from '@/components/PnLHealthBadge';
import { useLanguage, interpolate } from '@/i18n/LanguageContext';
import { useSettings } from '@/contexts/SettingsContext';
import { api } from '@/lib/apiClient';

interface OptimalFMethod {
  optimal_f: number;
  f_10: number;
  f_4: number;
  f_2: number;
  worst_loss?: number;
  worst_r?: number;
  trades_used?: number;
  description?: string;
}

interface OptimalFData {
  optimal_f: number;
  pnl_method: OptimalFMethod | null;
  r_method: OptimalFMethod | null;
  trades_with_risk: number;
  trades_without_risk: number;
  total_trades: number;
  is_valid: boolean;
}

interface DashboardData {
  total_pnl: number;
  unrealized_pnl?: number;
  account_level_adjustments?: number;  // Phase 6.4: natural_residual (cash_truth − headline, info-only)
  cash_truth_pnl?: number;  // Phase 6.4: broker reconciliation для PnLHealthBadge
  varmargin_total?: number;  // TR1.2: account-level varmargin (futures)
  total_pnl_with_unrealized?: number;
  // Phase 11 (2026-05-17): gross variants — для settings.pnlDisplayMode='gross'
  total_pnl_gross?: number;
  total_pnl_with_unrealized_gross?: number;
  account_level_adjustments_gross?: number;
  // Phase 12 (2026-05-17): отдельная карточка «Расходы» (best practices).
  total_costs?: number;
  total_costs_breakdown?: {
    broker_commission?: number;
    margin_fees?: number;
    service_fees?: number;
    taxes?: number;
  };
  // Phase 10 (2026-05-17): P&L Health Check status — двойная проверка корректности
  pnl_health?: {
    status: "ok" | "warning" | "mismatch" | "na" | "stale";
    diff_pct: number | null;
    diff_rub: number | null;
    checked_at: string | null;
    breakdown?: Record<string, unknown> | null;
    message?: string;
  } | null;
  win_rate: number;
  total_trades: number;
  profitable_trades: number;
  optimal_f: number;
  optimal_f_data?: OptimalFData;  // Полные данные с обоими методами
  sqn: { sqn: number; rating: string };
  z_score: { z_score: number; verdict: string; description: string };
  profit_factor: number;
  r_expectancy: number;
  recovery_factor: number;
  total_roi: number | null;
  expected_ghpr: number;
  sortino_ratio: number;
  max_drawdown_pct: number;
  max_drawdown_abs: number;
  current_drawdown_pct: number;
  tail_ratio: number;
  max_win_streak: number;
  max_loss_streak: number;
  current_streak: number;
  current_streak_type: string | null;
  avg_win: number;
  avg_loss: number;
  calmar_ratio: { calmar_ratio: number; rating: string };
  period_start_balance_reliable?: boolean;
  period_start_balance_reason?: string | null;
}

interface StatsGridProps {
  stats: DashboardData | null;
  hasData: boolean;
  /** Phase 6.5: live unrealized (Σ /trades/unrealized-pnl), null если endpoint fail'нул */
  liveUnrealizedSum?: number | null;
}

export function StatsGrid({ stats, hasData, liveUnrealizedSum }: StatsGridProps) {
  // Phase 10 (2026-05-17): локальное состояние для refresh кнопки бейджа.
  const [refreshingHealth, setRefreshingHealth] = useState(false);
  const [localHealth, setLocalHealth] = useState<DashboardData["pnl_health"] | undefined>(undefined);
  const healthData = localHealth !== undefined ? localHealth : stats?.pnl_health;

  const handleRefreshHealth = async () => {
    setRefreshingHealth(true);
    try {
      const fresh = await api.post<{
        status: "ok" | "warning" | "mismatch" | "na" | "stale";
        diff_pct: number | null;
        diff_rub: number | null;
        computed_at: string;
        components: Record<string, number>;
      }>('/stats/pnl-health/refresh', {});
      setLocalHealth({
        status: fresh.status,
        diff_pct: fresh.diff_pct,
        diff_rub: fresh.diff_rub,
        checked_at: fresh.computed_at,
        breakdown: fresh as unknown as Record<string, unknown>,
      });
    } catch (e) {
      console.error('PnL health refresh failed', e);
    } finally {
      setRefreshingHealth(false);
    }
  };
  const { t } = useLanguage();
  const { settings, formatCurrency } = useSettings();
  const noData = t.emptyState?.noData || '—';

  // Phase 11 (2026-05-17): выбираем gross vs net по настройке.
  //   net (default) — реальный финансовый результат (matches broker, includes commissions).
  //   gross         — только body P&L (от движения цены), без costs.
  const isGross = settings.pnlDisplayMode === 'gross';
  const displayTotalPnl = isGross ? stats?.total_pnl_gross : stats?.total_pnl;
  // Phase 6.5 (2026-05-18 PM): /trades/unrealized-pnl теперь использует
  // FX-adjusted effective_pv из Position snapshot — числа корректные и для
  // USD-фьючерсов. Берём liveUnrealizedSum для headline'а если доступен.
  const headlineUnrealized = (liveUnrealizedSum !== null && liveUnrealizedSum !== undefined)
    ? liveUnrealizedSum
    : (stats?.unrealized_pnl ?? 0);
  const displayTotalPnlWithUnrealized = (displayTotalPnl ?? 0) + headlineUnrealized;
  const displayAdjustments = isGross
    ? stats?.account_level_adjustments_gross
    : stats?.account_level_adjustments;

  const formatStat = (value: number | string | null | undefined, suffix: string = ''): string => {
    if (!hasData) return noData;
    if (value === null || value === undefined) return noData;
    if (typeof value === 'number' && (isNaN(value) || !isFinite(value))) return noData;
    return `${value}${suffix}`;
  };

  const formatStatPercent = (value: number | null | undefined, decimals: number = 1): string => {
    if (!hasData) return noData;
    if (value === null || value === undefined || isNaN(value) || !isFinite(value)) return noData;
    return `${value.toFixed(decimals)}%`;
  };

  const formatStatCurrency = (value: number | null | undefined): string => {
    if (!hasData) return noData;
    if (value === null || value === undefined || isNaN(value) || !isFinite(value)) return noData;
    return formatCurrency(value);
  };

  return (
    <>
      {/* Phase 10 (2026-05-17): P&L Health Check badge — двойная сверка корректности.
          Видна сверху для быстрого визуального сигнала пользователю.
          Tooltip + кнопка refresh для перерасчёта on-demand. */}
      {hasData && healthData && (
        <div className="mb-4 flex items-center gap-2">
          <PnLHealthBadge
            data={healthData}
            size="md"
            onRefresh={handleRefreshHealth}
            refreshing={refreshingHealth}
          />
          <span className="text-xs text-slate-500">
            Сравнение журнала с банковским балансом
          </span>
        </div>
      )}
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
      {/* Phase 12 (2026-05-17): headline title динамически меняется в зависимости
          от режима, явно сообщая пользователю что показывается:
          - net  → «Общий PnL» (итоговый с учётом всех расходов, как у брокера)
          - gross → «Общий PnL по сделкам» (только body, без расходов) */}
      <StatsCard
        title={isGross ? 'Общий PnL по сделкам' : t.stats.totalPnl.title}
        value={formatStatCurrency(displayTotalPnlWithUnrealized ?? displayTotalPnl)}
        description={hasData ? (() => {
          // Subtitle = компоненты headline. Расходы НЕ показываем здесь:
          // в net-режиме они уже зашиты в displayTotalPnl через Trade.net_pnl,
          // и параллельная строка «Расходы» читается как visual double-count.
          // Отдельная карточка <CostsBreakdownCard /> ниже даёт разбивку расходов.
          const parts: string[] = [];
          if (displayTotalPnl !== undefined && displayTotalPnl !== 0) {
            parts.push(`Реализ.: ${formatCurrency(displayTotalPnl)}`);
          }
          if (headlineUnrealized !== 0) {
            parts.push(`Нереализ.: ${formatCurrency(headlineUnrealized)}`);
          }
          if (displayAdjustments && Math.abs(displayAdjustments) > 1) {
            parts.push(`Прочие: ${formatCurrency(displayAdjustments)}`);
          }
          return parts.length > 0 ? parts.join(' | ') : t.stats.totalPnl.description;
        })() : ''}
        trend={hasData && (displayTotalPnlWithUnrealized ?? displayTotalPnl ?? 0) > 0 ? 'up' : hasData && (displayTotalPnlWithUnrealized ?? displayTotalPnl ?? 0) < 0 ? 'down' : undefined}
        icon={<TrendingUp size={18} />}
        tooltipText={(() => {
          const lines: string[] = [];
          lines.push(
            isGross
              ? 'Режим: По сделкам (только движение цены, без расходов)'
              : 'Режим: Итоговый (с учётом комиссий, сборов, налогов)'
          );
          if (displayTotalPnl !== undefined) {
            lines.push(`Реализованный (закрытые, P&L от цен): ${formatCurrency(displayTotalPnl)}`);
          }
          if (headlineUnrealized) {
            lines.push(`Нереализованный (открытые позиции): ${formatCurrency(headlineUnrealized)}`);
          }
          if (displayAdjustments && Math.abs(displayAdjustments) > 1) {
            lines.push(`Прочие сборы и корректировки счёта: ${formatCurrency(displayAdjustments)}`);
          }
          return lines.length > 0 ? lines.join('\n') : t.stats.totalPnl.tooltip;
        })()}
        manualAnchor="total-pnl"
      />
      {/* Карточка «Расходы» с детальной разбивкой (брокер/маржа/сервис/налоги)
          и hint'ом «Уже включены в Общий PnL» для устранения визуального double-count. */}
      {hasData && stats?.total_costs !== undefined && stats.total_costs !== 0 && (
        <CostsBreakdownCard
          total={stats.total_costs}
          breakdown={stats.total_costs_breakdown ?? {}}
          formatCurrency={formatCurrency}
        />
      )}
      <StatsCard 
        title={t.stats.winRate.title} 
        value={formatStatPercent(stats?.win_rate)} 
        description={hasData ? interpolate(t.stats.winRate.description, { profitable: stats?.profitable_trades || 0, total: stats?.total_trades || 0 }) : ''}
        icon={<Target size={18} />}
        tooltipText={t.stats.winRate.tooltip}
        manualAnchor="win-rate"
      />
      <StatsCard 
        title={t.stats.optimalF.title} 
        value={formatStat(stats?.optimal_f_data?.pnl_method?.optimal_f ?? stats?.optimal_f)} 
        description={hasData ? (
          stats?.optimal_f_data?.pnl_method 
            ? `PnL-метод • Риск: ${stats.optimal_f_data.pnl_method.f_10}%`
            : t.stats.optimalF.description
        ) : ''}
        highlight={hasData ? (
          (stats?.profit_factor || 0) >= 1 
            ? `Рекомендуемый: ${((stats?.optimal_f_data?.pnl_method?.f_10 ?? stats?.optimal_f ?? 0) * 10).toFixed(1)}% (f/10)`
            : `⚠️ PF < 1 — не торговать!`
        ) : undefined}
        secondaryValue={
          hasData && stats?.optimal_f_data?.r_method 
            ? `${stats.optimal_f_data.r_method.optimal_f} (R-метод)`
            : undefined
        }
        secondaryLabel={
          stats?.optimal_f_data?.r_method 
            ? `R-метод (${stats.optimal_f_data.trades_with_risk} сд.)`
            : undefined
        }
        trend={hasData && (stats?.profit_factor || 0) < 1 ? 'down' : undefined}
        icon={<Zap size={18} />}
        tooltipText={t.stats.optimalF.tooltip}
        manualAnchor="optimal-f"
      />
      <StatsCard 
        title={t.stats.sqn.title} 
        value={formatStat(stats?.sqn?.sqn)} 
        description={hasData ? (stats?.sqn?.rating || t.stats.sqn.description) : ''}
        icon={<Activity size={18} />}
        tooltipText={t.stats.sqn.tooltip}
        manualAnchor="sqn"
      />
      <StatsCard 
        title={t.stats.zScore.title} 
        value={formatStat(stats?.z_score?.z_score)} 
        description={hasData ? (stats?.z_score?.verdict || t.stats.zScore.description) : ''}
        icon={<GitGraph size={18} />}
        tooltipText={stats?.z_score?.description || t.stats.zScore.tooltip}
        manualAnchor="z-score"
      />
      <StatsCard 
        title={t.stats.profitFactor.title} 
        value={formatStat(stats?.profit_factor)} 
        description={hasData ? t.stats.profitFactor.description : ''}
        icon={<TrendingUp size={18} />}
        tooltipText={t.stats.profitFactor.tooltip}
        manualAnchor="profit-factor"
      />
      <StatsCard 
        title={t.stats.rExpectancy.title} 
        value={formatStat(stats?.r_expectancy, 'R')} 
        description={hasData ? t.stats.rExpectancy.description : ''}
        icon={<Target size={18} />}
        tooltipText={t.stats.rExpectancy.tooltip}
        manualAnchor="r-expectancy"
      />
      <StatsCard 
        title={t.stats.recoveryFactor.title} 
        value={formatStat(stats?.recovery_factor)} 
        description={hasData ? t.stats.recoveryFactor.description : ''}
        icon={<Activity size={18} />}
        tooltipText={t.stats.recoveryFactor.tooltip}
        manualAnchor="recovery-factor"
      />
      <StatsCard 
        title={t.stats.totalRoi.title} 
        value={formatStatPercent(stats?.total_roi, 2)} 
        description={hasData ? (stats?.period_start_balance_reliable === false ? 'ROI скрыт: нет надёжной базы периода' : t.stats.totalRoi.description) : ''}
        trend={hasData && stats?.total_roi && stats.total_roi > 0 ? 'up' : hasData && stats?.total_roi && stats.total_roi < 0 ? 'down' : undefined}
        icon={<Wallet size={18} />}
        tooltipText={stats?.period_start_balance_reliable === false ? (stats?.period_start_balance_reason || t.stats.totalRoi.tooltip) : t.stats.totalRoi.tooltip}
        manualAnchor="roi"
      />
      <StatsCard 
        title={t.stats.expectedGhpr.title} 
        value={formatStat(stats?.expected_ghpr)} 
        description={hasData ? t.stats.expectedGhpr.description : ''}
        icon={<TrendingUp size={18} />}
        tooltipText={t.stats.expectedGhpr.tooltip}
        manualAnchor="ghpr"
      />
      <StatsCard 
        title={t.stats.sortinoRatio.title} 
        value={formatStat(stats?.sortino_ratio)} 
        description={hasData ? t.stats.sortinoRatio.description : ''}
        icon={<Shield size={18} />}
        tooltipText={t.stats.sortinoRatio.tooltip}
        manualAnchor="sortino"
      />
      <StatsCard 
        title={t.stats.maxDrawdown.title} 
        value={formatStatPercent(stats?.max_drawdown_pct)} 
        description={hasData ? formatCurrency(stats?.max_drawdown_abs || 0) : ''}
        trend={hasData ? 'down' : undefined}
        icon={<TrendingDown size={18} />}
        tooltipText={t.stats.maxDrawdown.tooltip}
        manualAnchor="drawdown"
      />
      <StatsCard 
        title={t.stats.currentDrawdown.title} 
        value={formatStatPercent(stats?.current_drawdown_pct)} 
        description={hasData ? t.stats.currentDrawdown.description : ''}
        trend={hasData && stats?.current_drawdown_pct && stats.current_drawdown_pct > 5 ? 'down' : undefined}
        icon={<Activity size={18} />}
        tooltipText={t.stats.currentDrawdown.tooltip}
        manualAnchor="drawdown"
      />
      <StatsCard 
        title={t.stats.tailRatio.title} 
        value={hasData ? (stats?.tail_ratio?.toFixed(2) || noData) : noData} 
        description={hasData ? t.stats.tailRatio.description : ''}
        icon={<BarChart3 size={18} />}
        tooltipText={t.stats.tailRatio.tooltip}
        manualAnchor="tail-ratio"
      />
      <StatsCard 
        title={t.stats.winStreak.title} 
        value={formatStat(stats?.max_win_streak)} 
        description={hasData ? `${interpolate(t.stats.winStreak.description, { current: stats?.current_streak || 0 })} ${stats?.current_streak_type === 'win' ? '🟢' : stats?.current_streak_type === 'loss' ? '🔴' : ''}` : ''}
        icon={<Flame size={18} />}
        tooltipText={t.stats.winStreak.tooltip}
        manualAnchor="streaks"
      />
      <StatsCard 
        title={t.stats.lossStreak.title} 
        value={formatStat(stats?.max_loss_streak)} 
        description={hasData ? t.stats.lossStreak.description : ''}
        trend={hasData ? 'down' : undefined}
        icon={<AlertTriangle size={18} />}
        tooltipText={t.stats.lossStreak.tooltip}
        manualAnchor="streaks"
      />
      <StatsCard 
        title={t.stats.avgWinLoss.title} 
        value={formatStatCurrency(stats?.avg_win)} 
        description={hasData ? `${settings.currencySymbol}${Math.abs(stats?.avg_loss || 0).toFixed(0)}` : ''}
        icon={<Scale size={18} />}
        tooltipText={t.stats.avgWinLoss.tooltip}
        manualAnchor="avg-win-loss"
      />
      <StatsCard 
        title={t.stats.calmarRatio.title} 
        value={hasData ? (stats?.calmar_ratio?.calmar_ratio?.toFixed(2) || noData) : noData} 
        description={hasData ? (stats?.calmar_ratio?.rating || t.stats.calmarRatio.description) : ''}
        trend={hasData && stats?.calmar_ratio?.calmar_ratio && stats.calmar_ratio.calmar_ratio >= 1 ? 'up' : hasData && stats?.calmar_ratio?.calmar_ratio && stats.calmar_ratio.calmar_ratio < 0.5 ? 'down' : undefined}
        icon={<Gauge size={18} />}
        tooltipText={t.stats.calmarRatio.tooltip}
        manualAnchor="calmar-ratio"
      />
    </div>
    </>
  );
}
