/**
 * /dashboard-demo — изолированная демо-страница Server Components + Suspense.
 *
 * Цель: показать паттерн streaming на ОДНОЙ секции (EquityCurveSection),
 * не перекраивая существующий /. Пользователь может открыть /dashboard-demo
 * параллельно с / и увидеть разницу в first paint.
 *
 * НЕ используется в production — это demonstration ground для PR4.
 *
 * Принципы:
 *   - Файл — Server Component (нет 'use client').
 *   - Async, но БЕЗ await на верхнем уровне: shell должен отдаваться мгновенно.
 *   - searchParams — Promise (Next 16 contract).
 *   - Каждая независимая секция обёрнута в свой <Suspense> с собственным fallback.
 *
 * Архитектурное замечание:
 *   AppShell сейчас 'use client' (sidebar с popover/cmdk). Это нормально —
 *   Client-провайдеры сверху не превращают Server-children внутри в Client.
 *   AppShell получает {children} через React.ReactNode-prop, и реальные
 *   Server-секции (EquityCurveSection) рендерятся на сервере как обычно.
 */

import { Suspense } from 'react';

import { AppShell } from '@/components/AppShell';
import { EquityCurveSection } from './sections/EquityCurveSection';
import { EquityCurveSkeleton } from './sections/EquityCurveSkeleton';

export const metadata = {
  title: 'Дашборд (Server demo) · Эмпирик',
  description: 'Демо Server Components + Suspense streaming на изолированном роуте',
};

type DashboardDemoPageProps = {
  params: Promise<Record<string, never>>;
  searchParams: Promise<{
    period?: string;
    tag?: string;
  }>;
};

export default async function DashboardDemoPage({ searchParams }: DashboardDemoPageProps) {
  // searchParams — Promise в Next 16. Резолвим один раз.
  const sp = await searchParams;
  const period = sp.period ?? 'all';
  const tag = sp.tag;

  return (
    <AppShell pageTitle="Дашборд (Server demo)">
      <div className="p-6 md:p-8 max-w-6xl mx-auto flex flex-col gap-5">
        <header>
          <h1 className="text-3xl font-bold tracking-tight mb-1">
            Дашборд (Server demo)
          </h1>
          <p className="text-sm text-[var(--text-secondary)]">
            Демонстрация Server Components + Suspense streaming. Первый paint
            страницы происходит мгновенно, секции заполняются по мере
            готовности данных с бекенда.
          </p>
        </header>

        {/* Suspense вокруг ОДНОЙ секции — изолированный паттерн.
            key={period} перезапускает Suspense fallback при смене ?period=...
            и не показывает stale-данные. */}
        <Suspense
          key={`equity-${period}-${tag ?? ''}`}
          fallback={<EquityCurveSkeleton />}
        >
          <EquityCurveSection period={period} tag={tag} />
        </Suspense>
      </div>
    </AppShell>
  );
}
