'use client';

/**
 * Public status page — PR 26 Phase 2.
 *
 * Простая страница для пользователей: "работает или нет".
 * Никаких internal metrics — только пользовательский statuses:
 * - API: green/yellow/red
 * - Tinkoff sync: working/degraded/down
 * - Last incident: date
 */

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { CheckCircle, AlertCircle, AlertTriangle } from 'lucide-react';
import { getApiUrl } from '@/lib/apiClient';

interface ReadyResponse {
  status: 'ready' | 'not_ready';
  dependencies?: {
    database?: 'ok' | 'error';
    redis?: 'ok' | 'error' | 'unavailable';
  };
}

export default function StatusPage() {
  const [ready, setReady] = useState<ReadyResponse | null>(null);
  const [checking, setChecking] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const check = async () => {
      setChecking(true);
      setError(null);
      try {
        const r = await fetch(getApiUrl('/ready'), { cache: 'no-store' });
        const data = await r.json().catch(() => null);
        if (!r.ok) {
          setError(`HTTP ${r.status}`);
          setReady(data);
        } else {
          setReady(data);
        }
      } catch (e) {
        setError((e as Error).message || 'network error');
        setReady(null);
      } finally {
        setChecking(false);
      }
    };
    check();
    const id = setInterval(check, 30_000);
    return () => clearInterval(id);
  }, []);

  const overall: 'ok' | 'degraded' | 'down' = error
    ? 'down'
    : ready?.status === 'ready'
      ? 'ok'
      : 'degraded';

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 p-6 md:p-12">
      <div className="max-w-3xl mx-auto">
        <Link href="/" className="text-sm text-slate-400 hover:text-slate-200">
          ← Эмпирик
        </Link>
        <h1 className="text-3xl md:text-4xl font-bold mt-4 mb-2">System Status</h1>
        <p className="text-slate-400 mb-8">Текущее состояние сервиса. Обновляется каждые 30 секунд.</p>

        <div className={`rounded-xl border p-6 mb-6 ${
          overall === 'ok' ? 'border-green-500/30 bg-green-500/10' :
          overall === 'degraded' ? 'border-yellow-500/30 bg-yellow-500/10' :
          'border-red-500/30 bg-red-500/10'
        }`}>
          <div className="flex items-center gap-3">
            {overall === 'ok' && <CheckCircle size={32} className="text-green-400" />}
            {overall === 'degraded' && <AlertTriangle size={32} className="text-yellow-400" />}
            {overall === 'down' && <AlertCircle size={32} className="text-red-400" />}
            <div>
              <div className={`text-2xl font-bold ${
                overall === 'ok' ? 'text-green-300' :
                overall === 'degraded' ? 'text-yellow-300' :
                'text-red-300'
              }`}>
                {overall === 'ok' && 'Все системы работают нормально'}
                {overall === 'degraded' && 'Частичная работоспособность'}
                {overall === 'down' && 'Сервис недоступен'}
              </div>
              {error && <div className="text-sm text-red-300 mt-1">{error}</div>}
            </div>
          </div>
        </div>

        <div className="space-y-3">
          <h2 className="text-lg font-semibold mb-2">Компоненты</h2>
          <StatusRow
            name="API"
            status={ready?.status === 'ready' ? 'ok' : (error ? 'down' : 'unknown')}
          />
          <StatusRow
            name="База данных"
            status={ready?.dependencies?.database === 'ok' ? 'ok' :
              ready?.dependencies?.database === 'error' ? 'down' : 'unknown'}
          />
          <StatusRow
            name="Redis (rate limiter)"
            status={ready?.dependencies?.redis === 'ok' ? 'ok' :
              ready?.dependencies?.redis === 'error' ? 'down' :
              ready?.dependencies?.redis === 'unavailable' ? 'degraded' : 'unknown'}
          />
        </div>

        <div className="mt-8 text-xs text-slate-500">
          Последняя проверка: {checking ? 'идёт...' : new Date().toLocaleString('ru-RU')}
        </div>

        <div className="mt-12 text-sm text-slate-400 border-t border-slate-800 pt-6">
          Если что-то не работает — напишите в{' '}
          <a href="mailto:support@empirik.app" className="text-blue-400 hover:underline">support@empirik.app</a>.
          Мы ответим в течение 24 часов.
        </div>
      </div>
    </div>
  );
}

function StatusRow({ name, status }: { name: string; status: 'ok' | 'degraded' | 'down' | 'unknown' }) {
  const colors = {
    ok: { dot: 'bg-green-400', text: 'OK', cls: 'text-green-400' },
    degraded: { dot: 'bg-yellow-400', text: 'Degraded', cls: 'text-yellow-400' },
    down: { dot: 'bg-red-500', text: 'Down', cls: 'text-red-500' },
    unknown: { dot: 'bg-slate-500', text: 'Checking…', cls: 'text-slate-500' },
  };
  const c = colors[status];
  return (
    <div className="flex items-center justify-between rounded-lg border border-slate-800 bg-slate-900/50 p-3">
      <div className="flex items-center gap-3">
        <span className={`w-2.5 h-2.5 rounded-full ${c.dot}`} />
        <span>{name}</span>
      </div>
      <span className={`text-sm font-medium ${c.cls}`}>{c.text}</span>
    </div>
  );
}
