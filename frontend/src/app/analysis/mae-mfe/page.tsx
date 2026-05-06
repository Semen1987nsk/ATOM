"use client";
/**
 * /analysis/mae-mfe — Maximum Adverse / Favorable Excursion analytics
 *
 * Панель самодостаточна (фетчит и фильтрует сама), поэтому страница тонкая.
 * Свои период/тег-контролы у MAEMFEAnalysisPanel есть внутри — внешний
 * FilterPanel сюда не ставим, он бы дублировал поведение.
 */
import { Target } from "lucide-react";
import { AppShell } from "@/components/AppShell";
import { AnalysisPageHeader } from "@/components/analysis/AnalysisPageHeader";
import { MAEMFEAnalysisPanel } from "@/components/dashboard/MAEMFEAnalysisPanel";
import { DashboardSkeleton } from "@/components/Skeleton";
import { useAuth } from "@/contexts/AuthContext";

export default function MAEMFEPage() {
  const { user, isLoading: authLoading } = useAuth();

  if (authLoading) return <DashboardSkeleton />;

  return (
    <AppShell pageTitle="MAE / MFE анализ">
      <div className="p-6 md:p-8 max-w-7xl mx-auto">
        <AnalysisPageHeader
          title="MAE / MFE анализ"
          subtitle="Максимальный негативный и благоприятный экскурс цены — для оптимизации стопов и тейк-профитов."
          Icon={Target}
          accentColor="indigo"
        />

        {!user ? (
          <EmptyState text="Войдите, чтобы запустить MAE/MFE анализ по своим сделкам." />
        ) : (
          <MAEMFEAnalysisPanel />
        )}
      </div>
    </AppShell>
  );
}

function EmptyState({ text }: { text: string }) {
  return (
    <div className="rounded-[var(--radius-xl)] border border-[var(--border)] bg-[var(--surface-1)] p-10 text-center">
      <div className="w-12 h-12 mx-auto mb-3 rounded-full bg-[var(--surface-2)] flex items-center justify-center text-[var(--text-tertiary)]">
        <Target size={20} />
      </div>
      <p className="text-[14px] text-[var(--text-secondary)] max-w-sm mx-auto">{text}</p>
    </div>
  );
}
