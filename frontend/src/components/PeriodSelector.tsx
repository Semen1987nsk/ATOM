'use client';

import React, { useState } from 'react';
import { Calendar, ChevronDown, X } from 'lucide-react';
import { useLanguage } from '@/i18n/LanguageContext';

export type Period = 'all' | 'today' | 'week' | 'month' | '3months' | 'year' | 'custom';

interface PeriodSelectorProps {
  value: Period;
  onChange: (period: Period, startDate?: string, endDate?: string) => void;
  customStart?: string;
  customEnd?: string;
}

export const PeriodSelector: React.FC<PeriodSelectorProps> = ({ 
  value, 
  onChange, 
  customStart,
  customEnd
}) => {
  const { t } = useLanguage();
  const [isOpen, setIsOpen] = useState(false);
  const [showCustom, setShowCustom] = useState(false);
  const [startDate, setStartDate] = useState(customStart || '');
  const [endDate, setEndDate] = useState(customEnd || '');

  const periods: { value: Period; label: string }[] = [
    { value: 'all', label: t.period.all },
    { value: 'today', label: t.period.today },
    { value: 'week', label: t.period.week },
    { value: 'month', label: t.period.month },
    { value: '3months', label: t.period['3months'] },
    { value: 'year', label: t.period.year },
    { value: 'custom', label: t.period.custom },
  ];

  const handleSelect = (period: Period) => {
    if (period === 'custom') {
      setShowCustom(true);
      setIsOpen(false);
    } else {
      onChange(period);
      setIsOpen(false);
      setShowCustom(false);
    }
  };

  const handleCustomApply = () => {
    if (startDate) {
      onChange('custom', startDate, endDate || undefined);
      setShowCustom(false);
    }
  };

  const currentLabel = value === 'custom' && customStart 
    ? `${customStart}${customEnd ? ' - ' + customEnd : ''}`
    : periods.find(p => p.value === value)?.label || t.period.all;

  return (
    <div className="relative">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="flex items-center gap-2 bg-surface border border-border px-3 py-2 rounded-none hover:bg-border transition-colors text-xs font-bold uppercase tracking-widest"
      >
        <Calendar size={14} className="text-accent" />
        <span className="max-w-[120px] truncate">{currentLabel}</span>
        <ChevronDown size={12} className={`transition-transform ${isOpen ? 'rotate-180' : ''}`} />
      </button>

      {/* Dropdown */}
      {isOpen && (
        <div className="absolute top-full left-0 mt-1 bg-[#0d0d0d] border border-border z-50 min-w-[150px]">
          {periods.map((period) => (
            <button
              key={period.value}
              onClick={() => handleSelect(period.value)}
              className={`w-full text-left px-4 py-2 text-xs font-mono hover:bg-accent/10 transition-colors ${
                value === period.value ? 'text-accent bg-accent/5' : ''
              }`}
            >
              {period.label}
            </button>
          ))}
        </div>
      )}

      {/* Custom Date Modal */}
      {showCustom && (
        <div className="fixed inset-0 bg-black/80 backdrop-blur-sm flex items-center justify-center z-50">
          <div className="cyber-card w-full max-w-sm bg-[#0d0d0d] p-6 relative">
            <button 
              onClick={() => setShowCustom(false)} 
              className="absolute top-4 right-4 opacity-50 hover:opacity-100"
            >
              <X size={20} />
            </button>
            
            <h3 className="text-lg font-bold mb-4 flex items-center gap-2">
              <Calendar size={18} className="text-accent" />
              {t.period.custom}
            </h3>
            
            <div className="space-y-4">
              <div>
                <label className="block text-[10px] font-mono uppercase opacity-50 mb-1">
                  Start Date
                </label>
                <input
                  type="date"
                  value={startDate}
                  onChange={(e) => setStartDate(e.target.value)}
                  className="input-cyber"
                />
              </div>
              
              <div>
                <label className="block text-[10px] font-mono uppercase opacity-50 mb-1">
                  End Date (optional)
                </label>
                <input
                  type="date"
                  value={endDate}
                  onChange={(e) => setEndDate(e.target.value)}
                  className="input-cyber"
                />
              </div>
              
              <div className="flex gap-3 pt-2">
                <button
                  onClick={() => setShowCustom(false)}
                  className="flex-1 border border-border py-2 text-xs font-bold uppercase hover:bg-border transition-colors"
                >
                  Cancel
                </button>
                <button
                  onClick={handleCustomApply}
                  disabled={!startDate}
                  className="flex-1 bg-accent text-black py-2 text-xs font-bold uppercase hover:bg-white transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  Apply
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Click outside to close */}
      {isOpen && (
        <div 
          className="fixed inset-0 z-40" 
          onClick={() => setIsOpen(false)}
        />
      )}
    </div>
  );
};
