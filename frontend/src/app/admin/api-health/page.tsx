'use client';

/**
 * Admin → API Health (PR 26 Phase 2).
 * Источник: GET /admin/api-health + /admin/slo + /admin/rate-limits/status
 */

import { useEffect, useState } from 'react';
import { api } from '@/lib/apiClient';

interface ApiHealth {
  window_hours: number;
  total_calls: number;
  error_calls: number;
  error_rate_pct: number;
  rate_limited_429: number;
  circuit_open_accounts: number;
  status_distribution: { code: number; count: number; avg_latency_ms: number }[];
  top_error_endpoints: { method: string; errors: number }[];
}

interface Slo {
  window_7d: { sync_total: number; sync_ok: number; sync_error: number; sync_success_rate_pct: number };
  tinkoff_latency_24h_ms: { p50: number | null; p95: number | null; p99: number | null; samples: number };
}

interface RateLimit {
  enabled: boolean;
  backend: string;
  strategy: string;
}

export default function ApiHealthPage() {
  const [health, setHealth] = useState<ApiHealth | null>(null);
  const [slo, setSlo] = useState<Slo | null>(null);
  const [rl, setRl] = useState<RateLimit | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      api.get<ApiHealth>('/admin/api-health'),
      api.get<Slo>('/admin/slo'),
      api.get<RateLimit>('/admin/rate-limits/status'),
    ]).then(([h, s, r]) => {
      setHealth(h);
      setSlo(s);
      setRl(r);
    }).finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="p-8 text-slate-400">Загрузка...</div>;

  return (
    <div className="p-6 max-w-7xl mx-auto">
      <h1 className="text-2xl font-bold mb-6">API Health</h1>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
        <div className="rounded-xl border border-slate-700/50 bg-slate-800/30 p-4">
          <div className="text-xs text-slate-500 uppercase mb-1">Tinkoff calls 24h</div>
          <div className="text-2xl font-bold">{health?.total_calls ?? '—'}</div>
          <div className="text-xs text-slate-400 mt-1">errors: <span className={`font-mono ${(health?.error_rate_pct ?? 0) > 5 ? 'text-red-400' : 'text-slate-300'}`}>{health?.error_rate_pct ?? 0}%</span></div>
        </div>
        <div className="rounded-xl border border-slate-700/50 bg-slate-800/30 p-4">
          <div className="text-xs text-slate-500 uppercase mb-1">429 rate-limited</div>
          <div className={`text-2xl font-bold ${(health?.rate_limited_429 ?? 0) > 0 ? 'text-orange-400' : ''}`}>{health?.rate_limited_429 ?? 0}</div>
        </div>
        <div className="rounded-xl border border-slate-700/50 bg-slate-800/30 p-4">
          <div className="text-xs text-slate-500 uppercase mb-1">Circuit open</div>
          <div className={`text-2xl font-bold ${(health?.circuit_open_accounts ?? 0) > 0 ? 'text-red-400' : ''}`}>{health?.circuit_open_accounts ?? 0}</div>
          <div className="text-xs text-slate-400 mt-1">accounts</div>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
        <div className="rounded-xl border border-slate-700/50 bg-slate-800/30 p-4">
          <div className="text-xs text-slate-500 uppercase mb-3">SLO 7d</div>
          <div className="space-y-2 text-sm">
            <div className="flex justify-between"><span>Sync success rate:</span><span className={`font-mono ${(slo?.window_7d.sync_success_rate_pct ?? 100) < 95 ? 'text-orange-400' : 'text-green-400'}`}>{slo?.window_7d.sync_success_rate_pct ?? 0}%</span></div>
            <div className="flex justify-between"><span>Total syncs:</span><span className="font-mono">{slo?.window_7d.sync_total ?? 0}</span></div>
            <div className="flex justify-between"><span>OK:</span><span className="text-green-400 font-mono">{slo?.window_7d.sync_ok ?? 0}</span></div>
            <div className="flex justify-between"><span>Error:</span><span className="text-red-400 font-mono">{slo?.window_7d.sync_error ?? 0}</span></div>
          </div>
        </div>
        <div className="rounded-xl border border-slate-700/50 bg-slate-800/30 p-4">
          <div className="text-xs text-slate-500 uppercase mb-3">Tinkoff latency 24h</div>
          <div className="space-y-2 text-sm">
            <div className="flex justify-between"><span>p50:</span><span className="font-mono">{slo?.tinkoff_latency_24h_ms.p50 ?? '—'} ms</span></div>
            <div className="flex justify-between"><span>p95:</span><span className="font-mono">{slo?.tinkoff_latency_24h_ms.p95 ?? '—'} ms</span></div>
            <div className="flex justify-between"><span>p99:</span><span className="font-mono">{slo?.tinkoff_latency_24h_ms.p99 ?? '—'} ms</span></div>
            <div className="flex justify-between text-xs text-slate-400 pt-1 border-t border-slate-700/30 mt-2"><span>Samples:</span><span>{slo?.tinkoff_latency_24h_ms.samples ?? 0}</span></div>
          </div>
        </div>
      </div>

      <div className="rounded-xl border border-slate-700/50 bg-slate-800/30 p-4 mb-6">
        <div className="text-xs text-slate-500 uppercase mb-3">Rate limiter</div>
        <div className="text-sm space-y-1">
          <div>Backend: <span className={`font-medium ${rl?.backend === 'redis' ? 'text-green-400' : 'text-orange-400'}`}>{rl?.backend}</span></div>
          <div>Strategy: <span className="font-mono">{rl?.strategy}</span></div>
          <div>Enabled: {rl?.enabled ? '✅' : '❌'}</div>
        </div>
      </div>

      {(health?.top_error_endpoints?.length ?? 0) > 0 && (
        <div className="rounded-xl border border-slate-700/50 bg-slate-800/30 p-4">
          <div className="text-xs text-slate-500 uppercase mb-3">Top error endpoints (24h)</div>
          <div className="space-y-1 text-sm">
            {health!.top_error_endpoints.map((e, i) => (
              <div key={i} className="flex justify-between">
                <span className="font-mono text-slate-300">{e.method}</span>
                <span className="text-red-400">{e.errors}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
