'use client';

/**
 * Admin → User 360 detail page (PR 26 Phase 2).
 *
 * Композиция:
 * - Snapshot (A1) — профиль, подписка, аккаунты
 * - Verify button (A4) — запуск 12 проверок
 * - Sync timeline (A3) — последние 7 дней sync events
 * - Access log (A20) — последние HTTP requests
 * - Force resync (A13) и Reset broker (A14) — destructive buttons
 */

import { useState, useEffect } from 'react';
import { useParams, useRouter } from 'next/navigation';
import {
  ChevronLeft, RefreshCw, Shield, AlertTriangle, CheckCircle,
  Activity, Database, Settings as Cog, Scale, Play,
} from 'lucide-react';
import { api } from '@/lib/apiClient';

interface AccountSummary {
  id: number;
  name: string;
  currency: string;
  initial_balance: number;
  last_portfolio_value: number | null;
  last_portfolio_at: string | null;
  broker_account_id: string | null;
  last_sync_at: string | null;
  consecutive_failures: number;
  trades_count: number;
  net_pnl_total: number;
  open_positions: number;
  last_health_status: string | null;
  last_health_at: string | null;
}

interface Snapshot {
  user: {
    id: number;
    email: string;
    name: string | null;
    is_admin: boolean;
    is_active: boolean;
    created_at: string | null;
    last_login_at: string | null;
    registration_source: string | null;
  };
  subscription: {
    plan: string;
    expires_at: string | null;
    auto_renew: boolean;
  } | null;
  accounts: AccountSummary[];
}

interface VerifyCheck {
  id: string;
  status: 'ok' | 'warning' | 'error';
  message: string;
}

interface VerifyAccount {
  account_id: number;
  status: string;
  checks: VerifyCheck[];
}

interface VerifyReport {
  accounts: VerifyAccount[];
  summary: { ok: number; warning: number; error: number };
}

interface TimelineEvent {
  id: number;
  account_id: number;
  started_at: string;
  finished_at: string | null;
  duration_ms: number | null;
  status: string;
  operations_new_or_updated: number;
  trades_built: number;
  error_type: string | null;
  error_message: string | null;
}

// PR 26 Phase 3
interface ReconciliationRunRow {
  id: number;
  account_id: number;
  period_start: string | null;
  period_end: string | null;
  started_at: string | null;
  finished_at: string | null;
  status: 'ok' | 'warning' | 'break' | 'error';
  breaks_count: number;
  mode: string;
  trigger: string;
  error_message: string | null;
}

function formatBalance(amount: number | null, currency: string = 'RUB'): string {
  if (amount === null || amount === undefined) return '—';
  return amount.toLocaleString('ru-RU', { maximumFractionDigits: 0 }) + ' ' + (currency === 'RUB' ? '₽' : currency);
}

function StatusBadge({ status }: { status: string | null }) {
  if (!status) return <span className="text-slate-500 text-xs">—</span>;
  const colors: Record<string, string> = {
    ok: 'bg-green-500/15 text-green-400',
    warning: 'bg-yellow-500/15 text-yellow-400',
    error: 'bg-red-500/15 text-red-400',
    success: 'bg-green-500/15 text-green-400',
    failed: 'bg-red-500/15 text-red-400',
    interrupted: 'bg-orange-500/15 text-orange-400',
    running: 'bg-blue-500/15 text-blue-400',
  };
  return (
    <span className={`px-2 py-0.5 rounded text-[11px] font-medium ${colors[status] || 'bg-slate-500/15 text-slate-400'}`}>
      {status}
    </span>
  );
}

export default function UserDetailPage() {
  const params = useParams();
  const router = useRouter();
  const userId = parseInt(params.id as string);

  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [verifyResult, setVerifyResult] = useState<VerifyReport | null>(null);
  const [timeline, setTimeline] = useState<TimelineEvent[]>([]);
  const [reconciliationRuns, setReconciliationRuns] = useState<ReconciliationRunRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [verifying, setVerifying] = useState(false);
  const [reconciling, setReconciling] = useState(false);
  const [reconcilePeriod, setReconcilePeriod] = useState<number>(30);
  const [reconcileAccountId, setReconcileAccountId] = useState<number | 'all'>('all');
  const [errMsg, setErrMsg] = useState<string | null>(null);

  const loadReconciliation = async () => {
    try {
      const r = await api.get<{ runs: ReconciliationRunRow[] }>(
        `/admin/users/${userId}/reconciliation?limit=20`,
      );
      setReconciliationRuns(r.runs || []);
    } catch {
      // optional — silent fail если нет runs
    }
  };

  useEffect(() => {
    let cancelled = false;
    Promise.all([
      api.get<Snapshot>(`/admin/users/${userId}/snapshot`),
      api.get<{ events: TimelineEvent[] }>(`/admin/users/${userId}/sync-timeline?days=7`),
    ])
      .then(([snap, tl]) => {
        if (cancelled) return;
        setSnapshot(snap);
        setTimeline(tl.events || []);
      })
      .catch((e) => {
        if (!cancelled) setErrMsg(e.message || 'Не удалось загрузить');
      })
      .finally(() => !cancelled && setLoading(false));
    loadReconciliation();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [userId]);

  const runReconciliation = async () => {
    const periodLabel = reconcilePeriod >= 365 ? 'за весь период (365 дней)' : `за последние ${reconcilePeriod} дней`;
    const accLabel = reconcileAccountId === 'all' ? 'все счета' : `счёт #${reconcileAccountId}`;
    if (!confirm(`Запустить 3-way reconciliation ${periodLabel} (${accLabel})? Это сделает запрос к broker report Tinkoff (10-90 сек).`)) return;
    setReconciling(true);
    setErrMsg(null);
    try {
      const params = new URLSearchParams({ days: String(reconcilePeriod) });
      if (reconcileAccountId !== 'all') {
        params.set('account_id', String(reconcileAccountId));
      }
      await api.post(`/admin/users/${userId}/reconciliation/run?${params.toString()}`, {});
      await loadReconciliation();
    } catch (e) {
      setErrMsg((e as Error).message);
    } finally {
      setReconciling(false);
    }
  };

  const runVerify = async (skipLive: boolean) => {
    setVerifying(true);
    setErrMsg(null);
    try {
      const r = await api.get<VerifyReport>(
        `/admin/users/${userId}/verify?skip_live=${skipLive}`
      );
      setVerifyResult(r);
    } catch (e) {
      setErrMsg((e as Error).message);
    } finally {
      setVerifying(false);
    }
  };

  const forceResync = async (accountId: number) => {
    if (!confirm('Запустить sync минуя circuit breaker?')) return;
    try {
      await api.post(`/admin/users/${userId}/force-resync`, {});
      alert('Sync запущен');
    } catch (e) {
      alert('Ошибка: ' + (e as Error).message);
    }
  };

  const resetBroker = async (accountId: number) => {
    const input = prompt(`Введите ${accountId} для подтверждения СБРОСА всех данных аккаунта ${accountId}:`);
    if (input !== String(accountId)) return;
    try {
      await api.post(`/admin/users/${userId}/reset-broker?account_id=${accountId}&confirm=${accountId}`, {});
      alert('Broker сброшен');
      window.location.reload();
    } catch (e) {
      alert('Ошибка: ' + (e as Error).message);
    }
  };

  if (loading) {
    return <div className="p-8 text-slate-400">Загрузка...</div>;
  }
  if (errMsg && !snapshot) {
    return <div className="p-8 text-red-400">{errMsg}</div>;
  }
  if (!snapshot) {
    return <div className="p-8 text-slate-400">Не найден</div>;
  }

  const u = snapshot.user;

  return (
    <div className="p-6 max-w-7xl mx-auto">
      <button
        onClick={() => router.back()}
        className="flex items-center gap-1 text-sm text-slate-400 hover:text-slate-200 mb-4"
      >
        <ChevronLeft size={16} /> Назад
      </button>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 mb-6">
        {/* Profile */}
        <div className="rounded-xl border border-slate-700/50 bg-slate-800/30 p-5">
          <div className="text-xs text-slate-500 uppercase tracking-wider mb-2">Профиль</div>
          <div className="text-lg font-semibold mb-1">{u.email}</div>
          <div className="text-sm text-slate-400 mb-3">{u.name || '—'}</div>
          <div className="space-y-1 text-xs">
            <div className="flex gap-2"><span className="text-slate-500 w-24">ID:</span><span>{u.id}</span></div>
            <div className="flex gap-2"><span className="text-slate-500 w-24">Источник:</span><span>{u.registration_source || '—'}</span></div>
            <div className="flex gap-2"><span className="text-slate-500 w-24">Регистрация:</span><span>{u.created_at ? new Date(u.created_at).toLocaleString('ru-RU') : '—'}</span></div>
            <div className="flex gap-2"><span className="text-slate-500 w-24">Last login:</span><span>{u.last_login_at ? new Date(u.last_login_at).toLocaleString('ru-RU') : '—'}</span></div>
            <div className="flex gap-2 mt-2">
              {u.is_admin && <span className="px-2 py-0.5 bg-purple-500/15 text-purple-400 rounded text-[11px]">admin</span>}
              {u.is_active ? <span className="px-2 py-0.5 bg-green-500/15 text-green-400 rounded text-[11px]">active</span> : <span className="px-2 py-0.5 bg-red-500/15 text-red-400 rounded text-[11px]">inactive</span>}
            </div>
          </div>
        </div>

        {/* Subscription */}
        <div className="rounded-xl border border-slate-700/50 bg-slate-800/30 p-5">
          <div className="text-xs text-slate-500 uppercase tracking-wider mb-2">Подписка</div>
          <div className="text-2xl font-bold mb-1">
            {snapshot.subscription?.plan?.toUpperCase() || 'FREE'}
          </div>
          {snapshot.subscription?.expires_at && (
            <div className="text-xs text-slate-400">
              до {new Date(snapshot.subscription.expires_at).toLocaleDateString('ru-RU')}
            </div>
          )}
        </div>

        {/* Actions */}
        <div className="rounded-xl border border-slate-700/50 bg-slate-800/30 p-5">
          <div className="text-xs text-slate-500 uppercase tracking-wider mb-3">Действия</div>
          <div className="space-y-2">
            <button
              onClick={() => runVerify(true)}
              disabled={verifying}
              className="w-full px-3 py-2 bg-blue-500/15 hover:bg-blue-500/25 text-blue-300 rounded text-sm flex items-center gap-2 disabled:opacity-50"
            >
              <Shield size={14} />
              {verifying ? 'Запуск...' : 'Verify (DB-only)'}
            </button>
            <button
              onClick={() => runVerify(false)}
              disabled={verifying}
              className="w-full px-3 py-2 bg-purple-500/15 hover:bg-purple-500/25 text-purple-300 rounded text-sm flex items-center gap-2 disabled:opacity-50"
            >
              <Activity size={14} />
              Verify + Live API
            </button>
            <button
              onClick={runReconciliation}
              disabled={reconciling}
              className="w-full px-3 py-2 bg-orange-500/15 hover:bg-orange-500/25 text-orange-300 rounded text-sm flex items-center gap-2 disabled:opacity-50"
            >
              <Scale size={14} />
              {reconciling ? 'Reconciling...' : `Run reconciliation (${reconcilePeriod}d)`}
            </button>
          </div>
        </div>
      </div>

      {/* Verify result */}
      {verifyResult && (
        <div className="rounded-xl border border-slate-700/50 bg-slate-800/30 p-5 mb-6">
          <div className="flex items-center justify-between mb-3">
            <div className="font-semibold">Verify result</div>
            <div className="flex gap-3 text-xs">
              <span className="text-green-400">ok: {verifyResult.summary.ok}</span>
              <span className="text-yellow-400">warn: {verifyResult.summary.warning}</span>
              <span className="text-red-400">err: {verifyResult.summary.error}</span>
            </div>
          </div>
          {verifyResult.accounts.map(a => (
            <div key={a.account_id} className="mb-3">
              <div className="text-sm font-medium mb-1 flex gap-2 items-center">
                Account #{a.account_id} <StatusBadge status={a.status} />
              </div>
              <div className="text-xs space-y-1 ml-3">
                {a.checks.map((c) => (
                  <div key={c.id} className="flex gap-2 items-start">
                    <StatusBadge status={c.status} />
                    <span className="text-slate-300">{c.id}</span>
                    {c.message && <span className="text-slate-500">— {c.message}</span>}
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Accounts */}
      <div className="mb-6">
        <h2 className="text-lg font-semibold mb-3">Счета ({snapshot.accounts.length})</h2>
        <div className="space-y-3">
          {snapshot.accounts.map(a => (
            <div key={a.id} className="rounded-xl border border-slate-700/50 bg-slate-800/30 p-4">
              <div className="flex items-start justify-between mb-3 flex-wrap gap-2">
                <div>
                  <div className="font-medium">{a.name} <span className="text-slate-500 text-sm">#{a.id}</span></div>
                  <div className="text-xs text-slate-400">{a.broker_account_id ? `Tinkoff brk${a.broker_account_id}` : 'Без брокера'}</div>
                </div>
                <div className="flex gap-2">
                  {a.broker_account_id && (
                    <>
                      <button onClick={() => forceResync(a.id)} className="px-2 py-1 bg-blue-500/15 hover:bg-blue-500/25 text-blue-300 text-xs rounded">
                        Force sync
                      </button>
                      <button onClick={() => resetBroker(a.id)} className="px-2 py-1 bg-red-500/15 hover:bg-red-500/25 text-red-300 text-xs rounded">
                        Reset
                      </button>
                    </>
                  )}
                </div>
              </div>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs">
                <div><div className="text-slate-500">Баланс (cash)</div><div className="font-mono">{formatBalance(a.last_portfolio_value, a.currency)}</div></div>
                <div><div className="text-slate-500">Trades</div><div className="font-mono">{a.trades_count}</div></div>
                <div><div className="text-slate-500">Net PnL</div><div className={`font-mono ${a.net_pnl_total >= 0 ? 'text-green-400' : 'text-red-400'}`}>{formatBalance(a.net_pnl_total, a.currency)}</div></div>
                <div><div className="text-slate-500">Открыто позиций</div><div className="font-mono">{a.open_positions}</div></div>
                <div><div className="text-slate-500">Last sync</div><div className="text-xs">{a.last_sync_at ? new Date(a.last_sync_at).toLocaleString('ru-RU') : '—'}</div></div>
                <div><div className="text-slate-500">Health</div><div><StatusBadge status={a.last_health_status} /></div></div>
                <div><div className="text-slate-500">Fails</div><div className={`font-mono ${a.consecutive_failures > 0 ? 'text-orange-400' : ''}`}>{a.consecutive_failures}</div></div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* PR 26 Phase 3: Reconciliation */}
      <div className="rounded-xl border border-slate-700/50 bg-slate-800/30 p-5 mb-6">
        <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
          <h2 className="text-lg font-semibold">Reconciliation (3-way verification)</h2>
          <div className="flex items-center gap-2 flex-wrap">
            <label className="text-xs text-slate-400">Счёт:</label>
            <select
              value={reconcileAccountId === 'all' ? 'all' : String(reconcileAccountId)}
              onChange={(e) =>
                setReconcileAccountId(e.target.value === 'all' ? 'all' : parseInt(e.target.value))
              }
              disabled={reconciling}
              className="bg-slate-900/60 border border-slate-700/50 rounded text-xs px-2 py-1 text-slate-200 disabled:opacity-50"
            >
              <option value="all">Все счета</option>
              {snapshot.accounts
                .filter((a) => a.broker_account_id)
                .map((a) => (
                  <option key={a.id} value={a.id}>
                    #{a.id} · {a.name}
                  </option>
                ))}
            </select>
            <label className="text-xs text-slate-400 ml-2">Период:</label>
            <select
              value={reconcilePeriod}
              onChange={(e) => setReconcilePeriod(parseInt(e.target.value))}
              disabled={reconciling}
              className="bg-slate-900/60 border border-slate-700/50 rounded text-xs px-2 py-1 text-slate-200 disabled:opacity-50"
            >
              <option value={7}>7 дней</option>
              <option value={14}>14 дней</option>
              <option value={30}>30 дней</option>
              <option value={31}>31 день (максимум T-Bank API)</option>
            </select>
            <button
              onClick={runReconciliation}
              disabled={reconciling}
              className="px-3 py-1 bg-orange-500/15 hover:bg-orange-500/25 text-orange-300 rounded text-xs flex items-center gap-1 disabled:opacity-50"
            >
              <Play size={12} />
              {reconciling ? 'Запуск...' : 'Запустить'}
            </button>
          </div>
        </div>
        <div className="text-[11px] text-slate-500 mb-3">
          T-Bank API ограничивает broker_report 31 днём (ERR-113). Для full-period
          валидации нужна chunked-reconciliation — backend задача, см. RUNBOOK.
        </div>
        {reconciliationRuns.length === 0 ? (
          <div className="text-sm text-slate-500">
            Нет runs. Кнопка запуска — сверяет наши агрегаты с broker report Tinkoff.
          </div>
        ) : (
          <div className="space-y-1 text-xs">
            {reconciliationRuns.map((r) => (
              <a
                key={r.id}
                href={`/admin/reconciliation/${r.id}`}
                className="flex gap-3 items-center py-1 border-b border-slate-700/30 hover:bg-slate-700/20 px-2 rounded"
              >
                <span className="text-slate-500 w-32 shrink-0">
                  {r.started_at ? new Date(r.started_at).toLocaleString('ru-RU') : '—'}
                </span>
                <StatusBadge status={r.status} />
                <span className="text-slate-400">acc #{r.account_id}</span>
                {r.breaks_count > 0 && (
                  <span className="text-orange-400">{r.breaks_count} breaks</span>
                )}
                <span className="text-slate-500 ml-auto">{r.trigger}</span>
              </a>
            ))}
          </div>
        )}
      </div>

      {/* Timeline */}
      <div className="rounded-xl border border-slate-700/50 bg-slate-800/30 p-5">
        <h2 className="text-lg font-semibold mb-3">Sync timeline (7 дней)</h2>
        {timeline.length === 0 ? (
          <div className="text-sm text-slate-500">Нет событий за последние 7 дней</div>
        ) : (
          <div className="space-y-1 text-xs">
            {timeline.slice(0, 30).map(e => (
              <div key={e.id} className="flex gap-3 items-center py-1 border-b border-slate-700/30">
                <span className="text-slate-500 w-32 shrink-0">{new Date(e.started_at).toLocaleString('ru-RU')}</span>
                <StatusBadge status={e.status} />
                <span className="text-slate-400">acc #{e.account_id}</span>
                <span className="text-slate-500">{e.duration_ms ? `${e.duration_ms}ms` : ''}</span>
                {e.operations_new_or_updated > 0 && <span className="text-slate-400">+{e.operations_new_or_updated} ops</span>}
                {e.error_message && <span className="text-red-400 truncate">{e.error_message}</span>}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
