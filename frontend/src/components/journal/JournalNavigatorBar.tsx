'use client';

/**
 * Phase 13 (2026-05-17): Journal Navigator Bar.
 *
 * Sticky filter bar под status-табами в журнале сделок:
 *   [🔍 Поиск] [Все|LONG|SHORT] [Date pills] [Setup ▼] [Sort ▼] [×Reset]   Counter
 *
 * Best practices: Tradervue (sticky filters), TraderSync (date pills),
 * Edgewonk (multi-filter), TradeZella (advanced filter modal).
 */
import { useEffect, useRef, useState } from 'react';
import {
  Search,
  X,
  Calendar,
  ChevronDown,
  ArrowUpDown,
} from 'lucide-react';
import {
  JournalFilters,
  DateRange,
  DirectionFilter,
  SORT_OPTIONS,
  DATE_RANGE_OPTIONS,
} from './types';
import { isAnyFilterActive } from './filterUtils';

interface JournalNavigatorBarProps {
  filters: JournalFilters;
  onUpdate: (patch: Partial<JournalFilters>) => void;
  onReset: () => void;
  filteredCount: number;
  totalCount: number;
  availableSetups: { id: number; name: string }[];
}

const PILL_BASE =
  'px-2.5 py-1 text-[11px] font-medium rounded-md border transition-colors whitespace-nowrap';
const PILL_INACTIVE =
  'border-slate-700 bg-slate-800/40 text-slate-400 hover:text-slate-200 hover:border-slate-600';
const PILL_ACTIVE = 'border-accent bg-accent/10 text-accent';

export function JournalNavigatorBar({
  filters,
  onUpdate,
  onReset,
  filteredCount,
  totalCount,
  availableSetups,
}: JournalNavigatorBarProps) {
  // Controlled search input — directly bound to filters.search.
  // Для 10k+ сделок future Phase 14 добавит useDeferredValue в parent.
  const [showCustomDate, setShowCustomDate] = useState(false);
  const [showSetupDropdown, setShowSetupDropdown] = useState(false);
  const [showSortDropdown, setShowSortDropdown] = useState(false);
  const setupDropdownRef = useRef<HTMLDivElement>(null);
  const sortDropdownRef = useRef<HTMLDivElement>(null);

  // Click-outside для dropdowns
  useEffect(() => {
    if (!showSetupDropdown && !showSortDropdown) return;
    const handler = (e: MouseEvent) => {
      const target = e.target as Node;
      if (
        showSetupDropdown &&
        setupDropdownRef.current &&
        !setupDropdownRef.current.contains(target)
      ) {
        setShowSetupDropdown(false);
      }
      if (
        showSortDropdown &&
        sortDropdownRef.current &&
        !sortDropdownRef.current.contains(target)
      ) {
        setShowSortDropdown(false);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [showSetupDropdown, showSortDropdown]);

  const filterActive = isAnyFilterActive(filters);
  const isFiltered = filteredCount !== totalCount;

  const directionPills: { key: DirectionFilter; label: string }[] = [
    { key: 'all', label: 'Все' },
    { key: 'long', label: 'LONG' },
    { key: 'short', label: 'SHORT' },
  ];

  const currentSetupLabel =
    filters.setupId === 'all'
      ? 'Все сетапы'
      : filters.setupId === 'none'
      ? 'Без сетапа'
      : availableSetups.find((s) => s.id === filters.setupId)?.name ?? 'Сетап';

  const currentSortLabel =
    SORT_OPTIONS.find((s) => s.key === filters.sort)?.label ?? 'Дата ↓';

  const handleDateRangeClick = (key: DateRange) => {
    if (key === 'custom') {
      setShowCustomDate(true);
      return;
    }
    onUpdate({ dateRange: key, customDateFrom: null, customDateTo: null });
  };

  const customDateActive =
    filters.dateRange === 'custom' &&
    (filters.customDateFrom || filters.customDateTo);

  return (
    <div className="flex items-center flex-wrap gap-2 bg-slate-900/40 border border-slate-800 rounded-lg px-3 py-2">
      {/* Search */}
      <div className="relative flex-1 min-w-[200px] max-w-[320px]">
        <Search
          size={14}
          className="absolute left-2 top-1/2 -translate-y-1/2 text-slate-500 pointer-events-none"
        />
        <input
          type="text"
          value={filters.search}
          onChange={(e) => onUpdate({ search: e.target.value })}
          placeholder="Тикер, сетап, заметка…"
          className="w-full bg-slate-800/40 border border-slate-700 rounded-md pl-7 pr-7 py-1 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-accent"
        />
        {filters.search && (
          <button
            type="button"
            onClick={() => onUpdate({ search: '' })}
            className="absolute right-2 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-200"
            aria-label="Очистить поиск"
          >
            <X size={12} />
          </button>
        )}
      </div>

      {/* Direction pills */}
      <div className="flex items-center gap-1">
        {directionPills.map((d) => (
          <button
            key={d.key}
            type="button"
            onClick={() => onUpdate({ direction: d.key })}
            className={`${PILL_BASE} ${
              filters.direction === d.key ? PILL_ACTIVE : PILL_INACTIVE
            }`}
          >
            {d.label}
          </button>
        ))}
      </div>

      {/* Date range pills */}
      <div className="flex items-center gap-1">
        {DATE_RANGE_OPTIONS.map((d) => {
          const isActive =
            filters.dateRange === d.key ||
            (d.key === 'custom' && customDateActive);
          return (
            <button
              key={d.key}
              type="button"
              onClick={() => handleDateRangeClick(d.key)}
              className={`${PILL_BASE} ${isActive ? PILL_ACTIVE : PILL_INACTIVE}`}
            >
              {d.key === 'custom' && <Calendar size={11} className="inline mr-1" />}
              {d.label}
            </button>
          );
        })}
      </div>

      {/* Setup dropdown */}
      <div className="relative" ref={setupDropdownRef}>
        <button
          type="button"
          onClick={() => setShowSetupDropdown((v) => !v)}
          className={`${PILL_BASE} ${
            filters.setupId !== 'all' ? PILL_ACTIVE : PILL_INACTIVE
          } flex items-center gap-1`}
        >
          <span className="max-w-[120px] truncate">{currentSetupLabel}</span>
          <ChevronDown size={11} />
        </button>
        {showSetupDropdown && (
          <div className="absolute top-full left-0 mt-1 z-30 min-w-[180px] max-h-[280px] overflow-y-auto bg-[var(--surface-1)] border border-slate-700 rounded-md shadow-xl py-1">
            <button
              type="button"
              onClick={() => {
                onUpdate({ setupId: 'all' });
                setShowSetupDropdown(false);
              }}
              className={`w-full text-left px-3 py-1.5 text-xs hover:bg-slate-800 ${
                filters.setupId === 'all' ? 'text-accent' : 'text-slate-300'
              }`}
            >
              Все сетапы
            </button>
            <button
              type="button"
              onClick={() => {
                onUpdate({ setupId: 'none' });
                setShowSetupDropdown(false);
              }}
              className={`w-full text-left px-3 py-1.5 text-xs hover:bg-slate-800 ${
                filters.setupId === 'none' ? 'text-accent' : 'text-slate-300'
              }`}
            >
              Без сетапа
            </button>
            {availableSetups.length > 0 && (
              <div className="border-t border-slate-800 my-1" />
            )}
            {availableSetups.map((s) => (
              <button
                key={s.id}
                type="button"
                onClick={() => {
                  onUpdate({ setupId: s.id });
                  setShowSetupDropdown(false);
                }}
                className={`w-full text-left px-3 py-1.5 text-xs hover:bg-slate-800 ${
                  filters.setupId === s.id ? 'text-accent' : 'text-slate-300'
                }`}
              >
                {s.name}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Sort dropdown */}
      <div className="relative" ref={sortDropdownRef}>
        <button
          type="button"
          onClick={() => setShowSortDropdown((v) => !v)}
          className={`${PILL_BASE} ${
            filters.sort !== 'date_desc' ? PILL_ACTIVE : PILL_INACTIVE
          } flex items-center gap-1`}
        >
          <ArrowUpDown size={11} />
          <span>{currentSortLabel}</span>
          <ChevronDown size={11} />
        </button>
        {showSortDropdown && (
          <div className="absolute top-full left-0 mt-1 z-30 min-w-[180px] bg-[var(--surface-1)] border border-slate-700 rounded-md shadow-xl py-1">
            {SORT_OPTIONS.map((s) => (
              <button
                key={s.key}
                type="button"
                onClick={() => {
                  onUpdate({ sort: s.key });
                  setShowSortDropdown(false);
                }}
                className={`w-full text-left px-3 py-1.5 text-xs hover:bg-slate-800 ${
                  filters.sort === s.key ? 'text-accent' : 'text-slate-300'
                }`}
              >
                {s.label}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Reset */}
      {filterActive && (
        <button
          type="button"
          onClick={onReset}
          className={`${PILL_BASE} ${PILL_INACTIVE} flex items-center gap-1 text-amber-400 hover:text-amber-300`}
          title="Сбросить все фильтры"
        >
          <X size={11} />
          <span>Сбросить</span>
        </button>
      )}

      {/* Counter */}
      <div className="ml-auto text-[11px] text-slate-500 whitespace-nowrap">
        {isFiltered ? (
          <span>
            Показано <span className="text-slate-200 font-semibold">{filteredCount}</span> из{' '}
            {totalCount}
          </span>
        ) : (
          <span>{totalCount} сделок</span>
        )}
      </div>

      {/* Custom date modal */}
      {showCustomDate && (
        <div
          className="fixed inset-0 bg-black/80 backdrop-blur-sm flex items-center justify-center z-50"
          onClick={() => setShowCustomDate(false)}
        >
          <div
            className="cyber-card w-full max-w-sm bg-[var(--surface-1)] p-6 relative"
            onClick={(e) => e.stopPropagation()}
          >
            <button
              type="button"
              onClick={() => setShowCustomDate(false)}
              className="absolute top-4 right-4 opacity-50 hover:opacity-100"
              aria-label="Закрыть"
            >
              <X size={20} />
            </button>
            <h3 className="text-lg font-bold mb-4 flex items-center gap-2">
              <Calendar size={18} className="text-accent" />
              Свой период
            </h3>
            <div className="space-y-4">
              <div>
                <label className="block text-[10px] font-mono uppercase opacity-50 mb-1">
                  Начало периода
                </label>
                <input
                  type="date"
                  value={filters.customDateFrom ?? ''}
                  onChange={(e) =>
                    onUpdate({
                      dateRange: 'custom',
                      customDateFrom: e.target.value || null,
                    })
                  }
                  className="w-full bg-slate-800/40 border border-slate-700 rounded-md px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-accent"
                />
              </div>
              <div>
                <label className="block text-[10px] font-mono uppercase opacity-50 mb-1">
                  Конец периода (опционально)
                </label>
                <input
                  type="date"
                  value={filters.customDateTo ?? ''}
                  onChange={(e) =>
                    onUpdate({
                      dateRange: 'custom',
                      customDateTo: e.target.value || null,
                    })
                  }
                  className="w-full bg-slate-800/40 border border-slate-700 rounded-md px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-accent"
                />
              </div>
              <div className="flex gap-3 pt-2">
                <button
                  type="button"
                  onClick={() => {
                    onUpdate({
                      dateRange: 'all',
                      customDateFrom: null,
                      customDateTo: null,
                    });
                    setShowCustomDate(false);
                  }}
                  className="flex-1 border border-slate-700 py-2 text-xs font-bold uppercase hover:bg-slate-800 transition-colors text-slate-300"
                >
                  Очистить
                </button>
                <button
                  type="button"
                  onClick={() => setShowCustomDate(false)}
                  className="flex-1 bg-accent text-black py-2 text-xs font-bold uppercase hover:bg-white transition-colors"
                >
                  Готово
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
