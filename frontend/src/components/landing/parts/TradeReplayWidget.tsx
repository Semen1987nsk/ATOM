"use client";
import { useState, useMemo } from "react";
import { replayCandles, replayPoints } from "../data/trade-replay-sample";

/**
 * Mini Trade Replay для секции 03.
 * Slider по индексу свечи; точки entry/exit/stop/take подсвечиваются,
 * exit-маркер прыгает в позицию текущей свечи.
 */
export function TradeReplayWidget() {
  const [idx, setIdx] = useState(replayCandles.length - 1);
  const W = 640, H = 260, padL = 40, padR = 12, padT = 12, padB = 40;
  const innerW = W - padL - padR, innerH = H - padT - padB;

  const { max, range, xStep } = useMemo(() => {
    const prices = replayCandles.flatMap((c) => [c.h, c.l]);
    const allPointPrices = replayPoints.map((p) => p.price);
    const min = Math.min(...prices, ...allPointPrices);
    const max = Math.max(...prices, ...allPointPrices);
    const range = max - min || 1;
    const xStep = innerW / replayCandles.length;
    return { max, range, xStep };
  }, [innerW]);

  const xFor = (i: number) => padL + i * xStep + xStep / 2;
  const yFor = (p: number) => padT + ((max - p) / range) * innerH;

  const entry = replayPoints.find((p) => p.type === "entry")!;
  const stop = replayPoints.find((p) => p.type === "stop")!;
  const take = replayPoints.find((p) => p.type === "take")!;

  const currentCandle = replayCandles[idx];
  const currentPrice = currentCandle.c;
  const pnlR = (currentPrice - entry.price) / Math.abs(entry.price - stop.price);

  return (
    <figure className="m-0 p-0">
      <svg viewBox={`0 0 ${W} ${H}`} width="100%" role="img" aria-label="Trade Replay — навигация по сделке через slider">
        <line x1={padL} x2={W - padR} y1={yFor(take.price)} y2={yFor(take.price)} stroke="var(--profit)" strokeWidth="0.6" strokeDasharray="3,3" opacity="0.7" />
        <line x1={padL} x2={W - padR} y1={yFor(entry.price)} y2={yFor(entry.price)} stroke="var(--ink)" strokeWidth="0.7" />
        <line x1={padL} x2={W - padR} y1={yFor(stop.price)} y2={yFor(stop.price)} stroke="var(--loss)" strokeWidth="0.6" strokeDasharray="3,3" opacity="0.7" />

        {[take.price, entry.price, stop.price].map((p, i) => (
          <text key={i} x={padL - 6} y={yFor(p) + 3} textAnchor="end" fontSize="9" fill="var(--ink-3)" fontFamily="var(--font-mono), monospace">
            {p.toFixed(1)}
          </text>
        ))}

        {replayCandles.map((c, i) => {
          const x = xFor(i);
          const up = c.c >= c.o;
          const color = up ? "var(--profit)" : "var(--loss)";
          const bodyW = Math.max(5, xStep * 0.55);
          const bodyTop = Math.min(yFor(c.o), yFor(c.c));
          const bodyBottom = Math.max(yFor(c.o), yFor(c.c));
          const dim = i > idx;
          return (
            <g key={i} opacity={dim ? 0.18 : 1}>
              <line x1={x} x2={x} y1={yFor(c.h)} y2={yFor(c.l)} stroke={color} strokeWidth="1" />
              <rect x={x - bodyW / 2} y={bodyTop} width={bodyW} height={Math.max(1, bodyBottom - bodyTop)} fill={color} />
            </g>
          );
        })}

        <circle cx={xFor(replayCandles.findIndex((c) => c.t === entry.t))} cy={yFor(entry.price)} r="5" fill="var(--ink)" stroke="var(--paper)" strokeWidth="1.5" />
        <circle cx={xFor(idx)} cy={yFor(currentPrice)} r="5" fill="var(--accent)" stroke="var(--paper)" strokeWidth="1.5" />
      </svg>

      <div className="px-2 mt-2 flex items-center gap-4">
        <input
          type="range"
          min={0}
          max={replayCandles.length - 1}
          value={idx}
          onChange={(e) => setIdx(Number(e.target.value))}
          aria-label="Точка во времени"
          aria-valuetext={`${idx + 1} из ${replayCandles.length} — ${new Date(currentCandle.t).toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" })}`}
          className="flex-1 accent-[var(--accent)]"
        />
        <div className="num text-[12px] text-[var(--ink)] min-w-[88px] text-right">
          {pnlR >= 0 ? "+" : ""}{pnlR.toFixed(2)} R
        </div>
      </div>

      <figcaption
        className="text-[11px] italic text-[var(--ink-3)] mt-3"
        style={{ fontFamily: "var(--font-serif), Georgia, serif" }}
      >
        Двигай ползунок: видно момент, где сделка дала максимум R и где закрыта на самом деле.
      </figcaption>
    </figure>
  );
}
