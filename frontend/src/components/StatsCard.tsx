'use client';

import React, { useState, useRef } from 'react';
import { createPortal } from 'react-dom';
import { HelpCircle, ExternalLink } from 'lucide-react';
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
  manualAnchor?: string; // Ссылка на якорь в руководстве, напр. "optimal-f"
  secondaryValue?: string; // Второе значение для сравнения
  secondaryLabel?: string; // Подпись ко второму значению
}

// Tooltip компонент с Portal - рендерится вне DOM-дерева карточки
const Tooltip: React.FC<{
  text: string;
  position: { top: number; left: number };
  isVisible: boolean;
}> = ({ text, position, isVisible }) => {
  const tooltipRef = useRef<HTMLDivElement>(null);

  if (typeof document === 'undefined') return null;

  return createPortal(
    <div
      ref={tooltipRef}
      role="tooltip"
      className={`
        fixed w-72 p-4
        bg-card border-2 border-accent rounded-lg 
        shadow-lg
        transition-all duration-200 ease-out
        pointer-events-none
        ${isVisible 
          ? 'opacity-100 visible scale-100' 
          : 'opacity-0 invisible scale-95'
        }
      `}
      style={{ 
        top: position.top,
        left: position.left,
        zIndex: 99999,
      }}
    >
      {/* Заголовок */}
      <div className="flex items-center gap-2 mb-2 pb-2 border-b border-accent/30">
        <HelpCircle size={14} className="text-accent" />
        <span className="text-accent text-xs font-bold uppercase tracking-wider">Подсказка</span>
      </div>
      
      {/* Текст */}
      <p className="text-[13px] text-foreground leading-relaxed">
        {text}
      </p>
    </div>,
    document.body
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
  secondaryLabel
}) => {
  const [showTooltip, setShowTooltip] = useState(false);
  const [tooltipPosition, setTooltipPosition] = useState({ top: 0, left: 0 });
  const helpRef = useRef<HTMLButtonElement>(null);

  const updateTooltipPosition = (element: HTMLButtonElement) => {
    const targetRect = element.getBoundingClientRect();
    const tooltipWidth = 288;
    const tooltipHeight = 120;
    const padding = 16;

    let top = targetRect.top - tooltipHeight - 12;
    let left = targetRect.left + targetRect.width / 2 - tooltipWidth / 2;

    if (top < padding) {
      top = targetRect.top - 20;
      left = targetRect.left - tooltipWidth - 20;

      if (left < padding) {
        left = targetRect.right + 20;
      }
    }

    if (left + tooltipWidth > window.innerWidth - padding) {
      left = window.innerWidth - tooltipWidth - padding;
    }

    if (left < padding) {
      left = padding;
    }

    setTooltipPosition({ top, left });
  };

  const handleTooltipShow = (event: React.MouseEvent<HTMLButtonElement> | React.FocusEvent<HTMLButtonElement>) => {
    updateTooltipPosition(event.currentTarget);
    setShowTooltip(true);
  };

  return (
    <div className={`cyber-card p-6 flex flex-col gap-2 relative group ${className}`}>
      {/* Background glow effect on hover */}
      <div className="absolute inset-0 overflow-hidden rounded pointer-events-none">
        <div className="absolute -top-10 -right-10 w-24 h-24 bg-accent/0 group-hover:bg-accent/10 rounded-full blur-2xl transition-all duration-500" />
      </div>
      
      {/* Trend indicator line */}
      {trend && (
        <div 
          className={`absolute left-0 top-0 bottom-0 w-1 ${
            trend === 'up' 
              ? 'bg-gradient-to-b from-green-400 to-green-600' 
              : 'bg-gradient-to-b from-red-400 to-red-600'
          }`}
        />
      )}
      
      <div className="flex justify-between items-start relative z-10">
        {manualAnchor ? (
          <Link 
            href={`/manual#${manualAnchor}`}
            className="text-xs font-mono uppercase tracking-wider opacity-60 group-hover:opacity-100 group-hover:text-accent transition-all hover:underline flex items-center gap-1"
            title="Открыть в руководстве"
          >
            {title}
            <ExternalLink size={10} className="opacity-0 group-hover:opacity-60" />
          </Link>
        ) : (
          <span className="text-xs font-mono uppercase tracking-wider opacity-60 group-hover:opacity-80 transition-opacity">
            {title}
          </span>
        )}
        <div className="flex gap-2 items-center">
          {/* Help Icon */}
          {tooltipText && (
            <>
              <button
                ref={helpRef}
                onMouseEnter={handleTooltipShow}
                onMouseLeave={() => setShowTooltip(false)}
                onFocus={handleTooltipShow}
                onBlur={() => setShowTooltip(false)}
                className="text-gray-500 hover:text-accent transition-colors duration-200 focus:outline-none focus:text-accent"
                aria-label="Показать подсказку"
              >
                <HelpCircle size={14} strokeWidth={1.5} />
              </button>
              
              {/* Tooltip через Portal */}
              <Tooltip 
                text={tooltipText} 
                position={tooltipPosition}
                isVisible={showTooltip} 
              />
            </>
          )}
          {icon && (
            <div className="text-accent/60 group-hover:text-accent group-hover:scale-110 transition-all duration-300">
              {icon}
            </div>
          )}
        </div>
      </div>
      
      <div className="text-3xl font-bold tracking-tight text-neon group-hover:drop-shadow-[0_0_8px_rgba(0,255,159,0.5)] transition-all duration-300 relative z-10">
        {value}
      </div>
      
      {description && (
        <div className={`text-xs flex items-center gap-1 ${
          trend === 'up' ? 'text-green-400' : 
          trend === 'down' ? 'text-red-400' : 
          'opacity-40'
        }`}>
          {trend === 'up' && <span className="inline-block animate-bounce">↑</span>}
          {trend === 'down' && <span className="inline-block animate-bounce">↓</span>}
          {description}
        </div>
      )}
      
      {highlight && (
        <div className={`mt-1 px-2 py-1 rounded text-xs font-bold inline-flex items-center gap-1 w-fit ${
          trend === 'down' 
            ? 'bg-red-500/20 border border-red-500/40 text-red-400'
            : 'bg-green-500/20 border border-green-500/40 text-green-400'
        }`}>
          <span className={trend === 'down' ? 'text-red-500' : 'text-green-500'}>
            {trend === 'down' ? '⚠' : '▶'}
          </span>
          {highlight}
        </div>
      )}
      
      {/* Дополнительное значение (напр. второй метод расчёта) */}
      {secondaryValue && (
        <div className="mt-2 pt-2 border-t border-white/10 flex justify-between items-center text-xs">
          <span className="opacity-50">{secondaryLabel || 'Альт. метод:'}</span>
          <span className="font-mono text-accent/80">{secondaryValue}</span>
        </div>
      )}
    </div>
  );
};
