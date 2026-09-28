import { describe, it, expect } from 'vitest';

// Логика выбора нормировочной базы (вынесем в чистую функцию).
function benchmarkRatio(opts: {
  isBrokerCumulative: boolean;
  firstBalance: number | undefined;
  firstBenchmark: number | undefined;
  pctBaseline: number | undefined;
}): number | null {
  const { isBrokerCumulative, firstBalance, firstBenchmark, pctBaseline } = opts;
  if (!firstBenchmark) return null;
  const base = isBrokerCumulative ? pctBaseline : firstBalance;
  if (!base || base <= 0) return null;  // невалидная база → оверлей не рисуем
  return base / firstBenchmark;
}

describe('benchmarkRatio', () => {
  it('broker: использует pctBaseline, не PnL первой сделки', () => {
    const r = benchmarkRatio({ isBrokerCumulative: true, firstBalance: -500,
      firstBenchmark: 2800, pctBaseline: 1_000_000 });
    expect(r).toBeGreaterThan(0);
    expect(r).toBeCloseTo(1_000_000 / 2800);
  });

  it('broker без baseline → null (не рисуем)', () => {
    expect(benchmarkRatio({ isBrokerCumulative: true, firstBalance: -500,
      firstBenchmark: 2800, pctBaseline: 0 })).toBeNull();
  });

  it('non-broker: по firstBalance', () => {
    const r = benchmarkRatio({ isBrokerCumulative: false, firstBalance: 100000,
      firstBenchmark: 2800, pctBaseline: undefined });
    expect(r).toBeCloseTo(100000 / 2800);
  });
});
