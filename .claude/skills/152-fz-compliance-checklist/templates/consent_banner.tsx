'use client';

/**
 * CookieConsent — баннер согласия на cookies для Eqio.
 *
 * Соответствует ст. 9 152-ФЗ (explicit consent) и разъяснениям РКН от 27.05.2022:
 * - категории Analytics и Marketing по умолчанию выключены;
 * - кнопки «Принять все» и «Только необходимые» равноправны визуально;
 * - согласие версионируется (eqio_consent_v1) — при смене схемы перезапрашиваем.
 *
 * Использование:
 *   1. Смонтируй <CookieConsent /> в frontend/src/app/layout.tsx сразу после <body>.
 *   2. В аналитике: const { analytics } = useConsent(); if (analytics) loadMetrika();
 */

import { Cookie, X } from 'lucide-react';
import Link from 'next/link';
import { useCallback, useEffect, useState } from 'react';

const STORAGE_KEY = 'eqio_consent_v1';
const SCHEMA_VERSION = 1;

type ConsentCategories = {
  necessary: true; // всегда true — нельзя выключить
  analytics: boolean;
  marketing: boolean;
};

type StoredConsent = {
  schemaVersion: number;
  acceptedAt: string; // ISO timestamp
  categories: ConsentCategories;
};

const DEFAULT_CATEGORIES: ConsentCategories = {
  necessary: true,
  analytics: false,
  marketing: false,
};

function readConsent(): StoredConsent | null {
  if (typeof window === 'undefined') return null;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as StoredConsent;
    if (parsed.schemaVersion !== SCHEMA_VERSION) return null;
    return parsed;
  } catch {
    return null;
  }
}

function writeConsent(categories: ConsentCategories): StoredConsent {
  const payload: StoredConsent = {
    schemaVersion: SCHEMA_VERSION,
    acceptedAt: new Date().toISOString(),
    categories,
  };
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(payload));
  // Уведомляем подписчиков (другие табы / useConsent)
  window.dispatchEvent(new CustomEvent('eqio:consent-changed', { detail: payload }));
  return payload;
}

/**
 * Хук для использования в любом компоненте — например, для условной загрузки Метрики.
 *
 *   const { analytics, marketing, hasDecided, openSettings } = useConsent();
 *   useEffect(() => { if (analytics) loadYandexMetrika(); }, [analytics]);
 */
export function useConsent() {
  const [consent, setConsent] = useState<StoredConsent | null>(() => readConsent());

  useEffect(() => {
    const handler = (e: Event) => {
      const detail = (e as CustomEvent<StoredConsent>).detail;
      setConsent(detail);
    };
    window.addEventListener('eqio:consent-changed', handler);
    window.addEventListener('storage', () => setConsent(readConsent()));
    return () => {
      window.removeEventListener('eqio:consent-changed', handler);
    };
  }, []);

  const openSettings = useCallback(() => {
    window.dispatchEvent(new CustomEvent('eqio:open-consent-settings'));
  }, []);

  return {
    necessary: true as const,
    analytics: consent?.categories.analytics ?? false,
    marketing: consent?.categories.marketing ?? false,
    hasDecided: consent !== null,
    openSettings,
  };
}

export default function CookieConsent() {
  const [visible, setVisible] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  const [categories, setCategories] = useState<ConsentCategories>(DEFAULT_CATEGORIES);

  // Показываем баннер если решения ещё нет
  useEffect(() => {
    const existing = readConsent();
    if (!existing) {
      setVisible(true);
    } else {
      setCategories(existing.categories);
    }

    const openHandler = () => {
      setShowSettings(true);
      setVisible(true);
    };
    window.addEventListener('eqio:open-consent-settings', openHandler);
    return () => window.removeEventListener('eqio:open-consent-settings', openHandler);
  }, []);

  const acceptAll = () => {
    writeConsent({ necessary: true, analytics: true, marketing: true });
    setVisible(false);
  };

  const acceptNecessary = () => {
    writeConsent({ necessary: true, analytics: false, marketing: false });
    setVisible(false);
  };

  const saveCustom = () => {
    writeConsent(categories);
    setVisible(false);
    setShowSettings(false);
  };

  if (!visible) return null;

  return (
    <div
      role="dialog"
      aria-label="Настройки cookies"
      aria-modal="false"
      className="fixed inset-x-4 bottom-4 z-[100] mx-auto max-w-3xl rounded-2xl border border-white/10 bg-zinc-900/95 p-5 text-zinc-100 shadow-2xl backdrop-blur-md sm:inset-x-auto sm:right-4"
    >
      <div className="flex items-start gap-3">
        <Cookie className="mt-0.5 size-5 shrink-0 text-indigo-400" aria-hidden />
        <div className="flex-1">
          <h2 className="text-base font-semibold">Cookies и персональные данные</h2>
          <p className="mt-1 text-sm text-zinc-400">
            Мы используем cookies для работы сервиса, аналитики и улучшения качества. Аналитика и
            маркетинг — только с вашего согласия (152-ФЗ ст. 9).{' '}
            <Link href="/privacy" className="text-indigo-400 underline underline-offset-2">
              Политика конфиденциальности
            </Link>
            .
          </p>

          {showSettings && (
            <div className="mt-4 space-y-2">
              <CategoryRow
                title="Strictly Necessary (необходимые)"
                description="JWT cookies, CSRF, session — без них вход не работает."
                checked
                disabled
                onChange={() => undefined}
              />
              <CategoryRow
                title="Analytics (аналитика)"
                description="Yandex.Metrika, агрегированная статистика. Помогает улучшать продукт."
                checked={categories.analytics}
                onChange={(v) => setCategories((c) => ({ ...c, analytics: v }))}
              />
              <CategoryRow
                title="Marketing (маркетинг)"
                description="UTM-метки источников, ретаргетинг. Можно отключить."
                checked={categories.marketing}
                onChange={(v) => setCategories((c) => ({ ...c, marketing: v }))}
              />
            </div>
          )}

          <div className="mt-4 flex flex-wrap gap-2">
            {!showSettings ? (
              <>
                <button
                  type="button"
                  onClick={acceptAll}
                  className="rounded-2xl bg-indigo-500 px-4 py-2 text-sm font-medium text-white transition hover:bg-indigo-400"
                >
                  Принять все
                </button>
                <button
                  type="button"
                  onClick={acceptNecessary}
                  className="rounded-2xl border border-white/15 bg-transparent px-4 py-2 text-sm font-medium text-zinc-100 transition hover:bg-white/5"
                >
                  Только необходимые
                </button>
                <button
                  type="button"
                  onClick={() => setShowSettings(true)}
                  className="rounded-2xl px-4 py-2 text-sm font-medium text-zinc-400 transition hover:text-zinc-100"
                >
                  Настроить
                </button>
              </>
            ) : (
              <>
                <button
                  type="button"
                  onClick={saveCustom}
                  className="rounded-2xl bg-indigo-500 px-4 py-2 text-sm font-medium text-white transition hover:bg-indigo-400"
                >
                  Сохранить выбор
                </button>
                <button
                  type="button"
                  onClick={() => setShowSettings(false)}
                  className="rounded-2xl px-4 py-2 text-sm font-medium text-zinc-400 transition hover:text-zinc-100"
                >
                  Назад
                </button>
              </>
            )}
          </div>
        </div>

        <button
          type="button"
          onClick={acceptNecessary}
          aria-label="Закрыть (только необходимые cookies)"
          className="rounded-full p-1 text-zinc-500 transition hover:bg-white/5 hover:text-zinc-100"
        >
          <X className="size-4" />
        </button>
      </div>
    </div>
  );
}

type CategoryRowProps = {
  title: string;
  description: string;
  checked: boolean;
  disabled?: boolean;
  onChange: (value: boolean) => void;
};

function CategoryRow({ title, description, checked, disabled = false, onChange }: CategoryRowProps) {
  return (
    <label
      className={`flex cursor-pointer items-start gap-3 rounded-xl border border-white/5 bg-white/[0.02] p-3 transition ${
        disabled ? 'opacity-70' : 'hover:bg-white/[0.04]'
      }`}
    >
      <input
        type="checkbox"
        checked={checked}
        disabled={disabled}
        onChange={(e) => onChange(e.target.checked)}
        className="mt-1 size-4 accent-indigo-500"
      />
      <div className="flex-1">
        <div className="text-sm font-medium text-zinc-100">{title}</div>
        <div className="mt-0.5 text-xs text-zinc-400">{description}</div>
      </div>
    </label>
  );
}
