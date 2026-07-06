'use client';
// Авторизованный дашборд, вынесенный из page.tsx в lazy-чанк: аноним видит
// только <Landing/>, и ~137 KiB дашборд-JS не грузятся на лендинге.

import { useEffect, useState, useCallback, useMemo } from 'react';
import Link from 'next/link';
import { Plus, Lock, Upload, LogIn, BarChart3, Target, Brain, Activity, Clock, ArrowRight, Tag, Wallet, Plug } from 'lucide-react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { AddTradeModal } from '@/components/AddTradeModal';
import CloseTradeModal from '@/components/CloseTradeModal';
import { SettingsModal } from '@/components/SettingsModal';
import { ImportPreviewModal } from '@/components/ImportPreviewModal';
import { DepositManagerModal } from '@/components/DepositManagerModal';
import { SetupManagerModal } from '@/components/SetupManagerModal';
import BrokerConnectModal from '@/components/BrokerConnectModal';
import { ReconnectBanner } from '@/components/ReconnectBanner';
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
import { ActivityCalendar } from '@/components/dashboard/ActivityCalendar';
import { StreakIndicator } from '@/components/dashboard/StreakIndicator';
import { RecentTrades } from '@/components/dashboard/RecentTrades';
import { SetupPerformance } from '@/components/dashboard/SetupPerformance';
import { CollapsibleSection } from '@/components/dashboard/CollapsibleSection';
import { api, ApiError } from '@/lib/apiClient';
import { queryKeys } from '@/lib/queries';
import { toStatsSubset } from './dashboardTabsParams';
import { DataError } from '@/components/ui/DataError';

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
  varmargin_total?: number;  // TR1.2: account-level varmargin (futures)
  total_pnl_with_unrealized?: number;
  cash_truth_pnl?: number;  // Phase 6.4: broker reconciliation
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
  // PR 21: источник initial_balance — 'tinkoff_derived' | 'manual' | null.
  initial_balance_source?: string | null;
  // PR 23: для broker-юзера — реальный баланс счёта из Тинькова + кол-во позиций.
  current_cash_balance?: number | null;
  open_positions_count?: number | null;
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
  max_drawdown_peak_date?: string | null;
  max_drawdown_trough_date?: string | null;
  max_drawdown_duration_days?: number | null;
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
  equity_curve_gross?: { date: string; balance: number }[];  // Phase 11: gross variant
  imoex_curve?: { date: string; value: number }[];
  tag_stats: { tag: string; pnl: number; win_rate: number; count: number }[];
  // Phase 11 (2026-05-17): gross fields for pnlDisplayMode toggle
  total_pnl_gross?: number;
  total_pnl_with_unrealized_gross?: number;
  account_level_adjustments_gross?: number;
}

export function anchorSourceLabel(source?: string | null): string | null {
  switch (source) {
    case 'inferred_anchor':
      return 'База открытия восстановлена автоматически (не подтверждена депозитами)';
    case 'inferred_blocked':
      return 'Журнал требует проверки: автоякорь не применён';
    default:
      return null;
  }
}

export default function DashboardHome() {
  const { t } = useLanguage();
  const { settings, formatCurrency } = useSettings();
  const { user, isLoading: authLoading } = useAuth();
  const queryClient = useQueryClient();

  // FE-07: state, отвечающий за UI-поведение (модалки, табы), остаётся на
  // useState. Данные (stats/trades/advanced/benchmark) — TanStack Query.
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

  // params для /stats/ — собираем как раньше, но теперь это вход TanStack-ключа.
  // Запоминаем мемоизацией, чтобы queryKey оставался стабильным между рендерами.
  const statsParams = useMemo(() => {
    const params: Record<string, string> = {};
    const f = filters;
    if (settings.tradesStartTradeId) {
      params.start_trade_id = settings.tradesStartTradeId.toString();
    } else if (settings.tradesStartDate) {
      params.period = 'custom';
      params.start_date = settings.tradesStartDate;
    } else if (f.period !== 'all') {
      params.period = f.period;
      if (f.period === 'custom' && f.startDate) {
        params.start_date = f.startDate;
        if (f.endDate) params.end_date = f.endDate;
      }
    }
    if (f.tag) params.tag = f.tag;
    if (f.limit) params.limit = f.limit.toString();
    if (settings.maeCalculationMethod) {
      params.mae_method = settings.maeCalculationMethod;
    }
    return params;
  }, [
    filters,
    settings.tradesStartDate,
    settings.tradesStartTradeId,
    settings.maeCalculationMethod,
  ]);

  // advanced/benchmark принимают period/start_date/end_date/start_trade_id/tag,
  // но НЕ mae_method — иначе бэкенд отбросит лишний query-параметр.
  const statsSubset = useMemo(() => toStatsSubset(statsParams), [statsParams]);

  // /stats/ — useStatsQuery не подошёл (поддерживает только period/start/end),
  // нам нужны ещё tag/limit/mae_method/start_trade_id, поэтому прямой useQuery
  // с queryKeys.stats.summary (полный набор params в ключе → разные фильтры =
  // разные кеши).
  const statsQuery = useQuery<DashboardData>({
    queryKey: queryKeys.stats.summary(statsParams),
    queryFn: () => api.get<DashboardData>('/stats/', { params: statsParams }),
    enabled: !!user,
    staleTime: 60 * 1000,
  });

  // /trades/ — список без limit (фильтрация по start_trade_id/start_date
  // на клиенте). useTradesQuery без params вызывает /trades/ — то же поведение.
  const tradesQuery = useQuery<Trade[]>({
    queryKey: queryKeys.trades.list(undefined),
    queryFn: () => api.get<Trade[]>('/trades/'),
    enabled: !!user,
  });

  // Lazy-загрузка табов — TanStack делает идемпотентным «загрузить раз» через
  // staleTime: Infinity + enabled-флаг по activeTab. При повторном переключении
  // на advanced data уже в кеше → мгновенно показываем без сетевого запроса.
  const advancedQuery = useQuery<unknown>({
    queryKey: ['stats', 'advanced', statsSubset],
    queryFn: () => api.get('/stats/advanced', { params: statsSubset }),
    enabled: !!user && activeTab === 'advanced',
    staleTime: 5 * 60 * 1000,
  });
  const benchmarkQuery = useQuery<unknown>({
    queryKey: ['stats', 'benchmark', statsSubset],
    queryFn: () => api.get('/stats/benchmark', { params: statsSubset }),
    enabled: !!user && activeTab === 'benchmark',
    staleTime: 5 * 60 * 1000,
  });

  // Derived state — UI-фильтрация trades по tradesStartTradeId/Date.
  const trades: Trade[] = useMemo(() => {
    const raw = tradesQuery.data ?? [];
    let filtered = Array.isArray(raw) ? raw.slice() : [];
    if (settings.tradesStartTradeId) {
      const startTrade = filtered.find((tr) => tr.id === settings.tradesStartTradeId);
      if (startTrade) {
        const startTime = new Date(startTrade.entry_at);
        filtered = filtered.filter((tr) => new Date(tr.entry_at) >= startTime);
      }
    } else if (settings.tradesStartDate) {
      const startDate = new Date(settings.tradesStartDate);
      filtered = filtered.filter((tr) => new Date(tr.entry_at) >= startDate);
    }
    return filtered.reverse();
  }, [tradesQuery.data, settings.tradesStartDate, settings.tradesStartTradeId]);

  const stats = statsQuery.data ?? null;
  const loading = statsQuery.isLoading || tradesQuery.isLoading;
  const error = (statsQuery.error ?? tradesQuery.error) as ApiError | Error | null;
  const advancedData = advancedQuery.data ?? null;
  const benchmarkData = benchmarkQuery.data ?? null;
  const advancedLoading = advancedQuery.isLoading && activeTab === 'advanced';
  const benchmarkLoading = benchmarkQuery.isLoading && activeTab === 'benchmark';
  const advancedError = advancedQuery.error as ApiError | Error | null;
  const benchmarkError = benchmarkQuery.error as ApiError | Error | null;

  const effectiveInitialDeposit = stats?.period_start_balance_reliable !== false && stats?.period_start_balance && stats.period_start_balance > 0
    ? stats.period_start_balance
    : null;

  // PR 23: для broker-юзера показываем cash-баланс + кол-во позиций вместо
  // «стартового капитала». Это единственная честная цифра для margin/futures.
  const isBrokerUser = stats?.current_cash_balance !== null && stats?.current_cash_balance !== undefined;
  const currentCashBalance = stats?.current_cash_balance ?? null;
  const openPositionsCount = stats?.open_positions_count ?? 0;

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

  const addLog = useCallback((msg: string) => {
    const time = new Date().toLocaleTimeString();
    setLogs(prev => [{msg, time}, ...prev].slice(0, 5));
  }, []);

  // FE-07: refetch — централизованный «обновить всё», который дёргают
  // SyncStatusIndicator, modals onSuccess, retry-кнопка ошибки.
  // Инвалидируем queryKeys.trades/stats (включая открытые в этот момент
  // advanced/benchmark подзапросы) — TanStack сам решит, что перезапросить.
  const refetchAll = useCallback(() => {
    void statsQuery.refetch();
    void tradesQuery.refetch();
  }, [statsQuery, tradesQuery]);

  // Лог об успешной/упавшей загрузке для будущего notification-center.
  useEffect(() => {
    if (statsQuery.isSuccess && tradesQuery.isSuccess) {
      addLog(t.logs.synchronized);
    }
  }, [statsQuery.isSuccess, tradesQuery.isSuccess, t.logs.synchronized, addLog]);
  useEffect(() => {
    if (statsQuery.isError || tradesQuery.isError) {
      addLog(t.logs.syncFailed);
    }
  }, [statsQuery.isError, tradesQuery.isError, t.logs.syncFailed, addLog]);

  useEffect(() => {
    setMounted(true);
  }, []);

  // FE-01: retry-обёртки для табов advanced/benchmark. TanStack refetch
  // самостоятельно сбрасывает error → перезапрос → ok-ответ.
  const retryAdvanced = useCallback(() => {
    void advancedQuery.refetch();
  }, [advancedQuery]);
  const retryBenchmark = useCallback(() => {
    void benchmarkQuery.refetch();
  }, [benchmarkQuery]);

  const handleFiltersChange = (newFilters: Filters) => {
    setFilters(newFilters);
    // statsQuery автоматически отреагирует через изменение statsParams → queryKey;
    // TanStack сам подхватит изменение, явный refetch не нужен.
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
      // Инвалидируем trades + stats — оба зависят от закрытия позиции.
      queryClient.invalidateQueries({ queryKey: queryKeys.trades.all });
      queryClient.invalidateQueries({ queryKey: queryKeys.stats.all });
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
      queryClient.invalidateQueries({ queryKey: queryKeys.trades.all });
      queryClient.invalidateQueries({ queryKey: queryKeys.stats.all });
      addLog(`${t.logs.tradePurged}: ${tradeId}`);
    } catch (error) {
      console.error('Delete failed:', error);
      addLog(t.logs.purgeFailed);
    } finally {
      setActionInProgress(false);
    }
  };

  if (!mounted) return null;
  if (authLoading) return <DashboardSkeleton />;

  // page.tsx (тонкий роутер) рендерит этот чанк только для залогиненных;
  // guard оставлен на случай logout, пока чанк смонтирован.
  if (!user) return null;

  // ==================== AUTHENTICATED DASHBOARD ====================
  if (loading) return <DashboardSkeleton />;

  // Page-specific controls для AppShell.headerRight.
  // FilterPanel переехал в body (см. ниже) — popover'ы из header перекрывали search.
  // В хедере оставляем только контекстные icon-кнопки и переключатели.
  const headerActions = (
    <div className="hidden lg:flex items-center gap-1.5">
      <SyncStatusIndicator
        onTradesUpdated={refetchAll}
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
              {/* PR 23: для broker-юзера показываем реальный cash-баланс +
                  кол-во открытых позиций. Это честные цифры от Тинькова.
                  Никакого выдуманного «стартового капитала» — Tinkoff API
                  не даёт точной исторической реконструкции при margin/futures. */}
              {isBrokerUser && currentCashBalance !== null && (
                <>
                  <Wallet size={14} className="text-[var(--accent)]" />
                  <span>Баланс счёта:</span>
                  <span
                    className="font-semibold text-[var(--foreground)] cursor-help"
                    title="Текущий cash на счёте — total_amount_portfolio из Тинькова. Стоимость открытых фьючерсов считается отдельно (в пунктах) и не входит в эту цифру."
                  >
                    {formatCurrency(currentCashBalance)}
                  </span>
                  {openPositionsCount > 0 && (
                    <span className="text-xs text-[var(--text-tertiary)]">
                      • открыто {openPositionsCount} {openPositionsCount === 1 ? 'позиция' : 'позиций'}
                    </span>
                  )}
                </>
              )}
              {isBrokerUser && anchorSourceLabel(stats?.initial_balance_source) && (
                <span className="basis-full w-full text-[11px] text-[var(--text-tertiary)] mt-1">
                  {anchorSourceLabel(stats?.initial_balance_source)}
                </span>
              )}
              {/* Для manual-юзера (без брокера) — показываем initial_balance если задан. */}
              {!isBrokerUser && effectiveInitialDeposit && (
                <>
                  <Wallet size={14} className="text-[var(--accent)]" />
                  <span>{capitalLabel}</span>
                  <span className="font-semibold text-[var(--foreground)]">
                    {formatCurrency(effectiveInitialDeposit)}
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
                </>
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
        onSuccess={() => { refetchAll(); addLog('Новая позиция создана'); }}
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
        onSuccess={() => { refetchAll(); addLog('Импорт завершён'); }}
      />
      <DepositManagerModal
        isOpen={isDepositModalOpen}
        onClose={() => setIsDepositModalOpen(false)}
        onUpdate={() => { refetchAll(); addLog('Депозит обновлён'); }}
      />
      <SetupManagerModal
        isOpen={isSetupModalOpen}
        onClose={() => setIsSetupModalOpen(false)}
      />
      <BrokerConnectModal
        isOpen={isBrokerModalOpen}
        onClose={() => setIsBrokerModalOpen(false)}
        onConnectionChange={() => { refetchAll(); addLog('Синхронизация с брокером завершена'); }}
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

      {/* Empty State Banner — onboarding с приоритетом: брокер → CSV → ручная.
          API-подключение даёт автосинхронизацию, поэтому это primary CTA;
          CSV — fallback для не-Тинькофф брокеров; ручная — для разовых сделок. */}
      {!hasData && !loading && (
        <div className="mb-8 rounded-[var(--radius-xl)] border border-[var(--accent)]/30 bg-gradient-to-r from-[var(--accent-soft)] to-transparent p-6 md:p-7">
          <div className="flex items-start gap-4 mb-5">
            <div className="w-12 h-12 flex-shrink-0 rounded-[var(--radius-lg)] bg-[var(--accent-soft)] text-[var(--accent)] flex items-center justify-center">
              <Plug size={22} />
            </div>
            <div className="min-w-0 flex-1">
              <h3 className="text-[17px] font-semibold leading-tight mb-1">
                {t.emptyState?.title || 'Подключите брокера за 1 минуту'}
              </h3>
              <p className="text-[14px] text-[var(--text-secondary)] leading-relaxed">
                {t.emptyState?.description || 'Самый быстрый путь — подключить Тинькофф через API: сделки и позиции подтянутся автоматически. Если ваш брокер другой — загрузите отчёт CSV/Excel.'}
              </p>
            </div>
          </div>
          <div className="flex flex-col sm:flex-row flex-wrap gap-3 sm:pl-16">
            {/* Primary — API broker connect */}
            <div className="flex flex-col gap-1">
              <button
                onClick={() => user ? setIsBrokerModalOpen(true) : setIsAuthRequiredOpen(true)}
                className="btn-primary"
              >
                <Plug size={14} />
                {t.emptyState?.connectBrokerButton || 'Подключить Тинькофф'}
              </button>
              <span className="text-[11px] text-[var(--text-tertiary)] pl-1">
                {t.emptyState?.connectBrokerHint || 'Read-only API · автосинхронизация'}
              </span>
            </div>
            {/* Secondary — CSV/Excel fallback */}
            <div className="flex flex-col gap-1">
              <button
                onClick={() => user ? setIsImportModalOpen(true) : setIsAuthRequiredOpen(true)}
                className="btn-secondary"
              >
                <Upload size={14} />
                {t.emptyState?.importButton || 'Импорт CSV / Excel'}
              </button>
              <span className="text-[11px] text-[var(--text-tertiary)] pl-1">
                {t.emptyState?.importHint || 'Для других брокеров'}
              </span>
            </div>
            {/* Tertiary — manual entry */}
            <div className="flex flex-col gap-1">
              <button
                onClick={() => user ? setIsModalOpen(true) : setIsAuthRequiredOpen(true)}
                className="inline-flex items-center gap-1.5 px-3 py-2 text-[13px] text-[var(--text-secondary)] hover:text-[var(--foreground)] transition-colors"
              >
                <Plus size={14} />
                {t.emptyState?.addButton || 'Добавить вручную'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* PR 26 Scenario #31/#64: баннер «Требуется переподключение брокера»
          — показывается если есть broken BrokerConnection. Закрывает картину
          «дашборд пустой» при отозванном/невалидном токене. */}
      {user && (
        <ReconnectBanner
          onOpenBrokerModal={() => setIsBrokerModalOpen(true)}
        />
      )}

      {/* FE-01: error-баннер главного дашборда. Показывается только когда
          /stats/ или /trades/ упали — даёт юзеру кнопку retry с request_id. */}
      {error && <DataError error={error} onRetry={refetchAll} />}

      {/* ===== TAB CONTENT ===== */}
      {!error && activeTab === 'overview' && (
        <>
          {/* PR 25: новый порядок дашборда — сверху вниз daily-flow:
              1. Equity Curve (hero) — кривая, на которой держится взгляд
              2. Core KPI (StatsGrid) — daily scan, цифры за графиком
              3. Advanced (collapsible, свёрнут) — академические метрики рядом,
                 но не в поле зрения новичка
              4. Streak + Activity — behavioral hooks
              5. Recent Trades + Setup — drill-down контекст
              6. Portfolio — снимок счёта */}
          <EquityCurveCard
            data={settings.pnlDisplayMode === 'gross' ? stats?.equity_curve_gross : stats?.equity_curve}
            benchmark={stats?.imoex_curve}
            benchmarkLabel="IMOEX"
            initialBalance={effectiveInitialDeposit ?? undefined}
            formatCurrency={formatCurrency}
            isBrokerCumulative={isBrokerUser}
            pctBaseline={(stats as { drawdown_baseline?: number })?.drawdown_baseline ?? 0}
            peakDate={stats?.max_drawdown_peak_date ?? null}
            troughDate={stats?.max_drawdown_trough_date ?? null}
          />

          {/* Core KPI — сразу после Equity, для daily-scan */}
          <div className="mt-6">
            <StatsGrid stats={stats} hasData={hasData} />
          </div>

          {/* Advanced — collapsible, свёрнут по умолчанию */}
          <div className="mt-6">
            <CollapsibleSection
              title="Расширенные метрики"
              subtitle="Optimal F, SQN, GHPR, Z-Score, Tail Ratio, Calmar и др."
              storageKey="dashboard-advanced"
              defaultOpen={false}
            >
              <AdvancedStatsGrid stats={stats} hasData={hasData} embedded />
            </CollapsibleSection>
          </div>

          {/* Behavioral hooks — Streak + Activity */}
          {hasData && (
            <>
              <div className="mt-6 grid grid-cols-1 lg:grid-cols-3 gap-4">
                <StreakIndicator trades={trades} />
                <div className="lg:col-span-2">
                  <ActivityCalendar trades={trades} />
                </div>
              </div>

              {/* Drill-down контекст — Recent + Setup */}
              <div className="mt-6 grid grid-cols-1 lg:grid-cols-2 gap-4">
                <RecentTrades trades={trades} />
                <SetupPerformance tagStats={stats?.tag_stats} />
              </div>
            </>
          )}

          {/* Portfolio widget — текущее состояние счёта */}
          <div className="mt-6">
            <PortfolioCard />
          </div>
        </>
      )}

      {!error && activeTab === 'advanced' && (
        advancedError ? (
          <DataError error={advancedError} onRetry={retryAdvanced} />
        ) : (
          <AdvancedMetricsGrid
            data={advancedData as React.ComponentProps<typeof AdvancedMetricsGrid>['data']}
            loading={advancedLoading}
          />
        )
      )}

      {!error && activeTab === 'benchmark' && (
        benchmarkError ? (
          <DataError error={benchmarkError} onRetry={retryBenchmark} />
        ) : (
          <BenchmarkingView
            data={benchmarkData as React.ComponentProps<typeof BenchmarkingView>['data']}
            loading={benchmarkLoading}
          />
        )
      )}

      {/* Глубокий анализ — teaser-row.
          Только в Overview — на других табах дублирование избыточно. */}
      {!error && activeTab === 'overview' && hasData && (
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
