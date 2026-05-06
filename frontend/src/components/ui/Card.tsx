import { forwardRef, type HTMLAttributes, type ReactNode } from "react";
import { clsx } from "clsx";

type Padding = "none" | "sm" | "md" | "lg";
type Variant = "default" | "elevated";

export interface CardProps extends HTMLAttributes<HTMLDivElement> {
  variant?: Variant;
  padding?: Padding;
  interactive?: boolean;
  children: ReactNode;
}

const paddingClass: Record<Padding, string> = {
  none: "",
  sm: "p-4",
  md: "p-5",
  lg: "p-6",
};

/**
 * Карточка-контейнер. Стиль определяется .cyber-card / .card-elevated
 * из globals.css (back-compat — те же классы используются по всему legacy-коду).
 */
export const Card = forwardRef<HTMLDivElement, CardProps>(function Card(
  {
    variant = "default",
    padding = "md",
    interactive = false,
    className,
    children,
    ...rest
  },
  ref,
) {
  return (
    <div
      ref={ref}
      className={clsx(
        variant === "elevated" ? "card-elevated" : "cyber-card",
        paddingClass[padding],
        interactive && "cursor-pointer",
        className,
      )}
      {...rest}
    >
      {children}
    </div>
  );
});

/**
 * Card.Header / .Body / .Footer — опциональные слоты для структурирования.
 * Не обязательны: если контент простой, кладите его прямо в Card.
 */
export function CardHeader({ className, children }: { className?: string; children: ReactNode }) {
  return <div className={clsx("mb-3 flex items-center justify-between gap-2", className)}>{children}</div>;
}

export function CardTitle({ className, children }: { className?: string; children: ReactNode }) {
  return <h3 className={clsx("text-base font-semibold", className)}>{children}</h3>;
}

export function CardSubtitle({ className, children }: { className?: string; children: ReactNode }) {
  return <p className={clsx("text-[13px] text-[var(--text-secondary)]", className)}>{children}</p>;
}
