"use client";
/**
 * AnalysisPageHeader — единый заголовок для страниц /analysis/*
 *
 * Title + subtitle + опциональные правые контролы (Recalculate, Export, ...).
 * Не перетаскивает FilterPanel внутрь, чтобы у каждой страницы был выбор:
 * показывать общий FilterPanel или собственные под-фильтры (как у MAE/MFE).
 */
import type { ReactNode } from "react";
import { LucideIcon } from "lucide-react";

interface Props {
  title: string;
  subtitle?: string;
  Icon?: LucideIcon;
  /** Цвет акцент-чипа возле иконки. */
  accentColor?: "indigo" | "rose" | "violet" | "emerald" | "amber";
  right?: ReactNode;
}

const ACCENT_BG: Record<NonNullable<Props["accentColor"]>, string> = {
  indigo: "bg-[var(--accent-soft)] text-[var(--accent)]",
  rose: "bg-[var(--danger-soft)] text-[var(--danger)]",
  violet: "bg-[#6d28d922] text-[#a78bfa]",
  emerald: "bg-[var(--success-soft)] text-[var(--success)]",
  amber: "bg-[var(--warning-soft)] text-[var(--warning)]",
};

export function AnalysisPageHeader({
  title,
  subtitle,
  Icon,
  accentColor = "indigo",
  right,
}: Props) {
  return (
    <div className="mb-6 flex items-start justify-between gap-4 flex-wrap">
      <div className="flex items-start gap-3 min-w-0">
        {Icon && (
          <div
            className={`w-10 h-10 flex-shrink-0 rounded-[var(--radius-lg)] flex items-center justify-center ${ACCENT_BG[accentColor]}`}
          >
            <Icon size={20} />
          </div>
        )}
        <div className="min-w-0">
          <h1 className="text-2xl md:text-3xl font-bold tracking-tight leading-tight">{title}</h1>
          {subtitle && (
            <p className="text-[14px] text-[var(--text-secondary)] mt-1 leading-relaxed">
              {subtitle}
            </p>
          )}
        </div>
      </div>
      {right && <div className="flex items-center gap-2 flex-shrink-0">{right}</div>}
    </div>
  );
}
