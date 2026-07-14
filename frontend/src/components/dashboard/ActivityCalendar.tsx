'use client';

/**
 * Activity Calendar (PR 21) — heatmap дней текущего месяца с PnL.
 *
 * Каждая клетка — день. Цвет = daily PnL (зелёный/красный gradient).
 * Клик по дню переходит в /history с фильтром по дате.
 *
 * Источник данных: trades с exit_at в текущем месяце. Группируем по дню,
 * считаем sum(pnl). Это самая популярная фича индустрии 2023-2024 (TradeZella).
 */

import { useMemo } from 'react';
import { useRouter } from 'next/navigation';
import { parseApiDate } from '@/lib/dateUtils';
import { useSettings } from '@/contexts/SettingsContext';

interface Trade {
  id: number;
  pnl?: number | null;
  net_pnl?: number | null;
  exit_at?: string | null;
}

interface DayBucket {
  date: string; // YYYY-MM-DD
  dayOfMonth: number;
  dayOfWeek: number; // 0=Mon ... 6=Sun
  pnl: number;
  count: number;
}

interface Props {
  trades: Trade[];
  monthOffset?: number; // 0 = current month, -1 = previous, +1 = next
}

const MONTH_NAMES = [
  'Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь',
  'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь',
];
const WEEKDAYS = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс'];

function colorFor(pnl: number, maxAbs: number): string {
  if (pnl === 0) return 'bg-slate-800/40';
  const intensity = Math.min(1, Math.abs(pnl) / Math.max(maxAbs, 1));
  // Дискретные ступени (Tailwind classes для CSS-purge).
  const level = intensity > 0.66 ? 3 : intensity > 0.33 ? 2 : 1;
  if (pnl > 0) {
    return ['bg-green-500/20', 'bg-green-500/40', 'bg-green-500/60'][level - 1];
  }
  return ['bg-red-500/20', 'bg-red-500/40', 'bg-red-500/60'][level - 1];
}

export function ActivityCalendar({ trades, monthOffset = 0 }: Props) {
  const router = useRouter();
  const { formatCurrency } = useSettings();

  const { buckets, year, month, maxAbs, totalPnl, tradingDays } = useMemo(() => {
    const now = new Date();
    const cursor = new Date(now.getFullYear(), now.getMonth() + monthOffset, 1);
    const year = cursor.getFullYear();
    const month = cursor.getMonth();
    const daysInMonth = new Date(year, month + 1, 0).getDate();
    const firstDayOfMonth = new Date(year, month, 1);

    // Day-of-week shift: JS Sun=0..Sat=6 → у нас Mon=0..Sun=6.
    const firstDow = (firstDayOfMonth.getDay() + 6) % 7;

    const map = new Map<string, DayBucket>();
    for (let d = 1; d <= daysInMonth; d++) {
      const date = `${year}-${String(month + 1).padStart(2, '0')}-${String(d).padStart(2, '0')}`;
      const dow = (new Date(year, month, d).getDay() + 6) % 7;
      map.set(date, { date, dayOfMonth: d, dayOfWeek: dow, pnl: 0, count: 0 });
    }

    for (const t of trades) {
      if (!t.exit_at) continue;
      const dt = parseApiDate(t.exit_at);
      if (dt.getFullYear() !== year || dt.getMonth() !== month) continue;
      const date = `${year}-${String(month + 1).padStart(2, '0')}-${String(dt.getDate()).padStart(2, '0')}`;
      const bucket = map.get(date);
      if (!bucket) continue;
      const pnl = t.net_pnl ?? t.pnl ?? 0;
      bucket.pnl += pnl;
      bucket.count += 1;
    }

    const buckets = Array.from(map.values());
    let maxAbs = 0;
    let totalPnl = 0;
    let tradingDays = 0;
    for (const b of buckets) {
      maxAbs = Math.max(maxAbs, Math.abs(b.pnl));
      totalPnl += b.pnl;
      if (b.count > 0) tradingDays += 1;
    }
    return { buckets, year, month, firstDow, maxAbs, totalPnl, tradingDays };
  }, [trades, monthOffset]);

  const firstDow = useMemo(() => {
    const fd = new Date(year, month, 1).getDay();
    return (fd + 6) % 7;
  }, [year, month]);

  const handleClick = (b: DayBucket) => {
    if (b.count === 0) return;
    router.push(`/history?start_date=${b.date}&end_date=${b.date}`);
  };

  return (
    <div className="rounded-[var(--radius-xl)] border border-[var(--border)] bg-[var(--surface)] p-5">
      <div className="flex flex-wrap items-end justify-between mb-4 gap-3">
        <div>
          <h3 className="font-semibold text-base mb-0.5">Активность за {MONTH_NAMES[month]} {year}</h3>
          <p className="text-xs text-[var(--text-secondary)]">
            {tradingDays > 0
              ? `${tradingDays} торговых дн., итого ${totalPnl >= 0 ? '+' : ''}${formatCurrency(totalPnl)}`
              : 'В этом месяце нет закрытых сделок'}
          </p>
        </div>
      </div>

      <div className="grid grid-cols-7 gap-1.5">
        {WEEKDAYS.map((d) => (
          <div key={d} className="text-[10px] uppercase tracking-wider text-[var(--text-tertiary)] text-center mb-1">
            {d}
          </div>
        ))}
        {Array.from({ length: firstDow }).map((_, i) => (
          <div key={`empty-${i}`} />
        ))}
        {buckets.map((b) => {
          const colorCls = colorFor(b.pnl, maxAbs);
          const clickable = b.count > 0;
          return (
            <button
              key={b.date}
              type="button"
              onClick={() => handleClick(b)}
              disabled={!clickable}
              title={
                b.count > 0
                  ? `${b.date}: ${b.pnl >= 0 ? '+' : ''}${formatCurrency(b.pnl)} (${b.count} сделок)`
                  : `${b.date}: нет сделок`
              }
              className={`aspect-square rounded-md flex flex-col items-center justify-center text-[10px] font-mono transition ${colorCls} ${
                clickable
                  ? 'cursor-pointer hover:ring-1 hover:ring-[var(--accent)]'
                  : 'cursor-default opacity-50'
              }`}
            >
              <div className="text-[var(--foreground)] font-medium">{b.dayOfMonth}</div>
              {b.count > 0 && (
                <div
                  className="text-[8px] font-mono leading-none mt-0.5"
                  style={{ color: b.pnl >= 0 ? 'var(--success)' : 'var(--danger)' }}
                >
                  {b.pnl >= 0 ? '+' : ''}
                  {Math.abs(b.pnl) >= 1000
                    ? `${(b.pnl / 1000).toFixed(0)}к`
                    : b.pnl.toFixed(0)}
                </div>
              )}
            </button>
          );
        })}
      </div>
    </div>
  );
}
