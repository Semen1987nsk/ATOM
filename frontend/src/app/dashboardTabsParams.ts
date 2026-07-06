// advanced/benchmark принимают period/start_date/end_date/start_trade_id/tag,
// но НЕ mae_method — иначе бэкенд отбросит лишний query-параметр.
export function toStatsSubset(p: Record<string, string>): Record<string, string> {
  const { mae_method, ...rest } = p;
  void mae_method;
  return rest;
}
