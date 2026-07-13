'use client';

/**
 * StatusBadge — small green/orange/red dot showing system health (PR 26 Phase 2).
 *
 * Polls /ready every 60s. Если backend down → red, if 5xx rate spike → orange.
 * Linked to status.empirik.app для подробностей.
 */

import { useEffect, useState } from 'react';
import { getApiUrl } from '@/lib/apiClient';
import { fetchWithTimeout } from '@/lib/fetchWithTimeout';

type Status = 'ok' | 'degraded' | 'down' | 'unknown';

export function SystemStatusBadge() {
  const [status, setStatus] = useState<Status>('unknown');

  useEffect(() => {
    let cancelled = false;

    const check = async () => {
      try {
        const r = await fetchWithTimeout(getApiUrl('/ready'), {
          method: 'GET',
          cache: 'no-store',
          signal: AbortSignal.timeout(5000),
        });
        if (cancelled) return;
        if (r.ok) setStatus('ok');
        else if (r.status >= 500) setStatus('down');
        else setStatus('degraded');
      } catch {
        if (!cancelled) setStatus('down');
      }
    };

    check();
    const id = setInterval(check, 60_000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, []);

  const colors: Record<Status, { dot: string; text: string; label: string }> = {
    ok: { dot: 'bg-green-400', text: 'text-green-400', label: 'OK' },
    degraded: { dot: 'bg-yellow-400 animate-pulse', text: 'text-yellow-400', label: 'Degraded' },
    down: { dot: 'bg-red-500 animate-pulse', text: 'text-red-500', label: 'Down' },
    unknown: { dot: 'bg-slate-500', text: 'text-slate-500', label: 'Checking' },
  };
  const c = colors[status];

  return (
    <a
      href="/status"
      title={`API status: ${c.label}`}
      className="inline-flex items-center gap-1.5 text-[11px] text-slate-400 hover:text-slate-200"
    >
      <span className={`w-2 h-2 rounded-full ${c.dot}`} />
      <span className={c.text}>{c.label}</span>
    </a>
  );
}
