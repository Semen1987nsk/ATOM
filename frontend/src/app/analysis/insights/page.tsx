"use client";
/**
 * /analysis/insights — AI-инсайты и риск-tier
 *
 * До этого жил карточкой на дашборде. Вынесли, чтобы дашборд не превращался
 * в простыню, а у инсайтов был собственный экран с фильтром по периоду.
 */
import { useState } from "react";
import { Brain } from "lucide-react";
import { AppShell } from "@/components/AppShell";
import { AnalysisPageHeader } from "@/components/analysis/AnalysisPageHeader";
import { FilterPanel, Filters } from "@/components/FilterPanel";
import { AIInsightsCard } from "@/components/dashboard/AIInsightsCard";
import { DashboardSkeleton } from "@/components/Skeleton";
import { useAnalysisStats } from "@/lib/useAnalysisStats";
import { useAuth } from "@/contexts/AuthContext";

export default function InsightsPage() {
  const { user, isLoading: authLoading } = useAuth();
  const [filters, setFilters] = useState<Filters>({ period: "all" });
  const { stats, loading } = useAnalysisStats(filters);

  if (authLoading) return <DashboardSkeleton />;

  return (
    <AppShell pageTitle="AI-инсайты">
      <div className="p-6 md:p-8 max-w-5xl mx-auto">
        <AnalysisPageHeader
          title="AI-инсайты"
          subtitle="Рекомендации по риск-менеджменту и сетапам, основанные на ваших последних сделках."
          Icon={Brain}
          accentColor="violet"
        />

        <div className="mb-6">
          <FilterPanel filters={filters} onChange={setFilters} />
        </div>

        {!user ? (
          <EmptyState text="Войдите, чтобы увидеть инсайты по своим сделкам." />
        ) : loading ? (
          <DashboardSkeleton />
        ) : !stats || stats.total_trades === 0 ? (
          <EmptyState text="Сделок пока нет. Добавьте первую — рекомендации появятся автоматически." />
        ) : (
          <AIInsightsCard
            recommendations={stats.mae_mfe_analysis?.recommendations || []}
            optimalF={stats.optimal_f || 0}
          />
        )}
      </div>
    </AppShell>
  );
}

function EmptyState({ text }: { text: string }) {
  return (
    <div className="rounded-[var(--radius-xl)] border border-[var(--border)] bg-[var(--surface-1)] p-10 text-center">
      <div className="w-12 h-12 mx-auto mb-3 rounded-full bg-[var(--surface-2)] flex items-center justify-center text-[var(--text-tertiary)]">
        <Brain size={20} />
      </div>
      <p className="text-[14px] text-[var(--text-secondary)] max-w-sm mx-auto">{text}</p>
    </div>
  );
}
