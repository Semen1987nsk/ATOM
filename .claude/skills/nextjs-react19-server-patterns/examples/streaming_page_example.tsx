/**
 * Пример: дашборд Empirik со streaming через несколько Suspense-границ.
 *
 * Контекст Empirik:
 *   - Сейчас src/app/page.tsx — 'use client', 1013 строк.
 *   - Делает Promise.all([api.get('/stats/'), api.get('/trades/')]) и ждёт обоих
 *     перед тем, как нарисовать <DashboardSkeleton />.
 *   - Пользователь видит весь skeleton всегда минимум 800ms+ (даже если equity
 *     подгрузилось за 100ms).
 *
 * Этот пример показывает streaming-вариант:
 *   - Shell виден мгновенно
 *   - Каждая секция стримится независимо
 *   - Медленная AI-секция не блокирует быстрые статистики
 *
 * Файлы:
 *   - src/app/dashboard/page.tsx           (Server, async, Suspense-композиция)
 *   - src/app/dashboard/loading.tsx        (route-level fallback при навигации)
 *   - src/app/dashboard/sections/*.tsx     (Server, async, каждая фетчит своё)
 *
 * Что использовано:
 *   - Async Server Components
 *   - <Suspense> с независимыми fallback'ами
 *   - PageProps с params/searchParams как Promise (Next 16)
 *   - cache: 'no-store' для personalized stats
 *   - revalidate + tags для частично-статичного контента
 *   - <Skeleton> компоненты Empirik как fallbacks
 */

// ═════════════════════════════════════════════════════════════════
// ФАЙЛ 1: src/app/dashboard/loading.tsx
// Route-level fallback. Показывается ТОЛЬКО при навигации к этому роуту,
// не при первичной загрузке.
// ═════════════════════════════════════════════════════════════════

import { DashboardSkeleton } from '@/components/Skeleton';

export default function DashboardLoading() {
  return <DashboardSkeleton />;
}

// ═════════════════════════════════════════════════════════════════
// ФАЙЛ 2: src/app/dashboard/page.tsx
// Server Component. Async, но без await на верхнем уровне — иначе шелл
// будет ждать. Все async вынесено в отдельные секции под Suspense.
// ═════════════════════════════════════════════════════════════════

import { Suspense } from 'react';
import { AppShell } from '@/components/AppShell';
import {
  EquitySectionSkeleton,
  StatsGridSkeleton,
  AdvancedStatsSkeleton,
  AISectionSkeleton,
} from '@/components/Skeleton';
import { EquityCurveSection } from './sections/EquityCurveSection';
import { StatsGridSection } from './sections/StatsGridSection';
import { AdvancedStatsSection } from './sections/AdvancedStatsSection';
import { AIInsightsSection } from './sections/AIInsightsSection';

type DashboardPageProps = {
  params: Promise<Record<string, never>>;
  searchParams: Promise<{
    period?: 'all' | '1d' | '7d' | '30d' | '90d' | 'ytd' | 'custom';
    tag?: string;
    start_date?: string;
    end_date?: string;
  }>;
};

export const metadata = {
  title: 'Дашборд · Empirik',
  description: 'Сводная статистика по сделкам и портфелю',
};

export default async function DashboardPage({ searchParams }: DashboardPageProps) {
  // searchParams — Promise в Next 16. Resolve один раз, передаём дальше.
  const sp = await searchParams;
  const period = sp.period ?? 'all';
  const tag = sp.tag;

  return (
    <AppShell pageTitle="Дашборд">
      <div className="p-6 md:p-8 max-w-7xl mx-auto flex flex-col gap-6">
        {/* Header — синхронный, рендерится мгновенно */}
        <DashboardHeader />

        {/* 1. Equity curve — обычно быстро (~150ms) */}
        <Suspense fallback={<EquitySectionSkeleton />}>
          <EquityCurveSection period={period} tag={tag} />
        </Suspense>

        {/* 2. Базовая статистика — быстро */}
        <Suspense fallback={<StatsGridSkeleton />}>
          <StatsGridSection period={period} tag={tag} />
        </Suspense>

        {/* 3. Продвинутые метрики — Monte Carlo, MAE/MFE, тяжёлые расчёты (~800ms) */}
        <Suspense fallback={<AdvancedStatsSkeleton />}>
          <AdvancedStatsSection period={period} tag={tag} />
        </Suspense>

        {/* 4. AI insights — медленнее всего (~3-5s, GPT/Claude вызов).
               Stream'ится последним, остальное уже видно. */}
        <Suspense fallback={<AISectionSkeleton />}>
          <AIInsightsSection period={period} />
        </Suspense>
      </div>
    </AppShell>
  );
}

function DashboardHeader() {
  return (
    <div>
      <h1 className="text-3xl font-bold tracking-tight mb-1">Дашборд</h1>
      <p className="text-sm text-[var(--text-secondary)]">
        Сводная статистика по вашим сделкам
      </p>
    </div>
  );
}

// ═════════════════════════════════════════════════════════════════
// ФАЙЛ 3: src/app/dashboard/sections/EquityCurveSection.tsx
// Server Component. Async fetch + передача Client-обёртке для Recharts.
// ═════════════════════════════════════════════════════════════════

import { serverApi } from '@/lib/serverApiClient';
import { EquityCurveCard } from '@/components/dashboard/EquityCurveCard';

interface EquitySectionProps {
  period: string;
  tag?: string;
}

interface EquityResponse {
  equity_curve: Array<{ date: string; balance: number }>;
  imoex_curve?: Array<{ date: string; value: number }>;
  initial_balance?: number;
}

export async function EquityCurveSection({ period, tag }: EquitySectionProps) {
  const params = new URLSearchParams();
  if (period !== 'all') params.set('period', period);
  if (tag) params.set('tag', tag);
  const qs = params.toString() ? `?${params}` : '';

  // /stats/ зависит от user-cookie → нельзя кэшировать
  const data = await serverApi.get<EquityResponse>(`/stats/equity${qs}`, {
    cache: 'no-store',
  });

  // EquityCurveCard — Client (recharts), но получает готовые данные
  return (
    <EquityCurveCard
      data={data.equity_curve}
      benchmark={data.imoex_curve}
      benchmarkLabel="IMOEX"
      initialBalance={data.initial_balance}
    />
  );
}

// ═════════════════════════════════════════════════════════════════
// ФАЙЛ 4: src/app/dashboard/sections/StatsGridSection.tsx
// ═════════════════════════════════════════════════════════════════

import { serverApi } from '@/lib/serverApiClient';
import { StatsGrid } from '@/components/dashboard';

interface StatsResponse {
  total_pnl: number;
  win_rate: number;
  total_trades: number;
  profit_factor: number;
  // ... остальные поля
}

export async function StatsGridSection({ period, tag }: { period: string; tag?: string }) {
  const params = new URLSearchParams();
  if (period !== 'all') params.set('period', period);
  if (tag) params.set('tag', tag);
  const qs = params.toString() ? `?${params}` : '';

  const stats = await serverApi.get<StatsResponse>(`/stats/${qs}`, {
    cache: 'no-store',
  });

  return <StatsGrid stats={stats} hasData={stats.total_trades > 0} />;
}

// ═════════════════════════════════════════════════════════════════
// ФАЙЛ 5: src/app/dashboard/sections/AdvancedStatsSection.tsx
// Тяжёлая секция: Monte Carlo, MAE/MFE. Может быть 1+ секунд.
// ═════════════════════════════════════════════════════════════════

import { serverApi } from '@/lib/serverApiClient';
import { AdvancedStatsGrid } from '@/components/dashboard';

interface AdvancedResponse {
  monte_carlo: { median_return: number; worst_case_5pct: number; ruin_probability: number };
  mae_mfe_analysis: { avg_mae_pct: number; avg_mfe_pct: number; trades_analyzed: number };
  // ...
}

export async function AdvancedStatsSection({ period, tag }: { period: string; tag?: string }) {
  const params = new URLSearchParams();
  if (period !== 'all') params.set('period', period);
  if (tag) params.set('tag', tag);
  const qs = params.toString() ? `?${params}` : '';

  const data = await serverApi.get<AdvancedResponse>(`/stats/advanced${qs}`, {
    cache: 'no-store',
  });

  return <AdvancedStatsGrid stats={data} hasData />;
}

// ═════════════════════════════════════════════════════════════════
// ФАЙЛ 6: src/app/dashboard/sections/AIInsightsSection.tsx
// Самая медленная секция. Демонстрирует, что streaming реально нужен —
// без него весь дашборд блокировался бы на 3-5 секунд.
// ═════════════════════════════════════════════════════════════════

import { serverApi } from '@/lib/serverApiClient';
import { Brain, TrendingDown, TrendingUp } from 'lucide-react';

interface AIInsight {
  id: number;
  category: 'risk' | 'pattern' | 'recommendation';
  severity: 'info' | 'warning' | 'critical';
  title: string;
  body: string;
}

export async function AIInsightsSection({ period }: { period: string }) {
  // AI-эндпоинт может занимать 3-5 секунд — пользователь увидит
  // <AISectionSkeleton /> всё это время, пока остальной дашборд уже работает.
  const insights = await serverApi.get<AIInsight[]>(
    `/ai/insights?period=${period}`,
    {
      // Кэшируем на 5 минут — AI стоит денег, не дёргать на каждый рендер
      next: { revalidate: 300, tags: ['ai-insights'] },
    },
  );

  if (insights.length === 0) {
    return (
      <div className="rounded-[var(--radius-xl)] border border-[var(--border)] bg-[var(--surface-1)] p-6">
        <h3 className="text-base font-semibold mb-1">AI-инсайты</h3>
        <p className="text-[13px] text-[var(--text-tertiary)]">
          Добавьте больше сделок — AI начнёт находить паттерны.
        </p>
      </div>
    );
  }

  return (
    <section className="rounded-[var(--radius-xl)] border border-[var(--border)] bg-[var(--surface-1)] p-6">
      <div className="flex items-center gap-2 mb-4">
        <Brain size={18} className="text-[#a78bfa]" />
        <h3 className="text-base font-semibold tracking-tight">AI-инсайты</h3>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {insights.map((insight) => (
          <article
            key={insight.id}
            className="rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--surface-2)] p-4 flex flex-col gap-2"
          >
            <div className="flex items-center gap-2">
              {insight.severity === 'critical' ? (
                <TrendingDown size={14} className="text-[var(--danger)]" />
              ) : (
                <TrendingUp size={14} className="text-[var(--success)]" />
              )}
              <h4 className="text-sm font-semibold">{insight.title}</h4>
            </div>
            <p className="text-[12px] leading-relaxed text-[var(--text-secondary)]">
              {insight.body}
            </p>
          </article>
        ))}
      </div>
    </section>
  );
}

// ═════════════════════════════════════════════════════════════════
// ИТОГ
// ═════════════════════════════════════════════════════════════════
//
// User journey:
//   t=0ms:   браузер получает HTML с шеллом + 4 заглушками
//   t=50ms:  hydration, AppShell интерактивен
//   t=200ms: EquityCurveSection долетела, заменила свою заглушку
//   t=350ms: StatsGridSection долетела
//   t=900ms: AdvancedStatsSection долетела
//   t=4200ms: AIInsightsSection долетела, дашборд полностью готов
//
// Vs. текущая реализация:
//   t=0ms:   браузер получает HTML c <DashboardSkeleton />
//   t=50ms:  hydration, useEffect стартует первый fetch
//   t=200ms: первый fetch вернулся, ждём второй
//   t=4200ms: оба fetch'а вернулись, рендер всего дашборда разом
//
// Streaming-вариант показывает первый контент в 4 раза быстрее.
