'use client';

import dynamic from 'next/dynamic';
import { Landing } from '@/components/landing/Landing';
import { DashboardSkeleton } from '@/components/Skeleton';
import { useAuth } from '@/contexts/AuthContext';

// Дашборд статически тянет модалки, AppShell, графики (~137 KiB).
// Аноним видит только <Landing/>, поэтому грузим дашборд отдельным чанком
// лишь когда пользователь залогинен — это убирает мёртвый JS с лендинга.
const DashboardHome = dynamic(() => import('./DashboardHome'), {
  ssr: false,
  loading: () => <DashboardSkeleton />,
});

export default function Home() {
  const { user, isLoading: authLoading } = useAuth();

  if (authLoading) return <DashboardSkeleton />;
  if (!user) return <Landing />;
  return <DashboardHome />;
}
