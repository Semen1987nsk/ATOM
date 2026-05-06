import { forwardRef, type HTMLAttributes, type ReactNode } from "react";
import { clsx } from "clsx";

type TileColor = "indigo" | "violet" | "emerald" | "rose" | "amber" | "sky" | "neutral";
type TileSize = "sm" | "md" | "lg";

export interface TileProps extends HTMLAttributes<HTMLDivElement> {
  /** Цвет заливки. Brand-индиго по умолчанию. */
  color?: TileColor;
  size?: TileSize;
  /** Заголовок плитки (большим) */
  title?: string;
  /** Подзаголовок / метрика */
  subtitle?: string;
  /** Иконка слева вверху */
  icon?: ReactNode;
  /** Если плитка кликабельная — callback */
  onClick?: () => void;
  children?: ReactNode;
}

const sizeClass: Record<TileSize, string> = {
  sm: "min-h-[120px] p-4",
  md: "min-h-[160px] p-6",
  lg: "min-h-[220px] p-8",
};

const titleSizeClass: Record<TileSize, string> = {
  sm: "text-lg",
  md: "text-xl",
  lg: "text-3xl",
};

/**
 * Bento-tile в стиле Контура — крупная цветная плитка с заголовком и опционально
 * подзаголовком/иконкой. Используется для дашборда, ключевых разделов.
 *
 * Цветовая логика: один цвет на одну сущность (например, "Открытые позиции"
 * всегда indigo, "P&L месяц" — emerald). Не смешивай больше 2-3 цветов на экран.
 */
export const Tile = forwardRef<HTMLDivElement, TileProps>(function Tile(
  { color = "indigo", size = "md", title, subtitle, icon, onClick, className, children, ...rest },
  ref,
) {
  const isClickable = !!onClick;
  return (
    <div
      ref={ref}
      onClick={onClick}
      role={isClickable ? "button" : undefined}
      tabIndex={isClickable ? 0 : undefined}
      onKeyDown={
        isClickable
          ? (e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                onClick?.();
              }
            }
          : undefined
      }
      className={clsx(
        "tile",
        `tile-${color}`,
        sizeClass[size],
        "flex flex-col justify-between",
        isClickable && "cursor-pointer",
        className,
      )}
      {...rest}
    >
      {(icon || title) && (
        <div className="flex items-start justify-between gap-3">
          {icon && <div className="flex-shrink-0 opacity-90">{icon}</div>}
        </div>
      )}
      <div className="flex flex-col gap-1">
        {title && (
          <div className={clsx("font-bold leading-tight", titleSizeClass[size])}>
            {title}
          </div>
        )}
        {subtitle && (
          <div className="text-sm opacity-80 leading-snug">{subtitle}</div>
        )}
        {children}
      </div>
    </div>
  );
});
