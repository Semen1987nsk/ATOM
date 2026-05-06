"use client";
/**
 * /analysis/setups — per-setup deep-dive.
 *
 * Раньше TagStatsCard показывала только теги. Setups — это отдельная
 * сущность (стратегии: «Пробой», «Откат к уровню», ...). Эта страница
 * даёт полный разбор каждого сетапа с mini equity-curve, qual-score, R.
 */
import { useEffect, useState } from "react";
import { Layers, TrendingUp, TrendingDown } from "lucide-react";
import { ResponsiveContainer, AreaChart, Area, YAxis } from "recharts";
import { AppShell } from "@/components/AppShell";
import { AnalysisPageHeader } from "@/components/analysis/AnalysisPageHeader";
import { DashboardSkeleton } from "@/components/Skeleton";
import { api } from "@/lib/apiClient";
import { useAuth } from "@/contexts/AuthContext";
import { useSettings } from "@/contexts/SettingsContext";

interface SetupStats {
  setup: string;
  trades_count: number;
  wins: number;
  losses: number;
  win_rate: number;
  total_pnl: number;
  avg_pnl: number;
  avg_r: number | null;
  quality_score: number;
  equity_curve: Array<{ date: string | null; balance: number }>;
  best_trade: number;
  worst_trade: number;
}

interface SetupsResponse {
  total_trades: number;
  setups: SetupStats[];
}

export default function SetupsPage() {
  const { user, isLoading: authLoading } = useAuth();
  const { formatCurrency } = useSettings();
  const [data, setData] = useState<SetupsResponse | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!user) { setLoading(false); return; }
    setLoading(true);
    api.get<SetupsResponse>("/stats/setups")
      .then(setData)
      .catch(() => setData(null))
      .finally(() => setLoading(false));
  }, [user]);

  if (authLoading) return <DashboardSkeleton />;

  return (
    <AppShell pageTitle="Сетапы">
      <div className="p-6 md:p-8 max-w-6xl mx-auto">
        <AnalysisPageHeader
          title="Сетапы и стратегии"
          subtitle="Какие подходы реально приносят деньги, а какие сливают."
          Icon={Layers}
          accentColor="emerald"
        />

        {!user ? (
          <Empty text="Войдите, чтобы увидеть разбор сетапов." />
        ) : loading ? (
          <DashboardSkeleton />
        ) : !data || data.setups.length === 0 ? (
          <Empty text="Заполняйте поле «Сетап / стратегия» при добавлении сделок — здесь появится их рейтинг." />
        ) : (
          <div className="space-y-3">
            {data.setups.map((s) => (
              <SetupCard key={s.setup} setup={s} formatCurrency={formatCurrency} />
            ))}
          </div>
        )}
      </div>
    </AppShell>
  );
}

function SetupCard({ setup, formatCurrency }: { setup: SetupStats; formatCurrency: (n: number) => string }) {
  const isPositive = setup.total_pnl >= 0;
  const lineColor = isPositive ? "var(--success)" : "var(--danger)";
  const qualityTone =
    setup.quality_score >= 70 ? "success" : setup.quality_score >= 50 ? "warning" : "danger";
  const qualityLabel =
    setup.quality_score >= 70 ? "Отлично" : setup.quality_score >= 50 ? "Среднее" : "Слабо";

  return (
    <div className="rounded-[var(--radius-xl)] border border-[var(--border)] bg-[var(--surface-1)] p-5 hover:border-[var(--border-strong)] transition-colors">
      <div className="grid grid-cols-1 lg:grid-cols-[1fr_220px] gap-5">
        {/* Left: name + metrics */}
        <div>
          <div className="flex items-baseline gap-3 mb-3 flex-wrap">
            <h3 className="text-[16px] font-semibold tracking-tight">{setup.setup}</h3>
            <span className="text-[12px] text-[var(--text-tertiary)]">
              {setup.trades_count} сделок · {setup.wins}W / {setup.losses}L
            </span>
            <span
              className={`text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-[var(--radius-pill)] ${
                qualityTone === "success"
                  ? "bg-[var(--success-soft)] text-[var(--success)]"
                  : qualityTone === "warning"
                  ? "bg-[var(--warning-soft)] text-[var(--warning)]"
                  : "bg-[var(--danger-soft)] text-[var(--danger)]"
              }`}
            >
              {qualityLabel} · {setup.quality_score}/100
            </span>
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <Metric
              label="Total PnL"
              value={`${setup.total_pnl >= 0 ? "+" : ""}${formatCurrency(setup.total_pnl)}`}
              tone={isPositive ? "success" : "danger"}
              Icon={isPositive ? TrendingUp : TrendingDown}
            />
            <Metric label="Win Rate" value={`${setup.win_rate}%`} />
            <Metric
              label="Avg R"
              value={setup.avg_r != null ? `${setup.avg_r > 0 ? "+" : ""}${setup.avg_r}R` : "—"}
              tone={(setup.avg_r ?? 0) > 0 ? "success" : (setup.avg_r ?? 0) < 0 ? "danger" : "neutral"}
            />
            <Metric label="Avg PnL" value={formatCurrency(setup.avg_pnl)} />
          </div>

          <div className="mt-3 flex items-center gap-4 text-[11px] text-[var(--text-tertiary)]">
            <span>
              Лучшая: <span className="font-mono text-[var(--success)]">+{formatCurrency(setup.best_trade)}</span>
            </span>
            <span>
              Худшая: <span className="font-mono text-[var(--danger)]">{formatCurrency(setup.worst_trade)}</span>
            </span>
          </div>
        </div>

        {/* Right: mini equity curve */}
        <div className="h-[100px] -mx-2">
          <div className="text-[10px] text-[var(--text-tertiary)] uppercase tracking-wider px-2 mb-1">Equity по сетапу</div>
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={setup.equity_curve} margin={{ top: 4, right: 4, left: 4, bottom: 0 }}>
              <defs>
                <linearGradient id={`grad-${setup.setup}`} x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={lineColor} stopOpacity={0.3} />
                  <stop offset="100%" stopColor={lineColor} stopOpacity={0} />
                </linearGradient>
              </defs>
              <YAxis hide />
              <Area
                type="monotone"
                dataKey="balance"
                stroke={lineColor}
                strokeWidth={2}
                fill={`url(#grad-${setup.setup})`}
                dot={false}
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  );
}

function Metric({
  label,
  value,
  tone = "neutral",
  Icon,
}: {
  label: string;
  value: string;
  tone?: "neutral" | "success" | "danger";
  Icon?: typeof TrendingUp;
}) {
  const toneClass = tone === "success" ? "text-[var(--success)]" : tone === "danger" ? "text-[var(--danger)]" : "";
  return (
    <div>
      <div className="text-[11px] text-[var(--text-tertiary)] uppercase tracking-wider mb-0.5">{label}</div>
      <div className={`text-[16px] font-bold tracking-tight tabular-nums flex items-center gap-1 ${toneClass}`}>
        {Icon && <Icon size={14} />}
        {value}
      </div>
    </div>
  );
}

function Empty({ text }: { text: string }) {
  return (
    <div className="rounded-[var(--radius-xl)] border border-[var(--border)] bg-[var(--surface-1)] p-10 text-center">
      <div className="w-12 h-12 mx-auto mb-3 rounded-full bg-[var(--surface-2)] flex items-center justify-center text-[var(--text-tertiary)]">
        <Layers size={20} />
      </div>
      <p className="text-[14px] text-[var(--text-secondary)] max-w-sm mx-auto">{text}</p>
    </div>
  );
}
