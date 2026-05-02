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
  const [syncResult, setSyncResult] = useState<{success: boolean; message: string} | null>(null);

  useEffect(() => {
    if (isOpen) {
      fetchConnections();
      // Reset state
      setStep('list');
      setApiToken('');
      setVerifyError('');
      setAvailableAccounts([]);
      setSelectedAccountId('');
      setSyncResult(null);
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
      const data = await api.post<{ success: boolean; message: string }>(
        `/broker/connections/${connectionId}/sync`,
        { params: { force_full_sync: forceFullSync } }
      );
      setSyncResult({ success: data.success, message: data.message });
      
      if (data.success) {
        await fetchConnections();
        onConnectionChange?.();
      }
    } catch {
      setSyncResult({ success: false, message: 'Ошибка синхронизации' });
    } finally {
      setSyncing(null);
    }
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
                      
                      <div className="grid grid-cols-3 gap-2 mb-3 text-xs">
                        <div className="bg-[#0d1117] rounded-lg p-2 text-center">
                          <div className="text-gray-400">Сделок</div>
                          <div className="text-white font-semibold">{conn.total_synced_trades}</div>
                        </div>
                        <div className="bg-[#0d1117] rounded-lg p-2 text-center">
                          <div className="text-gray-400">Статус</div>
                          <div className={`font-semibold ${
                            conn.last_sync_status === 'success' ? 'text-[#00d4aa]' :
                            conn.last_sync_status === 'error' ? 'text-red-400' :
                            'text-yellow-400'
                          }`}>
                            {conn.last_sync_status === 'success' ? '✓ OK' :
                             conn.last_sync_status === 'error' ? '✗ Ошибка' :
                             conn.last_sync_status === 'partial' ? '⚠ Частично' : '—'}
                          </div>
                        </div>
                        <div className="bg-[#0d1117] rounded-lg p-2 text-center">
                          <div className="text-gray-400">Синхр.</div>
                          <div className="text-white font-semibold">
                            {conn.last_sync_at ? 
                              new Date(conn.last_sync_at).toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit' }) :
                              '—'}
                          </div>
                        </div>
                      </div>
                      
                      <div className="flex gap-2">
                        <button
                          onClick={() => syncConnection(conn.id)}
                          disabled={syncing === conn.id}
                          className="flex-1 py-2 px-3 rounded-lg bg-[#00d4aa] text-black font-medium text-sm flex items-center justify-center gap-2 hover:bg-[#00b894] transition-colors disabled:opacity-50"
                        >
                          {syncing === conn.id ? (
                            <Loader2 className="w-4 h-4 animate-spin" />
                          ) : (
                            <RefreshCw className="w-4 h-4" />
                          )}
                          Синхронизировать
                        </button>
                        <button
                          onClick={() => disconnectBroker(conn.id)}
                          className="py-2 px-3 rounded-lg bg-red-500/10 text-red-400 hover:bg-red-500/20 transition-colors"
                        >
                          <Unlink className="w-4 h-4" />
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
              
              {syncResult && (
                <div className={`p-3 rounded-lg ${syncResult.success ? 'bg-[#00d4aa]/10 text-[#00d4aa]' : 'bg-red-500/10 text-red-400'} text-sm`}>
                  {syncResult.message}
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
