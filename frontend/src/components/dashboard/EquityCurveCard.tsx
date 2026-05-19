"use client";
/**
 * EquityCurveCard — главный график дашборда: кумулятивный баланс по времени.
 *
 * Берёт `stats.equity_curve: [{ date, balance }]` (бекенд уже считал, но
 * фронт его никогда не рендерил — это была дыра #1 после аудита).
 *
 * Plus: опциональный benchmark-overlay (IMOEX). Если данных нет —
 * рисуем только equity, без разрыва UI.
 */
import { useMemo } from "react";
import {
  ComposedChart,
  Area,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
  ReferenceArea,
  ReferenceDot,
} from "recharts";

// recharts v3 убрал стабильный экспорт TooltipProps — используем локальный shape
// под content-callback'а, чтобы не пытаться угадать generic параметры.
type RechartsTooltipPayloadItem = { dataKey?: string | number; value?: number | string };
type RechartsTooltipContentProps = {
  active?: boolean;
  payload?: RechartsTooltipPayloadItem[];
  label?: string | number;
};
import { TrendingUp, TrendingDown } from "lucide-react";

interface EquityPoint {
  date: string;
  balance: number;
}

interface BenchmarkPoint {
  date: string;
  value: number;
}

interface Props {
  data?: EquityPoint[];
  benchmark?: BenchmarkPoint[];
  benchmarkLabel?: string;
  initialBalance?: number;
  formatCurrency?: (n: number) => string;
  // PR 23: для broker-юзера кривая = кумулятивный realized PnL (стартует от 0),
  // а не «капитал по времени». Точный исторический баланс при margin/futures
  // Tinkoff API не даёт реконструировать.
  isBrokerCumulative?: boolean;
  // Phase 6.6 (2026-05-18): single-source-of-truth для P&L.
  // liveUnrealizedSum = Σ /trades/unrealized-pnl (FX-adjusted live).
  // snapshotUnrealized = Σ Position.unrealized_pnl (то что backend уже
  // прибавил в data[-1].balance). Здесь переписываем последнюю точку
  // с live unrealized, чтобы curve top label == headline card.
  liveUnrealizedSum?: number | null;
  snapshotUnrealized?: number;
  // pctBaseline — для broker_user (isBrokerCumulative=true) используется как
  // знаменатель в % изменения капитала. Σ NET_DEPOSIT = вся capital deployed
  // на счёт за историю. Без baseline % в шапке не отрисуется.
  pctBaseline?: number;
  peakDate?: string | null;
  troughDate?: string | null;
}

export function EquityCurveCard({
  data,
  benchmark,
  benchmarkLabel = "IMOEX",
  initialBalance = 0,
  isBrokerCumulative = false,
  formatCurrency = (n) => `${n.toLocaleString("ru-RU", { maximumFractionDigits: 0 })} ₽`,
  liveUnrealizedSum,
  snapshotUnrealized,
  pctBaseline,
  peakDate,
  troughDate,
}: Props) {
  // Phase 6.6: override last point с live unrealized для single-source-of-truth.
  const dataAdjusted = useMemo(() => {
    if (!data || data.length === 0) return data;
    if (liveUnrealizedSum === null || liveUnrealizedSum === undefined) return data;
    const snapshot = snapshotUnrealized ?? 0;
    const delta = liveUnrealizedSum - snapshot;
    if (Math.abs(delta) < 0.005) return data;
    const last = data[data.length - 1];
    return [
      ...data.slice(0, -1),
      { date: last.date, balance: last.balance + delta },
    ];
  }, [data, liveUnrealizedSum, snapshotUnrealized]);
  // Объединяем equity + benchmark в общий dataset для recharts ComposedChart.
  // equity_curve может быть intraday ("YYYY-MM-DD HH:MM"), IMOEX — daily ("YYYY-MM-DD").
  // Матчим по date-префиксу: для всех intraday-точек одного дня используем CLOSE этого дня.
  const merged = useMemo(() => {
    if (!dataAdjusted || dataAdjusted.length === 0) return [];
    const benchByDate: Record<string, number> = {};
    if (benchmark) {
      for (const b of benchmark) benchByDate[b.date.slice(0, 10)] = b.value;
    }
    // Нормализуем benchmark к стартовому balance, чтобы линии были сравнимы
    const firstBenchmark = benchmark?.[0]?.value;
    const ratio = firstBenchmark && dataAdjusted[0]?.balance ? dataAdjusted[0].balance / firstBenchmark : 1;
    return dataAdjusted.map((p) => {
      const dayKey = p.date.slice(0, 10);
      const benchValue = benchByDate[dayKey];
      return {
        date: p.date,
        balance: p.balance,
        benchmark: benchValue !== undefined ? benchValue * ratio : null,
      };
    });
  }, [dataAdjusted, benchmark]);

  const stats = useMemo<{
    start: number;
    end: number;
    change: number;
    changePct: number | null;
  } | null>(() => {
    if (!dataAdjusted || dataAdjusted.length === 0) return null;
    const end = dataAdjusted[dataAdjusted.length - 1].balance;

    if (isBrokerCumulative) {
      // Кривая начинается от 0 → cumulative PnL. % считаем относительно
      // Σ NET_DEPOSIT (реальный historical baseline). data[0] для broker_user
      // ≈ PnL первой сделки (часто близко к 0), деление давало мусор -113188%.
      if (!pctBaseline || pctBaseline <= 0) {
        return { start: 0, end, change: end, changePct: null };
      }
      return {
        start: 0,
        end,
        change: end,
        changePct: (end / pctBaseline) * 100,
      };
    }

    const start = initialBalance || dataAdjusted[0].balance;
    const change = end - start;
    const changePct = start !== 0 ? (change / Math.abs(start)) * 100 : 0;
    return { start, end, change, changePct };
  }, [dataAdjusted, initialBalance, isBrokerCumulative, pctBaseline]);

  if (!data || data.length === 0) {
    return (
      <div className="rounded-[var(--radius-xl)] border border-[var(--border)] bg-[var(--surface-1)] p-6 mb-6">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h3 className="text-base font-semibold tracking-tight">{isBrokerCumulative ? "Кумулятивный PnL" : "Кривая капитала"}</h3>
            <p className="text-[12px] text-[var(--text-tertiary)] mt-0.5">
              Появится после первой закрытой сделки.
            </p>
          </div>
        </div>
        <div className="h-[280px] flex items-center justify-center text-[var(--text-tertiary)] text-[13px]">
          Нет данных
        </div>
      </div>
    );
  }

  const tone = (stats?.change ?? 0) >= 0 ? "success" : "danger";
  const lineColor = tone === "success" ? "var(--success)" : "var(--danger)";

  return (
    <div className="rounded-[var(--radius-xl)] border border-[var(--border)] bg-[var(--surface-1)] p-6 mb-6">
      {/* Header */}
      <div className="flex items-start justify-between gap-4 mb-5 flex-wrap">
        <div>
          <h3 className="text-base font-semibold tracking-tight">Кривая капитала</h3>
          <p className="text-[12px] text-[var(--text-tertiary)] mt-0.5">
            {isBrokerCumulative
              ? <>Сумма реализованной прибыли/убытка по закрытым сделкам (от 0 на дате первой сделки). Точный исторический баланс счёта при margin/futures Tinkoff API не даёт реконструировать.</>
              : <>Кумулятивный баланс счёта по времени{benchmark && benchmark.length > 0 ? ` · ${benchmarkLabel} для сравнения` : ""}.</>}
          </p>
        </div>
        {stats && (
          <div className="flex items-baseline gap-2">
            <span className="text-[20px] font-bold tracking-tight tabular-nums">
              {formatCurrency(stats.end)}
            </span>
            <span
              className={`flex items-center gap-1 text-[13px] font-semibold tabular-nums ${
                tone === "success" ? "text-[var(--success)]" : "text-[var(--danger)]"
              }`}
            >
              {tone === "success" ? <TrendingUp size={13} /> : <TrendingDown size={13} />}
              {stats.change >= 0 ? "+" : ""}{formatCurrency(stats.change)}
              {stats.changePct !== null && stats.changePct !== undefined && (
                <span className="opacity-70">
                  ({stats.changePct >= 0 ? "+" : ""}{stats.changePct.toFixed(1)}%)
                </span>
              )}
            </span>
          </div>
        )}
      </div>

      {/* Chart */}
      <div className="h-[280px] -mx-2">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={merged} margin={{ top: 5, right: 12, left: 0, bottom: 0 }}>
            <defs>
              <linearGradient id="equityGradient" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={lineColor} stopOpacity={0.25} />
                <stop offset="100%" stopColor={lineColor} stopOpacity={0} />
              </linearGradient>
            </defs>
            {peakDate && troughDate && (() => {
              // Найти точку в dataAdjusted по date prefix (YYYY-MM-DD) чтобы Recharts
              // matched по точному значению XAxis dataKey.
              const findClosest = (target: string) => {
                if (!target || !dataAdjusted) return null;
                const prefix = target.slice(0, 10);
                return dataAdjusted.find((p) => p.date.startsWith(prefix)) ?? null;
              };
              const peakPt = findClosest(peakDate);
              const troughPt = findClosest(troughDate);
              if (!peakPt || !troughPt) return null;
              return (
                <>
                  <ReferenceArea
                    x1={peakPt.date}
                    x2={troughPt.date}
                    fill="var(--danger)"
                    fillOpacity={0.15}
                    ifOverflow="extendDomain"
                  />
                  <ReferenceDot
                    x={peakPt.date}
                    y={peakPt.balance}
                    r={5}
                    fill="var(--success)"
                    stroke="var(--surface-1)"
                    strokeWidth={2}
                    label={{ value: "пик", position: "top", fill: "var(--success)", fontSize: 10, offset: 8 }}
                  />
                  <ReferenceDot
                    x={troughPt.date}
                    y={troughPt.balance}
                    r={5}
                    fill="var(--danger)"
                    stroke="var(--surface-1)"
                    strokeWidth={2}
                    label={{ value: "дно", position: "bottom", fill: "var(--danger)", fontSize: 10, offset: 8 }}
                  />
                </>
              );
            })()}
            <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" vertical={false} />
            <XAxis
              dataKey="date"
              tickFormatter={(v) => formatShortDate(v)}
              stroke="var(--text-tertiary)"
              tick={{ fontSize: 11 }}
              axisLine={false}
              tickLine={false}
              minTickGap={40}
            />
            <YAxis
              stroke="var(--text-tertiary)"
              tick={{ fontSize: 11 }}
              axisLine={false}
              tickLine={false}
              tickFormatter={(v) => compactCurrency(v)}
              width={70}
            />
            {initialBalance > 0 && (
              <ReferenceLine
                y={initialBalance}
                stroke="var(--text-tertiary)"
                strokeDasharray="4 4"
                strokeOpacity={0.5}
                label={{
                  value: "Старт",
                  position: "insideTopRight",
                  fill: "var(--text-tertiary)",
                  fontSize: 10,
                }}
              />
            )}
            <Tooltip content={<EquityTooltip formatCurrency={formatCurrency} benchmarkLabel={benchmarkLabel} />} />
            <Area
              type="monotone"
              dataKey="balance"
              name="Баланс"
              stroke={lineColor}
              strokeWidth={2}
              fill="url(#equityGradient)"
              dot={false}
              activeDot={{ r: 4, fill: lineColor }}
            />
            {benchmark && benchmark.length > 0 && (
              <Line
                type="monotone"
                dataKey="benchmark"
                name={benchmarkLabel}
                stroke="var(--text-tertiary)"
                strokeWidth={1.5}
                strokeDasharray="5 4"
                dot={false}
              />
            )}
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

function EquityTooltip({
  active,
  payload,
  label,
  formatCurrency,
  benchmarkLabel,
}: RechartsTooltipContentProps & {
  formatCurrency: (n: number) => string;
  benchmarkLabel: string;
}) {
  if (!active || !payload || payload.length === 0) return null;

  const balance = payload.find((p) => p.dataKey === "balance")?.value;
  const benchmark = payload.find((p) => p.dataKey === "benchmark")?.value;

  return (
    <div className="rounded-[var(--radius-md)] border border-[var(--border)] bg-[var(--surface-2)] shadow-[var(--shadow-lg)] px-3 py-2 text-[12px]">
      <div className="font-mono text-[var(--text-tertiary)] mb-1">{formatLongDate(String(label))}</div>
      {balance !== undefined && (
        <div className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-[var(--accent)]" />
          <span className="font-medium">Баланс:</span>
          <span className="font-mono">{formatCurrency(Number(balance))}</span>
        </div>
      )}
      {benchmark !== undefined && benchmark !== null && (
        <div className="flex items-center gap-2 mt-0.5">
          <span className="w-2 h-2 rounded-full bg-[var(--text-tertiary)]" />
          <span className="font-medium">{benchmarkLabel}:</span>
          <span className="font-mono">{formatCurrency(Number(benchmark))}</span>
        </div>
      )}
    </div>
  );
}

function formatShortDate(iso: string): string {
  try {
    const d = new Date(iso);
    return d.toLocaleDateString("ru-RU", { day: "2-digit", month: "short" });
  } catch {
    return iso;
  }
}

function formatLongDate(iso: string): string {
  try {
    const d = new Date(iso);
    return d.toLocaleDateString("ru-RU", {
      day: "2-digit",
      month: "long",
      year: "numeric",
    });
  } catch {
    return iso;
  }
}

function compactCurrency(v: number): string {
  if (Math.abs(v) >= 1_000_000) return `${(v / 1_000_000).toFixed(1)}M`;
  if (Math.abs(v) >= 1_000) return `${(v / 1_000).toFixed(0)}K`;
  return `${v}`;
}
