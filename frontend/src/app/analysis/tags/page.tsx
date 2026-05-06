"use client";
/**
 * /analysis/tags — статистика по тегам и сетапам
 *
 * Раньше — TagStatsCard в подвале дашборда. Теперь полноценная страница
 * с фильтром по периоду + сама карточка. На Phase 5 сюда же приедет разбор
 * по тикерам / asset_type.
 */
import { useState } from "react";
import { Tag } from "lucide-react";
import { AppShell } from "@/components/AppShell";
import { AnalysisPageHeader } from "@/components/analysis/AnalysisPageHeader";
import { FilterPanel, Filters } from "@/components/FilterPanel";
import { TagStatsCard } from "@/components/dashboard/TagStatsCard";
import { DashboardSkeleton } from "@/components/Skeleton";
import { useAnalysisStats } from "@/lib/useAnalysisStats";
import { useAuth } from "@/contexts/AuthContext";

export default function TagsPage() {
  const { user, isLoading: authLoading } = useAuth();
  const [filters, setFilters] = useState<Filters>({ period: "all" });
  const { stats, loading } = useAnalysisStats(filters);

  if (authLoading) return <DashboardSkeleton />;

  return (
    <AppShell pageTitle="По тегам и сетапам">
      <div className="p-6 md:p-8 max-w-5xl mx-auto">
        <AnalysisPageHeader
          title="По тегам и сетапам"
          subtitle="Какие подходы работают лучше: PnL, win-rate и количество сделок в разрезе тегов."
          Icon={Tag}
          accentColor="emerald"
        />

        <div className="mb-6">
          <FilterPanel filters={filters} onChange={setFilters} />
        </div>

        {!user ? (
          <EmptyState text="Войдите, чтобы увидеть свою разбивку по тегам." />
        ) : loading ? (
          <DashboardSkeleton />
        ) : !stats || stats.total_trades === 0 ? (
          <EmptyState text="Сделок пока нет. Добавьте сделки и проставьте теги — здесь появится их рейтинг." />
        ) : (
          <TagStatsCard tagStats={stats.tag_stats || []} />
        )}
      </div>
    </AppShell>
  );
}

function EmptyState({ text }: { text: string }) {
  return (
    <div className="rounded-[var(--radius-xl)] border border-[var(--border)] bg-[var(--surface-1)] p-10 text-center">
      <div className="w-12 h-12 mx-auto mb-3 rounded-full bg-[var(--surface-2)] flex items-center justify-center text-[var(--text-tertiary)]">
        <Tag size={20} />
      </div>
      <p className="text-[14px] text-[var(--text-secondary)] max-w-sm mx-auto">{text}</p>
    </div>
  );
}
