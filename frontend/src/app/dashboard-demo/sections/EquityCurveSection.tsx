/**
 * EquityCurveSection — Server Component, фетчит /stats/ и передаёт данные
 * в Client-обёртку EquityCurveCard (Recharts требует window).
 *
 * Это «правильная половина паттерна», которой не хватало в проекте:
 *   - data fetch на сервере (httpOnly-cookies passthrough, без flash-of-empty)
 *   - chart render на клиенте (recharts ssr unfriendly)
 *
 * Если бекенд недоступен (504, 502, network error) — рендерим понятный
 * fallback. Не падаем в error boundary, потому что demo-страница должна
 * оставаться полезной даже без бекенда (например при первом open'е, пока
 * пользователь ещё не запустил FastAPI на 8000).
 */

import { EquityCurveCard } from '@/components/dashboard/EquityCurveCard';
import { serverApi, ServerApiError } from '@/lib/serverApiClient';

interface EquityPoint {
  date: string;
  balance: number;
}

interface BenchmarkPoint {
  date: string;
  value: number;
}

interface StatsResponse {
  equity_curve?: EquityPoint[];
  imoex_curve?: BenchmarkPoint[];
  initial_balance?: number | null;
}

interface EquityCurveSectionProps {
  period: string;
  tag?: string;
}

function buildStatsPath(period: string, tag: string | undefined): string {
  const params = new URLSearchParams();
  if (period && period !== 'all') {
    params.set('period', period);
  }
  if (tag) {
    params.set('tag', tag);
  }
  const qs = params.toString();
  return qs ? `/stats/?${qs}` : '/stats/';
}

export async function EquityCurveSection({ period, tag }: EquityCurveSectionProps) {
  const path = buildStatsPath(period, tag);

  let data: StatsResponse | null = null;
  let errorMessage: string | null = null;

  try {
    // /stats/ — personalized, зависит от user-cookie. Никогда не кэшируем.
    data = await serverApi.get<StatsResponse>(path, { cache: 'no-store' });
  } catch (e) {
    if (e instanceof ServerApiError) {
      errorMessage =
        e.status === 401
          ? 'Войдите, чтобы увидеть кривую капитала.'
          : `Не удалось загрузить (${e.status}).`;
    } else {
      // Network error / fetch failed — backend, скорее всего, ещё не поднят.
      errorMessage = 'Не удалось загрузить. Проверьте, что backend запущен на 8000.';
    }
  }

  if (errorMessage !== null || data === null) {
    return (
      <section
        role="status"
        className="rounded-[var(--radius-xl)] border border-[var(--border)] bg-[var(--surface-1)] p-6"
      >
        <h3 className="text-base font-semibold tracking-tight mb-1">
          Кривая капитала
        </h3>
        <p className="text-[13px] text-[var(--text-tertiary)]">
          {errorMessage ?? 'Нет данных.'}
        </p>
      </section>
    );
  }

  const equityCurve: EquityPoint[] = Array.isArray(data.equity_curve)
    ? data.equity_curve
    : [];
  const imoexCurve: BenchmarkPoint[] | undefined = Array.isArray(data.imoex_curve)
    ? data.imoex_curve
    : undefined;
  const initialBalance: number | undefined =
    typeof data.initial_balance === 'number' ? data.initial_balance : undefined;

  return (
    <EquityCurveCard
      data={equityCurve}
      benchmark={imoexCurve}
      benchmarkLabel="IMOEX"
      initialBalance={initialBalance}
    />
  );
}
