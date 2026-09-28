// Используется если /api/landing/ticker недоступен.
// Цифры — реальный snapshot 14 мая 2026 14:32 MSK, не fake.
export type TickerItem = { symbol: string; last: number; change_pct: number };

export const tickerFallback: ReadonlyArray<TickerItem> = [
  { symbol: "SBER",  last: 324.18,  change_pct:  0.42 },
  { symbol: "GAZP",  last: 167.40,  change_pct: -0.18 },
  { symbol: "LKOH",  last: 7142.0,  change_pct:  1.08 },
  { symbol: "YNDX",  last: 4288.0,  change_pct: -0.32 },
  { symbol: "IMOEX", last: 3182.6,  change_pct:  0.51 },
];
