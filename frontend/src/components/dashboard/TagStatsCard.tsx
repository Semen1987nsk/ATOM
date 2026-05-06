'use client';

import { Tag } from 'lucide-react';
import { useLanguage } from '@/i18n/LanguageContext';
import { useSettings } from '@/contexts/SettingsContext';

interface TagStat {
  tag: string;
  pnl: number;
  win_rate: number;
  count: number;
}

interface TagStatsCardProps {
  tagStats: TagStat[];
}

export function TagStatsCard({ tagStats }: TagStatsCardProps) {
  const { t } = useLanguage();
  const { formatCurrency } = useSettings();

  return (
    <div className="cyber-card p-6 flex flex-col gap-4">
      {/* Header */}
      <div className="flex items-center gap-2.5">
        <div className="w-8 h-8 rounded-[var(--radius-md)] bg-[var(--accent-soft)] text-[var(--accent)] flex items-center justify-center">
          <Tag size={16} />
        </div>
        <h3 className="text-base font-semibold flex-1">{t.tagStats.title}</h3>
        <span className="badge badge-neutral">{tagStats?.length || 0}</span>
      </div>

      {/* Body */}
      {tagStats.length === 0 ? (
        <div className="empty-state py-6">
          <div className="empty-state-icon">
            <Tag size={20} />
          </div>
          <p className="text-[13px] text-[var(--text-tertiary)]">{t.tagStats.noTags}</p>
        </div>
      ) : (
        <ul className="flex flex-col gap-1 list-none p-0 max-h-[420px] overflow-y-auto scrollbar-thin -mx-2">
          {tagStats.map((item) => {
            const positive = Number(item.pnl) >= 0;
            const goodWinRate = Number(item.win_rate) >= 50;
            return (
              <li
                key={item.tag}
                className="flex items-center justify-between gap-3 px-2 py-2 rounded-[var(--radius-md)] hover:bg-[var(--surface-hover)] transition-colors"
              >
                <div className="min-w-0 flex-1">
                  <div className="text-[13px] font-medium text-[var(--foreground)] truncate">
                    <span className="text-[var(--text-tertiary)]">#</span>
                    {item.tag}
                  </div>
                  <div className="text-[11px] text-[var(--text-tertiary)]">
                    {item.count} {item.count === 1 ? 'сделка' : 'сделок'}
                  </div>
                </div>
                <div className="text-right flex-shrink-0">
                  <div
                    className={`text-[13px] font-semibold tabular-nums ${
                      positive ? 'text-[var(--success)]' : 'text-[var(--danger)]'
                    }`}
                  >
                    {positive ? '+' : ''}
                    {formatCurrency(Number(item.pnl))}
                  </div>
                  <div className="text-[11px] text-[var(--text-tertiary)] flex items-center gap-1.5 justify-end">
                    <span
                      className={`w-1.5 h-1.5 rounded-full ${
                        goodWinRate ? 'bg-[var(--success)]' : 'bg-[var(--danger)]'
                      }`}
                    />
                    {item.win_rate}% WR
                  </div>
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
