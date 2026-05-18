"use client";
import { useMemo, useState } from "react";
import { sberCandles, type Candle } from "../data/sber-candles-2026-04-21";

// Pre-computed MAE/MFE для каждой свечи относительно одной симуляции trade entry.
// Это data для tooltip, не реальный AI расчёт — фиксированный example.
type Annotated = Candle & { mae_r: number; mfe_r: number };
const TRADE_ENTRY = 168.0;
const RISK_PER_R = 0.6;

function annotate(candles: ReadonlyArray<Candle>): Annotated[] {
  return candles.map((c) => ({
    ...c,
    mae_r: +((c.l - TRADE_ENTRY) / RISK_PER_R).toFixed(2),
    mfe_r: +((c.h - TRADE_ENTRY) / RISK_PER_R).toFixed(2),
  }));
}

export function InteractiveCandleChart() {
  const data = useMemo(() => annotate(sberCandles), []);
  const [hover, setHover] = useState<number | null>(null);

  const W = 640, H = 280, padL = 36, padR = 12, padT = 12, padB = 24;
  const innerW = W - padL - padR, innerH = H - padT - padB;
  const prices = data.flatMap((c) => [c.h, c.l]);
  const min = Math.min(...prices), max = Math.max(...prices);
  const range = max - min || 1;
  const xStep = innerW / data.length;

  return (
    <figure className="m-0 p-0">
      <svg
        viewBox={`0 0 ${W} ${H}`}
        width="100%"
        role="img"
        aria-label="Свечи SBER 21 апреля 2026 с MAE/MFE по часам"
        onMouseLeave={() => setHover(null)}
      >
        {/* y-axis labels */}
        {[0, 0.25, 0.5, 0.75, 1].map((f, i) => {
          const y = padT + innerH * f;
          const price = max - range * f;
          return (
            <g key={i}>
              <line x1={padL} x2={W - padR} y1={y} y2={y} stroke="var(--rule)" strokeWidth="1" />
              <text x={padL - 6} y={y + 3} textAnchor="end" fontSize="10" fill="var(--ink-3)" fontFamily="var(--font-mono), monospace">
                {price.toFixed(1)}
              </text>
            </g>
          );
        })}

        {data.map((c, i) => {
          const x = padL + i * xStep + xStep / 2;
          const yH = padT + ((max - c.h) / range) * innerH;
          const yL = padT + ((max - c.l) / range) * innerH;
          const yO = padT + ((max - c.o) / range) * innerH;
          const yC = padT + ((max - c.c) / range) * innerH;
          const bodyTop = Math.min(yO, yC);
          const bodyBottom = Math.max(yO, yC);
          const up = c.c >= c.o;
          const color = up ? "var(--profit)" : "var(--loss)";
          const bodyW = Math.max(6, xStep * 0.6);
          return (
            <g
              key={i}
              onMouseEnter={() => setHover(i)}
              style={{ cursor: "pointer" }}
            >
              <rect x={x - xStep / 2} y={padT} width={xStep} height={innerH} fill="transparent" />
              <line x1={x} x2={x} y1={yH} y2={yL} stroke={color} strokeWidth="1" />
              <rect
                x={x - bodyW / 2}
                y={bodyTop}
                width={bodyW}
                height={Math.max(1, bodyBottom - bodyTop)}
                fill={up ? color : color}
                opacity={hover === i ? 1 : 0.85}
              />
              <title>{`${new Date(c.t).toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" })} · O ${c.o} H ${c.h} L ${c.l} C ${c.c} · MFE ${c.h.toFixed(1)} MAE ${c.l.toFixed(1)}`}</title>
            </g>
          );
        })}

        {/* Hover tooltip */}
        {hover !== null && (() => {
          const c = data[hover];
          const x = padL + hover * xStep + xStep / 2;
          return (
            <g>
              <line x1={x} x2={x} y1={padT} y2={H - padB} stroke="var(--ink)" strokeWidth="0.5" strokeDasharray="2,3" />
              <rect x={x + 8} y={padT} width="116" height="64" fill="var(--paper)" stroke="var(--rule-strong)" />
              <text x={x + 16} y={padT + 16} fontSize="10" fill="var(--ink-3)" fontFamily="var(--font-mono), monospace">
                {new Date(c.t).toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" })}
              </text>
              <text x={x + 16} y={padT + 32} fontSize="11" fill="var(--ink)" fontFamily="var(--font-mono), monospace">
                MFE {c.mfe_r >= 0 ? "+" : ""}{c.mfe_r}R
              </text>
              <text x={x + 16} y={padT + 48} fontSize="11" fill="var(--ink)" fontFamily="var(--font-mono), monospace">
                MAE {c.mae_r}R
              </text>
            </g>
          );
        })()}
      </svg>
      <figcaption
        className="text-[11px] italic text-[var(--ink-3)] mt-3"
        style={{ fontFamily: "var(--font-serif), Georgia, serif" }}
      >
        SBER · 21 апреля 2026 · 1H · hover на свечу — точки MAE/MFE из реальной свечи
      </figcaption>
    </figure>
  );
}
