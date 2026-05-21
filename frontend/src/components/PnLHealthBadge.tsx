"use client";
/**
 * Phase 10 (2026-05-17): P&L Health Check badge для дашборда.
 *
 * Показывает статус сверки двух методологий расчёта P&L:
 *   - Method A (Journal): closed Trade.net_pnl + open unrealized + adjustments
 *   - Method B (Cash):    portfolio_value − net_deposits
 *
 * Бейдж цвета:
 *   ✅ green   — diff < 0.5%  (status='ok')
 *   ⚠️ yellow  — diff 0.5–2%  (status='warning')
 *   ❌ red     — diff ≥ 2%    (status='mismatch')
 *   ⚪ gray    — нет данных   (status='na' или 'stale')
 *
 * Размер: compact (chip в headline area) или detailed (card в StatsGrid).
 */
import { useMemo } from "react";
import { ShieldCheck, AlertTriangle, AlertCircle, Loader2 } from "lucide-react";

export type PnLHealthStatus = "ok" | "warning" | "mismatch" | "na" | "stale";

export interface PnLHealthData {
  status: PnLHealthStatus;
  diff_pct: number | null;
  diff_rub: number | null;
  checked_at: string | null;
  breakdown?: Record<string, unknown> | null;
  message?: string;
}

interface BadgeStyle {
  dotColor: string;
  textColor: string;
  bgColor: string;
  borderColor: string;
  icon: React.ReactNode;
  label: string;
}

function styleFor(status: PnLHealthStatus): BadgeStyle {
  switch (status) {
    case "ok":
      return {
        dotColor: "bg-emerald-400",
        textColor: "text-emerald-400",
        bgColor: "bg-emerald-500/10",
        borderColor: "border-emerald-500/30",
        icon: <ShieldCheck size={14} />,
        label: "Корректно",
      };
    case "warning":
      return {
        dotColor: "bg-amber-400",
        textColor: "text-amber-400",
        bgColor: "bg-amber-500/10",
        borderColor: "border-amber-500/30",
        icon: <AlertTriangle size={14} />,
        label: "Внимание",
      };
    case "mismatch":
      return {
        dotColor: "bg-rose-400",
        textColor: "text-rose-400",
        bgColor: "bg-rose-500/10",
        borderColor: "border-rose-500/30",
        icon: <AlertCircle size={14} />,
        label: "Расхождение",
      };
    case "na":
      return {
        dotColor: "bg-slate-500",
        textColor: "text-slate-400",
        bgColor: "bg-slate-500/10",
        borderColor: "border-slate-500/30",
        icon: <ShieldCheck size={14} />,
        label: "Нет данных",
      };
    case "stale":
    default:
      return {
        dotColor: "bg-slate-500",
        textColor: "text-slate-400",
        bgColor: "bg-slate-500/10",
        borderColor: "border-slate-500/30",
        icon: <Loader2 size={14} />,
        label: "Проверка нужна",
      };
  }
}

function formatPct(pct: number | null): string {
  if (pct === null || pct === undefined) return "—";
  if (Math.abs(pct) < 0.01) return "<0.01%";
  return `${pct.toFixed(2)}%`;
}

function formatCurrency(value: number | null): string {
  if (value === null || value === undefined) return "—";
  return `${value.toLocaleString("ru-RU", { maximumFractionDigits: 0 })} ₽`;
}

function timeAgo(iso: string | null): string {
  if (!iso) return "никогда";
  const dt = new Date(iso);
  const diffMs = Date.now() - dt.getTime();
  const minutes = Math.floor(diffMs / 60000);
  if (minutes < 1) return "только что";
  if (minutes < 60) return `${minutes} мин назад`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} ч назад`;
  const days = Math.floor(hours / 24);
  return `${days} дн назад`;
}

interface PnLHealthBadgeProps {
  data: PnLHealthData | null;
  size?: "sm" | "md";
  onRefresh?: () => void;
  refreshing?: boolean;
}

interface HealthBreakdown {
  journal_pnl?: number | null;
  cash_pnl?: number | null;
  components?: {
    total_pnl_closed?: number | null;
    unrealized_pnl?: number | null;
    net_deposits?: number | null;
    portfolio_value?: number | null;
  } | null;
}

function PopoverRow({ label, value, strong = false, accent }: {
  label: string;
  value: string;
  strong?: boolean;
  accent?: string;
}) {
  return (
    <div className={`flex justify-between gap-4 ${strong ? "font-semibold" : ""}`}>
      <span className={strong ? "text-slate-200" : "text-slate-400"}>{label}</span>
      <span className={`font-mono tabular-nums ${accent ?? (strong ? "text-slate-100" : "text-slate-300")}`}>{value}</span>
    </div>
  );
}

/**
 * Богатый popover при наведении: подробная сверка журнала с брокером.
 * Объясняет ОБЕ цифры по компонентам + причину расхождения + шкалу.
 * Данные из breakdown (journal_pnl/cash_pnl/components) — приходят в /stats/.
 */
function HealthPopover({ data, status, style }: {
  data: PnLHealthData;
  status: PnLHealthStatus;
  style: BadgeStyle;
}) {
  const bd = (data.breakdown ?? null) as HealthBreakdown | null;
  const comp = bd?.components ?? null;

  // Нет данных / пустой счёт — короткое сообщение.
  if (status === "na" || data.diff_rub === null || data.diff_pct === null) {
    return (
      <div className="text-xs text-slate-300 leading-relaxed">
        {status === "na"
          ? "Недостаточно данных для сверки (нет операций по счёту)."
          : "Журнал и брокер сходятся — расхождений нет."}
      </div>
    );
  }

  const closed = comp?.total_pnl_closed ?? null;
  const unreal = comp?.unrealized_pnl ?? null;
  const deposits = comp?.net_deposits ?? null;
  const portfolio = comp?.portfolio_value ?? null;
  const journal = bd?.journal_pnl ?? null;
  const cash = bd?.cash_pnl ?? null;

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between gap-3">
        <span className="text-[13px] font-semibold text-slate-100">Сверка журнала с брокером</span>
        <span className={`text-xs font-semibold ${style.textColor}`}>{formatPct(data.diff_pct)}</span>
      </div>

      {/* Журнал */}
      <div className="space-y-1 text-[11px]">
        <div className="text-[10px] uppercase tracking-wider text-slate-500 font-semibold">Как считает журнал (дневник)</div>
        <PopoverRow label="Закрытые сделки (по ценам)" value={formatCurrency(closed)} />
        <PopoverRow label="Открытая позиция (текущая)" value={formatCurrency(unreal)} />
        <div className="border-t border-white/10 pt-1">
          <PopoverRow label="Итого журнал" value={formatCurrency(journal)} strong />
        </div>
      </div>

      {/* Брокер */}
      <div className="space-y-1 text-[11px]">
        <div className="text-[10px] uppercase tracking-wider text-slate-500 font-semibold">Как считает брокер (факт)</div>
        <PopoverRow label="Внесено (депозиты − выводы)" value={formatCurrency(deposits)} />
        <PopoverRow label="Сейчас на счёте" value={formatCurrency(portfolio)} />
        <div className="border-t border-white/10 pt-1">
          <PopoverRow label="Итого брокер" value={formatCurrency(cash)} strong />
        </div>
      </div>

      {/* Расхождение */}
      <div className="border-t border-white/10 pt-2">
        <PopoverRow
          label="Расхождение"
          value={`${formatCurrency(data.diff_rub)} (${formatPct(data.diff_pct)})`}
          strong
          accent={style.textColor}
        />
      </div>

      {/* Причина */}
      <p className="text-[11px] text-slate-400 leading-relaxed">
        Фьючерсы журнал считает по цене сделки (вход → выход), а брокер — по
        варм-марже (ежедневный клиринг по расчётной цене). Для закрытых сделок
        разрыв уже зафиксирован и сам не исчезнет. Деньги реально списаны со
        счёта — в балансе учтены, на торговлю не влияют.
      </p>

      {/* Шкала референсов */}
      <div className="border-t border-white/10 pt-2 text-[10px] text-slate-500">
        <span className="text-emerald-400">≤1% норма</span>
        <span className="mx-1">·</span>
        <span className="text-amber-400">1–5% ок для фьючерсов</span>
        <span className="mx-1">·</span>
        <span className="text-rose-400">&gt;5% стоит проверить</span>
      </div>
    </div>
  );
}

export function PnLHealthBadge({
  data,
  size = "md",
  onRefresh,
  refreshing = false,
}: PnLHealthBadgeProps) {
  // Пересчитываем status по diff_pct на фронте — БД хранит status строкой,
  // и пока user не нажал ↻, там может лежать старое значение. Frontend
  // же должен мгновенно отражать текущий threshold (1%/5%) без round-trip.
  const status: PnLHealthStatus = useMemo(() => {
    if (!data) return "stale";
    if (data.diff_pct === null || data.diff_pct === undefined) return data.status || "stale";
    const pct = Math.abs(data.diff_pct);
    if (data.status === "na") return "na";  // sentinel для пустых счетов
    if (pct < 1.0) return "ok";
    if (pct < 5.0) return "warning";
    return "mismatch";
  }, [data]);
  const style = styleFor(status);

  const isCompact = size === "sm";
  return (
    <div className="relative inline-block group">
      <div
        className={`inline-flex items-center gap-2 rounded-lg border ${style.borderColor} ${style.bgColor} ${isCompact ? "px-2 py-1" : "px-3 py-1.5"} ${style.textColor} cursor-help`}
      >
        <span className={`w-2 h-2 rounded-full ${style.dotColor} ${status === "warning" || status === "mismatch" ? "animate-pulse" : ""}`} />
        <span className={`inline-flex items-center gap-1 ${isCompact ? "text-xs" : "text-sm"} font-medium`}>
          {style.icon}
          {style.label}
          {data?.diff_pct !== null && data?.diff_pct !== undefined && (
            <span className="opacity-75">{formatPct(data.diff_pct)}</span>
          )}
        </span>
        {onRefresh && (
          <button
            onClick={onRefresh}
            disabled={refreshing}
            className="ml-1 text-xs underline decoration-dotted opacity-75 hover:opacity-100 disabled:opacity-40"
            title="Запустить проверку сейчас"
          >
            {refreshing ? "..." : "↻"}
          </button>
        )}
      </div>

      {/* Богатый popover при наведении */}
      {data && (
        <div className="absolute left-0 top-full mt-2 z-50 w-[340px] max-w-[90vw] rounded-xl border border-slate-700 bg-slate-900/98 backdrop-blur-sm p-4 shadow-2xl opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-opacity duration-150 pointer-events-none">
          <HealthPopover data={data} status={status} style={style} />
        </div>
      )}
    </div>
  );
}

export function PnLHealthCard({
  data,
  onRefresh,
  refreshing = false,
}: {
  data: PnLHealthData | null;
  onRefresh?: () => void;
  refreshing?: boolean;
}) {
  const status: PnLHealthStatus = data?.status || "stale";
  const style = styleFor(status);
  const breakdown = data?.breakdown as Record<string, number> | null;

  return (
    <div className={`rounded-xl border ${style.borderColor} ${style.bgColor} p-4`}>
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <span className={style.textColor}>{style.icon}</span>
          <h3 className={`text-sm font-semibold ${style.textColor}`}>
            P&L Health: {style.label}
          </h3>
        </div>
        {onRefresh && (
          <button
            onClick={onRefresh}
            disabled={refreshing}
            className="text-xs text-slate-400 hover:text-slate-200 disabled:opacity-40"
            title="Проверить сейчас"
          >
            {refreshing ? "Проверяется..." : "↻ Проверить"}
          </button>
        )}
      </div>

      {data && data.diff_rub !== null && (
        <div className="space-y-1.5 text-xs">
          <div className="flex justify-between text-slate-300">
            <span>Журнал:</span>
            <span className="font-mono tabular-nums">
              {formatCurrency(breakdown?.journal_pnl ?? null)}
            </span>
          </div>
          <div className="flex justify-between text-slate-300">
            <span>Cash truth:</span>
            <span className="font-mono tabular-nums">
              {formatCurrency(breakdown?.cash_pnl ?? null)}
            </span>
          </div>
          <div className={`flex justify-between font-semibold ${style.textColor} pt-1 border-t border-white/10`}>
            <span>Разница:</span>
            <span className="font-mono tabular-nums">
              {formatCurrency(data.diff_rub)} ({formatPct(data.diff_pct)})
            </span>
          </div>
        </div>
      )}

      <div className="mt-3 text-[10px] text-slate-500">
        Последняя проверка: {timeAgo(data?.checked_at ?? null)}
      </div>
    </div>
  );
}
