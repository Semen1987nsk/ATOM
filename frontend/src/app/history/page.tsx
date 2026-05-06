'use client';

import React, { useEffect, useState, useRef, useCallback } from 'react';
import Image from 'next/image';
import Link from 'next/link';
import { Trash2, Upload, Plus, Edit2, ChevronDown, ChevronRight, Lock, ChevronLeft, Settings, X, Eye, EyeOff, BarChart2, Loader2, Calendar, Check } from 'lucide-react';
import { AddTradeModal } from '@/components/AddTradeModal';
import { EditTradeModal } from '@/components/EditTradeModal';
import CloseTradeModal from '@/components/CloseTradeModal';
import { ImportPreviewModal } from '@/components/ImportPreviewModal';
import { AppShell } from '@/components/AppShell';
import { TradeCard } from '@/components/TradeCard';
import { TradeHistorySkeleton } from '@/components/Skeleton';
import { useSettings } from '@/contexts/SettingsContext';
import { api, getApiUrl } from '@/lib/apiClient';

type SortMode = 'latest_activity' | 'opened_at' | 'closed_at';

// Конфигурация колонок
interface ColumnConfig {
  id: string;
  label: string;
  defaultVisible: boolean;
  width?: string;
}

const ALL_COLUMNS: ColumnConfig[] = [
  { id: 'date', label: 'Дата', defaultVisible: true },
  { id: 'ticker', label: 'Тикер', defaultVisible: true },
  { id: 'direction', label: 'Сторона', defaultVisible: true },
  { id: 'entry', label: 'Вход', defaultVisible: true },
  { id: 'exit', label: 'Выход', defaultVisible: true },
  { id: 'quantity', label: 'Кол-во', defaultVisible: true },
  { id: 'setup', label: 'Сетап', defaultVisible: true },
  { id: 'timeframe', label: 'ТФ', defaultVisible: true },
  { id: 'pnl', label: 'PnL', defaultVisible: true },
  { id: 'status', label: 'Статус', defaultVisible: true },
  { id: 'tags', label: 'Теги', defaultVisible: false },
  { id: 'commission', label: 'Комиссия', defaultVisible: false },
  { id: 'swap', label: 'Своп', defaultVisible: false },
  { id: 'confidence', label: 'Уверенность', defaultVisible: false },
  { id: 'risk', label: 'Риск', defaultVisible: false },
  { id: 'rMultiple', label: 'R-Multiple', defaultVisible: false },
  { id: 'leverage', label: 'Плечо', defaultVisible: false },
];

const DIARY_PROMOTED_COLUMNS = ['setup', 'timeframe'];

const STORAGE_KEY = 'eqio_history_columns';
const SORT_STORAGE_KEY = 'eqio_history_sort';

interface Trade {
  id: number;
  symbol: string;
  asset_name?: string;
  asset_type?: string;
  direction: string;
  pnl: number | null;
  net_pnl?: number | null;
  commission?: number;
  entry_commission?: number;
  exit_commission?: number;
  swap?: number;
  leverage?: number;
  confidence?: number;
  mood?: number;
  discipline?: number;
  setup_id?: number;
  setup?: {
    name: string;
    icon: string;
    color: string;
  };
  entry_price: number;
  exit_price?: number;
  quantity: number;
  entry_at: string;
  exit_at?: string;
  setup_name?: string;
  timeframe?: string;
  notes?: string;
  stop_loss?: number;
  take_profit?: number;
  risk_amount?: number;
  news_event?: string;
  screenshot_url?: string;
  tags?: string[];
  ai_analysis?: {
    verdict: string;
    analysis: string;
    advice: string;
    score: number;
  };
  exit_reason?: string;
  isAddition?: boolean;
  // Новые поля
  currency?: string;
  operations?: Array<{
    type: string;
    time: string;
    date: string;
    price: number;
    qty: number;
    commission: number;
    direction: string;
    note?: string;
  }>;
  holding_time_minutes?: number;
  r_multiple?: number;
  position_id?: number;
  entry_reason?: string; // Причина/логика входа (для ИИ анализа)
  mae_price?: number; // Maximum Adverse Excursion - худшая цена
  mfe_price?: number; // Maximum Favorable Excursion - лучшая цена
}

function getTradeSortTimestamp(trade: Trade, sortMode: SortMode): number {
  if (sortMode === 'opened_at') {
    return new Date(trade.entry_at).getTime();
  }

  if (sortMode === 'closed_at') {
    return trade.exit_at ? new Date(trade.exit_at).getTime() : Number.NEGATIVE_INFINITY;
  }

  return new Date(trade.exit_at || trade.entry_at).getTime();
}

export default function HistoryPage() {
  const { settings, updateSettings } = useSettings();
  const [trades, setTrades] = useState<Trade[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedTag, setSelectedTag] = useState<string | null>(null);
  const [filterDirection, setFilterDirection] = useState<'ALL' | 'LONG' | 'SHORT'>('ALL');
  const [tempStartDate, setTempStartDate] = useState<string>(settings.tradesStartDate || '');
  const [tempStartTradeId, setTempStartTradeId] = useState<number | null>(settings.tradesStartTradeId || null);
  const [showDatePicker, setShowDatePicker] = useState(false);
  const [tradesForSelectedDate, setTradesForSelectedDate] = useState<Trade[]>([]);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [isEditModalOpen, setIsEditModalOpen] = useState(false);
  const [isCloseModalOpen, setIsCloseModalOpen] = useState(false);
  const [selectedTrade, setSelectedTrade] = useState<Trade | null>(null);
  const [selectedTradeToClose, setSelectedTradeToClose] = useState<Trade | null>(null);
  const [unrealizedData, setUnrealizedData] = useState<Record<number, { pnl: number; price: number }>>({});
  const [isImportModalOpen, setIsImportModalOpen] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [expandedTrades, setExpandedTrades] = useState<Set<number>>(new Set());
  const [isCalculatingMAE, setIsCalculatingMAE] = useState(false);
  const [maeCalculationResult, setMaeCalculationResult] = useState<{updated: number, failed: number} | null>(null);
  const [showColumnSettings, setShowColumnSettings] = useState(false);
  const [sortMode, setSortMode] = useState<SortMode>(() => {
    if (typeof window !== 'undefined') {
      const saved = localStorage.getItem(SORT_STORAGE_KEY);
      if (saved === 'latest_activity' || saved === 'opened_at' || saved === 'closed_at') {
        return saved;
      }
    }
    return 'latest_activity';
  });
  const [visibleColumns, setVisibleColumns] = useState<Set<string>>(() => {
    // Загружаем из localStorage при инициализации
    if (typeof window !== 'undefined') {
      const saved = localStorage.getItem(STORAGE_KEY);
      if (saved) {
        try {
          const parsed = JSON.parse(saved);
          const savedColumns = new Set(Array.isArray(parsed) ? parsed : []);

          DIARY_PROMOTED_COLUMNS.forEach((columnId) => {
            savedColumns.add(columnId);
          });

          return savedColumns;
        } catch {
          // Если ошибка парсинга, используем дефолтные
        }
      }
    }
    return new Set(ALL_COLUMNS.filter(c => c.defaultVisible).map(c => c.id));
  });

  // Horizontal scroll state
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const [canScrollLeft, setCanScrollLeft] = useState(false);
  const [canScrollRight, setCanScrollRight] = useState(false);

  const updateScrollState = useCallback(() => {
    const container = scrollContainerRef.current;
    if (container) {
      setCanScrollLeft(container.scrollLeft > 0);
      setCanScrollRight(container.scrollLeft < container.scrollWidth - container.clientWidth - 1);
    }
  }, []);

  const scrollTable = useCallback((direction: 'left' | 'right') => {
    const container = scrollContainerRef.current;
    if (container) {
      const scrollAmount = 300;
      container.scrollBy({
        left: direction === 'left' ? -scrollAmount : scrollAmount,
        behavior: 'smooth'
      });
    }
  }, []);

  useEffect(() => {
    const container = scrollContainerRef.current;
    if (container) {
      // Delay initial check to ensure DOM is fully rendered
      const timeoutId = setTimeout(updateScrollState, 100);
      container.addEventListener('scroll', updateScrollState);
      window.addEventListener('resize', updateScrollState);

      // Also use ResizeObserver for more reliable detection
      const resizeObserver = new ResizeObserver(() => {
        updateScrollState();
      });
      resizeObserver.observe(container);

      return () => {
        clearTimeout(timeoutId);
        container.removeEventListener('scroll', updateScrollState);
        window.removeEventListener('resize', updateScrollState);
        resizeObserver.disconnect();
      };
    }
  }, [updateScrollState, trades, loading]);

  const fetchTrades = async () => {
    try {
      const data = await api.get<Trade[]>('/trades/');
      setTrades(data);
    } catch (error) {
      console.error('Failed to fetch trades:', error);
    } finally {
      setLoading(false);
    }
  };

  const fetchUnrealizedPnL = async () => {
    try {
        const data = await api.get<Array<{trade_id: number; unrealized_pnl: number; current_price: number}>>('/trades/unrealized-pnl');
      const map: Record<number, { pnl: number; price: number }> = {};
      data.forEach((item) => {
            map[item.trade_id] = { pnl: item.unrealized_pnl, price: item.current_price };
        });
        setUnrealizedData(map);
    } catch (e) {
        console.error(e);
    }
  };

  useEffect(() => {
    fetchTrades();
    fetchUnrealizedPnL();
    const interval = setInterval(fetchUnrealizedPnL, 10000); // 10 sec
    return () => clearInterval(interval);
  }, []);

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
      fetchTrades();
    } catch (error) {
      console.error('Failed to close trade:', error);
    }
  };

  const handleEdit = (trade: Trade) => {
    setSelectedTrade(trade);
    setIsEditModalOpen(true);
  };

  const handleDelete = async (tradeId: number) => {
    if (!confirm('Вы уверены, что хотите удалить эту сделку?')) return;
    try {
      await api.delete(`/trades/${tradeId}`);
      fetchTrades();
    } catch (error) {
      console.error('Delete failed:', error);
    }
  };

  const handleDeleteAllTrades = async () => {
    setIsDeleting(true);
    try {
      // Удаляем все сделки по одной
      for (const trade of trades) {
        await api.delete(`/trades/${trade.id}`);
      }
      setShowDeleteConfirm(false);
      fetchTrades();
    } catch (error) {
      console.error('Delete all failed:', error);
      alert('Ошибка при удалении сделок');
    } finally {
      setIsDeleting(false);
    }
  };

  const allTags = Array.from(new Set(trades.flatMap(t => t.tags || [])));

  // Logic to detect additions (averaging/pyramiding)
  const enrichedTrades = trades.map(trade => {
    // We assume 'trades' is sorted Newest First (as per fetchTrades).
    // To check if 'trade' is an addition, we look for OLDER trades (which are AFTER it in the array)
    // that overlap with it.
    // Actually, it's safer to look at the whole list.

    const isAddition = trades.some(other =>
      other.id !== trade.id && // Not self
      other.symbol === trade.symbol && // Same symbol
      other.direction === trade.direction && // Same direction
      new Date(other.entry_at).getTime() < new Date(trade.entry_at).getTime() && // Other started BEFORE this one
      (other.exit_at ? new Date(other.exit_at).getTime() > new Date(trade.entry_at).getTime() : true) // Other ended AFTER this one started (or is still open)
    );

    return { ...trade, isAddition };
  });

  const filteredTrades = enrichedTrades.filter(t => {
    const matchesTag = selectedTag ? t.tags?.includes(selectedTag) : true;
    const matchesDirection = filterDirection === 'ALL' ? true : t.direction.toUpperCase() === filterDirection;

    // Фильтр по дате/сделке начала из настроек
    let matchesStart = true;
    if (settings.tradesStartTradeId) {
      // Если выбрана конкретная сделка — показываем только сделки начиная с неё
      const startTrade = trades.find(tr => tr.id === settings.tradesStartTradeId);
      if (startTrade) {
        matchesStart = new Date(t.entry_at) >= new Date(startTrade.entry_at);
      }
    } else if (settings.tradesStartDate) {
      // Если только дата — показываем сделки с начала этого дня
      matchesStart = new Date(t.entry_at) >= new Date(settings.tradesStartDate);
    }

    return matchesTag && matchesDirection && matchesStart;
  });

  const sortedTrades = [...filteredTrades].sort(
    (a, b) => {
      const primaryDiff = getTradeSortTimestamp(b, sortMode) - getTradeSortTimestamp(a, sortMode);
      if (primaryDiff !== 0) {
        return primaryDiff;
      }

      return new Date(b.entry_at).getTime() - new Date(a.entry_at).getTime();
    }
  );

  const toggleTrade = (tradeId: number) => {
    const newSet = new Set(expandedTrades);
    if (newSet.has(tradeId)) newSet.delete(tradeId);
    else newSet.add(tradeId);
    setExpandedTrades(newSet);
  };

  const toggleColumn = (columnId: string) => {
    const newSet = new Set(visibleColumns);
    if (newSet.has(columnId)) {
      // Не позволяем скрыть все колонки - минимум 3
      if (newSet.size > 3) {
        newSet.delete(columnId);
      }
    } else {
      newSet.add(columnId);
    }
    setVisibleColumns(newSet);
    localStorage.setItem(STORAGE_KEY, JSON.stringify([...newSet]));
  };

  const resetColumns = () => {
    const defaultCols = new Set(ALL_COLUMNS.filter(c => c.defaultVisible).map(c => c.id));
    setVisibleColumns(defaultCols);
    localStorage.setItem(STORAGE_KEY, JSON.stringify([...defaultCols]));
  };

  const isColumnVisible = (columnId: string) => visibleColumns.has(columnId);

  // Расчёт MAE/MFE для всех сделок
  const calculateMAEMFE = async (tradeIds?: number[]) => {
    setIsCalculatingMAE(true);
    setMaeCalculationResult(null);
    try {
      const result = await api.post<{updated: number; failed: number}>('/trades/calculate-mae-mfe', {
        body: tradeIds || null
      });
      setMaeCalculationResult({ updated: result.updated, failed: result.failed });
      // Перезагружаем сделки чтобы увидеть обновлённые данные
      const data = await api.get<Trade[]>('/trades/');
      setTrades(data);
      // Скрываем результат через 5 секунд
      setTimeout(() => setMaeCalculationResult(null), 5000);
    } catch (error) {
      console.error('Error calculating MAE/MFE:', error);
    } finally {
      setIsCalculatingMAE(false);
    }
  };

  if (loading) return <TradeHistorySkeleton />;

  // Page-specific actions для AppShell.headerRight (column settings, theme, etc).
  // Column-settings popup стартует из той же кнопки, но теперь живёт в шапке страницы.
  return (
    <AppShell
      pageTitle="Дневник сделок"
      onAddTrade={() => setIsModalOpen(true)}
      onImport={() => setIsImportModalOpen(true)}
    >
    <div className="p-6 md:p-8 max-w-7xl mx-auto">
      <div className="mb-6 flex justify-between items-center">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Дневник сделок</h1>
          <p className="text-sm text-[var(--text-secondary)] mt-1">
            Все ваши закрытые и открытые позиции
          </p>
        </div>
        <div className="flex gap-2 items-center">
          <div className="relative">
            <button
              onClick={() => setShowColumnSettings(!showColumnSettings)}
              className={`p-2 rounded-lg border transition-all cursor-pointer ${
                showColumnSettings
                  ? 'border-accent bg-accent/20 text-accent'
                  : 'border-border hover:border-accent/50 text-slate-400 hover:text-accent'
              }`}
              title="Настройки колонок"
            >
              <Settings size={18} />
            </button>

            {/* Column Settings Panel */}
            {showColumnSettings && (
              <div className="absolute right-0 top-12 z-50 bg-slate-900 border border-border rounded-xl shadow-2xl p-4 w-72">
                <div className="flex items-center justify-between mb-4">
                  <h3 className="font-bold text-white flex items-center gap-2">
                    <Settings size={16} className="text-accent" />
                    Колонки таблицы
                  </h3>
                  <button
                    onClick={() => setShowColumnSettings(false)}
                    className="text-slate-400 hover:text-white"
                  >
                    <X size={18} />
                  </button>
                </div>

                <div className="space-y-1 max-h-80 overflow-y-auto">
                  {ALL_COLUMNS.map(col => (
                    <button
                      key={col.id}
                      onClick={() => toggleColumn(col.id)}
                      className={`w-full flex items-center justify-between p-2 rounded-lg transition-all ${
                        isColumnVisible(col.id)
                          ? 'bg-accent/20 text-accent'
                          : 'bg-slate-800/50 text-slate-400 hover:bg-slate-800'
                      }`}
                    >
                      <span className="text-sm">{col.label}</span>
                      {isColumnVisible(col.id) ? (
                        <Eye size={16} className="text-accent" />
                      ) : (
                        <EyeOff size={16} className="text-slate-500" />
                      )}
                    </button>
                  ))}
                </div>

                <div className="mt-4 pt-4 border-t border-border flex justify-between items-center">
                  <span className="text-xs text-slate-500">
                    {visibleColumns.size} из {ALL_COLUMNS.length} колонок
                  </span>
                  <button
                    onClick={resetColumns}
                    className="text-xs text-accent hover:underline"
                  >
                    Сбросить
                  </button>
                </div>
              </div>
            )}
          </div>
          {trades.length > 0 && (
            <button
              onClick={() => setShowDeleteConfirm(true)}
              className="btn-danger flex items-center gap-2 cursor-pointer"
              title="Удалить все сделки"
            >
              <Trash2 size={14} />
              Удалить все
            </button>
          )}
          {trades.filter(t => t.exit_at && (!t.mae_price || !t.mfe_price)).length > 0 && (
            <button
              onClick={() => calculateMAEMFE()}
              disabled={isCalculatingMAE}
              className="btn-secondary flex items-center gap-2 cursor-pointer disabled:opacity-50"
              title="Рассчитать MAE/MFE для всех сделок"
            >
              {isCalculatingMAE ? (
                <Loader2 size={14} className="animate-spin" />
              ) : (
                <BarChart2 size={14} />
              )}
              {isCalculatingMAE ? 'Расчёт...' : 'MAE/MFE'}
            </button>
          )}
          {maeCalculationResult && (
            <span className="text-xs bg-accent/20 text-accent px-2 py-1 rounded" title="Фонды ликвидности и облигации не поддерживаются - нет свечных данных на MOEX">
              ✓ Обновлено: {maeCalculationResult.updated}{maeCalculationResult.failed > 0 && `, пропущено: ${maeCalculationResult.failed}`}
            </span>
          )}
          <button
            onClick={() => setIsImportModalOpen(true)}
            className="btn-secondary flex items-center gap-2 cursor-pointer"
          >
            <Upload size={14} />
            Импорт
          </button>
          <button
            onClick={() => setIsModalOpen(true)}
            className="btn-primary flex items-center gap-2"
          >
            <Plus size={14} /> Новая позиция
          </button>
        </div>
      </div>

      <AddTradeModal
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        onSuccess={() => fetchTrades()}
      />

      <EditTradeModal
        isOpen={isEditModalOpen}
        onClose={() => setIsEditModalOpen(false)}
        onSuccess={() => fetchTrades()}
        trade={selectedTrade}
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

      <ImportPreviewModal
        isOpen={isImportModalOpen}
        onClose={() => setIsImportModalOpen(false)}
        onSuccess={() => fetchTrades()}
      />

      {/* Delete Confirmation Modal */}
      {showDeleteConfirm && (
        <div className="fixed inset-0 bg-black/70 backdrop-blur-sm flex items-center justify-center z-50">
          <div className="bg-slate-900 border border-red-500/50 rounded-2xl p-6 max-w-md w-full mx-4 shadow-2xl">
            <div className="flex items-center gap-3 mb-4">
              <div className="w-12 h-12 rounded-full bg-red-500/20 flex items-center justify-center">
                <Trash2 className="w-6 h-6 text-red-500" />
              </div>
              <div>
                <h3 className="text-xl font-bold text-white">Удалить все сделки?</h3>
                <p className="text-slate-400 text-sm">Это действие нельзя отменить</p>
              </div>
            </div>

            <p className="text-slate-300 mb-6">
              Вы уверены, что хотите удалить <span className="font-bold text-red-400">{trades.length}</span> сделок?
              Все данные будут безвозвратно потеряны.
            </p>

            <div className="flex gap-3 justify-end">
              <button
                onClick={() => setShowDeleteConfirm(false)}
                disabled={isDeleting}
                className="px-4 py-2 rounded-lg bg-slate-700 hover:bg-slate-600 text-white transition-colors"
              >
                Отмена
              </button>
              <button
                onClick={handleDeleteAllTrades}
                disabled={isDeleting}
                className="px-4 py-2 rounded-lg bg-red-600 hover:bg-red-500 text-white transition-colors flex items-center gap-2 disabled:opacity-50"
              >
                {isDeleting ? (
                  <>
                    <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                    Удаление...
                  </>
                ) : (
                  <>
                    <Trash2 size={16} />
                    Удалить всё
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}

      <div className="cyber-card p-6">
        <div className="flex flex-wrap gap-4 mb-6 items-center">
          {/* Direction Filter */}
          <div className="flex items-center border border-border rounded-none overflow-hidden">
            <button
              onClick={() => setFilterDirection('ALL')}
              className={`px-3 py-1.5 text-xs font-mono uppercase transition-colors ${filterDirection === 'ALL' ? 'bg-accent text-black font-bold' : 'hover:bg-white/10 text-slate-300'}`}
            >
              Все
            </button>
            <div className="w-px h-full bg-border"></div>
            <button
              onClick={() => setFilterDirection('LONG')}
              className={`px-3 py-1.5 text-xs font-mono uppercase transition-colors ${filterDirection === 'LONG' ? 'bg-green-500 text-black font-bold' : 'hover:bg-white/10 text-green-400'}`}
            >
              Лонг
            </button>
            <div className="w-px h-full bg-border"></div>
            <button
              onClick={() => setFilterDirection('SHORT')}
              className={`px-3 py-1.5 text-xs font-mono uppercase transition-colors ${filterDirection === 'SHORT' ? 'bg-red-500 text-black font-bold' : 'hover:bg-white/10 text-red-400'}`}
            >
              Шорт
            </button>
          </div>

          <div className="w-px h-6 bg-border mx-2 hidden sm:block"></div>

          {/* Date Filter */}
          <div className="flex items-center gap-2">
            <button
              onClick={() => {
                setShowDatePicker(!showDatePicker);
                // Загружаем сделки за сохраненную дату при открытии
                if (!showDatePicker && settings.tradesStartDate) {
                  const dateStart = new Date(settings.tradesStartDate);
                  dateStart.setHours(0, 0, 0, 0);
                  const dateEnd = new Date(settings.tradesStartDate);
                  dateEnd.setHours(23, 59, 59, 999);
                  const filtered = trades.filter(t => {
                    const tradeDate = new Date(t.entry_at);
                    return tradeDate >= dateStart && tradeDate <= dateEnd;
                  }).sort((a, b) => new Date(a.entry_at).getTime() - new Date(b.entry_at).getTime());
                  setTradesForSelectedDate(filtered);
                }
              }}
              className={`flex items-center gap-2 px-3 py-1.5 text-xs font-mono border transition-colors ${
                settings.tradesStartDate
                  ? 'border-accent text-accent bg-accent/10'
                  : 'border-border text-slate-400 hover:text-slate-300 hover:border-accent/50'
              }`}
              title="Фильтр по дате начала"
            >
              <Calendar size={14} />
              {settings.tradesStartDate
                ? settings.tradesStartTradeSymbol
                  ? `С ${settings.tradesStartTradeSymbol} (${new Date(settings.tradesStartDate).toLocaleDateString('ru-RU', {day: '2-digit', month: '2-digit'})})`
                  : `С ${new Date(settings.tradesStartDate).toLocaleDateString('ru-RU', {day: '2-digit', month: '2-digit', year: '2-digit'})}`
                : 'Дата начала'
              }
            </button>

            {showDatePicker && (
              <div className="absolute top-20 left-4 z-50 bg-slate-900 border border-border rounded-xl shadow-2xl p-4 min-w-80">
                <div className="flex flex-col gap-3">
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-bold text-white">Показывать сделки с:</span>
                    <button onClick={() => setShowDatePicker(false)} className="text-slate-400 hover:text-white">
                      <X size={16} />
                    </button>
                  </div>

                  {/* Шаг 1: Выбор даты */}
                  <div>
                    <label className="text-xs text-slate-400 mb-1 block">1. Выберите дату:</label>
                    <input
                      type="date"
                      value={tempStartDate}
                      onChange={(e) => {
                        setTempStartDate(e.target.value);
                        setTempStartTradeId(null);
                        // Фильтруем сделки за выбранную дату
                        if (e.target.value) {
                          const dateStart = new Date(e.target.value);
                          dateStart.setHours(0, 0, 0, 0);
                          const dateEnd = new Date(e.target.value);
                          dateEnd.setHours(23, 59, 59, 999);
                          const filtered = trades.filter(t => {
                            const tradeDate = new Date(t.entry_at);
                            return tradeDate >= dateStart && tradeDate <= dateEnd;
                          }).sort((a, b) => new Date(a.entry_at).getTime() - new Date(b.entry_at).getTime());
                          setTradesForSelectedDate(filtered);
                        } else {
                          setTradesForSelectedDate([]);
                        }
                      }}
                      className="w-full bg-slate-800 border border-border rounded-lg px-3 py-2 text-white text-sm"
                      style={{ colorScheme: 'dark' }}
                    />
                  </div>

                  {/* Шаг 2: Выбор сделки (если есть сделки за эту дату) */}
                  {tempStartDate && tradesForSelectedDate.length > 0 && (
                    <div>
                      <label className="text-xs text-slate-400 mb-1 block">
                        2. Выберите сделку ({tradesForSelectedDate.length} за этот день):
                      </label>
                      <div className="max-h-40 overflow-y-auto bg-slate-800 border border-border rounded-lg">
                        <button
                          onClick={() => setTempStartTradeId(null)}
                          className={`w-full text-left px-3 py-2 text-xs hover:bg-slate-700 transition-colors border-b border-border ${
                            tempStartTradeId === null ? 'bg-accent/20 text-accent' : 'text-slate-300'
                          }`}
                        >
                          📅 Все сделки с этой даты
                        </button>
                        {tradesForSelectedDate.map((trade) => (
                          <button
                            key={trade.id}
                            onClick={() => setTempStartTradeId(trade.id)}
                            className={`w-full text-left px-3 py-2 text-xs hover:bg-slate-700 transition-colors border-b border-border last:border-0 ${
                              tempStartTradeId === trade.id ? 'bg-accent/20 text-accent' : 'text-slate-300'
                            }`}
                          >
                            <div className="flex items-center justify-between">
                              {(() => {
                                const pnlPreviewValue = trade.net_pnl ?? trade.pnl;
                                return (
                                  <>
                              <span className="font-mono">
                                {new Date(trade.entry_at).toLocaleTimeString('ru-RU', {hour: '2-digit', minute: '2-digit'})}
                                {' '}
                                <span className={trade.direction === 'LONG' ? 'text-green-400' : 'text-red-400'}>
                                  {trade.direction}
                                </span>
                                {' '}
                                {trade.symbol}
                              </span>
                              <span className={pnlPreviewValue !== null && pnlPreviewValue !== undefined && pnlPreviewValue >= 0 ? 'text-green-400' : 'text-red-400'}>
                                {trade.exit_at
                                  ? (pnlPreviewValue !== null && pnlPreviewValue !== undefined
                                      ? `${pnlPreviewValue > 0 ? '+' : ''}${pnlPreviewValue.toFixed(0)}₽`
                                      : '0₽')
                                  : 'ОТКРЫТА'}
                              </span>
                                  </>
                                );
                              })()}
                            </div>
                          </button>
                        ))}
                      </div>
                    </div>
                  )}

                  {tempStartDate && tradesForSelectedDate.length === 0 && (
                    <p className="text-xs text-yellow-500">⚠️ Нет сделок за выбранную дату</p>
                  )}

                  <div className="flex gap-2">
                    <button
                      onClick={() => {
                        const selectedTrade = tempStartTradeId
                          ? tradesForSelectedDate.find(t => t.id === tempStartTradeId)
                          : null;
                        updateSettings({
                          tradesStartDate: tempStartDate || null,
                          tradesStartTradeId: tempStartTradeId,
                          tradesStartTradeSymbol: selectedTrade ? selectedTrade.symbol : null
                        });
                        setShowDatePicker(false);
                      }}
                      disabled={!tempStartDate}
                      className="flex-1 flex items-center justify-center gap-1 px-3 py-2 bg-accent text-black font-bold text-xs rounded-lg hover:bg-accent/90 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      <Check size={14} />
                      Сохранить
                    </button>
                    {(settings.tradesStartDate || settings.tradesStartTradeId) && (
                      <button
                        onClick={() => {
                          setTempStartDate('');
                          setTempStartTradeId(null);
                          setTradesForSelectedDate([]);
                          updateSettings({
                            tradesStartDate: null,
                            tradesStartTradeId: null,
                            tradesStartTradeSymbol: null
                          });
                          setShowDatePicker(false);
                        }}
                        className="px-3 py-2 border border-red-500/50 text-red-400 text-xs rounded-lg hover:bg-red-500/10 transition-colors"
                      >
                        Сбросить
                      </button>
                    )}
                  </div>

                  <p className="text-xs text-slate-500">
                    Эта настройка влияет на все расчеты и дашборд
                  </p>
                </div>
              </div>
            )}
          </div>

          <div className="w-px h-6 bg-border mx-2 hidden sm:block"></div>

          <div className="flex items-center gap-2">
            <label className="text-[10px] font-mono uppercase tracking-wider text-slate-500">
              Сортировка
            </label>
            <select
              value={sortMode}
              onChange={(e) => {
                const nextSortMode = e.target.value as SortMode;
                setSortMode(nextSortMode);
                localStorage.setItem(SORT_STORAGE_KEY, nextSortMode);
              }}
              className="bg-slate-900 border border-border text-slate-200 text-xs font-mono px-3 py-1.5 rounded-lg focus:outline-none focus:border-accent"
            >
              <option value="latest_activity">Последняя активность</option>
              <option value="opened_at">По дате открытия</option>
              <option value="closed_at">По дате закрытия</option>
            </select>
          </div>

          {/* Tag Filter */}
          <div className="flex gap-2 overflow-x-auto no-scrollbar max-w-full">
            <button
              onClick={() => setSelectedTag(null)}
              className={`text-xs font-mono px-3 py-1.5 border whitespace-nowrap ${!selectedTag ? 'border-accent text-accent' : 'border-border text-slate-400 hover:text-slate-300'}`}
            >
              ВСЕ ТЕГИ
            </button>
            {allTags.map(tag => (
              <button
                key={tag}
                onClick={() => setSelectedTag(tag)}
                className={`text-xs font-mono px-3 py-1.5 border whitespace-nowrap transition-colors ${selectedTag === tag ? 'border-accent text-accent bg-accent/10' : 'border-border text-slate-400 hover:text-slate-300 hover:border-accent/40'}`}
              >
                #{tag}
              </button>
            ))}
          </div>

          <div className="flex items-center gap-2 ml-auto">
            <button
              onClick={() => scrollTable('left')}
              disabled={!canScrollLeft}
              className={`p-2 rounded-lg border transition-all ${
                canScrollLeft
                  ? 'border-accent/50 bg-accent/10 text-accent hover:bg-accent/20 cursor-pointer'
                  : 'border-border/30 text-slate-600 cursor-not-allowed'
              }`}
              title="Прокрутить влево"
            >
              <ChevronLeft size={18} />
            </button>
            <button
              onClick={() => scrollTable('right')}
              disabled={!canScrollRight}
              className={`p-2 rounded-lg border transition-all ${
                canScrollRight
                  ? 'border-accent/50 bg-accent/10 text-accent hover:bg-accent/20 cursor-pointer'
                  : 'border-border/30 text-slate-600 cursor-not-allowed'
              }`}
              title="Прокрутить вправо"
            >
              <ChevronRight size={18} />
            </button>
          </div>
        </div>

        {/* Table Container with scroll shadows */}
        <div className="relative">
          {/* Left shadow indicator */}
          <div
            className={`absolute left-0 top-0 bottom-0 w-8 bg-gradient-to-r from-slate-900/90 to-transparent pointer-events-none z-10 transition-opacity duration-200 ${
              canScrollLeft ? 'opacity-100' : 'opacity-0'
            }`}
          />
          {/* Right shadow indicator */}
          <div
            className={`absolute right-0 top-0 bottom-0 w-8 bg-gradient-to-l from-slate-900/90 to-transparent pointer-events-none z-10 transition-opacity duration-200 ${
              canScrollRight ? 'opacity-100' : 'opacity-0'
            }`}
          />

          {/* Mobile card view — viewport < md
              Таблица 16 колонок на телефоне = катастрофа. На узких экранах
              показываем вертикальный список карточек. */}
          <div className="md:hidden space-y-2">
            {sortedTrades.length === 0 ? (
              <div className="text-center py-10 text-[13px] text-[var(--text-tertiary)]">
                Нет сделок по текущему фильтру.
              </div>
            ) : (
              sortedTrades.map((trade) => (
                <TradeCard
                  key={trade.id}
                  trade={trade as Parameters<typeof TradeCard>[0]['trade']}
                  onEdit={(id) => {
                    const t = sortedTrades.find((tr) => tr.id === id);
                    if (t) {
                      setSelectedTrade(t);
                      setIsEditModalOpen(true);
                    }
                  }}
                  onDelete={(id) => handleDelete(id)}
                />
              ))
            )}
          </div>

          {/* Desktop table view — viewport >= md */}
          <div
            ref={scrollContainerRef}
            className="hidden md:block overflow-x-auto scrollbar-thin scrollbar-track-transparent scrollbar-thumb-accent/30 hover:scrollbar-thumb-accent/50"
            style={{ maxHeight: 'calc(100vh - 300px)' }}
          >
          <table className="w-full text-left border-collapse">
              <thead className="sticky top-0 z-20 bg-slate-900/95 backdrop-blur-sm">
              <tr className="text-xs font-mono uppercase text-slate-400 border-b border-border">
                  <th className="py-2 pl-2 w-8"></th>
                  {isColumnVisible('date') && <th className="py-2 w-40">Даты</th>}
                  {isColumnVisible('ticker') && <th className="py-2 w-20">Тикер</th>}
                  {isColumnVisible('direction') && <th className="py-2 w-14">Стор.</th>}
                  {isColumnVisible('entry') && <th className="py-2 w-20">Вход</th>}
                  {isColumnVisible('exit') && <th className="py-2 w-20">Выход</th>}
                  {isColumnVisible('quantity') && <th className="py-2 w-16">Кол-во</th>}
                  {isColumnVisible('setup') && <th className="py-2 w-24">Сетап</th>}
                  {isColumnVisible('timeframe') && <th className="py-2 w-14">ТФ</th>}
                  {isColumnVisible('commission') && <th className="py-2 w-20">Комис.</th>}
                  {isColumnVisible('swap') && <th className="py-2 w-16">Своп</th>}
                  {isColumnVisible('confidence') && <th className="py-2 w-12">Увер.</th>}
                  {isColumnVisible('risk') && <th className="py-2 w-20">Риск</th>}
                  {isColumnVisible('rMultiple') && <th className="py-2 w-16">R</th>}
                  {isColumnVisible('pnl') && <th className="py-2 w-24">PnL</th>}
                  {isColumnVisible('status') && <th className="py-2 w-16">Статус</th>}
                  {isColumnVisible('tags') && <th className="py-2 w-24">Теги</th>}
                  {isColumnVisible('leverage') && <th className="py-2 w-12">Плечо</th>}
                  <th className="py-2 w-16 text-right pr-2">Действ.</th>
              </tr>
            </thead>
            <tbody className="text-sm">
              {sortedTrades.map((trade) => {
                const isExpanded = expandedTrades.has(trade.id);
                const hasDetails = trade.setup_name || trade.news_event || trade.notes || trade.entry_reason || trade.tags?.length || trade.operations?.length || trade.mood || trade.discipline || trade.screenshot_url || trade.setup;

                const formatHoldingTime = (minutes: number | undefined) => {
                  if (!minutes) return '-';
                  if (minutes < 60) return `${minutes}м`;
                  if (minutes < 1440) return `${Math.floor(minutes / 60)}ч`;
                  return `${Math.floor(minutes / 1440)}д`;
                };

                const pnlValue = trade.net_pnl ?? trade.pnl;
                const unrealized = trade.exit_at ? undefined : unrealizedData[trade.id];

                return (
                  <React.Fragment key={trade.id}>
                    {/* Компактная строка */}
                    <tr
                      className={`border-b border-border/30 hover:bg-white/5 transition-colors ${hasDetails ? 'cursor-pointer' : ''}`}
                      onClick={() => hasDetails && toggleTrade(trade.id)}
                    >
                      {/* Expand Icon */}
                      <td className="py-2 pl-2">
                        {hasDetails && (
                          <button className="text-accent/50 hover:text-accent">
                            {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                          </button>
                        )}
                      </td>

                      {/* Дата */}
                      {isColumnVisible('date') && (
                        <td className="py-2 font-mono text-xs">
                          <div className="flex flex-col gap-1 leading-tight">
                            <div>
                              <span className="text-[9px] uppercase tracking-wide text-slate-500 mr-1">ВХ</span>
                              <span>{new Date(trade.entry_at).toLocaleDateString('ru-RU', {day: '2-digit', month: '2-digit', year: '2-digit'})}</span>
                              <span className="text-slate-500 ml-1 text-[10px]">
                                {new Date(trade.entry_at).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'})}
                              </span>
                            </div>
                            <div>
                              <span className="text-[9px] uppercase tracking-wide text-slate-500 mr-1">ВЫХ</span>
                              {trade.exit_at ? (
                                <>
                                  <span>{new Date(trade.exit_at).toLocaleDateString('ru-RU', {day: '2-digit', month: '2-digit', year: '2-digit'})}</span>
                                  <span className="text-slate-500 ml-1 text-[10px]">
                                    {new Date(trade.exit_at).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'})}
                                  </span>
                                </>
                              ) : (
                                <span className="text-accent/80">ОТКРЫТА</span>
                              )}
                            </div>
                          </div>
                        </td>
                      )}

                      {/* Тикер */}
                      {isColumnVisible('ticker') && (
                        <td className="py-2">
                          <span className="font-bold">{trade.symbol}</span>
                          {trade.asset_name && (
                            <span className="text-slate-500 text-[10px] ml-1 hidden sm:inline">{trade.asset_name.slice(0, 8)}</span>
                          )}
                        </td>
                      )}

                      {/* Сторона */}
                      {isColumnVisible('direction') && (
                        <td className="py-2">
                          <span className={`text-[10px] font-mono px-1.5 py-0.5 rounded ${
                            trade.direction === 'long' ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400'
                          }`}>
                            {trade.isAddition ? '+ ДОБ.' : (trade.direction === 'long' ? 'ЛОНГ' : 'ШОРТ')}
                          </span>
                        </td>
                      )}

                      {/* Вход */}
                      {isColumnVisible('entry') && (
                        <td className="py-2 font-mono text-xs">
                          {trade.entry_price.toLocaleString('ru-RU', { maximumFractionDigits: 2 })}
                        </td>
                      )}

                      {/* Выход */}
                      {isColumnVisible('exit') && (
                        <td className="py-2 font-mono text-xs">
                          {trade.exit_price
                            ? trade.exit_price.toLocaleString('ru-RU', { maximumFractionDigits: 2 })
                            : <span className="text-slate-500">—</span>
                          }
                        </td>
                      )}

                      {/* Кол-во */}
                      {isColumnVisible('quantity') && (
                        <td className="py-2 font-mono text-xs">
                          {trade.quantity.toLocaleString('ru-RU')}
                        </td>
                      )}

                      {/* Сетап */}
                      {isColumnVisible('setup') && (
                        <td className="py-2 text-xs max-w-24">
                          {trade.setup ? (
                            <div className="flex items-center gap-1 truncate">
                              <span style={{ color: trade.setup.color }}>{trade.setup.icon}</span>
                              <span className="truncate" style={{ color: trade.setup.color }}>{trade.setup.name}</span>
                            </div>
                          ) : (
                            <span className="text-slate-400 truncate block">{trade.setup_name || '—'}</span>
                          )}
                        </td>
                      )}

                      {/* Таймфрейм */}
                      {isColumnVisible('timeframe') && (
                        <td className="py-2 text-center">
                          <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-cyan-500/10 text-cyan-300 border border-cyan-500/20">
                            {trade.timeframe || '—'}
                          </span>
                        </td>
                      )}

                      {/* Комиссия */}
                      {isColumnVisible('commission') && (
                        <td className="py-2 font-mono text-xs text-red-400">
                          {(trade.commission || 0) > 0 ? `-${Number(trade.commission).toFixed(0)}` : '—'}
                        </td>
                      )}

                      {/* Своп */}
                      {isColumnVisible('swap') && (
                        <td className="py-2 font-mono text-xs text-red-400">
                          {(trade.swap || 0) > 0 ? `-${Number(trade.swap).toFixed(0)}` : '—'}
                        </td>
                      )}

                      {/* Уверенность */}
                      {isColumnVisible('confidence') && (
                        <td className="py-2 text-center">
                          {trade.confidence ? (
                            <span className={`text-[10px] font-mono px-1.5 py-0.5 rounded ${
                              trade.confidence >= 8 ? 'bg-green-500/20 text-green-400' :
                              trade.confidence >= 5 ? 'bg-yellow-500/20 text-yellow-400' :
                              'bg-red-500/20 text-red-400'
                            }`}>{trade.confidence}</span>
                          ) : '—'}
                        </td>
                      )}

                      {/* Риск */}
                      {isColumnVisible('risk') && (
                        <td className="py-2 font-mono text-xs">
                          {trade.risk_amount ? `${trade.risk_amount.toLocaleString('ru-RU')} ₽` : '—'}
                        </td>
                      )}

                      {/* R-Multiple */}
                      {isColumnVisible('rMultiple') && (
                        <td className="py-2 font-mono text-xs">
                          {trade.r_multiple ? (
                            <span className={trade.r_multiple >= 1 ? 'text-green-400' : trade.r_multiple < 0 ? 'text-red-400' : ''}>
                              {trade.r_multiple.toFixed(1)}R
                            </span>
                          ) : '—'}
                        </td>
                      )}

                      {/* PnL */}
                      {isColumnVisible('pnl') && (() => {
                        // Расчёт процента между ценами входа и выхода
                        let pnlPercent = 0;
                        if (trade.entry_price > 0) {
                          if (unrealized?.price) {
                            // Открытая позиция - считаем от текущей цены
                            const isLong = trade.direction.toLowerCase() === 'long';
                            pnlPercent = isLong
                              ? ((unrealized.price - trade.entry_price) / trade.entry_price * 100)
                              : ((trade.entry_price - unrealized.price) / trade.entry_price * 100);
                          } else if (trade.exit_price) {
                            // Закрытая позиция - считаем от цены выхода
                            const isLong = trade.direction.toLowerCase() === 'long';
                            pnlPercent = isLong
                              ? ((trade.exit_price - trade.entry_price) / trade.entry_price * 100)
                              : ((trade.entry_price - trade.exit_price) / trade.entry_price * 100);
                          }
                        }

                        return (
                          <td className="py-2 font-mono font-bold">
                            {unrealized ? (
                              <div className="flex flex-col">
                                <span className={unrealized.pnl >= 0 ? 'text-green-400' : 'text-red-400'}>
                                  {unrealized.pnl >= 0 ? '+' : ''}{unrealized.pnl.toLocaleString('ru-RU', { maximumFractionDigits: 0 })} ₽
                                </span>
                                <span className={`text-[10px] ${pnlPercent >= 0 ? 'text-green-400/60' : 'text-red-400/60'}`}>
                                  {pnlPercent >= 0 ? '+' : ''}{pnlPercent.toFixed(2)}%
                                </span>
                              </div>
                            ) : pnlValue !== null && pnlValue !== undefined ? (
                              <div className="flex flex-col">
                                <span className={Number(pnlValue) >= 0 ? 'text-green-400' : 'text-red-400'}>
                                  {Number(pnlValue) >= 0 ? '+' : ''}{Number(pnlValue).toLocaleString('ru-RU', { maximumFractionDigits: 0 })} ₽
                                </span>
                                <span className={`text-[10px] ${pnlPercent >= 0 ? 'text-green-400/60' : 'text-red-400/60'}`}>
                                  {pnlPercent >= 0 ? '+' : ''}{pnlPercent.toFixed(2)}%
                                </span>
                              </div>
                            ) : (
                              <span className="text-slate-500">—</span>
                            )}
                          </td>
                        );
                      })()}

                      {/* Статус */}
                      {isColumnVisible('status') && (
                        <td className="py-2">
                          {trade.exit_at ? (
                            <span className="text-[10px] font-mono text-slate-400">
                              {formatHoldingTime(trade.holding_time_minutes)}
                            </span>
                          ) : (
                            <span className="text-[10px] font-bold bg-accent/20 text-accent px-1.5 py-0.5 rounded animate-pulse">
                              OPEN
                            </span>
                          )}
                        </td>
                      )}

                      {/* Теги */}
                      {isColumnVisible('tags') && (
                        <td className="py-2">
                          <div className="flex gap-0.5 flex-wrap">
                            {trade.tags?.slice(0, 2).map(tag => (
                              <span key={tag} className="text-[9px] font-mono border border-accent/30 px-1 rounded text-accent">
                                #{tag}
                              </span>
                            ))}
                            {(trade.tags?.length || 0) > 2 && (
                              <span className="text-[9px] text-slate-500">+{(trade.tags?.length || 0) - 2}</span>
                            )}
                          </div>
                        </td>
                      )}

                      {/* Плечо */}
                      {isColumnVisible('leverage') && (
                        <td className="py-2 font-mono text-xs text-center">
                          {trade.leverage ? `${trade.leverage}x` : '—'}
                        </td>
                      )}

                      {/* Действия */}
                      <td className="py-2 pr-2">
                        <div className="flex justify-end gap-1">
                          {!trade.exit_at && (
                            <button
                              onClick={(e) => { e.stopPropagation(); openCloseModal(trade); }}
                              className="text-yellow-500/50 hover:text-yellow-500 p-1"
                              title="Закрыть"
                            >
                              <Lock size={14} />
                            </button>
                          )}
                          <button
                            onClick={(e) => { e.stopPropagation(); handleEdit(trade); }}
                            className="text-accent/50 hover:text-accent p-1"
                          >
                            <Edit2 size={14} />
                          </button>
                          <button
                            onClick={(e) => { e.stopPropagation(); handleDelete(trade.id); }}
                            className="text-red-500/50 hover:text-red-500 p-1"
                          >
                            <Trash2 size={14} />
                          </button>
                        </div>
                      </td>
                    </tr>

                    {/* Развёрнутые детали */}
                    {isExpanded && (
                      <tr className="bg-slate-800/30 border-b border-border/30">
                        <td colSpan={visibleColumns.size + 2} className="p-4">
                          <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-4 text-xs">
                            {/* Основная информация */}
                            {/* Сетап */}
                            <div>
                              <span className="text-slate-500 block mb-1">Сетап</span>
                              {trade.setup ? (
                                <span className="font-medium flex items-center gap-1" style={{ color: trade.setup.color }}>
                                  {trade.setup.icon} {trade.setup.name}
                                </span>
                              ) : (
                                <span className="font-medium">{trade.setup_name || '-'}</span>
                              )}
                            </div>
                            <div>
                              <span className="text-slate-500 block mb-1">Событие</span>
                              <span className="font-medium">{trade.news_event || '-'}</span>
                            </div>

                            {/* Психо-метрики */}
                            <div>
                              <span className="text-slate-500 block mb-1">Настроение</span>
                              {trade.mood ? (
                                <span className="text-lg">{['😤', '😟', '😐', '😊', '🚀'][trade.mood - 1]}</span>
                              ) : '-'}
                            </div>
                            <div>
                              <span className="text-slate-500 block mb-1">Уверенность</span>
                              {trade.confidence ? (
                                <span className={`px-1.5 py-0.5 rounded font-medium ${
                                  trade.confidence >= 4 ? 'bg-green-500/20 text-green-400' :
                                  trade.confidence >= 3 ? 'bg-yellow-500/20 text-yellow-400' :
                                  'bg-red-500/20 text-red-400'
                                }`}>{trade.confidence}/5</span>
                              ) : '-'}
                            </div>
                            <div>
                              <span className="text-slate-500 block mb-1">Дисциплина</span>
                              {trade.discipline ? (
                                <span className={`px-1.5 py-0.5 rounded font-medium ${
                                  trade.discipline >= 4 ? 'bg-green-500/20 text-green-400' :
                                  trade.discipline >= 3 ? 'bg-yellow-500/20 text-yellow-400' :
                                  'bg-red-500/20 text-red-400'
                                }`}>{['Нарушил', 'Частично', 'Нейтр.', 'Следовал', 'Идеально'][trade.discipline - 1]}</span>
                              ) : '-'}
                            </div>
                            <div>
                              <span className="text-slate-500 block mb-1">Комиссия</span>
                              <span className="font-medium text-red-400">
                                {(trade.commission || 0) > 0 ? `-${Number(trade.commission).toFixed(2)} ₽` : '-'}
                              </span>
                            </div>
                            <div>
                              <span className="text-slate-500 block mb-1">Своп</span>
                              <span className="font-medium text-red-400">
                                {(trade.swap || 0) > 0 ? `-${Number(trade.swap).toFixed(2)} ₽` : '-'}
                              </span>
                            </div>
                            <div>
                              <span className="text-slate-500 block mb-1">Время в сделке</span>
                              <span className="font-medium text-cyan-400">
                                {trade.holding_time_minutes ? formatHoldingTime(trade.holding_time_minutes) : '-'}
                              </span>
                            </div>

                            {/* Вторая строка */}
                            <div>
                              <span className="text-slate-500 block mb-1">SL</span>
                              <span className="font-mono">{trade.stop_loss?.toLocaleString('ru-RU') || '-'}</span>
                            </div>
                            <div>
                              <span className="text-slate-500 block mb-1">TP</span>
                              <span className="font-mono">{trade.take_profit?.toLocaleString('ru-RU') || '-'}</span>
                            </div>
                            <div>
                              <span className="text-slate-500 block mb-1">Риск</span>
                              <span className="font-mono">{trade.risk_amount ? `${trade.risk_amount.toLocaleString('ru-RU')} ₽` : '-'}</span>
                            </div>
                            <div>
                              <span className="text-slate-500 block mb-1">R-Multiple</span>
                              <span className={`font-mono font-bold ${
                                trade.r_multiple && trade.r_multiple >= 1 ? 'text-green-400' :
                                trade.r_multiple && trade.r_multiple < 0 ? 'text-red-400' : ''
                              }`}>
                                {trade.r_multiple ? `${trade.r_multiple.toFixed(2)}R` : '-'}
                              </span>
                            </div>
                            <div>
                              <span className="text-slate-500 block mb-1">Причина выхода</span>
                              <span className="font-medium">{trade.exit_reason || '-'}</span>
                            </div>
                            <div>
                              <span className="text-slate-500 block mb-1">Плечо</span>
                              <span className="font-mono">{trade.leverage ? `${trade.leverage}x` : '-'}</span>
                            </div>

                            {/* MAE/MFE Анализ */}
                            {trade.exit_at && (trade.mae_price || trade.mfe_price) && (
                              <div className="col-span-full border border-accent/20 rounded-lg p-3 bg-accent/5">
                                <div className="flex items-center gap-2 mb-3">
                                  <span className="text-accent font-bold text-sm">📊 MAE/MFE Анализ</span>
                                  {!trade.mae_price && !trade.mfe_price && (
                                    <span className="text-slate-500 text-[10px]">(нет данных)</span>
                                  )}
                                </div>

                                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                                  {/* MAE */}
                                  <div>
                                    <span className="text-slate-500 block mb-1 text-[10px]">MAE (худшая цена)</span>
                                    <span className="font-mono text-red-400">
                                      {trade.mae_price ? trade.mae_price.toLocaleString('ru-RU', { maximumFractionDigits: 2 }) : '—'}
                                    </span>
                                    {trade.mae_price && trade.entry_price && (
                                      <span className="text-red-400/70 text-[10px] ml-1">
                                        ({trade.direction === 'long'
                                          ? `-${(((trade.entry_price - trade.mae_price) / trade.entry_price) * 100).toFixed(2)}%`
                                          : `-${(((trade.mae_price - trade.entry_price) / trade.entry_price) * 100).toFixed(2)}%`
                                        })
                                      </span>
                                    )}
                                  </div>

                                  {/* MFE */}
                                  <div>
                                    <span className="text-slate-500 block mb-1 text-[10px]">MFE (лучшая цена)</span>
                                    <span className="font-mono text-green-400">
                                      {trade.mfe_price ? trade.mfe_price.toLocaleString('ru-RU', { maximumFractionDigits: 2 }) : '—'}
                                    </span>
                                    {trade.mfe_price && trade.entry_price && (
                                      <span className="text-green-400/70 text-[10px] ml-1">
                                        (+{trade.direction === 'long'
                                          ? (((trade.mfe_price - trade.entry_price) / trade.entry_price) * 100).toFixed(2)
                                          : (((trade.entry_price - trade.mfe_price) / trade.entry_price) * 100).toFixed(2)
                                        }%)
                                      </span>
                                    )}
                                  </div>

                                  {/* Edge Ratio */}
                                  {trade.mae_price && trade.mfe_price && trade.entry_price && (
                                    <div>
                                      <span className="text-slate-500 block mb-1 text-[10px]">Edge Ratio (MFE/MAE)</span>
                                      {(() => {
                                        const maeMove = trade.direction === 'long'
                                          ? trade.entry_price - trade.mae_price
                                          : trade.mae_price - trade.entry_price;
                                        const mfeMove = trade.direction === 'long'
                                          ? trade.mfe_price - trade.entry_price
                                          : trade.entry_price - trade.mfe_price;
                                        const edgeRatio = maeMove > 0 ? mfeMove / maeMove : 0;
                                        return (
                                          <span className={`font-mono font-bold ${edgeRatio >= 2 ? 'text-green-400' : edgeRatio >= 1 ? 'text-yellow-400' : 'text-red-400'}`}>
                                            {edgeRatio.toFixed(2)}
                                          </span>
                                        );
                                      })()}
                                      <span className="text-slate-500 text-[10px] ml-1">
                                        ({'>'}2 = отлично)
                                      </span>
                                    </div>
                                  )}

                                  {/* Capture Ratio */}
                                  {trade.mfe_price && trade.entry_price && trade.exit_price && (
                                    <div>
                                      <span className="text-slate-500 block mb-1 text-[10px]">Capture (захват MFE)</span>
                                      {(() => {
                                        const maxProfit = trade.direction === 'long'
                                          ? (trade.mfe_price - trade.entry_price) * trade.quantity
                                          : (trade.entry_price - trade.mfe_price) * trade.quantity;
                                        const actualProfit = trade.pnl || 0;
                                        const captureRatio = maxProfit > 0 ? (actualProfit / maxProfit) * 100 : 0;
                                        return (
                                          <span className={`font-mono font-bold ${captureRatio >= 70 ? 'text-green-400' : captureRatio >= 40 ? 'text-yellow-400' : 'text-red-400'}`}>
                                            {captureRatio.toFixed(0)}%
                                          </span>
                                        );
                                      })()}
                                      <span className="text-slate-500 text-[10px] ml-1">
                                        (сколько взяли от макс.)
                                      </span>
                                    </div>
                                  )}
                                </div>

                                {/* Visual representation */}
                                {trade.mae_price && trade.mfe_price && trade.entry_price && trade.exit_price && (
                                  <div className="mt-3 pt-3 border-t border-slate-700/50">
                                    <div className="flex items-center gap-2 text-[10px]">
                                      <span className="text-red-400">MAE {trade.mae_price.toLocaleString('ru-RU')}</span>
                                      <div className="flex-1 h-2 bg-slate-700 rounded-full relative overflow-hidden">
                                        {(() => {
                                          const min = Math.min(trade.mae_price, trade.entry_price, trade.exit_price);
                                          const max = Math.max(trade.mfe_price, trade.entry_price, trade.exit_price);
                                          const range = max - min;
                                          const entryPos = ((trade.entry_price - min) / range) * 100;
                                          const exitPos = ((trade.exit_price - min) / range) * 100;
                                          const maePos = ((trade.mae_price - min) / range) * 100;
                                          const mfePos = ((trade.mfe_price - min) / range) * 100;

                                          return (
                                            <>
                                              {/* MAE to MFE range */}
                                              <div
                                                className="absolute h-full bg-gradient-to-r from-red-500/30 via-slate-600 to-green-500/30"
                                                style={{ left: `${maePos}%`, width: `${mfePos - maePos}%` }}
                                              />
                                              {/* Entry marker */}
                                              <div
                                                className="absolute w-1 h-full bg-white"
                                                style={{ left: `${entryPos}%` }}
                                                title={`Вход: ${trade.entry_price}`}
                                              />
                                              {/* Exit marker */}
                                              <div
                                                className="absolute w-1 h-full bg-accent"
                                                style={{ left: `${exitPos}%` }}
                                                title={`Выход: ${trade.exit_price}`}
                                              />
                                            </>
                                          );
                                        })()}
                                      </div>
                                      <span className="text-green-400">MFE {trade.mfe_price.toLocaleString('ru-RU')}</span>
                                    </div>
                                    <div className="flex justify-between text-[9px] text-slate-500 mt-1">
                                      <span>⬜ Вход: {trade.entry_price.toLocaleString('ru-RU')}</span>
                                      <span>🟩 Выход: {trade.exit_price.toLocaleString('ru-RU')}</span>
                                    </div>
                                  </div>
                                )}
                              </div>
                            )}

                            {/* Нет данных MAE/MFE - показываем кнопку расчёта */}
                            {trade.exit_at && !trade.mae_price && !trade.mfe_price && (
                              <div className="col-span-full border border-slate-700 rounded-lg p-3 bg-slate-800/30">
                                <div className="flex items-center justify-between">
                                  <div>
                                    <span className="text-slate-400 text-sm">📊 MAE/MFE Анализ</span>
                                    <p className="text-slate-500 text-[10px] mt-1">Нет данных о ценовом диапазоне во время сделки</p>
                                  </div>
                                  <button
                                    onClick={(e) => {
                                      e.stopPropagation();
                                      calculateMAEMFE([trade.id]);
                                    }}
                                    disabled={isCalculatingMAE}
                                    className="flex items-center gap-1 px-3 py-1.5 bg-accent/20 hover:bg-accent/30 text-accent rounded text-xs transition-colors disabled:opacity-50"
                                  >
                                    {isCalculatingMAE ? (
                                      <Loader2 size={12} className="animate-spin" />
                                    ) : (
                                      <BarChart2 size={12} />
                                    )}
                                    Рассчитать
                                  </button>
                                </div>
                              </div>
                            )}

                            {/* Теги на всю ширину */}
                            {trade.tags && trade.tags.length > 0 && (
                              <div className="col-span-full">
                                <span className="text-slate-500 block mb-1">Теги</span>
                                <div className="flex gap-1 flex-wrap">
                                  {trade.tags.map(tag => (
                                    <span key={tag} className="text-[10px] font-mono border border-accent/30 px-2 py-0.5 rounded text-accent">
                                      #{tag}
                                    </span>
                                  ))}
                                </div>
                              </div>
                            )}

                            {/* Логика входа */}
                            {trade.entry_reason && (
                              <div className="col-span-full">
                                <span className="text-slate-500 block mb-1">Логика входа</span>
                                <span className="font-medium">{trade.entry_reason}</span>
                              </div>
                            )}

                            {/* Скриншот */}
                            {trade.screenshot_url && (
                              <div className="col-span-full">
                                <span className="text-slate-500 block mb-1">📷 Скриншот графика</span>
                                <a
                                  href={getApiUrl(trade.screenshot_url)}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  className="block"
                                >
                                  <Image
                                    src={getApiUrl(trade.screenshot_url)}
                                    alt="Скриншот сделки"
                                    width={640}
                                    height={160}
                                    unoptimized
                                    className="max-w-md h-40 object-cover rounded-lg border border-border hover:border-accent transition-colors cursor-pointer"
                                  />
                                </a>
                              </div>
                            )}

                            {/* Заметки */}
                            {trade.notes && (
                              <div className="col-span-full">
                                <span className="text-slate-500 block mb-1">📝 Заметки</span>
                                <p className="text-slate-300 whitespace-pre-wrap bg-slate-800/50 p-2 rounded-lg">{trade.notes}</p>
                              </div>
                            )}

                            {/* Операции */}
                            {trade.operations && trade.operations.length > 0 && (
                              <div className="col-span-full">
                                <span className="text-slate-500 block mb-2">Операции ({trade.operations.length})</span>
                                <div className="overflow-x-auto">
                                  <table className="w-full text-[10px]">
                                    <thead>
                                      <tr className="text-slate-500">
                                        <th className="text-left py-1">Дата</th>
                                        <th className="text-left py-1">Тип</th>
                                        <th className="text-right py-1">Цена</th>
                                        <th className="text-right py-1">Кол-во</th>
                                        <th className="text-right py-1">Комиссия</th>
                                      </tr>
                                    </thead>
                                    <tbody>
                                      {trade.operations.map((op, idx) => (
                                        <tr key={idx} className="border-t border-slate-700/50">
                                          <td className="py-1 font-mono">{op.date} {op.time}</td>
                                          <td className="py-1">
                                            <span className={`px-1 rounded ${op.type === 'entry' ? 'bg-blue-500/20 text-blue-400' : 'bg-orange-500/20 text-orange-400'}`}>
                                              {op.type === 'entry' ? 'ВХОД' : (op.note === 'partial_close' ? 'ЧАСТИЧ. ВЫХОД' : 'ВЫХОД')}
                                            </span>
                                          </td>
                                          <td className="py-1 text-right font-mono">{op.price?.toLocaleString('ru-RU')}</td>
                                          <td className="py-1 text-right font-mono">{op.qty?.toLocaleString('ru-RU')}</td>
                                          <td className="py-1 text-right font-mono text-red-400">
                                            {op.commission ? `-${op.commission.toFixed(2)}` : '-'}
                                          </td>
                        </tr>
                                      ))}
                                    </tbody>
                                  </table>
                                </div>
                              </div>
                            )}
                          </div>
                        </td>
                          </tr>
                        )}
                  </React.Fragment>
                );
              })}
            </tbody>
          </table>
          </div>
        </div>
      </div>
    </div>
    </AppShell>
  );
}
