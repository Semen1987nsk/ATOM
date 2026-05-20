'use client';

/**
 * TR1 — Trade Journal с round-trip aggregation.
 * TR1.1 — Extended columns: % result, R-Multiple, MAE/MFE, indicators gutter,
 *         column-picker с localStorage persistence.
 *
 * Best practices (Tradervue, TraderSync, TradeZella, Edgewonk):
 * - One row per round-trip; expand для individual executions
 * - Italic P&L для open positions (Tradervue pattern)
 * - 🪜 ladder icon при scale-in (≥2 executions)
 * - % result + R-Multiple — power-user metrics
 * - 📝 notes icon + tooltip preview (TradeZella pattern)
 * - Indicators gutter справа (📷 screenshot, 🪜 scale-in, 📝 notes)
 */

import { useState, useEffect, useRef, useMemo } from 'react';
import {
  ChevronDown,
  ChevronRight,
  ChevronUp,
  ArrowUpDown,
  TrendingUp,
  Briefcase,
  Coins,
  Layers,
  Banknote,
  Sparkles,
  Layers3,
  ArrowUpRight,
  ArrowDownRight,
  ArrowRight,
  StickyNote,
  ImageIcon,
  Settings,
  X,
  Eye,
  EyeOff,
} from 'lucide-react';
import { api } from '@/lib/apiClient';
import { JournalNavigatorBar } from './journal/JournalNavigatorBar';
import { TableTopScrollbar } from './journal/TableTopScrollbar';
import { useJournalFilters } from './journal/useJournalFilters';
import {
  applyFilters,
  applySort,
  extractUniqueSetups,
} from './journal/filterUtils';
import type { SortKey } from './journal/types';

interface TradeExecution {
  id: number;
  entry_at: string;
  exit_at: string | null;
  entry_price: number;
  exit_price: number | null;
  quantity: number;
  direction: string;
  pnl: number | null;
  net_pnl: number | null;
  commission: number | null;
  entry_value: number | null;
  exit_value: number | null;
  mae_price?: number | null;
  mfe_price?: number | null;
  screenshot_url?: string | null;
  setup_name?: string | null;
  risk_amount?: number | null;
  // TR1.3: per-execution attributed fees
  varmargin_attributed?: number | null;
  margin_fee_attributed?: number | null;
  service_fee_attributed?: number | null;
  other_fees_attributed?: number | null;
  // Phase 9 (2026-05-17): прозрачный P&L из цен open/close для futures.
  // body_from_prices = (exit-entry)*qty*point_value*sign — computed на сервере.
  // Для не-futures это просто Trade.pnl (= body для shares).
  body_from_prices?: number | null;
  point_value?: number | null;
  point_value_source?: string | null;
  instrument_type_v2?: string | null;
}

interface PositionTrade {
  position_id: number;
  account_id: number;
  instrument_uid: string | null;
  symbol: string;
  asset_name: string | null;
  asset_type: string | null;
  direction: string;
  total_quantity: number;
  weighted_entry_price: number;
  weighted_exit_price: number | null;
  realized_pnl: number | null;
  unrealized_pnl: number | null;
  total_commission: number;
  total_entry_value: number | null;
  total_exit_value: number | null;
  first_entry_at: string;
  last_exit_at: string | null;
  holding_time_minutes: number | null;
  status: 'open' | 'closed';
  execution_count: number;
  is_scale_in: boolean;
  setup_id: number | null;
  setup_name: string | null;
  tags: string[];
  notes: string | null;
  // TR1.1
  pnl_pct: number | null;
  r_multiple: number | null;
  total_risk_amount: number | null;
  mae_price: number | null;
  mfe_price: number | null;
  has_screenshot: boolean;
  has_notes: boolean;
  confidence: number | null;
  mood: number | null;
  discipline: number | null;
  timeframe: string | null;
  news_event: string | null;
  stop_loss: number | null;
  take_profit: number | null;
  entry_reason: string | null;
  exit_reason: string | null;
  screenshot_url: string | null;
  // TR1.3: aggregated attributed fees + body P&L breakdown
  total_varmargin?: number | null;
  total_margin_fee?: number | null;
  total_service_fee?: number | null;
  total_other_fees?: number | null;
  body_pnl?: number | null;
  // Phase 9 (2026-05-17): Σ body_from_prices по executions —
  // прозрачный P&L из цен открытия/закрытия (для futures = (exit-entry)*qty*pv).
  body_from_prices?: number | null;
  executions: TradeExecution[];
}

// 2026-05-19: убрали 'open' таб — после Position = source of truth rewrite
// открытые позиции живут в PositionORM (страница /positions), а журнал —
// архив закрытых сделок. Phantom Trades с exit_at=None закрываются стадией
// _stage_phantom_sweep на следующем sync.

// TR1.1: column configuration. Default visible — 12 core columns.
interface ColumnConfig {
  id: string;
  label: string;
  defaultVisible: boolean;
  alwaysVisible?: boolean;  // chevron — нельзя скрыть
}

const ALL_COLUMNS: ColumnConfig[] = [
  { id: 'expand',     label: '',                defaultVisible: true,  alwaysVisible: true },
  { id: 'date',       label: 'Дата',            defaultVisible: true },
  { id: 'ticker',     label: 'Тикер',           defaultVisible: true },
  { id: 'side',       label: 'Сторона',         defaultVisible: true },
  { id: 'qty',        label: 'Объём',           defaultVisible: true },
  { id: 'prices',     label: 'Вход → Выход',    defaultVisible: true },
  { id: 'pnl',        label: 'P&L',             defaultVisible: true },
  { id: 'pnl_pct',    label: '%',               defaultVisible: true },
  { id: 'r_multiple', label: 'R',               defaultVisible: true },
  { id: 'duration',   label: 'Длительность',    defaultVisible: true },
  { id: 'setup',      label: 'Сетап',           defaultVisible: true },
  { id: 'indicators', label: 'Инд.',            defaultVisible: true },
  // Hidden by default — power-user
  { id: 'tags',       label: 'Теги',            defaultVisible: false },
  { id: 'mae_mfe',    label: 'MAE / MFE',       defaultVisible: false },
  { id: 'stop_take',  label: 'SL / TP',         defaultVisible: false },
  { id: 'commission', label: 'Комиссия',        defaultVisible: false },
  // TR1.3: fee breakdown columns
  { id: 'varmargin',  label: 'Варм.',           defaultVisible: false },
  { id: 'margin_fee', label: 'Маржа',           defaultVisible: false },
  { id: 'service_fee', label: 'Сервис',         defaultVisible: false },
  { id: 'other_fees', label: 'Налог',           defaultVisible: false },
  { id: 'confidence', label: 'Уверенность',     defaultVisible: false },
  { id: 'mood',       label: 'Настроение',      defaultVisible: false },
  { id: 'timeframe',  label: 'ТФ',              defaultVisible: false },
];

const COLUMN_STORAGE_KEY = 'eqio_position_journal_columns';

function loadVisibleColumns(): Set<string> {
  if (typeof window === 'undefined') {
    return new Set(ALL_COLUMNS.filter((c) => c.defaultVisible).map((c) => c.id));
  }
  try {
    const raw = localStorage.getItem(COLUMN_STORAGE_KEY);
    if (raw) {
      const arr = JSON.parse(raw) as string[];
      if (Array.isArray(arr)) {
        // Always-visible columns добавляем форсированно
        const set = new Set(arr);
        ALL_COLUMNS.filter((c) => c.alwaysVisible).forEach((c) => set.add(c.id));
        return set;
      }
    }
  } catch {
    /* fall through */
  }
  return new Set(ALL_COLUMNS.filter((c) => c.defaultVisible).map((c) => c.id));
}

function AssetTypeIcon({ type }: { type?: string | null }) {
  const cls = 'w-3.5 h-3.5 text-slate-400 shrink-0';
  switch ((type || '').toLowerCase()) {
    case 'futures': return <Briefcase className={cls} />;
    case 'option':
    case 'options': return <Sparkles className={cls} />;
    case 'bond':    return <Coins className={cls} />;
    case 'etf':     return <Layers className={cls} />;
    case 'currency':return <Banknote className={cls} />;
    default:        return <TrendingUp className={cls} />;
  }
}

function fmtMoney(v: number | null | undefined): string {
  if (v === null || v === undefined || !isFinite(v)) return '—';
  return v.toLocaleString('ru-RU', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function fmtPct(v: number | null | undefined): string {
  if (v === null || v === undefined || !isFinite(v)) return '—';
  const sign = v >= 0 ? '+' : '';
  return `${sign}${v.toLocaleString('ru-RU', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}%`;
}

function fmtR(v: number | null | undefined): string {
  if (v === null || v === undefined || !isFinite(v)) return '—';
  const sign = v >= 0 ? '+' : '';
  return `${sign}${v.toLocaleString('ru-RU', { minimumFractionDigits: 1, maximumFractionDigits: 2 })}R`;
}

function fmtPrice(v: number | null | undefined): string {
  if (v === null || v === undefined || !isFinite(v)) return '—';
  const abs = Math.abs(v);
  const fd = abs < 10 ? 4 : abs < 1000 ? 2 : 2;
  return v.toLocaleString('ru-RU', { minimumFractionDigits: fd, maximumFractionDigits: fd });
}

function fmtQty(v: number | null | undefined): string {
  if (v === null || v === undefined) return '—';
  return Math.round(v).toLocaleString('ru-RU');
}

function fmtDate(s: string | null | undefined): string {
  if (!s) return '—';
  const d = new Date(s);
  return d.toLocaleString('ru-RU', {
    day: '2-digit', month: '2-digit', year: '2-digit',
    hour: '2-digit', minute: '2-digit',
  });
}

function fmtHolding(minutes: number | null): string {
  if (minutes === null || minutes === undefined) return '—';
  if (minutes < 60) return `${minutes}м`;
  if (minutes < 60 * 24) return `${Math.floor(minutes / 60)}ч ${minutes % 60}м`;
  const days = Math.floor(minutes / (60 * 24));
  return `${days}д ${Math.floor((minutes % (60 * 24)) / 60)}ч`;
}

function DirectionBadge({ direction }: { direction: string }) {
  const isLong = direction.toLowerCase() === 'long';
  return (
    <span
      className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-semibold ${
        isLong ? 'bg-emerald-500/15 text-emerald-300' : 'bg-rose-500/15 text-rose-300'
      }`}
    >
      {isLong ? <ArrowUpRight size={10} /> : <ArrowDownRight size={10} />}
      {isLong ? 'LONG' : 'SHORT'}
    </span>
  );
}

function StatusBadge({ status }: { status: 'open' | 'closed' }) {
  if (status === 'open') {
    return (
      <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-semibold bg-amber-500/15 text-amber-300 border border-amber-500/30">
        ОТКРЫТА
      </span>
    );
  }
  return (
    <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-semibold bg-slate-600/30 text-slate-400">
      ЗАКРЫТА
    </span>
  );
}

function PnLValue({ value, italic = false }: { value: number | null; italic?: boolean }) {
  if (value === null || value === undefined || !isFinite(value)) {
    return <span className="text-slate-500">—</span>;
  }
  const color = value >= 0 ? 'text-emerald-400' : 'text-rose-400';
  return (
    <span className={`font-mono tabular-nums ${color} ${italic ? 'italic' : ''}`}>
      {value >= 0 ? '+' : ''}{fmtMoney(value)}&nbsp;₽
    </span>
  );
}

function PctValue({ value, italic = false }: { value: number | null; italic?: boolean }) {
  if (value === null || value === undefined || !isFinite(value)) {
    return <span className="text-slate-500">—</span>;
  }
  const color = value >= 0 ? 'text-emerald-400' : 'text-rose-400';
  return (
    <span className={`font-mono tabular-nums ${color} ${italic ? 'italic' : ''}`}>
      {fmtPct(value)}
    </span>
  );
}

function RValue({ value, italic = false }: { value: number | null; italic?: boolean }) {
  if (value === null || value === undefined || !isFinite(value)) {
    return (
      <span
        className="text-slate-600 cursor-help"
        title="Введите Stop Loss и Risk при создании сделки чтобы видеть R-Multiple"
      >
        —
      </span>
    );
  }
  const color = value >= 0 ? 'text-emerald-400' : 'text-rose-400';
  const isStrong = Math.abs(value) >= 2;
  return (
    <span className={`font-mono tabular-nums ${color} ${italic ? 'italic' : ''} ${isStrong ? 'font-bold' : ''}`}>
      {fmtR(value)}
    </span>
  );
}

function NotesIndicator({ notes, has_notes }: { notes: string | null; has_notes: boolean }) {
  if (!has_notes || !notes) {
    return <StickyNote size={14} className="text-slate-700" />;
  }
  const preview = notes.length > 80 ? notes.slice(0, 80) + '…' : notes;
  return (
    <span title={preview} className="cursor-help">
      <StickyNote size={14} className="text-cyan-400" />
    </span>
  );
}

function ExecutionList({
  executions,
}: {
  executions: TradeExecution[];
}) {
  // 2026-05-19: per-execution P&L = net_pnl (включает варм-маржу, fees,
  // commissions). Согласовано с агрегированной колонкой P&L. Fallback на body
  // (ex.pnl) если net_pnl отсутствует (legacy/manual trades без attribution).
  const pnlFor = (ex: TradeExecution) => ex.net_pnl ?? ex.pnl;
  return (
    <div className="bg-slate-900/40 rounded-lg p-3 border border-slate-700/30">
      <div className="text-[10px] uppercase tracking-wider text-slate-500 mb-2 font-semibold">
        Исполнения ({executions.length})
      </div>
      <table className="w-full text-xs">
        <thead>
          <tr className="text-[10px] uppercase tracking-wider text-slate-500 border-b border-slate-700/50">
            <th className="text-left py-1.5 pr-2 font-medium">№</th>
            <th className="text-left py-1.5 px-2 font-medium">Тип</th>
            <th className="text-left py-1.5 px-2 font-medium">Дата</th>
            <th className="text-right py-1.5 px-2 font-medium">Кол-во</th>
            <th className="text-right py-1.5 px-2 font-medium">Цена</th>
            <th className="text-right py-1.5 px-2 font-medium">Цена выхода</th>
            <th className="text-right py-1.5 px-2 font-medium">Комиссия</th>
            <th className="text-right py-1.5 pl-2 font-medium">P&amp;L</th>
          </tr>
        </thead>
        <tbody>
          {executions.map((ex, idx) => {
            const isClosed = ex.exit_at !== null;
            return (
              <tr key={ex.id} className="border-b border-slate-800/50 hover:bg-slate-800/30">
                <td className="py-1.5 pr-2 text-slate-500 font-mono">{idx + 1}</td>
                <td className="py-1.5 px-2">
                  {isClosed
                    ? <span className="text-rose-300 text-[10px] font-semibold uppercase">Закрытие</span>
                    : <span className="text-emerald-300 text-[10px] font-semibold uppercase">Открытие</span>}
                </td>
                <td className="py-1.5 px-2 text-slate-300 whitespace-nowrap">{fmtDate(ex.entry_at)}</td>
                <td className="py-1.5 px-2 text-right font-mono tabular-nums text-slate-200">{fmtQty(ex.quantity)}</td>
                <td className="py-1.5 px-2 text-right font-mono tabular-nums text-slate-200">{fmtPrice(ex.entry_price)}</td>
                <td className="py-1.5 px-2 text-right font-mono tabular-nums text-slate-300">{fmtPrice(ex.exit_price)}</td>
                <td className="py-1.5 px-2 text-right font-mono tabular-nums text-slate-500">
                  {ex.commission !== null ? fmtMoney(ex.commission) : '—'}
                </td>
                <td className="py-1.5 pl-2 text-right"><PnLValue value={pnlFor(ex)} /></td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function ColumnPicker({
  visible,
  onToggle,
  onClose,
}: {
  visible: Set<string>;
  onToggle: (id: string) => void;
  onClose: () => void;
}) {
  return (
    <div className="absolute right-0 top-full mt-2 z-50 bg-slate-900 border border-slate-700 rounded-xl shadow-2xl p-4 w-72">
      <div className="flex items-center justify-between mb-3">
        <h3 className="font-semibold text-slate-200 text-sm flex items-center gap-2">
          <Settings size={14} className="text-cyan-400" />
          Колонки таблицы
        </h3>
        <button onClick={onClose} className="text-slate-400 hover:text-slate-200">
          <X size={16} />
        </button>
      </div>
      <div className="space-y-1 max-h-96 overflow-y-auto">
        {ALL_COLUMNS.filter((c) => !c.alwaysVisible && c.label).map((col) => {
          const isVisible = visible.has(col.id);
          return (
            <button
              key={col.id}
              onClick={() => onToggle(col.id)}
              className={`w-full flex items-center justify-between px-2 py-1.5 rounded text-xs transition-colors ${
                isVisible
                  ? 'bg-cyan-500/15 text-cyan-300'
                  : 'bg-slate-800/40 text-slate-400 hover:bg-slate-800'
              }`}
            >
              <span>{col.label}</span>
              {isVisible ? <Eye size={14} /> : <EyeOff size={14} />}
            </button>
          );
        })}
      </div>
    </div>
  );
}

function PnLBreakdownCard({ position }: { position: PositionTrade }) {
  /**
   * TR1.3: «Из чего сложился P&L» — разложение по компонентам.
   * Trader видит за счёт чего получился итог: body, commission, varmargin,
   * margin_fee, service_fee, tax.
   */
  const isOpen = position.status === 'open';
  const components: Array<{ label: string; value: number | null | undefined; muted?: boolean }> = [
    { label: 'Движение цены (body)', value: position.body_pnl },
    { label: 'Комиссия брокера', value: position.total_commission !== undefined ? -Math.abs(position.total_commission) : null },
    { label: 'Вариомаржа', value: position.total_varmargin },
    { label: 'Маржинальное кредит.', value: position.total_margin_fee },
    { label: 'Сервисная плата', value: position.total_service_fee },
    { label: 'Налог', value: position.total_other_fees },
  ];

  const total = isOpen ? position.unrealized_pnl : position.realized_pnl;
  const hasAnyComponent = components.some((c) => c.value !== null && c.value !== undefined && c.value !== 0);
  if (!hasAnyComponent && total === null) return null;

  return (
    <div className="bg-slate-900/40 rounded-lg p-3 border border-slate-700/30 mb-3">
      <div className="text-[10px] uppercase tracking-wider text-slate-500 mb-2 font-semibold">
        Из чего сложился результат
      </div>
      <div className="space-y-1.5 text-xs">
        {components.map((c) => {
          if (c.value === null || c.value === undefined || c.value === 0) return null;
          return (
            <div key={c.label} className="flex justify-between items-center">
              <span className="text-slate-400">{c.label}</span>
              <PnLValue value={c.value} />
            </div>
          );
        })}
        {isOpen && position.unrealized_pnl !== null && position.unrealized_pnl !== undefined && (
          <div className="flex justify-between items-center">
            <span className="text-slate-400 italic">Нереализованная (MTM)</span>
            <PnLValue value={position.unrealized_pnl} italic />
          </div>
        )}
        <div className="border-t border-slate-700/50 mt-2 pt-2 flex justify-between items-center">
          <span className="text-slate-200 font-semibold uppercase text-[11px]">
            {isOpen ? 'Net P&L (open, MTM)' : 'Net P&L'}
          </span>
          <span className="text-base">
            <PnLValue value={total} italic={isOpen} />
          </span>
        </div>
      </div>
    </div>
  );
}

function PositionRow({
  position,
  expanded,
  onToggle,
  visibleColumns,
}: {
  position: PositionTrade;
  expanded: boolean;
  onToggle: () => void;
  visibleColumns: Set<string>;
}) {
  const isOpen = position.status === 'open';
  // 2026-05-19: колонка P&L = реальный net P&L (включает варм-маржа, fees,
  // commissions). Раньше показывали body_from_prices (price-only), но это
  // вводило в заблуждение для фьючерсов: phantom_sweep устанавливает
  // exit_price = entry_price → body=0₽, при том что реальный убыток уже
  // списан через ежедневную варм-маржу. Теперь P&L согласован с % колонкой
  // и отражает реальный денежный поток. Breakdown по компонентам — в
  // expand-карточке (body + var-маржа + fees).
  const pnlValue = isOpen ? position.unrealized_pnl : position.realized_pnl;
  const has = (id: string) => visibleColumns.has(id);

  // Подсчёт количества visible колонок (для colSpan expand row).
  const visibleCount = ALL_COLUMNS.filter((c) => visibleColumns.has(c.id)).length;

  return (
    <>
      <tr
        className="border-b border-slate-800/50 hover:bg-slate-800/30 cursor-pointer transition-colors"
        onClick={onToggle}
      >
        {has('expand') && (
          <td className="py-3 pr-2 pl-3 align-middle">
            <button className="text-slate-400 hover:text-slate-200" aria-label={expanded ? 'Свернуть' : 'Развернуть'}>
              {expanded ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
            </button>
          </td>
        )}
        {has('date') && (
          <td className="py-3 px-2 text-xs text-slate-300 whitespace-nowrap">
            <div>{fmtDate(position.first_entry_at)}</div>
            {position.last_exit_at && (
              <div className="text-[10px] text-slate-500 mt-0.5">→ {fmtDate(position.last_exit_at)}</div>
            )}
          </td>
        )}
        {has('ticker') && (
          <td className="py-3 px-2">
            <div className="flex items-center gap-1.5">
              <AssetTypeIcon type={position.asset_type} />
              <span className="font-mono font-semibold text-slate-100 text-sm">{position.symbol}</span>
            </div>
            {position.asset_name && (
              <div className="text-[11px] text-slate-500 mt-0.5 truncate max-w-[180px]">{position.asset_name}</div>
            )}
          </td>
        )}
        {has('side') && (
          <td className="py-3 px-2">
            <div className="flex items-center gap-1.5">
              <DirectionBadge direction={position.direction} />
              <StatusBadge status={position.status} />
            </div>
          </td>
        )}
        {has('qty') && (
          <td className="py-3 px-2 text-right font-mono tabular-nums text-slate-200 text-sm">
            {fmtQty(position.total_quantity)}
            {position.execution_count > 1 && (
              <div className="text-[10px] text-slate-500 mt-0.5">{position.execution_count} исп.</div>
            )}
          </td>
        )}
        {has('prices') && (
          <td className="py-3 px-2 text-right font-mono tabular-nums text-slate-200 text-sm whitespace-nowrap">
            <div className="flex items-center justify-end gap-1.5">
              <span>{fmtPrice(position.weighted_entry_price)}</span>
              <ArrowRight size={11} className="text-slate-500 shrink-0" />
              <span className={position.weighted_exit_price === null ? 'text-slate-600' : ''}>
                {position.weighted_exit_price !== null ? fmtPrice(position.weighted_exit_price) : '—'}
              </span>
            </div>
          </td>
        )}
        {has('pnl') && (
          <td className="py-3 px-2 text-right whitespace-nowrap">
            <PnLValue value={pnlValue} italic={isOpen} />
          </td>
        )}
        {has('pnl_pct') && (
          <td className="py-3 px-2 text-right whitespace-nowrap">
            <PctValue value={position.pnl_pct} italic={isOpen} />
          </td>
        )}
        {has('r_multiple') && (
          <td className="py-3 px-2 text-right whitespace-nowrap">
            <RValue value={position.r_multiple} italic={isOpen} />
          </td>
        )}
        {has('duration') && (
          <td className="py-3 px-2 text-xs text-slate-400 whitespace-nowrap">
            {fmtHolding(position.holding_time_minutes)}
          </td>
        )}
        {has('setup') && (
          <td className="py-3 px-2 text-xs text-slate-400">
            {position.setup_name
              ? <span className="px-1.5 py-0.5 bg-slate-700/40 rounded text-slate-300">{position.setup_name}</span>
              : <span className="text-slate-600">—</span>}
          </td>
        )}
        {has('indicators') && (
          <td className="py-3 px-2 text-center whitespace-nowrap">
            <div className="inline-flex items-center gap-1.5">
              {position.is_scale_in && (
                <span title={`${position.execution_count} исполнений (scale-in)`} className="cursor-help">
                  <Layers3 size={13} className="text-cyan-400" />
                </span>
              )}
              {position.has_screenshot && (
                <span title="Скриншот прикреплён" className="cursor-help">
                  <ImageIcon size={13} className="text-violet-400" />
                </span>
              )}
              <NotesIndicator notes={position.notes} has_notes={position.has_notes} />
            </div>
          </td>
        )}
        {has('tags') && (
          <td className="py-3 px-2">
            <div className="flex gap-1 flex-wrap">
              {(position.tags || []).slice(0, 3).map((t) => (
                <span key={t} className="text-[10px] px-1.5 py-0.5 bg-slate-700/40 rounded text-slate-400">{t}</span>
              ))}
            </div>
          </td>
        )}
        {has('mae_mfe') && (
          <td className="py-3 px-2 text-xs text-slate-400 font-mono tabular-nums whitespace-nowrap">
            {position.mae_price !== null || position.mfe_price !== null ? (
              <div className="text-right">
                <div className="text-rose-400">MAE: {fmtPrice(position.mae_price)}</div>
                <div className="text-emerald-400">MFE: {fmtPrice(position.mfe_price)}</div>
              </div>
            ) : (
              <span className="text-slate-600">—</span>
            )}
          </td>
        )}
        {has('stop_take') && (
          <td className="py-3 px-2 text-xs text-slate-400 font-mono tabular-nums whitespace-nowrap">
            {position.stop_loss !== null || position.take_profit !== null ? (
              <div className="text-right">
                <div className="text-rose-400">SL: {fmtPrice(position.stop_loss)}</div>
                <div className="text-emerald-400">TP: {fmtPrice(position.take_profit)}</div>
              </div>
            ) : (
              <span className="text-slate-600">—</span>
            )}
          </td>
        )}
        {has('commission') && (
          <td className="py-3 px-2 text-right font-mono tabular-nums text-slate-400 text-xs whitespace-nowrap">
            {fmtMoney(position.total_commission)}
          </td>
        )}
        {has('varmargin') && (
          <td className="py-3 px-2 text-right font-mono tabular-nums text-slate-400 text-xs whitespace-nowrap">
            {position.total_varmargin !== null && position.total_varmargin !== undefined
              ? <PnLValue value={position.total_varmargin} />
              : <span className="text-slate-600">—</span>}
          </td>
        )}
        {has('margin_fee') && (
          <td className="py-3 px-2 text-right font-mono tabular-nums text-slate-400 text-xs whitespace-nowrap">
            {position.total_margin_fee !== null && position.total_margin_fee !== undefined
              ? <PnLValue value={position.total_margin_fee} />
              : <span className="text-slate-600">—</span>}
          </td>
        )}
        {has('service_fee') && (
          <td className="py-3 px-2 text-right font-mono tabular-nums text-slate-400 text-xs whitespace-nowrap">
            {position.total_service_fee !== null && position.total_service_fee !== undefined
              ? <PnLValue value={position.total_service_fee} />
              : <span className="text-slate-600">—</span>}
          </td>
        )}
        {has('other_fees') && (
          <td className="py-3 px-2 text-right font-mono tabular-nums text-slate-400 text-xs whitespace-nowrap">
            {position.total_other_fees !== null && position.total_other_fees !== undefined
              ? <PnLValue value={position.total_other_fees} />
              : <span className="text-slate-600">—</span>}
          </td>
        )}
        {has('confidence') && (
          <td className="py-3 px-2 text-center text-xs text-slate-400">
            {position.confidence !== null ? `${position.confidence}/5` : '—'}
          </td>
        )}
        {has('mood') && (
          <td className="py-3 px-2 text-center text-xs text-slate-400">
            {position.mood !== null ? `${position.mood}/5` : '—'}
          </td>
        )}
        {has('timeframe') && (
          <td className="py-3 px-2 text-center text-xs text-slate-400">
            {position.timeframe || '—'}
          </td>
        )}
      </tr>
      {expanded && (
        <tr className="bg-slate-900/30">
          <td colSpan={visibleCount} className="p-3 px-6">
            <PnLBreakdownCard position={position} />
            <ExecutionList executions={position.executions} />
            {position.notes && (
              <div className="mt-3 text-xs text-slate-400 bg-slate-900/40 rounded p-3 border border-slate-700/30">
                <div className="text-[10px] uppercase text-slate-500 mb-1 font-semibold">Заметка</div>
                {position.notes}
              </div>
            )}
            {position.entry_reason && (
              <div className="mt-2 text-xs text-slate-400 bg-slate-900/40 rounded p-3 border border-slate-700/30">
                <div className="text-[10px] uppercase text-slate-500 mb-1 font-semibold">Причина входа</div>
                {position.entry_reason}
              </div>
            )}
          </td>
        </tr>
      )}
    </>
  );
}

// Phase 13 (2026-05-17): mapping column id → SortKey pair (desc, asc).
// Click на заголовок такой колонки переключает sort. Если колонка скрыта
// через column-picker — фильтры не теряются, sort работает на back-end данных.
const SORTABLE_COLUMNS: Record<string, [SortKey, SortKey]> = {
  date: ['date_desc', 'date_asc'],
  pnl: ['pnl_desc', 'pnl_asc'],
  pnl_pct: ['pct_desc', 'pct_asc'],
  duration: ['duration_desc', 'duration_asc'],
};

export function PositionJournalView() {
  // Phase 12: журнал показывает body P&L ВСЕГДА — toggle settings.pnlDisplayMode
  // не влияет на журнал (он управляет ТОЛЬКО dashboard headline).
  const [positions, setPositions] = useState<PositionTrade[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set());
  const [visibleColumns, setVisibleColumns] = useState<Set<string>>(() => loadVisibleColumns());
  const [showColumnPicker, setShowColumnPicker] = useState(false);
  const pickerRef = useRef<HTMLDivElement>(null);
  // Phase 14: refs + state для top-sticky duplicate scrollbar.
  // ResizeObserver на <table> отслеживает изменение scrollWidth (column-picker
  // → колонки meняются → ширина пересчитывается).
  const mainScrollRef = useRef<HTMLDivElement>(null);
  const tableRef = useRef<HTMLTableElement>(null);
  const [scrollWidth, setScrollWidth] = useState(0);

  // Persist column visibility
  useEffect(() => {
    if (typeof window !== 'undefined') {
      localStorage.setItem(COLUMN_STORAGE_KEY, JSON.stringify(Array.from(visibleColumns)));
    }
  }, [visibleColumns]);

  // Click outside to close picker
  useEffect(() => {
    if (!showColumnPicker) return;
    const handler = (e: MouseEvent) => {
      if (pickerRef.current && !pickerRef.current.contains(e.target as Node)) {
        setShowColumnPicker(false);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [showColumnPicker]);

  // Phase 14: ResizeObserver — отслеживает изменение table.scrollWidth и
  // container.clientWidth. Top scrollbar показывается только когда есть
  // реальный horizontal overflow. RO сам реагирует на изменения content-rect,
  // поэтому effect монтируется один раз (rebind при изменении
  // table/container refs покрыт через recompute).
  useEffect(() => {
    const table = tableRef.current;
    const main = mainScrollRef.current;
    if (!table || !main) return;
    const recompute = () => {
      const innerW = table.scrollWidth;
      const outerW = main.clientWidth;
      setScrollWidth(innerW > outerW ? innerW : 0);
    };
    recompute();
    const ro = new ResizeObserver(recompute);
    ro.observe(table);
    ro.observe(main);
    return () => ro.disconnect();
  }, [positions.length, visibleColumns]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    api
      .get<PositionTrade[]>('/trades/positions?status=closed&limit=500')
      .then((data) => {
        if (cancelled) return;
        setPositions(data);
      })
      .catch((e) => {
        if (cancelled) return;
        setError((e as Error).message || 'Ошибка загрузки');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const toggleRow = (positionKey: string) => {
    setExpandedIds((prev) => {
      const next = new Set(prev);
      if (next.has(positionKey)) next.delete(positionKey);
      else next.add(positionKey);
      return next;
    });
  };

  const toggleColumn = (id: string) => {
    setVisibleColumns((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  // Phase 13: derived filter/sort/limit pipeline. Все три уровня в useMemo —
  // фильтрация запускается только когда меняется input.
  const { filters, update: updateFilters, reset: resetFilters } = useJournalFilters();
  const availableSetups = useMemo(() => extractUniqueSetups(positions), [positions]);
  const filteredPositions = useMemo(
    () => applyFilters(positions, filters),
    [positions, filters],
  );
  const sortedPositions = useMemo(
    () => applySort(filteredPositions, filters.sort),
    [filteredPositions, filters.sort],
  );
  const visiblePositions = useMemo(
    () => sortedPositions.slice(0, filters.visibleLimit),
    [sortedPositions, filters.visibleLimit],
  );
  const remainingCount = sortedPositions.length - visiblePositions.length;

  const toggleSort = (columnId: string) => {
    const sortPair = SORTABLE_COLUMNS[columnId];
    if (!sortPair) return;
    const [descKey, ascKey] = sortPair;
    // Click toggle: если сейчас desc этой колонки → asc; иначе → desc.
    updateFilters({ sort: filters.sort === descKey ? ascKey : descKey });
  };

  // Render header conditionally based on visible columns.
  // Phase 13: для sortable колонок — клик переключает sort + показывает arrow.
  const renderHeader = (id: string, label: string, align: 'left' | 'right' | 'center' = 'left', tooltip?: string) => {
    if (!visibleColumns.has(id)) return null;
    const alignClass = align === 'right' ? 'text-right' : align === 'center' ? 'text-center' : 'text-left';
    const sortPair = SORTABLE_COLUMNS[id];
    const sortable = !!sortPair;
    const [descKey, ascKey] = sortPair || [];
    const isActive = sortable && (filters.sort === descKey || filters.sort === ascKey);
    const isDesc = sortable && filters.sort === descKey;
    return (
      <th
        key={id}
        className={`${alignClass} py-2 px-2 font-medium ${sortable ? 'cursor-pointer select-none hover:text-slate-200' : ''}`}
        title={tooltip}
        onClick={sortable ? () => toggleSort(id) : undefined}
      >
        <span className={`inline-flex items-center gap-1 ${align === 'right' ? 'justify-end w-full' : ''}`}>
          {label}
          {sortable && isActive && (
            isDesc ? <ChevronDown size={12} className="text-accent" /> : <ChevronUp size={12} className="text-accent" />
          )}
          {sortable && !isActive && <ArrowUpDown size={10} className="opacity-25" />}
        </span>
      </th>
    );
  };

  return (
    <div className="space-y-3">
      {/* Column picker */}
      <div className="flex items-center justify-end">
        {/* Phase 13: счётчик перенесён в NavigatorBar (более релевантен при фильтре). */}
        <div className="relative" ref={pickerRef}>
          <button
            onClick={() => setShowColumnPicker((v) => !v)}
            className={`p-2 rounded-lg border transition-all ${
              showColumnPicker
                ? 'border-cyan-500/50 bg-cyan-500/15 text-cyan-300'
                : 'border-slate-700/50 hover:border-cyan-500/40 text-slate-400 hover:text-cyan-300'
            }`}
            title="Настройки колонок"
          >
            <Settings size={16} />
          </button>
          {showColumnPicker && (
            <ColumnPicker
              visible={visibleColumns}
              onToggle={toggleColumn}
              onClose={() => setShowColumnPicker(false)}
            />
          )}
        </div>
      </div>

      {/* Phase 13 (2026-05-17): Journal Navigator Bar — sticky filter row. */}
      <div className="sticky top-0 z-20 -mx-1 px-1 py-2 bg-[var(--bg,#0a0a0a)]/95 backdrop-blur-sm">
        <JournalNavigatorBar
          filters={filters}
          onUpdate={updateFilters}
          onReset={resetFilters}
          filteredCount={filteredPositions.length}
          totalCount={positions.length}
          availableSetups={availableSetups}
        />
      </div>

      {/* Hint */}
      <div className="text-[11px] text-slate-500 bg-cyan-500/5 border border-cyan-500/20 rounded p-2 flex items-start gap-2">
        <Layers3 size={14} className="text-cyan-400 shrink-0 mt-0.5" />
        <div>
          Сделки группируются по round-trip: scaled-in добавления и partial closes
          собираются в одну строку. Клик на строку → исполнения. Шестерёнка справа → колонки.
          <span className="ml-2 text-cyan-400/80">
            💡 Shift + колесо мыши = горизонтальная прокрутка таблицы.
          </span>
        </div>
      </div>

      {/* Phase 14: Top sticky horizontal scrollbar — дублирует bottom,
          sticky под NavigatorBar чтобы скроллить вправо БЕЗ перехода вниз. */}
      <TableTopScrollbar mainScrollRef={mainScrollRef} scrollWidth={scrollWidth} />

      {/* Table */}
      {/* Phase 13: убрали overflow-hidden — sticky thead требует прокручиваемого ancestor.
          Скруглённые углы сохраняем через overflow-x-auto на inner wrapper. */}
      <div className="rounded-xl border border-slate-700/40 bg-slate-800/20">
        {loading ? (
          <div className="p-8 text-center text-slate-500 text-sm">Загрузка...</div>
        ) : error ? (
          <div className="p-8 text-center text-rose-400 text-sm">{error}</div>
        ) : positions.length === 0 ? (
          <div className="p-8 text-center text-slate-500 text-sm">Нет сделок в выбранном фильтре</div>
        ) : filteredPositions.length === 0 ? (
          <div className="p-8 text-center text-slate-500 text-sm space-y-2">
            <div>Ничего не найдено по текущим фильтрам</div>
            <button
              type="button"
              onClick={resetFilters}
              className="text-xs text-accent hover:underline"
            >
              Сбросить фильтры
            </button>
          </div>
        ) : (
          <div ref={mainScrollRef} className="overflow-x-auto scrollbar-visible rounded-xl journal-scroll-container">
            <table ref={tableRef} className="w-full text-sm border-collapse journal-table-sticky">
              <thead>
                <tr className="text-[10px] uppercase tracking-wider text-slate-500 border-b border-slate-700/50 bg-slate-800/40">
                  {visibleColumns.has('expand') && <th className="text-left py-2 pl-3 pr-2 font-medium w-8"></th>}
                  {renderHeader('date', 'Дата')}
                  {renderHeader('ticker', 'Тикер')}
                  {renderHeader('side', 'Сторона')}
                  {renderHeader('qty', 'Объём', 'right')}
                  {renderHeader('prices', 'Вход → Выход', 'right')}
                  {renderHeader('pnl', 'P&L', 'right', 'Чистый P&L по сделке: для закрытых — реальный денежный исход (движение цены + варм-маржа за каждый день удержания + комиссии/fees). Для открытых — нереализованный MTM от брокера. Раскрой строку для разбивки.')}
                  {renderHeader('pnl_pct', '%', 'right')}
                  {renderHeader('r_multiple', 'R', 'right')}
                  {renderHeader('duration', 'Длительность')}
                  {renderHeader('setup', 'Сетап')}
                  {renderHeader('indicators', 'Инд.', 'center')}
                  {renderHeader('tags', 'Теги')}
                  {renderHeader('mae_mfe', 'MAE/MFE', 'right')}
                  {renderHeader('stop_take', 'SL/TP', 'right')}
                  {renderHeader('commission', 'Комиссия', 'right')}
                  {renderHeader('varmargin', 'Варм.', 'right')}
                  {renderHeader('margin_fee', 'Маржа', 'right')}
                  {renderHeader('service_fee', 'Сервис', 'right')}
                  {renderHeader('other_fees', 'Налог', 'right')}
                  {renderHeader('confidence', 'Увер.', 'center')}
                  {renderHeader('mood', 'Настр.', 'center')}
                  {renderHeader('timeframe', 'ТФ', 'center')}
                </tr>
              </thead>
              <tbody>
                {visiblePositions.map((p) => {
                  // Unique key per position: использует instrument_uid+position_id если есть,
                  // иначе fallback на symbol+first_entry_at (для legacy trades без position_id).
                  // Bug-fix 2026-05-19: parseInt(`${undefined}${account_id}`) давал NaN → все
                  // legacy позиции схлопывались в одну expand-группу.
                  const stateKey = p.position_id != null
                    ? `${p.instrument_uid || p.symbol}-${p.position_id}`
                    : `legacy-${p.symbol}-${p.first_entry_at}`;
                  return (
                    <PositionRow
                      key={stateKey}
                      position={p}
                      expanded={expandedIds.has(stateKey)}
                      onToggle={() => toggleRow(stateKey)}
                      visibleColumns={visibleColumns}
                    />
                  );
                })}
              </tbody>
            </table>
            {/* Phase 13: «Показать ещё» pagination — load +100 каждый клик. */}
            {remainingCount > 0 && (
              <div className="p-3 text-center border-t border-slate-700/40 bg-slate-900/30">
                <button
                  type="button"
                  onClick={() =>
                    updateFilters({
                      visibleLimit: filters.visibleLimit + 100,
                    })
                  }
                  className="px-4 py-2 text-xs font-medium rounded-md border border-slate-700 hover:border-accent text-slate-300 hover:text-accent transition-colors"
                >
                  Показать ещё 100{' '}
                  <span className="text-slate-500">
                    (осталось {remainingCount})
                  </span>
                </button>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
