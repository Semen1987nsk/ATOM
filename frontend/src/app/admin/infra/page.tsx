'use client';

/**
 * Admin → Infra (PR 26 Phase 2).
 * Источник: GET /admin/db-stats + /admin/backups/status + /admin/sync-queue
 */

import { useEffect, useState } from 'react';
import { Database, HardDrive, Activity } from 'lucide-react';
import { api } from '@/lib/apiClient';

interface DbStats {
  db_type: string;
  db_size_bytes: number | null;
  db_size_mb: number | null;
  row_counts: Record<string, number | null>;
}

interface BackupInfo {
  filename: string;
  size_mb: number;
  created_at: string;
}

interface BackupStatus {
  backup_dir: string;
  exists: boolean;
  backups: BackupInfo[];
  count: number;
  latest: BackupInfo | null;
  note?: string;
}

interface SyncQueueEntry {
  user_id: number;
  account_id: number;
  broker_account_id: string | null;
  last_sync_at: string | null;
  consecutive_failures: number;
  circuit_open_until?: string;
}

interface SyncQueue {
  circuit_open: SyncQueueEntry[];
  stale_24h: SyncQueueEntry[];
  healthy: SyncQueueEntry[];
  total_active: number;
}

export default function InfraPage() {
  const [db, setDb] = useState<DbStats | null>(null);
  const [bk, setBk] = useState<BackupStatus | null>(null);
  const [queue, setQueue] = useState<SyncQueue | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      api.get<DbStats>('/admin/db-stats'),
      api.get<BackupStatus>('/admin/backups/status'),
      api.get<SyncQueue>('/admin/sync-queue'),
    ]).then(([d, b, q]) => {
      setDb(d);
      setBk(b);
      setQueue(q);
    }).finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="p-8 text-slate-400">Загрузка...</div>;

  return (
    <div className="p-6 max-w-7xl mx-auto">
      <h1 className="text-2xl font-bold mb-6">Infrastructure</h1>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
        <div className="rounded-xl border border-slate-700/50 bg-slate-800/30 p-5">
          <div className="flex items-center gap-2 mb-3">
            <Database size={18} className="text-blue-400" />
            <h2 className="font-semibold">Database</h2>
          </div>
          <div className="text-sm space-y-1">
            <div className="flex justify-between"><span className="text-slate-500">Type:</span><span className="font-mono">{db?.db_type}</span></div>
            <div className="flex justify-between"><span className="text-slate-500">Size:</span><span className="font-mono">{db?.db_size_mb ? `${db.db_size_mb} MB` : '—'}</span></div>
          </div>
          <div className="mt-4">
            <div className="text-xs text-slate-500 uppercase mb-2">Row counts</div>
            <div className="grid grid-cols-2 gap-x-3 gap-y-1 text-xs">
              {db && Object.entries(db.row_counts).map(([t, n]) => (
                <div key={t} className="flex justify-between">
                  <span className="text-slate-400 truncate">{t}</span>
                  <span className="font-mono">{n ?? '—'}</span>
                </div>
              ))}
            </div>
          </div>
        </div>

        <div className="rounded-xl border border-slate-700/50 bg-slate-800/30 p-5">
          <div className="flex items-center gap-2 mb-3">
            <HardDrive size={18} className="text-green-400" />
            <h2 className="font-semibold">Backups</h2>
          </div>
          {!bk?.exists ? (
            <div className="text-sm text-orange-400">{bk?.note || 'Каталог backup не найден'}</div>
          ) : (
            <>
              <div className="text-sm mb-3">
                <span className="text-slate-500">Каталог:</span> <span className="font-mono text-xs">{bk.backup_dir}</span>
              </div>
              <div className="text-sm mb-3">
                <span className="text-slate-500">Всего:</span> {bk.count} файлов
              </div>
              {bk.latest && (
                <div className="text-xs">
                  <div className="text-slate-500 mb-1">Последний:</div>
                  <div className="font-mono">{bk.latest.filename}</div>
                  <div className="text-slate-400">{bk.latest.size_mb} MB · {new Date(bk.latest.created_at).toLocaleString('ru-RU')}</div>
                </div>
              )}
            </>
          )}
        </div>
      </div>

      <div className="rounded-xl border border-slate-700/50 bg-slate-800/30 p-5">
        <div className="flex items-center gap-2 mb-3">
          <Activity size={18} className="text-purple-400" />
          <h2 className="font-semibold">Sync queue</h2>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-sm">
          <div>
            <div className="text-xs text-slate-500 uppercase mb-2">Circuit open ({queue?.circuit_open.length ?? 0})</div>
            {queue?.circuit_open.length === 0 ? <div className="text-xs text-slate-500">—</div> :
              queue?.circuit_open.map((e, i) => (
                <div key={i} className="text-xs py-1 border-b border-slate-700/30">
                  <div>user #{e.user_id} acc #{e.account_id}</div>
                  <div className="text-red-400">{e.circuit_open_until ? `до ${new Date(e.circuit_open_until).toLocaleString('ru-RU')}` : ''}</div>
                </div>
              ))
            }
          </div>
          <div>
            <div className="text-xs text-slate-500 uppercase mb-2">Stale 24h+ ({queue?.stale_24h.length ?? 0})</div>
            {queue?.stale_24h.length === 0 ? <div className="text-xs text-slate-500">—</div> :
              queue?.stale_24h.slice(0, 10).map((e, i) => (
                <div key={i} className="text-xs py-1 border-b border-slate-700/30">
                  <div>user #{e.user_id} acc #{e.account_id}</div>
                  <div className="text-orange-400">{e.last_sync_at ? new Date(e.last_sync_at).toLocaleString('ru-RU') : 'never'}</div>
                </div>
              ))
            }
          </div>
          <div>
            <div className="text-xs text-slate-500 uppercase mb-2">Healthy ({queue?.healthy.length ?? 0})</div>
            <div className="text-xs text-slate-400">всего активных: {queue?.total_active ?? 0}</div>
          </div>
        </div>
      </div>
    </div>
  );
}
