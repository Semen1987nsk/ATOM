"use client";
import { useQuery } from "@tanstack/react-query";
import { tickerFallback, type TickerItem } from "../data/ticker-fallback";

type Response = { stale: boolean; tickers: TickerItem[]; fallback?: boolean };

async function fetchTicker(): Promise<TickerItem[]> {
  const r = await fetch("/api/landing/ticker");
  if (!r.ok) throw new Error("ticker fetch failed");
  const body: Response = await r.json();
  if (body.fallback || body.tickers.length === 0) return [...tickerFallback];
  return body.tickers;
}

export function LiveTicker() {
  const { data, isError } = useQuery({
    queryKey: ["landing-ticker"],
    queryFn: fetchTicker,
    refetchInterval: 60_000,
    refetchOnWindowFocus: false,
    staleTime: 30_000,
  });

  const items = data ?? (isError ? [...tickerFallback] : [...tickerFallback]);
  const isLive = !!data && !isError;

  return (
    <div
      className="px-6 lg:px-12 py-2 border-b border-[var(--rule)]"
      style={{ background: "rgba(20,17,11,0.025)" }}
    >
      <div className="max-w-[1200px] mx-auto flex flex-wrap items-center gap-x-7 gap-y-1 overflow-x-auto">
        {items.map((t, i) => (
          <div key={t.symbol} className="num text-[12px] inline-flex items-baseline gap-2 whitespace-nowrap">
            {i === 0 && isLive && (
              <span
                className="inline-block w-[5px] h-[5px] rounded-full"
                style={{
                  background: "var(--profit)",
                  animation: "maatt-pulse 1.6s infinite",
                }}
                aria-label="live"
              />
            )}
            <span className="text-[var(--ink-3)] tracking-wider">{t.symbol}</span>
            <span className="text-[var(--ink)] font-medium">{t.last.toLocaleString("ru-RU", { maximumFractionDigits: 2 })}</span>
            <span style={{ color: t.change_pct >= 0 ? "var(--profit)" : "var(--loss)" }}>
              {t.change_pct >= 0 ? "+" : ""}{t.change_pct.toFixed(2)}%
            </span>
          </div>
        ))}
        <div className="num text-[11px] text-[var(--ink-3)] ml-auto whitespace-nowrap">
          MSK · {new Date().toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" })}
        </div>
      </div>
      <style jsx global>{`
        @keyframes maatt-pulse {
          0%   { box-shadow: 0 0 0 0 rgba(31, 106, 71, 0.30); }
          70%  { box-shadow: 0 0 0 6px rgba(31, 106, 71, 0.00); }
          100% { box-shadow: 0 0 0 0 rgba(31, 106, 71, 0.00); }
        }
        @media (prefers-reduced-motion: reduce) {
          [aria-label="live"] { animation: none !important; }
        }
      `}</style>
    </div>
  );
}
