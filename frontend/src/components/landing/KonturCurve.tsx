/**
 * Декоративная SVG-кривая в стиле kontur.ru.
 * Тонкая S-образная линия в углу секции — единственный декор лендинга.
 *
 * Variant определяет угол: tr/tl/br/bl. Цвет — от родителя (currentColor)
 * или явно через className. Размер задаётся через className.
 */
type Props = {
  variant?: 'tr' | 'br' | 'bl' | 'tl';
  className?: string;
  opacity?: number;
};

export function KonturCurve({ variant = 'br', className = '', opacity = 0.5 }: Props) {
  // S-кривая 320×280, рисуем как path. Поворот через transform делаем
  // на CSS уровне (ниже), не пересчитывая координаты.
  const rotation = {
    br: 'rotate(0deg)',
    tr: 'rotate(-90deg)',
    tl: 'rotate(180deg)',
    bl: 'rotate(90deg)',
  }[variant];

  return (
    <svg
      className={`kontur-curve kontur-curve-${variant} ${className}`}
      width="320"
      height="280"
      viewBox="0 0 320 280"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      style={{ transform: rotation, opacity }}
      aria-hidden="true"
    >
      <path
        d="M 20 260 C 20 180, 80 140, 160 140 S 300 100, 300 20"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
      />
      <circle cx="300" cy="20" r="4" fill="currentColor" />
    </svg>
  );
}
