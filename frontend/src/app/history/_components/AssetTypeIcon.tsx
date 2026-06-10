'use client';

import React from 'react';
import { Briefcase, Sparkles, Coins, Layers, Banknote, TrendingUp } from 'lucide-react';

// Иконка для колонки «Тикер» — визуально различает типы инструментов.
// Маппинг по `instrument_type_v2` из бэка (приходит из Tinkoff API).
export const AssetTypeIcon: React.FC<{ type?: string; className?: string }> = ({ type, className }) => {
  const cls = className || 'w-3 h-3 text-slate-400 shrink-0';
  switch ((type || '').toLowerCase()) {
    case 'futures':
      return <Briefcase className={cls} />;
    case 'option':
    case 'options':
      return <Sparkles className={cls} />;
    case 'bond':
      return <Coins className={cls} />;
    case 'etf':
      return <Layers className={cls} />;
    case 'currency':
      return <Banknote className={cls} />;
    case 'share':
    default:
      return <TrendingUp className={cls} />;
  }
};
