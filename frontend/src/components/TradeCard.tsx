"use client";
/**
 * TradeCard — мобильная карточка сделки.
 *
 * 16-колоночная таблица на мобильном — катастрофа. На узких экранах
 * рендерим вертикальный список карточек: вся ключевая инфа за один клик.
 */
import Link from "next/link";
import { TrendingUp, TrendingDown, Edit2, Trash2, ChevronRight, Play } from "lucide-react";
import { parseApiDate } from "@/lib/dateUtils";

interface TradeLite {
  id: number;
  symbol: string;
  asset_name?: string;
  direction: string;
  pnl: number | null;
  net_pnl?: number | null;
  entry_price: number;
  exit_price?: number;
  quantity: number;
  entry_at: string;
  exit_at?: string;
  setup_name?: string;
  timeframe?: string;
  tags?: string[];
  r_multiple?: number;
  ai_analysis?: {
    verdict?: string;
    score?: number;
    insights?: Array<{ type: string; title: string }>;
  };
}

interface Props {
  trade: TradeLite;
  onEdit?: (id: number) => void;
  onDelete?: (id: number) => void;
  onClick?: (id: number) => void;
  formatCurrency?: (n: number) => string;
}

export function TradeCard({
  trade,
  onEdit,
  onDelete,
  onClick,
  formatCurrency = (n) => `${n.toLocaleString("ru-RU", { maximumFractionDigits: 2 })} ₽`,
}: Props) {
  const pnl = trade.net_pnl ?? trade.pnl ?? 0;
  const isOpen = !trade.exit_at;
  const isWin = pnl > 0;
  const direction = trade.direction.toUpperCase();

  return (
    <div
      onClick={() => onClick?.(trade.id)}
      className="rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--surface-1)] p-4 hover:border-[var(--border-strong)] active:bg-[var(--surface-hover)] transition-colors cursor-pointer"
    >
      {/* Header: ticker + direction + PnL */}
      <div className="flex items-start justify-between gap-3 mb-3">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="text-[16px] font-bold tracking-tight">{trade.symbol}</span>
            <span
              className={`text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-[var(--radius-pill)] ${
                direction === "LONG"
                  ? "bg-[var(--success-soft)] text-[var(--success)]"
                  : "bg-[var(--danger-soft)] text-[var(--danger)]"
              }`}
            >
              {direction}
            </span>
            {isOpen && (
              <span className="text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-[var(--radius-pill)] bg-[var(--accent-soft)] text-[var(--accent)]">
                Открыта
              </span>
            )}
          </div>
          {trade.asset_name && (
            <div className="text-[11px] text-[var(--text-tertiary)] truncate mt-0.5">{trade.asset_name}</div>
          )}
        </div>
        <div className="flex flex-col items-end">
          <div
            className={`text-[16px] font-bold tabular-nums flex items-center gap-1 ${
              isOpen ? "text-[var(--text-secondary)]" : isWin ? "text-[var(--success)]" : "text-[var(--danger)]"
            }`}
          >
            {!isOpen && (isWin ? <TrendingUp size={14} /> : <TrendingDown size={14} />)}
            {isOpen ? "—" : `${pnl >= 0 ? "+" : ""}${formatCurrency(pnl)}`}
          </div>
          {trade.r_multiple != null && !isOpen && (
            <div
              className={`text-[11px] font-mono ${
                trade.r_multiple > 0 ? "text-[var(--success)]" : "text-[var(--danger)]"
              }`}
            >
              {trade.r_multiple > 0 ? "+" : ""}{trade.r_multiple.toFixed(2)}R
            </div>
          )}
        </div>
      </div>

      {/* Body: prices + qty + dates */}
      <div className="grid grid-cols-2 gap-3 text-[12px]">
        <Row label="Вход" value={`${formatCurrency(trade.entry_price)} × ${trade.quantity}`} />
        {trade.exit_price ? (
          <Row label="Выход" value={formatCurrency(trade.exit_price)} />
        ) : (
          <Row label="Выход" value="—" muted />
        )}
        <Row label="Дата входа" value={formatShortDateTime(trade.entry_at)} />
        {trade.exit_at && <Row label="Дата выхода" value={formatShortDateTime(trade.exit_at)} />}
      </div>

      {/* AI verdict badge */}
      {trade.ai_analysis?.verdict && (
        <div className="mt-3 pt-3 border-t border-[var(--border)] flex items-center gap-2 text-[12px]">
          <span className="text-[10px] font-bold uppercase tracking-wider text-[var(--accent)]">AI</span>
          <span className="font-medium">{trade.ai_analysis.verdict}</span>
          {trade.ai_analysis.score !== undefined && (
            <span className={`ml-auto text-[11px] font-mono px-2 py-0.5 rounded-[var(--radius-pill)] ${
              trade.ai_analysis.score >= 70 ? "bg-[var(--success-soft)] text-[var(--success)]" :
              trade.ai_analysis.score >= 50 ? "bg-[var(--warning-soft)] text-[var(--warning)]" :
              "bg-[var(--danger-soft)] text-[var(--danger)]"
            }`}>{trade.ai_analysis.score}/100</span>
          )}
        </div>
      )}

      {/* Footer: setup, timeframe, tags */}
      {(trade.setup_name || trade.timeframe || (trade.tags && trade.tags.length > 0)) && (
        <div className="flex flex-wrap gap-1.5 mt-3 pt-3 border-t border-[var(--border)]">
          {trade.setup_name && (
            <span className="text-[10px] font-medium px-2 py-0.5 rounded-[var(--radius-pill)] bg-[var(--surface-2)] text-[var(--text-secondary)]">
              {trade.setup_name}
            </span>
          )}
          {trade.timeframe && (
            <span className="text-[10px] font-medium px-2 py-0.5 rounded-[var(--radius-pill)] bg-[var(--surface-2)] text-[var(--text-tertiary)]">
              {trade.timeframe}
            </span>
          )}
          {trade.tags?.slice(0, 3).map((tag) => (
            <span
              key={tag}
              className="text-[10px] font-medium px-2 py-0.5 rounded-[var(--radius-pill)] bg-[var(--accent-soft)] text-[var(--accent)]"
            >
              {tag}
            </span>
          ))}
        </div>
      )}

      {/* Actions */}
      <div className="flex items-center justify-end gap-1 mt-3" onClick={(e) => e.stopPropagation()}>
        <Link
          href={`/trades/${trade.id}/replay`}
          className="btn-icon"
          aria-label="Replay"
          title="Trade Replay"
        >
          <Play size={14} />
        </Link>
        {onEdit && (
          <button
            type="button"
            onClick={() => onEdit(trade.id)}
            className="btn-icon"
            aria-label="Редактировать"
          >
            <Edit2 size={14} />
          </button>
        )}
        {onDelete && (
          <button
            type="button"
            onClick={() => onDelete(trade.id)}
            className="btn-icon hover:text-[var(--danger)]"
            aria-label="Удалить"
          >
            <Trash2 size={14} />
          </button>
        )}
        <ChevronRight size={14} className="text-[var(--text-tertiary)]" />
      </div>
    </div>
  );
}

function Row({ label, value, muted }: { label: string; value: string; muted?: boolean }) {
  return (
    <div>
      <div className="text-[10px] text-[var(--text-tertiary)] uppercase tracking-wider mb-0.5">{label}</div>
      <div className={`font-mono tabular-nums ${muted ? "text-[var(--text-tertiary)]" : "text-[var(--foreground)]"}`}>
        {value}
      </div>
    </div>
  );
}

function formatShortDateTime(iso: string): string {
  try {
    const d = parseApiDate(iso);
    return d.toLocaleString("ru-RU", {
      day: "2-digit",
      month: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}
