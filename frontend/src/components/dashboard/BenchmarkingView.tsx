"use client";
/**
 * BenchmarkingView — анонимное сравнение метрик пользователя с когортой.
 *
 * Каждая метрика показывается строкой:
 *   [label]            [your value]
 *   ════════●════════════
 *   median 47%   top10% 58%   top1% 65%   ← ты на 73-м перцентиле
 *
 * Пока живых юзеров < 100 — база синтетическая (academic baselines из
 * Barber & Odean, Linnainmaa и др.) с явной плашкой «base academic».
 */
import { Globe, Info, Award } from "lucide-react";

interface BenchmarkItem {
  name: string;
  label: string;
  user_value: number;
  cohort_median: number;
  cohort_top10: number;
  cohort_top1: number;
  user_percentile: number;
  is_synthetic: boolean;
  lower_is_better: boolean;
  neutral?: boolean;
}

export interface BenchmarkResponse {
  cohort_size: number;
  is_synthetic: boolean;
  min_cohort_required?: number;
  items: BenchmarkItem[];
  disclaimer: string;
}

interface Props {
  data: BenchmarkResponse | null;
  loading?: boolean;
}

export function BenchmarkingView({ data, loading }: Props) {
  if (loading) return <Skeleton />;
  if (!data) {
    return (
      <div className="rounded-[var(--radius-xl)] border border-[var(--border)] bg-[var(--surface-1)] p-10 text-center text-[14px] text-[var(--text-secondary)]">
        Не удалось загрузить сравнение.
      </div>
    );
  }

  if (!data.items || data.items.length === 0) {
    return (
      <div className="rounded-[var(--radius-xl)] border border-[var(--border)] bg-[var(--surface-1)] p-10 text-center">
        <div className="w-12 h-12 mx-auto mb-3 rounded-full bg-[var(--surface-2)] flex items-center justify-center text-[var(--text-tertiary)]">
          <Globe size={20} />
        </div>
        <p className="text-[14px] text-[var(--text-secondary)] max-w-sm mx-auto">{data.disclaimer}</p>
      </div>
    );
  }

  // Подсчёт «итогового рейтинга» — медиана перцентилей по всем не-нейтральным метрикам.
  const scoring = data.items.filter((i) => !i.neutral);
  const overallPct =
    scoring.length > 0
      ? Math.round(
          scoring
            .map((i) => i.user_percentile)
            .sort((a, b) => a - b)[Math.floor(scoring.length / 2)],
        )
      : 0;

  return (
    <div className="space-y-5">
      {/* Header banner */}
      <div className="rounded-[var(--radius-xl)] border border-[var(--accent)]/30 bg-gradient-to-r from-[var(--accent-soft)] to-transparent p-5 md:p-6">
        <div className="flex items-start gap-4">
          <div className="w-12 h-12 flex-shrink-0 rounded-[var(--radius-lg)] bg-[var(--accent-soft)] text-[var(--accent)] flex items-center justify-center">
            <Award size={22} />
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-baseline gap-3 flex-wrap">
              <h3 className="text-[17px] font-semibold leading-tight">Твой общий рейтинг:</h3>
              <span className="text-[24px] font-bold tracking-tight text-[var(--accent)]">
                {overallPct}-й перцентиль
              </span>
            </div>
            <p className="text-[13px] text-[var(--text-secondary)] mt-1.5">
              {overallPct >= 90
                ? `Ты в топ-${100 - overallPct}% всех ${data.is_synthetic ? "ретейл-трейдеров (academic baseline)" : "юзеров Eqio"}. Это редкий уровень.`
                : overallPct >= 75
                ? `Ты лучше ${overallPct}% когорты. Хороший трейдер.`
                : overallPct >= 50
                ? `Ты выше медианы — большинство торгует хуже.`
                : `Есть куда расти. Топовые трейдеры выше по большинству метрик.`}
            </p>
          </div>
        </div>
      </div>

      {/* Disclaimer */}
      <div className="flex items-start gap-2 px-1 py-2 text-[12px] text-[var(--text-tertiary)]">
        <Info size={12} className="mt-0.5 flex-shrink-0" />
        <span>{data.disclaimer}</span>
      </div>

      {/* Per-metric comparison */}
      <div className="rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--surface-1)] divide-y divide-[var(--border)]">
        {data.items.map((item) => (
          <BenchmarkRow key={item.name} item={item} />
        ))}
      </div>
    </div>
  );
}

function BenchmarkRow({ item }: { item: BenchmarkItem }) {
  // Шкала визуально: 0 → 100. Маркер «ты» в позиции user_percentile.
  // Reference points (median=50, top25=75, top10=90, top1=99) рисуем тиками.
  const youPos = Math.max(2, Math.min(98, item.user_percentile));

  const accent = item.neutral
    ? "bg-[var(--text-tertiary)]"
    : item.user_percentile >= 90
    ? "bg-[var(--success)]"
    : item.user_percentile >= 75
    ? "bg-[var(--accent)]"
    : item.user_percentile >= 50
    ? "bg-[var(--warning)]"
    : "bg-[var(--danger)]";

  return (
    <div className="px-4 py-4">
      {/* Top: label + your value + percentile badge */}
      <div className="flex items-baseline justify-between gap-3 mb-2 flex-wrap">
        <div className="flex items-baseline gap-3">
          <span className="text-[13px] font-medium text-[var(--foreground)]">{item.label}</span>
          {item.neutral && (
            <span className="text-[10px] text-[var(--text-tertiary)] uppercase tracking-wider">активность</span>
          )}
        </div>
        <div className="flex items-baseline gap-3">
          <span className="text-[18px] font-bold tracking-tight font-mono">
            {fmtUserValue(item.user_value, item.name)}
          </span>
          {!item.neutral && (
            <span className={`text-[11px] font-semibold px-2 py-0.5 rounded-[var(--radius-pill)] text-white ${accent}`}>
              {item.user_percentile}-й перцентиль
            </span>
          )}
        </div>
      </div>

      {/* Percentile bar */}
      <div className="relative h-2 bg-[var(--surface-2)] rounded-full mb-2">
        {/* Tick marks at median(50), top25(75), top10(90), top1(99) */}
        {[50, 75, 90].map((tick) => (
          <div
            key={tick}
            className="absolute top-0 h-full w-px bg-[var(--border-strong)]"
            style={{ left: `${tick}%` }}
          />
        ))}
        {/* User position marker */}
        <div
          className={`absolute top-1/2 -translate-y-1/2 -translate-x-1/2 w-3 h-3 rounded-full ${accent} border-2 border-[var(--surface-1)] shadow`}
          style={{ left: `${youPos}%` }}
          title={`Ты на ${item.user_percentile}-м перцентиле`}
        />
      </div>

      {/* Reference values */}
      <div className="flex justify-between text-[10px] font-mono text-[var(--text-tertiary)]">
        <span>median {fmtRefValue(item.cohort_median, item.name)}</span>
        <span>top10% {fmtRefValue(item.cohort_top10, item.name)}</span>
        <span>top1% {fmtRefValue(item.cohort_top1, item.name)}</span>
      </div>
    </div>
  );
}

function Skeleton() {
  return (
    <div className="space-y-3">
      <div className="h-24 rounded-[var(--radius-xl)] border border-[var(--border)] bg-[var(--surface-1)] animate-pulse" />
      <div className="rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--surface-1)]">
        {Array.from({ length: 8 }).map((_, i) => (
          <div key={i} className="h-20 m-4 rounded bg-[var(--surface-2)] animate-pulse" />
        ))}
      </div>
    </div>
  );
}

// %-метрики и денежные различаем при форматировании
function fmtUserValue(v: number, name: string): string {
  if (v === null || v === undefined) return "—";
  if (name === "win_rate" || name === "max_drawdown_pct") return `${v.toFixed(1)}%`;
  if (name === "trades_per_week") return v.toFixed(1);
  if (name === "optimal_f") return v.toFixed(3);
  return v.toFixed(2);
}

function fmtRefValue(v: number, name: string): string {
  if (name === "win_rate" || name === "max_drawdown_pct") return `${v}%`;
  if (name === "optimal_f") return v.toFixed(3);
  return String(v);
}
