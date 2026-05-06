"use client";
/**
 * /review — Daily Review workflow.
 *
 * Каждый день: список сделок дня → быстрый комментарий по каждой →
 * общая рефлексия → намерение на завтра + рейтинг дня 1-5 ⭐.
 *
 * Stickiness фича: превращает «открыл раз в неделю» в «открыл каждый
 * вечер на 5 минут».
 */
import { useEffect, useMemo, useState } from "react";
import { Layers, ChevronLeft, ChevronRight, TrendingUp, TrendingDown, Save, Star } from "lucide-react";
import { AppShell } from "@/components/AppShell";
import { AnalysisPageHeader } from "@/components/analysis/AnalysisPageHeader";
import { DashboardSkeleton } from "@/components/Skeleton";
import { api } from "@/lib/apiClient";
import { useAuth } from "@/contexts/AuthContext";
import { useSettings } from "@/contexts/SettingsContext";

interface TradeMini {
  id: number;
  symbol: string;
  direction: string;
  pnl: number | null;
  entry_at: string;
  exit_at: string | null;
  setup_name: string | null;
  reflection: string;
}

interface ReviewData {
  date: string;
  reflection: string;
  intention: string;
  rating: number | null;
  trades: TradeMini[];
  summary: { total_trades: number; wins: number; losses: number; win_rate: number; total_pnl: number };
}

export default function ReviewPage() {
  const { user, isLoading: authLoading } = useAuth();
  const { formatCurrency } = useSettings();
  const [date, setDate] = useState<string>(() => new Date().toISOString().slice(0, 10));
  const [data, setData] = useState<ReviewData | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [savedAt, setSavedAt] = useState<number | null>(null);

  // Local form state — синхронизируется с data при загрузке
  const [reflection, setReflection] = useState("");
  const [intention, setIntention] = useState("");
  const [rating, setRating] = useState<number | null>(null);
  const [tradeReflections, setTradeReflections] = useState<Record<string, string>>({});

  useEffect(() => {
    if (!user) { setLoading(false); return; }
    setLoading(true);
    api.get<ReviewData>(`/review/?date=${date}`)
      .then((d) => {
        setData(d);
        setReflection(d.reflection);
        setIntention(d.intention);
        setRating(d.rating);
        const tr: Record<string, string> = {};
        for (const t of d.trades) tr[String(t.id)] = t.reflection || "";
        setTradeReflections(tr);
      })
      .catch(() => setData(null))
      .finally(() => setLoading(false));
  }, [user, date]);

  async function save() {
    setSaving(true);
    try {
      const updated = await api.post<ReviewData>("/review/", {
        body: {
          date,
          reflection,
          intention,
          rating,
          trade_reflections: tradeReflections,
        },
      });
      setData(updated);
      setSavedAt(Date.now());
      setTimeout(() => setSavedAt(null), 3000);
    } finally {
      setSaving(false);
    }
  }

  function shiftDate(days: number) {
    const d = new Date(date);
    d.setDate(d.getDate() + days);
    setDate(d.toISOString().slice(0, 10));
  }

  const dateLabel = useMemo(() => {
    const d = new Date(date);
    return d.toLocaleDateString("ru-RU", {
      weekday: "long", day: "2-digit", month: "long", year: "numeric",
    });
  }, [date]);

  if (authLoading) return <DashboardSkeleton />;

  return (
    <AppShell pageTitle="Daily Review">
      <div className="p-6 md:p-8 max-w-4xl mx-auto">
        <AnalysisPageHeader
          title="Daily Review"
          subtitle="5 минут вечером. Что сегодня сделал, чему научился, что планируешь завтра."
          Icon={Layers}
          accentColor="indigo"
        />

        {!user ? (
          <Empty />
        ) : (
          <>
            {/* Date navigator */}
            <div className="flex items-center justify-between mb-6 rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--surface-1)] p-3">
              <button onClick={() => shiftDate(-1)} className="btn-icon" aria-label="Предыдущий день">
                <ChevronLeft size={16} />
              </button>
              <div className="text-center">
                <div className="text-[15px] font-semibold capitalize">{dateLabel}</div>
                {data && (
                  <div className="text-[12px] mt-1">
                    {data.summary.total_trades > 0 ? (
                      <>
                        <span>{data.summary.total_trades} сделок · WR {data.summary.win_rate}% · </span>
                        <span className={data.summary.total_pnl >= 0 ? "text-[var(--success)] font-semibold" : "text-[var(--danger)] font-semibold"}>
                          {data.summary.total_pnl >= 0 ? "+" : ""}{formatCurrency(data.summary.total_pnl)}
                        </span>
                      </>
                    ) : (
                      <span className="text-[var(--text-tertiary)]">Сделок не было</span>
                    )}
                  </div>
                )}
              </div>
              <button onClick={() => shiftDate(1)} className="btn-icon" aria-label="Следующий день">
                <ChevronRight size={16} />
              </button>
            </div>

            {loading ? (
              <DashboardSkeleton />
            ) : (
              <div className="space-y-6">
                {/* Trades reflections */}
                {data && data.trades.length > 0 && (
                  <Section title="Сделки сегодня" subtitle="Опиши каждую кратко: что подтолкнуло войти, что подтолкнуло выйти, что сделал бы иначе.">
                    <div className="space-y-3">
                      {data.trades.map((t) => (
                        <TradeReflection
                          key={t.id}
                          trade={t}
                          value={tradeReflections[String(t.id)] || ""}
                          onChange={(v) => setTradeReflections({ ...tradeReflections, [String(t.id)]: v })}
                          formatCurrency={formatCurrency}
                        />
                      ))}
                    </div>
                  </Section>
                )}

                {/* Day reflection */}
                <Section title="Общий итог дня" subtitle="3-5 предложений: что было главное, какое было настроение, какие выводы.">
                  <textarea
                    value={reflection}
                    onChange={(e) => setReflection(e.target.value)}
                    rows={5}
                    placeholder="Сегодня ловил импульсные пробои на SBER. Один отработал на +2R, второй слил по тайт-стопу из-за резкого разворота. Урок: на пробоях после новостей ставить стоп шире..."
                    className="w-full rounded-[var(--radius-md)] border border-[var(--border)] bg-[var(--surface-1)] p-3 text-[14px] resize-none focus:outline-none focus:border-[var(--accent)] transition-colors"
                  />
                </Section>

                {/* Rating */}
                <Section title="Оценка дня" subtitle="Как ты сам оцениваешь свою торговлю сегодня (не по результату, а по качеству).">
                  <RatingPicker value={rating} onChange={setRating} />
                </Section>

                {/* Intention */}
                <Section title="Намерение на завтра" subtitle="Один-два конкретных тезиса. Что именно сделаешь иначе?">
                  <textarea
                    value={intention}
                    onChange={(e) => setIntention(e.target.value)}
                    rows={3}
                    placeholder="Не входить в сделки до 11:00 (проверял — лосю стат). Размер позиции не больше f/10 = 6%."
                    className="w-full rounded-[var(--radius-md)] border border-[var(--border)] bg-[var(--surface-1)] p-3 text-[14px] resize-none focus:outline-none focus:border-[var(--accent)] transition-colors"
                  />
                </Section>

                {/* Save button */}
                <div className="sticky bottom-4 flex justify-end gap-3 items-center">
                  {savedAt && (
                    <span className="text-[12px] text-[var(--success)] animate-fadeIn">Сохранено ✓</span>
                  )}
                  <button
                    onClick={save}
                    disabled={saving}
                    className="btn-primary disabled:opacity-60"
                  >
                    <Save size={14} />
                    {saving ? "Сохранение…" : "Сохранить review"}
                  </button>
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </AppShell>
  );
}

function TradeReflection({
  trade,
  value,
  onChange,
  formatCurrency,
}: {
  trade: TradeMini;
  value: string;
  onChange: (v: string) => void;
  formatCurrency: (n: number) => string;
}) {
  const pnl = trade.pnl ?? 0;
  const isWin = pnl > 0;
  const direction = trade.direction.toUpperCase();
  return (
    <div className="rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--surface-1)] p-4">
      <div className="flex items-center gap-2 mb-2.5">
        <span className="font-bold text-[14px]">{trade.symbol}</span>
        <span
          className={`text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-[var(--radius-pill)] ${
            direction === "LONG"
              ? "bg-[var(--success-soft)] text-[var(--success)]"
              : "bg-[var(--danger-soft)] text-[var(--danger)]"
          }`}
        >
          {direction}
        </span>
        {trade.setup_name && (
          <span className="text-[11px] text-[var(--text-tertiary)]">{trade.setup_name}</span>
        )}
        <span
          className={`ml-auto text-[14px] font-bold tabular-nums flex items-center gap-1 ${isWin ? "text-[var(--success)]" : "text-[var(--danger)]"}`}
        >
          {isWin ? <TrendingUp size={12} /> : <TrendingDown size={12} />}
          {pnl >= 0 ? "+" : ""}{formatCurrency(pnl)}
        </span>
      </div>
      <textarea
        value={value}
        onChange={(e) => onChange(e.target.value)}
        rows={2}
        placeholder="Почему вошёл? Почему вышел? Что бы изменил?"
        className="w-full rounded-[var(--radius-md)] border border-[var(--border)] bg-[var(--surface-2)] p-2.5 text-[13px] resize-none focus:outline-none focus:border-[var(--accent)] transition-colors"
      />
    </div>
  );
}

function RatingPicker({ value, onChange }: { value: number | null; onChange: (v: number) => void }) {
  return (
    <div className="flex items-center gap-2">
      {[1, 2, 3, 4, 5].map((n) => (
        <button
          key={n}
          type="button"
          onClick={() => onChange(n)}
          className="transition-transform hover:scale-110"
          aria-label={`Оценка ${n} из 5`}
        >
          <Star
            size={28}
            className={n <= (value ?? 0) ? "fill-[var(--warning)] text-[var(--warning)]" : "text-[var(--border-strong)]"}
          />
        </button>
      ))}
      {value !== null && (
        <span className="ml-3 text-[13px] text-[var(--text-secondary)]">
          {value === 5 ? "Отлично" : value === 4 ? "Хорошо" : value === 3 ? "Нормально" : value === 2 ? "Слабо" : "Плохо"}
        </span>
      )}
    </div>
  );
}

function Section({ title, subtitle, children }: { title: string; subtitle?: string; children: React.ReactNode }) {
  return (
    <div>
      <h3 className="text-[14px] font-semibold mb-1">{title}</h3>
      {subtitle && <p className="text-[12px] text-[var(--text-tertiary)] mb-3">{subtitle}</p>}
      {children}
    </div>
  );
}

function Empty() {
  return (
    <div className="rounded-[var(--radius-xl)] border border-[var(--border)] bg-[var(--surface-1)] p-10 text-center text-[14px] text-[var(--text-secondary)]">
      Войдите, чтобы вести daily review.
    </div>
  );
}
