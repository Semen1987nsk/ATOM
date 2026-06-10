"use client";
/**
 * Trade Replay — график цены вокруг сделки + маркеры entry/exit/SL/TP/MAE/MFE.
 *
 * Тащит свечи с MOEX ISS через /trades/{id}/replay. На графике:
 * - линия close (тонированная под направление сделки),
 * - тень high-low (Area),
 * - горизонтальные ReferenceLine для SL/TP/entry/exit/MAE/MFE,
 * - вертикальные ReferenceLine на момент входа/выхода.
 *
 * MVP: line + reference lines. Полноценные свечи (с Rectangle на канвасе)
 * — следующая итерация, если этого MVP окажется мало.
 */
import { useEffect, useMemo, useState } from "react";
import { useParams, useRouter } from "next/navigation";
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
} from "@/lib/lazy-recharts";
import { ArrowLeft, AlertCircle } from "lucide-react";

// recharts v3 — локальный shape для content-callback'а Tooltip-а.
type RechartsTooltipPayloadItem = {
  dataKey?: string | number;
  value?: number | string;
  payload?: { ts?: number };
};
type RechartsTooltipContentProps = {
  active?: boolean;
  payload?: RechartsTooltipPayloadItem[];
  label?: string | number;
};
import { AppShell } from "@/components/AppShell";
import { DashboardSkeleton } from "@/components/Skeleton";
import { api } from "@/lib/apiClient";
import { useAuth } from "@/contexts/AuthContext";

interface Candle {
  t: string;       // ISO from backend (datetime)
  o: number;
  h: number;
  l: number;
  c: number;
  v: number;
}

interface Marker {
  type: "entry" | "exit" | "sl" | "tp" | "mae" | "mfe";
  t?: string | null;
  price: number;
  label: string;
}

interface ReplayData {
  trade_id: number;
  symbol: string;
  direction: string;
  interval: string;
  interval_auto: boolean;
  range_start: string;
  range_end: string;
  candles: Candle[];
  markers: Marker[];
  is_open: boolean;
  note?: string | null;
}

const INTERVALS = ["1m", "10m", "1h", "1d", "1w", "1mo"] as const;

const MARKER_STYLE: Record<Marker["type"], { color: string; dash?: string }> = {
  entry: { color: "var(--accent)" },
  exit: { color: "var(--accent)", dash: "4 2" },
  sl: { color: "var(--danger)", dash: "4 4" },
  tp: { color: "var(--success)", dash: "4 4" },
  mae: { color: "var(--warning)", dash: "2 4" },
  mfe: { color: "var(--success)", dash: "2 4" },
};

export default function TradeReplayPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const { user, isLoading: authLoading } = useAuth();
  const [data, setData] = useState<ReplayData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [interval, setInterval] = useState<string | null>(null); // null = auto

  useEffect(() => {
    if (!user || !params?.id) return;
    setLoading(true);
    setError(null);
    const qs = interval ? `?interval=${interval}` : "";
    api
      .get<ReplayData>(`/trades/${params.id}/replay${qs}`)
      .then((d) => {
        setData(d);
        setError(null);
      })
      .catch((e) => {
        setError((e as Error).message || "Не удалось загрузить replay");
        setData(null);
      })
      .finally(() => setLoading(false));
  }, [user, params?.id, interval]);

  // Mерж свечей в формат для recharts. Добавляем поле hl для Area band.
  // PR 26 Phase 2 (#63): downsample при >5000 свечей. Recharts начинает
  // freeze'иться. Берём каждую N-ю свечу по lttb-aware подходу: max/min/last
  // в группе сохраняем форму графика.
  const chartData = useMemo(() => {
    if (!data) return [];
    const raw = data.candles;
    const MAX_POINTS = 5000;
    if (raw.length <= MAX_POINTS) {
      return raw.map((c) => ({
        t: c.t,
        ts: new Date(c.t).getTime(),
        close: c.c,
        high: c.h,
        low: c.l,
      }));
    }
    // Downsample: bucket size, в каждом bucket — open первой + high/low max + close последней.
    const bucketSize = Math.ceil(raw.length / MAX_POINTS);
    const result: { t: string; ts: number; close: number; high: number; low: number }[] = [];
    for (let i = 0; i < raw.length; i += bucketSize) {
      const slice = raw.slice(i, i + bucketSize);
      let hi = -Infinity;
      let lo = Infinity;
      for (const c of slice) {
        if (c.h > hi) hi = c.h;
        if (c.l < lo) lo = c.l;
      }
      const last = slice[slice.length - 1];
      result.push({
        t: last.t,
        ts: new Date(last.t).getTime(),
        close: last.c,
        high: hi,
        low: lo,
      });
    }
    return result;
  }, [data]);

  // Y-домен: расширяем чтобы все горизонтальные маркеры (SL/TP/entry/MAE/MFE)
  // гарантированно были в кадре, иначе пользователь не видит, КУДА он попал.
  const yDomain = useMemo<[number | "auto", number | "auto"]>(() => {
    if (!data || chartData.length === 0) return ["auto", "auto"];
    let lo = Number.POSITIVE_INFINITY;
    let hi = Number.NEGATIVE_INFINITY;
    for (const c of chartData) {
      if (c.low < lo) lo = c.low;
      if (c.high > hi) hi = c.high;
    }
    for (const m of data.markers) {
      if (m.price < lo) lo = m.price;
      if (m.price > hi) hi = m.price;
    }
    if (!isFinite(lo) || !isFinite(hi)) return ["auto", "auto"];
    const pad = (hi - lo) * 0.05 || 1;
    return [lo - pad, hi + pad];
  }, [data, chartData]);

  const direction = data?.direction?.toLowerCase();
  const isLong = direction === "long";
  const lineColor = isLong ? "var(--success)" : "var(--danger)";

  if (authLoading) return <DashboardSkeleton />;

  return (
    <AppShell pageTitle="Trade Replay">
      <div className="p-6 md:p-8 max-w-6xl mx-auto">
        {/* Header */}
        <div className="mb-6 flex items-center justify-between gap-4 flex-wrap">
          <div className="flex items-center gap-3">
            <button
              onClick={() => router.back()}
              className="btn-icon"
              aria-label="Назад"
            >
              <ArrowLeft size={16} />
            </button>
            <div>
              <h1 className="text-[20px] font-bold tracking-tight">
                {data?.symbol ?? "—"}
                {data && (
                  <span
                    className={`ml-3 align-middle text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-[var(--radius-pill)] ${
                      isLong
                        ? "bg-[var(--success-soft)] text-[var(--success)]"
                        : "bg-[var(--danger-soft)] text-[var(--danger)]"
                    }`}
                  >
                    {data.direction}
                  </span>
                )}
                {data?.is_open && (
                  <span className="ml-2 align-middle text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-[var(--radius-pill)] bg-[var(--accent-soft)] text-[var(--accent)]">
                    Открыта
                  </span>
                )}
              </h1>
              <p className="text-[12px] text-[var(--text-tertiary)] mt-0.5">
                Свечи MOEX вокруг сделки. Маркеры — вход/выход, стоп, тейк, MAE, MFE.
              </p>
            </div>
          </div>

          {/* Interval picker */}
          <div className="flex items-center gap-1 rounded-[var(--radius-pill)] border border-[var(--border)] bg-[var(--surface-1)] p-1">
            <button
              onClick={() => setInterval(null)}
              className={`text-[11px] px-2.5 py-1 rounded-[var(--radius-pill)] transition-colors ${
                interval === null
                  ? "bg-[var(--accent)] text-white"
                  : "text-[var(--text-secondary)] hover:bg-[var(--surface-hover)]"
              }`}
            >
              Авто{data?.interval_auto && data.interval ? ` (${data.interval})` : ""}
            </button>
            {INTERVALS.map((i) => (
              <button
                key={i}
                onClick={() => setInterval(i)}
                className={`text-[11px] px-2.5 py-1 rounded-[var(--radius-pill)] transition-colors ${
                  interval === i
                    ? "bg-[var(--accent)] text-white"
                    : "text-[var(--text-secondary)] hover:bg-[var(--surface-hover)]"
                }`}
              >
                {i}
              </button>
            ))}
          </div>
        </div>

        {/* Body */}
        {loading ? (
          <DashboardSkeleton />
        ) : error ? (
          <ErrorBox message={error} />
        ) : !data ? (
          <ErrorBox message="Нет данных" />
        ) : (
          <>
            <div className="rounded-[var(--radius-xl)] border border-[var(--border)] bg-[var(--surface-1)] p-5">
              {data.note && (
                <div className="mb-3 flex items-start gap-2 rounded-[var(--radius-md)] border border-[var(--warning-soft)] bg-[var(--warning-soft)]/30 p-3 text-[12px] text-[var(--warning)]">
                  <AlertCircle size={14} className="mt-0.5 flex-shrink-0" />
                  <span>{data.note}</span>
                </div>
              )}

              {chartData.length === 0 ? (
                <div className="h-[380px] flex items-center justify-center text-[var(--text-tertiary)] text-[13px]">
                  Свечей нет
                </div>
              ) : (
                <div className="h-[420px] -mx-2">
                  <ResponsiveContainer width="100%" height="100%">
                    <ComposedChart data={chartData} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
                      <defs>
                        <linearGradient id="replayLineGradient" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="0%" stopColor={lineColor} stopOpacity={0.18} />
                          <stop offset="100%" stopColor={lineColor} stopOpacity={0} />
                        </linearGradient>
                      </defs>
                      <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" vertical={false} />
                      <XAxis
                        dataKey="ts"
                        type="number"
                        domain={["dataMin", "dataMax"]}
                        scale="time"
                        tickFormatter={(v) => formatXTick(v, data.interval)}
                        stroke="var(--text-tertiary)"
                        tick={{ fontSize: 11 }}
                        axisLine={false}
                        tickLine={false}
                        minTickGap={50}
                      />
                      <YAxis
                        domain={yDomain}
                        stroke="var(--text-tertiary)"
                        tick={{ fontSize: 11 }}
                        axisLine={false}
                        tickLine={false}
                        width={70}
                        tickFormatter={(v) => formatPrice(v)}
                      />
                      <Tooltip content={<ReplayTooltip />} />

                      {/* Тень high-low — отдельная Area от low до high (через два Line с заливкой не получится) */}
                      <Area
                        type="monotone"
                        dataKey="high"
                        stroke="transparent"
                        fill={lineColor}
                        fillOpacity={0.08}
                        baseLine={undefined}
                        legendType="none"
                        isAnimationActive={false}
                      />
                      <Area
                        type="monotone"
                        dataKey="low"
                        stroke="transparent"
                        fill="var(--surface-1)"
                        fillOpacity={1}
                        legendType="none"
                        isAnimationActive={false}
                      />

                      {/* Главная линия — close */}
                      <Line
                        type="monotone"
                        dataKey="close"
                        name="Цена"
                        stroke={lineColor}
                        strokeWidth={2}
                        dot={false}
                        activeDot={{ r: 4, fill: lineColor }}
                        isAnimationActive={false}
                      />

                      {/* Горизонтальные маркеры — все цены: SL, TP, entry, exit, MAE, MFE */}
                      {data.markers.map((m, idx) => {
                        const style = MARKER_STYLE[m.type];
                        return (
                          <ReferenceLine
                            key={`h-${idx}`}
                            y={m.price}
                            stroke={style.color}
                            strokeDasharray={style.dash}
                            strokeOpacity={0.85}
                            label={{
                              value: `${m.label} ${formatPrice(m.price)}`,
                              position: "right",
                              fill: style.color,
                              fontSize: 10,
                            }}
                          />
                        );
                      })}

                      {/* Вертикальные маркеры — entry/exit с временем */}
                      {data.markers
                        .filter((m) => m.t && (m.type === "entry" || m.type === "exit"))
                        .map((m, idx) => (
                          <ReferenceLine
                            key={`v-${idx}`}
                            x={new Date(m.t!).getTime()}
                            stroke={MARKER_STYLE[m.type].color}
                            strokeDasharray="3 3"
                            strokeOpacity={0.4}
                          />
                        ))}
                    </ComposedChart>
                  </ResponsiveContainer>
                </div>
              )}

              {/* Legend */}
              <div className="mt-4 flex flex-wrap gap-x-4 gap-y-2 text-[11px]">
                {data.markers.map((m) => {
                  const style = MARKER_STYLE[m.type];
                  return (
                    <div key={`${m.type}-${m.label}`} className="flex items-center gap-1.5">
                      <span
                        className="inline-block w-3 h-0.5"
                        style={{ background: style.color }}
                      />
                      <span className="text-[var(--text-secondary)]">{m.label}</span>
                      <span className="font-mono text-[var(--text-tertiary)]">
                        {formatPrice(m.price)}
                      </span>
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Meta info */}
            <div className="mt-4 grid grid-cols-2 md:grid-cols-4 gap-3 text-[12px]">
              <Stat label="Окно" value={`${formatDate(data.range_start)} → ${formatDate(data.range_end)}`} />
              <Stat label="Интервал" value={data.interval} />
              <Stat label="Свечей" value={String(data.candles.length)} />
              <Stat label="Статус" value={data.is_open ? "Открыта" : "Закрыта"} />
            </div>
          </>
        )}
      </div>
    </AppShell>
  );
}

function ReplayTooltip({ active, payload }: RechartsTooltipContentProps) {
  if (!active || !payload || payload.length === 0) return null;
  const close = payload.find((p) => p.dataKey === "close")?.value;
  const high = payload.find((p) => p.dataKey === "high")?.value;
  const low = payload.find((p) => p.dataKey === "low")?.value;
  // payload[0].payload содержит ts
  const ts = (payload[0]?.payload as { ts?: number } | undefined)?.ts;
  return (
    <div className="rounded-[var(--radius-md)] border border-[var(--border)] bg-[var(--surface-2)] shadow-[var(--shadow-lg)] px-3 py-2 text-[12px]">
      {ts && (
        <div className="font-mono text-[var(--text-tertiary)] mb-1">
          {new Date(ts).toLocaleString("ru-RU", {
            day: "2-digit",
            month: "2-digit",
            year: "2-digit",
            hour: "2-digit",
            minute: "2-digit",
          })}
        </div>
      )}
      {close !== undefined && (
        <div className="flex items-center gap-2">
          <span className="text-[var(--text-secondary)]">Close:</span>
          <span className="font-mono font-medium">{formatPrice(Number(close))}</span>
        </div>
      )}
      {high !== undefined && low !== undefined && (
        <div className="flex items-center gap-2 text-[var(--text-tertiary)]">
          <span>H/L:</span>
          <span className="font-mono">
            {formatPrice(Number(high))} / {formatPrice(Number(low))}
          </span>
        </div>
      )}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-[var(--radius-md)] border border-[var(--border)] bg-[var(--surface-1)] px-3 py-2">
      <div className="text-[10px] uppercase tracking-wider text-[var(--text-tertiary)]">{label}</div>
      <div className="mt-0.5 font-mono text-[12px] text-[var(--foreground)]">{value}</div>
    </div>
  );
}

function ErrorBox({ message }: { message: string }) {
  return (
    <div className="rounded-[var(--radius-xl)] border border-[var(--danger-soft)] bg-[var(--danger-soft)]/30 p-6 text-[14px] text-[var(--danger)]">
      <div className="flex items-center gap-2 font-semibold">
        <AlertCircle size={16} />
        Ошибка
      </div>
      <div className="mt-1.5">{message}</div>
    </div>
  );
}

function formatPrice(v: number): string {
  if (Math.abs(v) >= 1000) return v.toLocaleString("ru-RU", { maximumFractionDigits: 0 });
  return v.toLocaleString("ru-RU", { maximumFractionDigits: 2 });
}

function formatXTick(ts: number, interval: string): string {
  const d = new Date(ts);
  if (interval === "1m" || interval === "10m" || interval === "1h") {
    return d.toLocaleString("ru-RU", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
  }
  return d.toLocaleDateString("ru-RU", { day: "2-digit", month: "short" });
}

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleString("ru-RU", {
      day: "2-digit",
      month: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}
