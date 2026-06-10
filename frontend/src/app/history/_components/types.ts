// Общие типы и константы для History page.
// Вынесено из page.tsx (refactor FE-08).

export const VIEW_MODE_STORAGE_KEY = 'empirik_history_view_mode';
export const STORAGE_KEY = 'empirik_history_columns';
export const SORT_STORAGE_KEY = 'empirik_history_sort';

export type JournalViewMode = 'grouped' | 'flat';
export type SortMode = 'latest_activity' | 'opened_at' | 'closed_at';
export type DirectionFilter = 'ALL' | 'LONG' | 'SHORT';

export interface ColumnConfig {
  id: string;
  label: string;
  defaultVisible: boolean;
  width?: string;
}

// PR 19: расширили список колонок по best practices трейдинг-дневников.
// Default-visible — 12 ключевых для активного MOEX-трейдера. Остальные
// доступны через column-picker. Порядок имеет значение — это порядок
// рендера и приоритет для пользователя.
export const ALL_COLUMNS: ColumnConfig[] = [
  { id: 'date', label: 'Дата', defaultVisible: true },
  { id: 'ticker', label: 'Тикер', defaultVisible: true },
  { id: 'name', label: 'Название', defaultVisible: true },
  { id: 'direction', label: 'Сторона', defaultVisible: true },
  { id: 'quantity', label: 'Кол-во', defaultVisible: true },
  { id: 'entry', label: 'Вход', defaultVisible: true },
  { id: 'exit', label: 'Выход', defaultVisible: true },
  { id: 'pnl', label: 'PnL', defaultVisible: true },
  { id: 'holding', label: 'Holding', defaultVisible: true },
  { id: 'setup', label: 'Сетап', defaultVisible: true },
  { id: 'note', label: 'Заметка', defaultVisible: true },
  // Hidden by default — доступны через column-picker:
  { id: 'timeframe', label: 'ТФ', defaultVisible: false },
  { id: 'status', label: 'Статус', defaultVisible: false }, // дублирует holding/exit_at
  { id: 'tags', label: 'Теги', defaultVisible: false },
  { id: 'commission', label: 'Комиссия', defaultVisible: false },
  { id: 'swap', label: 'Своп', defaultVisible: false },
  { id: 'confidence', label: 'Уверенность', defaultVisible: false },
  { id: 'risk', label: 'Риск', defaultVisible: false },
  { id: 'rMultiple', label: 'R-Multiple', defaultVisible: false },
  { id: 'leverage', label: 'Плечо', defaultVisible: false },
];

export const DIARY_PROMOTED_COLUMNS = ['setup', 'timeframe'];

export const ASSET_TYPE_LABELS: Record<string, string> = {
  share: 'Акции',
  futures: 'Фьючерсы',
  option: 'Опционы',
  bond: 'Облигации',
  etf: 'ETF',
  currency: 'Валюта',
};

export interface Trade {
  id: number;
  symbol: string;
  asset_name?: string;
  asset_type?: string;
  // PR 19: greenfield Tinkoff fields для иконок и фильтрации.
  instrument_type_v2?: string; // share|bond|etf|futures|option|currency
  instrument_uid?: string;
  data_source?: string; // tinkoff_v2|legacy|manual
  direction: string;
  pnl: number | null;
  net_pnl?: number | null;
  pnl_pct?: number | null;
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

export function getTradeSortTimestamp(trade: Trade, sortMode: SortMode): number {
  if (sortMode === 'opened_at') {
    return new Date(trade.entry_at).getTime();
  }

  if (sortMode === 'closed_at') {
    return trade.exit_at ? new Date(trade.exit_at).getTime() : Number.NEGATIVE_INFINITY;
  }

  return new Date(trade.exit_at || trade.entry_at).getTime();
}

export function formatHoldingTime(minutes: number | null | undefined): string {
  if (minutes == null || minutes < 0) return '—';
  if (minutes < 1) return '<1м';
  if (minutes < 60) return `${minutes}м`;
  // < 24 ч: "3ч 20м" (минуты только если >=5)
  if (minutes < 1440) {
    const h = Math.floor(minutes / 60);
    const m = minutes % 60;
    return m >= 5 ? `${h}ч ${m}м` : `${h}ч`;
  }
  // < 7 дней: "2д 4ч"
  if (minutes < 10080) {
    const d = Math.floor(minutes / 1440);
    const h = Math.floor((minutes % 1440) / 60);
    return h > 0 ? `${d}д ${h}ч` : `${d}д`;
  }
  // >= 7 дней: "1н 3д"
  const w = Math.floor(minutes / 10080);
  const d = Math.floor((minutes % 10080) / 1440);
  return d > 0 ? `${w}н ${d}д` : `${w}н`;
}
