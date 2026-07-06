'use client';

import { useState, useEffect, useCallback } from 'react';
import {
  RefreshCw, CheckCircle, AlertCircle, Clock,
  Zap, ChevronDown, ChevronUp, Link2, ShieldCheck, ShieldAlert
} from 'lucide-react';
import { api, ApiError } from '@/lib/apiClient';
import { useSyncStatusQuery } from '@/lib/useSyncStatusQuery';
import { useToast } from '@/contexts/ToastContext';

// PR 20: Health-audit response shape.
interface HealthIssue {
  check_id: string;
  severity: 'warning' | 'error';
  count: number;
  description: string;
  sample_ids?: number[];
}

interface HealthCheck {
  id: number;
  checked_at: string;
  status: 'ok' | 'warning' | 'error';
  total_trades_checked: number;
  trades_with_issues: number;
  main_issue: string | null;
  issues: HealthIssue[];
}

interface HealthResponse {
  latest: HealthCheck | null;
  history: HealthCheck[];
}

interface ConnectionStatus {
  id: number;
  broker: string;
  broker_account_id: string;
  auto_sync_enabled: boolean;
  sync_interval_minutes: number;
  last_sync_at: string | null;
  last_sync_status: string | null;
  last_sync_error: string | null;
  next_sync_at: string | null;
  total_synced_trades: number;
  is_syncing: boolean;
  // PR 17: детали последней синхронизации (заполняются pipeline'ом).
  last_sync_operations_count?: number | null;
  last_sync_trades_count?: number | null;
  last_sync_positions_count?: number | null;
  last_sync_duration_ms?: number | null;
}

interface SyncStatus {
  has_connections: boolean;
  scheduler: {
    running: boolean;
    last_check: string | null;
    check_interval_seconds: number;
    syncing_connections: number[];
  };
  connections: ConnectionStatus[];
}

interface SyncStatusIndicatorProps {
  onTradesUpdated?: () => void;
  onOpenBrokerModal?: () => void;
}

export default function SyncStatusIndicator({
  onTradesUpdated,
  onOpenBrokerModal
}: SyncStatusIndicatorProps) {
  // FE-10: shared TanStack-хук дедупит /broker/sync-status с BrokerStatusBadge.
  // refetch() даёт ручной форс-рефреш после triggerSync.
  const {
    data: status,
    isPending: statusLoading,
    refetch: refetchStatus,
  } = useSyncStatusQuery<SyncStatus>({ refetchInterval: 30000 });

  const [health, setHealth] = useState<HealthCheck | null>(null);
  const [healthLoading, setHealthLoading] = useState(true);
  const [expanded, setExpanded] = useState(false);
  const [syncing, setSyncing] = useState<number | null>(null);
  const [countdown, setCountdown] = useState<string>('');
  const toast = useToast();

  // PR 20: подтягиваем последний health-audit для индикатора.
  // (Отдельный poll — другая responsibility, не дедуплится с sync-status.)
  const fetchHealth = useCallback(async () => {
    try {
      const data = await api.get<HealthResponse>('/broker/health');
      setHealth(data.latest);
    } catch {
      // Health не критичен для основного UI — молча.
      setHealth(null);
    } finally {
      setHealthLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchHealth();
    const interval = setInterval(fetchHealth, 30000);
    return () => clearInterval(interval);
  }, [fetchHealth]);

  // Composite loading: до первой загрузки обоих источников.
  const loading = statusLoading || healthLoading;

  // Обновляем countdown каждую секунду
  useEffect(() => {
    const updateCountdown = () => {
      if (!status?.connections.length) return;
      
      const conn = status.connections[0];
      if (!conn.next_sync_at || !conn.auto_sync_enabled) {
        setCountdown('');
        return;
      }

      const nextSync = new Date(conn.next_sync_at);
      const now = new Date();
      const diff = nextSync.getTime() - now.getTime();

      if (diff <= 0) {
        setCountdown('сейчас');
        return;
      }

      const minutes = Math.floor(diff / 60000);
      const seconds = Math.floor((diff % 60000) / 1000);

      if (minutes > 0) {
        setCountdown(`${minutes}м ${seconds}с`);
      } else {
        setCountdown(`${seconds}с`);
      }
    };

    updateCountdown();
    const interval = setInterval(updateCountdown, 1000);
    return () => clearInterval(interval);
  }, [status]);

  const triggerSync = async (connectionId: number) => {
    setSyncing(connectionId);
    try {
      // Блокирующий endpoint (10-90с) — держим spinner до фактического ответа,
      // затем сразу рефетчим статус (ERR-303: фикс-таймеры вводили в заблуждение).
      await api.post(`/broker/trigger-sync/${connectionId}`);
      refetchStatus();
      onTradesUpdated?.();
    } catch (error) {
      toast.error(error instanceof ApiError ? error.toUserMessage() : 'Не удалось запустить синхронизацию');
    } finally {
      setSyncing(null);
    }
  };

  const formatTime = (isoString: string) => {
    const date = new Date(isoString);
    return date.toLocaleTimeString('ru-RU', { 
      hour: '2-digit', 
      minute: '2-digit' 
    });
  };

  const formatDate = (isoString: string) => {
    const date = new Date(isoString);
    const today = new Date();
    const isToday = date.toDateString() === today.toDateString();
    
    if (isToday) {
      return `Сегодня в ${formatTime(isoString)}`;
    }
    
    return date.toLocaleDateString('ru-RU', {
      day: '2-digit',
      month: '2-digit',
      hour: '2-digit',
      minute: '2-digit'
    });
  };

  // Нет подключений → показываем компактную кнопку «Подключить брокера»,
  // чтобы у юзера всегда был быстрый вход в API-онбординг из шапки.
  if (!loading && (!status || !status.has_connections)) {
    if (!onOpenBrokerModal) return null;
    return (
      <button
        onClick={onOpenBrokerModal}
        className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border border-[var(--accent)]/40 bg-[var(--accent-soft)] text-[var(--accent)] hover:bg-[var(--accent)]/15 transition-colors text-[12px] font-medium"
        title="Подключить брокера через API"
      >
        <Link2 size={13} />
        <span className="hidden xl:inline">Подключить брокера</span>
        <span className="xl:hidden">Брокер</span>
      </button>
    );
  }

  if (loading) {
    return (
      <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-slate-800/50 border border-slate-700/50">
        <RefreshCw size={14} className="animate-spin text-slate-500" />
        <span className="text-xs text-slate-500">Загрузка...</span>
      </div>
    );
  }

  const connection = status?.connections[0];
  const isSyncing = connection?.is_syncing || syncing === connection?.id;
  const isSuccess = connection?.last_sync_status === 'success';
  const isError = connection?.last_sync_status === 'error';

  return (
    <div className="relative">
      {/* Компактный индикатор */}
      <button
        onClick={() => setExpanded(!expanded)}
        className={`
          flex items-center gap-2 px-3 py-2 rounded-lg border transition-all
          ${isSyncing 
            ? 'bg-blue-500/10 border-blue-500/30 text-blue-400' 
            : isSuccess 
              ? 'bg-green-500/10 border-green-500/30 text-green-400'
              : isError
                ? 'bg-red-500/10 border-red-500/30 text-red-400'
                : 'bg-slate-800/50 border-slate-700/50 text-slate-400'
          }
          hover:border-accent/50
        `}
      >
        {isSyncing ? (
          <RefreshCw size={14} className="animate-spin" />
        ) : isSuccess ? (
          <CheckCircle size={14} />
        ) : isError ? (
          <AlertCircle size={14} />
        ) : (
          <Link2 size={14} />
        )}
        
        <div className="flex flex-col items-start">
          <span className="text-xs font-medium">
            {isSyncing ? 'Синхронизация...' : 'Тинькофф'}
          </span>
          {connection?.last_sync_at && !isSyncing && (
            <span className="text-[10px] opacity-70">
              {formatTime(connection.last_sync_at)}
            </span>
          )}
        </div>

        {expanded ? (
          <ChevronUp size={14} className="ml-1 opacity-50" />
        ) : (
          <ChevronDown size={14} className="ml-1 opacity-50" />
        )}
      </button>

      {/* Развёрнутая панель */}
      {expanded && connection && (
        <div className="absolute top-full right-0 mt-2 w-72 bg-slate-900/95 backdrop-blur-xl border border-slate-700 rounded-xl shadow-2xl z-[100] overflow-hidden">
          {/* Header */}
          <div className="p-4 border-b border-slate-700/50 bg-gradient-to-r from-yellow-500/10 to-orange-500/10">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Zap size={16} className="text-yellow-400" />
                <span className="font-semibold text-white">Авто-синхронизация</span>
              </div>
              <span className={`text-xs px-2 py-0.5 rounded-full ${
                connection.auto_sync_enabled 
                  ? 'bg-green-500/20 text-green-400' 
                  : 'bg-slate-700 text-slate-400'
              }`}>
                {connection.auto_sync_enabled ? 'Вкл' : 'Выкл'}
              </span>
            </div>
          </div>

          {/* Stats */}
          <div className="p-4 space-y-3">
            {/* Последняя синхронизация */}
            <div className="flex items-center justify-between">
              <span className="text-xs text-slate-500">Последняя синхр.</span>
              <span className="text-sm text-white">
                {connection.last_sync_at 
                  ? formatDate(connection.last_sync_at)
                  : 'Никогда'
                }
              </span>
            </div>

            {/* Статус */}
            <div className="flex items-center justify-between">
              <span className="text-xs text-slate-500">Статус</span>
              <span className={`text-sm flex items-center gap-1 ${
                isSuccess ? 'text-green-400' : isError ? 'text-red-400' : 'text-slate-400'
              }`}>
                {isSuccess ? (
                  <>
                    <CheckCircle size={12} />
                    Успешно
                  </>
                ) : isError ? (
                  <>
                    <AlertCircle size={12} />
                    Ошибка
                  </>
                ) : (
                  'Ожидание'
                )}
              </span>
            </div>

            {/* Следующая синхронизация */}
            {connection.auto_sync_enabled && countdown && (
              <div className="flex items-center justify-between">
                <span className="text-xs text-slate-500">Следующая через</span>
                <span className="text-sm text-blue-400 flex items-center gap-1">
                  <Clock size={12} />
                  {countdown}
                </span>
              </div>
            )}

            {/* Интервал */}
            <div className="flex items-center justify-between">
              <span className="text-xs text-slate-500">Интервал</span>
              <span className="text-sm text-slate-300">
                каждые {connection.sync_interval_minutes} мин
              </span>
            </div>

            {/* Всего сделок */}
            <div className="flex items-center justify-between">
              <span className="text-xs text-slate-500">Синхронизировано</span>
              <span className="text-sm text-white font-medium">
                {connection.total_synced_trades} сделок
              </span>
            </div>

            {/* Детали последнего sync (PR 17). Показываем только если есть
                хотя бы один из счётчиков — иначе блок пустой и сбивает с толку. */}
            {(connection.last_sync_operations_count != null ||
              connection.last_sync_trades_count != null ||
              connection.last_sync_positions_count != null ||
              connection.last_sync_duration_ms != null) && (
              <div className="pt-3 mt-3 border-t border-slate-700/50">
                <div className="text-[10px] text-slate-500 uppercase tracking-wider mb-2">
                  Последняя синхронизация
                </div>
                <div className="space-y-1.5">
                  {connection.last_sync_operations_count != null && (
                    <div className="flex items-center justify-between">
                      <span className="text-xs text-slate-500">Операций</span>
                      <span className="text-xs text-slate-300 font-mono">
                        {connection.last_sync_operations_count.toLocaleString('ru-RU')}
                      </span>
                    </div>
                  )}
                  {connection.last_sync_trades_count != null && (
                    <div className="flex items-center justify-between">
                      <span className="text-xs text-slate-500">FIFO-сделок</span>
                      <span className="text-xs text-slate-300 font-mono">
                        {connection.last_sync_trades_count.toLocaleString('ru-RU')}
                      </span>
                    </div>
                  )}
                  {connection.last_sync_positions_count != null && (
                    <div className="flex items-center justify-between">
                      <span className="text-xs text-slate-500">Открытых позиций</span>
                      <span className="text-xs text-slate-300 font-mono">
                        {connection.last_sync_positions_count}
                      </span>
                    </div>
                  )}
                  {connection.last_sync_duration_ms != null && (
                    <div className="flex items-center justify-between">
                      <span className="text-xs text-slate-500">Длительность</span>
                      <span className="text-xs text-slate-300 font-mono">
                        {connection.last_sync_duration_ms < 1000
                          ? `${connection.last_sync_duration_ms} мс`
                          : `${(connection.last_sync_duration_ms / 1000).toFixed(1)} с`}
                      </span>
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* Ошибка если есть */}
            {isError && connection.last_sync_error && (
              <div className="p-2 bg-red-500/10 rounded-lg border border-red-500/20">
                <p className="text-xs text-red-400 line-clamp-2">
                  {connection.last_sync_error}
                </p>
              </div>
            )}

            {/* PR 20: Health-audit карточка. Простое сообщение для юзера —
                без технических деталей (issues_json — это для админа). */}
            {health && (
              <div className={`pt-3 mt-3 border-t border-slate-700/50`}>
                <div className="text-[10px] text-slate-500 uppercase tracking-wider mb-2">
                  Проверки импорта
                </div>
                {health.status === 'ok' && (
                  <div className="flex items-start gap-2 p-2 rounded-lg bg-green-500/10 border border-green-500/20">
                    <ShieldCheck size={14} className="text-green-400 mt-0.5 shrink-0" />
                    <div className="text-xs text-green-300">
                      Все {health.total_trades_checked.toLocaleString('ru-RU')} сделок прошли проверку
                    </div>
                  </div>
                )}
                {health.status === 'warning' && (
                  <div className="flex items-start gap-2 p-2 rounded-lg bg-yellow-500/10 border border-yellow-500/20">
                    <ShieldAlert size={14} className="text-yellow-400 mt-0.5 shrink-0" />
                    <div className="text-xs text-yellow-200">
                      <div>Найдено {health.issues.length} предупреждение(й)</div>
                      <div className="text-[10px] text-yellow-200/70 mt-1">
                        Данные импортируются, но проверьте детали с поддержкой.
                      </div>
                    </div>
                  </div>
                )}
                {health.status === 'error' && (
                  <div className="flex items-start gap-2 p-2 rounded-lg bg-red-500/10 border border-red-500/20">
                    <ShieldAlert size={14} className="text-red-400 mt-0.5 shrink-0" />
                    <div className="text-xs text-red-300">
                      <div>
                        Обнаружены проблемы с {health.trades_with_issues || health.issues.length} сделками
                      </div>
                      <div className="text-[10px] text-red-300/70 mt-1">
                        Свяжитесь с поддержкой — мы поможем восстановить данные.
                      </div>
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Actions */}
          <div className="p-3 border-t border-slate-700/50 bg-slate-800/30 flex gap-2">
            <button
              onClick={() => triggerSync(connection.id)}
              disabled={isSyncing}
              className={`
                flex-1 py-2 px-3 rounded-lg text-sm font-medium
                flex items-center justify-center gap-2 transition-all
                ${isSyncing 
                  ? 'bg-blue-500/20 text-blue-400 cursor-wait'
                  : 'bg-accent text-white hover:bg-accent/80'
                }
              `}
            >
              <RefreshCw size={14} className={isSyncing ? 'animate-spin' : ''} />
              {isSyncing ? 'Синхронизация...' : 'Синхр. сейчас'}
            </button>
            
            <button
              onClick={() => {
                setExpanded(false);
                onOpenBrokerModal?.();
              }}
              className="py-2 px-3 rounded-lg text-sm text-slate-400 hover:text-white hover:bg-slate-700 transition-all"
              title="Настройки"
            >
              ⚙️
            </button>
          </div>
        </div>
      )}

      {/* Click outside to close */}
      {expanded && (
        <div 
          className="fixed inset-0 z-[99]" 
          onClick={() => setExpanded(false)}
        />
      )}
    </div>
  );
}
