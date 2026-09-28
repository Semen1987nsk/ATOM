"use client";

import { useEffect, useRef } from "react";
import { heroEquity } from "../data/hero-equity-snapshot";

type Props = { width?: number; height?: number };

export function HeroEquityCurve({ width = 280, height = 140 }: Props) {
  const pathRef = useRef<SVGPathElement | null>(null);

  const n = heroEquity.length;
  const max = Math.max(...heroEquity);
  const min = Math.min(...heroEquity);
  const range = max - min || 1;

  const points = heroEquity.map((v, i) => {
    const x = (i / (n - 1)) * width;
    const y = height - ((v - min) / range) * (height - 10) - 5;
    return [x, y] as const;
  });

  const pathD = points
    .map(([x, y], i) => (i === 0 ? `M${x},${y}` : `L${x},${y}`))
    .join(" ");
  const fillD = `${pathD} L${width},${height} L0,${height} Z`;

  const [endX, endY] = points[points.length - 1];

  useEffect(() => {
    const el = pathRef.current;
    if (!el) return;
    const len = el.getTotalLength();
    el.style.setProperty("--curve-length", String(len));
    el.style.strokeDasharray = String(len);
    el.style.strokeDashoffset = String(len);
    void el.getBoundingClientRect();
    el.classList.add("uplift-curve-animate");
  }, []);

  return (
    <figure className="m-0 p-0">
      <svg
        width="100%"
        viewBox={`0 0 ${width} ${height}`}
        preserveAspectRatio="xMidYMid meet"
        role="img"
        aria-label="Кривая капитала когорты — 60 закрытых сделок, апрель 2026"
      >
        <defs>
          <linearGradient id="hero-equity-fill" x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" stopColor="var(--orange)" stopOpacity="0.20" />
            <stop offset="100%" stopColor="var(--orange)" stopOpacity="0" />
          </linearGradient>
        </defs>
        <path d={fillD} fill="url(#hero-equity-fill)" />
        <path
          ref={pathRef}
          d={pathD}
          stroke="var(--orange)"
          strokeWidth="2"
          fill="none"
          style={{ strokeDasharray: 9999, strokeDashoffset: 9999 }}
        />
        <circle cx={endX} cy={endY} r="3" fill="var(--orange)" />
      </svg>
      <figcaption
        className="text-[11px] italic mt-2 leading-snug"
        style={{ fontFamily: "var(--font-serif), Georgia, serif", color: "var(--paper-on-dark-3)" }}
      >
        cohort · 60 закрытых сделок · апрель 2026
      </figcaption>
    </figure>
  );
}
