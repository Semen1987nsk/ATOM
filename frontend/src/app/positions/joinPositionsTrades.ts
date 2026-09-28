// frontend/src/app/positions/joinPositionsTrades.ts

/**
 * Join Position-snapshot (Tinkoff Portfolio API) с агрегированными
 * round-trip позициями (Trade table) по `instrument_uid`. Возвращает
 * массив enriched-позиций: snapshot строка с прикреплёнными open Trade
 * rows для expand-row UI.
 *
 * Контракт endpoint'ов:
 * - `/positions` отдаёт `PositionResponse[]` (snapshot).
 * - `/trades/positions?status=open` отдаёт `PositionTrade[]` (aggregate
 *   с executions внутри).
 *
 * Если у snapshot позиции нет matching open Trade rows — позиция
 * показывается с пустым executions (UI отрендерит «Trade row не создан»
 * placeholder).
 *
 * Если есть open Trade rows без matching snapshot — они отфильтровываются
 * (Position table = source of truth для отображения, см. design doc).
 */

export interface PositionResponse {
  instrument_uid: string;
  instrument_type: string;
  figi: string | null;
  ticker: string | null;
  name: string | null;
  quantity: number;
  avg_entry_price: string;
  current_price: string | null;
  unrealized_pnl: string | null;
  unrealized_pnl_percent: number | null;
  last_priced_at: string | null;
  currency: string;
}

export interface TradeExecution {
  id: number;
  entry_at: string;
  exit_at: string | null;
  entry_price: number;
  exit_price: number | null;
  quantity: number;
  direction: string;
  notes?: string | null;
  has_notes?: boolean;
  setup_name?: string | null;
  screenshot_url?: string | null;
}

export interface PositionTrade {
  symbol: string;
  asset_name: string | null;
  instrument_uid: string | null;
  status: 'open' | 'closed';
  executions: TradeExecution[];
}

export interface EnrichedPosition extends PositionResponse {
  open_executions: TradeExecution[];
}

export function joinPositionsTrades(
  snapshot: PositionResponse[],
  openTrades: PositionTrade[],
): EnrichedPosition[] {
  // Индексируем open Trade rows по instrument_uid → executions.
  // Один instrument_uid может иметь только одну PositionTrade-группу
  // в статусе 'open' (round-trip lifecycle = один открытый цикл per
  // instrument). Если несколько — мерджим executions (defensive).
  const tradesByUid = new Map<string, TradeExecution[]>();
  for (const pt of openTrades) {
    if (!pt.instrument_uid || pt.status !== 'open') continue;
    const existing = tradesByUid.get(pt.instrument_uid) || [];
    tradesByUid.set(pt.instrument_uid, [...existing, ...pt.executions]);
  }

  return snapshot.map((pos) => ({
    ...pos,
    open_executions: tradesByUid.get(pos.instrument_uid) || [],
  }));
}
