"use client";
import { useQuery } from "@tanstack/react-query";
import { tickerFallback, type TickerItem } from "../data/ticker-fallback";
import { fetchWithTimeout } from "@/lib/fetchWithTimeout";

type Response = { stale: boolean; tickers: TickerItem[]; fallback?: boolean };

async function fetchTicker(): Promise<TickerItem[]> {
  const r = await fetchWithTimeout("/api/landing/ticker");
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
      aria-label="Биржевой тикер MOEX"
    >
      <div className="relative h-[38px] flex items-center">
        <div className="uplift-ticker-track" aria-hidden="false">
          {[...items, ...items].map((t, idx) => (
            <span key={`${t.symbol}-${idx}`} className="inline-flex items-center gap-2">
              <span className="font-semibold">{t.symbol}</span>
              <span>{t.last.toLocaleString("ru-RU", { maximumFractionDigits: 2 })}</span>
              <span>
                {t.change_pct >= 0 ? "▲" : "▼"} {Math.abs(t.change_pct).toFixed(2)}%
              </span>
              <span className="opacity-50 mx-2">·</span>
            </span>
          ))}
        </div>
      </div>
    </section>
  );
}
