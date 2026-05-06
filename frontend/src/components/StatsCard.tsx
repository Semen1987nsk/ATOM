'use client';

import React, { useState, useRef } from 'react';
import { createPortal } from 'react-dom';
import { HelpCircle, ExternalLink, TrendingUp, TrendingDown } from 'lucide-react';
import Link from 'next/link';

interface StatsCardProps {
  title: string;
  value: string | number;
  description?: string;
  highlight?: string;
  trend?: 'up' | 'down';
  icon?: React.ReactNode;
  tooltipText?: string;
  className?: string;
  manualAnchor?: string;
  secondaryValue?: string;
  secondaryLabel?: string;
}

/**
 * Tooltip с Portal — рендерится в body, чтобы не зажиматься overflow карточки.
 */
const Tooltip: React.FC<{
  text: string;
  position: { top: number; left: number };
  isVisible: boolean;
}> = ({ text, position, isVisible }) => {
  if (typeof document === 'undefined') return null;

  return createPortal(
    <div
      role="tooltip"
      className={`
        fixed w-72 p-3
        bg-[var(--surface-2)] border border-[var(--border-strong)]
        rounded-[var(--radius-md)] shadow-[var(--shadow-lg)]
        transition-opacity duration-150
        pointer-events-none
        ${isVisible ? 'opacity-100 visible' : 'opacity-0 invisible'}
      `}
      style={{
        top: position.top,
        left: position.left,
        zIndex: 99999,
      }}
    >
      <div className="text-[11px] font-semibold uppercase tracking-wider text-[var(--text-tertiary)] mb-1.5">
        Подсказка
      </div>
      <p className="text-[13px] text-[var(--foreground)] leading-relaxed">{text}</p>
    </div>,
    document.body,
  );
};

export const StatsCard: React.FC<StatsCardProps> = ({
  title,
  value,
  description,
  highlight,
  trend,
  icon,
  tooltipText,
  className = '',
  manualAnchor,
  secondaryValue,
  secondaryLabel,
}) => {
  const [showTooltip, setShowTooltip] = useState(false);
  const [tooltipPosition, setTooltipPosition] = useState({ top: 0, left: 0 });

  const updateTooltipPosition = (element: HTMLButtonElement) => {
    const targetRect = element.getBoundingClientRect();
    const tooltipWidth = 288;
    const tooltipHeight = 100;
    const padding = 16;

    let top = targetRect.top - tooltipHeight - 12;
    let left = targetRect.left + targetRect.width / 2 - tooltipWidth / 2;

    if (top < padding) top = targetRect.bottom + 8;
    if (left + tooltipWidth > window.innerWidth - padding) {
      left = window.innerWidth - tooltipWidth - padding;
    }
    if (left < padding) left = padding;

    setTooltipPosition({ top, left });
  };

  const handleTooltipShow = (
    event: React.MouseEvent<HTMLButtonElement> | React.FocusEvent<HTMLButtonElement>,
  ) => {
    updateTooltipPosition(event.currentTarget);
    setShowTooltip(true);
  };

  const valueToneClass =
    trend === 'up'
      ? 'text-[var(--success)]'
      : trend === 'down'
        ? 'text-[var(--danger)]'
        : 'text-[var(--foreground)]';

  return (
    <div className={`cyber-card p-5 flex flex-col gap-2 ${className}`}>
      {/* Header: title (link to manual) + icons */}
      <div className="flex items-start justify-between gap-2">
        {manualAnchor ? (
          <Link
            href={`/manual#${manualAnchor}`}
            className="group inline-flex items-center gap-1 text-[12px] font-medium text-[var(--text-secondary)] hover:text-[var(--accent)] transition-colors no-underline"
            title="Открыть в руководстве"
          >
            {title}
            <ExternalLink size={10} className="opacity-0 group-hover:opacity-60 transition-opacity" />
          </Link>
        ) : (
          <span className="text-[12px] font-medium text-[var(--text-secondary)]">{title}</span>
        )}

        <div className="flex items-center gap-1.5 text-[var(--text-tertiary)]">
          {tooltipText && (
            <button
              type="button"
              onMouseEnter={handleTooltipShow}
              onMouseLeave={() => setShowTooltip(false)}
              onFocus={handleTooltipShow}
              onBlur={() => setShowTooltip(false)}
              className="hover:text-[var(--foreground)] transition-colors focus:outline-none focus:text-[var(--accent)]"
              aria-label="Показать подсказку"
            >
              <HelpCircle size={13} strokeWidth={1.6} />
            </button>
          )}
          {icon && <div className="text-[var(--accent)] opacity-70">{icon}</div>}
        </div>
      </div>

      {/* Value — крупная, tabular-nums для выравнивания цифр в столбцах */}
      <div className={`text-[26px] font-bold leading-none tracking-tight tabular-nums ${valueToneClass}`}>
        {value}
      </div>

      {/* Description / trend */}
      {description && (
        <div className="flex items-center gap-1.5 text-[12px] text-[var(--text-tertiary)] min-h-[18px]">
          {trend === 'up' && <TrendingUp size={12} className="text-[var(--success)] flex-shrink-0" />}
          {trend === 'down' && <TrendingDown size={12} className="text-[var(--danger)] flex-shrink-0" />}
          <span className="truncate">{description}</span>
        </div>
      )}

      {/* Highlight badge — для важных аномалий типа "PF<1, не торговать" */}
      {highlight && (
        <div
          className={`mt-1 inline-flex items-center gap-1.5 px-2.5 py-1 rounded-[var(--radius-pill)] text-[11px] font-medium w-fit ${
            trend === 'down'
              ? 'bg-[var(--danger-soft)] text-[var(--danger)]'
              : 'bg-[var(--success-soft)] text-[var(--success)]'
          }`}
        >
          {highlight}
        </div>
      )}

      {/* Secondary метрика (например, R-метод vs PnL-метод для Optimal F) */}
      {secondaryValue && (
        <div className="mt-2 pt-2 border-t border-[var(--border)] flex justify-between items-center text-[12px]">
          <span className="text-[var(--text-tertiary)]">{secondaryLabel || 'Альт. метод:'}</span>
          <span className="font-medium tabular-nums text-[var(--text-secondary)]">{secondaryValue}</span>
        </div>
      )}

      {tooltipText && (
        <Tooltip text={tooltipText} position={tooltipPosition} isVisible={showTooltip} />
      )}
    </div>
  );
};
