/**
 * Custom SVG-иллюстрация пера Маатт.
 * Hand-tuned path + золотой gradient + тонкие "бородки" пера.
 * Единственное декоративное изображение на лендинге.
 */
type Props = { width?: number; className?: string };

export function ManuscriptFeather({ width = 120, className }: Props) {
  const h = (width * 320) / 120;
  return (
    <svg
      width={width}
      height={h}
      viewBox="0 0 120 320"
      fill="none"
      className={className}
      role="img"
      aria-label="Перо Маатт — символ меры и дисциплины"
    >
      <defs>
        <linearGradient id="feather-grad" x1="0" x2="1" y1="0" y2="1">
          <stop offset="0%" stopColor="var(--accent)" stopOpacity="0.85" />
          <stop offset="100%" stopColor="var(--ink)" stopOpacity="0.45" />
        </linearGradient>
      </defs>
      <path
        d="M60 6 C 48 50, 30 110, 18 200 C 14 230, 22 250, 36 256 L 60 314 L 84 256 C 98 250, 106 230, 102 200 C 90 110, 72 50, 60 6 Z"
        fill="url(#feather-grad)"
        opacity="0.55"
      />
      <line x1="60" y1="14" x2="60" y2="316" stroke="var(--ink)" strokeWidth="0.8" />
      <g stroke="var(--ink)" strokeWidth="0.5" opacity="0.55">
        <line x1="60" y1="40" x2="42" y2="62" /><line x1="60" y1="40" x2="78" y2="62" />
        <line x1="60" y1="64" x2="38" y2="92" /><line x1="60" y1="64" x2="82" y2="92" />
        <line x1="60" y1="92" x2="32" y2="128" /><line x1="60" y1="92" x2="88" y2="128" />
        <line x1="60" y1="120" x2="26" y2="160" /><line x1="60" y1="120" x2="94" y2="160" />
        <line x1="60" y1="148" x2="22" y2="190" /><line x1="60" y1="148" x2="98" y2="190" />
        <line x1="60" y1="178" x2="20" y2="220" /><line x1="60" y1="178" x2="100" y2="220" />
        <line x1="60" y1="210" x2="26" y2="246" /><line x1="60" y1="210" x2="94" y2="246" />
      </g>
    </svg>
  );
}
