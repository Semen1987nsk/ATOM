'use client';

/**
 * Setup Performance (PR 21) — топ-5 setup'ов / тегов по PnL.
 *
 * Edgewonk считает это своим USP: без тегирования сетапов журнал = Excel.
 * Источник: `tag_stats` из /stats — массив { tag, pnl, win_rate, count }.
 *
 * Sort: by abs(pnl) DESC (показываем самые «движущие» — и top winners,
 * и top losers). Каждая строка кликабельна → переход в /history с фильтром.
 */

import { useMemo } from 'react';
import Link from 'next/link';
import { ArrowRight, Tag as TagIcon } from 'lucide-react';
import { useSettings } from '@/contexts/SettingsContext';

interface TagStat {
  tag: string;
  pnl: number;
  win_rate: number;
  count: number;
}

interface Props {
  tagStats: TagStat[] | null | undefined;
}

export function SetupPerformance({ tagStats }: Props) {
  const { formatCurrency } = useSettings();
  const top = useMemo(() => {
    if (!tagStats || tagStats.length === 0) return [];
    return tagStats
      .slice()
      .sort((a, b) => Math.abs(b.pnl) - Math.abs(a.pnl))
      .slice(0, 5);
  }, [tagStats]);

  return (
    <div className="rounded-[var(--radius-xl)] border border-[var(--border)] bg-[var(--surface)] p-5">
      <div className="flex items-center justify-between mb-3">
        <h3 className="font-semibold text-base">Топ-5 сетапов / тегов</h3>
        <Link
          href="/analysis/tags"
          className="text-xs text-[var(--accent)] hover:underline inline-flex items-center gap-1"
        >
          Все теги <ArrowRight size={12} />
        </Link>
      </div>

      {top.length === 0 && (
        <div className="text-sm text-[var(--text-secondary)] py-6 text-center">
          Поставьте теги к сделкам в Дневнике — здесь появится разбивка по
          сетапам.
        </div>
      )}

      {top.length > 0 && (
        <div className="space-y-1">
          {top.map((t) => {
            const isWin = t.pnl >= 0;
            return (
              <Link
                key={t.tag}
                href={`/history?tag=${encodeURIComponent(t.tag)}`}
                className="flex items-center justify-between gap-2 px-2 py-2 rounded-lg hover:bg-[var(--surface-hover)] no-underline"
              >
                <div className="flex items-center gap-2 min-w-0 flex-1">
                  <TagIcon size={12} className="text-[var(--text-tertiary)] shrink-0" />
                  <span className="text-sm font-medium truncate">{t.tag}</span>
                </div>
                <div className="flex items-center gap-3 text-xs shrink-0">
                  <span className="text-[var(--text-tertiary)] font-mono">
                    {t.count} ⊕
                  </span>
                  <span className="text-[var(--text-secondary)] font-mono">
                    {t.win_rate.toFixed(0)}%
                  </span>
                  <span
                    className={`font-mono font-bold w-20 text-right ${
                      isWin ? 'text-green-400' : 'text-red-400'
                    }`}
                  >
                    {isWin ? '+' : ''}
                    {formatCurrency(t.pnl)}
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
