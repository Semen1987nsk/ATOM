'use client';

/**
 * PR 26 (Phase 3, D6) — Onboarding Reconciliation Wizard.
 *
 * URL: /onboarding/reconcile
 *
 * Открывается автоматически после первого full sync с Tinkoff. Показывает
 * side-by-side: наши агрегаты vs broker report Tinkoff. 8 метрик с
 * цветовой кодировкой ✓/⚠/✗.
 *
 * UX: soft warning (user choice в Phase 3 plan). При breaks показываем
 * баннер «Найдены расхождения» с CTA «Связаться с поддержкой», но юзер
 * может продолжать.
 */

import { useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { CheckCircle, AlertTriangle, XCircle, Loader2, ArrowRight, Mail } from 'lucide-react';
import { api, ApiError } from '@/lib/apiClient';

type MetricStatus = 'ok' | 'soft' | 'hard';

type Metric = {
  metric: string;
  ours: string;
  broker: string;
  diff_abs: string;
  diff_pct: string;
  status: MetricStatus;
  note?: string;
};

type TransformationWarning = {
  code: string;
  severity: 'critical' | 'high' | 'medium' | 'low';
  description: string;
  count: number;
};

type Run = {
  run_id?: number;
  account_id: number;
  account_name?: string;
  status: 'ok' | 'warning' | 'break' | 'error';
  breaks_count: number;
  hard_breaks_count?: number;
  metrics?: Metric[];
  transformation_warnings?: TransformationWarning[];
  error?: string;
};

const METRIC_LABELS: Record<string, string> = {
  realized_pnl: 'Финансовый результат',
  broker_commission_total: 'Комиссия брокера',
  exchange_commission_total: 'Комиссия биржи',
  clearing_commission_total: 'Клиринговая комиссия',
  dividends_gross: 'Дивиденды (gross)',
  ndfl_withheld: 'НДФЛ удержан',
  net_cash_flow: 'Net cash flow (deposits - withdrawals)',
  end_cash_balance: 'Cash balance на конец периода',
};

function MetricRow({ m }: { m: Metric }) {
  const label = METRIC_LABELS[m.metric] || m.metric;
  const StatusIcon =
    m.status === 'ok' ? CheckCircle : m.status === 'soft' ? AlertTriangle : XCircle;
  const color =
    m.status === 'ok'
      ? 'text-green-400'
      : m.status === 'soft'
        ? 'text-orange-400'
        : 'text-red-400';
  return (
    <tr className="border-b border-slate-800/50">
      <td className="py-2 pr-4 text-slate-300">{label}</td>
      <td className="py-2 pr-4 text-right font-mono">{m.ours}</td>
      <td className="py-2 pr-4 text-right font-mono">{m.broker}</td>
      <td className="py-2 pr-4 text-right font-mono text-slate-400">{m.diff_abs}</td>
      <td className="py-2 text-center">
        <StatusIcon size={18} className={`${color} inline`} />
      </td>
    </tr>
  );
}

export default function OnboardingReconcilePage() {
  const router = useRouter();
  const [runs, setRuns] = useState<Run[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleRun = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.post<{ runs: Run[] }>(`/onboarding/reconcile?days=30`);
      setRuns(data.runs);
    } catch (e) {
      const err = e as ApiError;
      setError(err.detail || err.message || 'Ошибка проверки. Попробуйте позже.');
    } finally {
      setLoading(false);
    }
  };

  const hasBreaks = runs?.some((r) => r.status !== 'ok');
  const hasCriticalWarnings = runs?.some((r) =>
    r.transformation_warnings?.some((w) => w.severity === 'critical'),
  );

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 p-6">
      <div className="max-w-4xl mx-auto">
        <div className="mb-6">
          <h1 className="text-2xl font-semibold mb-2">Проверка корректности данных</h1>
          <p className="text-slate-400 text-sm">
            Эмпирик сверит свои расчёты с официальным брокерским отчётом Tinkoff за
            последние 30 дней. Это разовая проверка для уверенности, что цифры в
            журнале совпадают с тем, что показывает Тинькофф в личном кабинете.
          </p>
        </div>

        {!runs && (
          <div className="rounded-xl border border-slate-700/50 bg-slate-800/30 p-8">
            <div className="text-center">
              <p className="text-slate-300 mb-6">
                Нажмите «Запустить проверку» — это займёт 30–60 секунд.
                Мы запросим у Tinkoff официальный отчёт за период и сверим
                восемь финансовых показателей.
              </p>
              {error && (
                <div className="mb-4 p-3 rounded-lg bg-red-500/10 border border-red-500/30 text-red-300 text-sm">
                  {error}
                </div>
              )}
              <button
                onClick={handleRun}
                disabled={loading}
                className="px-6 py-2 bg-blue-500 hover:bg-blue-600 disabled:opacity-50 text-white rounded-md transition-colors inline-flex items-center gap-2"
              >
                {loading && <Loader2 size={18} className="animate-spin" />}
                {loading ? 'Проверяем…' : 'Запустить проверку'}
              </button>
              <div className="mt-4">
                <Link href="/" className="text-slate-500 hover:text-slate-300 text-sm">
                  Пропустить и продолжить →
                </Link>
              </div>
            </div>
          </div>
        )}

        {runs && (
          <>
            {(hasBreaks || hasCriticalWarnings) && (
              <div className="mb-6 p-4 rounded-xl border border-orange-500/40 bg-orange-500/10">
                <div className="flex items-start gap-3">
                  <AlertTriangle size={24} className="text-orange-400 mt-0.5" />
                  <div className="flex-1">
                    <h3 className="font-semibold text-orange-200 mb-1">
                      Найдены расхождения с отчётом Tinkoff
                    </h3>
                    <p className="text-sm text-slate-300 mb-3">
                      В большинстве случаев это рабочие особенности (открытые
                      позиции, разные периоды отчёта), но если суммы значительно
                      отличаются — свяжитесь с поддержкой, мы разберёмся.
                    </p>
                    <a
                      href="mailto:support@empirik.app?subject=Расхождение%20в%20reconciliation"
                      className="inline-flex items-center gap-1 text-sm text-orange-300 hover:text-orange-200"
                    >
                      <Mail size={14} /> support@empirik.app
                    </a>
                  </div>
                </div>
              </div>
            )}

            {runs.map((r) => (
              <div
                key={r.account_id}
                className="mb-4 rounded-xl border border-slate-700/50 bg-slate-800/30 p-6"
              >
                <div className="flex items-center justify-between mb-4">
                  <h2 className="text-lg font-semibold">
                    {r.account_name || `Account #${r.account_id}`}
                  </h2>
                  <span
                    className={`px-2 py-0.5 rounded text-xs font-medium ${
                      r.status === 'ok'
                        ? 'bg-green-500/20 text-green-300'
                        : r.status === 'warning'
                          ? 'bg-yellow-500/20 text-yellow-300'
                          : 'bg-red-500/20 text-red-300'
                    }`}
                  >
                    {r.status === 'ok'
                      ? 'OK'
                      : r.status === 'warning'
                        ? 'предупреждения'
                        : 'расхождения'}
                  </span>
                </div>

                {r.error && (
                  <p className="text-red-300 text-sm">Ошибка: {r.error}</p>
                )}

                {r.metrics && r.metrics.length > 0 && (
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="text-slate-500 text-xs uppercase tracking-wide">
                          <th className="text-left pb-2">Метрика</th>
                          <th className="text-right pb-2">Эмпирик</th>
                          <th className="text-right pb-2">Tinkoff</th>
                          <th className="text-right pb-2">Разница</th>
                          <th className="text-center pb-2">Статус</th>
                        </tr>
                      </thead>
                      <tbody>
                        {r.metrics.map((m) => (
                          <MetricRow key={m.metric} m={m} />
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}

                {r.transformation_warnings && r.transformation_warnings.length > 0 && (
                  <div className="mt-4 pt-4 border-t border-slate-700/50">
                    <h3 className="text-xs uppercase text-slate-500 mb-2">
                      Диагностика данных
                    </h3>
                    <ul className="space-y-1 text-xs">
                      {r.transformation_warnings.map((w) => (
                        <li
                          key={w.code}
                          className={`${
                            w.severity === 'critical'
                              ? 'text-red-300'
                              : w.severity === 'high'
                                ? 'text-orange-300'
                                : 'text-slate-400'
                          }`}
                        >
                          <span className="font-mono">[{w.code}]</span> {w.description}{' '}
                          <span className="opacity-60">(затронуто: {w.count})</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            ))}

            <div className="mt-6 flex items-center justify-end gap-3">
              <button
                onClick={() => router.push('/')}
                className="px-6 py-2 bg-blue-500 hover:bg-blue-600 text-white rounded-md transition-colors inline-flex items-center gap-2"
              >
                Перейти в журнал <ArrowRight size={16} />
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
