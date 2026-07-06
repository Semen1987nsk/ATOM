import { describe, it, expect } from 'vitest';

import { toStatsSubset } from '../dashboardTabsParams';

describe('toStatsSubset', () => {
  it('выбрасывает mae_method, сохраняет период/тег/точку отсчёта', () => {
    const params = { period: '7days', tag: 'plan', start_trade_id: '42', mae_method: 'moex' };
    expect(toStatsSubset(params)).toEqual({ period: '7days', tag: 'plan', start_trade_id: '42' });
  });

  it('пустой набор → пустой', () => {
    expect(toStatsSubset({})).toEqual({});
  });
});
