'use client';

import { useEffect, useState, useCallback } from 'react';
import Link from 'next/link';
import { Plus, Lock, Upload, BookOpen, History, Settings, Wallet, LogIn, BarChart3, HelpCircle, FileText, Target, Zap, TrendingUp, TrendingDown, Brain, Shield, GitGraph, Activity, Gauge, LineChart, Dice5, Clock, ArrowRight, ChevronDown, Percent, Repeat, Scale, Tag, Calendar } from 'lucide-react';
import { AddTradeModal } from '@/components/AddTradeModal';
import CloseTradeModal from '@/components/CloseTradeModal';
import { SettingsModal } from '@/components/SettingsModal';
import { ImportPreviewModal } from '@/components/ImportPreviewModal';
import { DepositManagerModal } from '@/components/DepositManagerModal';
import { SetupManagerModal } from '@/components/SetupManagerModal';
import BrokerConnectModal from '@/components/BrokerConnectModal';
import SyncStatusIndicator from '@/components/SyncStatusIndicator';
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
  PostExitCard,
  TagStatsCard,
  TerminalLog,
  MAEMFEAnalysisPanel
} from '@/components/dashboard';
import PortfolioCard from '@/components/dashboard/PortfolioCard';
import EquityCurveCard from '@/components/dashboard/EquityCurveCard';
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
  const { user, isLoading: authLoading } = useAuth();
  
  const [stats, setStats] = useState<DashboardData | null>(null);
  const [trades, setTrades] = useState<Trade[]>([]);
  const [loading, setLoading] = useState(true);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [isCloseModalOpen, setIsCloseModalOpen] = useState(false);
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const [isImportModalOpen, setIsImportModalOpen] = useState(false);
  const [isDepositModalOpen, setIsDepositModalOpen] = useState(false);
  const [isSetupModalOpen, setIsSetupModalOpen] = useState(false);
  const [isBrokerModalOpen, setIsBrokerModalOpen] = useState(false);
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
      if (settings.initialDeposit && settings.initialDeposit > 0) {
        params.append('initial_deposit', settings.initialDeposit.toString());
      }
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
  }, [user, filters, settings.initialDeposit, settings.maeCalculationMethod, settings.tradesStartDate, settings.tradesStartTradeId, t.logs.synchronized, t.logs.syncFailed]);

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
    }
  };

  const handleDelete = async (tradeId: number) => {
    if (!confirm('Are you sure you want to delete this trade?')) return;
    try {
      await api.delete(`/trades/${tradeId}`);
      fetchData();
      addLog(`${t.logs.tradePurged}: ${tradeId}`);
    } catch (error) {
      console.error('Delete failed:', error);
      addLog(t.logs.purgeFailed);
    }
  };

  if (!mounted) return null;
  if (authLoading) return <DashboardSkeleton />;

  // ==================== GUEST LANDING PAGE ====================
  if (!user) {
    return (
      <main className="min-h-screen relative overflow-hidden">
        {/* Background effects */}
        <div className="fixed inset-0 pointer-events-none">
          <div className="absolute top-0 left-1/2 -translate-x-1/2 w-[800px] h-[800px] bg-accent/[0.03] rounded-full blur-[150px]" />
          <div className="absolute bottom-0 right-0 w-[500px] h-[500px] bg-accent-secondary/[0.03] rounded-full blur-[120px]" />
        </div>

        {/* ===== HERO SECTION ===== */}
        <section className="relative z-10 flex flex-col items-center justify-center min-h-screen px-6 text-center">
          <div className="max-w-3xl space-y-8">
            {/* Badge */}
            <div className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full border border-accent/30 bg-accent/5 text-accent text-xs font-mono uppercase tracking-wider">
              <span className="w-1.5 h-1.5 rounded-full bg-accent animate-pulse" />
              Торговая аналитика нового поколения
            </div>

            {/* Title */}
            <h1 className="text-7xl md:text-8xl font-black tracking-tighter italic">
              <span className="text-accent">Eqio</span>
            </h1>
            <p className="text-xl md:text-2xl text-muted-foreground leading-relaxed max-w-2xl mx-auto">
              Профессиональный дневник трейдера с 30+ метриками, AI&#8209;аналитикой и автоматической синхронизацией с брокером
            </p>

            {/* CTA */}
            <div className="flex flex-col sm:flex-row gap-4 justify-center pt-4">
              <Link href="/register" className="btn-primary px-10 py-4 flex items-center justify-center gap-2 text-base font-semibold">
                Начать бесплатно <ArrowRight size={18} />
              </Link>
              <Link href="/login" className="btn-secondary px-10 py-4 flex items-center justify-center gap-2 text-base">
                <LogIn size={18} /> Войти
              </Link>
            </div>

            {/* Scroll hint */}
            <button 
              onClick={() => document.getElementById('features')?.scrollIntoView({ behavior: 'smooth' })}
              className="mt-8 text-muted-foreground/50 hover:text-accent transition-colors animate-bounce"
            >
              <ChevronDown size={28} />
            </button>
          </div>
        </section>

        {/* ===== METRICS SHOWCASE ===== */}
        <section id="features" className="relative z-10 py-24 px-6">
          <div className="max-w-6xl mx-auto">
            <div className="text-center mb-16">
              <p className="text-accent text-xs font-mono uppercase tracking-[0.3em] mb-3">Ваш торговый терминал</p>
              <h2 className="text-4xl md:text-5xl font-black tracking-tight mb-4">30+ метрик в реальном времени</h2>
              <p className="text-muted-foreground text-lg max-w-2xl mx-auto">
                Каждая сделка анализируется по десяткам параметров — от базовых до продвинутых статистических моделей
              </p>
            </div>

            {/* === Основные показатели === */}
            <p className="text-xs font-mono text-accent/60 uppercase tracking-[0.2em] mb-3">Основные показатели</p>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-10">
              {[
                { icon: <TrendingUp size={20} />, label: 'P&L', desc: 'Прибыль/убыток с учётом комиссий и нереализованных позиций', anchor: 'total-pnl' },
                { icon: <Target size={20} />, label: 'Win Rate', desc: 'Процент прибыльных сделок с фильтрацией по сетапам и тегам', anchor: 'win-rate' },
                { icon: <Activity size={20} />, label: 'Profit Factor', desc: 'Отношение валовой прибыли к валовому убытку', anchor: 'profit-factor' },
                { icon: <Gauge size={20} />, label: 'SQN', desc: 'System Quality Number — оценка качества торговой системы по Тарпу', anchor: 'sqn' },
              ].map((m, i) => (
                <Link key={i} href={`/manual#${m.anchor}`} className="cyber-card p-5 group hover:border-accent/40 transition-all duration-300 cursor-pointer block no-underline">
                  <div className="text-accent mb-3 opacity-60 group-hover:opacity-100 transition-opacity">{m.icon}</div>
                  <h3 className="font-bold text-sm mb-1">{m.label}</h3>
                  <p className="text-xs text-muted-foreground leading-relaxed mb-2">{m.desc}</p>
                  <span className="text-[10px] font-mono text-accent/0 group-hover:text-accent/60 transition-colors flex items-center gap-1">
                    Подробнее <ArrowRight size={10} />
                  </span>
                </Link>
              ))}
            </div>

            {/* === Риск-менеджмент === */}
            <p className="text-xs font-mono text-red-400/60 uppercase tracking-[0.2em] mb-3">Риск-менеджмент</p>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-10">
              {[
                { icon: <Zap size={20} />, label: 'Optimal F', desc: 'Оптимальная доля депозита на сделку по методу Ральфа Винса', anchor: 'optimal-f' },
                { icon: <TrendingDown size={20} />, label: 'Drawdown', desc: 'Максимальная и текущая просадка — в процентах и абсолютных значениях', anchor: 'drawdown' },
                { icon: <Shield size={20} />, label: 'Risk of Ruin', desc: 'Вероятность потери 20% и 50% депозита на основе вашей статистики', anchor: 'risk-of-ruin' },
                { icon: <Dice5 size={20} />, label: 'Monte Carlo', desc: '10 000 симуляций для прогноза худшего и лучшего сценариев', anchor: 'monte-carlo' },
              ].map((m, i) => (
                <Link key={i} href={`/manual#${m.anchor}`} className="cyber-card p-5 group hover:border-accent/40 transition-all duration-300 cursor-pointer block no-underline">
                  <div className="text-red-400/60 mb-3 group-hover:text-red-400 transition-colors">{m.icon}</div>
                  <h3 className="font-bold text-sm mb-1">{m.label}</h3>
                  <p className="text-xs text-muted-foreground leading-relaxed mb-2">{m.desc}</p>
                  <span className="text-[10px] font-mono text-accent/0 group-hover:text-accent/60 transition-colors flex items-center gap-1">
                    Подробнее <ArrowRight size={10} />
                  </span>
                </Link>
              ))}
            </div>

            {/* === Продвинутая статистика === */}
            <p className="text-xs font-mono text-violet-400/60 uppercase tracking-[0.2em] mb-3">Продвинутая статистика</p>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-10">
              {[
                { icon: <GitGraph size={20} />, label: 'Z-Score', desc: 'Зависимость между последовательными сделками — стрики не случайны?', anchor: 'z-score' },
                { icon: <LineChart size={20} />, label: 'R-Expectancy', desc: 'Средний доход на единицу риска — сколько R приносит каждая сделка', anchor: 'r-expectancy' },
                { icon: <BarChart3 size={20} />, label: 'Sortino Ratio', desc: 'Доходность относительно нисходящей волатильности', anchor: 'sortino' },
                { icon: <TrendingUp size={20} />, label: 'Recovery Factor', desc: 'Отношение чистой прибыли к максимальной просадке', anchor: 'recovery-factor' },
              ].map((m, i) => (
                <Link key={i} href={`/manual#${m.anchor}`} className="cyber-card p-5 group hover:border-accent/40 transition-all duration-300 cursor-pointer block no-underline">
                  <div className="text-violet-400/60 mb-3 group-hover:text-violet-400 transition-colors">{m.icon}</div>
                  <h3 className="font-bold text-sm mb-1">{m.label}</h3>
                  <p className="text-xs text-muted-foreground leading-relaxed mb-2">{m.desc}</p>
                  <span className="text-[10px] font-mono text-accent/0 group-hover:text-accent/60 transition-colors flex items-center gap-1">
                    Подробнее <ArrowRight size={10} />
                  </span>
                </Link>
              ))}
            </div>

            {/* === Эффективность капитала === */}
            <p className="text-xs font-mono text-emerald-400/60 uppercase tracking-[0.2em] mb-3">Эффективность капитала</p>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-10">
              {[
                { icon: <Percent size={20} />, label: 'ROI', desc: 'Процентная доходность относительно начального депозита', anchor: 'roi' },
                { icon: <TrendingUp size={20} />, label: 'GHPR', desc: 'Геометрическая средняя доходность с учётом сложного процента', anchor: 'ghpr' },
                { icon: <Clock size={20} />, label: 'Tail Ratio', desc: 'Соотношение правого и левого хвостов распределения P&L', anchor: 'tail-ratio' },
                { icon: <Activity size={20} />, label: 'Calmar Ratio', desc: 'CAGR к максимальной просадке — стабильность роста капитала', anchor: 'calmar-ratio' },
              ].map((m, i) => (
                <Link key={i} href={`/manual#${m.anchor}`} className="cyber-card p-5 group hover:border-accent/40 transition-all duration-300 cursor-pointer block no-underline">
                  <div className="text-emerald-400/60 mb-3 group-hover:text-emerald-400 transition-colors">{m.icon}</div>
                  <h3 className="font-bold text-sm mb-1">{m.label}</h3>
                  <p className="text-xs text-muted-foreground leading-relaxed mb-2">{m.desc}</p>
                  <span className="text-[10px] font-mono text-accent/0 group-hover:text-accent/60 transition-colors flex items-center gap-1">
                    Подробнее <ArrowRight size={10} />
                  </span>
                </Link>
              ))}
            </div>

            {/* === Поведенческий анализ === */}
            <p className="text-xs font-mono text-amber-400/60 uppercase tracking-[0.2em] mb-3">Поведенческий анализ</p>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              {[
                { icon: <Calendar size={20} />, label: 'Time Patterns', desc: 'Лучшие и худшие дни и часы — когда торговать, а когда нет', anchor: 'time-patterns' },
                { icon: <Repeat size={20} />, label: 'Win/Loss Streaks', desc: 'Максимальные серии побед и поражений, текущая серия', anchor: 'streaks' },
                { icon: <Scale size={20} />, label: 'Avg Win / Avg Loss', desc: 'Соотношение среднего выигрыша к среднему убытку', anchor: 'avg-win-loss' },
                { icon: <Tag size={20} />, label: 'Теги и сетапы', desc: 'P&L и win rate по каждому тегу — какие сетапы работают', anchor: 'tags' },
              ].map((m, i) => (
                <Link key={i} href={`/manual#${m.anchor}`} className="cyber-card p-5 group hover:border-accent/40 transition-all duration-300 cursor-pointer block no-underline">
                  <div className="text-amber-400/60 mb-3 group-hover:text-amber-400 transition-colors">{m.icon}</div>
                  <h3 className="font-bold text-sm mb-1">{m.label}</h3>
                  <p className="text-xs text-muted-foreground leading-relaxed mb-2">{m.desc}</p>
                  <span className="text-[10px] font-mono text-accent/0 group-hover:text-accent/60 transition-colors flex items-center gap-1">
                    Подробнее <ArrowRight size={10} />
                  </span>
                </Link>
              ))}
            </div>

            {/* Guide CTA */}
            <div className="text-center mt-10">
              <Link href="/manual" className="inline-flex items-center gap-2 text-sm text-accent hover:text-accent/80 transition-colors font-mono">
                <BookOpen size={16} /> Полное руководство по всем метрикам <ArrowRight size={14} />
              </Link>
            </div>
          </div>
        </section>

        {/* ===== MAE/MFE & POST-EXIT ===== */}
        <section className="relative z-10 py-24 px-6 border-t border-border/50">
          <div className="max-w-6xl mx-auto">
            <div className="grid md:grid-cols-2 gap-16 items-start">
              {/* MAE/MFE */}
              <div>
                <Link href="/manual#mae-mfe" className="flex items-center gap-3 mb-6 group no-underline">
                  <div className="w-10 h-10 rounded-lg bg-accent/10 flex items-center justify-center group-hover:bg-accent/20 transition-colors">
                    <Target size={20} className="text-accent" />
                  </div>
                  <h3 className="text-2xl font-black tracking-tight group-hover:text-accent transition-colors">MAE / MFE анализ</h3>
                  <ArrowRight size={16} className="text-accent/0 group-hover:text-accent/60 transition-colors ml-auto" />
                </Link>
                <p className="text-muted-foreground mb-6 leading-relaxed">
                  Maximum Adverse Excursion (MAE) и Maximum Favorable Excursion (MFE) — ключевые метрики для оптимизации стоп-лоссов и тейк-профитов.
                </p>
                <div className="space-y-4">
                  {[
                    { title: 'Edge Ratio', desc: 'Отношение MFE к MAE — показывает, насколько ваше преимущество перевешивает риск' },
                    { title: 'Quality Score', desc: 'Комплексная оценка сетапа: win rate × efficiency × edge ratio' },
                    { title: 'Группировка', desc: 'Анализ по тегам, сетапам, инструментам, таймфреймам и направлению' },
                    { title: 'Персентили', desc: 'P25, P50, P75 распределения MAE/MFE для точной настройки стопов' },
                  ].map((item, i) => (
                    <div key={i} className="flex gap-3 items-start">
                      <div className="w-1.5 h-1.5 rounded-full bg-accent mt-2 shrink-0" />
                      <div>
                        <span className="font-semibold text-sm">{item.title}</span>
                        <span className="text-muted-foreground text-sm"> — {item.desc}</span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* Post-exit analysis */}
              <div>
                <Link href="/manual#post-exit" className="flex items-center gap-3 mb-6 group no-underline">
                  <div className="w-10 h-10 rounded-lg bg-accent-secondary/10 flex items-center justify-center group-hover:bg-accent-secondary/20 transition-colors">
                    <Clock size={20} className="text-accent-secondary" />
                  </div>
                  <h3 className="text-2xl font-black tracking-tight group-hover:text-accent-secondary transition-colors">Post-Exit анализ</h3>
                  <ArrowRight size={16} className="text-accent-secondary/0 group-hover:text-accent-secondary/60 transition-colors ml-auto" />
                </Link>
                <p className="text-muted-foreground mb-6 leading-relaxed">
                  Что происходит с ценой после вашего выхода? Система загружает реальные свечи и считает, сколько вы оставили на столе.
                </p>
                <div className="space-y-4">
                  {[
                    { title: 'Упущенная прибыль', desc: 'Процент движения цены в вашу сторону после закрытия позиции' },
                    { title: 'Мульти-таймфрейм', desc: 'Анализ на 15м, 1ч, 4ч, 1д — от скальпинга до свинг-трейдинга' },
                    { title: 'Early Exit детекция', desc: 'Автоматическое выявление сделок, закрытых слишком рано' },
                    { title: 'Реальные свечи', desc: 'Данные MOEX ISS API — точные цены, а не модели' },
                  ].map((item, i) => (
                    <div key={i} className="flex gap-3 items-start">
                      <div className="w-1.5 h-1.5 rounded-full bg-accent-secondary mt-2 shrink-0" />
                      <div>
                        <span className="font-semibold text-sm">{item.title}</span>
                        <span className="text-muted-foreground text-sm"> — {item.desc}</span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* ===== AI & BROKER SYNC ===== */}
        <section className="relative z-10 py-24 px-6 border-t border-border/50">
          <div className="max-w-6xl mx-auto">
            <div className="grid md:grid-cols-3 gap-8">
              {/* AI */}
              <div className="cyber-card p-8 border-accent/20 hover:border-accent/40 transition-all duration-300">
                <Brain size={28} className="text-accent mb-4" />
                <h3 className="text-xl font-bold mb-3">AI-аналитика</h3>
                <p className="text-muted-foreground text-sm leading-relaxed mb-4">
                  Каждая сделка оценивается нейросетью: вердикт, анализ ошибок, рекомендации и балл от 1 до 10.
                </p>
                <div className="space-y-2 text-xs text-muted-foreground">
                  <div className="flex items-center gap-2"><Zap size={12} className="text-accent" /> Автоматический анализ при закрытии</div>
                  <div className="flex items-center gap-2"><Zap size={12} className="text-accent" /> Рекомендации по улучшению сетапов</div>
                  <div className="flex items-center gap-2"><Zap size={12} className="text-accent" /> Паттерны в ваших ошибках</div>
                </div>
              </div>

              {/* Broker sync */}
              <div className="cyber-card p-8 border-accent/20 hover:border-accent/40 transition-all duration-300">
                <GitGraph size={28} className="text-accent mb-4" />
                <h3 className="text-xl font-bold mb-3">Синхронизация с брокером</h3>
                <p className="text-muted-foreground text-sm leading-relaxed mb-4">
                  Подключите Тинькофф Инвестиции — сделки, портфель и баланс загрузятся автоматически.
                </p>
                <div className="space-y-2 text-xs text-muted-foreground">
                  <div className="flex items-center gap-2"><Zap size={12} className="text-accent" /> Автоимпорт через Tinkoff Invest API</div>
                  <div className="flex items-center gap-2"><Zap size={12} className="text-accent" /> Портфель и equity curve в реальном времени</div>
                  <div className="flex items-center gap-2"><Zap size={12} className="text-accent" /> Автоматический расчёт комиссий</div>
                </div>
              </div>

              {/* Risk management */}
              <div className="cyber-card p-8 border-accent/20 hover:border-accent/40 transition-all duration-300">
                <Shield size={28} className="text-accent mb-4" />
                <h3 className="text-xl font-bold mb-3">Управление рисками</h3>
                <p className="text-muted-foreground text-sm leading-relaxed mb-4">
                  Optimal F, Kelly Criterion, Risk of Ruin — научный подход к размеру позиции.
                </p>
                <div className="space-y-2 text-xs text-muted-foreground">
                  <Link href="/manual#optimal-f" className="flex items-center gap-2 hover:text-accent transition-colors no-underline"><Zap size={12} className="text-accent" /> Optimal F по P&L и R-мультипликаторам</Link>
                  <Link href="/manual#drawdown" className="flex items-center gap-2 hover:text-accent transition-colors no-underline"><Zap size={12} className="text-accent" /> Drawdown tracking в реальном времени</Link>
                  <Link href="/manual#monte-carlo" className="flex items-center gap-2 hover:text-accent transition-colors no-underline"><Zap size={12} className="text-accent" /> Monte Carlo симуляция 10 000 итераций</Link>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* ===== HOW IT WORKS ===== */}
        <section className="relative z-10 py-24 px-6 border-t border-border/50">
          <div className="max-w-4xl mx-auto">
            <div className="text-center mb-16">
              <p className="text-accent text-xs font-mono uppercase tracking-[0.3em] mb-3">Начните за 2 минуты</p>
              <h2 className="text-4xl font-black tracking-tight">Как это работает</h2>
            </div>

            <div className="grid md:grid-cols-4 gap-6">
              {[
                { step: '01', title: 'Регистрация', desc: 'Создайте аккаунт — email и пароль, или OAuth через Google/GitHub', icon: <LogIn size={20} /> },
                { step: '02', title: 'Импорт сделок', desc: 'Подключите брокера или загрузите отчёт в формате Excel/CSV', icon: <Upload size={20} /> },
                { step: '03', title: 'Анализ', desc: '30+ метрик рассчитываются мгновенно, AI разбирает каждую сделку', icon: <Brain size={20} /> },
                { step: '04', title: 'Рост', desc: 'Находите паттерны, устраняйте слабости, растите как трейдер', icon: <TrendingUp size={20} /> },
              ].map((s, i) => (
                <div key={i} className="text-center">
                  <div className="w-14 h-14 mx-auto mb-4 rounded-full border border-accent/30 bg-accent/5 flex items-center justify-center text-accent">
                    {s.icon}
                  </div>
                  <div className="text-accent font-mono text-xs mb-2">{s.step}</div>
                  <h4 className="font-bold mb-2">{s.title}</h4>
                  <p className="text-xs text-muted-foreground leading-relaxed">{s.desc}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* ===== FINAL CTA ===== */}
        <section className="relative z-10 py-24 px-6 border-t border-border/50">
          <div className="max-w-2xl mx-auto text-center space-y-8">
            <h2 className="text-4xl md:text-5xl font-black tracking-tight">
              Готовы торговать <span className="text-accent">осознанно</span>?
            </h2>
            <p className="text-muted-foreground text-lg">
              Присоединяйтесь к трейдерам, которые принимают решения на основе данных, а не эмоций.
            </p>
            <div className="flex flex-col sm:flex-row gap-4 justify-center">
              <Link href="/register" className="btn-primary px-10 py-4 flex items-center justify-center gap-2 text-base font-semibold">
                Создать аккаунт <ArrowRight size={18} />
              </Link>
              <Link href="/manual" className="btn-secondary px-10 py-4 flex items-center justify-center gap-2 text-base">
                <BookOpen size={18} /> Руководство по метрикам
              </Link>
            </div>

            {/* Footer links */}
            <div className="pt-8 flex justify-center gap-8 text-sm text-muted-foreground">
              <Link href="/manual" className="hover:text-accent transition-colors flex items-center gap-1.5">
                <BookOpen size={14} /> Руководство
              </Link>
              <Link href="/blog" className="hover:text-accent transition-colors flex items-center gap-1.5">
                <FileText size={14} /> Блог
              </Link>
              <Link href="/help" className="hover:text-accent transition-colors flex items-center gap-1.5">
                <HelpCircle size={14} /> Помощь
              </Link>
              <Link href="/pricing" className="hover:text-accent transition-colors flex items-center gap-1.5">
                <Wallet size={14} /> Тарифы
              </Link>
            </div>
          </div>
        </section>
      </main>
    );
  }

  // ==================== AUTHENTICATED DASHBOARD ====================
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
          <div className="mt-3 flex items-center gap-2 text-sm flex-wrap">
            <Wallet size={14} className="text-accent" />
            <span className="text-slate-400">Депозит:</span>
            <span className="font-bold text-accent">{formatCurrency(settings.initialDeposit)}</span>
            {stats?.total_pnl !== undefined && (
              <span className={`text-xs ${(stats.total_pnl_with_unrealized ?? stats.total_pnl) >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                ({(stats.total_pnl_with_unrealized ?? stats.total_pnl) >= 0 ? '+' : ''}{(((stats.total_pnl_with_unrealized ?? stats.total_pnl) / settings.initialDeposit) * 100).toFixed(2)}%)
              </span>
            )}
            {settings.tradesStartDate && (
              <span className="text-xs bg-accent/20 text-accent px-2 py-0.5 rounded-full border border-accent/30">
                📅 С {settings.tradesStartTradeSymbol 
                  ? `${settings.tradesStartTradeSymbol} (${new Date(settings.tradesStartDate).toLocaleDateString('ru-RU', {day: '2-digit', month: '2-digit'})})`
                  : new Date(settings.tradesStartDate).toLocaleDateString('ru-RU', {day: '2-digit', month: '2-digit', year: '2-digit'})
                }
              </span>
            )}
          </div>
        </div>
        <div className="flex gap-3 flex-wrap justify-end items-center">
          <FilterPanel filters={filters} onChange={handleFiltersChange} />
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
              <button onClick={() => setIsSetupModalOpen(true)} className="btn-secondary flex items-center gap-2" title="Управление сетапами">
                <Target size={14} />
              </button>
              <SyncStatusIndicator 
                onTradesUpdated={fetchData}
                onOpenBrokerModal={() => setIsBrokerModalOpen(true)}
              />
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
      <SetupManagerModal
        isOpen={isSetupModalOpen}
        onClose={() => setIsSetupModalOpen(false)}
      />
      <BrokerConnectModal
        isOpen={isBrokerModalOpen}
        onClose={() => setIsBrokerModalOpen(false)}
        onConnectionChange={() => { fetchData(); addLog('Broker sync completed'); }}
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
          {/* Portfolio Widget - показывает баланс и метрики */}
          <PortfolioCard />
          
          {/* Equity Curve - график роста депозита */}
          <EquityCurveCard />
          
          <AIInsightsCard
            recommendations={stats?.mae_mfe_analysis?.recommendations || []}
            optimalF={stats?.optimal_f || 0}
          />
          <MAEMFEAnalysisPanel 
            onRecalculate={() => fetchData()}
          />
          <PostExitCard 
            tradesCount={trades.length}
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
