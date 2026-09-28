"use client";
/**
 * Phase 10 (2026-05-17): Admin "P&L Health" tab.
 *
 * Показывает таблицу всех accounts × их reconciliation status.
 * Источник: GET /admin/pnl-health (cached на Account.last_pnl_health_*).
 * Force refresh per-account через POST /admin/pnl-health/{id}/refresh.
 */
import { useState, useEffect, useCallback } from "react";
import { Shield, AlertTriangle, AlertCircle, Filter, RefreshCw } from "lucide-react";
import { api } from "@/lib/apiClient";

interface AccountHealthRow {
  account_id: number;
  account_name: string;
  user_id: number;
  user_email: string;
  status: "ok" | "warning" | "mismatch" | "na" | "stale";
  diff_pct: number | null;
  diff_rub: number | null;
  checked_at: string | null;
  currency: string;
  last_portfolio_value: number | null;
}

interface SummaryCounts {
  ok: number;
  warning: number;
  mismatch: number;
  na: number;
  stale: number;
}

interface HealthResponse {
  accounts: AccountHealthRow[];
  summary: SummaryCounts;
  skip: number;
  limit: number;
  total: number;
}

const STATUS_STYLES = {
  ok: { color: "text-emerald-400", bg: "bg-emerald-500/10", label: "OK" },
  warning: { color: "text-amber-400", bg: "bg-amber-500/10", label: "Warning" },
  mismatch: { color: "text-rose-400", bg: "bg-rose-500/10", label: "Mismatch" },
  na: { color: "text-slate-400", bg: "bg-slate-500/10", label: "N/A" },
  stale: { color: "text-slate-400", bg: "bg-slate-500/10", label: "Stale" },
} as const;

function formatCurrency(value: number | null, currency = "₽"): string {
  if (value === null) return "—";
  return `${value.toLocaleString("ru-RU", { maximumFractionDigits: 0 })} ${currency}`;
}

function formatPct(value: number | null): string {
  if (value === null) return "—";
  if (Math.abs(value) < 0.01) return "<0.01%";
  return `${value.toFixed(2)}%`;
}

function timeAgo(iso: string | null): string {
  if (!iso) return "никогда";
  const diffMs = Date.now() - new Date(iso).getTime();
  const minutes = Math.floor(diffMs / 60000);
  if (minutes < 1) return "только что";
  if (minutes < 60) return `${minutes} мин назад`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} ч назад`;
  return `${Math.floor(hours / 24)} дн назад`;
}

export function PnLHealthTab() {
  const [data, setData] = useState<HealthResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [refreshingId, setRefreshingId] = useState<number | null>(null);
  const [page, setPage] = useState(0);
  const limit = 50;

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({
        skip: String(page * limit),
        limit: String(limit),
        sort: "diff_pct_desc",
      });
      if (statusFilter !== "all") {
        params.set("status_filter", statusFilter);
      }
      const resp = await api.get<HealthResponse>(`/admin/pnl-health?${params}`);
      setData(resp);
    } catch (e) {
      console.error("Failed to load P&L health", e);
    } finally {
      setLoading(false);
    }
  }, [page, statusFilter]);

  useEffect(() => {
    void fetchData();
  }, [fetchData]);

  const handleRefreshAccount = async (accountId: number) => {
    setRefreshingId(accountId);
    try {
      await api.post(`/admin/pnl-health/${accountId}/refresh`, {});
      await fetchData();
    } catch (e) {
      console.error(`Failed to refresh account ${accountId}`, e);
    } finally {
      setRefreshingId(null);
    }
  };

  if (loading && !data) {
    return <div className="p-6 text-slate-400">Загрузка...</div>;
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold mb-2">P&L Health Check</h2>
        <p className="text-sm text-slate-400">
          Сверка двух методологий расчёта P&L: журнал сделок vs cash truth.
          ≤0.5% — OK, 0.5–2% — Warning, &gt;2% — Mismatch.
        </p>
      </div>

      {/* Summary cards */}
      {data?.summary && (
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
          {(["ok", "warning", "mismatch", "na", "stale"] as const).map((s) => {
            const style = STATUS_STYLES[s];
            const count = data.summary[s];
            return (
              <div
                key={s}
                className={`rounded-lg border border-white/10 ${style.bg} p-3 cursor-pointer hover:opacity-80`}
                onClick={() => {
                  setStatusFilter(s === statusFilter ? "all" : s);
                  setPage(0);
                }}
              >
                <div className={`text-2xl font-bold ${style.color}`}>{count}</div>
                <div className={`text-xs ${style.color} mt-1`}>{style.label}</div>
              </div>
            );
          })}
        </div>
      )}

      {/* Filter bar */}
      <div className="flex items-center gap-3 text-sm">
        <Filter size={14} className="text-slate-500" />
        <span className="text-slate-400">Фильтр:</span>
        <select
          value={statusFilter}
          onChange={(e) => {
            setStatusFilter(e.target.value);
            setPage(0);
          }}
          className="bg-secondary border border-white/10 rounded px-3 py-1.5"
        >
          <option value="all">Все статусы</option>
          <option value="mismatch">Только mismatch</option>
          <option value="warning">Только warning</option>
          <option value="ok">Только ok</option>
          <option value="stale">Только stale</option>
          <option value="na">Только n/a</option>
        </select>
        <button
          onClick={() => void fetchData()}
          disabled={loading}
          className="ml-auto px-3 py-1.5 bg-secondary border border-white/10 rounded hover:bg-white/5 disabled:opacity-40"
        >
          <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
        </button>
      </div>

      {/* Accounts table */}
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="text-[11px] uppercase tracking-wider text-slate-500 border-b border-white/10">
            <tr>
              <th className="text-left py-2 px-2">Email</th>
              <th className="text-left py-2 px-2">Account</th>
              <th className="text-right py-2 px-2">Status</th>
              <th className="text-right py-2 px-2">Diff %</th>
              <th className="text-right py-2 px-2">Diff ₽</th>
              <th className="text-right py-2 px-2">Portfolio</th>
              <th className="text-right py-2 px-2">Checked</th>
              <th className="text-right py-2 px-2"></th>
            </tr>
          </thead>
          <tbody>
            {data?.accounts.map((row) => {
              const style = STATUS_STYLES[row.status];
              return (
                <tr
                  key={row.account_id}
                  className="border-b border-white/5 hover:bg-white/2"
                >
                  <td className="py-2 px-2 text-slate-200">{row.user_email}</td>
                  <td className="py-2 px-2 text-slate-300">
                    #{row.account_id} {row.account_name}
                  </td>
                  <td className="py-2 px-2 text-right">
                    <span
                      className={`inline-flex items-center gap-1 px-2 py-0.5 rounded ${style.bg} ${style.color}`}
                    >
                      <span className={`w-1.5 h-1.5 rounded-full ${style.color.replace("text-", "bg-")}`} />
                      {style.label}
                    </span>
                  </td>
                  <td className={`py-2 px-2 text-right font-mono tabular-nums ${style.color}`}>
                    {formatPct(row.diff_pct)}
                  </td>
                  <td className="py-2 px-2 text-right font-mono tabular-nums text-slate-300">
                    {formatCurrency(row.diff_rub)}
                  </td>
                  <td className="py-2 px-2 text-right font-mono tabular-nums text-slate-400">
                    {formatCurrency(row.last_portfolio_value)}
                  </td>
                  <td className="py-2 px-2 text-right text-xs text-slate-500">
                    {timeAgo(row.checked_at)}
                  </td>
                  <td className="py-2 px-2 text-right">
                    <button
                      onClick={() => handleRefreshAccount(row.account_id)}
                      disabled={refreshingId === row.account_id}
                      className="text-xs text-slate-400 hover:text-slate-200 disabled:opacity-40"
                      title="Запустить проверку"
                    >
                      {refreshingId === row.account_id ? "..." : "↻"}
                    </button>
                  </td>
                </tr>
              );
            })}
            {data?.accounts.length === 0 && (
              <tr>
                <td colSpan={8} className="py-8 text-center text-slate-500">
                  Нет данных
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {data && data.total > limit && (
        <div className="flex items-center justify-between text-sm text-slate-400">
          <div>
            Показано {data.accounts.length} из {data.total}
          </div>
          <div className="flex gap-2">
            <button
              onClick={() => setPage((p) => Math.max(0, p - 1))}
              disabled={page === 0}
              className="px-3 py-1 bg-secondary border border-white/10 rounded disabled:opacity-40"
            >
              ← Назад
            </button>
            <button
              onClick={() => setPage((p) => p + 1)}
              disabled={(page + 1) * limit >= data.total}
              className="px-3 py-1 bg-secondary border border-white/10 rounded disabled:opacity-40"
            >
              Вперёд →
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
