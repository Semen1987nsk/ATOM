'use client';

import { useEffect, useState, useCallback } from 'react';
import Link from 'next/link';
import { Plus, Lock, Upload, BookOpen, History, Settings, Wallet, LogIn, BarChart3, HelpCircle, FileText } from 'lucide-react';
import { AddTradeModal } from '@/components/AddTradeModal';
import CloseTradeModal from '@/components/CloseTradeModal';
import { SettingsModal } from '@/components/SettingsModal';
import { ImportPreviewModal } from '@/components/ImportPreviewModal';
import { DepositManagerModal } from '@/components/DepositManagerModal';
import { LanguageSwitcher } from '@/components/LanguageSwitcher';
import ThemeToggle from '@/components/ThemeToggle';
import { FilterPanel, Filters } from '@/components/FilterPanel';
import { DashboardSkeleton } from '@/components/Skeleton';
import { useLanguage } from '@/i18n/LanguageContext';
import { useSettings } from '@/contexts/SettingsContext';
import { useAuth } from '@/contexts/AuthContext';
import {
  AuthButton,
  StatsGrid,
  AdvancedStatsGrid,
  EquityChart,
  RecentTradesCard,
  AIInsightsCard,
  MAEMFECard,
  PostExitCard,
  TagStatsCard,
  TerminalLog
} from '@/components/dashboard';

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
  avg_win: number;
  avg_loss: number;
  largest_win: number;
  largest_loss: number;
  max_win_streak: number;
  max_loss_streak: number;
  current_streak: number;
  current_streak_type: string | null;
  tail_ratio: number;
  calmar_ratio: { calmar_ratio: number; cagr_pct: number; max_drawdown_pct: number; rating: string };
  risk_of_ruin: { ror_20pct: number; ror_50pct: number; message: string };
  r_distribution: { pct_positive_r: number; pct_above_1r: number; pct_above_2r: number };
  trade_duration: { avg_duration_hours: number; avg_win_duration_hours: number; avg_loss_duration_hours: number; median_duration_hours: number };
  monte_carlo: { median_return: number; worst_case_5pct: number; best_case_95pct: number; ruin_probability: number };
  time_patterns: { best_day: { day: string; total_pnl: number } | null; worst_day: { day: string; total_pnl: number } | null };
  mae_mfe_analysis: { avg_mae_pct: number; avg_mfe_pct: number; avg_efficiency: number; trades_analyzed: number; recommendations: string[] };
  equity_curve: { date: string; balance: number }[];
  tag_stats: { tag: string; pnl: number; win_rate: number; count: number }[];
}

export default function Home() {
  const { t } = useLanguage();
  const { settings, formatCurrency } = useSettings();
  const { user } = useAuth();
  
  const [stats, setStats] = useState<DashboardData | null>(null);
  const [trades, setTrades] = useState<Trade[]>([]);
  const [loading, setLoading] = useState(true);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [isCloseModalOpen, setIsCloseModalOpen] = useState(false);
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const [isImportModalOpen, setIsImportModalOpen] = useState(false);
  const [isDepositModalOpen, setIsDepositModalOpen] = useState(false);
  const [isAuthRequiredOpen, setIsAuthRequiredOpen] = useState(false);
  const [selectedTradeToClose, setSelectedTradeToClose] = useState<Trade | null>(null);
  const [logs, setLogs] = useState<{msg: string, time: string}[]>([]);
  const [mounted, setMounted] = useState(false);
  
  const [filters, setFilters] = useState<Filters>({
    period: 'all',
    tag: undefined,
    limit: undefined,
    startDate: undefined,
    endDate: undefined
  });

  const hasData = trades.length > 0;

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
    // Если пользователь не авторизован - не загружаем данные
    if (!user) {
      setStats(null);
      setTrades([]);
      setLoading(false);
      return;
    }
    
    try {
      let statsUrl = '/stats/';
      const params = new URLSearchParams();
      const f = currentFilters || filters;
      
      if (f.period !== 'all') {
        params.append('period', f.period);
        if (f.period === 'custom' && f.startDate) {
          params.append('start_date', f.startDate);
          if (f.endDate) params.append('end_date', f.endDate);
        }
      }
      if (f.tag) params.append('tag', f.tag);
      if (f.limit) params.append('limit', f.limit.toString());
      if (settings.initialDeposit && settings.initialDeposit > 0) {
        params.append('initial_deposit', settings.initialDeposit.toString());
      }
      if (params.toString()) statsUrl += '?' + params.toString();

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
  }, [user, filters, settings.initialDeposit, t.logs.synchronized, t.logs.syncFailed]);

  useEffect(() => {
    setMounted(true);
    fetchData();
  }, [fetchData]);

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
          mae_price: exitPrice * 0.98,
          mfe_price: exitPrice * 1.02
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

  return (
    <main className="min-h-screen p-8 max-w-7xl mx-auto">
      {/* Header */}
      <header className="mb-12 flex justify-between items-start relative z-10">
        <div>
          <h1 className="text-4xl font-black tracking-tighter mb-2 italic">
            <span className="text-accent">Eqio</span>
          </h1>
          <p className="text-xs font-mono text-slate-400 uppercase tracking-[0.2em]">
            {t.app.subtitle}
          </p>
          <div className="mt-3 flex items-center gap-2 text-sm">
            <Wallet size={14} className="text-accent" />
            <span className="text-slate-400">Депозит:</span>
            <span className="font-bold text-accent">{formatCurrency(settings.initialDeposit)}</span>
            {stats?.total_pnl !== undefined && (
              <span className={`text-xs ${stats.total_pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                ({stats.total_pnl >= 0 ? '+' : ''}{((stats.total_pnl / settings.initialDeposit) * 100).toFixed(2)}%)
              </span>
            )}
          </div>
        </div>
        <div className="flex gap-3 flex-wrap justify-end items-center">
          <FilterPanel filters={filters} onChange={handleFiltersChange} getApiUrl={getApiUrl} />
          <div className="flex gap-2 items-center">
            <ThemeToggle />
            <button onClick={() => setIsSettingsOpen(true)} className="btn-secondary p-2.5 aspect-square" title="Настройки">
              <Settings size={14} />
            </button>
            <LanguageSwitcher />
            <AuthButton />
          </div>
          <Link href="/history" className="btn-secondary flex items-center gap-2">
            <History size={14} />
            {t.nav.tradeHistory}
          </Link>
          <Link href="/manual" className="btn-secondary flex items-center gap-2">
            <BookOpen size={14} />
            {t.nav.systemManual}
          </Link>
          <Link href="/blog" className="btn-secondary flex items-center gap-2">
            <FileText size={14} />
            {t.nav.blog}
          </Link>
          <Link href="/help" className="btn-secondary flex items-center gap-2">
            <HelpCircle size={14} />
            {t.nav.help}
          </Link>
          {user ? (
            <>
              <button onClick={() => setIsDepositModalOpen(true)} className="btn-secondary flex items-center gap-2" title="Управление депозитом">
                <Wallet size={14} />
              </button>
              <button onClick={() => setIsImportModalOpen(true)} className="btn-secondary flex items-center gap-2">
                <Upload size={14} />
                {t.nav.importData}
              </button>
              <button onClick={() => setIsModalOpen(true)} className="btn-primary flex items-center gap-2">
                <Plus size={14} /> {t.nav.logPosition}
              </button>
            </>
          ) : (
            <>
              <button onClick={() => setIsAuthRequiredOpen(true)} className="btn-secondary flex items-center gap-2" title="Управление депозитом">
                <Wallet size={14} />
              </button>
              <button onClick={() => setIsAuthRequiredOpen(true)} className="btn-secondary flex items-center gap-2">
                <Upload size={14} />
                {t.nav.importData}
              </button>
              <button onClick={() => setIsAuthRequiredOpen(true)} className="btn-primary flex items-center gap-2">
                <Plus size={14} /> {t.nav.logPosition}
              </button>
            </>
          )}
        </div>
      </header>

      {/* Modals */}
      <AddTradeModal 
        isOpen={isModalOpen} 
        onClose={() => setIsModalOpen(false)} 
        onSuccess={() => { fetchData(); addLog('New position initialized'); }} 
      />
      <CloseTradeModal
        isOpen={isCloseModalOpen}
        onClose={() => { setIsCloseModalOpen(false); setSelectedTradeToClose(null); }}
        onConfirm={handleCloseTradeConfirm}
        tradeTicker={selectedTradeToClose?.symbol}
        tradeDirection={selectedTradeToClose?.direction}
      />
      <SettingsModal isOpen={isSettingsOpen} onClose={() => setIsSettingsOpen(false)} />
      <ImportPreviewModal
        isOpen={isImportModalOpen}
        onClose={() => setIsImportModalOpen(false)}
        onSuccess={() => { fetchData(); addLog('Import completed'); }}
      />
      <DepositManagerModal
        isOpen={isDepositModalOpen}
        onClose={() => setIsDepositModalOpen(false)}
        onUpdate={() => { fetchData(); addLog('Deposit updated'); }}
      />

      {/* Auth Required Modal */}
      {isAuthRequiredOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
          <div className="absolute inset-0 bg-black/70 backdrop-blur-sm" onClick={() => setIsAuthRequiredOpen(false)} />
          <div className="relative cyber-card w-full max-w-md mx-4 p-6 text-center">
            <div className="w-16 h-16 mx-auto mb-4 rounded-full bg-accent/20 flex items-center justify-center">
              <Lock size={32} className="text-accent" />
            </div>
            <h2 className="text-xl font-bold mb-2">Требуется авторизация</h2>
            <p className="text-muted-foreground mb-6">
              Войдите в аккаунт, чтобы добавлять и импортировать сделки.
            </p>
            <div className="flex gap-3 justify-center">
              <button onClick={() => setIsAuthRequiredOpen(false)} className="btn-secondary px-6">Отмена</button>
              <Link href="/login" className="btn-primary px-6 flex items-center gap-2">
                <LogIn size={16} />
                Войти
              </Link>
            </div>
            <p className="text-xs text-muted-foreground mt-4">
              Нет аккаунта? <Link href="/register" className="text-accent hover:underline">Зарегистрируйтесь</Link>
            </p>
          </div>
        </div>
      )}

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
                <p className="text-sm opacity-60">{t.emptyState?.description || 'Import broker report or add your first trade'}</p>
              </div>
            </div>
            <div className="flex gap-3">
              {user ? (
                <>
                  <button onClick={() => setIsImportModalOpen(true)} className="btn-secondary flex items-center gap-2">
                    <Upload size={14} />
                    {t.emptyState?.importButton || 'Import'}
                  </button>
                  <button onClick={() => setIsModalOpen(true)} className="btn-primary flex items-center gap-2">
                    <Plus size={14} />
                    {t.emptyState?.addButton || 'Add'}
                  </button>
                </>
              ) : (
                <>
                  <button onClick={() => setIsAuthRequiredOpen(true)} className="btn-secondary flex items-center gap-2">
                    <Upload size={14} />
                    {t.emptyState?.importButton || 'Import'}
                  </button>
                  <button onClick={() => setIsAuthRequiredOpen(true)} className="btn-primary flex items-center gap-2">
                    <Plus size={14} />
                    {t.emptyState?.addButton || 'Add'}
                  </button>
                </>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Stats Grid */}
      <StatsGrid stats={stats} hasData={hasData} />

      {/* Advanced Stats */}
      <AdvancedStatsGrid stats={stats} hasData={hasData} />

      {/* Main Content Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="lg:col-span-2 space-y-4">
          <EquityChart data={stats?.equity_curve || []} />
          <RecentTradesCard
            trades={trades}
            onOpenCloseModal={openCloseModal}
            onDelete={handleDelete}
            onOpenAddModal={() => setIsModalOpen(true)}
          />
        </div>

        <div className="space-y-4">
          <AIInsightsCard
            recommendations={stats?.mae_mfe_analysis?.recommendations || []}
            optimalF={stats?.optimal_f || 0}
          />
          <MAEMFECard 
            analysis={stats?.mae_mfe_analysis} 
            onRecalculate={() => fetchData()}
            getApiUrl={getApiUrl}
          />
          <PostExitCard 
            tradesCount={trades.length}
            getApiUrl={getApiUrl}
            onRecalculate={() => fetchData()}
          />
          <TagStatsCard tagStats={stats?.tag_stats || []} />
        </div>
      </div>

      {/* Terminal Log */}
      {hasData && <TerminalLog logs={logs} />}
    </main>
  );
}
