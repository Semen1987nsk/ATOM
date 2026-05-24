'use client';

/**
 * PR 26 (Phase 3, D7) — Admin reconciliation drill-down.
 * URL: /admin/reconciliation/{run_id}
 *
 * Показывает все 8 метрик в side-by-side, breaks отдельно с severity,
 * + transformation_warnings (T1-T8).
 */

import { useEffect, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { ChevronLeft, CheckCircle, AlertTriangle, XCircle, AlertOctagon, Info } from 'lucide-react';
import { api } from '@/lib/apiClient';

type Severity = 'hard' | 'soft';

type Break = {
  id: number;
  metric: string;
  our_value: string | null;
  broker_value: string | null;
  diff_abs: string | null;
  diff_pct: string | null;
  severity: Severity;
  note: string | null;
  resolved_at: string | null;
  resolved_by_user_id: number | null;
  resolution_note: string | null;
};

type MetricEntry = {
  metric: string;
  ours: string;
  broker: string;
  diff_abs: string;
  diff_pct: string;
  status: 'ok' | 'soft' | 'hard';
  note: string;
};

type TransformationWarning = {
  code: string;
  severity: 'critical' | 'high' | 'medium' | 'low';
  description: string;
  count: number;
  details?: Record<string, unknown>;
};

type RunDetail = {
  id: number;
  user_id: number;
  account_id: number;
  period_start: string;
  period_end: string;
  started_at: string;
  finished_at: string | null;
  status: 'ok' | 'warning' | 'break' | 'error';
  breaks_count: number;
  mode: string;
  trigger: string;
  error_message: string | null;
  metrics: Record<string, MetricEntry>;
  breaks: Break[];
  broker_report_loaded?: boolean;
  transformation_warnings?: TransformationWarning[];
};

const METRIC_LABELS: Record<string, string> = {
  realized_pnl: 'Финансовый результат',
  broker_commission_total: 'Комиссия брокера',
  exchange_commission_total: 'Комиссия биржи',
  clearing_commission_total: 'Клиринговая комиссия',
  dividends_gross: 'Дивиденды (gross)',
  ndfl_withheld: 'НДФЛ удержан',
  net_cash_flow: 'Net cash flow',
  end_cash_balance: 'Cash balance',
};

function StatusIcon({ status }: { status: string }) {
  if (status === 'ok') return <CheckCircle size={16} className="text-green-400" />;
  if (status === 'soft' || status === 'warning')
    return <AlertTriangle size={16} className="text-orange-400" />;
  return <XCircle size={16} className="text-red-400" />;
}

function StatusBadge({ status }: { status: string }) {
  const map: Record<string, { label: string; cls: string }> = {
    ok: { label: 'OK', cls: 'bg-green-500/15 text-green-300 border border-green-500/30' },
    soft: { label: 'SOFT', cls: 'bg-orange-500/15 text-orange-300 border border-orange-500/30' },
    hard: { label: 'HARD', cls: 'bg-red-500/15 text-red-300 border border-red-500/30' },
    warning: { label: 'WARN', cls: 'bg-orange-500/15 text-orange-300 border border-orange-500/30' },
  };
  const s = map[status] || { label: status.toUpperCase(), cls: 'bg-slate-500/15 text-slate-300' };
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-semibold ${s.cls}`}>
      <StatusIcon status={status} />
      {s.label}
    </span>
  );
}

function fmtMoney(v: string | number | null | undefined): string {
  if (v === null || v === undefined || v === '') return '—';
  const n = typeof v === 'string' ? parseFloat(v) : v;
  if (!isFinite(n)) return '—';
  if (n === 0) return '0';
  return n.toLocaleString('ru-RU', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

function fmtPct(v: string | number | null | undefined): string {
  if (v === null || v === undefined || v === '') return '—';
  const n = typeof v === 'string' ? parseFloat(v) : v;
  if (!isFinite(n)) return '—';
  if (n === 0) return '0%';
  if (n > 10000) return '>10000%';
  if (n < 0.01 && n > 0) return '<0.01%';
  return n.toLocaleString('ru-RU', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }) + '%';
}

export default function AdminReconciliationDetailPage() {
  const params = useParams();
  const router = useRouter();
  const runId = parseInt(params.id as string);

  const [run, setRun] = useState<RunDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    api
      .get<RunDetail>(`/admin/reconciliation/${runId}`)
      .then(setRun)
      .catch((e) => setErr((e as Error).message))
      .finally(() => setLoading(false));
  }, [runId]);

  if (loading) return <div className="p-8 text-slate-400">Загрузка...</div>;
  if (err) return <div className="p-8 text-red-400">{err}</div>;
  if (!run) return <div className="p-8 text-slate-400">Не найден</div>;

  const metricsList = Object.values(run.metrics);

  return (
    <div className="p-6 max-w-5xl mx-auto">
      <button
        onClick={() => router.back()}
        className="flex items-center gap-1 text-sm text-slate-400 hover:text-slate-200 mb-4"
      >
        <ChevronLeft size={16} /> Назад
      </button>

      <div className="rounded-xl border border-slate-700/50 bg-slate-800/30 p-5 mb-6">
        <div className="flex items-start justify-between mb-3">
          <div>
            <h1 className="text-xl font-semibold">Reconciliation Run #{run.id}</h1>
            <div className="text-sm text-slate-400">
              User {run.user_id} · Account #{run.account_id} · {run.trigger}
            </div>
          </div>
          <div className="flex items-center gap-2">
            <StatusIcon status={run.status} />
            <span className="text-sm uppercase">{run.status}</span>
          </div>
        </div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs">
          <div>
            <div className="text-slate-500">Период</div>
            <div>
              {new Date(run.period_start).toLocaleDateString('ru-RU')} —{' '}
              {new Date(run.period_end).toLocaleDateString('ru-RU')}
            </div>
          </div>
          <div>
            <div className="text-slate-500">Запущен</div>
            <div>{new Date(run.started_at).toLocaleString('ru-RU')}</div>
          </div>
          <div>
            <div className="text-slate-500">Breaks</div>
            <div className="font-mono">{run.breaks_count}</div>
          </div>
          <div>
            <div className="text-slate-500">Mode</div>
            <div>{run.mode}</div>
          </div>
        </div>
        {run.error_message && (
          <div className="mt-3 p-3 rounded bg-red-500/10 border border-red-500/30 text-red-300 text-xs">
            {run.error_message}
          </div>
        )}
      </div>

      {/* PR 26 Phase 3 — TRANSFORMATION WARNINGS блок ВЫШЕ метрик,
          потому что это реальные баги в данных, а не ложные cross-check breaks */}
      {run.transformation_warnings && run.transformation_warnings.length > 0 && (
        <div className="rounded-xl border border-red-700/50 bg-red-900/10 p-5 mb-6">
          <div className="flex items-start gap-2 mb-3">
            <AlertOctagon size={20} className="text-red-400 mt-0.5" />
            <div>
              <h2 className="text-lg font-semibold text-red-200">
                Реальные проблемы в данных ({run.transformation_warnings.length})
              </h2>
              <p className="text-xs text-slate-400 mt-1">
                Найдено локальным аудитом (T1–T8). Не зависит от broker report —
                это то, что можно починить прямо сейчас.
              </p>
            </div>
          </div>
          <ul className="space-y-3">
            {run.transformation_warnings.map((w) => (
              <li
                key={w.code}
                className={`p-3 rounded-lg ${
                  w.severity === 'critical'
                    ? 'bg-red-500/10 border border-red-500/30'
                    : w.severity === 'high'
                      ? 'bg-orange-500/10 border border-orange-500/30'
                      : 'bg-yellow-500/10 border border-yellow-500/30'
                }`}
              >
                <div className="flex items-center gap-2 mb-1">
                  <span
                    className={`px-2 py-0.5 rounded text-[11px] font-mono ${
                      w.severity === 'critical'
                        ? 'bg-red-500/30 text-red-200'
                        : w.severity === 'high'
                          ? 'bg-orange-500/30 text-orange-200'
                          : 'bg-yellow-500/30 text-yellow-200'
                    }`}
                  >
                    [{w.code}]
                  </span>
                  <span className="text-xs uppercase text-slate-400">
                    {w.severity}
                  </span>
                  <span className="ml-auto text-xs text-slate-400">
                    затронуто записей: <span className="font-mono text-white">{w.count}</span>
                  </span>
                </div>
                <div className="text-sm text-slate-200">{w.description}</div>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Если broker_report не загрузился — предупреждение что метрики некорректны */}
      {run.broker_report_loaded === false && run.breaks.length > 0 && (
        <div className="rounded-xl border border-yellow-700/50 bg-yellow-900/10 p-4 mb-6 flex items-start gap-2">
          <Info size={18} className="text-yellow-400 mt-0.5 shrink-0" />
          <div className="text-sm">
            <div className="font-semibold text-yellow-200 mb-1">
              Broker report не загрузился
            </div>
            <div className="text-xs text-slate-300">
              Все значения «Tinkoff = 0» в таблице ниже — это <strong>не реальные расхождения</strong>,
              а технический сбой загрузки отчёта (вероятнее всего проблема с расшифровкой токена).
              Cross-check breaks следует игнорировать. Реальные находки выше — в блоке
              «Реальные проблемы в данных».
            </div>
          </div>
        </div>
      )}

      <div className="rounded-xl border border-slate-700/50 bg-slate-800/30 p-5 mb-6">
        <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
          <h2 className="text-lg font-semibold">Метрики (8)</h2>
          <div className="flex items-center gap-3 text-[11px] text-slate-400">
            <StatusBadge status="ok" />
            <span>совпало</span>
            <StatusBadge status="soft" />
            <span>методология (ожидаемо)</span>
            <StatusBadge status="hard" />
            <span>требует разбора</span>
          </div>
        </div>

        <div className="text-[11px] text-slate-500 mb-3 leading-relaxed">
          <strong className="text-slate-400">Эмпирик</strong> — сумма по нашей БД (что показывает дашборд).
          <span className="mx-1">·</span>
          <strong className="text-slate-400">Tinkoff</strong> — то же из broker_report API.
          <span className="mx-1">·</span>
          <strong className="text-slate-400">Δ abs</strong> — модуль разницы в ₽.
          <span className="mx-1">·</span>
          <strong className="text-slate-400">Δ %</strong> — относительная разница.
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-sm border-collapse">
            <thead>
              <tr className="text-[10px] text-slate-500 uppercase tracking-wider border-b border-slate-700/50">
                <th className="text-left pb-2 pr-3 font-medium" style={{ width: '35%' }}>Метрика</th>
                <th className="text-right pb-2 px-3 font-medium" style={{ width: '15%' }}>Эмпирик</th>
                <th className="text-right pb-2 px-3 font-medium" style={{ width: '15%' }}>Tinkoff</th>
                <th className="text-right pb-2 px-3 font-medium" style={{ width: '12%' }}>Δ abs ₽</th>
                <th className="text-right pb-2 px-3 font-medium" style={{ width: '10%' }}>Δ %</th>
                <th className="text-center pb-2 pl-3 font-medium" style={{ width: '13%' }}>Статус</th>
              </tr>
            </thead>
            <tbody>
              {metricsList.map((m) => (
                <tr key={m.metric} className="border-b border-slate-800/60 hover:bg-slate-800/20">
                  <td className="py-3 pr-3 text-slate-200 align-top">
                    <div className="font-medium">{METRIC_LABELS[m.metric] || m.metric}</div>
                    {m.note && (
                      <div className="text-[11px] text-slate-500 mt-1 leading-snug">{m.note}</div>
                    )}
                  </td>
                  <td className="py-3 px-3 text-right font-mono tabular-nums text-slate-100 align-top whitespace-nowrap">
                    {fmtMoney(m.ours)}
                  </td>
                  <td className="py-3 px-3 text-right font-mono tabular-nums text-slate-100 align-top whitespace-nowrap">
                    {fmtMoney(m.broker)}
                  </td>
                  <td className="py-3 px-3 text-right font-mono tabular-nums text-slate-400 align-top whitespace-nowrap">
                    {fmtMoney(m.diff_abs)}
                  </td>
                  <td className="py-3 px-3 text-right font-mono tabular-nums text-slate-400 align-top whitespace-nowrap">
                    {fmtPct(m.diff_pct)}
                  </td>
                  <td className="py-3 pl-3 text-center align-top whitespace-nowrap">
                    <StatusBadge status={m.status} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {run.breaks.length > 0 && (
        <div className="rounded-xl border border-orange-700/50 bg-orange-900/10 p-5 mb-6">
          <h2 className="text-lg font-semibold mb-3 text-orange-200">
            Breaks ({run.breaks.length})
          </h2>
          <ul className="space-y-3 text-sm">
            {run.breaks.map((b) => (
              <li key={b.id} className="p-4 rounded-lg bg-slate-800/40 border border-slate-700/30">
                <div className="flex items-center gap-2 mb-3 flex-wrap">
                  <span
                    className={`px-2 py-0.5 rounded text-[11px] font-semibold uppercase ${
                      b.severity === 'hard'
                        ? 'bg-red-500/20 text-red-300 border border-red-500/30'
                        : 'bg-orange-500/20 text-orange-300 border border-orange-500/30'
                    }`}
                  >
                    {b.severity}
                  </span>
                  <span className="font-mono text-slate-300">
                    {METRIC_LABELS[b.metric] || b.metric}
                  </span>
                </div>
                <div className="grid grid-cols-3 gap-3 text-xs">
                  <div className="bg-slate-900/40 rounded px-3 py-2">
                    <div className="text-slate-500 text-[10px] uppercase">Эмпирик</div>
                    <div className="font-mono tabular-nums text-slate-100 mt-0.5">
                      {fmtMoney(b.our_value)}
                    </div>
                  </div>
                  <div className="bg-slate-900/40 rounded px-3 py-2">
                    <div className="text-slate-500 text-[10px] uppercase">Tinkoff</div>
                    <div className="font-mono tabular-nums text-slate-100 mt-0.5">
                      {fmtMoney(b.broker_value)}
                    </div>
                  </div>
                  <div className="bg-slate-900/40 rounded px-3 py-2">
                    <div className="text-slate-500 text-[10px] uppercase">Δ abs</div>
                    <div className="font-mono tabular-nums text-orange-300 mt-0.5">
                      {fmtMoney(b.diff_abs)}
                    </div>
                  </div>
                </div>
                {b.note && (
                  <div className="text-xs text-slate-400 mt-3 leading-relaxed">{b.note}</div>
                )}
                {b.resolved_at && (
                  <div className="text-xs text-green-400 mt-2">
                    Resolved by user {b.resolved_by_user_id}: {b.resolution_note}
                  </div>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
