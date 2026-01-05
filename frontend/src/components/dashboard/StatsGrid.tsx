'use client';

import { Activity, TrendingUp, TrendingDown, Target, Zap, AlertTriangle, 
         GitGraph, BarChart3, Flame, Scale, Shield, Wallet, Gauge } from 'lucide-react';
import { StatsCard } from '@/components/StatsCard';
import { useLanguage, interpolate } from '@/i18n/LanguageContext';
import { useSettings } from '@/contexts/SettingsContext';

interface DashboardData {
  total_pnl: number;
  win_rate: number;
  total_trades: number;
  profitable_trades: number;
  optimal_f: number;
  sqn: { sqn: number; rating: string };
  z_score: { z_score: number; verdict: string; description: string };
  profit_factor: number;
  r_expectancy: number;
  recovery_factor: number;
  total_roi: number;
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
}

interface StatsGridProps {
  stats: DashboardData | null;
  hasData: boolean;
}

export function StatsGrid({ stats, hasData }: StatsGridProps) {
  const { t } = useLanguage();
  const { settings, formatCurrency } = useSettings();
  const noData = t.emptyState?.noData || '—';

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
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
      <StatsCard 
        title={t.stats.totalPnl.title} 
        value={formatStatCurrency(stats?.total_pnl)} 
        description={hasData ? t.stats.totalPnl.description : ''}
        trend={hasData && stats?.total_pnl && stats.total_pnl > 0 ? 'up' : hasData && stats?.total_pnl && stats.total_pnl < 0 ? 'down' : undefined}
        icon={<TrendingUp size={18} />}
        tooltipText={t.stats.totalPnl.tooltip}
      />
      <StatsCard 
        title={t.stats.winRate.title} 
        value={formatStatPercent(stats?.win_rate)} 
        description={hasData ? interpolate(t.stats.winRate.description, { profitable: stats?.profitable_trades || 0, total: stats?.total_trades || 0 }) : ''}
        icon={<Target size={18} />}
        tooltipText={t.stats.winRate.tooltip}
      />
      <StatsCard 
        title={t.stats.optimalF.title} 
        value={formatStat(stats?.optimal_f)} 
        description={hasData ? t.stats.optimalF.description : ''}
        highlight={hasData ? (
          (stats?.profit_factor || 0) >= 1 
            ? `Риск: ${((stats?.optimal_f || 0) * 10).toFixed(1)}% (1/10)`
            : `⚠️ PF < 1 — не торговать!`
        ) : undefined}
        trend={hasData && (stats?.profit_factor || 0) < 1 ? 'down' : undefined}
        icon={<Zap size={18} />}
        tooltipText={t.stats.optimalF.tooltip}
      />
      <StatsCard 
        title={t.stats.sqn.title} 
        value={formatStat(stats?.sqn?.sqn)} 
        description={hasData ? (stats?.sqn?.rating || t.stats.sqn.description) : ''}
        icon={<Activity size={18} />}
        tooltipText={t.stats.sqn.tooltip}
      />
      <StatsCard 
        title={t.stats.zScore.title} 
        value={formatStat(stats?.z_score?.z_score)} 
        description={hasData ? (stats?.z_score?.verdict || t.stats.zScore.description) : ''}
        icon={<GitGraph size={18} />}
        tooltipText={stats?.z_score?.description || t.stats.zScore.tooltip}
      />
      <StatsCard 
        title={t.stats.profitFactor.title} 
        value={formatStat(stats?.profit_factor)} 
        description={hasData ? t.stats.profitFactor.description : ''}
        icon={<TrendingUp size={18} />}
        tooltipText={t.stats.profitFactor.tooltip}
      />
      <StatsCard 
        title={t.stats.rExpectancy.title} 
        value={formatStat(stats?.r_expectancy, 'R')} 
        description={hasData ? t.stats.rExpectancy.description : ''}
        icon={<Target size={18} />}
        tooltipText={t.stats.rExpectancy.tooltip}
      />
      <StatsCard 
        title={t.stats.recoveryFactor.title} 
        value={formatStat(stats?.recovery_factor)} 
        description={hasData ? t.stats.recoveryFactor.description : ''}
        icon={<Activity size={18} />}
        tooltipText={t.stats.recoveryFactor.tooltip}
      />
      <StatsCard 
        title={t.stats.totalRoi.title} 
        value={formatStatPercent(stats?.total_roi, 2)} 
        description={hasData ? t.stats.totalRoi.description : ''}
        trend={hasData && stats?.total_roi && stats.total_roi > 0 ? 'up' : hasData && stats?.total_roi && stats.total_roi < 0 ? 'down' : undefined}
        icon={<Wallet size={18} />}
        tooltipText={t.stats.totalRoi.tooltip}
      />
      <StatsCard 
        title={t.stats.expectedGhpr.title} 
        value={formatStat(stats?.expected_ghpr)} 
        description={hasData ? t.stats.expectedGhpr.description : ''}
        icon={<TrendingUp size={18} />}
        tooltipText={t.stats.expectedGhpr.tooltip}
      />
      <StatsCard 
        title={t.stats.sortinoRatio.title} 
        value={formatStat(stats?.sortino_ratio)} 
        description={hasData ? t.stats.sortinoRatio.description : ''}
        icon={<Shield size={18} />}
        tooltipText={t.stats.sortinoRatio.tooltip}
      />
      <StatsCard 
        title={t.stats.maxDrawdown.title} 
        value={formatStatPercent(stats?.max_drawdown_pct)} 
        description={hasData ? formatCurrency(stats?.max_drawdown_abs || 0) : ''}
        trend={hasData ? 'down' : undefined}
        icon={<TrendingDown size={18} />}
        tooltipText={t.stats.maxDrawdown.tooltip}
      />
      <StatsCard 
        title={t.stats.currentDrawdown.title} 
        value={formatStatPercent(stats?.current_drawdown_pct)} 
        description={hasData ? t.stats.currentDrawdown.description : ''}
        trend={hasData && stats?.current_drawdown_pct && stats.current_drawdown_pct > 5 ? 'down' : undefined}
        icon={<Activity size={18} />}
        tooltipText={t.stats.currentDrawdown.tooltip}
      />
      <StatsCard 
        title={t.stats.tailRatio.title} 
        value={hasData ? (stats?.tail_ratio?.toFixed(2) || noData) : noData} 
        description={hasData ? t.stats.tailRatio.description : ''}
        icon={<BarChart3 size={18} />}
        tooltipText={t.stats.tailRatio.tooltip}
      />
      <StatsCard 
        title={t.stats.winStreak.title} 
        value={formatStat(stats?.max_win_streak)} 
        description={hasData ? `${interpolate(t.stats.winStreak.description, { current: stats?.current_streak || 0 })} ${stats?.current_streak_type === 'win' ? '🟢' : stats?.current_streak_type === 'loss' ? '🔴' : ''}` : ''}
        icon={<Flame size={18} />}
        tooltipText={t.stats.winStreak.tooltip}
      />
      <StatsCard 
        title={t.stats.lossStreak.title} 
        value={formatStat(stats?.max_loss_streak)} 
        description={hasData ? t.stats.lossStreak.description : ''}
        trend={hasData ? 'down' : undefined}
        icon={<AlertTriangle size={18} />}
        tooltipText={t.stats.lossStreak.tooltip}
      />
      <StatsCard 
        title={t.stats.avgWinLoss.title} 
        value={formatStatCurrency(stats?.avg_win)} 
        description={hasData ? `${settings.currencySymbol}${Math.abs(stats?.avg_loss || 0).toFixed(0)}` : ''}
        icon={<Scale size={18} />}
        tooltipText={t.stats.avgWinLoss.tooltip}
      />
      <StatsCard 
        title={t.stats.calmarRatio.title} 
        value={hasData ? (stats?.calmar_ratio?.calmar_ratio?.toFixed(2) || noData) : noData} 
        description={hasData ? (stats?.calmar_ratio?.rating || t.stats.calmarRatio.description) : ''}
        trend={hasData && stats?.calmar_ratio?.calmar_ratio && stats.calmar_ratio.calmar_ratio >= 1 ? 'up' : hasData && stats?.calmar_ratio?.calmar_ratio && stats.calmar_ratio.calmar_ratio < 0.5 ? 'down' : undefined}
        icon={<Gauge size={18} />}
        tooltipText={t.stats.calmarRatio.tooltip}
      />
    </div>
  );
}
