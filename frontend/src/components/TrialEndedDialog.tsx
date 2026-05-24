'use client';

/**
 * TrialEndedDialog — D+21 экран «Подарок за trial».
 *
 * Эталон: .business/product/feature-canon/04-downgrade-experience.md §«D+21 экран»
 * Решение: ADR-0005
 *
 * Триггер показа:
 *   subscription.status === 'trial_expired' && !subscription.trial_summary_shown
 *
 * Появляется ОДИН раз. При закрытии вызывает markTrialSummaryShown() —
 * backend ставит trial_summary_shown=true и переводит status='free_plus'.
 * Повторно не показывается.
 *
 * DS:
 *   - <Gift /> в заголовке, <FileText /> на PDF-кнопке (lucide, не эмодзи)
 *   - Заголовок 24px Geist Sans 600
 *   - Главная CTA — .btn-primary indigo
 *   - Вторичная «Позже» — .btn-ghost
 *   - PDF-кнопка — .btn-secondary
 */

import { Gift, FileText } from 'lucide-react';
import { useSubscription } from '@/contexts/SubscriptionContext';
import { api } from '@/lib/apiClient';
import { useAuth } from '@/contexts/AuthContext';

interface TrialSummary {
  trades_count: number;
  insights: string[]; // 0-3 AI-инсайтов реальных, не выдуманных
  pdf_url: string | null; // URL для скачивания PDF-отчёта trial-периода
}

export function TrialEndedDialog() {
  const { subscription, markTrialSummaryShown } = useSubscription();
  const { user } = useAuth();

  if (!subscription) return null;
  if (subscription.status !== 'trial_expired') return null;
  if (subscription.trial_summary_shown) return null;
  if (!user) return null;

  return <TrialEndedDialogContent userId={user.id} onClose={markTrialSummaryShown} />;
}

function TrialEndedDialogContent({
  userId,
  onClose,
}: {
  userId: number;
  onClose: () => Promise<void>;
}) {
  // Подгружаем сводку из /subscription/trial-summary (endpoint реализуется в backend-patches).
  // На время отсутствия endpoint компонент деградирует в «вежливый dialog без AI-инсайтов».
  const summary = useTrialSummary(userId);

  const handlePrimary = () => {
    // Главная цель — конвертация в Pro. Перед уходом помечаем dialog как показанный.
    void onClose();
    window.location.href = '/pricing?from=trial-ended';
  };

  const handleLater = () => {
    void onClose();
  };

  const handleDownloadPdf = () => {
    if (summary?.pdf_url) {
      window.open(summary.pdf_url, '_blank', 'noopener,noreferrer');
    }
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="trial-ended-title"
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ backgroundColor: 'rgba(0, 0, 0, 0.55)' }}
    >
      <div
        className="w-full max-w-md rounded-2xl p-6"
        style={{
          backgroundColor: 'var(--surface-2, #1c1c20)',
          border: '1px solid var(--border, rgba(255,255,255,0.08))',
          boxShadow: '0 4px 12px rgba(0, 0, 0, 0.5)',
        }}
      >
        <div className="flex items-center gap-3 mb-3">
          <Gift size={28} aria-hidden="true" style={{ color: 'var(--accent, #6366F1)' }} />
          <h2
            id="trial-ended-title"
            className="text-2xl font-semibold"
            style={{ color: 'var(--foreground, #fafafa)' }}
          >
            Твой trial завершён
          </h2>
        </div>

        {summary && summary.trades_count > 0 ? (
          <>
            <p
              className="text-sm mb-3"
              style={{ color: 'var(--text-secondary, #a1a1aa)' }}
            >
              За 21 день мы проанализировали {summary.trades_count}{' '}
              {pluralizeTrades(summary.trades_count)}
              {summary.insights.length > 0 ? ' и нашли:' : '.'}
            </p>
            {summary.insights.length > 0 && (
              <ul className="space-y-2 mb-4">
                {summary.insights.map((insight, i) => (
                  <li
                    key={i}
                    className="text-sm flex gap-2"
                    style={{ color: 'var(--foreground, #fafafa)' }}
                  >
                    <span style={{ color: 'var(--accent, #6366F1)' }}>•</span>
                    <span>{insight}</span>
                  </li>
                ))}
              </ul>
            )}
          </>
        ) : (
          <p
            className="text-sm mb-4"
            style={{ color: 'var(--text-secondary, #a1a1aa)' }}
          >
            Спасибо что попробовал Eqio. Твоя история сделок сохранена на Free+ навсегда.
          </p>
        )}

        {summary?.pdf_url && (
          <button
            type="button"
            onClick={handleDownloadPdf}
            className="w-full flex items-center justify-center gap-2 px-4 py-2 mb-3 rounded-md text-sm transition-colors"
            style={{
              backgroundColor: 'var(--surface-3, #26262c)',
              color: 'var(--foreground, #fafafa)',
              border: '1px solid var(--border, rgba(255,255,255,0.08))',
            }}
          >
            <FileText size={16} aria-hidden="true" />
            Скачать PDF-отчёт за trial
          </button>
        )}

        <p
          className="text-xs mb-4"
          style={{ color: 'var(--text-tertiary, #71717a)' }}
        >
          Твоя история сохранена. Хочешь продолжить мониторинг?
        </p>

        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={handlePrimary}
            className="flex-1 px-4 py-2 rounded-full text-sm font-medium transition-colors"
            style={{
              backgroundColor: 'var(--accent, #6366F1)',
              color: '#fff',
            }}
          >
            Возобновить Pro — 399₽/мес
          </button>
          <button
            type="button"
            onClick={handleLater}
            className="px-4 py-2 rounded-full text-sm transition-colors"
            style={{
              color: 'var(--text-secondary, #a1a1aa)',
              backgroundColor: 'transparent',
            }}
          >
            Позже
          </button>
        </div>
      </div>
    </div>
  );
}

function pluralizeTrades(n: number): string {
  const lastTwo = n % 100;
  if (lastTwo >= 11 && lastTwo <= 14) return 'сделок';
  const last = n % 10;
  if (last === 1) return 'сделку';
  if (last >= 2 && last <= 4) return 'сделки';
  return 'сделок';
}

// Внутренний hook для подгрузки сводки. Использует useEffect/useState, чтобы не
// тянуть TanStack Query ради одного dialog — компонент рендерится максимум раз
// на жизнь юзера.
import { useEffect, useState } from 'react';

function useTrialSummary(userId: number): TrialSummary | null {
  const [summary, setSummary] = useState<TrialSummary | null>(null);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const data = await api.get<TrialSummary>('/subscription/trial-summary');
        if (!cancelled) setSummary(data);
      } catch {
        // Endpoint может ещё не существовать — деградируем в «вежливый dialog».
        if (!cancelled) setSummary({ trades_count: 0, insights: [], pdf_url: null });
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [userId]);

  return summary;
}
