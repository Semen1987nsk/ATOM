'use client';

/**
 * PR 26 (Phase 3, D6) — ReconciliationBanner.
 *
 * Висит в header пока есть unresolved reconciliation breaks за последние 30 дней.
 * Soft warning per Phase 3 plan: не блокирует юзера, но не даёт забыть.
 *
 * Использование:
 *   <ReconciliationBanner />
 */

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { AlertTriangle, X } from 'lucide-react';
import { api } from '@/lib/apiClient';

type BannerState = {
  show: boolean;
  unresolved_breaks: number;
  last_run_at: string | null;
  last_status?: string;
};

const DISMISS_KEY = 'empirik_reconciliation_banner_dismissed_until';
const DISMISS_HOURS = 24;

function isDismissed(): boolean {
  if (typeof window === 'undefined') return false;
  const until = localStorage.getItem(DISMISS_KEY);
  if (!until) return false;
  try {
    return new Date(until).getTime() > Date.now();
  } catch {
    return false;
  }
}

export function ReconciliationBanner() {
  const [state, setState] = useState<BannerState | null>(null);
  const [dismissed, setDismissed] = useState(false);

  useEffect(() => {
    if (isDismissed()) {
      setDismissed(true);
      return;
    }
    api
      .get<BannerState>('/onboarding/reconciliation-banner')
      .then((r) => setState(r))
      .catch(() => setState(null));
  }, []);

  if (dismissed || !state || !state.show) return null;

  const handleDismiss = () => {
    const until = new Date(Date.now() + DISMISS_HOURS * 3600 * 1000).toISOString();
    localStorage.setItem(DISMISS_KEY, until);
    setDismissed(true);
  };

  return (
    <div className="bg-orange-500/10 border-b border-orange-500/30 px-4 py-2">
      <div className="max-w-7xl mx-auto flex items-center justify-between gap-3">
        <div className="flex items-center gap-2 text-sm">
          <AlertTriangle size={16} className="text-orange-400 shrink-0" />
          <span className="text-orange-200">
            Найдены расхождения с отчётом Tinkoff
            {state.unresolved_breaks > 0 && (
              <span className="opacity-80"> ({state.unresolved_breaks})</span>
            )}
          </span>
          <Link
            href="/onboarding/reconcile"
            className="text-orange-300 hover:text-orange-200 underline ml-1"
          >
            подробнее
          </Link>
          <span className="text-orange-300/60 mx-1">·</span>
          <a
            href="mailto:support@empirik.app?subject=Расхождение%20в%20reconciliation"
            className="text-orange-300 hover:text-orange-200 underline"
          >
            написать поддержке
          </a>
        </div>
        <button
          onClick={handleDismiss}
          className="text-orange-300/60 hover:text-orange-200 transition-colors"
          aria-label="Скрыть на 24 часа"
        >
          <X size={16} />
        </button>
      </div>
    </div>
  );
}
