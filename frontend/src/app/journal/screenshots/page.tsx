"use client";
/**
 * /journal/screenshots — галерея скринов сделок.
 *
 * Tradervue's edge — collection of chart screenshots with PnL context.
 * Сортировка: best PnL / worst PnL / chronological.
 * Фильтр: все / только прибыльные / только убыточные.
 */
import { useEffect, useMemo, useState } from "react";
import { Image as ImageIcon, TrendingUp, TrendingDown, ExternalLink } from "lucide-react";
import { AppShell } from "@/components/AppShell";
import { AnalysisPageHeader } from "@/components/analysis/AnalysisPageHeader";
import { DashboardSkeleton } from "@/components/Skeleton";
import { api, getApiUrl, ApiError } from "@/lib/apiClient";
import { useAuth } from "@/contexts/AuthContext";
import { useSettings } from "@/contexts/SettingsContext";
import { DataError } from "@/components/ui/DataError";

interface TradeWithScreenshot {
  id: number;
  symbol: string;
  direction: string;
  pnl: number | null;
  net_pnl?: number | null;
  entry_at: string;
  exit_at?: string;
  setup_name?: string;
  screenshot_url?: string;
  notes?: string;
}

type SortMode = "best" | "worst" | "recent";
type FilterMode = "all" | "wins" | "losses";

export default function ScreenshotsPage() {
  const { user, isLoading: authLoading } = useAuth();
  const { formatCurrency } = useSettings();
  const [trades, setTrades] = useState<TradeWithScreenshot[]>([]);
  const [loading, setLoading] = useState(true);
  const [sort, setSort] = useState<SortMode>("best");
  const [filter, setFilter] = useState<FilterMode>("all");
  const [lightbox, setLightbox] = useState<TradeWithScreenshot | null>(null);
  const [error, setError] = useState<ApiError | Error | null>(null);
  const [refetchKey, setRefetchKey] = useState(0);

  useEffect(() => {
    if (!user) { setLoading(false); return; }
    setLoading(true);
    setError(null);
    let cancelled = false;
    api.get<TradeWithScreenshot[]>("/trades/")
      .then((data) => { if (!cancelled) setTrades((data || []).filter((t) => t.screenshot_url)); })
      .catch((e) => { if (!cancelled) { setTrades([]); setError(e as ApiError | Error); } })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [user, refetchKey]);

  const retry = () => setRefetchKey((k) => k + 1);

  const filteredSorted = useMemo(() => {
    const pnlOf = (t: TradeWithScreenshot) => (t.net_pnl ?? t.pnl ?? 0);
    const filtered = trades.filter((t) => {
      if (filter === "all") return true;
      if (filter === "wins") return pnlOf(t) > 0;
      return pnlOf(t) < 0;
    });
    if (sort === "best") return [...filtered].sort((a, b) => pnlOf(b) - pnlOf(a));
    if (sort === "worst") return [...filtered].sort((a, b) => pnlOf(a) - pnlOf(b));
    return [...filtered].sort((a, b) => new Date(b.entry_at).getTime() - new Date(a.entry_at).getTime());
  }, [trades, sort, filter]);

  if (authLoading) return <DashboardSkeleton />;

  return (
    <AppShell pageTitle="Скриншоты сделок">
      <div className="p-6 md:p-8 max-w-7xl mx-auto">
        <AnalysisPageHeader
          title="Галерея скринов"
          subtitle="Визуальный архив твоих сделок. Учиться на лучших и худших — самый быстрый способ расти."
          Icon={ImageIcon}
          accentColor="violet"
        />

        {!user ? (
          <Empty text="Войдите, чтобы увидеть свои скриншоты." />
        ) : error ? (
          <DataError error={error} onRetry={retry} />
        ) : loading ? (
          <DashboardSkeleton />
        ) : trades.length === 0 ? (
          <Empty text="Пока нет ни одного скриншота. Прикладывай скрин при добавлении сделки — он появится здесь." />
        ) : (
          <>
            {/* Toolbar */}
            <div className="flex flex-wrap items-center gap-3 mb-5">
              <FilterTabs filter={filter} setFilter={setFilter} />
              <div className="ml-auto flex items-center gap-1.5">
                <SortBtn label="Лучшие" active={sort === "best"} onClick={() => setSort("best")} />
                <SortBtn label="Худшие" active={sort === "worst"} onClick={() => setSort("worst")} />
                <SortBtn label="Новые" active={sort === "recent"} onClick={() => setSort("recent")} />
              </div>
            </div>

            <div className="text-[12px] text-[var(--text-tertiary)] mb-3">
              {filteredSorted.length} скрин{filteredSorted.length === 1 ? "" : filteredSorted.length < 5 ? "а" : "ов"}
            </div>

            {/* Grid */}
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
              {filteredSorted.map((t) => (
                <ScreenshotCard
                  key={t.id}
                  trade={t}
                  formatCurrency={formatCurrency}
                  onClick={() => setLightbox(t)}
                />
              ))}
            </div>
          </>
        )}

        {/* Lightbox */}
        {lightbox && (
          <Lightbox trade={lightbox} formatCurrency={formatCurrency} onClose={() => setLightbox(null)} />
        )}
      </div>
    </AppShell>
  );
}

function ScreenshotCard({
  trade,
  formatCurrency,
  onClick,
}: {
  trade: TradeWithScreenshot;
  formatCurrency: (n: number) => string;
  onClick: () => void;
}) {
  const pnl = trade.net_pnl ?? trade.pnl ?? 0;
  const isWin = pnl > 0;
  const url = trade.screenshot_url?.startsWith("http")
    ? trade.screenshot_url
    : getApiUrl(trade.screenshot_url || "");

  return (
    <button
      type="button"
      onClick={onClick}
      className="group rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--surface-1)] overflow-hidden hover:border-[var(--border-strong)] transition-colors text-left"
    >
      {/* Image */}
      <div className="aspect-video bg-[var(--surface-2)] relative overflow-hidden">
        {trade.screenshot_url ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={url}
            alt={`${trade.symbol} ${trade.direction}`}
            className="w-full h-full object-cover transition-transform group-hover:scale-105"
          />
        ) : (
          <div className="w-full h-full flex items-center justify-center text-[var(--text-tertiary)]">
            <ImageIcon size={28} />
          </div>
        )}
        {/* PnL badge overlay */}
        <div
          className={`absolute top-2 right-2 px-2 py-1 rounded-[var(--radius-pill)] text-[12px] font-bold backdrop-blur-md ${
            isWin
              ? "bg-[var(--success)]/90 text-white"
              : "bg-[var(--danger)]/90 text-white"
          }`}
        >
          {pnl >= 0 ? "+" : ""}{formatCurrency(pnl)}
        </div>
      </div>

      {/* Meta */}
      <div className="p-3">
        <div className="flex items-center gap-2 mb-1">
          <span className="font-bold text-[14px]">{trade.symbol}</span>
          <span
            className={`text-[10px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded-[var(--radius-pill)] ${
              trade.direction.toUpperCase() === "LONG"
                ? "bg-[var(--success-soft)] text-[var(--success)]"
                : "bg-[var(--danger-soft)] text-[var(--danger)]"
            }`}
          >
            {trade.direction}
          </span>
          {trade.setup_name && (
            <span className="text-[11px] text-[var(--text-tertiary)] truncate">{trade.setup_name}</span>
          )}
        </div>
        <div className="text-[11px] text-[var(--text-tertiary)]">
          {new Date(trade.entry_at).toLocaleDateString("ru-RU", { day: "2-digit", month: "long" })}
        </div>
      </div>
    </button>
  );
}

function Lightbox({
  trade,
  formatCurrency,
  onClose,
}: {
  trade: TradeWithScreenshot;
  formatCurrency: (n: number) => string;
  onClose: () => void;
}) {
  const pnl = trade.net_pnl ?? trade.pnl ?? 0;
  const isWin = pnl > 0;
  const url = trade.screenshot_url?.startsWith("http")
    ? trade.screenshot_url
    : getApiUrl(trade.screenshot_url || "");

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="relative max-w-4xl w-full max-h-[90vh] flex flex-col bg-[var(--surface-2)] rounded-[var(--radius-xl)] overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-[var(--border)]">
          <div>
            <div className="flex items-center gap-2">
              <span className="text-[18px] font-bold">{trade.symbol}</span>
              <span
                className={`text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-[var(--radius-pill)] ${
                  trade.direction.toUpperCase() === "LONG"
                    ? "bg-[var(--success-soft)] text-[var(--success)]"
                    : "bg-[var(--danger-soft)] text-[var(--danger)]"
                }`}
              >
                {trade.direction}
              </span>
              <span
                className={`text-[16px] font-bold tabular-nums flex items-center gap-1 ${isWin ? "text-[var(--success)]" : "text-[var(--danger)]"}`}
              >
                {isWin ? <TrendingUp size={14} /> : <TrendingDown size={14} />}
                {pnl >= 0 ? "+" : ""}{formatCurrency(pnl)}
              </span>
            </div>
            <div className="text-[12px] text-[var(--text-tertiary)] mt-1">
              {trade.setup_name || "Без сетапа"} · {new Date(trade.entry_at).toLocaleString("ru-RU")}
            </div>
          </div>
          <button onClick={onClose} className="btn-icon" aria-label="Закрыть">
            ✕
          </button>
        </div>

        {/* Image */}
        <div className="flex-1 overflow-auto bg-black/20 flex items-center justify-center">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={url} alt={trade.symbol} className="max-w-full max-h-[60vh] object-contain" />
        </div>

        {/* Notes */}
        {trade.notes && (
          <div className="p-4 border-t border-[var(--border)] text-[13px] text-[var(--text-secondary)] max-h-[20vh] overflow-y-auto">
            {trade.notes}
          </div>
        )}
      </div>
    </div>
  );
}

function FilterTabs({ filter, setFilter }: { filter: FilterMode; setFilter: (f: FilterMode) => void }) {
  return (
    <div className="flex items-center gap-1 p-1 rounded-[var(--radius-pill)] bg-[var(--surface-2)]">
      <FilterTab active={filter === "all"} onClick={() => setFilter("all")}>Все</FilterTab>
      <FilterTab active={filter === "wins"} onClick={() => setFilter("wins")} tone="success">Прибыльные</FilterTab>
      <FilterTab active={filter === "losses"} onClick={() => setFilter("losses")} tone="danger">Убыточные</FilterTab>
    </div>
  );
}

function FilterTab({ children, active, onClick, tone }: { children: React.ReactNode; active: boolean; onClick: () => void; tone?: "success" | "danger" }) {
  const activeBg = tone === "success" ? "bg-[var(--success-soft)] text-[var(--success)]" : tone === "danger" ? "bg-[var(--danger-soft)] text-[var(--danger)]" : "bg-[var(--accent-soft)] text-[var(--accent)]";
  return (
    <button
      type="button"
      onClick={onClick}
      className={`px-3 py-1.5 rounded-[var(--radius-pill)] text-[12px] font-medium transition-colors ${
        active ? activeBg : "text-[var(--text-secondary)] hover:text-[var(--foreground)]"
      }`}
    >
      {children}
    </button>
  );
}

function SortBtn({ label, active, onClick }: { label: string; active: boolean; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`px-3 py-1.5 rounded-[var(--radius-md)] text-[12px] font-medium border transition-colors ${
        active
          ? "border-[var(--accent)] bg-[var(--accent-soft)] text-[var(--accent)]"
          : "border-[var(--border)] text-[var(--text-secondary)] hover:border-[var(--border-strong)]"
      }`}
    >
      {label}
    </button>
  );
}

function Empty({ text }: { text: string }) {
  return (
    <div className="rounded-[var(--radius-xl)] border border-[var(--border)] bg-[var(--surface-1)] p-10 text-center">
      <div className="w-12 h-12 mx-auto mb-3 rounded-full bg-[var(--surface-2)] flex items-center justify-center text-[var(--text-tertiary)]">
        <ImageIcon size={20} />
      </div>
      <p className="text-[14px] text-[var(--text-secondary)] max-w-sm mx-auto">{text}</p>
    </div>
  );
}
