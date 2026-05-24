'use client';

/**
 * ReconnectBanner — PR 26 Scenario #31, #64.
 *
 * Показывается на dashboard если у юзера есть BrokerConnection в состоянии:
 * - is_active=False (токен отозван в Tinkoff приложении)
 * - last_sync_status='error' с consecutive_failures >= 3
 * - circuit_open_until в будущем (sync временно отключён)
 *
 * Без этого баннера юзер видит "0 сделок" и думает что приложение сломано.
 * А реальная причина — токен надо пересоздать.
 */

import { useEffect, useState } from 'react';
import { AlertTriangle, X } from 'lucide-react';
import { api } from '@/lib/apiClient';

interface ConnectionStatus {
  id: number;
  broker: string;
  is_active: boolean;
  last_sync_status: string | null;
  last_sync_error: string | null;
  consecutive_failures?: number;
  circuit_open_until?: string | null;
}

interface Props {
  onOpenBrokerModal?: () => void;
}

export function ReconnectBanner({ onOpenBrokerModal }: Props) {
  const [conn, setConn] = useState<ConnectionStatus | null>(null);
  const [dismissed, setDismissed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    api.get<ConnectionStatus[]>('/broker/connections').then(connections => {
      if (cancelled) return;
      const list = connections || [];
      // Ищем первое broken-соединение
      const broken = list.find(c => {
        if (!c.is_active) return true;
        if ((c.consecutive_failures ?? 0) >= 3) return true;
        if (c.circuit_open_until && new Date(c.circuit_open_until) > new Date()) return true;
        return false;
      });
      setConn(broken ?? null);
    }).catch(() => {
      // Ignore — баннер просто не показывается
    });
    return () => { cancelled = true; };
  }, []);

  if (!conn || dismissed) return null;

  // Определяем причину
  let reason = '';
  let actionLabel = 'Переподключить';
  if (!conn.is_active) {
    reason = 'Токен брокера отозван или удалён. Возможно, вы пересоздали токен в приложении Тинькофф.';
  } else if (conn.circuit_open_until && new Date(conn.circuit_open_until) > new Date()) {
    reason = `Синхронизация временно приостановлена из-за повторяющихся ошибок (до ${new Date(conn.circuit_open_until).toLocaleString('ru-RU')}). Это может быть проблема API Тинькоф.`;
    actionLabel = 'Подробнее';
  } else {
    reason = `Несколько последних синхронизаций завершились ошибкой${conn.last_sync_error ? `: ${conn.last_sync_error}` : ''}. Проверьте токен брокера.`;
  }

  return (
    <div className="mb-4 rounded-[var(--radius-xl)] border border-red-500/40 bg-red-500/10 p-4">
      <div className="flex items-start gap-3">
        <AlertTriangle size={20} className="text-red-400 shrink-0 mt-0.5" />
        <div className="flex-1 min-w-0">
          <div className="font-semibold text-red-300 mb-1">
            Требуется переподключение брокера
          </div>
          <div className="text-sm text-red-200/90 mb-3">
            {reason}
          </div>
          <div className="flex flex-wrap gap-2">
            <button
              onClick={onOpenBrokerModal}
              className="px-3 py-1.5 bg-red-500 hover:bg-red-600 text-white text-sm rounded-md transition-colors"
            >
              {actionLabel}
            </button>
            <button
              onClick={() => setDismissed(true)}
              className="px-3 py-1.5 border border-red-500/30 text-red-300 hover:bg-red-500/10 text-sm rounded-md transition-colors"
            >
              Скрыть
            </button>
          </div>
        </div>
        <button
          onClick={() => setDismissed(true)}
          className="text-red-400/70 hover:text-red-400 shrink-0"
          aria-label="Закрыть"
        >
          <X size={18} />
        </button>
      </div>
    </div>
  );
}
