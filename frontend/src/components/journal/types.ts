/**
 * Phase 13 (2026-05-17): Journal Navigator Bar — filter state types.
 */

export type SortKey =
  | 'date_desc'
  | 'date_asc'
  | 'pnl_desc'
  | 'pnl_asc'
  | 'pct_desc'
  | 'pct_asc'
  | 'duration_desc'
  | 'duration_asc';

export type DateRange =
  | 'all'
  | 'today'
  | 'week'
  | 'month'
  | '3months'
  | 'year'
  | 'custom';

export type DirectionFilter = 'all' | 'long' | 'short';

export interface JournalFilters {
  search: string;
  direction: DirectionFilter;
  dateRange: DateRange;
  customDateFrom: string | null;
  customDateTo: string | null;
  setupId: number | 'all' | 'none';
  sort: SortKey;
  visibleLimit: number;
}

export const DEFAULT_JOURNAL_FILTERS: JournalFilters = {
  search: '',
  direction: 'all',
  dateRange: 'all',
  customDateFrom: null,
  customDateTo: null,
  setupId: 'all',
  sort: 'date_desc',
  visibleLimit: 100,
};

export const SORT_OPTIONS: { key: SortKey; label: string }[] = [
  { key: 'date_desc', label: 'Дата ↓' },
  { key: 'date_asc', label: 'Дата ↑' },
  { key: 'pnl_desc', label: 'P&L ↓' },
  { key: 'pnl_asc', label: 'P&L ↑' },
  { key: 'pct_desc', label: '% ↓' },
  { key: 'pct_asc', label: '% ↑' },
  { key: 'duration_desc', label: 'Длительность ↓' },
  { key: 'duration_asc', label: 'Длительность ↑' },
];

export const DATE_RANGE_OPTIONS: { key: DateRange; label: string }[] = [
  { key: 'all', label: 'Всё' },
  { key: 'today', label: 'Сегодня' },
  { key: 'week', label: 'Неделя' },
  { key: 'month', label: 'Месяц' },
  { key: '3months', label: '3 мес' },
  { key: 'year', label: 'Год' },
  { key: 'custom', label: 'Период…' },
];
