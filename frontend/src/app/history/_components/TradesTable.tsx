'use client';

import { RefObject } from 'react';
import { TradeCard } from '@/components/TradeCard';
import { TradeRow } from './TradeRow';
import type { Trade } from './types';

interface TradesTableProps {
  scrollContainerRef: RefObject<HTMLDivElement | null>;
  sortedTrades: Trade[];
  isColumnVisible: (id: string) => boolean;
  visibleColumnsSize: number;
  expandedTrades: Set<number>;
  unrealizedData: Record<number, { pnl: number; price: number }>;
  isCalculatingMAE: boolean;
  canScrollLeft: boolean;
  canScrollRight: boolean;
  onToggleExpand: (tradeId: number) => void;
  onEdit: (trade: Trade) => void;
  onDelete: (tradeId: number) => void;
  onOpenClose: (trade: Trade) => void;
  onCalculateMAE: (tradeIds: number[]) => void;
  // Mobile-card path использует другой Edit-handler (находит trade в sortedTrades).
  onMobileEdit: (id: number) => void;
}

export function TradesTable({
  scrollContainerRef,
  sortedTrades,
  isColumnVisible,
  visibleColumnsSize,
  expandedTrades,
  unrealizedData,
  isCalculatingMAE,
  canScrollLeft,
  canScrollRight,
  onToggleExpand,
  onEdit,
  onDelete,
  onOpenClose,
  onCalculateMAE,
  onMobileEdit,
}: TradesTableProps) {
  return (
    <div className="relative">
      {/* Left shadow indicator */}
      <div
        className={`absolute left-0 top-0 bottom-0 w-8 bg-gradient-to-r from-slate-900/90 to-transparent pointer-events-none z-10 transition-opacity duration-200 ${
          canScrollLeft ? 'opacity-100' : 'opacity-0'
        }`}
      />
      {/* Right shadow indicator */}
      <div
        className={`absolute right-0 top-0 bottom-0 w-8 bg-gradient-to-l from-slate-900/90 to-transparent pointer-events-none z-10 transition-opacity duration-200 ${
          canScrollRight ? 'opacity-100' : 'opacity-0'
        }`}
      />

      {/* Mobile card view — viewport < md
          Таблица 16 колонок на телефоне = катастрофа. На узких экранах
          показываем вертикальный список карточек. */}
      <div className="md:hidden space-y-2">
        {sortedTrades.length === 0 ? (
          <div className="text-center py-10 text-[13px] text-[var(--text-tertiary)]">
            Нет сделок по текущему фильтру.
          </div>
        ) : (
          sortedTrades.map((trade) => (
            <TradeCard
              key={trade.id}
              trade={trade as Parameters<typeof TradeCard>[0]['trade']}
              onEdit={onMobileEdit}
              onDelete={(id) => onDelete(id)}
            />
          ))
        )}
      </div>

      {/* Desktop table view — viewport >= md */}
      <div
        ref={scrollContainerRef}
        className="hidden md:block overflow-x-auto scrollbar-thin scrollbar-track-transparent scrollbar-thumb-accent/30 hover:scrollbar-thumb-accent/50"
        style={{ maxHeight: 'calc(100vh - 300px)' }}
      >
        <table className="w-full text-left border-collapse">
          <thead className="sticky top-0 z-20 bg-slate-900/95 backdrop-blur-sm">
            <tr className="text-xs font-mono uppercase text-slate-400 border-b border-border">
              <th className="py-2 pl-2 w-8"></th>
              {isColumnVisible('date') && <th className="py-2 w-40">Даты</th>}
              {isColumnVisible('ticker') && <th className="py-2 w-24">Тикер</th>}
              {isColumnVisible('name') && <th className="py-2 w-44">Название</th>}
              {isColumnVisible('direction') && <th className="py-2 w-14">Стор.</th>}
              {isColumnVisible('quantity') && <th className="py-2 w-16">Кол-во</th>}
              {isColumnVisible('entry') && <th className="py-2 w-20">Вход</th>}
              {isColumnVisible('exit') && <th className="py-2 w-20">Выход</th>}
              {isColumnVisible('pnl') && <th className="py-2 w-24">PnL</th>}
              {isColumnVisible('holding') && <th className="py-2 w-20">Holding</th>}
              {isColumnVisible('setup') && <th className="py-2 w-24">Сетап</th>}
              {isColumnVisible('note') && <th className="py-2 w-12 text-center">📝</th>}
              {isColumnVisible('timeframe') && <th className="py-2 w-14">ТФ</th>}
              {isColumnVisible('commission') && <th className="py-2 w-20">Комис.</th>}
              {isColumnVisible('swap') && <th className="py-2 w-16">Своп</th>}
              {isColumnVisible('confidence') && <th className="py-2 w-12">Увер.</th>}
              {isColumnVisible('risk') && <th className="py-2 w-20">Риск</th>}
              {isColumnVisible('rMultiple') && <th className="py-2 w-16">R</th>}
              {isColumnVisible('status') && <th className="py-2 w-16">Статус</th>}
              {isColumnVisible('tags') && <th className="py-2 w-24">Теги</th>}
              {isColumnVisible('leverage') && <th className="py-2 w-12">Плечо</th>}
              <th className="py-2 w-16 text-right pr-2">Действ.</th>
            </tr>
          </thead>
          <tbody className="text-sm">
            {sortedTrades.map((trade) => (
              <TradeRow
                key={trade.id}
                trade={trade}
                isExpanded={expandedTrades.has(trade.id)}
                unrealized={trade.exit_at ? undefined : unrealizedData[trade.id]}
                visibleColumnsSize={visibleColumnsSize}
                isColumnVisible={isColumnVisible}
                isCalculatingMAE={isCalculatingMAE}
                onToggleExpand={onToggleExpand}
                onOpenClose={onOpenClose}
                onEdit={onEdit}
                onDelete={onDelete}
                onCalculateMAE={onCalculateMAE}
              />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
