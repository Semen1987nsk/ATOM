/**
 * Пример: страница «Кривая капитала» с правильным разделением
 * Server (data fetch) и Client (Recharts render).
 *
 * Контекст Empirik:
 *   - src/components/dashboard/EquityCurveCard.tsx уже Client (Recharts требует window).
 *   - Получает data как props — это правильно.
 *   - Не хватает: Server-обёртки, которая фетчит данные с разными периодами,
 *     и Client-обёртки, которая делает period-switcher с useTransition.
 *
 * Этот пример показывает полный паттерн «Server fetches data → Client renders chart»:
 *   - Page (Server) читает searchParams, фетчит equity curve
 *   - Chart (Client, dynamic import, ssr: false) рисует Recharts
 *   - Period switcher (Client) использует useTransition для smooth UX при переключении
 *
 * Файлы:
 *   - src/app/equity/page.tsx                    (Server, async, читает searchParams)
 *   - src/app/equity/loading.tsx                 (route-level fallback)
 *   - src/components/equity/EquityChartClient.tsx  (Client, dynamic Recharts)
 *   - src/components/equity/PeriodSwitcher.tsx     (Client, useTransition + router.push)
 *   - src/components/equity/EquityChartSkeleton.tsx (Server, статичный)
 */

// ═════════════════════════════════════════════════════════════════
// ФАЙЛ 1: src/app/equity/loading.tsx
// ═════════════════════════════════════════════════════════════════

import { EquityChartSkeleton } from '@/components/equity/EquityChartSkeleton';

export default function EquityLoading() {
  return (
    <div className="p-6 md:p-8 max-w-6xl mx-auto">
      <EquityChartSkeleton />
    </div>
  );
}

// ═════════════════════════════════════════════════════════════════
// ФАЙЛ 2: src/app/equity/page.tsx
// Server Component. Читает searchParams, фетчит данные, передаёт в Client-чарт.
// ═════════════════════════════════════════════════════════════════

import { Suspense } from 'react';
import { AppShell } from '@/components/AppShell';
import { serverApi } from '@/lib/serverApiClient';
import { PeriodSwitcher, type Period, ALL_PERIODS } from '@/components/equity/PeriodSwitcher';
import { EquityChartClient } from '@/components/equity/EquityChartClient';
import { EquityChartSkeleton } from '@/components/equity/EquityChartSkeleton';

interface EquityCurveResponse {
  equity_curve: Array<{ date: string; balance: number }>;
  imoex_curve?: Array<{ date: string; value: number }>;
  initial_balance: number;
  current_balance: number;
  period_label: string;
}

type EquityPageProps = {
  params: Promise<Record<string, never>>;
  searchParams: Promise<{ period?: string }>;
};

function isValidPeriod(value: string | undefined): value is Period {
  return value !== undefined && (ALL_PERIODS as readonly string[]).includes(value);
}

export const metadata = {
  title: 'Кривая капитала · Empirik',
};

export default async function EquityPage({ searchParams }: EquityPageProps) {
  const sp = await searchParams;
  const period: Period = isValidPeriod(sp.period) ? sp.period : 'all';

  return (
    <AppShell pageTitle="Кривая капитала">
      <div className="p-6 md:p-8 max-w-6xl mx-auto flex flex-col gap-5">
        <header className="flex items-end justify-between gap-4 flex-wrap">
          <div>
            <h1 className="text-3xl font-bold tracking-tight mb-1">Кривая капитала</h1>
            <p className="text-sm text-[var(--text-secondary)]">
              Кумулятивный баланс счёта по времени с benchmark IMOEX
            </p>
          </div>
          <PeriodSwitcher current={period} />
        </header>

        {/* key={period} — заставляет Suspense заново показать fallback при смене
            периода. Без key React переиспользует boundary, и старые данные
            висят до прихода новых. С key — мгновенный skeleton. */}
        <Suspense key={period} fallback={<EquityChartSkeleton />}>
          <EquityDataLoader period={period} />
        </Suspense>
      </div>
    </AppShell>
  );
}

async function EquityDataLoader({ period }: { period: Period }) {
  const qs = period === 'all' ? '' : `?period=${period}`;
  const data = await serverApi.get<EquityCurveResponse>(`/stats/equity${qs}`, {
    cache: 'no-store',
  });

  return (
    <EquityChartClient
      data={data.equity_curve}
      benchmark={data.imoex_curve}
      initialBalance={data.initial_balance}
      currentBalance={data.current_balance}
      periodLabel={data.period_label}
    />
  );
}

// ═════════════════════════════════════════════════════════════════
// ФАЙЛ 3: src/components/equity/PeriodSwitcher.tsx
// Client. Меняет ?period=... через router.push, обёрнутый в useTransition.
// ═════════════════════════════════════════════════════════════════

'use client';

import { useTransition } from 'react';
import { useRouter, usePathname } from 'next/navigation';
import { Loader2 } from 'lucide-react';

export const ALL_PERIODS = ['all', '7d', '30d', '90d', 'ytd', '1y'] as const;
export type Period = (typeof ALL_PERIODS)[number];

const PERIOD_LABELS: Record<Period, string> = {
  all: 'Всё время',
  '7d': '7 дней',
  '30d': '30 дней',
  '90d': '90 дней',
  ytd: 'YTD',
  '1y': '1 год',
};

interface PeriodSwitcherProps {
  current: Period;
}

export function PeriodSwitcher({ current }: PeriodSwitcherProps) {
  const router = useRouter();
  const pathname = usePathname();
  const [isPending, startTransition] = useTransition();

  const handleSelect = (period: Period) => {
    if (period === current) return;
    const qs = period === 'all' ? '' : `?period=${period}`;
    startTransition(() => {
      router.push(`${pathname}${qs}`, { scroll: false });
    });
  };

  return (
    <div className="inline-flex items-center gap-1 p-1 rounded-[var(--radius-md)] border border-[var(--border)] bg-[var(--surface-2)]">
      {ALL_PERIODS.map((period) => {
        const isActive = period === current;
        return (
          <button
            key={period}
            type="button"
            onClick={() => handleSelect(period)}
            disabled={isPending}
            aria-pressed={isActive}
            className={`relative px-3 py-1.5 text-[12px] font-medium rounded-[var(--radius-sm)] transition-colors ${
              isActive
                ? 'bg-[var(--accent)] text-white'
                : 'text-[var(--text-secondary)] hover:text-[var(--foreground)] hover:bg-[var(--surface-hover)]'
            } disabled:opacity-60`}
          >
            {isPending && isActive && (
              <Loader2 size={11} className="inline mr-1 animate-spin" />
            )}
            {PERIOD_LABELS[period]}
          </button>
        );
      })}
    </div>
  );
}

// ═════════════════════════════════════════════════════════════════
// ФАЙЛ 4: src/components/equity/EquityChartClient.tsx
// Client-обёртка над Recharts. dynamic() с ssr:false убирает Recharts
// из server-bundle полностью.
// ═════════════════════════════════════════════════════════════════

'use client';

import dynamic from 'next/dynamic';
import { TrendingUp, TrendingDown } from 'lucide-react';
import { EquityChartSkeleton } from './EquityChartSkeleton';

// Recharts весит ~100KB. Lazy-load + ssr:false — чистый bundle на сервере,
// и chart грузится только когда страница реально открыта.
const RechartsBody = dynamic(
  () => import('./EquityChartRecharts').then((m) => m.EquityChartRecharts),
  {
    ssr: false,
    loading: () => <EquityChartSkeleton compact />,
  },
);

interface EquityChartClientProps {
  data: Array<{ date: string; balance: number }>;
  benchmark?: Array<{ date: string; value: number }>;
  initialBalance: number;
  currentBalance: number;
  periodLabel: string;
}

export function EquityChartClient(props: EquityChartClientProps) {
  const { data, initialBalance, currentBalance, periodLabel } = props;

  if (data.length === 0) {
    return (
      <div className="rounded-[var(--radius-xl)] border border-[var(--border)] bg-[var(--surface-1)] p-6">
        <h3 className="text-base font-semibold mb-1">Нет сделок в выбранном периоде</h3>
        <p className="text-[13px] text-[var(--text-tertiary)]">
          Попробуйте сменить период или добавить сделки.
        </p>
      </div>
    );
  }

  const change = currentBalance - initialBalance;
  const changePct = initialBalance > 0 ? (change / initialBalance) * 100 : 0;
  const tone: 'success' | 'danger' = change >= 0 ? 'success' : 'danger';

  const formatRub = (n: number): string =>
    `${n.toLocaleString('ru-RU', { maximumFractionDigits: 0 })} ₽`;

  return (
    <section className="rounded-[var(--radius-xl)] border border-[var(--border)] bg-[var(--surface-1)] p-6">
      <header className="flex items-start justify-between gap-4 mb-5 flex-wrap">
        <div>
          <h3 className="text-base font-semibold tracking-tight">{periodLabel}</h3>
          <p className="text-[12px] text-[var(--text-tertiary)] mt-0.5">
            Старт: {formatRub(initialBalance)}
          </p>
        </div>
        <div className="flex items-baseline gap-2">
          <span className="text-[24px] font-bold tabular-nums">
            {formatRub(currentBalance)}
          </span>
          <span
            className={`flex items-center gap-1 text-[13px] font-semibold tabular-nums ${
              tone === 'success' ? 'text-[var(--success)]' : 'text-[var(--danger)]'
            }`}
          >
            {tone === 'success' ? <TrendingUp size={13} /> : <TrendingDown size={13} />}
            {change >= 0 ? '+' : ''}
            {formatRub(change)}
            <span className="opacity-70">
              ({changePct >= 0 ? '+' : ''}
              {changePct.toFixed(1)}%)
            </span>
          </span>
        </div>
      </header>

      <div className="h-[360px] -mx-2">
        <RechartsBody {...props} />
      </div>
    </section>
  );
}

// ═════════════════════════════════════════════════════════════════
// ФАЙЛ 5: src/components/equity/EquityChartRecharts.tsx
// Сам Recharts. Отдельный файл, потому что dynamic import нужен на конкретный модуль.
// ═════════════════════════════════════════════════════════════════

'use client';

import {
  ComposedChart,
  Area,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
} from 'recharts';
import { useMemo } from 'react';

interface RechartsBodyProps {
  data: Array<{ date: string; balance: number }>;
  benchmark?: Array<{ date: string; value: number }>;
  initialBalance: number;
}

export function EquityChartRecharts({ data, benchmark, initialBalance }: RechartsBodyProps) {
  const merged = useMemo(() => {
    const benchByDate: Record<string, number> = {};
    if (benchmark) for (const b of benchmark) benchByDate[b.date.slice(0, 10)] = b.value;
    const firstBench = benchmark?.[0]?.value;
    const ratio = firstBench && data[0]?.balance ? data[0].balance / firstBench : 1;
    return data.map((p) => ({
      date: p.date,
      balance: p.balance,
      benchmark: benchByDate[p.date.slice(0, 10)] !== undefined
        ? benchByDate[p.date.slice(0, 10)] * ratio
        : null,
    }));
  }, [data, benchmark]);

  const tone = data[data.length - 1].balance >= initialBalance ? 'success' : 'danger';
  const lineColor = tone === 'success' ? 'var(--success)' : 'var(--danger)';

  return (
    <ResponsiveContainer width="100%" height="100%">
      <ComposedChart data={merged} margin={{ top: 5, right: 12, left: 0, bottom: 0 }}>
        <defs>
          <linearGradient id="equityGradient" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={lineColor} stopOpacity={0.25} />
            <stop offset="100%" stopColor={lineColor} stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" vertical={false} />
        <XAxis
          dataKey="date"
          tickFormatter={(v: string) =>
            new Date(v).toLocaleDateString('ru-RU', { day: '2-digit', month: 'short' })
          }
          stroke="var(--text-tertiary)"
          tick={{ fontSize: 11 }}
          axisLine={false}
          tickLine={false}
          minTickGap={40}
        />
        <YAxis
          stroke="var(--text-tertiary)"
          tick={{ fontSize: 11 }}
          axisLine={false}
          tickLine={false}
          tickFormatter={(v: number) =>
            Math.abs(v) >= 1_000_000
              ? `${(v / 1_000_000).toFixed(1)}M`
              : Math.abs(v) >= 1_000
                ? `${(v / 1_000).toFixed(0)}K`
                : `${v}`
          }
          width={70}
        />
        {initialBalance > 0 && (
          <ReferenceLine
            y={initialBalance}
            stroke="var(--text-tertiary)"
            strokeDasharray="4 4"
            strokeOpacity={0.5}
          />
        )}
        <Tooltip />
        <Area
          type="monotone"
          dataKey="balance"
          stroke={lineColor}
          strokeWidth={2}
          fill="url(#equityGradient)"
          dot={false}
        />
        {benchmark && benchmark.length > 0 && (
          <Line
            type="monotone"
            dataKey="benchmark"
            stroke="var(--text-tertiary)"
            strokeWidth={1.5}
            strokeDasharray="5 4"
            dot={false}
          />
        )}
      </ComposedChart>
    </ResponsiveContainer>
  );
}

// ═════════════════════════════════════════════════════════════════
// ФАЙЛ 6: src/components/equity/EquityChartSkeleton.tsx
// Server Component (без 'use client'). Чистый CSS-skeleton.
// ═════════════════════════════════════════════════════════════════

export function EquityChartSkeleton({ compact = false }: { compact?: boolean }) {
  return (
    <div
      role="status"
      aria-busy="true"
      aria-label="Загрузка графика капитала"
      className={`rounded-[var(--radius-xl)] border border-[var(--border)] bg-[var(--surface-1)] ${
        compact ? 'p-2' : 'p-6'
      }`}
    >
      {!compact && (
        <div className="flex items-start justify-between gap-4 mb-5 flex-wrap">
          <div className="flex flex-col gap-2">
            <div className="h-4 w-32 rounded bg-[var(--surface-2)] animate-pulse" />
            <div className="h-3 w-24 rounded bg-[var(--surface-2)] animate-pulse" />
          </div>
          <div className="flex flex-col items-end gap-2">
            <div className="h-6 w-28 rounded bg-[var(--surface-2)] animate-pulse" />
            <div className="h-3 w-20 rounded bg-[var(--surface-2)] animate-pulse" />
          </div>
        </div>
      )}
      <div className="h-[360px] rounded bg-[var(--surface-2)] animate-pulse" />
    </div>
  );
}

// ═════════════════════════════════════════════════════════════════
// ИТОГ — что даёт этот паттерн
// ═════════════════════════════════════════════════════════════════
//
// 1. Recharts (~100KB) НЕ попадает в server bundle (ssr: false).
// 2. Recharts НЕ попадает в initial client bundle (dynamic import) — догружается,
//    когда пользователь реально открыл /equity.
// 3. Server-side fetch — initial paint без flash-of-loading.
// 4. Period switcher через ?period=... в URL — shareable links.
// 5. useTransition даёт smooth UX при переключении (старые данные не моргают).
// 6. <Suspense key={period}> заставляет skeleton показаться при смене периода.
// 7. SEO-friendly: HTML с реальными цифрами в DOM.
