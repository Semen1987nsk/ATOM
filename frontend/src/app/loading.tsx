/**
 * FE-06 — App Router root loading boundary.
 *
 * Показывается, пока React-Server-Component-рендер сегмента ещё не закончен.
 * Используем уже существующий DashboardSkeleton — он соответствует layout'у
 * дашборда, который и есть root-страница `/`.
 */
import { DashboardSkeleton } from '@/components/Skeleton';

export default function RootLoading() {
  return <DashboardSkeleton />;
}
