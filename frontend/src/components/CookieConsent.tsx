'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { X } from 'lucide-react';

const STORAGE_KEY = 'empirik.cookie_consent.v1';

export function CookieConsent() {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    // Не показываем если уже принято.
    if (typeof window === 'undefined') return;
    const accepted = localStorage.getItem(STORAGE_KEY);
    if (!accepted) setVisible(true);
  }, []);

  const accept = () => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({
      version: 'v1',
      accepted_at: new Date().toISOString(),
    }));
    setVisible(false);
  };

  if (!visible) return null;

  return (
    <div
      role="dialog"
      aria-label="Согласие на использование cookies"
      className="fixed bottom-4 left-4 right-4 md:left-auto md:right-6 md:bottom-6 md:max-w-[440px] z-50
                 cyber-card p-5 shadow-2xl border border-[var(--border)]"
    >
      <div className="flex items-start justify-between gap-3 mb-3">
        <h3 className="text-sm font-semibold">Cookies и персональные данные</h3>
        <button
          type="button"
          onClick={accept}
          aria-label="Закрыть"
          className="text-[var(--text-tertiary)] hover:text-[var(--foreground)] -mt-1 -mr-1 p-1"
        >
          <X size={16} />
        </button>
      </div>

      <p className="text-[13px] text-[var(--text-secondary)] leading-relaxed mb-4">
        Мы используем строго необходимые cookies для работы сервиса
        (авторизация, защита от CSRF). Подробнее — в{' '}
        <Link
          href="/privacy"
          className="text-[var(--accent)] hover:text-[var(--accent-hover)] underline"
        >
          политике конфиденциальности
        </Link>
        .
      </p>

      <button
        type="button"
        onClick={accept}
        className="btn-primary text-sm py-2 px-4 w-full"
      >
        Понятно
      </button>
    </div>
  );
}
