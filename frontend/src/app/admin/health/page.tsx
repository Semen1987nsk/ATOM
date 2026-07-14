'use client';

/**
 * Admin: «Здоровье синхронизации» (PR 20)
 *
 * Таблица всех аккаунтов с их последним sync_health_check.
 * Sort: error → warning → ok. Фильтр по статусу. Клик на строку →
 * модалка с полной историей (последние 30 дней) + детали issues.
 */

import { useCallback, useEffect, useState } from 'react';
import { RefreshCw, ShieldCheck, ShieldAlert, X, AlertCircle } from 'lucide-react';
import Link from 'next/link';
import { AppShell } from '@/components/AppShell';
import { api } from '@/lib/apiClient';
import { useAuth } from '@/contexts/AuthContext';

interface HealthIssue {
  check_id: string;
  severity: 'warning' | 'error';
  count: number;
  description: string;
  sample_ids?: number[];
}

interface AccountHealth {
  account_id: number;
  user_email_hash: string;
  user_email: string;
  broker_account_id: string;
  checked_at: string | null;
  status: 'ok' | 'warning' | 'error';
  total_trades_checked: number;
  trades_with_issues: number;
  main_issue: string | null;
  issues_count: number;
  last_sync_at: string | null;
  circuit_open_until: string | null;
}

interface SyncHealthOverview {
  accounts: AccountHealth[];
  summary: { ok: number; warning: number; error: number; total_with_checks: number };
}

interface HealthHistoryEntry {
  id: number;
  checked_at: string;
  sync_id: string | null;
  status: 'ok' | 'warning' | 'error';
  total_trades_checked: number;
  trades_with_issues: number;
  issues: HealthIssue[];
}

const STATUS_BADGE: Record<string, { label: string; cls: string; icon: string }> = {
  ok: { label: 'OK', cls: 'bg-green-500/15 text-green-400 border-green-500/30', icon: '🟢' },
  warning: { label: 'Warning', cls: 'bg-yellow-500/15 text-yellow-300 border-yellow-500/30', icon: '🟡' },
  error: { label: 'Error', cls: 'bg-red-500/15 text-red-400 border-red-500/30', icon: '🔴' },
};

export default function AdminHealthPage() {
  const { user, isLoading: authLoading } = useAuth();
  const [data, setData] = useState<SyncHealthOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState<string>('ALL');
  const [drillAccount, setDrillAccount] = useState<AccountHealth | null>(null);
  const [drillHistory, setDrillHistory] = useState<HealthHistoryEntry[] | null>(null);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const params = statusFilter === 'ALL' ? '' : `?status_filter=${statusFilter}`;
      const resp = await api.get<SyncHealthOverview>(`/admin/sync-health${params}`);
      setData(resp);
    } catch (err) {
      console.error('Failed to fetch admin health:', err);
    } finally {
      setLoading(false);
    }
  }, [statusFilter]);

  useEffect(() => {
    if (user?.is_admin) fetchData();
  }, [user, fetchData]);

  const openDrill = useCallback(async (acc: AccountHealth) => {
    setDrillAccount(acc);
    setDrillHistory(null);
    try {
      const resp = await api.get<{ history: HealthHistoryEntry[] }>(
        `/admin/sync-health/${acc.account_id}`,
      );
      setDrillHistory(resp.history);
    } catch (err) {
      console.error('Failed to fetch drill detail:', err);
      setDrillHistory([]);
    }
  }, []);

  if (authLoading) {
    return (
      <AppShell pageTitle="Здоровье импорта">
        <div className="p-6">Загрузка...</div>
      </AppShell>
    );
  }
  if (!user?.is_admin) {
    return (
      <AppShell pageTitle="Здоровье импорта">
        <div className="p-6">
          <div className="rounded-lg border border-red-500/30 bg-red-500/5 p-5 text-red-400">
            <AlertCircle className="inline mr-2" size={16} />
            Требуются права администратора.
          </div>
        </div>
      </AppShell>
    );
  }

  return (
    <AppShell pageTitle="Здоровье импорта">
      <div className="p-6 md:p-8 max-w-7xl mx-auto">
        <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
          <div>
            <h1 className="text-3xl font-bold tracking-tight mb-1">Здоровье синхронизации</h1>
            <p className="text-sm text-slate-400">
              Последний health-audit по каждому аккаунту. Sort: ошибки → предупреждения → OK.
            </p>
          </div>
          <button onClick={fetchData} disabled={loading} className="btn-secondary inline-flex items-center gap-2">
            <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
            Обновить
          </button>
        </div>

        {/* Summary cards */}
        {data && (
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-6">
            <SummaryCard label="Всего" value={data.summary.total_with_checks} color="text-slate-200" />
            <SummaryCard label="🟢 OK" value={data.summary.ok} color="text-green-400" onClick={() => setStatusFilter('ok')} />
            <SummaryCard label="🟡 Warning" value={data.summary.warning} color="text-yellow-300" onClick={() => setStatusFilter('warning')} />
            <SummaryCard label="🔴 Error" value={data.summary.error} color="text-red-400" onClick={() => setStatusFilter('error')} />
          </div>
        )}

        {/* Filter */}
        <div className="mb-4 flex items-center gap-2 text-xs">
          <span className="text-slate-500">Фильтр:</span>
          {(['ALL', 'error', 'warning', 'ok'] as const).map((s) => (
            <button
              key={s}
              onClick={() => setStatusFilter(s)}
              className={`px-3 py-1 rounded-lg border transition-colors ${
                statusFilter === s
                  ? 'bg-accent text-black border-accent font-bold'
                  : 'bg-transparent border-slate-700 text-slate-400 hover:text-white'
              }`}
            >
              {s === 'ALL' ? 'Все' : STATUS_BADGE[s]?.label || s}
            </button>
          ))}
        </div>

        {loading && (
          <div className="rounded-xl border border-slate-800 bg-slate-900/50 p-12 text-center">
            <RefreshCw className="mx-auto animate-spin text-slate-500" size={32} />
          </div>
        )}

        {!loading && data && data.accounts.length === 0 && (
          <div className="rounded-xl border border-slate-800 bg-slate-900/50 p-8 text-center text-slate-400">
            Нет аккаунтов с health-данными для выбранного фильтра.
          </div>
        )}

        {!loading && data && data.accounts.length > 0 && (
          <div className="rounded-xl border border-slate-800 bg-slate-900/50 overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-slate-900/80 text-slate-400 text-xs uppercase">
                <tr>
                  <th className="px-4 py-3 text-left">Статус</th>
                  <th className="px-4 py-3 text-left">Юзер</th>
                  <th className="px-4 py-3 text-left">Брокер-счёт</th>
                  <th className="px-4 py-3 text-left">Проверка</th>
                  <th className="px-4 py-3 text-right">Сделок</th>
                  <th className="px-4 py-3 text-right">С проблемами</th>
                  <th className="px-4 py-3 text-left">Главная проблема</th>
                </tr>
              </thead>
              <tbody>
                {data.accounts.map((a) => {
                  const badge = STATUS_BADGE[a.status] || STATUS_BADGE.ok;
                  return (
                    <tr
                      key={a.account_id}
                      onClick={() => openDrill(a)}
                      className="border-t border-slate-800 hover:bg-slate-800/40 cursor-pointer transition-colors"
                    >
                      <td className="px-4 py-3">
                        <span className={`text-[11px] font-mono uppercase px-2 py-0.5 rounded border ${badge.cls}`}>
                          {badge.icon} {badge.label}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-slate-300 font-mono text-xs">
                        {a.user_email}
                      </td>
                      <td className="px-4 py-3 text-slate-400 font-mono text-xs">{a.broker_account_id}</td>
                      <td className="px-4 py-3 text-slate-400 text-xs">
                        {a.checked_at ? new Date(a.checked_at).toLocaleString('ru-RU') : '—'}
                      </td>
                      <td className="px-4 py-3 text-right font-mono text-xs text-slate-300">
                        {a.total_trades_checked.toLocaleString('ru-RU')}
                      </td>
                      <td className={`px-4 py-3 text-right font-mono text-xs ${a.trades_with_issues > 0 ? 'text-yellow-300' : 'text-slate-500'}`}>
                        {a.trades_with_issues}
                      </td>
                      <td className="px-4 py-3 text-xs">
                        {a.main_issue ? (
                          <span className="font-mono text-slate-300">{a.main_issue}</span>
                        ) : (
                          <span className="text-slate-600">—</span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}

        {/* Drill-down modal */}
        {drillAccount && (
          <div
            className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4"
            onClick={() => setDrillAccount(null)}
          >
            <div
              className="bg-slate-900 border border-slate-700 rounded-xl max-w-4xl w-full max-h-[85vh] overflow-y-auto"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="flex items-center justify-between p-4 border-b border-slate-800 sticky top-0 bg-slate-900/95 backdrop-blur">
                <div>
                  <h2 className="font-bold text-white">
                    Account #{drillAccount.account_id} · {drillAccount.user_email}
                  </h2>
                  <p className="text-xs text-slate-400 mt-1 font-mono">
                    Брокер-счёт {drillAccount.broker_account_id}
                  </p>
                </div>
                <button
                  onClick={() => setDrillAccount(null)}
                  className="p-1 hover:bg-slate-800 rounded"
                >
                  <X size={18} />
                </button>
              </div>

              <div className="p-4 space-y-4">
                {drillHistory === null && (
                  <div className="text-center py-8">
                    <RefreshCw className="mx-auto animate-spin text-slate-500" size={24} />
                  </div>
                )}
                {drillHistory && drillHistory.length === 0 && (
                  <div className="text-center py-8 text-slate-400">
                    Нет health-проверок за последние 30 дней.
                  </div>
                )}
                {drillHistory && drillHistory.map((entry) => {
                  const badge = STATUS_BADGE[entry.status] || STATUS_BADGE.ok;
                  return (
                    <div key={entry.id} className="rounded-lg border border-slate-800 bg-slate-950/50 overflow-hidden">
                      <div className="flex items-center justify-between px-4 py-2 bg-slate-900/50 border-b border-slate-800">
                        <span className={`text-[11px] font-mono uppercase px-2 py-0.5 rounded border ${badge.cls}`}>
                          {badge.icon} {badge.label}
                        </span>
                        <span className="text-xs text-slate-500 font-mono">
                          {new Date(entry.checked_at).toLocaleString('ru-RU')}
                          {entry.sync_id && <span className="ml-2 opacity-60">· {entry.sync_id}</span>}
                        </span>
                      </div>
                      <div className="px-4 py-3 text-xs text-slate-400">
                        <span className="text-slate-300 font-mono">{entry.total_trades_checked}</span> сделок проверено,{' '}
                        <span className="text-slate-300 font-mono">{entry.trades_with_issues}</span> с проблемами
                      </div>
                      {entry.issues.length > 0 && (
                        <div className="px-4 pb-3 space-y-2">
                          {entry.issues.map((issue, idx) => (
                            <div key={idx} className="rounded border border-slate-800 bg-slate-950 p-2 text-xs">
                              <div className="flex items-start gap-2">
                                <span className={`shrink-0 inline-block w-2 h-2 rounded-full mt-1 ${
                                  issue.severity === 'error' ? 'bg-red-400' : 'bg-yellow-400'
                                }`} />
                                <div className="flex-1 min-w-0">
                                  <div className="font-mono text-slate-200">
                                    {issue.check_id} <span className="text-slate-500">×{issue.count}</span>
                                  </div>
                                  <div className="text-slate-400 mt-0.5">{issue.description}</div>
                                  {issue.sample_ids && issue.sample_ids.length > 0 && (
                                    <div className="text-slate-500 mt-1 font-mono">
                                      sample IDs: {issue.sample_ids.slice(0, 5).join(', ')}
                                    </div>
                                  )}
                                </div>
                              </div>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        )}

        <div className="mt-6 text-xs text-slate-500">
          <Link href="/admin" className="hover:text-slate-300">← Назад в админку</Link>
        </div>
      </div>
    </AppShell>
  );
}

function SummaryCard({
  label,
  value,
  color,
  onClick,
}: {
  label: string;
  value: number;
  color: string;
  onClick?: () => void;
}) {
  const Tag = onClick ? 'button' : 'div';
  return (
    <Tag
      onClick={onClick}
      className="rounded-xl border border-slate-800 bg-slate-900/50 p-4 text-left hover:bg-slate-800/50 transition-colors w-full"
    >
      <div className="text-[10px] text-slate-500 uppercase tracking-wider mb-1">{label}</div>
      <div className={`text-2xl font-bold font-mono ${color}`}>{value.toLocaleString('ru-RU')}</div>
    </Tag>
  );
}
