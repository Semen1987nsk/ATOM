/**
 * Phase 13 (2026-05-17): pure filter/sort utilities для Journal Navigator Bar.
 * Тестируемые без UI зависимостей (Jest/Vitest).
 */
import { JournalFilters, SortKey } from './types';

// Minimal shape of PositionTrade что нужен для filter/sort.
// (Дублируется here чтобы можно было unit-тестировать без import из PositionJournalView.)
export interface PositionTradeFilterable {
  symbol: string;
  asset_name: string | null;
  direction: string;
  realized_pnl: number | null;
  unrealized_pnl: number | null;
  first_entry_at: string;
  holding_time_minutes: number | null;
  setup_id: number | null;
  setup_name: string | null;
  notes: string | null;
  tags: string[];
  pnl_pct: number | null;
  status: 'open' | 'closed';
}

// ── date range helpers ───────────────────────────────────────────────

function startOfDay(d: Date): Date {
  const r = new Date(d);
  r.setHours(0, 0, 0, 0);
  return r;
}

function daysAgo(days: number): Date {
  const r = startOfDay(new Date());
  r.setDate(r.getDate() - days);
  return r;
}

function matchesDateRange(iso: string, f: JournalFilters): boolean {
  if (f.dateRange === 'all') return true;
  const at = new Date(iso);
  if (Number.isNaN(at.getTime())) return false;

  if (f.dateRange === 'custom') {
    if (f.customDateFrom) {
      const from = new Date(f.customDateFrom);
      if (at < startOfDay(from)) return false;
    }
    if (f.customDateTo) {
      const to = new Date(f.customDateTo);
      // inclusive: добавляем 1 день и < startOfDay
      const toExclusive = startOfDay(to);
      toExclusive.setDate(toExclusive.getDate() + 1);
      if (at >= toExclusive) return false;
    }
    return true;
  }

  let cutoff: Date;
  switch (f.dateRange) {
    case 'today':
      cutoff = startOfDay(new Date());
      break;
    case 'week':
      cutoff = daysAgo(7);
      break;
    case 'month':
      cutoff = daysAgo(30);
      break;
    case '3months':
      cutoff = daysAgo(90);
      break;
    case 'year':
      cutoff = daysAgo(365);
      break;
    default:
      return true;
  }
  return at >= cutoff;
}

// ── search helper ────────────────────────────────────────────────────

function matchesSearch(p: PositionTradeFilterable, q: string): boolean {
  const lowered = q.trim().toLowerCase();
  if (!lowered) return true;
  const haystack = [
    p.symbol || '',
    p.asset_name || '',
    p.setup_name || '',
    p.notes || '',
    (p.tags || []).join(' '),
  ]
    .join(' ')
    .toLowerCase();
  return haystack.includes(lowered);
}

// ── main filter ──────────────────────────────────────────────────────

export function applyFilters<T extends PositionTradeFilterable>(
  positions: T[],
  filters: JournalFilters,
): T[] {
  return positions.filter((p) => {
    if (filters.search && !matchesSearch(p, filters.search)) return false;
    if (
      filters.direction !== 'all' &&
      (p.direction || '').toLowerCase() !== filters.direction
    ) {
      return false;
    }
    if (!matchesDateRange(p.first_entry_at, filters)) return false;
    if (filters.setupId === 'none' && p.setup_id !== null) return false;
    if (
      typeof filters.setupId === 'number' &&
      p.setup_id !== filters.setupId
    ) {
      return false;
    }
    return true;
  });
}

// ── sort ─────────────────────────────────────────────────────────────

function getPnl(p: PositionTradeFilterable): number {
  // Для open позиций используем unrealized, для closed — realized.
  if (p.status === 'open') return p.unrealized_pnl ?? 0;
  return p.realized_pnl ?? 0;
}

function getDate(p: PositionTradeFilterable): number {
  const t = new Date(p.first_entry_at).getTime();
  return Number.isNaN(t) ? 0 : t;
}

export function applySort<T extends PositionTradeFilterable>(
  positions: T[],
  sort: SortKey,
): T[] {
  const arr = [...positions];
  switch (sort) {
    case 'date_desc':
      arr.sort((a, b) => getDate(b) - getDate(a));
      break;
    case 'date_asc':
      arr.sort((a, b) => getDate(a) - getDate(b));
      break;
    case 'pnl_desc':
      arr.sort((a, b) => getPnl(b) - getPnl(a));
      break;
    case 'pnl_asc':
      arr.sort((a, b) => getPnl(a) - getPnl(b));
      break;
    case 'pct_desc':
      arr.sort((a, b) => (b.pnl_pct ?? -Infinity) - (a.pnl_pct ?? -Infinity));
      break;
    case 'pct_asc':
      arr.sort((a, b) => (a.pnl_pct ?? Infinity) - (b.pnl_pct ?? Infinity));
      break;
    case 'duration_desc':
      arr.sort(
        (a, b) =>
          (b.holding_time_minutes ?? 0) - (a.holding_time_minutes ?? 0),
      );
      break;
    case 'duration_asc':
      arr.sort(
        (a, b) =>
          (a.holding_time_minutes ?? Infinity) -
          (b.holding_time_minutes ?? Infinity),
      );
      break;
  }
  return arr;
}

// ── setup options ────────────────────────────────────────────────────

export function extractUniqueSetups<T extends PositionTradeFilterable>(
  positions: T[],
): { id: number; name: string }[] {
  const map = new Map<number, string>();
  for (const p of positions) {
    if (p.setup_id !== null && p.setup_name && !map.has(p.setup_id)) {
      map.set(p.setup_id, p.setup_name);
    }
  }
  return Array.from(map.entries())
    .map(([id, name]) => ({ id, name }))
    .sort((a, b) => a.name.localeCompare(b.name));
}

// ── helper: is filter active (для Reset button visibility) ───────────

export function isAnyFilterActive(filters: JournalFilters): boolean {
  return (
    filters.search !== '' ||
    filters.direction !== 'all' ||
    filters.dateRange !== 'all' ||
    filters.setupId !== 'all' ||
    filters.sort !== 'date_desc'
  );
}
