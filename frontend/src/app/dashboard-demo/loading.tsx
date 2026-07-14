/**
 * Route-level fallback для /dashboard-demo.
 *
 * Показывается ТОЛЬКО при навигации к этому роуту (push, prefetch).
 * При первой загрузке (cold open) браузер сразу получает результат
 * page.tsx с уже встроенными Suspense-границами — этот fallback не
 * показывается.
 */

import { EquityCurveSkeleton } from './sections/EquityCurveSkeleton';

export default function DashboardDemoLoading() {
  return (
    <div className="p-6 md:p-8 max-w-6xl mx-auto flex flex-col gap-5">
      <div className="flex flex-col gap-2">
        <div className="h-8 w-72 rounded bg-[var(--surface-2)] animate-pulse" />
        <div className="h-4 w-96 rounded bg-[var(--surface-2)] animate-pulse" />
      </div>
      <EquityCurveSkeleton />
    </div>
  );
}
