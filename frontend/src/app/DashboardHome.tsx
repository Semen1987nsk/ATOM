'use client';

import { useEffect, useState, useCallback } from 'react';
import Link from 'next/link';
import { Plus, Lock, Upload, LogIn, BarChart3, Target, Brain, Activity, Clock, ArrowRight, Tag, Wallet } from 'lucide-react';
import { AddTradeModal } from '@/components/AddTradeModal';
import CloseTradeModal from '@/components/CloseTradeModal';
import { SettingsModal } from '@/components/SettingsModal';
import { ImportPreviewModal } from '@/components/ImportPreviewModal';
import { DepositManagerModal } from '@/components/DepositManagerModal';
import { SetupManagerModal } from '@/components/SetupManagerModal';
import BrokerConnectModal from '@/components/BrokerConnectModal';
import SyncStatusIndicator from '@/components/SyncStatusIndicator';
import { FilterPanel, Filters } from '@/components/FilterPanel';
import { DashboardSkeleton } from '@/components/Skeleton';
import { AppShell } from '@/components/AppShell';
import { useLanguage } from '@/i18n/LanguageContext';
import { useSettings } from '@/contexts/SettingsContext';
import { useAuth } from '@/contexts/AuthContext';
import {
  StatsGrid,
  AdvancedStatsGrid,
  AdvancedMetricsGrid,
  BenchmarkingView,
  EquityCurveCard,
} from '@/components/dashboard';
import PortfolioCard from '@/components/dashboard/PortfolioCard';
import { api } from '@/lib/apiClient';

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
  entry_at: string;
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
  unrealized_pnl?: number;
  total_pnl_with_unrealized?: number;
  initial_balance?: number | null;
  current_balance?: number | null;
  period_start_balance?: number | null;
  period_end_balance?: number | null;
  period_start_date?: string | null;
  period_start_net_deposit?: number;
  period_start_realized_pnl?: number;
  period_start_balance_reliable?: boolean;
  period_start_balance_source?: string;
  period_start_balance_reason?: string | null;
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
  imoex_curve?: { date: string; value: number }[];
  tag_stats: { tag: string; pnl: number; win_rate: number; count: number }[];
}

export default function DashboardHome() {
  const { t } = useLanguage();
  const { settings, formatCurrency } = useSettings();
  const { user, isLoading: authLoading } = useAuth();

  const [stats, setStats] = useState<DashboardData | null>(null);
  const [trades, setTrades] = useState<Trade[]>([]);
  const [loading, setLoading] = useState(true);
  const [actionInProgress, setActionInProgress] = useState(false);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [isCloseModalOpen, setIsCloseModalOpen] = useState(false);
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const [isImportModalOpen, setIsImportModalOpen] = useState(false);
  const [isDepositModalOpen, setIsDepositModalOpen] = useState(false);
  const [isSetupModalOpen, setIsSetupModalOpen] = useState(false);
  const [isBrokerModalOpen, setIsBrokerModalOpen] = useState(false);
  const [isAuthRequiredOpen, setIsAuthRequiredOpen] = useState(false);
  const [selectedTradeToClose, setSelectedTradeToClose] = useState<Trade | null>(null);

  // Tab-state дашборда. Persist в localStorage чтобы юзер вернулся туда же.
  type DashTab = 'overview' | 'advanced' | 'benchmark';
  const [activeTab, setActiveTab] = useState<DashTab>('overview');
  const [advancedData, setAdvancedData] = useState<unknown | null>(null);
  const [benchmarkData, setBenchmarkData] = useState<unknown | null>(null);
  const [advancedLoading, setAdvancedLoading] = useState(false);
  const [benchmarkLoading, setBenchmarkLoading] = useState(false);
  // Раздельные «tried» флаги — без них useEffect-зависимость от *Data
  // создаёт бесконечный fetch при ошибке (data остаётся null → triggers retry).
  const [advancedTried, setAdvancedTried] = useState(false);
  const [benchmarkTried, setBenchmarkTried] = useState(false);
  // Logs state — TerminalLog уехал из дашборда, но addLog продолжает копить
  // события: на Phase 5 это станет источником для notification-center в шапке.
  const [, setLogs] = useState<{msg: string, time: string}[]>([]);
  const [mounted, setMounted] = useState(false);

  const [filters, setFilters] = useState<Filters>({
    period: 'all',
    tag: undefined,
    limit: undefined,
    startDate: undefined,
    endDate: undefined
  });

  const effectiveInitialDeposit = stats?.period_start_balance_reliable !== false && stats?.period_start_balance && stats.period_start_balance > 0
    ? stats.period_start_balance
    : null;

  const hasScopedPeriodFilter = Boolean(
    settings.tradesStartTradeId ||
    settings.tradesStartDate ||
    filters.period !== 'all' ||
    filters.tag ||
    filters.limit
  );

  const capitalLabel = hasScopedPeriodFilter ? 'Капитал на старт периода:' : 'Стартовый капитал:';

  const totalPnlWithUnrealized = stats ? (stats.total_pnl_with_unrealized ?? stats.total_pnl) : null;
  const totalPnlPct = effectiveInitialDeposit && totalPnlWithUnrealized !== null
    ? (totalPnlWithUnrealized / effectiveInitialDeposit) * 100
    : null;

  const hasData = trades.length > 0;

  const addLog = (msg: string) => {
    const time = new Date().toLocaleTimeString();
    setLogs(prev => [{msg, time}, ...prev].slice(0, 5));
  };

  const fetchData = useCallback(async () => {
    // Если пользователь не авторизован - не загружаем данные
    if (!user) {
      setStats(null);
      setTrades([]);
      setLoading(false);
      return;
    }

    setLoading(true);
    try {
      let statsUrl = '/stats/';
      const params = new URLSearchParams();
      const f = filters;

      // Применяем глобальную настройку tradesStartDate/tradesStartTradeId
      if (settings.tradesStartTradeId) {
        params.append('start_trade_id', settings.tradesStartTradeId.toString());
      } else if (settings.tradesStartDate) {
        params.append('period', 'custom');
        params.append('start_date', settings.tradesStartDate);
      } else if (f.period !== 'all') {
        params.append('period', f.period);
        if (f.period === 'custom' && f.startDate) {
          params.append('start_date', f.startDate);
          if (f.endDate) params.append('end_date', f.endDate);
        }
      }
      if (f.tag) params.append('tag', f.tag);
      if (f.limit) params.append('limit', f.limit.toString());
      if (settings.maeCalculationMethod) {
        params.append('mae_method', settings.maeCalculationMethod);
      }
      if (params.toString()) statsUrl += '?' + params.toString();

      const [statsData, tradesData] = await Promise.all([
        api.get<DashboardData>(statsUrl),
        api.get<Trade[]>('/trades/')
      ]);
      setStats(statsData);
      // Фильтруем сделки по дате/сделке начала из настроек
      let filteredTrades = Array.isArray(tradesData) ? tradesData : [];
      if (settings.tradesStartTradeId) {
        // Находим сделку и фильтруем по её времени
        const startTrade = filteredTrades.find((t: Trade) => t.id === settings.tradesStartTradeId);
        if (startTrade) {
          const startTime = new Date(startTrade.entry_at);
          filteredTrades = filteredTrades.filter((t: Trade) => new Date(t.entry_at) >= startTime);
        }
      } else if (settings.tradesStartDate) {
        const startDate = new Date(settings.tradesStartDate);
        filteredTrades = filteredTrades.filter((t: Trade) => new Date(t.entry_at) >= startDate);
      }
      setTrades(filteredTrades.reverse());
      addLog(t.logs.synchronized);
    } catch (error) {
      console.error('Failed to fetch data:', error);
      addLog(t.logs.syncFailed);
    } finally {
      setLoading(false);
    }
  }, [user, filters, settings.maeCalculationMethod, settings.tradesStartDate, settings.tradesStartTradeId, t.logs.synchronized, t.logs.syncFailed]);

  useEffect(() => {
    setMounted(true);
    fetchData();
  }, [fetchData]);

  // Lazy-fetch продвинутых табов. При переключении на «advanced» / «benchmark»
  // догружаем именно их payload — не трогаем основной /stats/ запрос.
  // Идемпотентно: tried-флаги предотвращают retry при ошибке.
  useEffect(() => {
    if (!user) return;
    if (activeTab === 'advanced' && !advancedTried) {
      setAdvancedTried(true);
      setAdvancedLoading(true);
      api.get('/stats/advanced')
        .then(setAdvancedData)
        .catch((e) => { console.error('advanced fetch failed', e); setAdvancedData(null); })
        .finally(() => setAdvancedLoading(false));
    }
    if (activeTab === 'benchmark' && !benchmarkTried) {
      setBenchmarkTried(true);
      setBenchmarkLoading(true);
      api.get('/stats/benchmark')
        .then(setBenchmarkData)
        .catch((e) => { console.error('benchmark fetch failed', e); setBenchmarkData(null); })
        .finally(() => setBenchmarkLoading(false));
    }
  }, [activeTab, user, advancedTried, benchmarkTried]);

  const handleFiltersChange = (newFilters: Filters) => {
    setFilters(newFilters);
    // fetchData will be triggered automatically via useEffect when filters state changes
    // (fetchData depends on filters via useCallback deps) — no need to call it here
  };

  const openCloseModal = (trade: Trade) => {
    setSelectedTradeToClose(trade);
    setIsCloseModalOpen(true);
  };

  const handleCloseTradeConfirm = async (exitPrice: number, exitReason: string) => {
    if (!selectedTradeToClose || actionInProgress) return;
    setActionInProgress(true);
    try {
      await api.patch(`/trades/${selectedTradeToClose.id}/close`, {
        body: {
          exit_price: exitPrice,
          exit_at: new Date().toISOString(),
          exit_reason: exitReason
        }
      });
      fetchData();
      addLog(`${t.logs.positionClosed}: ${selectedTradeToClose.id}`);
    } catch (error) {
      console.error('Failed to close trade:', error);
      addLog(t.logs.closeFailed);
    } finally {
      setActionInProgress(false);
    }
  };

  const handleDelete = async (tradeId: number) => {
    if (actionInProgress) return;
    if (!confirm('Вы уверены, что хотите удалить эту сделку?')) return;
    setActionInProgress(true);
    try {
      await api.delete(`/trades/${tradeId}`);
      fetchData();
      addLog(`${t.logs.tradePurged}: ${tradeId}`);
    } catch (error) {
      console.error('Delete failed:', error);
      addLog(t.logs.purgeFailed);
    } finally {
      setActionInProgress(false);
    }
  };

  if (!mounted) return null;
  if (authLoading || loading) return <DashboardSkeleton />;

  // Page-specific controls для AppShell.headerRight.
  // FilterPanel переехал в body (см. ниже) — popover'ы из header перекрывали search.
  // В хедере оставляем только контекстные icon-кнопки и переключатели.
  const headerActions = (
    <div className="hidden lg:flex items-center gap-1.5">
      <SyncStatusIndicator
        onTradesUpdated={fetchData}
        onOpenBrokerModal={() => setIsBrokerModalOpen(true)}
      />
      <button
        onClick={() => setIsDepositModalOpen(true)}
        className="btn-icon"
        title="Управление депозитом"
      >
        <Wallet size={14} />
      </button>
      <button
        onClick={() => setIsSetupModalOpen(true)}
        className="btn-icon"
        title="Управление сетапами"
      >
        <Target size={14} />
      </button>
      <button
        onClick={() => setIsImportModalOpen(true)}
        className="btn-icon"
        title="Импорт сделок"
      >
        <Upload size={14} />
      </button>
    </div>
  );

  return (
    <AppShell
      pageTitle="Дашборд"
      headerRight={headerActions}
      onAddTrade={() => setIsModalOpen(true)}
      onImport={() => setIsImportModalOpen(true)}
    >
      <div className="p-6 md:p-8 max-w-7xl mx-auto">
        {/* Заголовок страницы + сводка по балансу (вместо старого header) */}
        <div className="mb-8 flex flex-wrap items-end justify-between gap-3">
          <div>
            <h1 className="text-3xl font-bold tracking-tight mb-1">Дашборд</h1>
            <div className="flex items-center gap-2 text-sm flex-wrap text-[var(--text-secondary)]">
              <Wallet size={14} className="text-[var(--accent)]" />
              <span>{capitalLabel}</span>
              <span className="font-semibold text-[var(--foreground)]">
                {effectiveInitialDeposit ? formatCurrency(effectiveInitialDeposit) : 'недоступно'}
              </span>
              {totalPnlPct !== null && totalPnlWithUnrealized !== null && (
                <span
                  className={`text-xs font-medium ${
                    totalPnlWithUnrealized >= 0
                      ? 'text-[var(--success)]'
                      : 'text-[var(--danger)]'
                  }`}
                >
                  ({totalPnlWithUnrealized >= 0 ? '+' : ''}{totalPnlPct.toFixed(2)}%)
                </span>
              )}
              {stats?.period_start_balance_reliable === false && stats?.period_start_balance_reason && (
                <span className="text-xs text-[var(--warning)]">{stats.period_start_balance_reason}</span>
              )}
              {settings.tradesStartDate && (
                <span className="badge badge-accent">
                  📅 С{' '}
                  {settings.tradesStartTradeSymbol
                    ? `${settings.tradesStartTradeSymbol} (${new Date(settings.tradesStartDate).toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit' })})`
                    : new Date(settings.tradesStartDate).toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit', year: '2-digit' })}
                </span>
              )}
            </div>
          </div>

          {/* Mobile-only action-кнопки (на десктопе они в headerRight) */}
          <div className="lg:hidden flex items-center gap-2">
            <button onClick={() => setIsImportModalOpen(true)} className="btn-icon" title="Импорт">
              <Upload size={14} />
            </button>
          </div>
        </div>

        {/* FilterPanel — отдельной строкой над контентом.
            Раньше жил в header, но popover дропдаунов конфликтовал с search.
            Теперь это полноценный filter-bar страницы. */}
        <div className="mb-5">
          <FilterPanel filters={filters} onChange={handleFiltersChange} />
        </div>

        {/* Tab-switcher — Обзор / Продвинутая / Сравнение.
            Базовый дашборд (Stats) → "Обзор". Quant-метрики (Ulcer, K-Ratio,
            heatmap, mistakes) → "Продвинутая". Анонимное сравнение с когортой → "Сравнение". */}
        <div className="mb-6 flex gap-1 border-b border-[var(--border)]">
          {([
            { key: 'overview', label: 'Обзор', icon: <BarChart3 size={14} /> },
            { key: 'advanced', label: 'Продвинутая', icon: <Activity size={14} /> },
            { key: 'benchmark', label: 'Сравнение', icon: <Target size={14} /> },
          ] as Array<{ key: DashTab; label: string; icon: React.ReactNode }>).map((tab) => (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              className={`flex items-center gap-1.5 px-4 py-2.5 text-[13px] font-medium border-b-2 -mb-px transition-colors ${
                activeTab === tab.key
                  ? 'border-[var(--accent)] text-[var(--foreground)]'
                  : 'border-transparent text-[var(--text-secondary)] hover:text-[var(--foreground)]'
              }`}
            >
              {tab.icon}
              {tab.label}
            </button>
          ))}
        </div>

      {/* Modals */}
      <AddTradeModal
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        onSuccess={() => { fetchData(); addLog('Новая позиция создана'); }}
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
        onSuccess={() => { fetchData(); addLog('Импорт завершён'); }}
      />
      <DepositManagerModal
        isOpen={isDepositModalOpen}
        onClose={() => setIsDepositModalOpen(false)}
        onUpdate={() => { fetchData(); addLog('Депозит обновлён'); }}
      />
      <SetupManagerModal
        isOpen={isSetupModalOpen}
        onClose={() => setIsSetupModalOpen(false)}
      />
      <BrokerConnectModal
        isOpen={isBrokerModalOpen}
        onClose={() => setIsBrokerModalOpen(false)}
        onConnectionChange={() => { fetchData(); addLog('Синхронизация с брокером завершена'); }}
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
        <div className="mb-8 rounded-[var(--radius-xl)] border border-[var(--accent)]/30 bg-gradient-to-r from-[var(--accent-soft)] to-transparent p-6 md:p-7">
          <div className="flex items-start gap-4 mb-5">
            <div className="w-12 h-12 flex-shrink-0 rounded-[var(--radius-lg)] bg-[var(--accent-soft)] text-[var(--accent)] flex items-center justify-center">
              <BarChart3 size={22} />
            </div>
            <div className="min-w-0 flex-1">
              <h3 className="text-[17px] font-semibold leading-tight mb-1">
                {t.emptyState?.title || 'Начните вести журнал сделок'}
              </h3>
              <p className="text-[14px] text-[var(--text-secondary)] leading-relaxed">
                {t.emptyState?.description || 'Импортируйте отчёт брокера или добавьте первую сделку вручную, чтобы увидеть аналитику.'}
              </p>
            </div>
          </div>
          <div className="flex flex-wrap gap-2 pl-16">
            <button
              onClick={() => user ? setIsModalOpen(true) : setIsAuthRequiredOpen(true)}
              className="btn-primary"
            >
              <Plus size={14} />
              Добавить сделку
            </button>
            <button
              onClick={() => user ? setIsImportModalOpen(true) : setIsAuthRequiredOpen(true)}
              className="btn-secondary"
            >
              <Upload size={14} />
              Импорт отчёта
            </button>
          </div>
        </div>
      )}

      {/* ===== TAB CONTENT ===== */}
      {activeTab === 'overview' && (
        <>
          {/* Equity Curve — главный график «как развивается мой счёт».
              До этого данные фетчались но никогда не рисовались. */}
          <EquityCurveCard
            data={stats?.equity_curve}
            benchmark={stats?.imoex_curve}
            benchmarkLabel="IMOEX"
            initialBalance={effectiveInitialDeposit ?? undefined}
            formatCurrency={formatCurrency}
          />

          {/* Stats Grid */}
          <StatsGrid stats={stats} hasData={hasData} />

          {/* Advanced Stats */}
          <AdvancedStatsGrid stats={stats} hasData={hasData} />

          {/* Portfolio widget — текущее состояние счёта */}
          <div className="mt-6">
            <PortfolioCard />
          </div>
        </>
      )}

      {activeTab === 'advanced' && (
        <AdvancedMetricsGrid
          data={advancedData as React.ComponentProps<typeof AdvancedMetricsGrid>['data']}
          loading={advancedLoading}
        />
      )}

      {activeTab === 'benchmark' && (
        <BenchmarkingView
          data={benchmarkData as React.ComponentProps<typeof BenchmarkingView>['data']}
          loading={benchmarkLoading}
        />
      )}

      {/* Глубокий анализ — teaser-row.
          Только в Overview — на других табах дублирование избыточно. */}
      {activeTab === 'overview' && hasData && (
        <div className="mt-10">
          <div className="mb-4 flex items-end justify-between gap-3">
            <div>
              <h2 className="text-lg font-semibold tracking-tight">Глубокий анализ</h2>
              <p className="text-[13px] text-[var(--text-secondary)] mt-0.5">
                Открой любой раздел, чтобы погрузиться в детали.
              </p>
            </div>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
            {[
              {
                href: '/analysis/insights',
                title: 'AI-инсайты',
                desc: 'Рекомендации и риск-tier по Optimal f.',
                Icon: Brain,
                tone: 'violet' as const,
              },
              {
                href: '/analysis/mae-mfe',
                title: 'MAE / MFE',
                desc: 'Edge ratio, quality score, оптимизация стопов.',
                Icon: Target,
                tone: 'indigo' as const,
              },
              {
                href: '/analysis/post-exit',
                title: 'Post-Exit',
                desc: 'Что было после выхода. Реальные свечи MOEX.',
                Icon: Clock,
                tone: 'amber' as const,
              },
              {
                href: '/analysis/tags',
                title: 'По тегам',
                desc: 'Какие сетапы реально работают на ваших сделках.',
                Icon: Tag,
                tone: 'emerald' as const,
              },
            ].map((card) => {
              const toneClass = {
                violet: 'bg-[#6d28d922] text-[#a78bfa]',
                indigo: 'bg-[var(--accent-soft)] text-[var(--accent)]',
                amber: 'bg-[var(--warning-soft)] text-[var(--warning)]',
                emerald: 'bg-[var(--success-soft)] text-[var(--success)]',
              }[card.tone];
              return (
                <Link
                  key={card.href}
                  href={card.href}
                  className="group flex flex-col gap-3 p-4 rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--surface-1)] hover:border-[var(--border-strong)] hover:bg-[var(--surface-hover)] transition-colors no-underline"
                >
                  <div className="flex items-center justify-between">
                    <div className={`w-9 h-9 rounded-[var(--radius-md)] flex items-center justify-center ${toneClass}`}>
                      <card.Icon size={18} />
                    </div>
                    <ArrowRight
                      size={14}
                      className="text-[var(--text-tertiary)] group-hover:text-[var(--accent)] transition-colors"
                    />
                  </div>
                  <div>
                    <div className="font-semibold text-[14px] mb-1">{card.title}</div>
                    <div className="text-[12px] text-[var(--text-secondary)] leading-relaxed">
                      {card.desc}
                    </div>
                  </div>
                </Link>
              );
            })}
          </div>
        </div>
      )}
      </div>
    </AppShell>
  );
}
