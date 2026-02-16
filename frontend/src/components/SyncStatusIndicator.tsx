'use client';

import { useState, useEffect, useCallback } from 'react';
import { 
  RefreshCw, CheckCircle, AlertCircle, Clock, 
  Zap, ChevronDown, ChevronUp, Link2
} from 'lucide-react';
import { api } from '@/lib/apiClient';

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
  const [status, setStatus] = useState<SyncStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState(false);
  const [syncing, setSyncing] = useState<number | null>(null);
  const [countdown, setCountdown] = useState<string>('');

  const fetchStatus = useCallback(async () => {
    try {
      const data = await api.get<SyncStatus>('/broker/sync-status');
      setStatus(data);
    } catch (error) {
      console.error('Failed to fetch sync status:', error);
    } finally {
      setLoading(false);
    }
  }, []);

  // Обновляем статус каждые 30 секунд
  useEffect(() => {
    fetchStatus();
    const interval = setInterval(fetchStatus, 30000);
    return () => clearInterval(interval);
  }, [fetchStatus]);

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
      await api.post(`/broker/trigger-sync/${connectionId}`);
      // Ждём немного и обновляем статус
      setTimeout(() => {
        fetchStatus();
        onTradesUpdated?.();
      }, 2000);
    } catch (error) {
      console.error('Failed to trigger sync:', error);
    } finally {
      setTimeout(() => setSyncing(null), 3000);
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

  // Не показываем если нет подключений
  if (!loading && (!status || !status.has_connections)) {
    return null;
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
                <span className="font-semibold text-white">Auto-Sync</span>
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

            {/* Ошибка если есть */}
            {isError && connection.last_sync_error && (
              <div className="p-2 bg-red-500/10 rounded-lg border border-red-500/20">
                <p className="text-xs text-red-400 line-clamp-2">
                  {connection.last_sync_error}
                </p>
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
