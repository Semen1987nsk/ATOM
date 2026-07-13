"use client";
/**
 * AdvancedMetricsGrid — рендерит 14 продвинутых quant-метрик
 * (Ulcer, K-Ratio, Sterling, Omega, MAR, drawdown duration, hold-time
 * distribution, period breakdown, hour×dow heatmap, plan adherence,
 * mistake categories, commission ratio, trade frequency, RR realized).
 *
 * Берёт payload как есть с /stats/advanced — если поле null, показываем «—»
 * с tooltip-объяснением «недостаточно данных».
 */
import {
  Activity,
  TrendingUp,
  Gauge,
  Sigma,
  Calendar,
  Clock,
  AlertTriangle,
  Zap,
  Calculator,
  ArrowDownToLine,
  TrendingDown,
  Repeat,
} from "lucide-react";
import { useSettings } from "@/contexts/SettingsContext";

interface AdvancedMetricsResponse {
  total_trades: number;
  items: {
    ulcer_index?: number | null;
    k_ratio?: number | null;
    sterling_ratio?: number | null;
    omega_ratio?: number | null;
    mar_ratio?: number | null;
    cagr_pct?: number | null;
    drawdown_duration?: {
      max_dd_duration_trades: number;
      current_dd_duration_trades: number;
      longest_recovery_trades: number;
      underwater_pct: number;
    };
    hold_time_distribution?: Array<{
      bucket: string;
      count: number;
      win_rate: number;
      total_pnl: number;
      avg_pnl: number;
    }>;
    period_breakdown?: {
      weekly?: { best?: { period: string; pnl: number; trades: number }; worst?: { period: string; pnl: number; trades: number } };
      monthly?: { best?: { period: string; pnl: number; trades: number }; worst?: { period: string; pnl: number; trades: number } };
      yearly?: { best?: { period: string; pnl: number; trades: number }; worst?: { period: string; pnl: number; trades: number } };
    };
    hour_dow_heatmap?: Array<Array<{ count: number; win_rate: number; total_pnl: number }>>;
    plan_adherence?: { avg_score: number | null; good_pct: number; bad_pct: number; trades_rated: number };
    mistake_categories?: Array<{ tag: string; total_pnl: number; count: number; loss_count: number; loss_rate: number }>;
    commission_ratio_pct?: number | null;
    trade_frequency?: { per_week: number; per_month: number; avg_days_between: number | null; total_span_days?: number };
    rr_realized?: {
      avg_planned_rr: number | null;
      avg_realized_rr: number | null;
      delta: number | null;
      planned_count: number;
      realized_count: number;
    };
    psycho_correlations?: {
      mood?: Array<{ value: number; count: number; win_rate: number; avg_pnl: number; total_pnl: number }>;
      confidence?: Array<{ value: number; count: number; win_rate: number; avg_pnl: number; total_pnl: number }>;
      discipline?: Array<{ value: number; count: number; win_rate: number; avg_pnl: number; total_pnl: number }>;
    };
    news_event_stats?: {
      with_news: { count: number; win_rate: number; avg_pnl: number; total_pnl: number };
      without_news: { count: number; win_rate: number; avg_pnl: number; total_pnl: number };
      top_events: Array<{ event: string; count: number; win_rate: number; total_pnl: number }>;
    };
    exit_breakdown?: {
      by_reason: Array<{ reason: string; count: number; pct: number; win_rate: number; total_pnl: number }>;
      sl_set_pct: number;
      tp_set_pct: number;
    };
    r_distribution?: Array<{ bucket: string; count: number; pct: number; total_pnl: number; is_loss: boolean }>;
    tax_visibility?: {
      year: number;
      realized_ytd: number;
      trades_ytd: number;
      estimated_tax: number;
      after_tax: number;
      tax_rate_applied: number;
    };
  };
}

interface Props {
  data: AdvancedMetricsResponse | null;
  loading?: boolean;
}

export function AdvancedMetricsGrid({ data, loading }: Props) {
  const { formatCurrency } = useSettings();
  if (loading) {
    return <GridSkeleton />;
  }
  if (!data || data.total_trades === 0) {
    return (
      <EmptyMetricsState />
    );
  }

  const m = data.items;

  return (
    <div className="space-y-6">
      {/* Quant ratios */}
      <SectionHeader title="Quant-метрики" subtitle="Гладкость equity, экстремумы распределения, drawdown-боль." />
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
        <MetricTile
          Icon={Activity}
          label="Ulcer Index"
          value={fmt(m.ulcer_index, { suffix: "" })}
          hint="Чем ниже, тем глаже equity. < 5 — отлично."
          tone={ulcerTone(m.ulcer_index)}
        />
        <MetricTile
          Icon={TrendingUp}
          label="K-Ratio"
          value={fmt(m.k_ratio)}
          hint="Линейность роста. > 1 — стабильно."
          tone={genericTone(m.k_ratio, [0.5, 1, 2])}
        />
        <MetricTile
          Icon={Gauge}
          label="Sterling Ratio"
          value={fmt(m.sterling_ratio)}
          hint="Доходность относительно худших DD."
          tone={genericTone(m.sterling_ratio, [0.5, 1, 2])}
        />
        <MetricTile
          Icon={Sigma}
          label="Omega Ratio"
          value={fmt(m.omega_ratio)}
          hint="Прибыли над порогом / убытки под ним. > 1 = плюсовая."
          tone={genericTone(m.omega_ratio, [0.8, 1, 1.5])}
        />
        <MetricTile
          Icon={Calculator}
          label="MAR Ratio"
          value={fmt(m.mar_ratio)}
          hint="CAGR / Max DD. Hedge-fund стандарт."
          tone={genericTone(m.mar_ratio, [0.3, 0.7, 1.5])}
        />
        <MetricTile
          Icon={TrendingUp}
          label="CAGR"
          value={fmt(m.cagr_pct, { suffix: "%" })}
          hint="Среднегодовая доходность."
        />
      </div>

      {/* Drawdown duration */}
      <SectionHeader title="Длительность просадок" subtitle="Не «насколько глубоко», а «как долго» под водой." />
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <MetricTile
          Icon={ArrowDownToLine}
          label="Макс. DD длительность"
          value={`${m.drawdown_duration?.max_dd_duration_trades ?? 0} сделок`}
          hint="Самая долгая серия под пиком."
        />
        <MetricTile
          Icon={Clock}
          label="Текущая DD"
          value={`${m.drawdown_duration?.current_dd_duration_trades ?? 0} сделок`}
          hint="Сколько сделок с момента последнего пика."
          tone={(m.drawdown_duration?.current_dd_duration_trades ?? 0) > 0 ? "warning" : "success"}
        />
        <MetricTile
          Icon={Repeat}
          label="Самое долгое восстановление"
          value={`${m.drawdown_duration?.longest_recovery_trades ?? 0} сделок`}
          hint="Время на возврат к предыдущему пику в прошлом."
        />
        <MetricTile
          Icon={Activity}
          label="% времени в просадке"
          value={fmt(m.drawdown_duration?.underwater_pct, { suffix: "%" })}
          hint="Доля сделок ниже исторического пика."
          tone={genericTone(100 - (m.drawdown_duration?.underwater_pct ?? 50), [30, 50, 70])}
        />
      </div>

      {/* Hold-time distribution */}
      {m.hold_time_distribution && m.hold_time_distribution.some((b) => b.count > 0) && (
        <>
          <SectionHeader title="Распределение по длительности удержания" subtitle="В каких таймфреймах ты реально зарабатываешь." />
          <div className="rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--surface-1)] p-4">
            <div className="grid grid-cols-7 gap-2">
              {m.hold_time_distribution.map((b) => (
                <HoldTimeBar key={b.bucket} bucket={b} maxCount={Math.max(...m.hold_time_distribution!.map((x) => x.count))} />
              ))}
            </div>
          </div>
        </>
      )}

      {/* Period breakdown */}
      {m.period_breakdown && (
        <>
          <SectionHeader title="Лучшие и худшие периоды" subtitle="Когда система работает / когда её ломает." />
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <PeriodCard label="Неделя" data={m.period_breakdown.weekly} formatCurrency={formatCurrency} />
            <PeriodCard label="Месяц" data={m.period_breakdown.monthly} formatCurrency={formatCurrency} />
            <PeriodCard label="Год" data={m.period_breakdown.yearly} formatCurrency={formatCurrency} />
          </div>
        </>
      )}

      {/* Hour×DoW heatmap */}
      {m.hour_dow_heatmap && (
        <>
          <SectionHeader title="Тепловая карта: день × час" subtitle="В какое время твой win-rate выше." />
          <Heatmap matrix={m.hour_dow_heatmap} />
        </>
      )}

      {/* Behavioral */}
      <SectionHeader title="Поведение" subtitle="Дисциплина, повторяющиеся ошибки, частота торговли." />
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <PlanAdherenceCard data={m.plan_adherence} />
        <MistakesCard data={m.mistake_categories} formatCurrency={formatCurrency} />
      </div>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <MetricTile
          Icon={TrendingDown}
          label="Комиссии съедают"
          value={fmt(m.commission_ratio_pct, { suffix: "%" })}
          hint="Доля валовой прибыли, ушедшей в брокеру."
          tone={genericTone(20 - (m.commission_ratio_pct ?? 10), [5, 10, 15])}
        />
        <MetricTile
          Icon={Zap}
          label="Сделок в неделю"
          value={fmt(m.trade_frequency?.per_week)}
          hint={`В среднем ${m.trade_frequency?.avg_days_between ?? "—"} дн. между сделками.`}
        />
        <MetricTile
          Icon={Calendar}
          label="Сделок в месяц"
          value={fmt(m.trade_frequency?.per_month)}
          hint={`За весь период: ${m.trade_frequency?.total_span_days ?? "—"} дней.`}
        />
        <MetricTile
          Icon={Calculator}
          label="Realized vs Planned RR"
          value={
            m.rr_realized?.avg_realized_rr != null
              ? `${m.rr_realized.avg_realized_rr.toFixed(2)} R`
              : "—"
          }
          hint={
            m.rr_realized?.delta != null
              ? `Δ ${m.rr_realized.delta > 0 ? "+" : ""}${m.rr_realized.delta} к планируемому`
              : "Укажите SL/TP в сделках, чтобы увидеть."
          }
          tone={(m.rr_realized?.delta ?? 0) >= 0 ? "success" : "warning"}
        />
      </div>

      {/* R-Multiple distribution */}
      {m.r_distribution && m.r_distribution.some((b) => b.count > 0) && (
        <>
          <SectionHeader title="R-Multiple распределение" subtitle="Гистограмма выходов в R-множителях. Толстый правый хвост — хорошо." />
          <RDistributionChart data={m.r_distribution} />
        </>
      )}

      {/* Psycho correlations */}
      {m.psycho_correlations && (
        (m.psycho_correlations.mood?.length || m.psycho_correlations.confidence?.length || m.psycho_correlations.discipline?.length) ? (
          <>
            <SectionHeader title="Psycho-корреляции" subtitle="Как настроение, уверенность и дисциплина влияют на твой результат." />
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
              <PsychoCard label="Настроение" emoji="😐" data={m.psycho_correlations.mood} />
              <PsychoCard label="Уверенность" emoji="💪" data={m.psycho_correlations.confidence} />
              <PsychoCard label="Дисциплина" emoji="✅" data={m.psycho_correlations.discipline} />
            </div>
          </>
        ) : null
      )}

      {/* SL/TP / exit reasons */}
      {m.exit_breakdown && (
        <>
          <SectionHeader title="SL / TP и причины выхода" subtitle="Соблюдаешь ли ты свой план: где SL, где TP, а где руками." />
          <ExitBreakdownCard data={m.exit_breakdown} formatCurrency={formatCurrency} />
        </>
      )}

      {/* News event stats */}
      {m.news_event_stats && (m.news_event_stats.with_news.count > 0 || m.news_event_stats.without_news.count > 0) && (
        <>
          <SectionHeader title="Сделки рядом с новостями" subtitle="Помогает понять — отчётности и выступления ЦБ работают на тебя или против." />
          <NewsEventCard data={m.news_event_stats} formatCurrency={formatCurrency} />
        </>
      )}

      {/* Tax visibility */}
      {m.tax_visibility && (
        <>
          <SectionHeader title="Налоговая видимость" subtitle="Брокер удержит автоматически — но полезно знать заранее." />
          <TaxCard data={m.tax_visibility} formatCurrency={formatCurrency} />
        </>
      )}
    </div>
  );
}

// ──────────────────────────────────────────────────────────────────
//  Sub-components
// ──────────────────────────────────────────────────────────────────

type Tone = "neutral" | "success" | "warning" | "danger";

function MetricTile({
  Icon,
  label,
  value,
  hint,
  tone = "neutral",
}: {
  Icon: typeof Activity;
  label: string;
  value: string;
  hint?: string;
  tone?: Tone;
}) {
  const toneClass = {
    neutral: "text-[var(--foreground)]",
    success: "text-[var(--success)]",
    warning: "text-[var(--warning)]",
    danger: "text-[var(--danger)]",
  }[tone];

  return (
    <div
      className="rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--surface-1)] p-4 hover:border-[var(--border-strong)] transition-colors"
      title={hint}
    >
      <div className="flex items-center justify-between mb-2">
        <span className="text-[12px] font-medium text-[var(--text-secondary)]">{label}</span>
        <Icon size={14} className="text-[var(--text-tertiary)]" />
      </div>
      <div className={`text-[22px] font-bold tracking-tight ${toneClass}`}>{value}</div>
      {hint && <div className="mt-1.5 text-[11px] text-[var(--text-tertiary)] leading-snug">{hint}</div>}
    </div>
  );
}

function SectionHeader({ title, subtitle }: { title: string; subtitle?: string }) {
  return (
    <div className="mt-4">
      <h3 className="text-[15px] font-semibold tracking-tight">{title}</h3>
      {subtitle && <p className="text-[12px] text-[var(--text-tertiary)] mt-0.5">{subtitle}</p>}
    </div>
  );
}

function HoldTimeBar({
  bucket,
  maxCount,
}: {
  bucket: { bucket: string; count: number; win_rate: number; total_pnl: number };
  maxCount: number;
}) {
  const heightPct = maxCount > 0 ? (bucket.count / maxCount) * 100 : 0;
  const winColor =
    bucket.win_rate >= 60
      ? "bg-[var(--success)]"
      : bucket.win_rate >= 45
      ? "bg-[var(--accent)]"
      : "bg-[var(--danger)]";

  return (
    <div className="flex flex-col items-center gap-2">
      <div className="text-[11px] font-mono text-[var(--text-tertiary)]">{bucket.count}</div>
      <div className="w-full h-24 bg-[var(--surface-2)] rounded-md flex items-end overflow-hidden">
        <div className={`w-full ${winColor} transition-all`} style={{ height: `${heightPct}%` }} />
      </div>
      <div className="text-[10px] text-[var(--text-tertiary)] text-center leading-tight">
        {bucket.bucket}
      </div>
      <div className="text-[10px] font-medium text-[var(--text-secondary)]">
        WR {bucket.win_rate}%
      </div>
    </div>
  );
}

function PeriodCard({
  label,
  data,
  formatCurrency,
}: {
  label: string;
  data?: { best?: { period: string; pnl: number; trades: number }; worst?: { period: string; pnl: number; trades: number } };
  formatCurrency: (amount: number) => string;
}) {
  if (!data?.best && !data?.worst) {
    return (
      <div className="rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--surface-1)] p-4 text-[12px] text-[var(--text-tertiary)]">
        {label}: нет данных
      </div>
    );
  }
  return (
    <div className="rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--surface-1)] p-4">
      <div className="text-[12px] font-medium text-[var(--text-secondary)] mb-3">{label}</div>
      {data.best && (
        <div className="mb-2">
          <div className="text-[11px] text-[var(--text-tertiary)]">Лучший</div>
          <div className="flex items-baseline justify-between">
            <span className="text-[14px] font-mono font-medium">{data.best.period}</span>
            <span className="text-[14px] font-bold text-[var(--success)]">{formatCurrency(data.best.pnl)}</span>
          </div>
          <div className="text-[10px] text-[var(--text-tertiary)]">{data.best.trades} сделок</div>
        </div>
      )}
      {data.worst && (
        <div>
          <div className="text-[11px] text-[var(--text-tertiary)]">Худший</div>
          <div className="flex items-baseline justify-between">
            <span className="text-[14px] font-mono font-medium">{data.worst.period}</span>
            <span className="text-[14px] font-bold text-[var(--danger)]">{formatCurrency(data.worst.pnl)}</span>
          </div>
          <div className="text-[10px] text-[var(--text-tertiary)]">{data.worst.trades} сделок</div>
        </div>
      )}
    </div>
  );
}

function Heatmap({ matrix }: { matrix: Array<Array<{ count: number; win_rate: number; total_pnl: number }>> }) {
  const days = ["ПН", "ВТ", "СР", "ЧТ", "ПТ", "СБ", "ВС"];
  const maxPnl = Math.max(...matrix.flat().map((c) => Math.abs(c.total_pnl)), 1);

  return (
    <div className="rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--surface-1)] p-4 overflow-x-auto">
      <div className="inline-grid" style={{ gridTemplateColumns: "auto repeat(24, 1fr)" }}>
        <div />
        {Array.from({ length: 24 }).map((_, h) => (
          <div key={h} className="text-[9px] text-[var(--text-tertiary)] text-center pb-1">
            {h}
          </div>
        ))}
        {matrix.map((row, dow) => (
          <div key={dow} className="contents">
            <div className="text-[10px] font-medium text-[var(--text-tertiary)] pr-2 flex items-center">{days[dow]}</div>
            {row.map((cell, h) => {
              const intensity = Math.abs(cell.total_pnl) / maxPnl;
              const bg =
                cell.count === 0
                  ? "rgba(255,255,255,0.03)"
                  : cell.total_pnl >= 0
                  ? `rgba(34, 197, 94, ${0.15 + intensity * 0.6})`
                  : `rgba(239, 68, 68, ${0.15 + intensity * 0.6})`;
              return (
                <div
                  key={h}
                  className="h-5 m-[1px] rounded-sm"
                  style={{ background: bg }}
                  title={cell.count > 0 ? `${days[dow]} ${h}:00 — ${cell.count} сделок, WR ${cell.win_rate}%, PnL ${cell.total_pnl}` : "нет сделок"}
                />
              );
            })}
          </div>
        ))}
      </div>
    </div>
  );
}

function PlanAdherenceCard({ data }: { data?: { avg_score: number | null; good_pct: number; bad_pct: number; trades_rated: number } }) {
  if (!data || data.trades_rated === 0) {
    return (
      <div className="rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--surface-1)] p-4">
        <div className="text-[12px] font-medium text-[var(--text-secondary)] mb-1">Дисциплина</div>
        <div className="text-[12px] text-[var(--text-tertiary)]">
          Оценивайте поле «Следование плану» при добавлении сделок — здесь появится статистика.
        </div>
      </div>
    );
  }
  return (
    <div className="rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--surface-1)] p-4">
      <div className="text-[12px] font-medium text-[var(--text-secondary)] mb-2">Дисциплина (по {data.trades_rated} сделкам)</div>
      <div className="flex items-baseline gap-3 mb-3">
        <span className="text-[28px] font-bold tracking-tight">{data.avg_score?.toFixed(2)}</span>
        <span className="text-[12px] text-[var(--text-tertiary)]">/ 5</span>
      </div>
      <div className="space-y-2">
        <BarRow label="Идеально / Следовал" pct={data.good_pct} tone="success" />
        <BarRow label="Нарушил" pct={data.bad_pct} tone="danger" />
      </div>
    </div>
  );
}

function MistakesCard({
  data,
  formatCurrency,
}: {
  data?: Array<{ tag: string; total_pnl: number; count: number; loss_count: number; loss_rate: number }>;
  formatCurrency: (amount: number) => string;
}) {
  if (!data || data.length === 0) {
    return (
      <div className="rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--surface-1)] p-4">
        <div className="text-[12px] font-medium text-[var(--text-secondary)] mb-1">Категории ошибок</div>
        <div className="text-[12px] text-[var(--text-tertiary)]">
          Тегируйте сделки (например «FOMO», «Догон», «Без стопа»), чтобы видеть свои паттерны.
        </div>
      </div>
    );
  }
  return (
    <div className="rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--surface-1)] p-4">
      <div className="text-[12px] font-medium text-[var(--text-secondary)] mb-3">Топ-{data.length} категорий ошибок</div>
      <div className="space-y-2">
        {data.map((m) => (
          <div key={m.tag} className="flex items-center justify-between gap-2">
            <div className="flex items-center gap-2 min-w-0 flex-1">
              <AlertTriangle size={12} className={m.total_pnl < 0 ? "text-[var(--danger)]" : "text-[var(--text-tertiary)]"} />
              <span className="text-[13px] font-medium truncate">{m.tag}</span>
              <span className="text-[10px] text-[var(--text-tertiary)] flex-shrink-0">
                {m.loss_count}/{m.count} убыт.
              </span>
            </div>
            <span className={`text-[13px] font-mono font-semibold ${m.total_pnl < 0 ? "text-[var(--danger)]" : "text-[var(--success)]"}`}>
              {m.total_pnl >= 0 ? "+" : ""}{formatCurrency(m.total_pnl)}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

function BarRow({ label, pct, tone }: { label: string; pct: number; tone: "success" | "danger" }) {
  const toneClass = tone === "success" ? "bg-[var(--success)]" : "bg-[var(--danger)]";
  return (
    <div>
      <div className="flex justify-between text-[11px] text-[var(--text-tertiary)] mb-0.5">
        <span>{label}</span>
        <span className="font-mono">{pct}%</span>
      </div>
      <div className="h-1.5 bg-[var(--surface-2)] rounded-full overflow-hidden">
        <div className={`h-full ${toneClass}`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

function GridSkeleton() {
  return (
    <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
      {Array.from({ length: 12 }).map((_, i) => (
        <div key={i} className="h-[100px] rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--surface-1)] animate-pulse" />
      ))}
    </div>
  );
}

function EmptyMetricsState() {
  return (
    <div className="rounded-[var(--radius-xl)] border border-[var(--border)] bg-[var(--surface-1)] p-10 text-center">
      <div className="w-12 h-12 mx-auto mb-3 rounded-full bg-[var(--surface-2)] flex items-center justify-center text-[var(--text-tertiary)]">
        <Sigma size={20} />
      </div>
      <p className="text-[14px] text-[var(--text-secondary)] max-w-sm mx-auto">
        Добавьте сделки — здесь появятся продвинутые quant-метрики (Ulcer Index, K-Ratio, тепловая карта и др.).
      </p>
    </div>
  );
}

// ──────────────────────────────────────────────────────────────────
//  Helpers
// ──────────────────────────────────────────────────────────────────

function fmt(v: number | null | undefined, opts: { suffix?: string } = {}): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  return `${typeof v === "number" ? v.toFixed(2) : v}${opts.suffix ?? ""}`;
}

function ulcerTone(v: number | null | undefined): Tone {
  if (v == null) return "neutral";
  if (v < 5) return "success";
  if (v < 10) return "neutral";
  if (v < 15) return "warning";
  return "danger";
}

function genericTone(v: number | null | undefined, thresholds: [number, number, number]): Tone {
  if (v == null) return "neutral";
  if (v < thresholds[0]) return "danger";
  if (v < thresholds[1]) return "warning";
  if (v < thresholds[2]) return "neutral";
  return "success";
}

// ──────────────────────────────────────────────────────────────────
//  Wave-4 sub-components: R-distribution, Psycho, Exit, News, Tax
// ──────────────────────────────────────────────────────────────────

function RDistributionChart({
  data,
}: {
  data: Array<{ bucket: string; count: number; pct: number; total_pnl: number; is_loss: boolean }>;
}) {
  const maxCount = Math.max(...data.map((b) => b.count), 1);
  return (
    <div className="rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--surface-1)] p-4">
      <div className="grid grid-cols-8 gap-2">
        {data.map((b) => {
          const height = maxCount > 0 ? (b.count / maxCount) * 100 : 0;
          const color = b.is_loss
            ? `rgba(239, 68, 68, ${0.4 + (b.count / maxCount) * 0.5})`
            : `rgba(34, 197, 94, ${0.4 + (b.count / maxCount) * 0.5})`;
          return (
            <div key={b.bucket} className="flex flex-col items-center gap-1.5">
              <div className="text-[11px] font-mono text-[var(--text-tertiary)]">{b.count}</div>
              <div className="w-full h-24 bg-[var(--surface-2)] rounded-md flex items-end overflow-hidden">
                <div
                  className="w-full transition-all"
                  style={{ height: `${height}%`, background: color }}
                />
              </div>
              <div className="text-[10px] text-[var(--text-tertiary)] text-center leading-tight">{b.bucket}</div>
              <div className="text-[10px] font-medium text-[var(--text-secondary)]">{b.pct}%</div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function PsychoCard({
  label,
  emoji,
  data,
}: {
  label: string;
  emoji: string;
  data?: Array<{ value: number; count: number; win_rate: number; avg_pnl: number }>;
}) {
  if (!data || data.length === 0) {
    return (
      <div className="rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--surface-1)] p-4">
        <div className="text-[12px] font-medium text-[var(--text-secondary)] mb-1">{label}</div>
        <div className="text-[12px] text-[var(--text-tertiary)]">Не оценивается в сделках.</div>
      </div>
    );
  }
  // Считаем разницу между лучшим и худшим
  const sorted = [...data].sort((a, b) => b.value - a.value);
  const best = sorted[0];
  const worst = sorted[sorted.length - 1];
  const wrDelta = best.win_rate - worst.win_rate;
  return (
    <div className="rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--surface-1)] p-4">
      <div className="text-[12px] font-medium text-[var(--text-secondary)] mb-3 flex items-center gap-1.5">
        <span>{emoji}</span>
        {label}
      </div>
      <div className="space-y-1.5">
        {data.map((b) => (
          <div key={b.value} className="flex items-center gap-2 text-[12px]">
            <div className="font-mono text-[var(--text-tertiary)] w-5">{b.value}/5</div>
            <div className="flex-1 h-1.5 bg-[var(--surface-2)] rounded-full overflow-hidden">
              <div
                className="h-full bg-[var(--accent)]"
                style={{ width: `${Math.min(b.win_rate, 100)}%` }}
              />
            </div>
            <div className="text-right tabular-nums w-20">
              <span className="font-medium">{b.win_rate}%</span>
              <span className="text-[10px] text-[var(--text-tertiary)] ml-1">·{b.count}</span>
            </div>
          </div>
        ))}
      </div>
      {wrDelta !== 0 && data.length >= 2 && (
        <div className={`mt-3 pt-3 border-t border-[var(--border)] text-[11px] ${wrDelta > 0 ? "text-[var(--success)]" : "text-[var(--danger)]"}`}>
          Δ WR между {best.value}/5 и {worst.value}/5: <strong>{wrDelta > 0 ? "+" : ""}{wrDelta.toFixed(1)}%</strong>
        </div>
      )}
    </div>
  );
}

function ExitBreakdownCard({
  data,
  formatCurrency,
}: {
  data: { by_reason: Array<{ reason: string; count: number; pct: number; win_rate: number; total_pnl: number }>; sl_set_pct: number; tp_set_pct: number };
  formatCurrency: (amount: number) => string;
}) {
  return (
    <div className="rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--surface-1)] p-4">
      <div className="grid grid-cols-2 gap-3 mb-4">
        <div className="rounded-[var(--radius-md)] bg-[var(--surface-2)] p-3">
          <div className="text-[11px] text-[var(--text-tertiary)] uppercase tracking-wider">SL установлен</div>
          <div className="text-[20px] font-bold mt-1 tabular-nums">{data.sl_set_pct}%</div>
          <div className="text-[11px] text-[var(--text-tertiary)] mt-0.5">от всех сделок</div>
        </div>
        <div className="rounded-[var(--radius-md)] bg-[var(--surface-2)] p-3">
          <div className="text-[11px] text-[var(--text-tertiary)] uppercase tracking-wider">TP установлен</div>
          <div className="text-[20px] font-bold mt-1 tabular-nums">{data.tp_set_pct}%</div>
          <div className="text-[11px] text-[var(--text-tertiary)] mt-0.5">от всех сделок</div>
        </div>
      </div>
      <div className="space-y-2">
        <div className="text-[11px] font-medium text-[var(--text-tertiary)] uppercase tracking-wider mb-1.5">Причины выхода</div>
        {data.by_reason.map((r) => (
          <div key={r.reason} className="flex items-center justify-between gap-2 text-[12px]">
            <span className="font-medium truncate flex-1">{r.reason}</span>
            <span className="text-[var(--text-tertiary)]">{r.count} ({r.pct}%)</span>
            <span className="text-[var(--text-tertiary)]">WR {r.win_rate}%</span>
            <span className={`font-mono font-semibold w-24 text-right ${r.total_pnl >= 0 ? "text-[var(--success)]" : "text-[var(--danger)]"}`}>
              {r.total_pnl >= 0 ? "+" : ""}{formatCurrency(r.total_pnl)}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

function NewsEventCard({
  data,
  formatCurrency,
}: {
  data: {
    with_news: { count: number; win_rate: number; avg_pnl: number; total_pnl: number };
    without_news: { count: number; win_rate: number; avg_pnl: number; total_pnl: number };
    top_events: Array<{ event: string; count: number; win_rate: number; total_pnl: number }>;
  };
  formatCurrency: (amount: number) => string;
}) {
  const wrDelta = data.with_news.win_rate - data.without_news.win_rate;
  const verdict =
    data.with_news.count === 0
      ? "Нет сделок с тегом новости — заполняй поле «Новостное событие» для статистики."
      : wrDelta > 5
      ? `Сделки в новостях имеют WR на ${wrDelta.toFixed(1)}% выше — хорошо ловишь движения.`
      : wrDelta < -5
      ? `Сделки в новостях имеют WR на ${Math.abs(wrDelta).toFixed(1)}% НИЖЕ — возможно стоит избегать.`
      : "Разница незначительная — новости не дают edge.";
  return (
    <div className="rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--surface-1)] p-4">
      <div className="grid grid-cols-2 gap-3 mb-3">
        <ExitMiniStat label="С новостями" stats={data.with_news} formatCurrency={formatCurrency} />
        <ExitMiniStat label="Без новостей" stats={data.without_news} formatCurrency={formatCurrency} />
      </div>
      <div className="text-[12px] text-[var(--text-secondary)] py-2">{verdict}</div>
      {data.top_events.length > 0 && (
        <div className="border-t border-[var(--border)] pt-3 mt-2 space-y-1.5">
          <div className="text-[11px] font-medium text-[var(--text-tertiary)] uppercase tracking-wider">Топ событий</div>
          {data.top_events.map((e) => (
            <div key={e.event} className="flex items-center justify-between gap-2 text-[12px]">
              <span className="font-medium truncate">{e.event}</span>
              <span className="text-[var(--text-tertiary)]">{e.count} · WR {e.win_rate}%</span>
              <span className={`font-mono font-semibold w-24 text-right ${e.total_pnl >= 0 ? "text-[var(--success)]" : "text-[var(--danger)]"}`}>
                {e.total_pnl >= 0 ? "+" : ""}{formatCurrency(e.total_pnl)}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function ExitMiniStat({
  label,
  stats,
  formatCurrency,
}: {
  label: string;
  stats: { count: number; win_rate: number; avg_pnl: number; total_pnl: number };
  formatCurrency: (amount: number) => string;
}) {
  return (
    <div className="rounded-[var(--radius-md)] bg-[var(--surface-2)] p-3">
      <div className="text-[11px] text-[var(--text-tertiary)] uppercase tracking-wider">{label}</div>
      <div className="text-[18px] font-bold mt-1 tabular-nums">{stats.count}</div>
      <div className="text-[11px] mt-0.5">
        <span className="text-[var(--text-secondary)]">WR </span>
        <span className="font-medium">{stats.win_rate}%</span>
        {" · "}
        <span className={`font-mono ${stats.total_pnl >= 0 ? "text-[var(--success)]" : "text-[var(--danger)]"}`}>
          {stats.total_pnl >= 0 ? "+" : ""}{formatCurrency(stats.total_pnl)}
        </span>
      </div>
    </div>
  );
}

function TaxCard({
  data,
  formatCurrency,
}: {
  data: {
    year: number;
    realized_ytd: number;
    trades_ytd: number;
    estimated_tax: number;
    after_tax: number;
    tax_rate_applied: number;
  };
  formatCurrency: (amount: number) => string;
}) {
  const isPositive = data.realized_ytd > 0;
  return (
    <div className="rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--surface-1)] p-4">
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        <div className="rounded-[var(--radius-md)] bg-[var(--surface-2)] p-3">
          <div className="text-[11px] text-[var(--text-tertiary)] uppercase tracking-wider">Реализовано в {data.year}</div>
          <div className={`text-[22px] font-bold mt-1 tabular-nums ${isPositive ? "text-[var(--success)]" : "text-[var(--danger)]"}`}>
            {data.realized_ytd >= 0 ? "+" : ""}{formatCurrency(data.realized_ytd)}
          </div>
          <div className="text-[11px] text-[var(--text-tertiary)] mt-0.5">{data.trades_ytd} сделок</div>
        </div>
        <div className="rounded-[var(--radius-md)] bg-[var(--surface-2)] p-3">
          <div className="text-[11px] text-[var(--text-tertiary)] uppercase tracking-wider">Удержит брокер</div>
          <div className="text-[22px] font-bold mt-1 tabular-nums text-[var(--warning)]">
            {formatCurrency(-Math.abs(data.estimated_tax))}
          </div>
          <div className="text-[11px] text-[var(--text-tertiary)] mt-0.5">по ставке {(data.tax_rate_applied * 100).toFixed(0)}%</div>
        </div>
        <div className="rounded-[var(--radius-md)] bg-[var(--accent-soft)] p-3">
          <div className="text-[11px] text-[var(--accent)] uppercase tracking-wider font-medium">После налога</div>
          <div className="text-[22px] font-bold mt-1 tabular-nums">
            {data.after_tax >= 0 ? "+" : ""}{formatCurrency(data.after_tax)}
          </div>
          <div className="text-[11px] text-[var(--text-tertiary)] mt-0.5">в карман</div>
        </div>
      </div>
      <div className="mt-3 text-[11px] text-[var(--text-tertiary)] leading-relaxed">
        Брокер автоматически удерживает НДФЛ при выводе средств. Сальдирование убытков между брокерами — только через 3-НДФЛ.
      </div>
    </div>
  );
}
