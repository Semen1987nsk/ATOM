'use client';

/**
 * BrokerStatusBadge — компактный индикатор статуса брокерского
 * подключения для header'а (PR 13).
 *
 * Цвета:
 * - зелёный  — есть активное подключение, последний sync ≤ 5 минут
 * - голубой  — есть подключение, sync ≤ интервала auto-sync
 * - жёлтый   — auto-sync выключен или давно не синхронизировались
 * - красный  — error в последнем sync / circuit breaker открыт
 * - серый    — нет подключений
 */

import { useEffect, useState } from 'react';
import { Link2, RefreshCw, AlertTriangle, CheckCircle2 } from 'lucide-react';
import { api } from '@/lib/apiClient';

interface SyncStatusConnection {
  id: number;
  broker: string;
  broker_account_id: string;
  auto_sync_enabled: boolean;
  sync_interval_minutes: number;
  last_sync_at: string | null;
  last_sync_status: string | null;
  last_sync_error: string | null;
  next_sync_at: string | null;
  consecutive_failures: number;
  circuit_open_until: string | null;
  total_synced_trades: number;
}

interface SyncStatusResponse {
  has_connections: boolean;
  scheduler: Record<string, unknown>;
  connections: SyncStatusConnection[];
}

type BadgeState = {
  color: 'green' | 'blue' | 'amber' | 'red' | 'gray';
  label: string;
  detail: string;
  icon: 'check' | 'sync' | 'warn' | 'unplug';
};

const COLOR_CLASSES: Record<BadgeState['color'], string> = {
  green: 'bg-[#00d4aa]/15 text-[#00d4aa] border-[#00d4aa]/30',
  blue: 'bg-blue-500/15 text-blue-300 border-blue-500/30',
  amber: 'bg-amber-500/15 text-amber-300 border-amber-500/30',
  red: 'bg-red-500/15 text-red-300 border-red-500/30',
  gray: 'bg-gray-500/15 text-gray-300 border-gray-500/30',
};

function deriveState(data: SyncStatusResponse | null): BadgeState {
  if (!data?.has_connections) {
    return {
      color: 'gray',
      label: 'Брокер не подключён',
      detail: 'Подключите Тинькофф для автоимпорта сделок',
      icon: 'unplug',
    };
  }
  // Берём «самое тревожное» состояние среди всех подключений.
  let worst: BadgeState = {
    color: 'green',
    label: 'Синхронизировано',
    detail: '',
    icon: 'check',
  };
  const now = Date.now();

  for (const c of data.connections) {
    // Circuit breaker открыт — самое тревожное.
    if (c.circuit_open_until && Date.parse(c.circuit_open_until) > now) {
      return {
        color: 'red',
        label: 'Sync приостановлен',
        detail: `${c.broker_account_id}: ${c.consecutive_failures} ошибок подряд. Проверьте токен.`,
        icon: 'warn',
      };
    }
    if (c.last_sync_status === 'error') {
      worst = {
        color: 'red',
        label: 'Ошибка sync',
        detail: c.last_sync_error?.slice(0, 80) ?? 'unknown',
        icon: 'warn',
      };
      continue;
    }
    if (!c.last_sync_at) {
      // Ещё ни разу не синкались.
      if (worst.color === 'green' || worst.color === 'blue') {
        worst = {
          color: 'amber',
          label: 'Ожидание первой синхронизации',
          detail: c.auto_sync_enabled
            ? `Запустится автоматически через ${c.sync_interval_minutes} мин`
            : 'Auto-sync выключен — запустите вручную',
          icon: 'sync',
        };
      }
      continue;
    }
    const lastMs = Date.parse(c.last_sync_at);
    const ageMin = (now - lastMs) / 60000;
    if (!c.auto_sync_enabled) {
      if (worst.color === 'green') {
        worst = {
          color: 'amber',
          label: 'Auto-sync выключен',
          detail: `Последняя синхронизация ${formatRelative(c.last_sync_at)}`,
          icon: 'sync',
        };
      }
      continue;
    }
    if (ageMin > c.sync_interval_minutes * 3) {
      if (worst.color === 'green' || worst.color === 'blue') {
        worst = {
          color: 'amber',
          label: 'Синхронизация отстаёт',
          detail: `Последняя синхронизация ${formatRelative(c.last_sync_at)}`,
          icon: 'sync',
        };
      }
      continue;
    }
    if (worst.color === 'green') {
      worst = {
        color: 'green',
        label: 'Синхронизировано',
        detail: `Последняя ${formatRelative(c.last_sync_at)}`,
        icon: 'check',
      };
    }
  }
  return worst;
}

function formatRelative(iso: string): string {
  const diffSec = (Date.now() - Date.parse(iso)) / 1000;
  if (diffSec < 60) return 'только что';
  if (diffSec < 3600) return `${Math.round(diffSec / 60)} мин назад`;
  if (diffSec < 86400) return `${Math.round(diffSec / 3600)} ч назад`;
  return `${Math.round(diffSec / 86400)} дн назад`;
}

interface Props {
  /** Интервал поллинга /broker/sync-status, мс. По умолчанию 30 сек. */
  refreshIntervalMs?: number;
  /** Колбек при клике (обычно открывает BrokerConnectModal). */
  onClick?: () => void;
}

export default function BrokerStatusBadge({
  refreshIntervalMs = 30000,
  onClick,
}: Props) {
  const [data, setData] = useState<SyncStatusResponse | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    const fetchOnce = async () => {
      try {
        const res = await api.get<SyncStatusResponse>('/broker/sync-status');
        if (!cancelled) setData(res);
      } catch {
        // Не падаем — оставим прежнее состояние или null.
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    fetchOnce();
    const interval = setInterval(fetchOnce, refreshIntervalMs);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [refreshIntervalMs]);

  if (loading && !data) {
    return (
      <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-gray-500/10 text-gray-400 text-xs border border-gray-500/20">
        <RefreshCw className="w-3.5 h-3.5 animate-spin" />
        <span>Загрузка…</span>
      </div>
    );
  }

  const state = deriveState(data);
  const Icon =
    state.icon === 'check'
      ? CheckCircle2
      : state.icon === 'sync'
      ? RefreshCw
      : state.icon === 'warn'
      ? AlertTriangle
      : Link2;

  return (
    <button
      type="button"
      onClick={onClick}
      title={state.detail}
      className={`inline-flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-medium border transition-colors hover:opacity-90 ${COLOR_CLASSES[state.color]}`}
    >
      <Icon className="w-3.5 h-3.5" />
      <span>{state.label}</span>
    </button>
  );
}
