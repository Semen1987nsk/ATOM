'use client';

import { useEffect, useState, useCallback } from 'react';
import { StatsCard } from '@/components/StatsCard';
import { AddTradeModal } from '@/components/AddTradeModal';
import CloseTradeModal from '@/components/CloseTradeModal';
import { SettingsModal } from '@/components/SettingsModal';
import { LanguageSwitcher } from '@/components/LanguageSwitcher';
import ThemeToggle from '@/components/ThemeToggle';
import { FilterPanel, Filters, Period } from '@/components/FilterPanel';
import { useLanguage, interpolate } from '@/i18n/LanguageContext';
import { useSettings } from '@/contexts/SettingsContext';
import { useAuth } from '@/contexts/AuthContext';
import Link from 'next/link';
import { Activity, TrendingUp, TrendingDown, Target, Zap, AlertTriangle, Plus, Lock, Upload, Trash2, BookOpen, GitGraph, History, Shield, BarChart3, Flame, Scale, Skull, Dice5, LineChart as LineChartIcon, Clock, Calendar, Gauge, Brain, Settings, Wallet, User, LogIn } from 'lucide-react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, AreaChart, Area } from 'recharts';
import { DashboardSkeleton } from '@/components/Skeleton';

interface Trade {
  id: number;
  symbol: string;
  asset_name?: string;
  asset_type?: string;
  direction: string;
  pnl: number | null;
  commission?: number;
  entry_price: number;
  quantity: number;
  setup_name?: string;
  timeframe?: string;
  tags?: string[];
  ai_analysis?: {
    verdict: string;
    analysis: string;
    advice: string;
    score: number;
  };
}

interface DashboardData {
  total_pnl: number;
  win_rate: number;
  total_trades: number;
  profitable_trades: number;
  optimal_f: number;
  sqn: {
    sqn: number;
    rating: string;
  };
  z_score: {
    z_score: number;
    verdict: string;
    description: string;
  };
  profit_factor: number;
  r_expectancy: number;
  recovery_factor: number;
  total_roi: number;
  expected_ghpr: number;
  sortino_ratio: number;
  max_drawdown_pct: number;
  max_drawdown_abs: number;
  current_drawdown_pct: number;
  avg_win: number;
  avg_loss: number;
  largest_win: number;
  largest_loss: number;
  max_win_streak: number;
  max_loss_streak: number;
  current_streak: number;
  current_streak_type: string | null;
  tail_ratio: number;
  calmar_ratio: {
    calmar_ratio: number;
    cagr_pct: number;
    max_drawdown_pct: number;
    rating: string;
  };
  risk_of_ruin: {
    ror_20pct: number;
    ror_50pct: number;
    message: string;
  };
  r_distribution: {
    pct_positive_r: number;
    pct_above_1r: number;
    pct_above_2r: number;
  };
  trade_duration: {
    avg_duration_hours: number;
    avg_win_duration_hours: number;
    avg_loss_duration_hours: number;
    median_duration_hours: number;
  };
  monte_carlo: {
    median_return: number;
    worst_case_5pct: number;
    best_case_95pct: number;
    ruin_probability: number;
  };
  time_patterns: {
    best_day: { day: string; total_pnl: number } | null;
    worst_day: { day: string; total_pnl: number } | null;
  };
  mae_mfe_analysis: {
    avg_mae_pct: number;
    avg_mfe_pct: number;
    avg_efficiency: number;
    trades_analyzed: number;
    recommendations: string[];
  };
  equity_curve: { date: string; balance: number }[];
  tag_stats: { tag: string; pnl: number; win_rate: number; count: number }[];
}

// Auth button component
function AuthButton() {
  const { user, isLoading } = useAuth();
  
  if (isLoading) {
    return <div className="w-8 h-8 bg-secondary rounded-full animate-pulse" />;
  }
  
  if (user) {
    return (
      <div className="flex items-center gap-2">
        {user.is_admin && (
          <Link 
            href="/admin"
            className="btn-secondary p-2.5 aspect-square text-purple-400"
            title="Админ-панель"
          >
            <Shield size={14} />
          </Link>
        )}
        <Link 
          href="/profile"
          className="flex items-center gap-2 btn-secondary"
          title="Профиль"
        >
          <div className="w-5 h-5 bg-accent rounded-full flex items-center justify-center">
            <span className="text-xs font-bold text-white">
              {(user.name || user.email)[0].toUpperCase()}
            </span>
          </div>
          <span className="hidden md:inline text-sm">{user.name || 'Профиль'}</span>
        </Link>
      </div>
    );
  }
  
  return (
    <Link 
      href="/login"
      className="btn-secondary flex items-center gap-2"
    >
      <LogIn size={14} />
      <span className="hidden md:inline">Войти</span>
    </Link>
  );
}

export default function Home() {
  const { t } = useLanguage();
  const { settings, formatCurrency } = useSettings();
  const [stats, setStats] = useState<DashboardData | null>(null);
  const [trades, setTrades] = useState<Trade[]>([]);
  const [loading, setLoading] = useState(true);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [isCloseModalOpen, setIsCloseModalOpen] = useState(false);
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const [selectedTradeToClose, setSelectedTradeToClose] = useState<Trade | null>(null);
  const [selectedTag, setSelectedTag] = useState<string | null>(null);
  const [logs, setLogs] = useState<{msg: string, time: string}[]>([]);
  const [mounted, setMounted] = useState(false);
  
  // Check if we have any data
  const hasData = trades.length > 0;
  const noData = t.emptyState?.noData || '—';
  
  // Helper to format stat values - shows dash when no data
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
  
  // Unified filters state
  const [filters, setFilters] = useState<Filters>({
    period: 'all',
    tag: undefined,
    limit: undefined,
    startDate: undefined,
    endDate: undefined
  });

  const getApiUrl = (path: string) => {
    if (typeof window !== 'undefined' && window.location.hostname.includes('github.dev')) {
      const codespaceName = window.location.hostname.split('-3000')[0];
      return `https://${codespaceName}-8000.app.github.dev${path}`;
    }
    return `http://localhost:8000${path}`;
  };

  const addLog = (msg: string) => {
    const time = new Date().toLocaleTimeString();
    setLogs(prev => [{msg, time}, ...prev].slice(0, 5));
  };

  const fetchData = useCallback(async (currentFilters?: Filters) => {
    try {
      // Build stats URL with all filters
      let statsUrl = '/stats/';
      const params = new URLSearchParams();
      
      const f = currentFilters || filters;
      
      // Period filter
      if (f.period !== 'all') {
        params.append('period', f.period);
        if (f.period === 'custom' && f.startDate) {
          params.append('start_date', f.startDate);
          if (f.endDate) params.append('end_date', f.endDate);
        }
      }
      
      // Tag filter
      if (f.tag) {
        params.append('tag', f.tag);
      }
      
      // Limit filter
      if (f.limit) {
        params.append('limit', f.limit.toString());
      }
      
      // Initial deposit for ROI calculation
      if (settings.initialDeposit && settings.initialDeposit > 0) {
        params.append('initial_deposit', settings.initialDeposit.toString());
      }
      
      if (params.toString()) {
        statsUrl += '?' + params.toString();
      }

      const [statsRes, tradesRes] = await Promise.all([
        fetch(getApiUrl(statsUrl)),
        fetch(getApiUrl('/trades/'))
      ]);
      const statsData = await statsRes.json();
      const tradesData = await tradesRes.json();
      setStats(statsData);
      setTrades(tradesData.reverse());
      addLog(t.logs.synchronized);
    } catch (error) {
      console.error('Failed to fetch data:', error);
      addLog(t.logs.syncFailed);
    } finally {
      setLoading(false);
    }
  }, [filters, settings.initialDeposit, t.logs.synchronized, t.logs.syncFailed]);

  useEffect(() => {
    setMounted(true);
    fetchData();
  }, [fetchData]);

  // Handle filters change
  const handleFiltersChange = (newFilters: Filters) => {
    setFilters(newFilters);
    fetchData(newFilters);
  };

  const openCloseModal = (trade: Trade) => {
    setSelectedTradeToClose(trade);
    setIsCloseModalOpen(true);
  };

  const handleCloseTradeConfirm = async (exitPrice: number, exitReason: string) => {
    if (!selectedTradeToClose) return;
    
    try {
      const response = await fetch(getApiUrl(`/trades/${selectedTradeToClose.id}/close`), {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          exit_price: exitPrice,
          exit_at: new Date().toISOString(),
          exit_reason: exitReason,
          mae_price: exitPrice * 0.98, // Mock MAE for now
          mfe_price: exitPrice * 1.02  // Mock MFE for now
        }),
      });
      if (response.ok) {
        fetchData();
        addLog(`${t.logs.positionClosed}: ${selectedTradeToClose.id}`);
      }
    } catch (error) {
      console.error('Failed to close trade:', error);
      addLog(t.logs.closeFailed);
    }
  };

  const handleImport = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    const formData = new FormData();
    formData.append('file', file);

    try {
      addLog(t.logs.uploading);
      const response = await fetch(getApiUrl('/trades/import'), {
        method: 'POST',
        body: formData,
      });

      if (response.ok) {
        const result = await response.json();
        addLog(result.message);
        fetchData();
      } else {
        const err = await response.json();
        addLog(`ERROR: ${err.detail}`);
      }
    } catch (error) {
      console.error('Import failed:', error);
      addLog(t.logs.importFailed);
    }
    // Reset input
    e.target.value = '';
  };

  const handleDelete = async (tradeId: number) => {
    if (!confirm('Are you sure you want to delete this trade?')) return;
    try {
      await fetch(getApiUrl(`/trades/${tradeId}`), { method: 'DELETE' });
      fetchData();
      addLog(`${t.logs.tradePurged}: ${tradeId}`);
    } catch (error) {
      console.error('Delete failed:', error);
      addLog(t.logs.purgeFailed);
    }
  };

  if (!mounted) return null;
  if (loading) return <DashboardSkeleton />;

  const allTags = Array.from(new Set(trades.flatMap(t => t.tags || [])));
  const filteredTrades = selectedTag 
    ? trades.filter(t => t.tags?.includes(selectedTag)) 
    : trades;

  return (
    <main className="min-h-screen p-8 max-w-7xl mx-auto">
      <header className="mb-12 flex justify-between items-start relative z-10">
        <div>
          <h1 className="text-4xl font-black tracking-tighter mb-2 italic">
            <span className="text-accent">Eqio</span>
          </h1>
          <p className="text-xs font-mono opacity-50 uppercase tracking-[0.2em]">
            {t.app.subtitle}
          </p>
          {/* Deposit Display */}
          <div className="mt-3 flex items-center gap-2 text-sm">
            <Wallet size={14} className="text-accent" />
            <span className="opacity-50">Депозит:</span>
            <span className="font-bold text-accent">{formatCurrency(settings.initialDeposit)}</span>
            {stats?.total_pnl !== undefined && (
              <span className={`text-xs ${stats.total_pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                ({stats.total_pnl >= 0 ? '+' : ''}{((stats.total_pnl / settings.initialDeposit) * 100).toFixed(2)}%)
              </span>
            )}
          </div>
        </div>
        <div className="flex gap-3 flex-wrap justify-end items-center">
          <FilterPanel
            filters={filters}
            onChange={handleFiltersChange}
            getApiUrl={getApiUrl}
          />
          <div className="flex gap-2 items-center">
            <ThemeToggle />
            <button
              onClick={() => setIsSettingsOpen(true)}
              className="btn-secondary p-2.5 aspect-square"
              title="Настройки"
            >
              <Settings size={14} />
            </button>
            <LanguageSwitcher />
            <AuthButton />
          </div>
          <Link 
            href="/history"
            className="btn-secondary flex items-center gap-2"
          >
            <History size={14} />
            {t.nav.tradeHistory}
          </Link>
          <Link 
            href="/manual"
            className="btn-secondary flex items-center gap-2"
          >
            <BookOpen size={14} />
            {t.nav.systemManual}
          </Link>
          <label className="btn-secondary flex items-center gap-2 cursor-pointer">
            <input type="file" accept=".csv,.xlsx,.xls,.pdf" className="hidden" onChange={handleImport} />
            <Upload size={14} />
            {t.nav.importData}
          </label>
          <button 
            onClick={() => setIsModalOpen(true)}
            className="btn-primary flex items-center gap-2"
          >
            <Plus size={14} /> {t.nav.logPosition}
          </button>
        </div>
      </header>

      <AddTradeModal 
        isOpen={isModalOpen} 
        onClose={() => setIsModalOpen(false)} 
        onSuccess={() => {
          fetchData();
          addLog('New position initialized');
        }} 
      />

      <CloseTradeModal
        isOpen={isCloseModalOpen}
        onClose={() => {
          setIsCloseModalOpen(false);
          setSelectedTradeToClose(null);
        }}
        onConfirm={handleCloseTradeConfirm}
        tradeTicker={selectedTradeToClose?.symbol}
        tradeDirection={selectedTradeToClose?.direction}
      />

      <SettingsModal
        isOpen={isSettingsOpen}
        onClose={() => setIsSettingsOpen(false)}
      />

      {/* Empty State Banner */}
      {!hasData && !loading && (
        <div className="mb-8 p-6 cyber-card border-accent/30 bg-gradient-to-r from-accent/5 to-transparent">
          <div className="flex flex-col md:flex-row items-center justify-between gap-4">
            <div className="flex items-center gap-4">
              <div className="w-12 h-12 rounded-full bg-accent/20 flex items-center justify-center">
                <BarChart3 size={24} className="text-accent" />
              </div>
              <div>
                <h3 className="text-lg font-bold">{t.emptyState?.title || 'Start Your Trading Journal'}</h3>
                <p className="text-sm opacity-60">{t.emptyState?.description || 'Import broker report or add your first trade to see analytics'}</p>
              </div>
            </div>
            <div className="flex gap-3">
              <label className="btn-secondary flex items-center gap-2 cursor-pointer">
                <input type="file" accept=".csv,.xlsx,.xls,.pdf" className="hidden" onChange={handleImport} />
                <Upload size={14} />
                {t.emptyState?.importButton || 'Import Trades'}
              </label>
              <button 
                onClick={() => setIsModalOpen(true)}
                className="btn-primary flex items-center gap-2"
              >
                <Plus size={14} />
                {t.emptyState?.addButton || 'Add Manually'}
              </button>
            </div>
          </div>
        </div>
      )}

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
              ? `Риск: ${((stats?.optimal_f || 0) * 25).toFixed(0)}% от депо`
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

      {/* Advanced Metrics Section */}
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

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="lg:col-span-2 space-y-4">
          <div className="cyber-card p-6 relative overflow-hidden group">
            {/* Background glow */}
            <div className="absolute top-0 right-0 w-64 h-64 bg-accent/5 rounded-full blur-3xl opacity-0 group-hover:opacity-100 transition-opacity duration-500" />
            
            <h2 className="text-sm font-mono uppercase mb-6 flex items-center gap-2 relative z-10">
              <Activity size={16} className="text-accent" />
              {t.charts.equityCurve}
              <span className="ml-auto text-[10px] opacity-40">{stats?.equity_curve?.length || 0} {t.charts.dataPoints || 'points'}</span>
            </h2>
            <div className="h-[250px] w-full relative z-10">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={stats?.equity_curve || []}>
                  <defs>
                    <linearGradient id="colorBalance" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#00ff9f" stopOpacity={0.4}/>
                      <stop offset="50%" stopColor="#00ff9f" stopOpacity={0.15}/>
                      <stop offset="100%" stopColor="#00ff9f" stopOpacity={0}/>
                    </linearGradient>
                    <linearGradient id="strokeGradient" x1="0" y1="0" x2="1" y2="0">
                      <stop offset="0%" stopColor="#00ff9f" stopOpacity={0.5}/>
                      <stop offset="50%" stopColor="#00ff9f" stopOpacity={1}/>
                      <stop offset="100%" stopColor="#bc13fe" stopOpacity={0.8}/>
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1a1a1a" vertical={false} />
                  <XAxis 
                    dataKey="date" 
                    stroke="#333" 
                    fontSize={10} 
                    tickLine={false} 
                    axisLine={false}
                    tickFormatter={(str) => str.split(' ')[0]} 
                  />
                  <YAxis 
                    stroke="#333" 
                    fontSize={10} 
                    tickLine={false} 
                    axisLine={false}
                    tickFormatter={(val) => `${settings.currencySymbol}${val}`}
                  />
                  <Tooltip 
                    contentStyle={{ 
                      backgroundColor: 'rgba(13, 13, 13, 0.95)', 
                      border: '1px solid rgba(0, 255, 159, 0.3)', 
                      borderRadius: '8px',
                      boxShadow: '0 0 20px rgba(0, 255, 159, 0.1)',
                      backdropFilter: 'blur(10px)',
                      fontSize: '12px' 
                    }}
                    itemStyle={{ color: '#00ff9f' }}
                    labelStyle={{ color: '#888', marginBottom: '4px' }}
                    cursor={{ stroke: 'rgba(0, 255, 159, 0.3)', strokeWidth: 1 }}
                  />
                  <Area 
                    type="monotone" 
                    dataKey="balance" 
                    stroke="url(#strokeGradient)" 
                    fillOpacity={1} 
                    fill="url(#colorBalance)" 
                    strokeWidth={2}
                    dot={false}
                    activeDot={{ 
                      r: 6, 
                      fill: '#00ff9f', 
                      stroke: '#000', 
                      strokeWidth: 2,
                      style: { filter: 'drop-shadow(0 0 6px rgba(0, 255, 159, 0.8))' }
                    }}
                  />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </div>

          <div className="cyber-card p-6 relative overflow-hidden">
            <div className="flex justify-between items-center mb-6">
              <h2 className="text-sm font-mono uppercase flex items-center gap-2">
                <Activity size={16} className="text-accent" />
                {t.charts.recentTrades}
              </h2>
              <Link href="/history" className="text-[10px] font-mono text-accent hover:underline flex items-center gap-1 hover:gap-2 transition-all">
                {t.charts.viewAll}
                <span>→</span>
              </Link>
            </div>
            <div className="space-y-4">
              {filteredTrades.length === 0 ? (
                <div className="empty-state py-12">
                  <div className="empty-state-icon">
                    <Activity size={32} className="text-accent/50" />
                  </div>
                  <h3 className="text-lg font-bold mb-2">{t.charts.noTrades}</h3>
                  <p className="text-sm opacity-50 mb-4">Начните торговать и данные появятся здесь</p>
                  <button 
                    onClick={() => setIsModalOpen(true)}
                    className="btn-primary text-xs"
                  >
                    <Plus size={14} className="inline mr-2" />
                    {t.nav.logPosition}
                  </button>
                </div>
              ) : (
                filteredTrades.slice(0, 5).map((trade, index) => ( // Show only last 5 trades
                  <div 
                    key={trade.id} 
                    className="border-b border-border pb-4 last:border-0 table-row-hover p-3 -mx-3 rounded-lg"
                    style={{ animationDelay: `${index * 0.1}s` }}
                  >
                    <div className="flex justify-between items-center mb-2">
                      <div className="flex items-center gap-3">
                        <span className={`text-[10px] font-mono px-2 py-0.5 rounded ${trade.direction === 'long' ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400'}`}>
                          {trade.direction === 'long' ? t.trades.long : t.trades.short}
                        </span>
                        <div>
                          <span className="font-bold">{trade.symbol}</span>
                          {trade.asset_name && <span className="text-[10px] text-gray-500 ml-2">{trade.asset_name}</span>}
                          {trade.asset_type && <span className="text-[9px] border border-gray-700 rounded px-1 ml-2 text-gray-400">{trade.asset_type}</span>}
                        </div>
                      </div>
                      <div className="flex items-center gap-4">
                        <div className="text-right">
                           {trade.pnl !== null ? (
                            <span className={`block font-bold ${Number(trade.pnl) >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                              {Number(trade.pnl) >= 0 ? '+' : ''}{formatCurrency(Number(trade.pnl))}
                            </span>
                          ) : (
                            <span className="text-[10px] text-accent">{t.trades.open}</span>
                          )}
                          {trade.commission && <div className="text-[9px] text-gray-500">{t.trades.commission}: {settings.currencySymbol}{trade.commission.toFixed(2)}</div>}
                        </div>
                        
                        {/* Close trade button for open trades */}
                        {trade.pnl === null && (
                          <button 
                            onClick={() => openCloseModal(trade)}
                            className="text-yellow-500/50 hover:text-yellow-500 transition-colors p-1"
                            title={t.trades.closeTrade}
                          >
                            <Lock size={12} />
                          </button>
                        )}
                        
                        <button 
                          onClick={() => handleDelete(trade.id)}
                          className="text-red-500/50 hover:text-red-500 transition-colors p-1"
                        >
                          <Trash2 size={12} />
                        </button>
                      </div>
                    </div>
                    
                    <div className="flex flex-wrap gap-2 mb-2 items-center">
                      {trade.setup_name && (
                         <span className="text-[10px] bg-blue-500/10 text-blue-400 px-1.5 py-0.5 rounded">
                           {t.trades.setup}: {trade.setup_name}
                         </span>
                      )}
                      {trade.timeframe && (
                         <span className="text-[10px] bg-purple-500/10 text-purple-400 px-1.5 py-0.5 rounded">
                           {t.trades.timeframe}: {trade.timeframe}
                         </span>
                      )}
                      {trade.tags && trade.tags.length > 0 && trade.tags.map(tag => (
                          <span key={tag} className="text-[9px] font-mono border border-border px-1.5 py-0.5 rounded text-muted">
                            #{tag.toUpperCase()}
                          </span>
                        ))}
                    </div>

                    {trade.ai_analysis && (
                      <div className="bg-white/5 p-3 rounded text-xs">
                        <div className="flex items-center gap-2 mb-1">
                          <Zap size={12} className="text-accent" />
                          <span className="font-bold uppercase text-accent">{trade.ai_analysis.verdict}</span>
                          <span className="opacity-40 ml-auto">{t.ai.score}: {trade.ai_analysis.score}/100</span>
                        </div>
                        <p className="opacity-70 mb-2">{trade.ai_analysis.analysis}</p>
                        <p className="text-accent-secondary italic">{trade.ai_analysis.advice}</p>
                      </div>
                    )}
                  </div>
                ))
              )}
            </div>
          </div>
        </div>

        <div className="space-y-4">
          <div className="cyber-card p-6 border-l-accent/30 relative overflow-hidden group">
            {/* Glow effect */}
            <div className="absolute -top-20 -right-20 w-40 h-40 bg-accent/10 rounded-full blur-3xl opacity-0 group-hover:opacity-100 transition-opacity duration-500" />
            
            <h2 className="text-sm font-mono uppercase mb-6 flex items-center gap-2 relative z-10">
              <AlertTriangle size={16} className="text-accent animate-pulse" />
              AI Insights
              <span className="ml-auto badge-accent text-[8px]">LIVE</span>
            </h2>
            <div className="space-y-4 relative z-10">
              {stats?.mae_mfe_analysis?.recommendations.map((rec, i) => (
                <div 
                  key={i} 
                  className="p-3 bg-accent/5 border-l-2 border-accent text-sm hover:bg-accent/10 transition-all duration-300 rounded-r-lg cursor-default"
                  style={{ animationDelay: `${i * 0.1}s` }}
                >
                  <span className="opacity-30 text-[10px] mr-2">0{i + 1}</span>
                  {rec}
                </div>
              ))}
              <div className="p-3 bg-gradient-to-r from-green-500/10 to-transparent border-l-2 border-green-500 text-sm rounded-r-lg">
                <span className="text-green-400 font-bold">Optimal f:</span> 
                <span className="ml-2">{((stats?.optimal_f || 0) * 25).toFixed(1)}%</span>
                <span className="text-[10px] opacity-40 ml-2">рекомендуемый риск (f/4)</span>
              </div>
              <div className="mt-3 p-2 text-[10px] border border-white/5 rounded-lg space-y-2">
                <div className="font-mono uppercase opacity-60 mb-2">Варианты риска:</div>
                <div className="flex justify-between items-center">
                  <span className="flex items-center gap-1">
                    <span className="w-2 h-2 rounded-full bg-blue-500"></span>
                    Ультра-консерв. (f/10):
                  </span>
                  <span className="text-blue-400 font-bold">{((stats?.optimal_f || 0) * 10).toFixed(1)}%</span>
                </div>
                <div className="flex justify-between items-center opacity-80">
                  <span className="flex items-center gap-1">
                    <span className="w-2 h-2 rounded-full bg-green-500"></span>
                    Консервативный (f/4):
                  </span>
                  <span className="text-green-400">{((stats?.optimal_f || 0) * 25).toFixed(1)}%</span>
                </div>
                <div className="flex justify-between items-center opacity-70">
                  <span className="flex items-center gap-1">
                    <span className="w-2 h-2 rounded-full bg-accent-secondary"></span>
                    Умеренный (f/2):
                  </span>
                  <span className="text-accent-secondary">{((stats?.optimal_f || 0) * 50).toFixed(1)}%</span>
                </div>
                <div className="flex justify-between items-center opacity-70">
                  <span className="flex items-center gap-1">
                    <span className="w-2 h-2 rounded-full bg-red-500"></span>
                    Агрессивный (f):
                  </span>
                  <span className="text-red-400">{((stats?.optimal_f || 0) * 100).toFixed(1)}%</span>
                </div>
                <div className="mt-2 pt-2 border-t border-white/5 space-y-1 opacity-60">
                  <div className="text-blue-400/80">✓ f/10 — большой капитал, минимальная волатильность</div>
                  <div className="text-green-400/80">✓ f/4 — основной капитал, долгосрочная торговля</div>
                  <div className="text-accent-secondary/80">✓ f/2 — уверенные сетапы, средний риск</div>
                  <div className="text-red-400/80">✓ f — конкурсы, разгон депо, «play money»</div>
                </div>
              </div>
            </div>
          </div>

          {/* MAE/MFE Detailed Analysis Panel */}
          <div className="cyber-card p-6 border-l-cyan-500/30 relative overflow-hidden group">
            <div className="absolute -top-20 -left-20 w-40 h-40 bg-cyan-500/10 rounded-full blur-3xl opacity-0 group-hover:opacity-100 transition-opacity duration-500" />
            
            <h2 className="text-sm font-mono uppercase mb-6 flex items-center gap-2 relative z-10">
              <Gauge size={16} className="text-cyan-400" />
              MAE/MFE Анализ
              <span className="ml-auto text-[10px] opacity-40">{stats?.mae_mfe_analysis?.trades_analyzed || 0} сделок</span>
            </h2>
            
            <div className="space-y-4 relative z-10">
              {/* Основные метрики */}
              <div className="grid grid-cols-3 gap-3">
                <div className="p-3 bg-red-500/10 border border-red-500/20 rounded-lg text-center">
                  <div className="text-[10px] opacity-60 uppercase mb-1">MAE (просадка)</div>
                  <div className="text-2xl font-bold text-red-400">{stats?.mae_mfe_analysis?.avg_mae_pct?.toFixed(2) || 0}%</div>
                  <div className="text-[9px] opacity-40">против позиции</div>
                </div>
                <div className="p-3 bg-green-500/10 border border-green-500/20 rounded-lg text-center">
                  <div className="text-[10px] opacity-60 uppercase mb-1">MFE (прибыль)</div>
                  <div className="text-2xl font-bold text-green-400">{stats?.mae_mfe_analysis?.avg_mfe_pct?.toFixed(2) || 0}%</div>
                  <div className="text-[9px] opacity-40">в нашу сторону</div>
                </div>
                <div className="p-3 bg-cyan-500/10 border border-cyan-500/20 rounded-lg text-center">
                  <div className="text-[10px] opacity-60 uppercase mb-1">Эффективность</div>
                  <div className="text-2xl font-bold text-cyan-400">{stats?.mae_mfe_analysis?.avg_efficiency?.toFixed(0) || 0}%</div>
                  <div className="text-[9px] opacity-40">от MFE забираем</div>
                </div>
              </div>
              
              {/* Визуальная шкала MAE vs MFE */}
              <div className="p-3 bg-white/5 rounded-lg">
                <div className="text-[10px] opacity-60 uppercase mb-2">Соотношение MAE / MFE</div>
                <div className="relative h-6 bg-white/5 rounded-full overflow-hidden">
                  <div 
                    className="absolute left-0 top-0 h-full bg-gradient-to-r from-red-500/60 to-red-500/30 rounded-l-full"
                    style={{ width: `${Math.min(50, (stats?.mae_mfe_analysis?.avg_mae_pct || 0) / ((stats?.mae_mfe_analysis?.avg_mae_pct || 0) + (stats?.mae_mfe_analysis?.avg_mfe_pct || 1)) * 100)}%` }}
                  />
                  <div 
                    className="absolute right-0 top-0 h-full bg-gradient-to-l from-green-500/60 to-green-500/30 rounded-r-full"
                    style={{ width: `${Math.min(50, (stats?.mae_mfe_analysis?.avg_mfe_pct || 0) / ((stats?.mae_mfe_analysis?.avg_mae_pct || 0) + (stats?.mae_mfe_analysis?.avg_mfe_pct || 1)) * 100)}%` }}
                  />
                  <div className="absolute inset-0 flex items-center justify-center text-[10px] font-mono">
                    <span className="text-red-400 mr-2">−{stats?.mae_mfe_analysis?.avg_mae_pct?.toFixed(1) || 0}%</span>
                    <span className="text-white/40">|</span>
                    <span className="text-green-400 ml-2">+{stats?.mae_mfe_analysis?.avg_mfe_pct?.toFixed(1) || 0}%</span>
                  </div>
                </div>
              </div>
              
              {/* Интерпретация */}
              <div className="p-3 bg-white/5 rounded-lg space-y-2 text-[11px]">
                <div className="font-mono uppercase opacity-60 text-[10px] mb-2">Интерпретация</div>
                {(stats?.mae_mfe_analysis?.avg_mae_pct || 0) < 1 && (
                  <div className="flex items-center gap-2 text-green-400">
                    <span className="w-1.5 h-1.5 rounded-full bg-green-500"></span>
                    Отличные точки входа! Средняя просадка менее 1%
                  </div>
                )}
                {(stats?.mae_mfe_analysis?.avg_mae_pct || 0) >= 1 && (stats?.mae_mfe_analysis?.avg_mae_pct || 0) < 3 && (
                  <div className="flex items-center gap-2 text-yellow-400">
                    <span className="w-1.5 h-1.5 rounded-full bg-yellow-500"></span>
                    Нормальные входы. Просадка в пределах нормы
                  </div>
                )}
                {(stats?.mae_mfe_analysis?.avg_mae_pct || 0) >= 3 && (
                  <div className="flex items-center gap-2 text-red-400">
                    <span className="w-1.5 h-1.5 rounded-full bg-red-500"></span>
                    Высокий MAE. Рассмотрите улучшение точек входа
                  </div>
                )}
                
                {(stats?.mae_mfe_analysis?.avg_efficiency || 0) < 50 && (
                  <div className="flex items-center gap-2 text-yellow-400">
                    <span className="w-1.5 h-1.5 rounded-full bg-yellow-500"></span>
                    Низкая эффективность. Вы забираете менее половины движения
                  </div>
                )}
                {(stats?.mae_mfe_analysis?.avg_efficiency || 0) >= 50 && (stats?.mae_mfe_analysis?.avg_efficiency || 0) < 80 && (
                  <div className="flex items-center gap-2 text-cyan-400">
                    <span className="w-1.5 h-1.5 rounded-full bg-cyan-500"></span>
                    Хорошая эффективность закрытия позиций
                  </div>
                )}
                {(stats?.mae_mfe_analysis?.avg_efficiency || 0) >= 80 && (
                  <div className="flex items-center gap-2 text-green-400">
                    <span className="w-1.5 h-1.5 rounded-full bg-green-500"></span>
                    Отличная эффективность! Вы улавливаете большую часть движения
                  </div>
                )}
                
                {(stats?.mae_mfe_analysis?.avg_mfe_pct || 0) > (stats?.mae_mfe_analysis?.avg_mae_pct || 0) * 1.5 && (
                  <div className="flex items-center gap-2 text-green-400">
                    <span className="w-1.5 h-1.5 rounded-full bg-green-500"></span>
                    MFE превышает MAE в {((stats?.mae_mfe_analysis?.avg_mfe_pct || 0) / (stats?.mae_mfe_analysis?.avg_mae_pct || 1)).toFixed(1)}x — положительное соотношение
                  </div>
                )}
              </div>
            </div>
          </div>

          <div className="cyber-card p-6 border-l-accent-secondary/30 relative overflow-hidden group">
            <div className="absolute -bottom-20 -left-20 w-40 h-40 bg-accent-secondary/10 rounded-full blur-3xl opacity-0 group-hover:opacity-100 transition-opacity duration-500" />
            
            <h2 className="text-sm font-mono uppercase mb-6 flex items-center gap-2 relative z-10">
              <Target size={16} className="text-accent-secondary" />
              {t.tagStats.title}
              <span className="ml-auto text-[10px] opacity-40">{stats?.tag_stats?.length || 0} tags</span>
            </h2>
            <div className="space-y-3 relative z-10">
              {stats?.tag_stats.length === 0 ? (
                <div className="empty-state py-8">
                  <Target size={24} className="text-accent-secondary/30 mx-auto mb-2" />
                  <p className="text-[10px] opacity-30 font-mono text-center">{t.tagStats.noTags}</p>
                </div>
              ) : (
                stats?.tag_stats.map((item, index) => (
                  <div 
                    key={item.tag} 
                    className="flex justify-between items-center border-b border-border pb-2 last:border-0 hover:bg-accent-secondary/5 p-2 -mx-2 rounded-lg transition-all cursor-default"
                    style={{ animationDelay: `${index * 0.05}s` }}
                  >
                    <div>
                      <div className="text-[10px] font-mono text-accent-secondary uppercase flex items-center gap-1">
                        <span className="opacity-30">#</span>{item.tag}
                      </div>
                      <div className="text-[9px] opacity-40">{item.count} trades</div>
                    </div>
                    <div className="text-right">
                      <div className={`text-xs font-bold ${Number(item.pnl) >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                        {Number(item.pnl) >= 0 ? '+' : ''}{formatCurrency(Number(item.pnl))}
                      </div>
                      <div className="text-[9px] opacity-60 flex items-center gap-1 justify-end">
                        <div className={`w-1 h-1 rounded-full ${Number(item.win_rate) >= 50 ? 'bg-green-400' : 'bg-red-400'}`} />
                        {item.win_rate}% WR
                      </div>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Terminal Log - only show when user has trades */}
      {hasData && (
        <div className="mt-8 cyber-card p-4 bg-black/50 border-t-2 border-accent/20 relative overflow-hidden">
          {/* Scan line animation */}
          <div className="absolute inset-0 pointer-events-none overflow-hidden">
            <div className="absolute top-0 left-0 right-0 h-px bg-gradient-to-r from-transparent via-accent/50 to-transparent animate-pulse" />
          </div>
          
          <div className="flex items-center gap-2 mb-3 opacity-50">
            <div className="w-2 h-2 bg-accent rounded-full animate-pulse" />
            <span className="text-[10px] font-mono uppercase tracking-widest">{t.logs.title}</span>
            <span className="text-[9px] opacity-50 ml-auto font-mono">{logs.length} entries</span>
          </div>
          <div className="space-y-1 font-mono text-[10px] max-h-32 overflow-y-auto scrollbar-thin scrollbar-thumb-accent/20 scrollbar-track-transparent">
            {logs.map((log, i) => (
              <div 
                key={i} 
                className={`flex gap-4 py-0.5 ${i === 0 ? 'text-accent' : 'opacity-60'} hover:opacity-100 transition-opacity`}
              >
                <span className="opacity-30 shrink-0">[{log.time}]</span>
                <span className="flex-1">
                  {i === 0 && <span className="text-accent mr-1">▸</span>}
                  {log.msg}
                </span>
              </div>
            ))}
            {logs.length === 0 && (
              <div className="opacity-20 italic py-4 text-center">
                <span className="animate-pulse">_</span> Awaiting system events...
              </div>
            )}
          </div>
        </div>
      )}
    </main>
  );
}
