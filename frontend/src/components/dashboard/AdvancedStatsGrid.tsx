'use client';

import { Brain, Skull, Dice5, LineChart as LineChartIcon, BarChart3, Clock, Calendar, Gauge } from 'lucide-react';
import { StatsCard } from '@/components/StatsCard';
import { useLanguage, interpolate } from '@/i18n/LanguageContext';
import { useSettings } from '@/contexts/SettingsContext';

interface AdvancedMetrics {
  risk_of_ruin?: { ror_20pct: number; ror_50pct: number };
  monte_carlo?: { median_return: number; worst_case_5pct: number };
  r_distribution?: { pct_above_1r: number; pct_above_2r: number };
  trade_duration?: { 
    avg_duration_hours: number; 
    avg_win_duration_hours: number; 
    avg_loss_duration_hours: number 
  };
  time_patterns?: { best_day: { day: string; total_pnl: number } | null };
  mae_mfe_analysis?: { 
    avg_mae_pct: number; 
    avg_mfe_pct: number; 
    avg_efficiency: number 
  };
}

interface AdvancedStatsGridProps {
  stats: AdvancedMetrics | null;
  hasData: boolean;
}

export function AdvancedStatsGrid({ stats, hasData }: AdvancedStatsGridProps) {
  const { t } = useLanguage();
  const { formatCurrency } = useSettings();
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
    <div className="mt-8 mb-8">
      <h2 className="text-sm font-mono uppercase mb-4 flex items-center gap-2">
        <Brain size={16} className="text-accent" />
        {t.advancedStats.title}
      </h2>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatsCard 
          title={t.advancedStats.ror20.title}
          value={formatStatPercent(stats?.risk_of_ruin?.ror_20pct)} 
          description={hasData ? t.advancedStats.ror20.description : ''}
          trend={hasData && stats?.risk_of_ruin?.ror_20pct && stats.risk_of_ruin.ror_20pct > 10 ? 'down' : undefined}
          icon={<Skull size={18} />}
          tooltipText={t.advancedStats.ror20.tooltip}
        />
        <StatsCard 
          title={t.advancedStats.ror50.title}
          value={formatStatPercent(stats?.risk_of_ruin?.ror_50pct)} 
          description={hasData ? t.advancedStats.ror50.description : ''}
          trend={hasData && stats?.risk_of_ruin?.ror_50pct && stats.risk_of_ruin.ror_50pct > 1 ? 'down' : undefined}
          icon={<Skull size={18} />}
          tooltipText={t.advancedStats.ror50.tooltip}
        />
        <StatsCard 
          title={t.advancedStats.monteCarlo5.title}
          value={formatStatCurrency(stats?.monte_carlo?.worst_case_5pct)} 
          description={hasData ? t.advancedStats.monteCarlo5.description : ''}
          trend={hasData ? 'down' : undefined}
          icon={<Dice5 size={18} />}
          tooltipText={t.advancedStats.monteCarlo5.tooltip}
        />
        <StatsCard 
          title={t.advancedStats.monteCarloMedian.title}
          value={formatStatCurrency(stats?.monte_carlo?.median_return)} 
          description={hasData ? t.advancedStats.monteCarloMedian.description : ''}
          trend={hasData && stats?.monte_carlo?.median_return && stats.monte_carlo.median_return > 0 ? 'up' : hasData ? 'down' : undefined}
          icon={<LineChartIcon size={18} />}
          tooltipText={t.advancedStats.monteCarloMedian.tooltip}
        />
        <StatsCard 
          title={t.advancedStats.rDistribution.title}
          value={formatStatPercent(stats?.r_distribution?.pct_above_1r, 0)} 
          description={hasData ? interpolate(t.advancedStats.rDistribution.description, { pct: stats?.r_distribution?.pct_above_2r?.toFixed(0) || 0 }) : ''}
          icon={<BarChart3 size={18} />}
          tooltipText={t.advancedStats.rDistribution.tooltip}
        />
        <StatsCard 
          title={t.advancedStats.tradeDuration.title}
          value={formatStat(stats?.trade_duration?.avg_duration_hours?.toFixed(1), 'h')} 
          description={hasData ? interpolate(t.advancedStats.tradeDuration.description, { win: stats?.trade_duration?.avg_win_duration_hours?.toFixed(1) || 0, loss: stats?.trade_duration?.avg_loss_duration_hours?.toFixed(1) || 0 }) : ''}
          icon={<Clock size={18} />}
          tooltipText={t.advancedStats.tradeDuration.tooltip}
        />
        <StatsCard 
          title={t.advancedStats.bestDay.title}
          value={hasData && stats?.time_patterns?.best_day?.day ? (t.days as Record<string, string>)[stats.time_patterns.best_day.day] || stats.time_patterns.best_day.day : noData} 
          description={hasData ? `PnL: ${formatCurrency(stats?.time_patterns?.best_day?.total_pnl || 0)}` : ''}
          icon={<Calendar size={18} />}
          tooltipText={t.advancedStats.bestDay.tooltip}
        />
        <StatsCard 
          title={t.advancedStats.maeMfe.title}
          value={formatStatPercent(stats?.mae_mfe_analysis?.avg_mae_pct, 2)} 
          description={hasData ? interpolate(t.advancedStats.maeMfe.description, { mfe: `${stats?.mae_mfe_analysis?.avg_mfe_pct?.toFixed(2) || 0}%`, efficiency: `${stats?.mae_mfe_analysis?.avg_efficiency?.toFixed(0) || 0}%` }) : ''}
          icon={<Gauge size={18} />}
          tooltipText={t.advancedStats.maeMfe.tooltip}
        />
      </div>
    </div>
  );
}
