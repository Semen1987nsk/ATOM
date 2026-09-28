'use client';

/**
 * CollapsibleSection — сворачиваемый блок с заголовком (PR 25).
 *
 * Используется для размещения «Расширенных метрик» (Optimal F, SQN, GHPR,
 * Z-Score, Tail Ratio, Risk of Ruin…) прямо на дашборде, но свёрнутыми
 * по умолчанию. Это компромисс между «всё на виду» и «прогрессивное
 * раскрытие»: метрики рядом для тех, кому нужны, но не загромождают
 * первый экран для daily-юзера.
 *
 * Состояние сохраняется в localStorage по `storageKey` — юзер один раз
 * развернул блок, и при следующих заходах он останется открытым.
 */

import { useState, useEffect } from 'react';
import { ChevronDown, ChevronRight } from 'lucide-react';

interface Props {
  title: string;
  subtitle?: string;
  storageKey: string;
  defaultOpen?: boolean;
  children: React.ReactNode;
}

export function CollapsibleSection({
  title,
  subtitle,
  storageKey,
  defaultOpen = false,
  children,
}: Props) {
  const [isOpen, setIsOpen] = useState(defaultOpen);
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => {
    try {
      const stored = localStorage.getItem(`collapsible:${storageKey}`);
      if (stored !== null) setIsOpen(stored === '1');
    } catch {
      // ignore localStorage errors (SSR / private mode)
    }
    setHydrated(true);
  }, [storageKey]);

  const toggle = () => {
    const next = !isOpen;
    setIsOpen(next);
    try {
      localStorage.setItem(`collapsible:${storageKey}`, next ? '1' : '0');
    } catch {
      // ignore
    }
  };

  return (
    <div className="rounded-[var(--radius-xl)] border border-[var(--border)] bg-[var(--surface)] overflow-hidden">
      <button
        type="button"
        onClick={toggle}
        className="w-full flex items-center justify-between gap-3 px-5 py-3 hover:bg-[var(--surface-hover)] transition-colors"
        aria-expanded={isOpen}
      >
        <div className="text-left">
          <div className="font-semibold text-base flex items-center gap-2">
            {isOpen ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
            {title}
          </div>
          {subtitle && (
            <div className="text-xs text-[var(--text-tertiary)] mt-0.5 ml-6">
              {subtitle}
            </div>
          )}
        </div>
      </button>
      {hydrated && isOpen && (
        <div className="px-5 pb-5 border-t border-[var(--border)]">
          <div className="pt-4">{children}</div>
        </div>
      )}
    </div>
  );
}
