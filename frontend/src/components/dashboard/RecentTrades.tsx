'use client';

/**
 * Recent Trades (PR 21) — последние 5 закрытых сделок на дашборде.
 *
 * Стандарт индустрии: Tradervue, TraderSync, TradeZella, Edgewonk все
 * имеют этот виджет. Помогает trader'у быстро увидеть «что я наделал
 * сегодня/вчера», без перехода в полный журнал.
 *
 * Клик → переход в /history (TODO: с фильтром по trade id когда сделаем).
 */

import { useMemo } from 'react';
import Link from 'next/link';
import { ArrowRight, TrendingUp, TrendingDown } from 'lucide-react';

interface Trade {
  id: number;
  symbol: string;
  asset_name?: string | null;
  direction: string;
  entry_price: number;
  exit_price?: number | null;
  quantity: number;
  pnl?: number | null;
  net_pnl?: number | null;
  entry_at: string;
  exit_at?: string | null;
  holding_time_minutes?: number | null;
  instrument_type_v2?: string | null;
}

interface Props {
  trades: Trade[];
}

function formatHolding(minutes: number | null | undefined): string {
  if (minutes == null || minutes < 0) return '—';
  if (minutes < 60) return `${minutes}м`;
  if (minutes < 1440) {
    const h = Math.floor(minutes / 60);
    const m = minutes % 60;
    return m >= 5 ? `${h}ч ${m}м` : `${h}ч`;
  }
  const d = Math.floor(minutes / 1440);
  const h = Math.floor((minutes % 1440) / 60);
  return h > 0 ? `${d}д ${h}ч` : `${d}д`;
}

export function RecentTrades({ trades }: Props) {
  const recent = useMemo(() => {
    return trades
      .filter((t) => t.exit_at)
      .slice()
      .sort((a, b) => new Date(b.exit_at!).getTime() - new Date(a.exit_at!).getTime())
      .slice(0, 5);
  }, [trades]);

  return (
    <div className="rounded-[var(--radius-xl)] border border-[var(--border)] bg-[var(--surface)] p-5">
      <div className="flex items-center justify-between mb-3">
        <h3 className="font-semibold text-base">Последние сделки</h3>
        <Link
          href="/history"
          className="text-xs text-[var(--accent)] hover:underline inline-flex items-center gap-1"
        >
          Все <ArrowRight size={12} />
        </Link>
      </div>

      {recent.length === 0 && (
        <div className="text-sm text-[var(--text-secondary)] py-6 text-center">
          Нет закрытых сделок
        </div>
      )}

      {recent.length > 0 && (
        <div className="space-y-2">
          {recent.map((t) => {
            const pnl = t.net_pnl ?? t.pnl ?? 0;
            const isWin = pnl >= 0;
            const isLong = t.direction.toLowerCase() === 'long';
            return (
              <Link
                key={t.id}
                href={`/history`}
                className="flex items-center justify-between gap-3 px-3 py-2 rounded-lg hover:bg-[var(--surface-hover)] transition-colors no-underline"
              >
                <div className="flex items-center gap-2 min-w-0 flex-1">
                  {isLong ? (
                    <TrendingUp size={14} className="text-green-400/70 shrink-0" />
                  ) : (
                    <TrendingDown size={14} className="text-red-400/70 shrink-0" />
                  )}
                  <div className="min-w-0">
                    <div className="text-sm font-mono font-semibold truncate">
                      {t.symbol}
                    </div>
                    {t.asset_name && (
                      <div className="text-[11px] text-[var(--text-tertiary)] truncate">
                        {t.asset_name}
                      </div>
                    )}
                  </div>
                </div>
                <div className="flex items-center gap-3 text-xs shrink-0">
                  <span className="text-[var(--text-tertiary)] font-mono">
                    {formatHolding(t.holding_time_minutes)}
                  </span>
                  <span
                    className={`font-mono font-bold ${
                      isWin ? 'text-green-400' : 'text-red-400'
                    }`}
                  >
                    {isWin ? '+' : ''}
                    {pnl.toLocaleString('ru-RU', { maximumFractionDigits: 0 })} ₽
                  </span>
                </div>
              </Link>
            );
          })}
        </div>
      )}
    </div>
  );
}
