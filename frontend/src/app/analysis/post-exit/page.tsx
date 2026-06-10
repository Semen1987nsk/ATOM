"use client";
/**
 * /analysis/post-exit — анализ упущенной прибыли после закрытия
 *
 * PostExitCard самодостаточен: запускает /post-exit/* эндпоинты и сам рисует
 * результаты. Нам нужен только tradesCount чтобы показать, сколько данных
 * можно проанализировать.
 */
import { useEffect, useState } from "react";
import { Clock } from "lucide-react";
import { AppShell } from "@/components/AppShell";
import { AnalysisPageHeader } from "@/components/analysis/AnalysisPageHeader";
import { PostExitCard } from "@/components/dashboard/PostExitCard";
import { DashboardSkeleton } from "@/components/Skeleton";
import { api, ApiError } from "@/lib/apiClient";
import { useAuth } from "@/contexts/AuthContext";
import { DataError } from "@/components/ui/DataError";

interface MinimalTrade {
  id: number;
  exit_at?: string;
}

export default function PostExitPage() {
  const { user, isLoading: authLoading } = useAuth();
  const [tradesCount, setTradesCount] = useState<number | null>(null);
  const [error, setError] = useState<ApiError | Error | null>(null);
  const [refetchKey, setRefetchKey] = useState(0);

  useEffect(() => {
    if (!user) {
      setTradesCount(0);
      return;
    }
    setError(null);
    let cancelled = false;
    api
      .get<MinimalTrade[]>("/trades/")
      .then((data) => {
        if (cancelled) return;
        const closed = Array.isArray(data) ? data.filter((t) => t.exit_at).length : 0;
        setTradesCount(closed);
      })
      .catch((e) => {
        if (cancelled) return;
        setTradesCount(0);
        setError(e as ApiError | Error);
      });
    return () => {
      cancelled = true;
    };
  }, [user, refetchKey]);

  const retry = () => { setTradesCount(null); setRefetchKey((k) => k + 1); };

  if (authLoading) return <DashboardSkeleton />;

  return (
    <AppShell pageTitle="Post-Exit анализ">
      <div className="p-6 md:p-8 max-w-6xl mx-auto">
        <AnalysisPageHeader
          title="Post-Exit анализ"
          subtitle="Что было с ценой после вашего выхода. Реальные свечи MOEX, мульти-таймфрейм, детекция early-exit."
          Icon={Clock}
          accentColor="amber"
        />

        {!user ? (
          <EmptyState text="Войдите, чтобы проанализировать выходы из своих сделок." />
        ) : error ? (
          <DataError error={error} onRetry={retry} />
        ) : tradesCount === null ? (
          <DashboardSkeleton />
        ) : tradesCount === 0 ? (
          <EmptyState text="Нет закрытых сделок для анализа. Закройте хотя бы одну позицию — и здесь появятся данные по упущенной прибыли." />
        ) : (
          <PostExitCard tradesCount={tradesCount} />
        )}
      </div>
    </AppShell>
  );
}

function EmptyState({ text }: { text: string }) {
  return (
    <div className="rounded-[var(--radius-xl)] border border-[var(--border)] bg-[var(--surface-1)] p-10 text-center">
      <div className="w-12 h-12 mx-auto mb-3 rounded-full bg-[var(--surface-2)] flex items-center justify-center text-[var(--text-tertiary)]">
        <Clock size={20} />
      </div>
      <p className="text-[14px] text-[var(--text-secondary)] max-w-sm mx-auto">{text}</p>
    </div>
  );
}
