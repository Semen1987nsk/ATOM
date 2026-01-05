'use client';

import { Target } from 'lucide-react';
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
    <div className="cyber-card p-6 border-l-accent-secondary/30 relative overflow-hidden group">
      <div className="absolute -bottom-20 -left-20 w-40 h-40 bg-accent-secondary/10 rounded-full blur-3xl opacity-0 group-hover:opacity-100 transition-opacity duration-500" />
      
      <h2 className="text-sm font-mono uppercase mb-6 flex items-center gap-2 relative z-10">
        <Target size={16} className="text-accent-secondary" />
        {t.tagStats.title}
        <span className="ml-auto text-[10px] opacity-40">{tagStats?.length || 0} tags</span>
      </h2>
      <div className="space-y-3 relative z-10">
        {tagStats.length === 0 ? (
          <div className="empty-state py-8">
            <Target size={24} className="text-accent-secondary/30 mx-auto mb-2" />
            <p className="text-[10px] opacity-30 font-mono text-center">{t.tagStats.noTags}</p>
          </div>
        ) : (
          tagStats.map((item, index) => (
            <div 
              key={item.tag} 
              className="flex justify-between items-center border-b border-border pb-2 last:border-0 hover:bg-accent-secondary/5 p-2 -mx-2 rounded-lg transition-all cursor-default"
              style={{ animationDelay: `${index * 0.05}s` }}
            >
              <div>
                <div className="text-[10px] font-mono text-accent-secondary uppercase flex items-center gap-1">
                  <span className="opacity-30">#</span>{item.tag}
                </div>
                <div className="text-[9px] opacity-40">{item.count} trades</div>
              </div>
              <div className="text-right">
                <div className={`text-xs font-bold ${Number(item.pnl) >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                  {Number(item.pnl) >= 0 ? '+' : ''}{formatCurrency(Number(item.pnl))}
                </div>
                <div className="text-[9px] opacity-60 flex items-center gap-1 justify-end">
                  <div className={`w-1 h-1 rounded-full ${Number(item.win_rate) >= 50 ? 'bg-green-400' : 'bg-red-400'}`} />
                  {item.win_rate}% WR
                </div>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
