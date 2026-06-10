"use client";
/**
 * /analysis/calendar — Calendar P&L heatmap.
 *
 * Месячный grid 7×N с цветными ячейками: зелёный = плюс, красный = минус.
 * Интенсивность цвета пропорциональна |PnL| относительно max-дневного.
 * Tooltip показывает PnL, кол-во сделок, win-rate.
 */
import { useEffect, useMemo, useState } from "react";
import { CalendarDays, ChevronLeft, ChevronRight } from "lucide-react";
import { AppShell } from "@/components/AppShell";
import { AnalysisPageHeader } from "@/components/analysis/AnalysisPageHeader";
import { DashboardSkeleton } from "@/components/Skeleton";
import { api, ApiError } from "@/lib/apiClient";
import { useAuth } from "@/contexts/AuthContext";
import { useSettings } from "@/contexts/SettingsContext";
import { DataError } from "@/components/ui/DataError";

interface DayPnL {
  date: string;
  pnl: number;
  trades_count: number;
  win_rate: number;
}

interface CalendarResponse {
  total_trades: number;
  days: DayPnL[];
}

const WEEKDAYS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"];
const MONTH_NAMES = [
  "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
  "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь",
];

export default function CalendarPage() {
  const { user, isLoading: authLoading } = useAuth();
  const { formatCurrency } = useSettings();
  const [data, setData] = useState<CalendarResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<ApiError | Error | null>(null);
  // FE-02: refetchKey-bump = re-trigger useEffect для retry-кнопки.
  const [refetchKey, setRefetchKey] = useState(0);

  useEffect(() => {
    if (!user) { setLoading(false); return; }
    setLoading(true);
    setError(null);
    let cancelled = false;
    api.get<CalendarResponse>("/stats/calendar")
      .then((d) => { if (!cancelled) setData(d); })
      .catch((e) => { if (!cancelled) { setData(null); setError(e as ApiError | Error); } })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [user, refetchKey]);

  const retry = () => setRefetchKey((k) => k + 1);

  // Группируем дни по «год-месяц» для рендера месячных сеток
  const monthsData = useMemo(() => {
    if (!data?.days) return [];
    const grouped: Record<string, DayPnL[]> = {};
    for (const day of data.days) {
      const key = day.date.slice(0, 7); // 'YYYY-MM'
      if (!grouped[key]) grouped[key] = [];
      grouped[key].push(day);
    }
    const result = Object.entries(grouped)
      .sort(([a], [b]) => b.localeCompare(a)) // по убыванию (свежие сверху)
      .map(([yearMonth, days]) => {
        const [y, m] = yearMonth.split("-").map(Number);
        const pnl = days.reduce((s, d) => s + d.pnl, 0);
        const trades = days.reduce((s, d) => s + d.trades_count, 0);
        return { yearMonth, year: y, month: m - 1, days, pnl, trades };
      });

    // BUG-006: гарантируем текущий месяц в navigator (даже без закрытых сделок).
    // Иначе при открытой позиции в текущем месяце календарь «застревает» на
    // последнем месяце с закрытыми сделками (март), а «Следующий месяц» disabled.
    const now = new Date();
    const currentYM = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
    if (!result.some((m) => m.yearMonth === currentYM)) {
      result.unshift({
        yearMonth: currentYM,
        year: now.getFullYear(),
        month: now.getMonth(),
        days: [],
        pnl: 0,
        trades: 0,
      });
    }
    return result;
  }, [data]);

  const maxAbsPnl = useMemo(() => {
    if (!data?.days) return 1;
    return Math.max(...data.days.map((d) => Math.abs(d.pnl)), 1);
  }, [data]);

  const [monthIdx, setMonthIdx] = useState(0);

  // BUG-006: landing на текущем месяце если он есть в данных. Иначе остаёмся
  // на дефолтном 0 (самый свежий доступный месяц). Раньше всегда открывался
  // monthsData[0] — пользователь видел март вместо мая, потому что свежие
  // сделки могли быть open (без pnl, не попадают в /stats/calendar).
  useEffect(() => {
    if (monthsData.length === 0) return;
    const now = new Date();
    const currentYM = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
    const idx = monthsData.findIndex((m) => m.yearMonth === currentYM);
    if (idx >= 0) setMonthIdx(idx);
  }, [monthsData]);

  if (authLoading) return <DashboardSkeleton />;

  return (
    <AppShell pageTitle="Календарь P&L">
      <div className="p-6 md:p-8 max-w-5xl mx-auto">
        <AnalysisPageHeader
          title="Календарь P&L"
          subtitle="Каждый день — отдельная ячейка. Цвет показывает результат, насыщенность — масштаб."
          Icon={CalendarDays}
          accentColor="indigo"
        />

        {!user ? (
          <Empty text="Войдите, чтобы увидеть календарь сделок." />
        ) : error ? (
          <DataError error={error} onRetry={retry} />
        ) : loading ? (
          <DashboardSkeleton />
        ) : !data || data.total_trades === 0 ? (
          <Empty text="Сделок пока нет — добавьте первую и календарь оживёт." />
        ) : monthsData.length === 0 ? (
          <Empty text="Нет данных для отображения." />
        ) : (
          <>
            {/* Month navigator */}
            <div className="flex items-center justify-between mb-4">
              <button
                onClick={() => setMonthIdx((i) => Math.min(i + 1, monthsData.length - 1))}
                disabled={monthIdx >= monthsData.length - 1}
                className="btn-icon disabled:opacity-30"
                aria-label="Предыдущий месяц"
              >
                <ChevronLeft size={16} />
              </button>
              <div className="text-center">
                <div className="text-[18px] font-semibold tracking-tight">
                  {MONTH_NAMES[monthsData[monthIdx].month]} {monthsData[monthIdx].year}
                </div>
                <div className="text-[12px] text-[var(--text-tertiary)] mt-0.5">
                  <span
                    className={
                      monthsData[monthIdx].pnl >= 0
                        ? "text-[var(--success)] font-semibold"
                        : "text-[var(--danger)] font-semibold"
                    }
                  >
                    {monthsData[monthIdx].pnl >= 0 ? "+" : ""}{formatCurrency(monthsData[monthIdx].pnl)}
                  </span>
                  {" · "}
                  {monthsData[monthIdx].trades} сделок
                </div>
              </div>
              <button
                onClick={() => setMonthIdx((i) => Math.max(i - 1, 0))}
                disabled={monthIdx <= 0}
                className="btn-icon disabled:opacity-30"
                aria-label="Следующий месяц"
              >
                <ChevronRight size={16} />
              </button>
            </div>

            {/* Calendar grid for current month */}
            <CalendarGrid
              year={monthsData[monthIdx].year}
              month={monthsData[monthIdx].month}
              days={monthsData[monthIdx].days}
              maxAbs={maxAbsPnl}
              formatCurrency={formatCurrency}
            />

            {/* Legend */}
            <div className="mt-6 flex items-center justify-center gap-4 text-[11px] text-[var(--text-tertiary)]">
              <div className="flex items-center gap-1.5">
                <div className="w-3 h-3 rounded" style={{ background: "rgba(34,197,94,0.7)" }} />
                Прибыльный день
              </div>
              <div className="flex items-center gap-1.5">
                <div className="w-3 h-3 rounded" style={{ background: "rgba(239,68,68,0.7)" }} />
                Убыточный день
              </div>
              <div className="flex items-center gap-1.5">
                <div className="w-3 h-3 rounded bg-[var(--surface-2)]" />
                Без сделок
              </div>
            </div>
          </>
        )}
      </div>
    </AppShell>
  );
}

function CalendarGrid({
  year,
  month,
  days,
  maxAbs,
  formatCurrency,
}: {
  year: number;
  month: number; // 0-11
  days: DayPnL[];
  maxAbs: number;
  formatCurrency: (n: number) => string;
}) {
  // ISO weekday: 0=ПН ... 6=ВС, getDay returns 0=ВС ... 6=СБ
  const firstDay = new Date(year, month, 1);
  const isoFirstDay = (firstDay.getDay() + 6) % 7; // shift to ПН=0
  const daysInMonth = new Date(year, month + 1, 0).getDate();
  const byDate: Record<string, DayPnL> = {};
  for (const d of days) byDate[d.date] = d;

  // Total cells = leading blanks + days + trailing blanks (to multiple of 7)
  const cells: Array<{ date?: string; day?: number; data?: DayPnL }> = [];
  for (let i = 0; i < isoFirstDay; i++) cells.push({});
  for (let d = 1; d <= daysInMonth; d++) {
    const dateStr = `${year}-${String(month + 1).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
    cells.push({ date: dateStr, day: d, data: byDate[dateStr] });
  }
  while (cells.length % 7 !== 0) cells.push({});

  return (
    <div className="rounded-[var(--radius-xl)] border border-[var(--border)] bg-[var(--surface-1)] p-4 md:p-6">
      {/* Weekday labels */}
      <div className="grid grid-cols-7 gap-2 mb-2">
        {WEEKDAYS.map((w) => (
          <div key={w} className="text-[11px] font-medium text-[var(--text-tertiary)] text-center">
            {w}
          </div>
        ))}
      </div>

      {/* Day cells */}
      <div className="grid grid-cols-7 gap-2">
        {cells.map((cell, idx) => {
          if (!cell.day) {
            return <div key={`blank-${idx}`} className="aspect-square" />;
          }
          const d = cell.data;
          const intensity = d ? Math.abs(d.pnl) / maxAbs : 0;
          const bg = !d
            ? "var(--surface-2)"
            : d.pnl >= 0
            ? `rgba(34, 197, 94, ${0.18 + intensity * 0.65})`
            : `rgba(239, 68, 68, ${0.18 + intensity * 0.65})`;
          const textColor = d ? "white" : "var(--text-tertiary)";

          return (
            <div
              key={cell.date}
              className="aspect-square rounded-md p-1.5 flex flex-col text-[11px] cursor-default transition-transform hover:scale-105"
              style={{ background: bg, color: textColor }}
              title={
                d
                  ? `${cell.date}: ${d.pnl >= 0 ? "+" : ""}${formatCurrency(d.pnl)} · ${d.trades_count} сд. · WR ${d.win_rate}%`
                  : `${cell.date}: нет сделок`
              }
            >
              <div className="font-semibold tabular-nums">{cell.day}</div>
              {d && (
                <div className="mt-auto text-[10px] font-mono leading-none">
                  {d.pnl >= 0 ? "+" : ""}
                  {compactNumber(d.pnl)}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function Empty({ text }: { text: string }) {
  return (
    <div className="rounded-[var(--radius-xl)] border border-[var(--border)] bg-[var(--surface-1)] p-10 text-center">
      <div className="w-12 h-12 mx-auto mb-3 rounded-full bg-[var(--surface-2)] flex items-center justify-center text-[var(--text-tertiary)]">
        <CalendarDays size={20} />
      </div>
      <p className="text-[14px] text-[var(--text-secondary)] max-w-sm mx-auto">{text}</p>
    </div>
  );
}

function compactNumber(v: number): string {
  if (Math.abs(v) >= 1_000_000) return `${(v / 1_000_000).toFixed(1)}M`;
  if (Math.abs(v) >= 1_000) return `${(v / 1_000).toFixed(0)}K`;
  return v.toFixed(0);
}
