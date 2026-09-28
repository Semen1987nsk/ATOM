'use client';

/**
 * Admin → Audit log (PR 26 Phase 2).
 * Источник: GET /admin/audit-log
 */

import { useEffect, useState } from 'react';
import { api } from '@/lib/apiClient';

interface AuditEntry {
  id: number;
  actor_user_id: number;
  action: string;
  target_user_id: number | null;
  target_account_id: number | null;
  details: Record<string, unknown> | null;
  ip_address: string | null;
  user_agent: string | null;
  created_at: string | null;
}

export default function AuditPage() {
  const [entries, setEntries] = useState<AuditEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [actionFilter, setActionFilter] = useState('');

  useEffect(() => {
    setLoading(true);
    const q = actionFilter ? `?action=${actionFilter}&limit=200` : '?limit=200';
    api.get<{ entries: AuditEntry[] }>(`/admin/audit-log${q}`)
      .then(r => setEntries(r.entries))
      .finally(() => setLoading(false));
  }, [actionFilter]);

  const uniqueActions = Array.from(new Set(entries.map(e => e.action)));

  return (
    <div className="p-6 max-w-7xl mx-auto">
      <h1 className="text-2xl font-bold mb-4">Audit Log</h1>

      <div className="mb-4 flex gap-2">
        <select
          value={actionFilter}
          onChange={(e) => setActionFilter(e.target.value)}
          className="px-3 py-2 bg-slate-800 border border-slate-700 rounded text-sm"
        >
          <option value="">Все действия</option>
          {uniqueActions.map(a => <option key={a} value={a}>{a}</option>)}
        </select>
      </div>

      {loading ? (
        <div className="text-slate-400">Загрузка...</div>
      ) : entries.length === 0 ? (
        <div className="text-slate-500">Нет записей</div>
      ) : (
        <div className="rounded-xl border border-slate-700/50 bg-slate-800/30 overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-slate-800/50 text-xs uppercase text-slate-500">
              <tr>
                <th className="text-left p-3">Время</th>
                <th className="text-left p-3">Actor</th>
                <th className="text-left p-3">Action</th>
                <th className="text-left p-3">Target</th>
                <th className="text-left p-3">IP</th>
                <th className="text-left p-3">Детали</th>
              </tr>
            </thead>
            <tbody>
              {entries.map(e => (
                <tr key={e.id} className="border-t border-slate-700/30 hover:bg-slate-800/30">
                  <td className="p-3 text-xs text-slate-400 whitespace-nowrap">{e.created_at ? new Date(e.created_at).toLocaleString('ru-RU') : '—'}</td>
                  <td className="p-3 font-mono text-xs">user #{e.actor_user_id}</td>
                  <td className="p-3"><span className="px-2 py-0.5 bg-slate-700/50 rounded text-xs">{e.action}</span></td>
                  <td className="p-3 text-xs">
                    {e.target_user_id ? `user #${e.target_user_id}` : ''}
                    {e.target_account_id ? ` acc #${e.target_account_id}` : ''}
                  </td>
                  <td className="p-3 font-mono text-xs text-slate-400">{e.ip_address || '—'}</td>
                  <td className="p-3 text-xs text-slate-400 max-w-xs truncate" title={JSON.stringify(e.details)}>
                    {e.details ? JSON.stringify(e.details) : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
