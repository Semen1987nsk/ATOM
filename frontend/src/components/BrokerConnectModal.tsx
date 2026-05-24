'use client';

import { useState, useEffect } from 'react';
import { 
  X, Link2, Unlink, RefreshCw, CheckCircle, AlertCircle, 
  Zap, Shield, ArrowRight, Loader2,
  ChevronDown
} from 'lucide-react';
import { api } from '@/lib/apiClient';

interface BrokerAccount {
  id: string;
  name: string;
  type: string;
  status: string;
  access_level: string;
}

interface BrokerConnection {
  id: number;
  broker: string;
  broker_account_id: string;
  is_active: boolean;
  auto_sync_enabled: boolean;
  sync_interval_minutes: number;
  last_sync_at: string | null;
  last_sync_status: string | null;
  total_synced_trades: number;
  created_at: string;
  // PR 26 Phase 3 — детали последнего sync + реальные counts
  last_sync_operations_count?: number | null;
  last_sync_trades_count?: number | null;
  last_sync_positions_count?: number | null;
  last_sync_duration_ms?: number | null;
  real_trades_count?: number;
  real_operations_count?: number;
}

interface BrokerConnectModalProps {
  isOpen: boolean;
  onClose: () => void;
  onConnectionChange?: () => void;
}

export default function BrokerConnectModal({ isOpen, onClose, onConnectionChange }: BrokerConnectModalProps) {
  // Step state
  const [step, setStep] = useState<'list' | 'connect' | 'verify' | 'configure'>('list');
  
  // Connections
  const [connections, setConnections] = useState<BrokerConnection[]>([]);
  const [loadingConnections, setLoadingConnections] = useState(true);
  
  // Connect form
  const [apiToken, setApiToken] = useState('');
  const [verifying, setVerifying] = useState(false);
  const [verifyError, setVerifyError] = useState('');
  const [availableAccounts, setAvailableAccounts] = useState<BrokerAccount[]>([]);
  const [selectedAccountId, setSelectedAccountId] = useState('');
  
  // Configuration
  const [autoSyncEnabled, setAutoSyncEnabled] = useState(true);
  const [syncInterval, setSyncInterval] = useState(60);
  const [syncFromDate, setSyncFromDate] = useState('');
  const [connecting, setConnecting] = useState(false);
  
  // Sync state
  const [syncing, setSyncing] = useState<number | null>(null);
  const [syncResult, setSyncResult] = useState<{
    success: boolean;
    message: string;
    connectionId?: number;
    operations?: number;
    trades?: number;
    positions?: number;
    durationSec?: number;
    completedAt?: Date;
  } | null>(null);
  // Live elapsed timer while sync is in progress (sec).
  const [syncElapsedSec, setSyncElapsedSec] = useState<number>(0);

  // Tick elapsed timer every second while syncing is non-null.
  useEffect(() => {
    if (syncing === null) {
      setSyncElapsedSec(0);
      return;
    }
    const start = Date.now();
    const timer = setInterval(() => {
      setSyncElapsedSec(Math.floor((Date.now() - start) / 1000));
    }, 1000);
    return () => clearInterval(timer);
  }, [syncing]);

  useEffect(() => {
    if (isOpen) {
      fetchConnections();
      // Reset state — но НЕ сбрасываем syncResult, чтобы юзер видел
      // последний результат если только что нажал sync и закрыл/открыл модал.
      setStep('list');
      setApiToken('');
      setVerifyError('');
      setAvailableAccounts([]);
      setSelectedAccountId('');
    }
  }, [isOpen]);

  const fetchConnections = async () => {
    setLoadingConnections(true);
    try {
      const data = await api.get<BrokerConnection[]>('/broker/connections');
      setConnections(data);
    } catch (error) {
      console.error('Failed to fetch connections:', error);
    } finally {
      setLoadingConnections(false);
    }
  };

  const verifyToken = async () => {
    if (!apiToken.trim()) {
      setVerifyError('Введите токен');
      return;
    }
    
    setVerifying(true);
    setVerifyError('');
    
    try {
      const data = await api.post<{ valid: boolean; accounts?: BrokerAccount[]; error?: string }>('/broker/verify-token', {
        body: { broker: 'tinkoff', api_token: apiToken }
      });
      
      if (data.valid && data.accounts?.length) {
        setAvailableAccounts(data.accounts);
        setSelectedAccountId(data.accounts[0].id);
        setStep('configure');
      } else {
        setVerifyError(data.error || 'Не удалось получить счета');
      }
    } catch {
      setVerifyError('Ошибка соединения с API');
    } finally {
      setVerifying(false);
    }
  };

  const connectBroker = async () => {
    setConnecting(true);
    
    try {
      await api.post('/broker/connect', {
        body: {
          broker: 'tinkoff',
          api_token: apiToken,
          broker_account_id: selectedAccountId,
          auto_sync_enabled: autoSyncEnabled,
          sync_interval_minutes: syncInterval,
          sync_from_date: syncFromDate || null
        }
      });
      await fetchConnections();
      setStep('list');
      onConnectionChange?.();
    } catch (error: unknown) {
      setVerifyError(error instanceof Error ? error.message : 'Ошибка подключения');
    } finally {
      setConnecting(false);
    }
  };

  const syncConnection = async (connectionId: number, forceFullSync = false) => {
    setSyncing(connectionId);
    setSyncResult(null);

    try {
      // PR 12: новый endpoint возвращает rich report.
      const data = await api.post<{
        success: boolean;
        operations_synced: number;
        trades_built: number;
        positions_open: number;
        account_varmargin_total: string;
        duration_sec: number;
        error?: string | null;
      }>(`/broker/connections/${connectionId}/sync`, {
        params: { full: forceFullSync },
      });

      const hasNewData = data.operations_synced > 0 || data.trades_built > 0;
      const message = data.success
        ? (hasNewData
            ? `Готово за ${data.duration_sec}с — добавлено: +${data.operations_synced} операций, +${data.trades_built} сделок, ${data.positions_open} открытых позиций` +
              (parseFloat(data.account_varmargin_total) !== 0
                ? `. Варм-маржа: ${parseFloat(data.account_varmargin_total).toFixed(2)} ₽`
                : '')
            : `Готово за ${data.duration_sec}с — новых сделок нет, всё уже импортировано. Открытых позиций: ${data.positions_open}`)
        : `Ошибка: ${data.error ?? 'неизвестная'}`;
      setSyncResult({
        success: data.success,
        message,
        connectionId,
        operations: data.operations_synced,
        trades: data.trades_built,
        positions: data.positions_open,
        durationSec: data.duration_sec,
        completedAt: new Date(),
      });

      if (data.success) {
        await fetchConnections();
        onConnectionChange?.();
        // PR 26 Phase 3 UX fix: toast НЕ исчезает автоматически — юзер сам
        // решит когда закрыть. Раньше через 8 сек он пропадал и юзер был
        // в недоумении «что произошло».
      }
    } catch (error: unknown) {
      const msg = error instanceof Error ? error.message : 'Ошибка синхронизации';
      setSyncResult({
        success: false,
        message: msg,
        connectionId,
        completedAt: new Date(),
      });
    } finally {
      setSyncing(null);
    }
  };

  // Форматирует «прошло X минут / часов назад» — для last_sync_at.
  const formatRelativeTime = (iso: string): string => {
    const date = new Date(iso);
    const diffMs = Date.now() - date.getTime();
    const diffMin = Math.floor(diffMs / 60000);
    if (diffMin < 1) return 'только что';
    if (diffMin < 60) return `${diffMin} мин назад`;
    const diffH = Math.floor(diffMin / 60);
    if (diffH < 24) return `${diffH} ч назад`;
    const diffD = Math.floor(diffH / 24);
    return `${diffD} дн назад`;
  };

  const formatFullDateTime = (iso: string): string => {
    const date = new Date(iso);
    return date.toLocaleString('ru-RU', {
      day: '2-digit',
      month: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  const disconnectBroker = async (connectionId: number) => {
    if (!confirm('Отключить брокера? Импортированные сделки останутся.')) return;
    
    try {
      await api.delete(`/broker/connections/${connectionId}`);
      await fetchConnections();
      onConnectionChange?.();
    } catch (error) {
      console.error('Failed to disconnect:', error);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black/80 backdrop-blur-sm flex items-center justify-center z-50 p-4">
      <div className="bg-[#0d1117] border border-[#30363d] rounded-xl w-full max-w-xl max-h-[90vh] overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-[#30363d]">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-gradient-to-br from-yellow-400 to-yellow-600 flex items-center justify-center">
              <Zap className="w-5 h-5 text-black" />
            </div>
            <div>
              <h2 className="text-lg font-bold text-white">Авто-синхронизация</h2>
              <p className="text-xs text-gray-400">Автоматический импорт сделок</p>
            </div>
          </div>
          <button onClick={onClose} className="text-gray-400 hover:text-white p-1">
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="overflow-y-auto max-h-[calc(90vh-80px)]">
          {/* Step: List connections */}
          {step === 'list' && (
            <div className="p-4 space-y-4">
              {loadingConnections ? (
                <div className="flex items-center justify-center py-8">
                  <Loader2 className="w-6 h-6 animate-spin text-[#00d4aa]" />
                </div>
              ) : connections.length === 0 ? (
                <div className="text-center py-8">
                  <div className="w-16 h-16 rounded-full bg-[#21262d] flex items-center justify-center mx-auto mb-4">
                    <Link2 className="w-8 h-8 text-gray-500" />
                  </div>
                  <h3 className="text-lg font-semibold text-white mb-2">Нет подключённых брокеров</h3>
                  <p className="text-gray-400 text-sm mb-4">
                    Подключите брокера для автоматического импорта сделок
                  </p>
                </div>
              ) : (
                <div className="space-y-3">
                  {connections.map(conn => (
                    <div key={conn.id} className="bg-[#161b22] border border-[#30363d] rounded-lg p-4">
                      <div className="flex items-start justify-between mb-3">
                        <div className="flex items-center gap-3">
                          <div className="w-10 h-10 rounded-lg bg-yellow-500/20 flex items-center justify-center">
                            <span className="text-xl">🏦</span>
                          </div>
                          <div>
                            <div className="font-semibold text-white">Тинькофф</div>
                            <div className="text-xs text-gray-400">Счёт: {conn.broker_account_id}</div>
                          </div>
                        </div>
                        <div className="flex items-center gap-2">
                          {conn.auto_sync_enabled ? (
                            <span className="px-2 py-0.5 rounded-full bg-[#00d4aa]/20 text-[#00d4aa] text-xs flex items-center gap-1">
                              <Zap className="w-3 h-3" /> Auto
                            </span>
                          ) : (
                            <span className="px-2 py-0.5 rounded-full bg-gray-500/20 text-gray-400 text-xs">
                              Ручной
                            </span>
                          )}
                        </div>
                      </div>
                      
                      {/* PR 26 Phase 3: одна информативная панель вместо 3-х бесполезных кружочков */}
                      <div className="mb-3 bg-[#0d1117] rounded-lg p-3 space-y-2">
                        {/* Строка 1: реальные counts из БД (что у юзера импортировано всего) */}
                        <div className="flex items-center justify-between text-xs">
                          <span className="text-gray-400">В базе сейчас</span>
                          <span className="text-white font-mono">
                            {(conn.real_operations_count ?? 0).toLocaleString('ru-RU')} операций · {(conn.real_trades_count ?? 0).toLocaleString('ru-RU')} сделок
                          </span>
                        </div>

                        {/* Строка 2: последний sync — статус + время */}
                        <div className="flex items-center justify-between text-xs pt-2 border-t border-[#21262d]">
                          <span className="text-gray-400">Последний sync</span>
                          <span className={`font-medium flex items-center gap-1 ${
                            conn.last_sync_status === 'success' ? 'text-[#00d4aa]' :
                            conn.last_sync_status === 'error' ? 'text-red-400' :
                            'text-gray-500'
                          }`}>
                            {conn.last_sync_status === 'success' ? '✓ успех' :
                             conn.last_sync_status === 'error' ? '✗ ошибка' :
                             conn.last_sync_status === 'partial' ? '⚠ частично' : '— ни разу'}
                            {conn.last_sync_at && (
                              <span className="text-gray-500 font-normal ml-1">
                                · {formatFullDateTime(conn.last_sync_at)} ({formatRelativeTime(conn.last_sync_at)})
                              </span>
                            )}
                          </span>
                        </div>

                        {/* Строка 3: ЧТО именно сделал последний sync — это и есть «что произошло» */}
                        {(conn.last_sync_operations_count != null ||
                          conn.last_sync_trades_count != null ||
                          conn.last_sync_positions_count != null) && (
                          <div className="flex items-center justify-between text-xs pt-2 border-t border-[#21262d]">
                            <span className="text-gray-400">В этот sync</span>
                            <span className="text-white font-mono">
                              {`+${conn.last_sync_operations_count ?? 0} op · +${conn.last_sync_trades_count ?? 0} trades · ${conn.last_sync_positions_count ?? 0} open`}
                              {conn.last_sync_duration_ms != null && (
                                <span className="text-gray-500 ml-1">
                                  · {conn.last_sync_duration_ms < 1000
                                      ? `${conn.last_sync_duration_ms}мс`
                                      : `${(conn.last_sync_duration_ms / 1000).toFixed(1)}с`}
                                </span>
                              )}
                            </span>
                          </div>
                        )}
                      </div>

                      {/* Inline sync result — рядом с карточкой, не внизу модала */}
                      {syncResult && syncResult.connectionId === conn.id && (
                        <div className={`mb-3 p-3 rounded-lg border ${
                          syncResult.success
                            ? 'bg-[#00d4aa]/10 border-[#00d4aa]/30 text-[#00d4aa]'
                            : 'bg-red-500/10 border-red-500/30 text-red-400'
                        } text-sm`}>
                          <div className="flex items-start gap-2">
                            {syncResult.success ? (
                              <CheckCircle className="w-4 h-4 mt-0.5 shrink-0" />
                            ) : (
                              <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" />
                            )}
                            <div className="flex-1">
                              <div className="font-medium">{syncResult.message}</div>
                              {syncResult.completedAt && (
                                <div className="text-[11px] opacity-70 mt-1">
                                  Завершено в {syncResult.completedAt.toLocaleTimeString('ru-RU', {
                                    hour: '2-digit',
                                    minute: '2-digit',
                                    second: '2-digit',
                                  })}
                                </div>
                              )}
                            </div>
                            <button
                              onClick={() => setSyncResult(null)}
                              className="opacity-50 hover:opacity-100 shrink-0"
                              aria-label="Скрыть"
                            >
                              <X className="w-3.5 h-3.5" />
                            </button>
                          </div>
                        </div>
                      )}

                      {/* Главная кнопка-действие — состояние зависит от результата */}
                      {syncResult && syncResult.connectionId === conn.id && syncResult.success && syncing !== conn.id ? (
                        /* После успеха: primary CTA = «Закрыть и перейти в журнал»,
                           secondary link = «Синхронизировать снова» */
                        <div className="space-y-2">
                          <button
                            onClick={() => {
                              setSyncResult(null);
                              onClose();
                            }}
                            className="w-full py-2 px-3 rounded-lg bg-[#00d4aa] text-black font-medium text-sm flex items-center justify-center gap-2 hover:bg-[#00b894] transition-colors"
                          >
                            <CheckCircle className="w-4 h-4" />
                            Готово — перейти в журнал
                          </button>
                          <div className="flex gap-2">
                            <button
                              onClick={() => syncConnection(conn.id)}
                              className="flex-1 py-1.5 px-3 rounded-lg border border-[#30363d] text-gray-400 hover:text-white hover:border-[#00d4aa] text-xs flex items-center justify-center gap-2 transition-colors"
                            >
                              <RefreshCw className="w-3 h-3" />
                              Синхронизировать снова
                            </button>
                            <button
                              onClick={() => disconnectBroker(conn.id)}
                              className="py-1.5 px-3 rounded-lg bg-red-500/10 text-red-400 hover:bg-red-500/20 transition-colors text-xs"
                              title="Отключить брокера"
                            >
                              <Unlink className="w-3 h-3" />
                            </button>
                          </div>
                        </div>
                      ) : (
                        /* Обычное состояние: idle или ошибка — primary = «Синхронизировать» */
                        <div className="flex gap-2">
                          <button
                            onClick={() => syncConnection(conn.id)}
                            disabled={syncing === conn.id}
                            className="flex-1 py-2 px-3 rounded-lg bg-[#00d4aa] text-black font-medium text-sm flex items-center justify-center gap-2 hover:bg-[#00b894] transition-colors disabled:opacity-60 disabled:cursor-wait"
                          >
                            {syncing === conn.id ? (
                              <>
                                <Loader2 className="w-4 h-4 animate-spin" />
                                <span>Синхронизация… {syncElapsedSec}с</span>
                              </>
                            ) : (
                              <>
                                <RefreshCw className="w-4 h-4" />
                                <span>Синхронизировать</span>
                              </>
                            )}
                          </button>
                          <button
                            onClick={() => disconnectBroker(conn.id)}
                            disabled={syncing === conn.id}
                            className="py-2 px-3 rounded-lg bg-red-500/10 text-red-400 hover:bg-red-500/20 transition-colors disabled:opacity-30"
                            title="Отключить брокера"
                          >
                            <Unlink className="w-4 h-4" />
                          </button>
                        </div>
                      )}

                      {/* Hint про реальное время ожидания у Tinkoff broker_report */}
                      {syncing === conn.id && syncElapsedSec > 10 && (
                        <div className="mt-2 text-[11px] text-gray-500 text-center">
                          {syncElapsedSec < 30
                            ? 'Загрузка операций…'
                            : syncElapsedSec < 60
                              ? 'Запрос отчёта у Tinkoff (генерируется на стороне брокера)…'
                              : 'Ещё подождите, отчёт занимает до 90 секунд при первом запуске'}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}

              {/* Add broker button */}
              <button
                onClick={() => setStep('connect')}
                className="w-full py-3 px-4 rounded-lg border-2 border-dashed border-[#30363d] hover:border-[#00d4aa] text-gray-400 hover:text-[#00d4aa] transition-colors flex items-center justify-center gap-2"
              >
                <Link2 className="w-5 h-5" />
                Подключить Тинькофф
              </button>
            </div>
          )}

          {/* Step: Enter token */}
          {step === 'connect' && (
            <div className="p-4 space-y-4">
              <button
                onClick={() => setStep('list')}
                className="text-gray-400 hover:text-white text-sm flex items-center gap-1"
              >
                ← Назад
              </button>
              
              <div className="bg-gradient-to-br from-yellow-500/10 to-orange-500/10 border border-yellow-500/20 rounded-lg p-4">
                <div className="flex items-start gap-3">
                  <div className="w-12 h-12 rounded-lg bg-yellow-500 flex items-center justify-center shrink-0">
                    <span className="text-2xl">🏦</span>
                  </div>
                  <div>
                    <h3 className="text-lg font-bold text-white">Тинькофф Инвестиции</h3>
                    <p className="text-sm text-gray-400 mt-1">
                      Автоматический импорт всех сделок через API
                    </p>
                  </div>
                </div>
              </div>

              <div className="space-y-3">
                <div>
                  <label className="block text-sm font-medium text-gray-300 mb-2">
                    API Токен
                  </label>
                  <input
                    type="password"
                    value={apiToken}
                    onChange={(e) => setApiToken(e.target.value)}
                    placeholder="t.xxxxxxxxxxxxx..."
                    className="w-full px-4 py-3 bg-[#161b22] border border-[#30363d] rounded-lg text-white placeholder-gray-500 focus:border-[#00d4aa] focus:ring-1 focus:ring-[#00d4aa] transition-colors"
                  />
                </div>
                
                <div className="bg-[#161b22] border border-[#30363d] rounded-lg p-3 text-sm">
                  <div className="flex items-start gap-2">
                    <Shield className="w-4 h-4 text-[#00d4aa] mt-0.5 shrink-0" />
                    <div className="text-gray-400">
                      <p className="mb-2">Как получить токен:</p>
                      <ol className="list-decimal list-inside space-y-1 text-xs">
                        <li>Откройте <a href="https://www.tinkoff.ru/invest/settings/" target="_blank" rel="noopener" className="text-[#00d4aa] hover:underline">настройки Тинькофф Инвестиций</a></li>
                        <li>Перейдите в раздел &quot;API токены&quot;</li>
                        <li>Создайте токен с правами &quot;Только чтение&quot;</li>
                        <li>Скопируйте токен и вставьте сюда</li>
                      </ol>
                    </div>
                  </div>
                </div>
                
                {verifyError && (
                  <div className="flex items-center gap-2 p-3 bg-red-500/10 border border-red-500/20 rounded-lg text-red-400 text-sm">
                    <AlertCircle className="w-4 h-4 shrink-0" />
                    {verifyError}
                  </div>
                )}
              </div>

              <button
                onClick={verifyToken}
                disabled={verifying || !apiToken.trim()}
                className="w-full py-3 px-4 rounded-lg bg-[#00d4aa] text-black font-semibold flex items-center justify-center gap-2 hover:bg-[#00b894] transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {verifying ? (
                  <Loader2 className="w-5 h-5 animate-spin" />
                ) : (
                  <>
                    Проверить токен
                    <ArrowRight className="w-4 h-4" />
                  </>
                )}
              </button>
            </div>
          )}

          {/* Step: Configure */}
          {step === 'configure' && (
            <div className="p-4 space-y-4">
              <button
                onClick={() => setStep('connect')}
                className="text-gray-400 hover:text-white text-sm flex items-center gap-1"
              >
                ← Назад
              </button>

              <div className="flex items-center gap-2 p-3 bg-[#00d4aa]/10 border border-[#00d4aa]/20 rounded-lg text-[#00d4aa] text-sm">
                <CheckCircle className="w-4 h-4" />
                Токен подтверждён! Выберите счёт и настройки.
              </div>

              {/* Account selection */}
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">
                  Брокерский счёт
                </label>
                <div className="relative">
                  <select
                    value={selectedAccountId}
                    onChange={(e) => setSelectedAccountId(e.target.value)}
                    className="w-full px-4 py-3 bg-[#161b22] border border-[#30363d] rounded-lg text-white appearance-none cursor-pointer focus:border-[#00d4aa]"
                  >
                    {availableAccounts.map(acc => (
                      <option key={acc.id} value={acc.id}>
                        {acc.name} ({acc.type}) — {acc.id}
                      </option>
                    ))}
                  </select>
                  <ChevronDown className="w-4 h-4 absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 pointer-events-none" />
                </div>
                {/* Access level badge для выбранного счёта */}
                {(() => {
                  const acc = availableAccounts.find(a => a.id === selectedAccountId);
                  if (!acc) return null;
                  const isReadOnly = acc.access_level === 'ACCOUNT_ACCESS_LEVEL_READ_ONLY';
                  const isFull = acc.access_level === 'ACCOUNT_ACCESS_LEVEL_FULL_ACCESS';
                  if (isReadOnly) {
                    return (
                      <div className="mt-2 flex items-center gap-2 text-xs text-[#00d4aa]">
                        <Shield className="w-3.5 h-3.5" />
                        Токен read-only — рекомендуемый уровень безопасности
                      </div>
                    );
                  }
                  if (isFull) {
                    return (
                      <div className="mt-2 flex items-center gap-2 text-xs text-amber-400">
                        <AlertCircle className="w-3.5 h-3.5" />
                        У токена есть права на торговлю — мы используем только чтение,
                        но рекомендуем создать read-only токен в Тинькофф
                      </div>
                    );
                  }
                  return (
                    <div className="mt-2 flex items-center gap-2 text-xs text-red-400">
                      <AlertCircle className="w-3.5 h-3.5" />
                      У токена нет прав на чтение этого счёта ({acc.access_level})
                    </div>
                  );
                })()}
              </div>

              {/* Auto-sync toggle */}
              <div className="flex items-center justify-between p-3 bg-[#161b22] border border-[#30363d] rounded-lg">
                <div className="flex items-center gap-3">
                  <Zap className="w-5 h-5 text-yellow-400" />
                  <div>
                    <div className="text-white font-medium">Авто-синхронизация</div>
                    <div className="text-xs text-gray-400">Автоматический импорт новых сделок</div>
                  </div>
                </div>
                <button
                  onClick={() => setAutoSyncEnabled(!autoSyncEnabled)}
                  className={`w-12 h-6 rounded-full transition-colors ${autoSyncEnabled ? 'bg-[#00d4aa]' : 'bg-[#30363d]'}`}
                >
                  <div className={`w-5 h-5 rounded-full bg-white transition-transform ${autoSyncEnabled ? 'translate-x-6' : 'translate-x-0.5'}`} />
                </button>
              </div>

              {autoSyncEnabled && (
                <div>
                  <label className="block text-sm font-medium text-gray-300 mb-2">
                    Интервал синхронизации
                  </label>
                  <div className="grid grid-cols-4 gap-2">
                    {[15, 30, 60, 120].map(mins => (
                      <button
                        key={mins}
                        onClick={() => setSyncInterval(mins)}
                        className={`py-2 px-3 rounded-lg text-sm font-medium transition-colors ${
                          syncInterval === mins 
                            ? 'bg-[#00d4aa] text-black' 
                            : 'bg-[#161b22] border border-[#30363d] text-gray-300 hover:border-[#00d4aa]'
                        }`}
                      >
                        {mins < 60 ? `${mins} мин` : `${mins / 60} ч`}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">
                  Синхронизировать с даты (опционально)
                </label>
                <input
                  type="date"
                  value={syncFromDate}
                  onChange={(e) => setSyncFromDate(e.target.value)}
                  className="w-full px-4 py-3 bg-[#161b22] border border-[#30363d] rounded-lg text-white focus:border-[#00d4aa]"
                />
                <p className="text-xs text-gray-500 mt-1">
                  Если не указано — последние 30 дней
                </p>
              </div>

              {verifyError && (
                <div className="flex items-center gap-2 p-3 bg-red-500/10 border border-red-500/20 rounded-lg text-red-400 text-sm">
                  <AlertCircle className="w-4 h-4 shrink-0" />
                  {verifyError}
                </div>
              )}

              <button
                onClick={connectBroker}
                disabled={connecting}
                className="w-full py-3 px-4 rounded-lg bg-gradient-to-r from-[#00d4aa] to-[#00b894] text-black font-semibold flex items-center justify-center gap-2 hover:opacity-90 transition-opacity disabled:opacity-50"
              >
                {connecting ? (
                  <Loader2 className="w-5 h-5 animate-spin" />
                ) : (
                  <>
                    <Link2 className="w-5 h-5" />
                    Подключить и синхронизировать
                  </>
                )}
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
