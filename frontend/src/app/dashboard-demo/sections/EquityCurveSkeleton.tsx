/**
 * EquityCurveSkeleton — Server Component (без 'use client').
 *
 * Чистый CSS-skeleton, не тянет в bundle ни recharts, ни Skeleton.tsx
 * (тот помечен 'use client' из-за анимации). Используется как fallback
 * для <Suspense> и в loading.tsx роута.
 */

export function EquityCurveSkeleton() {
  return (
    <div
      role="status"
      aria-busy="true"
      aria-label="Загрузка кривой капитала"
      className="rounded-[var(--radius-xl)] border border-[var(--border)] bg-[var(--surface-1)] p-6"
    >
      <div className="flex items-start justify-between gap-4 mb-5 flex-wrap">
        <div className="flex flex-col gap-2">
          <div className="h-4 w-36 rounded bg-[var(--surface-2)] animate-pulse" />
          <div className="h-3 w-52 rounded bg-[var(--surface-2)] animate-pulse" />
        </div>
        <div className="flex flex-col items-end gap-2">
          <div className="h-6 w-32 rounded bg-[var(--surface-2)] animate-pulse" />
          <div className="h-3 w-24 rounded bg-[var(--surface-2)] animate-pulse" />
        </div>
      </div>
      <div className="h-[280px] rounded bg-[var(--surface-2)] animate-pulse" />
    </div>
  );
}
