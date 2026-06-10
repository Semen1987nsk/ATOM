'use client';

import React, { useState, useEffect } from 'react';
import { Calendar, Tag, Hash, ChevronDown, X, Filter, RotateCcw } from 'lucide-react';
import { useLanguage } from '@/i18n/LanguageContext';
import { useAuth } from '@/contexts/AuthContext';
import { api } from '@/lib/apiClient';

export type Period = 'all' | 'today' | 'week' | 'month' | '3months' | 'year' | 'custom';

interface TagInfo {
  tag: string;
  count: number;
  pnl: number;
  win_rate: number;
}

export interface Filters {
  period: Period;
  startDate?: string;
  endDate?: string;
  tag?: string;
  limit?: number;
}

interface FilterPanelProps {
  filters: Filters;
  onChange: (filters: Filters) => void;
}

const LIMIT_OPTIONS = [
  { value: undefined, label: 'all' },
  { value: 10, label: '10' },
  { value: 20, label: '20' },
  { value: 50, label: '50' },
  { value: 100, label: '100' },
];

export const FilterPanel: React.FC<FilterPanelProps> = ({ 
  filters, 
  onChange
}) => {
  const { t } = useLanguage();
  const { user } = useAuth();
  const [tags, setTags] = useState<TagInfo[]>([]);
  const [openDropdown, setOpenDropdown] = useState<'period' | 'tag' | 'limit' | null>(null);
  const [showCustomDate, setShowCustomDate] = useState(false);
  const [customStart, setCustomStart] = useState(filters.startDate || '');
  const [customEnd, setCustomEnd] = useState(filters.endDate || '');

  // Fetch available tags
  useEffect(() => {
    if (!user) return;
    const fetchTags = async () => {
      try {
        const data = await api.get<TagInfo[]>('/stats/tags/');
        setTags(data);
      } catch (e) {
        console.error('Failed to fetch tags:', e);
      }
    };
    fetchTags();
  }, [user]);

  const periods: { value: Period; label: string }[] = [
    { value: 'all', label: t.period?.all || 'Все время' },
    { value: 'today', label: t.period?.today || 'Сегодня' },
    { value: 'week', label: t.period?.week || '7 дней' },
    { value: 'month', label: t.period?.month || '30 дней' },
    { value: '3months', label: t.period?.['3months'] || '3 месяца' },
    { value: 'year', label: t.period?.year || 'Год' },
    { value: 'custom', label: t.period?.custom || 'Период' },
  ];

  const handlePeriodSelect = (period: Period) => {
    if (period === 'custom') {
      setShowCustomDate(true);
      setOpenDropdown(null);
    } else {
      onChange({ ...filters, period, startDate: undefined, endDate: undefined });
      setOpenDropdown(null);
    }
  };

  const handleCustomApply = () => {
    if (customStart) {
      onChange({ 
        ...filters, 
        period: 'custom', 
        startDate: customStart, 
        endDate: customEnd || undefined 
      });
      setShowCustomDate(false);
    }
  };

  const handleTagSelect = (tag?: string) => {
    onChange({ ...filters, tag });
    setOpenDropdown(null);
  };

  const handleLimitSelect = (limit?: number) => {
    onChange({ ...filters, limit });
    setOpenDropdown(null);
  };

  const handleReset = () => {
    onChange({ period: 'all', tag: undefined, limit: undefined, startDate: undefined, endDate: undefined });
    setCustomStart('');
    setCustomEnd('');
  };

  const hasActiveFilters = filters.period !== 'all' || filters.tag || filters.limit;

  const getPeriodLabel = () => {
    if (filters.period === 'custom' && filters.startDate) {
      return `${filters.startDate}${filters.endDate ? ' → ' + filters.endDate : ''}`;
    }
    return periods.find(p => p.value === filters.period)?.label || t.period?.all || 'Все';
  };

  const getTagLabel = () => {
    if (filters.tag) {
      const tagInfo = tags.find(t => t.tag === filters.tag);
      return tagInfo ? `#${tagInfo.tag} (${tagInfo.count})` : `#${filters.tag}`;
    }
    return t.filters?.allTags || 'Все теги';
  };

  const getLimitLabel = () => {
    if (filters.limit) {
      return `${t.filters?.last || 'Последние'} ${filters.limit}`;
    }
    return t.filters?.allTrades || 'Все сделки';
  };

  return (
    <div className="flex flex-wrap items-center gap-2">
      <div className="flex items-center gap-1 text-accent mr-2">
        <Filter size={14} />
        <span className="text-xs font-bold uppercase tracking-widest hidden sm:inline">
          {t.filters?.title || 'Фильтры'}
        </span>
      </div>

      {/* Period Selector */}
      <div className="relative">
        <button
          onClick={() => setOpenDropdown(openDropdown === 'period' ? null : 'period')}
          className={`flex items-center gap-2 bg-surface border px-3 py-2 rounded-none hover:bg-border transition-colors text-xs font-bold uppercase tracking-widest ${
            filters.period !== 'all' ? 'border-accent text-accent' : 'border-border'
          }`}
        >
          <Calendar size={14} />
          <span className="max-w-[120px] truncate">{getPeriodLabel()}</span>
          <ChevronDown size={12} className={`transition-transform ${openDropdown === 'period' ? 'rotate-180' : ''}`} />
        </button>

        {openDropdown === 'period' && (
          <div className="absolute top-full left-0 mt-1 bg-[#0d0d0d] border border-border z-50 min-w-[150px]">
            {periods.map((period) => (
              <button
                key={period.value}
                onClick={() => handlePeriodSelect(period.value)}
                className={`w-full text-left px-4 py-2 text-xs font-mono hover:bg-accent/10 transition-colors ${
                  filters.period === period.value ? 'text-accent bg-accent/5' : ''
                }`}
              >
                {period.label}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Tag Selector */}
      <div className="relative">
        <button
          onClick={() => setOpenDropdown(openDropdown === 'tag' ? null : 'tag')}
          className={`flex items-center gap-2 bg-surface border px-3 py-2 rounded-none hover:bg-border transition-colors text-xs font-bold uppercase tracking-widest ${
            filters.tag ? 'border-accent text-accent' : 'border-border'
          }`}
        >
          <Tag size={14} />
          <span className="max-w-[100px] truncate">{getTagLabel()}</span>
          <ChevronDown size={12} className={`transition-transform ${openDropdown === 'tag' ? 'rotate-180' : ''}`} />
        </button>

        {openDropdown === 'tag' && (
          <div className="absolute top-full left-0 mt-1 bg-[#0d0d0d] border border-border z-50 min-w-[180px] max-h-[300px] overflow-y-auto">
            <button
              onClick={() => handleTagSelect(undefined)}
              className={`w-full text-left px-4 py-2 text-xs font-mono hover:bg-accent/10 transition-colors ${
                !filters.tag ? 'text-accent bg-accent/5' : ''
              }`}
            >
              {t.filters?.allTags || 'Все теги'}
            </button>
            {tags.map((tag) => (
              <button
                key={tag.tag}
                onClick={() => handleTagSelect(tag.tag)}
                className={`w-full text-left px-4 py-2 text-xs font-mono hover:bg-accent/10 transition-colors flex justify-between items-center ${
                  filters.tag === tag.tag ? 'text-accent bg-accent/5' : ''
                }`}
              >
                <span>#{tag.tag}</span>
                <span className={`text-[10px] ${tag.pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                  {tag.count} • {tag.pnl >= 0 ? '+' : ''}{tag.pnl.toFixed(0)}
                </span>
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Limit Selector */}
      <div className="relative">
        <button
          onClick={() => setOpenDropdown(openDropdown === 'limit' ? null : 'limit')}
          className={`flex items-center gap-2 bg-surface border px-3 py-2 rounded-none hover:bg-border transition-colors text-xs font-bold uppercase tracking-widest ${
            filters.limit ? 'border-accent text-accent' : 'border-border'
          }`}
        >
          <Hash size={14} />
          <span>{getLimitLabel()}</span>
          <ChevronDown size={12} className={`transition-transform ${openDropdown === 'limit' ? 'rotate-180' : ''}`} />
        </button>

        {openDropdown === 'limit' && (
          <div className="absolute top-full left-0 mt-1 bg-[#0d0d0d] border border-border z-50 min-w-[120px]">
            {LIMIT_OPTIONS.map((opt) => (
              <button
                key={opt.label}
                onClick={() => handleLimitSelect(opt.value)}
                className={`w-full text-left px-4 py-2 text-xs font-mono hover:bg-accent/10 transition-colors ${
                  filters.limit === opt.value ? 'text-accent bg-accent/5' : ''
                }`}
              >
                {opt.value ? `${t.filters?.last || 'Последние'} ${opt.value}` : (t.filters?.allTrades || 'Все сделки')}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Reset Button */}
      {hasActiveFilters && (
        <button
          onClick={handleReset}
          className="flex items-center gap-1 px-3 py-2 text-xs text-red-400 hover:text-red-300 hover:bg-red-400/10 transition-colors"
          title={t.filters?.reset || 'Сбросить фильтры'}
        >
          <RotateCcw size={14} />
          <span className="hidden sm:inline">{t.filters?.reset || 'Сбросить'}</span>
        </button>
      )}

      {/* Custom Date Modal */}
      {showCustomDate && (
        <div className="fixed inset-0 bg-black/80 backdrop-blur-sm flex items-center justify-center z-50 animate-fadeIn">
          <div className="cyber-card w-full max-w-sm bg-[#0d0d0d] p-6 relative animate-scaleIn overflow-hidden">
            <button 
              onClick={() => setShowCustomDate(false)} 
              className="absolute top-4 right-4 opacity-50 hover:opacity-100 hover:text-accent transition-colors z-10"
            >
              <X size={20} />
            </button>
            
            <h3 className="text-lg font-bold mb-4 flex items-center gap-2 relative z-10">
              <Calendar size={18} className="text-accent" />
              {t.period?.custom || 'Период'}
            </h3>
            
            <div className="space-y-4 relative z-10">
              <div>
                <label className="block text-[10px] font-mono uppercase opacity-50 mb-1">
                  {t.filters?.startDate || 'Начало периода'}
                </label>
                <input
                  type="date"
                  value={customStart}
                  onChange={(e) => setCustomStart(e.target.value)}
                  className="input-cyber"
                />
              </div>
              <div>
                <label className="block text-[10px] font-mono uppercase opacity-50 mb-1">
                  {t.filters?.endDate || 'Конец периода'} ({t.filters?.optional || 'опционально'})
                </label>
                <input
                  type="date"
                  value={customEnd}
                  onChange={(e) => setCustomEnd(e.target.value)}
                  className="input-cyber"
                />
              </div>
              <button
                onClick={handleCustomApply}
                disabled={!customStart}
                className="btn-primary w-full justify-center disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {t.filters?.apply || 'Применить'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Close dropdown on outside click */}
      {openDropdown && (
        <div 
          className="fixed inset-0 z-40" 
          onClick={() => setOpenDropdown(null)}
        />
      )}
    </div>
  );
};
