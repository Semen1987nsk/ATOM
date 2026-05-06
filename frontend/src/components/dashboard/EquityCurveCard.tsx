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
}

export function EquityCurveCard({
  data,
  benchmark,
  benchmarkLabel = "IMOEX",
  initialBalance = 0,
  formatCurrency = (n) => `${n.toLocaleString("ru-RU", { maximumFractionDigits: 0 })} ₽`,
}: Props) {
  // Объединяем equity + benchmark в общий dataset для recharts ComposedChart.
  // equity_curve может быть intraday ("YYYY-MM-DD HH:MM"), IMOEX — daily ("YYYY-MM-DD").
  // Матчим по date-префиксу: для всех intraday-точек одного дня используем CLOSE этого дня.
  const merged = useMemo(() => {
    if (!data || data.length === 0) return [];
    const benchByDate: Record<string, number> = {};
    if (benchmark) {
      for (const b of benchmark) benchByDate[b.date.slice(0, 10)] = b.value;
    }
    // Нормализуем benchmark к стартовому balance, чтобы линии были сравнимы
    const firstBenchmark = benchmark?.[0]?.value;
    const ratio = firstBenchmark && data[0]?.balance ? data[0].balance / firstBenchmark : 1;
    return data.map((p) => {
      const dayKey = p.date.slice(0, 10);
      const benchValue = benchByDate[dayKey];
      return {
        date: p.date,
        balance: p.balance,
        benchmark: benchValue !== undefined ? benchValue * ratio : null,
      };
    });
  }, [data, benchmark]);

  const stats = useMemo(() => {
    if (!data || data.length === 0) return null;
    const start = initialBalance || data[0].balance;
    const end = data[data.length - 1].balance;
    const change = end - start;
    const changePct = start !== 0 ? (change / Math.abs(start)) * 100 : 0;
    return { start, end, change, changePct };
  }, [data, initialBalance]);

  if (!data || data.length === 0) {
    return (
      <div className="rounded-[var(--radius-xl)] border border-[var(--border)] bg-[var(--surface-1)] p-6 mb-6">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h3 className="text-base font-semibold tracking-tight">Кривая капитала</h3>
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
            Кумулятивный баланс счёта по времени{benchmark && benchmark.length > 0 ? ` · ${benchmarkLabel} для сравнения` : ""}.
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
              <span className="opacity-70">
                ({stats.changePct >= 0 ? "+" : ""}{stats.changePct.toFixed(1)}%)
              </span>
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
