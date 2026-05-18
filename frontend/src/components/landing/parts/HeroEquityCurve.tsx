import { heroEquity } from "../data/hero-equity-snapshot";

/**
 * Mini equity curve в Hero. SSR, static path из snapshot.
 * Без анимации reveal.
 */
type Props = { width?: number; height?: number };

export function HeroEquityCurve({ width = 280, height = 140 }: Props) {
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
            <stop offset="0%" stopColor="var(--ink)" stopOpacity="0.18" />
            <stop offset="100%" stopColor="var(--ink)" stopOpacity="0" />
          </linearGradient>
        </defs>
        <path d={fillD} fill="url(#hero-equity-fill)" />
        <path d={pathD} stroke="var(--ink)" strokeWidth="1.4" fill="none" />
        <circle cx={endX} cy={endY} r="3" fill="var(--accent)" />
      </svg>
      <figcaption
        className="text-[11px] italic text-[var(--ink-3)] mt-2 leading-snug"
        style={{ fontFamily: "var(--font-serif), Georgia, serif" }}
      >
        cohort · 60 закрытых сделок · апрель 2026
      </figcaption>
    </figure>
  );
}
