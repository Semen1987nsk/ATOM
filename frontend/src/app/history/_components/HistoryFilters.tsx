'use client';

import { Dispatch, SetStateAction } from 'react';
import { Calendar, X, Check, ChevronLeft, ChevronRight } from 'lucide-react';
import type { Settings } from '@/contexts/SettingsContext';
import type { Trade, DirectionFilter, SortMode } from './types';
import { SORT_STORAGE_KEY } from './types';

interface HistoryFiltersProps {
  filterDirection: DirectionFilter;
  setFilterDirection: Dispatch<SetStateAction<DirectionFilter>>;
  filterAssetType: string;
  setFilterAssetType: Dispatch<SetStateAction<string>>;
  showDatePicker: boolean;
  setShowDatePicker: Dispatch<SetStateAction<boolean>>;
  settings: Settings;
  updateSettings: (patch: Partial<Settings>) => void;
  trades: Trade[];
  tempStartDate: string;
  setTempStartDate: Dispatch<SetStateAction<string>>;
  tempStartTradeId: number | null;
  setTempStartTradeId: Dispatch<SetStateAction<number | null>>;
  tradesForSelectedDate: Trade[];
  setTradesForSelectedDate: Dispatch<SetStateAction<Trade[]>>;
  sortMode: SortMode;
  setSortMode: Dispatch<SetStateAction<SortMode>>;
  allTags: string[];
  selectedTag: string | null;
  setSelectedTag: Dispatch<SetStateAction<string | null>>;
  canScrollLeft: boolean;
  canScrollRight: boolean;
  scrollTable: (direction: 'left' | 'right') => void;
}

export function HistoryFilters({
  filterDirection,
  setFilterDirection,
  filterAssetType,
  setFilterAssetType,
  showDatePicker,
  setShowDatePicker,
  settings,
  updateSettings,
  trades,
  tempStartDate,
  setTempStartDate,
  tempStartTradeId,
  setTempStartTradeId,
  tradesForSelectedDate,
  setTradesForSelectedDate,
  sortMode,
  setSortMode,
  allTags,
  selectedTag,
  setSelectedTag,
  canScrollLeft,
  canScrollRight,
  scrollTable,
}: HistoryFiltersProps) {
  return (
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

      {/* PR 19: Asset type filter — Все / Акции / Фьючерсы / Опционы / Облигации / ETF / Валюта */}
      <div className="hidden md:flex items-center">
        <select
          value={filterAssetType}
          onChange={(e) => setFilterAssetType(e.target.value)}
          className="bg-surface border border-border rounded-lg px-3 py-1.5 text-xs font-mono uppercase text-slate-300 hover:bg-white/5 transition-colors"
          title="Фильтр по типу актива"
        >
          <option value="ALL">Все типы</option>
          <option value="share">Акции</option>
          <option value="futures">Фьючерсы</option>
          <option value="option">Опционы</option>
          <option value="bond">Облигации</option>
          <option value="etf">ETF</option>
          <option value="currency">Валюта</option>
        </select>
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
            if (typeof window !== 'undefined') {
              localStorage.setItem(SORT_STORAGE_KEY, nextSortMode);
            }
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
  );
}
