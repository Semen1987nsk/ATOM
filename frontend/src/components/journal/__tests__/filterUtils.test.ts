/**
 * Phase 13 (2026-05-17): unit tests для filterUtils.
 *
 * NB: на момент Phase 13 в frontend/ нет test runner'а (jest/vitest).
 * Эти тесты vitest-compatible API; запустятся после добавления vitest:
 *   pnpm add -D vitest @vitest/ui
 *   npx vitest src/components/journal
 *
 * Pure-function утилиты — никаких React зависимостей, проверка чёткая.
 */
import { describe, it, expect } from 'vitest';
import {
  applyFilters,
  applySort,
  extractUniqueSetups,
  isAnyFilterActive,
  PositionTradeFilterable,
} from '../filterUtils';
import { DEFAULT_JOURNAL_FILTERS, JournalFilters } from '../types';

// ── fixtures ─────────────────────────────────────────────────────────

function makePos(over: Partial<PositionTradeFilterable> = {}): PositionTradeFilterable {
  return {
    symbol: 'TICK',
    asset_name: 'Test Asset',
    direction: 'long',
    realized_pnl: 100,
    unrealized_pnl: null,
    first_entry_at: '2026-05-17T10:00:00Z',
    holding_time_minutes: 60,
    setup_id: null,
    setup_name: null,
    notes: null,
    tags: [],
    pnl_pct: 1.5,
    status: 'closed',
    ...over,
  };
}

// ── search filter ────────────────────────────────────────────────────

describe('applyFilters — search', () => {
  it('matches symbol substring case-insensitive', () => {
    const positions = [
      makePos({ symbol: 'S0M6' }),
      makePos({ symbol: 'GLM6' }),
    ];
    const filters: JournalFilters = { ...DEFAULT_JOURNAL_FILTERS, search: 's0m' };
    const out = applyFilters(positions, filters);
    expect(out).toHaveLength(1);
    expect(out[0].symbol).toBe('S0M6');
  });

  it('matches setup_name', () => {
    const positions = [
      makePos({ symbol: 'AAA', setup_name: 'Breakout' }),
      makePos({ symbol: 'BBB', setup_name: 'Pullback' }),
    ];
    const out = applyFilters(positions, {
      ...DEFAULT_JOURNAL_FILTERS,
      search: 'breakout',
    });
    expect(out).toHaveLength(1);
    expect(out[0].symbol).toBe('AAA');
  });

  it('matches notes', () => {
    const positions = [
      makePos({ symbol: 'X', notes: 'был эмоциональный вход' }),
      makePos({ symbol: 'Y', notes: 'по плану' }),
    ];
    const out = applyFilters(positions, {
      ...DEFAULT_JOURNAL_FILTERS,
      search: 'эмоци',
    });
    expect(out).toHaveLength(1);
    expect(out[0].symbol).toBe('X');
  });

  it('empty search returns all', () => {
    const positions = [makePos(), makePos()];
    expect(applyFilters(positions, DEFAULT_JOURNAL_FILTERS)).toHaveLength(2);
  });
});

// ── direction filter ────────────────────────────────────────────────

describe('applyFilters — direction', () => {
  const positions = [
    makePos({ symbol: 'L1', direction: 'long' }),
    makePos({ symbol: 'L2', direction: 'LONG' }),
    makePos({ symbol: 'S1', direction: 'short' }),
  ];

  it('filters long', () => {
    const out = applyFilters(positions, {
      ...DEFAULT_JOURNAL_FILTERS,
      direction: 'long',
    });
    expect(out.map((p) => p.symbol).sort()).toEqual(['L1', 'L2']);
  });

  it('filters short', () => {
    const out = applyFilters(positions, {
      ...DEFAULT_JOURNAL_FILTERS,
      direction: 'short',
    });
    expect(out.map((p) => p.symbol)).toEqual(['S1']);
  });

  it('"all" passes both', () => {
    expect(
      applyFilters(positions, { ...DEFAULT_JOURNAL_FILTERS, direction: 'all' }),
    ).toHaveLength(3);
  });
});

// ── date range filter ───────────────────────────────────────────────

describe('applyFilters — dateRange', () => {
  const today = new Date();
  const isoToday = today.toISOString();
  const eightDaysAgo = new Date(today.getTime() - 8 * 86_400_000).toISOString();
  const ninetyOneDaysAgo = new Date(today.getTime() - 91 * 86_400_000).toISOString();

  const positions = [
    makePos({ symbol: 'TODAY', first_entry_at: isoToday }),
    makePos({ symbol: 'OLD8', first_entry_at: eightDaysAgo }),
    makePos({ symbol: 'OLD91', first_entry_at: ninetyOneDaysAgo }),
  ];

  it('week filter excludes >7d old', () => {
    const out = applyFilters(positions, {
      ...DEFAULT_JOURNAL_FILTERS,
      dateRange: 'week',
    });
    expect(out.map((p) => p.symbol)).toEqual(['TODAY']);
  });

  it('month filter (30d) excludes 91d-old', () => {
    const out = applyFilters(positions, {
      ...DEFAULT_JOURNAL_FILTERS,
      dateRange: 'month',
    });
    expect(out.map((p) => p.symbol).sort()).toEqual(['OLD8', 'TODAY']);
  });

  it('3months filter (90d) includes 8d-old but not 91d', () => {
    const out = applyFilters(positions, {
      ...DEFAULT_JOURNAL_FILTERS,
      dateRange: '3months',
    });
    expect(out.map((p) => p.symbol).sort()).toEqual(['OLD8', 'TODAY']);
  });

  it('custom from-to inclusive', () => {
    const fromDate = new Date(today.getTime() - 10 * 86_400_000)
      .toISOString()
      .slice(0, 10);
    const toDate = new Date(today.getTime() - 5 * 86_400_000)
      .toISOString()
      .slice(0, 10);
    const out = applyFilters(positions, {
      ...DEFAULT_JOURNAL_FILTERS,
      dateRange: 'custom',
      customDateFrom: fromDate,
      customDateTo: toDate,
    });
    expect(out.map((p) => p.symbol)).toEqual(['OLD8']);
  });
});

// ── setup filter ────────────────────────────────────────────────────

describe('applyFilters — setupId', () => {
  const positions = [
    makePos({ symbol: 'A', setup_id: 1, setup_name: 'Breakout' }),
    makePos({ symbol: 'B', setup_id: 2, setup_name: 'Pullback' }),
    makePos({ symbol: 'C', setup_id: null }),
  ];

  it('exact setup id match', () => {
    const out = applyFilters(positions, {
      ...DEFAULT_JOURNAL_FILTERS,
      setupId: 1,
    });
    expect(out.map((p) => p.symbol)).toEqual(['A']);
  });

  it('"none" matches только без setup_id', () => {
    const out = applyFilters(positions, {
      ...DEFAULT_JOURNAL_FILTERS,
      setupId: 'none',
    });
    expect(out.map((p) => p.symbol)).toEqual(['C']);
  });

  it('"all" passes all', () => {
    expect(applyFilters(positions, DEFAULT_JOURNAL_FILTERS)).toHaveLength(3);
  });
});

// ── combined filters ────────────────────────────────────────────────

describe('applyFilters — combined', () => {
  it('AND логика: direction + search', () => {
    const positions = [
      makePos({ symbol: 'AAPL', direction: 'long' }),
      makePos({ symbol: 'AAPL', direction: 'short' }),
      makePos({ symbol: 'TSLA', direction: 'long' }),
    ];
    const out = applyFilters(positions, {
      ...DEFAULT_JOURNAL_FILTERS,
      search: 'aapl',
      direction: 'long',
    });
    expect(out).toHaveLength(1);
    expect(out[0].direction).toBe('long');
    expect(out[0].symbol).toBe('AAPL');
  });
});

// ── sort ────────────────────────────────────────────────────────────

describe('applySort', () => {
  const positions = [
    makePos({
      symbol: 'A',
      first_entry_at: '2026-05-15T10:00:00Z',
      realized_pnl: 100,
      pnl_pct: 5,
      holding_time_minutes: 30,
    }),
    makePos({
      symbol: 'B',
      first_entry_at: '2026-05-17T10:00:00Z',
      realized_pnl: -50,
      pnl_pct: -2,
      holding_time_minutes: 120,
    }),
    makePos({
      symbol: 'C',
      first_entry_at: '2026-05-16T10:00:00Z',
      realized_pnl: 200,
      pnl_pct: 10,
      holding_time_minutes: 60,
    }),
  ];

  it('date_desc — newest first', () => {
    expect(applySort(positions, 'date_desc').map((p) => p.symbol)).toEqual(['B', 'C', 'A']);
  });

  it('date_asc — oldest first', () => {
    expect(applySort(positions, 'date_asc').map((p) => p.symbol)).toEqual(['A', 'C', 'B']);
  });

  it('pnl_desc — winners first', () => {
    expect(applySort(positions, 'pnl_desc').map((p) => p.symbol)).toEqual(['C', 'A', 'B']);
  });

  it('pnl_asc — losers first', () => {
    expect(applySort(positions, 'pnl_asc').map((p) => p.symbol)).toEqual(['B', 'A', 'C']);
  });

  it('duration_desc — longest holds first', () => {
    expect(applySort(positions, 'duration_desc').map((p) => p.symbol)).toEqual(['B', 'C', 'A']);
  });

  it('handles null pnl as 0', () => {
    const withNull = [
      makePos({ symbol: 'X', realized_pnl: null, status: 'closed' }),
      makePos({ symbol: 'Y', realized_pnl: 50 }),
      makePos({ symbol: 'Z', realized_pnl: -50 }),
    ];
    // null treated as 0 → между -50 и 50
    expect(applySort(withNull, 'pnl_asc').map((p) => p.symbol)).toEqual(['Z', 'X', 'Y']);
  });

  it('uses unrealized_pnl для open positions', () => {
    const mixed = [
      makePos({ symbol: 'OPEN', status: 'open', unrealized_pnl: 500, realized_pnl: null }),
      makePos({ symbol: 'CLOSED', status: 'closed', realized_pnl: 100 }),
    ];
    expect(applySort(mixed, 'pnl_desc').map((p) => p.symbol)).toEqual(['OPEN', 'CLOSED']);
  });
});

// ── extractUniqueSetups ─────────────────────────────────────────────

describe('extractUniqueSetups', () => {
  it('deduplicates by setup_id and sorts alphabetically', () => {
    const positions = [
      makePos({ setup_id: 2, setup_name: 'Pullback' }),
      makePos({ setup_id: 1, setup_name: 'Breakout' }),
      makePos({ setup_id: 2, setup_name: 'Pullback' }),
      makePos({ setup_id: null }),
    ];
    const out = extractUniqueSetups(positions);
    expect(out).toEqual([
      { id: 1, name: 'Breakout' },
      { id: 2, name: 'Pullback' },
    ]);
  });

  it('returns empty array when no setups', () => {
    expect(extractUniqueSetups([makePos({ setup_id: null })])).toEqual([]);
  });
});

// ── isAnyFilterActive ────────────────────────────────────────────────

describe('isAnyFilterActive', () => {
  it('returns false for default filters', () => {
    expect(isAnyFilterActive(DEFAULT_JOURNAL_FILTERS)).toBe(false);
  });

  it('returns true when search active', () => {
    expect(
      isAnyFilterActive({ ...DEFAULT_JOURNAL_FILTERS, search: 'x' }),
    ).toBe(true);
  });

  it('returns true when direction != all', () => {
    expect(
      isAnyFilterActive({ ...DEFAULT_JOURNAL_FILTERS, direction: 'long' }),
    ).toBe(true);
  });

  it('returns true when sort != date_desc', () => {
    expect(
      isAnyFilterActive({ ...DEFAULT_JOURNAL_FILTERS, sort: 'pnl_desc' }),
    ).toBe(true);
  });

  it('visibleLimit changes alone — NOT active (это pagination, не filter)', () => {
    expect(
      isAnyFilterActive({ ...DEFAULT_JOURNAL_FILTERS, visibleLimit: 500 }),
    ).toBe(false);
  });
});
