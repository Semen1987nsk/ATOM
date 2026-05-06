import { type ReactNode } from "react";
import { TrendingUp, TrendingDown, Minus } from "lucide-react";
import { clsx } from "clsx";

export interface StatTileProps {
  /** Подпись метрики ("Total P&L", "Win Rate", ...) */
  label: string;
  /** Значение — отформатированная строка ("+₽15,420", "67.3%") */
  value: string;
  /** Дополнительная подпись под значением */
  subtitle?: string;
  /** Если задано — рендерим стрелку вверх/вниз */
  delta?: number;
  /** Форматтер для подписи delta. По умолчанию " {delta}%" */
  formatDelta?: (d: number) => string;
  /** Иконка слева */
  icon?: ReactNode;
  /** Тон значения: profit/loss/neutral. По умолчанию neutral. */
  tone?: "neutral" | "profit" | "loss";
  /** Skeleton-состояние */
  loading?: boolean;
  className?: string;
}

const toneClass = {
  neutral: "text-[var(--foreground)]",
  profit: "text-[var(--success)]",
  loss: "text-[var(--danger)]",
};

/**
 * Карточка-метрика: подпись, большое значение, опциональный delta.
 * Используется на дашборде и в `<StatsGrid>`.
 *
 * Дизайн-инвариант: значение — крупное (28-32px), подпись — небольшая (12-13px),
 * НЕ uppercase, чтобы не уходить в "Bloomberg-вайб".
 */
export function StatTile({
  label,
  value,
  subtitle,
  delta,
  formatDelta = (d) => `${d >= 0 ? "+" : ""}${d.toFixed(1)}%`,
  icon,
  tone = "neutral",
  loading,
  className,
}: StatTileProps) {
  if (loading) {
    return (
      <div className={clsx("cyber-card p-5", className)}>
        <div className="skeleton-shimmer h-3 w-20 mb-3" />
        <div className="skeleton-shimmer h-8 w-32 mb-2" />
        <div className="skeleton-shimmer h-3 w-16" />
      </div>
    );
  }

  return (
    <div className={clsx("cyber-card p-5 flex flex-col gap-2", className)}>
      <div className="flex items-center justify-between gap-2">
        <span className="text-[12px] font-medium text-[var(--text-secondary)]">{label}</span>
        {icon && <span className="text-[var(--text-tertiary)]">{icon}</span>}
      </div>
      <div className={clsx("text-[28px] font-bold leading-none tracking-tight tabular-nums", toneClass[tone])}>
        {value}
      </div>
      <div className="flex items-center gap-2 min-h-[20px]">
        {typeof delta === "number" && (
          <span
            className={clsx(
              "inline-flex items-center gap-1 text-[12px] font-medium",
              delta > 0 && "text-[var(--success)]",
              delta < 0 && "text-[var(--danger)]",
              delta === 0 && "text-[var(--text-tertiary)]",
            )}
          >
            {delta > 0 ? <TrendingUp className="w-3 h-3" /> : delta < 0 ? <TrendingDown className="w-3 h-3" /> : <Minus className="w-3 h-3" />}
            {formatDelta(delta)}
          </span>
        )}
        {subtitle && (
          <span className="text-[12px] text-[var(--text-tertiary)]">{subtitle}</span>
        )}
      </div>
    </div>
  );
}
