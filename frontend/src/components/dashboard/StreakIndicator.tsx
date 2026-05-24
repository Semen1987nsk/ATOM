'use client';

/**
 * Streak Indicator (PR 21) — текущая серия побед/убытков + история последних 10.
 *
 * Поведенческий якорь: трейдер видит «вы сейчас на 5-дневной победной серии»
 * → меньше шансов сорваться. Или «3 убытка подряд» → пора остановиться.
 *
 * Источник: первые N closed trades в обратном хронологическом порядке.
 * Streak = текущая последовательность одного знака с самого начала.
 */

import { useMemo } from 'react';
import { Flame, Snowflake } from 'lucide-react';

interface Trade {
  pnl?: number | null;
  net_pnl?: number | null;
  exit_at?: string | null;
}

interface Props {
  trades: Trade[];
}

export function StreakIndicator({ trades }: Props) {
  const { streak, type, last10 } = useMemo(() => {
    // Берём закрытые сделки в порядке от свежих к старым.
    const closed = trades
      .filter((t) => t.exit_at)
      .slice()
      .sort((a, b) => new Date(b.exit_at!).getTime() - new Date(a.exit_at!).getTime());

    const last10 = closed.slice(0, 10).map((t) => t.net_pnl ?? t.pnl ?? 0);

    // Текущая серия с самой свежей сделки.
    let streak = 0;
    let type: 'win' | 'loss' | null = null;
    for (const t of closed) {
      const pnl = t.net_pnl ?? t.pnl ?? 0;
      const isWin = pnl > 0;
      if (type === null) {
        type = isWin ? 'win' : 'loss';
        streak = 1;
        continue;
      }
      if ((type === 'win' && isWin) || (type === 'loss' && !isWin)) {
        streak += 1;
      } else {
        break;
      }
    }
    return { streak, type, last10 };
  }, [trades]);

  if (streak === 0 || type === null) {
    return (
      <div className="rounded-[var(--radius-xl)] border border-[var(--border)] bg-[var(--surface)] p-5">
        <div className="text-[10px] uppercase tracking-wider text-[var(--text-tertiary)] mb-2">
          Текущая серия
        </div>
        <div className="text-sm text-[var(--text-secondary)]">Нет закрытых сделок</div>
      </div>
    );
  }

  const isWin = type === 'win';
  return (
    <div className="rounded-[var(--radius-xl)] border border-[var(--border)] bg-[var(--surface)] p-5">
      <div className="text-[10px] uppercase tracking-wider text-[var(--text-tertiary)] mb-2">
        Текущая серия
      </div>
      <div className="flex items-baseline gap-2">
        {isWin ? (
          <Flame size={24} className="text-orange-400" />
        ) : (
          <Snowflake size={24} className="text-blue-400" />
        )}
        <div className={`text-3xl font-bold ${isWin ? 'text-green-400' : 'text-red-400'}`}>
          {streak}
        </div>
        <div className="text-sm text-[var(--text-secondary)]">
          {isWin ? 'побед(ы) подряд' : 'убытк(а/ов) подряд'}
        </div>
      </div>
      {/* Mini-история последних 10 — точки green/red */}
      {last10.length > 1 && (
        <div className="mt-3">
          <div className="text-[10px] text-[var(--text-tertiary)] mb-1">Последние 10:</div>
          <div className="flex gap-1">
            {last10.map((pnl, i) => (
              <span
                key={i}
                className={`w-3 h-3 rounded-sm ${
                  pnl > 0 ? 'bg-green-500/70' : 'bg-red-500/70'
                }`}
                title={`${pnl >= 0 ? '+' : ''}${pnl.toLocaleString('ru-RU', { maximumFractionDigits: 0 })} ₽`}
              />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
