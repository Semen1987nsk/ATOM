'use client';

/**
 * TrialCountdownBanner — баннер обратного отсчёта последних дней trial.
 *
 * Эталон: .business/product/feature-canon/04-downgrade-experience.md
 * Решение: ADR-0005 (Reverse-Trial)
 *
 * Показывается только когда:
 *   - subscription.status === 'trial_active'
 *   - 0 < trial_days_left <= 7
 *
 * Не модальный, занимает ~48px вверху dashboard.
 * На D-1 (days_left === 1) — non-dismissable.
 *
 * DS:
 *   - <Clock /> из lucide (не эмодзи)
 *   - Фон var(--info) с opacity 0.10
 *   - Текст var(--foreground)
 *   - CTA-кнопка var(--accent) indigo
 */

import { useState } from 'react';
import { Clock, X } from 'lucide-react';
import { useSubscription } from '@/contexts/SubscriptionContext';

export function TrialCountdownBanner() {
  const { subscription, isTrialActive, daysLeft } = useSubscription();
  const [dismissed, setDismissed] = useState(false);

  if (!subscription || !isTrialActive || daysLeft === null) return null;
  if (daysLeft <= 0 || daysLeft > 7) return null;

  const isLastDay = daysLeft === 1;
  if (dismissed && !isLastDay) return null;

  const message =
    daysLeft === 1
      ? 'Завтра trial завершится. История останется, но AI / MAE / Replay / sync остановятся.'
      : `Осталось ${daysLeft} ${pluralizeDays(daysLeft)} Pro. История сохранится навсегда.`;

  return (
    <div
      role="status"
      className="flex items-center justify-between gap-4 px-4 py-3 text-sm"
      style={{
        backgroundColor: 'rgba(59, 130, 246, 0.10)',
        borderBottom: '1px solid rgba(59, 130, 246, 0.25)',
        color: 'var(--foreground)',
      }}
    >
      <div className="flex items-center gap-2">
        <Clock size={16} aria-hidden="true" style={{ color: 'var(--info, #3b82f6)' }} />
        <span>{message}</span>
      </div>

      <div className="flex items-center gap-2">
        <a
          href="/pricing?from=trial-countdown"
          className="px-3 py-1 rounded-md text-xs font-medium transition-colors"
          style={{
            backgroundColor: 'var(--accent, #6366F1)',
            color: '#fff',
          }}
        >
          Подключить Pro — 399₽
        </a>
        {!isLastDay && (
          <button
            type="button"
            onClick={() => setDismissed(true)}
            aria-label="Скрыть баннер"
            className="p-1 rounded-md transition-colors hover:bg-white/5"
            style={{ color: 'var(--text-tertiary, #71717a)' }}
          >
            <X size={14} aria-hidden="true" />
          </button>
        )}
      </div>
    </div>
  );
}

function pluralizeDays(n: number): string {
  const lastTwo = n % 100;
  if (lastTwo >= 11 && lastTwo <= 14) return 'дней';
  const last = n % 10;
  if (last === 1) return 'день';
  if (last >= 2 && last <= 4) return 'дня';
  return 'дней';
}
