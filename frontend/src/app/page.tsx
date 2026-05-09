'use client';

import { useEffect, useState, useCallback } from 'react';
import Link from 'next/link';
import { Plus, Lock, Upload, BookOpen, LogIn, BarChart3, Target, Zap, TrendingUp, Brain, Shield, GitGraph, Activity, Clock, ArrowRight, Tag, Calendar, Wallet, ArrowUpRight, Sparkles } from 'lucide-react';
import { KonturCurve } from '@/components/landing/KonturCurve';
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

export default function Home() {
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
  if (authLoading) return <DashboardSkeleton />;

  // ==================== GUEST LANDING PAGE ====================
  if (!user) {
    // Категории метрик: bento-плитки с цветным акцентом + список метрик внутри.
    // Принципы (после редизайна Phase 4): один цвет = одна категория, без mono/uppercase
    // в подписях, без cyberpunk-glow — спокойный продуктовый стиль.
    const metricCategories: Array<{
      title: string;
      color: 'indigo' | 'rose' | 'violet' | 'emerald' | 'amber';
      icon: React.ReactNode;
      blurb: string;
      metrics: Array<{ label: string; anchor: string }>;
    }> = [
      {
        title: 'Базовые показатели',
        color: 'indigo',
        icon: <BarChart3 size={22} />,
        blurb: 'P&L, Win Rate, Profit Factor, SQN — то, что должно быть в каждом дневнике.',
        metrics: [
          { label: 'P&L и баланс', anchor: 'total-pnl' },
          { label: 'Win Rate', anchor: 'win-rate' },
          { label: 'Profit Factor', anchor: 'profit-factor' },
          { label: 'SQN (Тарп)', anchor: 'sqn' },
        ],
      },
      {
        title: 'Риск-менеджмент',
        color: 'rose',
        icon: <Shield size={22} />,
        blurb: 'Optimal F, Drawdown, Risk of Ruin, Monte Carlo — научный подход к риску.',
        metrics: [
          { label: 'Optimal F (Винс)', anchor: 'optimal-f' },
          { label: 'Drawdown', anchor: 'drawdown' },
          { label: 'Risk of Ruin', anchor: 'risk-of-ruin' },
          { label: 'Monte Carlo', anchor: 'monte-carlo' },
        ],
      },
      {
        title: 'Продвинутая статистика',
        color: 'violet',
        icon: <GitGraph size={22} />,
        blurb: 'Z-Score, R-Expectancy, Sortino, Recovery Factor — для системных трейдеров.',
        metrics: [
          { label: 'Z-Score', anchor: 'z-score' },
          { label: 'R-Expectancy', anchor: 'r-expectancy' },
          { label: 'Sortino Ratio', anchor: 'sortino' },
          { label: 'Recovery Factor', anchor: 'recovery-factor' },
        ],
      },
      {
        title: 'Эффективность капитала',
        color: 'emerald',
        icon: <TrendingUp size={22} />,
        blurb: 'ROI, GHPR, Tail Ratio, Calmar — насколько эффективно работает капитал.',
        metrics: [
          { label: 'ROI', anchor: 'roi' },
          { label: 'GHPR', anchor: 'ghpr' },
          { label: 'Tail Ratio', anchor: 'tail-ratio' },
          { label: 'Calmar Ratio', anchor: 'calmar-ratio' },
        ],
      },
      {
        title: 'Поведенческий анализ',
        color: 'amber',
        icon: <Calendar size={22} />,
        blurb: 'Когда вы торгуете лучше всего, какие сетапы работают, где паттерны.',
        metrics: [
          { label: 'Time Patterns', anchor: 'time-patterns' },
          { label: 'Win/Loss Streaks', anchor: 'streaks' },
          { label: 'Avg Win / Loss', anchor: 'avg-win-loss' },
          { label: 'Теги и сетапы', anchor: 'tags' },
        ],
      },
    ];

    return (
      <main className="min-h-screen section-dark">
        {/* ===== 1. HEADER ===== */}
        <header className="sticky top-0 z-30 backdrop-blur-md bg-[var(--background)]/80 border-b border-[var(--border)]">
          <div className="max-w-6xl mx-auto flex items-center justify-between px-6 h-16">
            <Link href="/" className="text-2xl font-bold tracking-tight no-underline text-[var(--foreground)]">
              Eqio
            </Link>
            <nav className="hidden md:flex items-center gap-6 text-sm text-[var(--text-secondary)]">
              <Link href="/manual" className="hover:text-[var(--foreground)] transition-colors no-underline">Возможности</Link>
              <Link href="/pricing" className="hover:text-[var(--foreground)] transition-colors no-underline">Тарифы</Link>
              <Link href="/blog" className="hover:text-[var(--foreground)] transition-colors no-underline">Блог</Link>
              <Link href="/help" className="hover:text-[var(--foreground)] transition-colors no-underline">Помощь</Link>
            </nav>
            <div className="flex items-center gap-3">
              <Link href="/login" className="btn-pill-outline">Войти в сервис</Link>
              <Link href="/register" className="btn-primary hidden sm:inline-flex">Начать</Link>
            </div>
          </div>
        </header>

        {/* ===== 2. HERO ===== */}
        <section className="section-dark relative overflow-hidden px-6 pt-20 pb-24 md:pt-32 md:pb-32">
          <KonturCurve variant="br" className="text-white hidden md:block" opacity={0.45} />
          <div className="max-w-6xl mx-auto relative z-10">
            <div className="inline-flex items-center gap-2 px-3 py-1 rounded-[var(--radius-pill)] bg-[var(--accent-soft)] text-[var(--accent)] text-[12px] font-medium mb-10">
              <span className="w-1.5 h-1.5 rounded-full bg-[var(--accent)]" />
              Торговый дневник для MOEX
            </div>

            <h1 className="headline-2xl mb-8 max-w-4xl">
              Системная торговля<br />
              начинается с&nbsp;дневника
            </h1>

            <p className="text-lg md:text-xl text-[var(--text-secondary)] leading-relaxed max-w-2xl mb-12">
              30+ метрик, AI-разбор каждой сделки и автоматическая синхронизация с Тинькофф.
              Бесплатно до 50 сделок в месяц.
            </p>

            <div className="flex flex-col sm:flex-row gap-3">
              <Link href="/register" className="btn-primary" style={{ padding: '14px 28px', fontSize: '16px' }}>
                Начать бесплатно <ArrowRight size={16} />
              </Link>
              <Link href="/manual" className="btn-pill-outline" style={{ padding: '14px 28px', fontSize: '15px' }}>
                <BookOpen size={16} /> Что внутри
              </Link>
            </div>
          </div>
        </section>

        {/* ===== 3. HERO BENTO — 6 плиток, 3 типа (kontur-style) ===== */}
        <section className="section-dark px-6 pb-24 md:pb-32">
          <div className="max-w-6xl mx-auto">
            <div className="grid grid-cols-12 gap-4 md:gap-5">
              {/* Row 1: text-only / colored-indigo / text-only */}
              <div className="col-span-12 md:col-span-4 tile-text">
                <div className="text-[28px] font-bold leading-tight mb-2 text-[var(--foreground)]">30+ метрик</div>
                <div className="text-sm text-[var(--text-secondary)]">
                  Optimal f, SQN, Sharpe, Sortino, Calmar, Ulcer, K-Ratio — настоящие формулы, не шаблоны.
                </div>
              </div>

              <div className="col-span-12 md:col-span-4 tile tile-indigo flex flex-col justify-between min-h-[220px]">
                <div className="flex items-start justify-between">
                  <Sparkles size={22} className="opacity-95" />
                </div>
                <div>
                  <div className="text-2xl font-bold leading-tight mb-2">AI-разбор сделки</div>
                  <div className="text-sm opacity-85">
                    Вердикт, ошибки, рекомендации — для каждого закрытия.
                  </div>
                </div>
              </div>

              <div className="col-span-12 md:col-span-4 tile-text">
                <div className="text-[28px] font-bold leading-tight mb-2 text-[var(--foreground)]">MOEX свечи</div>
                <div className="text-sm text-[var(--text-secondary)]">
                  MAE / MFE и Trade Replay автоматически из биржевых свечей. В РФ ни у кого больше нет.
                </div>
              </div>

              {/* Row 2: colored-emerald / text-only / outlined-link */}
              <div className="col-span-12 md:col-span-5 tile tile-emerald flex flex-col justify-between min-h-[200px]">
                <Target size={22} className="opacity-95" />
                <div>
                  <div className="text-2xl font-bold leading-tight mb-2">Trade Replay</div>
                  <div className="text-sm opacity-85">
                    Свечи MOEX вокруг каждой сделки с маркерами входа, выхода, stop и take.
                  </div>
                </div>
              </div>

              <div className="col-span-12 md:col-span-4 tile-text">
                <div className="text-[28px] font-bold leading-tight mb-2 text-[var(--foreground)]">Тинькофф API</div>
                <div className="text-sm text-[var(--text-secondary)]">
                  Авто-синхронизация портфеля, FIFO-учёт сделок, расчёт комиссий каждые 60 секунд.
                </div>
              </div>

              <Link href="/manual" className="col-span-12 md:col-span-3 tile-outline no-underline group">
                <div className="flex flex-col h-full justify-between min-h-[180px] w-full">
                  <div className="text-lg font-semibold">Все возможности</div>
                  <ArrowUpRight size={28} className="self-end transition-transform group-hover:translate-x-1 group-hover:-translate-y-1" />
                </div>
              </Link>
            </div>
          </div>
        </section>

        {/* ===== 4. NUMBERS BAND — светлая контрастная секция ===== */}
        <section className="section-light relative overflow-hidden px-6 py-24 md:py-32">
          <KonturCurve variant="bl" className="text-black hidden md:block" opacity={0.12} />
          <div className="max-w-6xl mx-auto relative z-10">
            <p className="eyebrow mb-4">Что вы получаете</p>
            <h2 className="headline-lg mb-16 max-w-3xl">Цифры, а не обещания</h2>

            <div className="grid grid-cols-2 md:grid-cols-4 gap-10 md:gap-6">
              {[
                { n: '30+', label: 'метрик статистики' },
                { n: '10 000', label: 'итераций Monte Carlo' },
                { n: '1м – 1д', label: 'таймфреймы MOEX' },
                { n: '399₽', label: '/ месяц Pro' },
              ].map((f) => (
                <div key={f.label} className="flex flex-col gap-2">
                  <div className="number-fact">{f.n}</div>
                  <div className="text-sm text-[#6b7280]">{f.label}</div>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* ===== 5. METRICS DEEP DIVE — bento с 5 категорий + outlined link ===== */}
        <section id="features" className="section-dark px-6 py-24 md:py-32">
          <div className="max-w-6xl mx-auto">
            <p className="eyebrow mb-4">Аналитический центр</p>
            <h2 className="headline-lg mb-12 max-w-3xl">30+ метрик. По-настоящему 30+</h2>

            <div className="grid grid-cols-12 gap-4 md:gap-5">
              {metricCategories.map((cat, idx) => {
                const layoutClass = [
                  'col-span-12 md:col-span-7',
                  'col-span-12 md:col-span-5',
                  'col-span-12 md:col-span-5',
                  'col-span-12 md:col-span-4',
                  'col-span-12 md:col-span-3',
                ][idx];
                return (
                  <div key={cat.title} className={layoutClass}>
                    <div className={`tile tile-${cat.color} h-full min-h-[220px] flex flex-col gap-4`}>
                      <div className="opacity-95">{cat.icon}</div>
                      <div className="flex-1">
                        <h3 className="text-xl md:text-2xl font-bold leading-tight mb-2">
                          {cat.title}
                        </h3>
                        <p className="text-sm leading-snug opacity-85">{cat.blurb}</p>
                      </div>
                      <div className="flex flex-wrap gap-2">
                        {cat.metrics.map((m) => (
                          <Link
                            key={m.anchor}
                            href={`/manual#${m.anchor}`}
                            className="inline-flex items-center gap-1 px-3 py-1 rounded-[var(--radius-pill)] bg-white/15 text-white text-[12px] font-medium hover:bg-white/25 transition-colors no-underline"
                          >
                            {m.label}
                          </Link>
                        ))}
                      </div>
                    </div>
                  </div>
                );
              })}

              <Link
                href="/manual"
                className="col-span-12 md:col-span-12 tile-outline no-underline group"
              >
                <div className="flex flex-row items-center justify-between w-full">
                  <div>
                    <div className="text-lg font-semibold mb-1">Полное руководство по метрикам</div>
                    <div className="text-sm text-[var(--text-secondary)]">
                      Подробное описание каждого показателя, формулы и примеры расчёта.
                    </div>
                  </div>
                  <ArrowUpRight size={32} className="transition-transform group-hover:translate-x-1 group-hover:-translate-y-1 flex-shrink-0" />
                </div>
              </Link>
            </div>
          </div>
        </section>

        {/* ===== 6. SPLIT MAE/MFE × POST-EXIT — surface-1 фон ===== */}
        <section className="section-surface px-6 py-24 md:py-32">
          <div className="max-w-6xl mx-auto">
            <p className="eyebrow mb-4">Уникальное в РФ</p>
            <h2 className="headline-lg mb-12 max-w-3xl">Не очередной Excel</h2>

            <div className="grid md:grid-cols-2 gap-6 lg:gap-8">
              <div className="cyber-card p-8 lg:p-10">
                <Link href="/manual#mae-mfe" className="inline-flex items-center gap-3 mb-5 group no-underline">
                  <div className="w-12 h-12 rounded-[var(--radius-md)] bg-[var(--accent-soft)] text-[var(--accent)] flex items-center justify-center">
                    <Target size={22} />
                  </div>
                  <h3 className="text-2xl font-bold tracking-tight group-hover:text-[var(--accent)] transition-colors">
                    MAE / MFE анализ
                  </h3>
                </Link>
                <p className="text-[var(--text-secondary)] mb-6 leading-relaxed">
                  Maximum Adverse / Favorable Excursion — ключевые метрики для оптимизации стопов
                  и тейк-профитов. Считаются автоматически по реальным свечам MOEX.
                </p>
                <ul className="flex flex-col gap-3 list-none p-0">
                  {[
                    ['Edge Ratio', 'отношение MFE/MAE — насколько преимущество перевешивает риск'],
                    ['Quality Score', 'комплексная оценка сетапа: win-rate × efficiency × edge'],
                    ['Группировка', 'по тегам, сетапам, инструментам, таймфреймам, направлению'],
                    ['Персентили', 'P25/P50/P75 распределения для точной настройки стопов'],
                  ].map(([t, d]) => (
                    <li key={t} className="flex gap-3 items-start">
                      <span className="w-1.5 h-1.5 rounded-full bg-[var(--accent)] mt-2.5 flex-shrink-0" />
                      <span>
                        <span className="font-semibold">{t}</span>
                        <span className="text-[var(--text-secondary)]"> — {d}</span>
                      </span>
                    </li>
                  ))}
                </ul>
              </div>

              <div className="cyber-card p-8 lg:p-10">
                <Link href="/manual#post-exit" className="inline-flex items-center gap-3 mb-5 group no-underline">
                  <div className="w-12 h-12 rounded-[var(--radius-md)] bg-[var(--warning-soft)] text-[var(--warning)] flex items-center justify-center">
                    <Clock size={22} />
                  </div>
                  <h3 className="text-2xl font-bold tracking-tight group-hover:text-[var(--warning)] transition-colors">
                    Post-Exit анализ
                  </h3>
                </Link>
                <p className="text-[var(--text-secondary)] mb-6 leading-relaxed">
                  Что было с ценой после вашего выхода? Система загружает реальные свечи
                  и считает, сколько вы оставили на столе.
                </p>
                <ul className="flex flex-col gap-3 list-none p-0">
                  {[
                    ['Упущенная прибыль', '% движения цены в вашу сторону после закрытия'],
                    ['Мульти-таймфрейм', '15м / 1ч / 4ч / 1д — от скальпинга до свинга'],
                    ['Early Exit детекция', 'автоматическое выявление сделок, закрытых рано'],
                    ['Реальные свечи', 'данные MOEX ISS API — точные цены, а не модели'],
                  ].map(([t, d]) => (
                    <li key={t} className="flex gap-3 items-start">
                      <span className="w-1.5 h-1.5 rounded-full bg-[var(--warning)] mt-2.5 flex-shrink-0" />
                      <span>
                        <span className="font-semibold">{t}</span>
                        <span className="text-[var(--text-secondary)]"> — {d}</span>
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          </div>
        </section>

        {/* ===== 7. HOW IT WORKS — светлая, 4 карточки с огромными цифрами ===== */}
        <section className="section-light px-6 py-24 md:py-32">
          <div className="max-w-6xl mx-auto">
            <p className="eyebrow mb-4">Начните за 2 минуты</p>
            <h2 className="headline-lg mb-12 max-w-3xl text-[#0a0a0b]">
              От первой сделки до системы — за 4 шага
            </h2>

            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-5">
              {[
                { n: '01', title: 'Регистрация', desc: 'Email или OAuth — Google / Яндекс / Сбер / Тинькофф ID. 30 секунд.' },
                { n: '02', title: 'Импорт сделок', desc: 'Подключите Тинькофф API или загрузите Excel/CSV из любого брокера.' },
                { n: '03', title: 'Анализ', desc: '30+ метрик считаются мгновенно. AI разбирает каждое закрытие.' },
                { n: '04', title: 'Рост', desc: 'Находите паттерны в своих ошибках. Устраняйте слабые места системно.' },
              ].map((s) => (
                <div
                  key={s.n}
                  className="bg-white border-2 border-[#0a0a0b] rounded-[var(--radius-lg)] p-6 lg:p-8 flex flex-col gap-3 min-h-[240px]"
                >
                  <div className="text-[64px] md:text-[72px] font-extrabold leading-none tracking-tight text-[#0a0a0b]">
                    {s.n}
                  </div>
                  <div className="flex-1">
                    <h4 className="text-xl font-bold mb-2 text-[#0a0a0b]">{s.title}</h4>
                    <p className="text-[14px] text-[#6b7280] leading-relaxed">{s.desc}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* ===== 8. AI / BROKER / RISK — 3 разнотипные плитки ===== */}
        <section className="section-dark px-6 py-24 md:py-32">
          <div className="max-w-6xl mx-auto">
            <p className="eyebrow mb-4">Зачем платить Pro</p>
            <h2 className="headline-lg mb-12 max-w-3xl">Три причины 399&nbsp;₽ в&nbsp;месяц</h2>

            <div className="grid grid-cols-12 gap-4 md:gap-5">
              <div className="col-span-12 md:col-span-4 tile tile-violet flex flex-col justify-between min-h-[280px]">
                <Brain size={28} className="opacity-95" />
                <div>
                  <h3 className="text-2xl font-bold mb-3 leading-tight">AI-аналитика</h3>
                  <p className="text-sm opacity-85 leading-relaxed mb-4">
                    Нейросеть оценивает каждую сделку: вердикт, ошибки, рекомендации, балл от 1 до 10.
                  </p>
                  <ul className="flex flex-col gap-1.5 list-none p-0 text-[13px] opacity-90">
                    <li>• Автоанализ при закрытии</li>
                    <li>• Рекомендации по сетапам</li>
                    <li>• Паттерны в ошибках</li>
                  </ul>
                </div>
              </div>

              <div className="col-span-12 md:col-span-4 tile-outline flex flex-col justify-between min-h-[280px]">
                <GitGraph size={28} />
                <div>
                  <h3 className="text-2xl font-bold mb-3 leading-tight">Тинькофф Инвестиции</h3>
                  <p className="text-sm text-[var(--text-secondary)] leading-relaxed mb-4">
                    Подключите API — сделки, портфель и баланс синхронизируются автоматически.
                  </p>
                  <ul className="flex flex-col gap-1.5 list-none p-0 text-[13px] text-[var(--text-secondary)]">
                    <li>• Tinkoff Invest API</li>
                    <li>• Портфель в реальном времени</li>
                    <li>• Расчёт комиссий и FIFO</li>
                  </ul>
                </div>
              </div>

              <div className="col-span-12 md:col-span-4 tile tile-rose flex flex-col justify-between min-h-[280px]">
                <Shield size={28} className="opacity-95" />
                <div>
                  <h3 className="text-2xl font-bold mb-3 leading-tight">Управление рисками</h3>
                  <p className="text-sm opacity-85 leading-relaxed mb-4">
                    Optimal F (Винс), Kelly, Risk of Ruin — научный подход к размеру позиции.
                  </p>
                  <ul className="flex flex-col gap-1.5 list-none p-0 text-[13px] opacity-90">
                    <li>• Optimal F по PnL и R</li>
                    <li>• Drawdown в реальном времени</li>
                    <li>• Monte Carlo 10 000 итераций</li>
                  </ul>
                </div>
              </div>
            </div>

            <p className="text-center text-sm text-[var(--text-tertiary)] mt-10">
              Бесплатно до 50 сделок в месяц. Pro — 399 ₽/мес. Без карты на старте.
            </p>
          </div>
        </section>

        {/* ===== 9. FINAL CTA — accent indigo ===== */}
        <section className="section-accent relative overflow-hidden px-6 py-24 md:py-32">
          <KonturCurve variant="tr" className="text-white hidden md:block" opacity={0.3} />
          <div className="max-w-4xl mx-auto text-center flex flex-col gap-8 relative z-10">
            <h2 className="headline-xl">Готовы торговать осознанно?</h2>
            <p className="text-lg md:text-xl opacity-90 max-w-2xl mx-auto">
              Присоединяйтесь к трейдерам, которые принимают решения на основе данных, а не эмоций.
            </p>
            <div className="flex flex-col sm:flex-row gap-3 justify-center mt-2">
              <Link href="/register" className="btn-pill-inverted">
                Начать бесплатно <ArrowRight size={18} />
              </Link>
              <Link href="/pricing" className="btn-pill-outline" style={{ color: '#fff', padding: '14px 28px', fontSize: '15px' }}>
                Посмотреть тарифы
              </Link>
            </div>
          </div>
        </section>

        {/* ===== 10. FOOTER — 4-col grid ===== */}
        <footer className="section-dark border-t border-[var(--border)] px-6 py-16 text-sm">
          <div className="max-w-6xl mx-auto">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-8 mb-12">
              <div>
                <Link href="/" className="text-xl font-bold tracking-tight no-underline text-[var(--foreground)] mb-4 block">
                  Eqio
                </Link>
                <p className="text-[var(--text-tertiary)] leading-relaxed">
                  Торговый дневник для серьёзного трейдера MOEX.
                </p>
              </div>
              <div>
                <div className="text-[var(--foreground)] font-semibold mb-4">Продукт</div>
                <nav className="flex flex-col gap-2.5">
                  <Link href="/manual" className="text-[var(--text-tertiary)] hover:text-[var(--foreground)] transition-colors no-underline">Возможности</Link>
                  <Link href="/pricing" className="text-[var(--text-tertiary)] hover:text-[var(--foreground)] transition-colors no-underline">Тарифы</Link>
                  <Link href="/calculator" className="text-[var(--text-tertiary)] hover:text-[var(--foreground)] transition-colors no-underline">Калькулятор</Link>
                </nav>
              </div>
              <div>
                <div className="text-[var(--foreground)] font-semibold mb-4">Компания</div>
                <nav className="flex flex-col gap-2.5">
                  <Link href="/blog" className="text-[var(--text-tertiary)] hover:text-[var(--foreground)] transition-colors no-underline">Блог</Link>
                  <Link href="/help" className="text-[var(--text-tertiary)] hover:text-[var(--foreground)] transition-colors no-underline">Помощь</Link>
                  <Link href="/manual" className="text-[var(--text-tertiary)] hover:text-[var(--foreground)] transition-colors no-underline">Руководство</Link>
                </nav>
              </div>
              <div>
                <div className="text-[var(--foreground)] font-semibold mb-4">Право</div>
                <nav className="flex flex-col gap-2.5">
                  <Link href="/privacy" className="text-[var(--text-tertiary)] hover:text-[var(--foreground)] transition-colors no-underline">Политика конфиденциальности</Link>
                  <span className="text-[var(--text-tertiary)]">152-ФЗ</span>
                </nav>
              </div>
            </div>
            <div className="pt-8 border-t border-[var(--border)] flex flex-wrap items-center justify-between gap-4 text-[var(--text-tertiary)]">
              <div>© Eqio · Торговая аналитика для российских трейдеров</div>
              <div>MOEX · Тинькофф Invest API</div>
            </div>
          </div>
        </footer>
      </main>
    );
  }

  // ==================== AUTHENTICATED DASHBOARD ====================
  if (loading) return <DashboardSkeleton />;

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
