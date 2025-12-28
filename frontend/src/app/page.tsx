'use client';

import { useEffect, useState, useCallback } from 'react';
import { StatsCard } from '@/components/StatsCard';
import { AddTradeModal } from '@/components/AddTradeModal';
import CloseTradeModal from '@/components/CloseTradeModal';
import { SettingsModal } from '@/components/SettingsModal';
import { LanguageSwitcher } from '@/components/LanguageSwitcher';
import { FilterPanel, Filters, Period } from '@/components/FilterPanel';
import { useLanguage, interpolate } from '@/i18n/LanguageContext';
import { useSettings } from '@/contexts/SettingsContext';
import Link from 'next/link';
import { Activity, TrendingUp, TrendingDown, Target, Zap, AlertTriangle, Plus, Lock, Download, Upload, Trash2, BookOpen, GitGraph, History, Shield, BarChart3, Flame, Scale, Skull, Dice5, LineChart as LineChartIcon, Clock, Calendar, Gauge, Brain, Settings, Wallet } from 'lucide-react';
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
  ahpr: number;
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
    avg_mae_ratio: number;
    avg_mfe_ratio: number;
    recommendations: string[];
  };
  equity_curve: { date: string; balance: number }[];
  tag_stats: { tag: string; pnl: number; win_rate: number; count: number }[];
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
  }, [filters, t.logs.synchronized, t.logs.syncFailed]);

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

  const handleExport = async () => {
    try {
      window.open(getApiUrl('/trades/export'), '_blank');
      addLog(t.logs.exporting);
    } catch (error) {
      console.error('Export failed:', error);
      addLog(t.logs.exportFailed);
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
      <header className="mb-12 flex justify-between items-start">
        <div>
          <h1 className="text-4xl font-black tracking-tighter mb-2 italic">
            <span className="text-accent">ATOM</span>
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
        <div className="flex gap-4 flex-wrap justify-end items-center">
          <FilterPanel
            filters={filters}
            onChange={handleFiltersChange}
            getApiUrl={getApiUrl}
          />
          <div className="flex gap-2">
            <button
              onClick={() => setIsSettingsOpen(true)}
              className="flex items-center gap-2 bg-surface border border-border px-3 py-2 rounded-none hover:bg-border transition-colors text-xs font-bold uppercase tracking-widest"
              title="Настройки"
            >
              <Settings size={14} />
            </button>
            <LanguageSwitcher />
          </div>
          <Link 
            href="/history"
            className="flex items-center gap-2 bg-surface border border-border px-4 py-2 rounded-none hover:bg-border transition-colors text-xs font-bold uppercase tracking-widest text-accent"
          >
            <History size={14} />
            {t.nav.tradeHistory}
          </Link>
          <Link 
            href="/manual"
            className="flex items-center gap-2 bg-surface border border-border px-4 py-2 rounded-none hover:bg-border transition-colors text-xs font-bold uppercase tracking-widest text-accent"
          >
            <BookOpen size={14} />
            {t.nav.systemManual}
          </Link>
          <label className="flex items-center gap-2 bg-surface border border-border px-4 py-2 rounded-none hover:bg-border transition-colors text-xs font-bold uppercase tracking-widest cursor-pointer">
            <input type="file" accept=".csv,.xlsx,.xls,.pdf" className="hidden" onChange={handleImport} />
            <Upload size={14} />
            {t.nav.importData}
          </label>
          <button 
            onClick={handleExport}
            className="flex items-center gap-2 bg-surface border border-border px-4 py-2 rounded-none hover:bg-border transition-colors text-xs font-bold uppercase tracking-widest"
          >
            <Download size={14} />
            {t.nav.exportCsv}
          </button>
          <button 
            onClick={() => setIsModalOpen(true)}
            className="bg-accent text-black px-6 py-2 font-bold text-xs uppercase tracking-widest hover:bg-white transition-colors flex items-center gap-2"
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

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        <StatsCard 
          title={t.stats.totalPnl.title} 
          value={formatCurrency(stats?.total_pnl || 0)} 
          description={t.stats.totalPnl.description}
          trend={stats?.total_pnl && stats.total_pnl > 0 ? 'up' : 'down'}
          icon={<TrendingUp size={18} />}
          tooltipText={t.stats.totalPnl.tooltip}
        />
        <StatsCard 
          title={t.stats.winRate.title} 
          value={`${stats?.win_rate.toFixed(1)}%`} 
          description={interpolate(t.stats.winRate.description, { profitable: stats?.profitable_trades || 0, total: stats?.total_trades || 0 })}
          icon={<Target size={18} />}
          tooltipText={t.stats.winRate.tooltip}
        />
        <StatsCard 
          title={t.stats.optimalF.title} 
          value={stats?.optimal_f || 0} 
          description={t.stats.optimalF.description}
          icon={<Zap size={18} />}
          tooltipText={t.stats.optimalF.tooltip}
        />
        <StatsCard 
          title={t.stats.sqn.title} 
          value={stats?.sqn?.sqn || 0} 
          description={stats?.sqn?.rating || t.stats.sqn.description}
          icon={<Activity size={18} />}
          tooltipText={t.stats.sqn.tooltip}
        />
        <StatsCard 
          title={t.stats.zScore.title} 
          value={stats?.z_score?.z_score || 0} 
          description={stats?.z_score?.verdict || t.stats.zScore.description}
          icon={<GitGraph size={18} />}
          tooltipText={stats?.z_score?.description || t.stats.zScore.tooltip}
        />
        <StatsCard 
          title={t.stats.profitFactor.title} 
          value={stats?.profit_factor || 0} 
          description={t.stats.profitFactor.description}
          icon={<TrendingUp size={18} />}
          tooltipText={t.stats.profitFactor.tooltip}
        />
        <StatsCard 
          title={t.stats.rExpectancy.title} 
          value={`${stats?.r_expectancy || 0}R`} 
          description={t.stats.rExpectancy.description}
          icon={<Target size={18} />}
          tooltipText={t.stats.rExpectancy.tooltip}
        />
        <StatsCard 
          title={t.stats.recoveryFactor.title} 
          value={stats?.recovery_factor || 0} 
          description={t.stats.recoveryFactor.description}
          icon={<Activity size={18} />}
          tooltipText={t.stats.recoveryFactor.tooltip}
        />
        <StatsCard 
          title={t.stats.ahpr.title} 
          value={stats?.ahpr || 0} 
          description={t.stats.ahpr.description}
          icon={<TrendingUp size={18} />}
          tooltipText={t.stats.ahpr.tooltip}
        />
        <StatsCard 
          title={t.stats.sortinoRatio.title} 
          value={stats?.sortino_ratio || 0} 
          description={t.stats.sortinoRatio.description}
          icon={<Shield size={18} />}
          tooltipText={t.stats.sortinoRatio.tooltip}
        />
        <StatsCard 
          title={t.stats.maxDrawdown.title} 
          value={`${stats?.max_drawdown_pct?.toFixed(1) || 0}%`} 
          description={`${formatCurrency(stats?.max_drawdown_abs || 0)}`}
          trend="down"
          icon={<TrendingDown size={18} />}
          tooltipText={t.stats.maxDrawdown.tooltip}
        />
        <StatsCard 
          title={t.stats.currentDrawdown.title} 
          value={`${stats?.current_drawdown_pct?.toFixed(1) || 0}%`} 
          description={t.stats.currentDrawdown.description}
          trend={stats?.current_drawdown_pct && stats.current_drawdown_pct > 5 ? 'down' : undefined}
          icon={<Activity size={18} />}
          tooltipText={t.stats.currentDrawdown.tooltip}
        />
        <StatsCard 
          title={t.stats.tailRatio.title} 
          value={stats?.tail_ratio?.toFixed(2) || 0} 
          description={t.stats.tailRatio.description}
          icon={<BarChart3 size={18} />}
          tooltipText={t.stats.tailRatio.tooltip}
        />
        <StatsCard 
          title={t.stats.winStreak.title} 
          value={stats?.max_win_streak || 0} 
          description={`${interpolate(t.stats.winStreak.description, { current: stats?.current_streak || 0 })} ${stats?.current_streak_type === 'win' ? '🟢' : stats?.current_streak_type === 'loss' ? '🔴' : ''}`}
          icon={<Flame size={18} />}
          tooltipText={t.stats.winStreak.tooltip}
        />
        <StatsCard 
          title={t.stats.lossStreak.title} 
          value={stats?.max_loss_streak || 0} 
          description={t.stats.lossStreak.description}
          trend="down"
          icon={<AlertTriangle size={18} />}
          tooltipText={t.stats.lossStreak.tooltip}
        />
        <StatsCard 
          title={t.stats.avgWinLoss.title} 
          value={formatCurrency(stats?.avg_win || 0)} 
          description={`${settings.currencySymbol}${Math.abs(stats?.avg_loss || 0).toFixed(0)}`}
          icon={<Scale size={18} />}
          tooltipText={t.stats.avgWinLoss.tooltip}
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
            value={`${((stats?.risk_of_ruin?.ror_20pct || 0) * 100).toFixed(1)}%`} 
            description={t.advancedStats.ror20.description}
            trend={stats?.risk_of_ruin?.ror_20pct && stats.risk_of_ruin.ror_20pct > 0.1 ? 'down' : undefined}
            icon={<Skull size={18} />}
            tooltipText={t.advancedStats.ror20.tooltip}
          />
          <StatsCard 
            title={t.advancedStats.ror50.title}
            value={`${((stats?.risk_of_ruin?.ror_50pct || 0) * 100).toFixed(2)}%`} 
            description={t.advancedStats.ror50.description}
            trend={stats?.risk_of_ruin?.ror_50pct && stats.risk_of_ruin.ror_50pct > 0.01 ? 'down' : undefined}
            icon={<Skull size={18} />}
            tooltipText={t.advancedStats.ror50.tooltip}
          />
          <StatsCard 
            title={t.advancedStats.monteCarlo5.title}
            value={`${((stats?.monte_carlo?.worst_case_5pct || 0) * 100).toFixed(1)}%`} 
            description={t.advancedStats.monteCarlo5.description}
            trend="down"
            icon={<Dice5 size={18} />}
            tooltipText={t.advancedStats.monteCarlo5.tooltip}
          />
          <StatsCard 
            title={t.advancedStats.monteCarloMedian.title}
            value={`${((stats?.monte_carlo?.median_return || 0) * 100).toFixed(1)}%`} 
            description={t.advancedStats.monteCarloMedian.description}
            trend={stats?.monte_carlo?.median_return && stats.monte_carlo.median_return > 0 ? 'up' : 'down'}
            icon={<LineChartIcon size={18} />}
            tooltipText={t.advancedStats.monteCarloMedian.tooltip}
          />
          <StatsCard 
            title={t.advancedStats.rDistribution.title}
            value={`${stats?.r_distribution?.pct_above_1r?.toFixed(0) || 0}%`} 
            description={interpolate(t.advancedStats.rDistribution.description, { pct: stats?.r_distribution?.pct_above_2r?.toFixed(0) || 0 })}
            icon={<BarChart3 size={18} />}
            tooltipText={t.advancedStats.rDistribution.tooltip}
          />
          <StatsCard 
            title={t.advancedStats.tradeDuration.title}
            value={`${stats?.trade_duration?.avg_duration_hours?.toFixed(1) || 0}h`} 
            description={interpolate(t.advancedStats.tradeDuration.description, { win: stats?.trade_duration?.avg_win_duration_hours?.toFixed(1) || 0, loss: stats?.trade_duration?.avg_loss_duration_hours?.toFixed(1) || 0 })}
            icon={<Clock size={18} />}
            tooltipText={t.advancedStats.tradeDuration.tooltip}
          />
          <StatsCard 
            title={t.advancedStats.bestDay.title}
            value={stats?.time_patterns?.best_day?.day ? (t.days as Record<string, string>)[stats.time_patterns.best_day.day] || stats.time_patterns.best_day.day : 'N/A'} 
            description={`PnL: ${formatCurrency(stats?.time_patterns?.best_day?.total_pnl || 0)}`}
            icon={<Calendar size={18} />}
            tooltipText={t.advancedStats.bestDay.tooltip}
          />
          <StatsCard 
            title={t.advancedStats.maeMfe.title}
            value={stats?.mae_mfe_analysis?.avg_mae_ratio?.toFixed(2) || 0} 
            description={interpolate(t.advancedStats.maeMfe.description, { mfe: stats?.mae_mfe_analysis?.avg_mfe_ratio?.toFixed(2) || 0 })}
            icon={<Gauge size={18} />}
            tooltipText={t.advancedStats.maeMfe.tooltip}
          />
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="lg:col-span-2 space-y-4">
          <div className="cyber-card p-6">
            <h2 className="text-sm font-mono uppercase mb-6 flex items-center gap-2">
              <Activity size={16} className="text-accent" />
              {t.charts.equityCurve}
            </h2>
            <div className="h-[250px] w-full">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={stats?.equity_curve || []}>
                  <defs>
                    <linearGradient id="colorBalance" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#00ff9f" stopOpacity={0.3}/>
                      <stop offset="95%" stopColor="#00ff9f" stopOpacity={0}/>
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1a1a1a" vertical={false} />
                  <XAxis 
                    dataKey="date" 
                    stroke="#444" 
                    fontSize={10} 
                    tickLine={false} 
                    axisLine={false}
                    tickFormatter={(str) => str.split(' ')[0]} 
                  />
                  <YAxis 
                    stroke="#444" 
                    fontSize={10} 
                    tickLine={false} 
                    axisLine={false}
                    tickFormatter={(val) => `${settings.currencySymbol}${val}`}
                  />
                  <Tooltip 
                    contentStyle={{ backgroundColor: '#0d0d0d', border: '1px solid #1a1a1a', fontSize: '12px' }}
                    itemStyle={{ color: '#00ff9f' }}
                  />
                  <Area 
                    type="monotone" 
                    dataKey="balance" 
                    stroke="#00ff9f" 
                    fillOpacity={1} 
                    fill="url(#colorBalance)" 
                    strokeWidth={2}
                  />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </div>

          <div className="cyber-card p-6">
            <div className="flex justify-between items-center mb-6">
              <h2 className="text-sm font-mono uppercase flex items-center gap-2">
                <Activity size={16} className="text-accent" />
                {t.charts.recentTrades}
              </h2>
              <Link href="/history" className="text-[10px] font-mono text-accent hover:underline">
                {t.charts.viewAll}
              </Link>
            </div>
            <div className="space-y-4">
              {filteredTrades.length === 0 ? (
                <div className="text-center py-8 opacity-30 font-mono">{t.charts.noTrades}</div>
              ) : (
                filteredTrades.slice(0, 5).map((trade) => ( // Show only last 5 trades
                  <div key={trade.id} className="border-b border-border pb-4 last:border-0">
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
                          <span key={tag} className="text-[9px] font-mono border border-border px-1.5 opacity-50">
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
          <div className="cyber-card p-6 border-l-accent/30">
            <h2 className="text-sm font-mono uppercase mb-6 flex items-center gap-2">
              <AlertTriangle size={16} className="text-accent" />
              AI Insights
            </h2>
            <div className="space-y-4">
              {stats?.mae_mfe_analysis?.recommendations.map((rec, i) => (
                <div key={i} className="p-3 bg-accent/5 border-l-2 border-accent text-sm">
                  {rec}
                </div>
              ))}
              <div className="p-3 bg-accent-secondary/5 border-l-2 border-accent-secondary text-sm opacity-80">
                Optimal f: {((stats?.optimal_f || 0) * 10).toFixed(1)}%
              </div>
            </div>
          </div>

          <div className="cyber-card p-6 border-l-accent-secondary/30">
            <h2 className="text-sm font-mono uppercase mb-6 flex items-center gap-2">
              <Target size={16} className="text-accent-secondary" />
              {t.tagStats.title}
            </h2>
            <div className="space-y-3">
              {stats?.tag_stats.length === 0 ? (
                <div className="text-center py-4 opacity-30 font-mono text-[10px]">{t.tagStats.noTags}</div>
              ) : (
                stats?.tag_stats.map((item) => (
                  <div key={item.tag} className="flex justify-between items-center border-b border-border pb-2 last:border-0">
                    <div>
                      <div className="text-[10px] font-mono text-accent-secondary uppercase">#{item.tag}</div>
                      <div className="text-[9px] opacity-40">{item.count} trades</div>
                    </div>
                    <div className="text-right">
                      <div className={`text-xs font-bold ${Number(item.pnl) >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                        {Number(item.pnl) >= 0 ? '+' : ''}{formatCurrency(Number(item.pnl))}
                      </div>
                      <div className="text-[9px] opacity-60">{item.win_rate}% WR</div>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Terminal Log */}
      <div className="mt-8 cyber-card p-4 bg-black/50 border-t-2 border-accent/20">
        <div className="flex items-center gap-2 mb-2 opacity-50">
          <div className="w-2 h-2 bg-accent rounded-full animate-pulse" />
          <span className="text-[10px] font-mono uppercase tracking-widest">{t.logs.title}</span>
        </div>
        <div className="space-y-1">
          {logs.map((log, i) => (
            <div key={i} className="font-mono text-[10px] flex gap-4">
              <span className="opacity-30">[{log.time}]</span>
              <span className={i === 0 ? 'text-accent' : 'opacity-60'}>
                {i === 0 ? '> ' : '  '}{log.msg}
              </span>
            </div>
          ))}
          {logs.length === 0 && (
            <div className="font-mono text-[10px] opacity-20 italic">...</div>
          )}
        </div>
      </div>
    </main>
  );
}
