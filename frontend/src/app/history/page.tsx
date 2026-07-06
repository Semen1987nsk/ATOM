'use client';

import { useEffect, useState, useRef, useCallback } from 'react';
import { Trash2, Upload, Plus, X, BarChart2, Loader2 } from 'lucide-react';
import { AddTradeModal } from '@/components/AddTradeModal';
import { EditTradeModal } from '@/components/EditTradeModal';
import CloseTradeModal from '@/components/CloseTradeModal';
import { ImportPreviewModal } from '@/components/ImportPreviewModal';
import { AppShell } from '@/components/AppShell';
import { TradeHistorySkeleton } from '@/components/Skeleton';
import { PositionJournalView } from '@/components/PositionJournalView';
import { useSettings } from '@/contexts/SettingsContext';
import { useToast } from '@/contexts/ToastContext';
import { api, ApiError } from '@/lib/apiClient';
import {
  Trade,
  JournalViewMode,
  SortMode,
  DirectionFilter,
  ALL_COLUMNS,
  DIARY_PROMOTED_COLUMNS,
  VIEW_MODE_STORAGE_KEY,
  STORAGE_KEY,
  SORT_STORAGE_KEY,
  getTradeSortTimestamp,
} from './_components/types';
import { DeleteAllModal } from './_components/DeleteAllModal';
import { ColumnSettings } from './_components/ColumnSettings';
import { HistoryFilters } from './_components/HistoryFilters';
import { TradesTable } from './_components/TradesTable';

export default function HistoryPage() {
  const { settings, updateSettings } = useSettings();
  const toast = useToast();
  const [trades, setTrades] = useState<Trade[]>([]);
  // API-02: полное число сделок на счёте из X-Total-Count — бэкенд режет
  // выдачу limit'ом (500 по умолчанию), и без заголовка усечение невидимо.
  const [totalCount, setTotalCount] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedTag, setSelectedTag] = useState<string | null>(null);
  const [filterDirection, setFilterDirection] = useState<DirectionFilter>('ALL');
  // PR 19: фильтр по типу актива (share/futures/option/bond/etf/currency).
  const [filterAssetType, setFilterAssetType] = useState<string>('ALL');
  const [tempStartDate, setTempStartDate] = useState<string>(settings.tradesStartDate || '');
  const [tempStartTradeId, setTempStartTradeId] = useState<number | null>(settings.tradesStartTradeId || null);
  const [showDatePicker, setShowDatePicker] = useState(false);
  const [tradesForSelectedDate, setTradesForSelectedDate] = useState<Trade[]>([]);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [isEditModalOpen, setIsEditModalOpen] = useState(false);
  const [isCloseModalOpen, setIsCloseModalOpen] = useState(false);
  const [selectedTrade, setSelectedTrade] = useState<Trade | null>(null);
  const [selectedTradeToClose, setSelectedTradeToClose] = useState<Trade | null>(null);
  const [unrealizedData] = useState<Record<number, { pnl: number; price: number }>>({});
  const [isImportModalOpen, setIsImportModalOpen] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [expandedTrades, setExpandedTrades] = useState<Set<number>>(new Set());
  const [isCalculatingMAE, setIsCalculatingMAE] = useState(false);
  const [maeCalculationResult, setMaeCalculationResult] = useState<{updated: number, failed: number} | null>(null);
  const [showColumnSettings, setShowColumnSettings] = useState(false);
  // TR1: round-trip grouped view (default) vs legacy flat per-execution view.
  const [viewMode, setViewMode] = useState<JournalViewMode>(() => {
    if (typeof window !== 'undefined') {
      const saved = localStorage.getItem(VIEW_MODE_STORAGE_KEY);
      if (saved === 'grouped' || saved === 'flat') return saved;
    }
    return 'grouped';
  });
  useEffect(() => {
    if (typeof window !== 'undefined') {
      localStorage.setItem(VIEW_MODE_STORAGE_KEY, viewMode);
    }
  }, [viewMode]);
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
          const savedColumns = new Set<string>(Array.isArray(parsed) ? parsed : []);

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
    setLoading(true);
    setError(null);
    try {
      const res = await api.get<Response>('/trades/', { rawResponse: true });
      const data = (await res.json()) as Trade[];
      setTrades(data);
      const total = Number(res.headers.get('X-Total-Count'));
      setTotalCount(Number.isFinite(total) && total > 0 ? total : null);
    } catch (err) {
      console.error('Failed to fetch trades:', err);
      setError(err instanceof ApiError ? err.toUserMessage() : 'Не удалось загрузить сделки');
    } finally {
      setLoading(false);
    }
  };

  // /trades/unrealized-pnl endpoint удалён вместе с Phase 6.5 (Position table
  // теперь единственная правда для unrealized). Колонка "unrealized" для open
  // trades в журнале остаётся пустой до full переработки на чтение из Position
  // table напрямую. См. spec 2026-05-19-position-source-of-truth-design.md.

  useEffect(() => {
    fetchTrades();
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
      toast.error(error instanceof ApiError ? error.toUserMessage() : 'Не удалось закрыть сделку');
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
    const isAddition = trades.some(other =>
      other.id !== trade.id &&
      other.symbol === trade.symbol &&
      other.direction === trade.direction &&
      new Date(other.entry_at).getTime() < new Date(trade.entry_at).getTime() &&
      (other.exit_at ? new Date(other.exit_at).getTime() > new Date(trade.entry_at).getTime() : true)
    );

    return { ...trade, isAddition };
  });

  const filteredTrades = enrichedTrades.filter(t => {
    const matchesTag = selectedTag ? t.tags?.includes(selectedTag) : true;
    const matchesDirection = filterDirection === 'ALL' ? true : t.direction.toUpperCase() === filterDirection;
    // PR 19: фильтр по типу актива.
    const tType = (t.instrument_type_v2 || t.asset_type || '').toLowerCase();
    const matchesAssetType = filterAssetType === 'ALL' ? true : tType === filterAssetType;

    // Фильтр по дате/сделке начала из настроек
    let matchesStart = true;
    if (settings.tradesStartTradeId) {
      const startTrade = trades.find(tr => tr.id === settings.tradesStartTradeId);
      if (startTrade) {
        matchesStart = new Date(t.entry_at) >= new Date(startTrade.entry_at);
      }
    } else if (settings.tradesStartDate) {
      matchesStart = new Date(t.entry_at) >= new Date(settings.tradesStartDate);
    }

    return matchesTag && matchesDirection && matchesAssetType && matchesStart;
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

  // Завис/недоступен бэкенд → явная ошибка + повтор, а не вечный скелетон.
  if (error) {
    return (
      <div className="min-h-screen flex items-center justify-center p-6">
        <div className="cyber-card max-w-md w-full p-8 text-center">
          <div className="w-12 h-12 mx-auto mb-4 rounded-full bg-red-500/20 flex items-center justify-center">
            <X className="w-6 h-6 text-red-500" />
          </div>
          <h2 className="text-xl font-bold mb-2">Не удалось загрузить сделки</h2>
          <p className="text-sm text-[var(--text-secondary)] mb-6">{error}</p>
          <button
            onClick={() => fetchTrades()}
            className="btn-primary inline-flex items-center gap-2"
          >
            <Loader2 size={16} />
            Повторить
          </button>
        </div>
      </div>
    );
  }

  // Page-specific actions для AppShell.headerRight (column settings, theme, etc).
  // Column-settings popup стартует из той же кнопки, но теперь живёт в шапке страницы.
  return (
    <AppShell
      pageTitle="Дневник сделок"
      onAddTrade={() => setIsModalOpen(true)}
      onImport={() => setIsImportModalOpen(true)}
    >
      <div className="p-6 md:p-8 max-w-7xl mx-auto">
        <div className="mb-6 flex justify-between items-center flex-wrap gap-4">
          <div>
            <h1 className="text-3xl font-bold tracking-tight">Дневник сделок</h1>
            <p className="text-sm text-[var(--text-secondary)] mt-1">
              {viewMode === 'grouped'
                ? 'Сделки сгруппированы по round-trip: scaled-in добавления собраны вместе.'
                : 'Каждая операция отдельной строкой (классический режим).'}
            </p>
          </div>
          <div className="flex gap-2 items-center">
            {/* TR1: view-mode toggle — grouped (default) vs flat (legacy) */}
            <div className="flex items-center gap-1 bg-slate-800/40 rounded-lg p-1">
              <button
                onClick={() => setViewMode('grouped')}
                className={`px-3 py-1.5 rounded text-xs font-medium transition-colors ${
                  viewMode === 'grouped'
                    ? 'bg-slate-700 text-slate-100'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
                title="Round-trip — сделки группируются по lifecycle"
              >
                По сделкам
              </button>
              <button
                onClick={() => setViewMode('flat')}
                className={`px-3 py-1.5 rounded text-xs font-medium transition-colors ${
                  viewMode === 'flat'
                    ? 'bg-slate-700 text-slate-100'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
                title="Классический режим — каждая операция отдельной строкой"
              >
                По операциям
              </button>
            </div>
            <ColumnSettings
              isOpen={showColumnSettings}
              onToggle={() => setShowColumnSettings(!showColumnSettings)}
              onClose={() => setShowColumnSettings(false)}
              visibleColumns={visibleColumns}
              toggleColumn={toggleColumn}
              resetColumns={resetColumns}
            />
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

        <DeleteAllModal
          isOpen={showDeleteConfirm}
          onClose={() => setShowDeleteConfirm(false)}
          onConfirm={handleDeleteAllTrades}
          tradeCount={trades.length}
          isDeleting={isDeleting}
        />

        {/* API-02: бэкенд отдаёт максимум limit строк — предупреждаем об усечении */}
        {totalCount !== null && totalCount > trades.length && (
          <div className="mb-4 px-4 py-2.5 text-sm text-[var(--text-secondary)] bg-[var(--surface-2)] border border-[var(--border)] rounded-[var(--radius-lg)]">
            Показаны {trades.length} из {totalCount} сделок — уточните фильтры или период.
          </div>
        )}

        {/* TR1: grouped view (default) — round-trip aggregation */}
        {viewMode === 'grouped' && (
          <div className="cyber-card p-6">
            <PositionJournalView />
          </div>
        )}

        {/* Classic flat view (legacy) — каждая операция отдельной строкой */}
        {viewMode === 'flat' && (
          <div className="cyber-card p-6">
            <HistoryFilters
              filterDirection={filterDirection}
              setFilterDirection={setFilterDirection}
              filterAssetType={filterAssetType}
              setFilterAssetType={setFilterAssetType}
              showDatePicker={showDatePicker}
              setShowDatePicker={setShowDatePicker}
              settings={settings}
              updateSettings={updateSettings}
              trades={trades}
              tempStartDate={tempStartDate}
              setTempStartDate={setTempStartDate}
              tempStartTradeId={tempStartTradeId}
              setTempStartTradeId={setTempStartTradeId}
              tradesForSelectedDate={tradesForSelectedDate}
              setTradesForSelectedDate={setTradesForSelectedDate}
              sortMode={sortMode}
              setSortMode={setSortMode}
              allTags={allTags}
              selectedTag={selectedTag}
              setSelectedTag={setSelectedTag}
              canScrollLeft={canScrollLeft}
              canScrollRight={canScrollRight}
              scrollTable={scrollTable}
            />

            <TradesTable
              scrollContainerRef={scrollContainerRef}
              sortedTrades={sortedTrades}
              isColumnVisible={isColumnVisible}
              visibleColumnsSize={visibleColumns.size}
              expandedTrades={expandedTrades}
              unrealizedData={unrealizedData}
              isCalculatingMAE={isCalculatingMAE}
              canScrollLeft={canScrollLeft}
              canScrollRight={canScrollRight}
              onToggleExpand={toggleTrade}
              onEdit={handleEdit}
              onDelete={handleDelete}
              onOpenClose={openCloseModal}
              onCalculateMAE={calculateMAEMFE}
              onMobileEdit={(id) => {
                const t = sortedTrades.find((tr) => tr.id === id);
                if (t) {
                  setSelectedTrade(t);
                  setIsEditModalOpen(true);
                }
              }}
            />
          </div>
        )}
      </div>
    </AppShell>
  );
}
