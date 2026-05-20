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

  return (
    <section
      data-section="live-ticker"
      className="uplift-ticker-strip overflow-hidden"
      style={{ backgroundColor: "#E84E1C", color: "#0a0a0a", borderTop: "1px solid #0a0a0a", borderBottom: "1px solid #0a0a0a" }}
      aria-label="Биржевой тикер MOEX"
    >
      <div className="relative h-9.5 flex items-center">
        <div
          className="uplift-ticker-track"
          aria-hidden="false"
          style={{
            display: "inline-flex",
            gap: "36px",
            whiteSpace: "nowrap",
            animation: "uplift-ticker-scroll 60s linear infinite",
            fontFamily: 'var(--font-mono, "JetBrains Mono", monospace)',
            fontWeight: 500,
            fontSize: "12px",
            letterSpacing: "0.04em",
          }}
        >
          {/* двойная копия списка для seamless loop при translateX(-50%) */}
          {[...items, ...items].map((t, idx) => (
            <span key={`${t.symbol}-${idx}`} className="inline-flex items-center gap-2">
              <span className="font-semibold">{t.symbol}</span>
              <span>{t.last.toLocaleString("ru-RU", { maximumFractionDigits: 2 })}</span>
              <span>
                {t.change_pct >= 0 ? "▲" : "▼"} {Math.abs(t.change_pct).toFixed(2)}%
              </span>
              <span style={{ opacity: 0.5, margin: "0 8px" }}>·</span>
            </span>
          ))}
        </div>
      </div>
      <style>{`
        @keyframes uplift-ticker-scroll {
          from { transform: translateX(0); }
          to   { transform: translateX(-50%); }
        }
        @media (prefers-reduced-motion: reduce) {
          [data-section="live-ticker"] .uplift-ticker-track {
            animation: none;
            transform: none;
          }
        }
      `}</style>
    </section>
  );
}
