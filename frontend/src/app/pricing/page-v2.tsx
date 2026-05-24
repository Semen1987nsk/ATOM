'use client';

/**
 * Pricing page v2 — Reverse-Trial 21d / Free+ / Pro 399₽.
 *
 * Эталон: .business/sales/pricing.md (2026-05-14)
 * Решение: ADR-0005 (.business/tech/decisions/0005-reverse-trial-model.md)
 *
 * Этот файл — ПАРАЛЛЕЛЬНАЯ версия. Существующий page.tsx редактирует
 * параллельный агент. После слияния его изменений — page-v2.tsx
 * становится новым page.tsx (см. .business/instructions/0019-reverse-trial-patches.md).
 *
 * DS-правила:
 *   - Только var(--accent) #6366F1 для CTA. Никаких purple-indigo градиентов
 *     (анти-паттерн DS «Discord»).
 *   - Иконки только lucide-react. Без эмодзи в заголовках/кнопках.
 *   - Фоны: var(--surface-1) / var(--surface-2). Границы: var(--border).
 *   - Радиусы: var(--radius-lg) 14px для карточек.
 */

import Link from 'next/link';
import { Check, X, ArrowRight, Snowflake, Sparkles, Shield, RefreshCw } from 'lucide-react';
import { AppShell } from '@/components/AppShell';
import { useAuth } from '@/contexts/AuthContext';
import { useSubscription } from '@/contexts/SubscriptionContext';

interface FeatureRow {
  text: string;
  trial: boolean | 'frozen';
  freePlus: boolean | 'frozen';
  pro: boolean;
}

const FEATURES: FeatureRow[] = [
  { text: 'Безлимит сделок и история навсегда', trial: true, freePlus: true, pro: true },
  { text: 'Ручной ввод + CSV/Excel импорт', trial: true, freePlus: true, pro: true },
  { text: 'Базовые метрики (PnL, WinRate, Profit Factor, Expectancy, R-Multiple)', trial: true, freePlus: true, pro: true },
  { text: 'Equity curve', trial: true, freePlus: true, pro: true },
  { text: 'Экспорт CSV', trial: true, freePlus: true, pro: true },
  { text: 'Расширенные метрики (Sharpe, Sortino, Calmar, Ulcer, K-Ratio)', trial: true, freePlus: 'frozen', pro: true },
  { text: 'MAE/MFE из MOEX автоматически', trial: true, freePlus: 'frozen', pro: true },
  { text: 'AI-инсайты', trial: true, freePlus: 'frozen', pro: true },
  { text: 'Optimal f / SQN / Monte Carlo', trial: true, freePlus: 'frozen', pro: true },
  { text: 'Trade Replay со свечами', trial: true, freePlus: 'frozen', pro: true },
  { text: 'API-синхронизация Тинькофф', trial: true, freePlus: false, pro: true },
  { text: 'До 5 торговых счетов', trial: false, freePlus: false, pro: true },
  { text: 'Безлимит PDF-экспорта', trial: true, freePlus: false, pro: true },
];

export default function PricingPageV2() {
  const { isAuthenticated } = useAuth();
  const { subscription } = useSubscription();

  const currentStatus = subscription?.status ?? 'none';

  return (
    <AppShell>
      <div className="max-w-6xl mx-auto px-4 py-12">
        <Hero />
        <PlanCards isAuthenticated={isAuthenticated} currentStatus={currentStatus} />
        <ComparisonTable />
        <NdflNote />
        <Footer />
      </div>
    </AppShell>
  );
}

function Hero() {
  return (
    <section className="text-center mb-12">
      <h1
        className="text-4xl md:text-5xl font-semibold mb-4"
        style={{ color: 'var(--foreground)' }}
      >
        Один тариф для серьёзного трейдинга
      </h1>
      <p
        className="text-lg max-w-2xl mx-auto"
        style={{ color: 'var(--text-secondary)' }}
      >
        21 день полного Pro бесплатно без карты. Дальше — Free+ навсегда с сохранением всей истории, или Pro 399₽/мес.
      </p>
    </section>
  );
}

function PlanCards({
  isAuthenticated,
  currentStatus,
}: {
  isAuthenticated: boolean;
  currentStatus: string;
}) {
  return (
    <section className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-16">
      <PlanCard
        title="Trial"
        price="0₽"
        priceCaption="21 день при регистрации"
        description="Полный Pro без карты"
        icon={<Sparkles size={20} aria-hidden="true" />}
        ctaText={
          currentStatus === 'trial_active'
            ? 'Твой trial идёт'
            : isAuthenticated
              ? 'Trial уже использован'
              : 'Начать без карты'
        }
        ctaHref={isAuthenticated ? '/dashboard' : '/register'}
        ctaDisabled={isAuthenticated && currentStatus !== 'none'}
        bullets={[
          'Все Pro-фичи на 21 день',
          'AI-инсайты до 30 запросов',
          'API-sync Тинькофф',
          'MAE/MFE из MOEX автоматически',
          'Trade Replay со свечами',
        ]}
      />

      <PlanCard
        title="Free+"
        price="0₽"
        priceCaption="навсегда после trial"
        description="История сохраняется, базовая аналитика всегда"
        icon={<Shield size={20} aria-hidden="true" />}
        ctaText={
          currentStatus === 'trial_expired' || currentStatus === 'free_plus'
            ? 'Ваш текущий план'
            : 'Доступен после trial'
        }
        ctaHref="#"
        ctaDisabled={true}
        bullets={[
          'Безлимит сделок, история не удаляется',
          'PnL, WinRate, Profit Factor — всегда',
          'PDF-итоги trial-периода навсегда',
          'CSV-экспорт',
          'Pro-фичи видны как архив (Snowflake-бейдж)',
        ]}
      />

      <PlanCard
        title="Pro"
        price="399₽"
        priceCaption="/месяц"
        description="Безлимит, AI, API-sync, multi-account"
        icon={<RefreshCw size={20} aria-hidden="true" />}
        ctaText={
          currentStatus === 'pro_active' || currentStatus === 'corporate_active'
            ? 'Ваш текущий план'
            : 'Подключить Pro'
        }
        ctaHref={isAuthenticated ? '/billing/upgrade' : '/register'}
        ctaDisabled={currentStatus === 'pro_active' || currentStatus === 'corporate_active'}
        primary
        bullets={[
          'Всё из Trial + размораживается на Free+ архиве',
          'Безлимит AI-инсайтов',
          'Live MAE/MFE для всех сделок',
          'API-sync 60s — мгновенно после оплаты',
          'До 5 счетов',
        ]}
      />
    </section>
  );
}

function PlanCard(props: {
  title: string;
  price: string;
  priceCaption: string;
  description: string;
  icon: React.ReactNode;
  ctaText: string;
  ctaHref: string;
  ctaDisabled?: boolean;
  primary?: boolean;
  bullets: string[];
}) {
  const { title, price, priceCaption, description, icon, ctaText, ctaHref, ctaDisabled, primary, bullets } = props;
  return (
    <article
      className="flex flex-col p-6 rounded-2xl"
      style={{
        backgroundColor: 'var(--surface-1, #141416)',
        border: primary
          ? '1px solid var(--accent, #6366F1)'
          : '1px solid var(--border, rgba(255,255,255,0.08))',
        boxShadow: primary ? '0 4px 12px rgba(99, 102, 241, 0.20)' : '0 1px 2px rgba(0,0,0,0.4)',
      }}
    >
      <div className="flex items-center gap-2 mb-2">
        <span style={{ color: primary ? 'var(--accent)' : 'var(--text-secondary)' }}>{icon}</span>
        <h3 className="text-lg font-semibold" style={{ color: 'var(--foreground)' }}>
          {title}
        </h3>
      </div>

      <div className="mb-4">
        <div className="flex items-baseline gap-1">
          <span
            className="text-3xl font-semibold"
            style={{ color: 'var(--foreground)', fontVariantNumeric: 'tabular-nums' }}
          >
            {price}
          </span>
          <span className="text-sm" style={{ color: 'var(--text-secondary)' }}>
            {priceCaption}
          </span>
        </div>
        <p className="text-sm mt-1" style={{ color: 'var(--text-secondary)' }}>
          {description}
        </p>
      </div>

      <ul className="space-y-2 mb-6 flex-1">
        {bullets.map((b, i) => (
          <li key={i} className="flex items-start gap-2 text-sm" style={{ color: 'var(--foreground)' }}>
            <Check
              size={14}
              aria-hidden="true"
              className="mt-1 flex-shrink-0"
              style={{ color: 'var(--success, #10b981)' }}
            />
            <span>{b}</span>
          </li>
        ))}
      </ul>

      {ctaDisabled ? (
        <span
          className="text-center px-4 py-2 rounded-full text-sm font-medium select-none"
          style={{
            backgroundColor: 'var(--surface-3, #26262c)',
            color: 'var(--text-tertiary, #71717a)',
            border: '1px solid var(--border, rgba(255,255,255,0.08))',
          }}
        >
          {ctaText}
        </span>
      ) : (
        <Link
          href={ctaHref}
          className="inline-flex items-center justify-center gap-1 px-4 py-2 rounded-full text-sm font-medium transition-colors"
          style={
            primary
              ? { backgroundColor: 'var(--accent, #6366F1)', color: '#fff' }
              : {
                  backgroundColor: 'transparent',
                  color: 'var(--accent, #6366F1)',
                  border: '1px solid var(--accent, #6366F1)',
                }
          }
        >
          {ctaText}
          <ArrowRight size={14} aria-hidden="true" />
        </Link>
      )}
    </article>
  );
}

function ComparisonTable() {
  return (
    <section className="mb-16">
      <h2 className="text-2xl font-semibold mb-4" style={{ color: 'var(--foreground)' }}>
        Сравнение возможностей
      </h2>
      <div
        className="overflow-x-auto rounded-2xl"
        style={{
          backgroundColor: 'var(--surface-1, #141416)',
          border: '1px solid var(--border, rgba(255,255,255,0.08))',
        }}
      >
        <table className="w-full text-sm">
          <thead>
            <tr style={{ borderBottom: '1px solid var(--border, rgba(255,255,255,0.08))' }}>
              <th className="text-left p-4 font-medium" style={{ color: 'var(--text-secondary)' }}>
                Фича
              </th>
              <th className="text-center p-4 font-medium" style={{ color: 'var(--text-secondary)' }}>
                Trial 21д
              </th>
              <th className="text-center p-4 font-medium" style={{ color: 'var(--text-secondary)' }}>
                Free+
              </th>
              <th className="text-center p-4 font-medium" style={{ color: 'var(--text-secondary)' }}>
                Pro
              </th>
            </tr>
          </thead>
          <tbody>
            {FEATURES.map((row, i) => (
              <tr
                key={i}
                style={{
                  borderBottom:
                    i < FEATURES.length - 1
                      ? '1px solid var(--border, rgba(255,255,255,0.08))'
                      : undefined,
                }}
              >
                <td className="p-3" style={{ color: 'var(--foreground)' }}>
                  {row.text}
                </td>
                <td className="text-center p-3">
                  <FeatureCell value={row.trial} />
                </td>
                <td className="text-center p-3">
                  <FeatureCell value={row.freePlus} />
                </td>
                <td className="text-center p-3">
                  <FeatureCell value={row.pro} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-xs mt-2" style={{ color: 'var(--text-tertiary)' }}>
        <Snowflake size={11} className="inline mr-1" aria-hidden="true" /> = заморожено: видно как архив за trial-период, новые сделки без расчёта.
      </p>
    </section>
  );
}

function FeatureCell({ value }: { value: boolean | 'frozen' }) {
  if (value === true) {
    return <Check size={16} aria-hidden="true" style={{ color: 'var(--success, #10b981)' }} className="inline" />;
  }
  if (value === 'frozen') {
    return (
      <span
        title="Видно как архив за trial. Новые сделки без расчёта."
        className="inline-flex"
      >
        <Snowflake size={14} aria-hidden="true" style={{ color: 'var(--info, #3b82f6)' }} />
      </span>
    );
  }
  return <X size={16} aria-hidden="true" style={{ color: 'var(--text-tertiary, #71717a)' }} className="inline" />;
}

function NdflNote() {
  return (
    <section
      className="rounded-2xl p-6 mb-12"
      style={{
        backgroundColor: 'var(--surface-1, #141416)',
        border: '1px solid var(--border, rgba(255,255,255,0.08))',
      }}
    >
      <h3 className="text-lg font-semibold mb-2" style={{ color: 'var(--foreground)' }}>
        А что с налогами?
      </h3>
      <p className="text-sm" style={{ color: 'var(--text-secondary)' }}>
        Российский брокер (Тинькофф, БКС, Финам, Сбер) — налоговый агент: удерживает
        НДФЛ автоматически и сам подаёт отчётность. Декларация 3-НДФЛ нужна только в
        специфичных случаях: перенос убытков прошлых лет, мульти-брокерская консолидация,
        иностранные эмитенты. Помощник для этих сценариев — на roadmap.
      </p>
    </section>
  );
}

function Footer() {
  return (
    <section className="text-center">
      <h2 className="text-xl font-semibold mb-2" style={{ color: 'var(--foreground)' }}>
        Готов начать?
      </h2>
      <p className="text-sm mb-4" style={{ color: 'var(--text-secondary)' }}>
        21 день полного Pro без карты. История останется на Free+ навсегда.
      </p>
      <Link
        href="/register"
        className="inline-flex items-center gap-2 px-6 py-3 rounded-full text-sm font-medium transition-colors"
        style={{ backgroundColor: 'var(--accent, #6366F1)', color: '#fff' }}
      >
        Создать аккаунт
        <ArrowRight size={16} aria-hidden="true" />
      </Link>
    </section>
  );
}
