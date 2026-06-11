'use client';

import React, { useState, useCallback, useMemo } from 'react';
import { X, Upload, AlertTriangle, Check, FileSpreadsheet, Filter, ArrowDown, ArrowUp } from 'lucide-react';
import { useAuth } from '@/contexts/AuthContext';
import { api } from '@/lib/apiClient';

interface PreviewTrade {
  index: number;
  symbol: string;
  asset_name: string;
  direction: string;
  entry_at: string | null;
  exit_at: string | null;
  entry_price: number | null;
  exit_price: number | null;
  quantity: number | null;
  pnl: number | null;
  net_pnl: number | null;
  is_duplicate: boolean;
  existing_id: number | null;
  is_open: boolean;
}

interface BalanceInfo {
  initial_balance: number | null;
  final_balance: number | null;
  deposits: number | null;
  withdrawals: number | null;
  currency: string;
  period_start: string | null;
  period_end: string | null;
}

interface PreviewResponse {
  filename: string;
  total_trades: number;
  new_trades: number;
  duplicates: number;
  open_trades: number;
  trades: PreviewTrade[];
  date_range: {
    first: string | null;
    last: string | null;
  };
  balance_info: BalanceInfo;
}

interface ImportPreviewModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess: () => void;
}

export const ImportPreviewModal: React.FC<ImportPreviewModalProps> = ({ isOpen, onClose, onSuccess }) => {
  const { isAuthenticated } = useAuth();
  
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<PreviewResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [importing, setImporting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [progress, setProgress] = useState(0); // Прогресс 0-100
  const [progressText, setProgressText] = useState('');
  
  // Диапазон выбора
  const [startIndex, setStartIndex] = useState<number>(0);
  const [endIndex, setEndIndex] = useState<number>(0);
  const [skipDuplicates, setSkipDuplicates] = useState(true);
  const [showOnlyNew, setShowOnlyNew] = useState(false);
  
  // Сохранение баланса
  const [saveBalance, setSaveBalance] = useState(true);
  const [manualBalance, setManualBalance] = useState<number | null>(null);

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const selectedFile = e.target.files?.[0];
    if (selectedFile) {
      setFile(selectedFile);
      setPreview(null);
      setError(null);
    }
  };

  const handlePreview = async () => {
    if (!file) return;
    
    if (!isAuthenticated) {
      setError('Необходимо войти в аккаунт для импорта сделок');
      return;
    }
    
    setLoading(true);
    setError(null);
    setProgress(0);
    setProgressText('Загрузка файла...');
    
    try {
      const formData = new FormData();
      formData.append('file', file);
      
      // Симуляция прогресса для UX (реальный прогресс сложно отследить)
      const progressInterval = setInterval(() => {
        setProgress(prev => Math.min(prev + 15, 85));
      }, 200);
      
      setProgressText('Парсинг сделок...');
      
      const data = await api.upload<PreviewResponse>('/trades/import/preview', formData);
      
      clearInterval(progressInterval);
      setProgress(90);
      setProgressText('Проверка дубликатов...');
      
      setProgress(100);
      setProgressText('Готово!');
      
      setTimeout(() => {
        setPreview(data);
        setStartIndex(0);
        setEndIndex(data.trades.length - 1);
        setProgress(0);
      }, 300);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Неизвестная ошибка');
      setProgress(0);
    } finally {
      setLoading(false);
    }
  };

  const handleImport = async () => {
    if (!file || !preview) return;
    
    setImporting(true);
    setError(null);
    setProgress(0);
    setProgressText('Подготовка к импорту...');
    
    try {
      const formData = new FormData();
      formData.append('file', file);
      formData.append('start_index', startIndex.toString());
      formData.append('end_index', endIndex.toString());
      formData.append('skip_duplicates', skipDuplicates.toString());
      
      // Отправляем баланс если выбрано
      if (saveBalance) {
        // Приоритет: автоматический баланс > ручной ввод
        const initialBal = preview.balance_info?.initial_balance ?? manualBalance;
        if (initialBal !== null) {
          formData.append('initial_balance', initialBal.toString());
        }
        if (preview.balance_info?.final_balance !== null) {
          formData.append('final_balance', preview.balance_info.final_balance.toString());
        }
        // Если есть период — отправляем, иначе используем дату первой сделки
        if (preview.balance_info?.period_start) {
          formData.append('balance_date_start', preview.balance_info.period_start);
        } else if (preview.date_range.first) {
          formData.append('balance_date_start', preview.date_range.first);
        }
        if (preview.balance_info?.period_end) {
          formData.append('balance_date_end', preview.balance_info.period_end);
        } else if (preview.date_range.last) {
          formData.append('balance_date_end', preview.date_range.last);
        }
      }
      
      // Симуляция прогресса импорта
      const totalTrades = endIndex - startIndex + 1;
      let currentProgress = 0;
      const progressInterval = setInterval(() => {
        currentProgress += 5;
        const displayProgress = Math.min(currentProgress, 90);
        setProgress(displayProgress);
        const estimatedTrades = Math.floor((displayProgress / 100) * totalTrades);
        setProgressText(`Импорт сделок: ${estimatedTrades}/${totalTrades}`);
      }, 150);
      
      const result = await api.upload<{ imported: number; message: string }>('/trades/import', formData);
      
      clearInterval(progressInterval);
      setProgress(95);
      setProgressText('Сохранение в базу данных...');
      
      setProgress(100);
      setProgressText(`✅ Импортировано: ${result.imported}`);
      
      setTimeout(() => {
        alert(`✅ ${result.message}`);
        onSuccess();
        handleClose();
      }, 500);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Неизвестная ошибка');
      setProgress(0);
    } finally {
      setImporting(false);
    }
  };

  const handleClose = useCallback(() => {
    setFile(null);
    setPreview(null);
    setError(null);
    setStartIndex(0);
    setEndIndex(0);
    setProgress(0);
    setProgressText('');
    setManualBalance(null);
    setSaveBalance(true);
    onClose();
  }, [onClose]);

  // Фильтрованный список сделок
  const displayedTrades = useMemo(() => {
    if (!preview) return [];
    let trades = preview.trades;
    if (showOnlyNew) {
      trades = trades.filter(t => !t.is_duplicate);
    }
    return trades;
  }, [preview, showOnlyNew]);

  // Статистика выбранного диапазона
  const selectionStats = useMemo(() => {
    if (!preview) return null;
    const selected = preview.trades.slice(startIndex, endIndex + 1);
    const duplicates = selected.filter(t => t.is_duplicate).length;
    const newTrades = selected.length - duplicates;
    const openTrades = selected.filter(t => t.is_open).length;
    return { total: selected.length, newTrades, duplicates, openTrades };
  }, [preview, startIndex, endIndex]);

  const formatDate = (dateStr: string | null) => {
    if (!dateStr) return '-';
    try {
      return new Date(dateStr).toLocaleString('ru-RU', {
        day: '2-digit',
        month: '2-digit',
        year: '2-digit',
        hour: '2-digit',
        minute: '2-digit'
      });
    } catch {
      return dateStr;
    }
  };

  const formatPrice = (price: number | null) => {
    if (price === null || price === undefined) return '-';
    return price.toLocaleString('ru-RU', { maximumFractionDigits: 2 });
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-slate-800 rounded-xl w-full max-w-6xl max-h-[90vh] flex flex-col shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-slate-700">
          <div className="flex items-center gap-3">
            <FileSpreadsheet className="w-6 h-6 text-indigo-400" />
            <h2 className="text-xl font-semibold text-[var(--foreground)]">Импорт сделок</h2>
          </div>
          <button 
            onClick={handleClose}
            className="p-2 hover:bg-slate-700 rounded-lg transition-colors"
          >
            <X className="w-5 h-5 text-slate-400" />
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-auto p-4 space-y-4">
          {/* File Upload */}
          <div className="flex items-center gap-4">
            <div className="flex-1 flex items-center gap-3">
              <input 
                type="file" 
                id="file-upload"
                accept=".xlsx,.xls,.csv"
                onChange={handleFileSelect}
                className="hidden"
              />
              <button
                type="button"
                onClick={() => document.getElementById('file-upload')?.click()}
                className="flex-1 flex items-center justify-center gap-3 p-4 border-2 border-dashed border-slate-600 rounded-xl hover:border-indigo-500 cursor-pointer transition-colors bg-slate-800/50"
              >
                <Upload className="w-6 h-6 text-slate-400" />
                <span className="text-slate-300">
                  {file ? file.name : 'Выберите файл (Excel или CSV)'}
                </span>
              </button>
            </div>
            
            <button
              onClick={handlePreview}
              disabled={!file || loading}
              className="px-6 py-3 bg-indigo-600 text-white rounded-xl hover:bg-indigo-500 disabled:opacity-50 disabled:cursor-not-allowed transition-colors font-medium"
            >
              {loading ? 'Загрузка...' : 'Предпросмотр'}
            </button>
          </div>

          {/* Error */}
          {error && (
            <div className="flex items-center gap-3 p-4 bg-red-500/10 border border-red-500/30 rounded-xl text-red-400">
              <AlertTriangle className="w-5 h-5 flex-shrink-0" />
              <span>{error}</span>
            </div>
          )}

          {/* Progress Bar */}
          {(loading || importing) && progress > 0 && (
            <div className="space-y-2">
              <div className="flex justify-between text-sm">
                <span className="text-slate-300">{progressText}</span>
                <span className="text-indigo-400 font-medium">{progress}%</span>
              </div>
              <div className="w-full bg-slate-700 rounded-full h-3 overflow-hidden">
                <div 
                  className="bg-gradient-to-r from-indigo-500 to-purple-500 h-full rounded-full transition-all duration-300 ease-out"
                  style={{ width: `${progress}%` }}
                />
              </div>
            </div>
          )}

          {/* Preview Stats */}
          {preview && (
            <>
              <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
                <div className="bg-slate-700/50 rounded-xl p-4">
                  <div className="text-2xl font-bold text-[var(--foreground)]">{preview.total_trades}</div>
                  <div className="text-sm text-slate-400">Всего в файле</div>
                </div>
                <div className="bg-green-500/10 border border-green-500/30 rounded-xl p-4">
                  <div className="text-2xl font-bold text-green-400">{preview.new_trades}</div>
                  <div className="text-sm text-slate-400">Новых</div>
                </div>
                <div className="bg-yellow-500/10 border border-yellow-500/30 rounded-xl p-4">
                  <div className="text-2xl font-bold text-yellow-400">{preview.duplicates}</div>
                  <div className="text-sm text-slate-400">Дубликатов</div>
                </div>
                <div className="bg-blue-500/10 border border-blue-500/30 rounded-xl p-4">
                  <div className="text-2xl font-bold text-blue-400">{preview.open_trades}</div>
                  <div className="text-sm text-slate-400">Открытых</div>
                </div>
                <div className="bg-slate-700/50 rounded-xl p-4">
                  <div className="text-sm font-medium text-[var(--foreground)] truncate">
                    {formatDate(preview.date_range.first)} 
                  </div>
                  <div className="text-sm font-medium text-[var(--foreground)] truncate mt-1">
                    — {formatDate(preview.date_range.last)}
                  </div>
                  <div className="text-sm text-slate-400">Период</div>
                </div>
              </div>

              {/* Range Selection */}
              <div className="bg-slate-700/30 rounded-xl p-4 space-y-4">
                <h3 className="font-medium text-[var(--foreground)] flex items-center gap-2">
                  <Filter className="w-4 h-4" />
                  Выбор диапазона импорта
                </h3>
                
              {/* Balance Info - показываем всегда с возможностью ручного ввода */}
              <div className="bg-indigo-500/10 border border-indigo-500/30 rounded-xl p-4 mt-4">
                <div className="flex items-center justify-between mb-3">
                  <h4 className="font-medium text-indigo-300">💰 Начальный баланс счёта</h4>
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input 
                      type="checkbox"
                      checked={saveBalance}
                      onChange={(e) => setSaveBalance(e.target.checked)}
                      className="w-4 h-4 rounded border-indigo-500 text-indigo-600 focus:ring-indigo-500 bg-slate-700"
                    />
                    <span className="text-sm text-indigo-300">Сохранить баланс</span>
                  </label>
                </div>
                
                {/* Если баланс найден автоматически */}
                {(preview.balance_info.initial_balance !== null || preview.balance_info.final_balance !== null) ? (
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
                    {preview.balance_info.initial_balance !== null && (
                      <div className={saveBalance ? '' : 'opacity-50'}>
                        <span className="text-slate-400">Начальный:</span>
                        <div className="text-[var(--foreground)] font-medium">
                          {preview.balance_info.initial_balance.toLocaleString('ru-RU')} {preview.balance_info.currency}
                        </div>
                      </div>
                    )}
                    {preview.balance_info.final_balance !== null && (
                      <div className={saveBalance ? '' : 'opacity-50'}>
                        <span className="text-slate-400">Конечный:</span>
                        <div className="text-[var(--foreground)] font-medium">
                          {preview.balance_info.final_balance.toLocaleString('ru-RU')} {preview.balance_info.currency}
                        </div>
                      </div>
                    )}
                    {preview.balance_info.deposits !== null && preview.balance_info.deposits > 0 && (
                      <div className={saveBalance ? '' : 'opacity-50'}>
                        <span className="text-slate-400">Пополнения:</span>
                        <div className="text-green-400 font-medium">
                          +{preview.balance_info.deposits.toLocaleString('ru-RU')} {preview.balance_info.currency}
                        </div>
                      </div>
                    )}
                    {preview.balance_info.withdrawals !== null && preview.balance_info.withdrawals > 0 && (
                      <div className={saveBalance ? '' : 'opacity-50'}>
                        <span className="text-slate-400">Выводы:</span>
                        <div className="text-red-400 font-medium">
                          -{preview.balance_info.withdrawals.toLocaleString('ru-RU')} {preview.balance_info.currency}
                        </div>
                      </div>
                    )}
                  </div>
                ) : (
                  /* Ручной ввод если баланс не найден */
                  <div className="space-y-3">
                    <div className="text-sm text-slate-400 mb-2">
                      Баланс не найден в файле. Введите начальный баланс вручную:
                    </div>
                    <div className="flex items-center gap-3">
                      <div className="flex-1">
                        <label className="block text-xs text-slate-500 mb-1">Баланс до первой сделки</label>
                        <input
                          type="number"
                          placeholder="Например: 500000"
                          value={manualBalance || ''}
                          onChange={(e) => setManualBalance(e.target.value ? parseFloat(e.target.value) : null)}
                          className="w-full p-2 bg-[var(--input-bg)] border border-[var(--border)] rounded-lg text-[var(--foreground)] placeholder-slate-500"
                          disabled={!saveBalance}
                        />
                      </div>
                      <div className="text-slate-400 pt-5">₽</div>
                    </div>
                  </div>
                )}
                
                {preview.balance_info.period_start && preview.balance_info.period_end && (
                  <div className="mt-2 text-xs text-slate-500">
                    Период: {formatDate(preview.balance_info.period_start)} — {formatDate(preview.balance_info.period_end)}
                  </div>
                )}
                {saveBalance && (preview.balance_info.initial_balance !== null || manualBalance) && (
                  <div className="mt-3 p-2 bg-green-500/10 border border-green-500/20 rounded text-xs text-green-400">
                    ✓ Баланс будет сохранён для расчёта исторической базы и ROI
                  </div>
                )}
              </div>
                
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  <div>
                    <label className="block text-sm text-slate-400 mb-1">С позиции</label>
                    <select 
                      value={startIndex}
                      onChange={(e) => setStartIndex(Number(e.target.value))}
                      className="w-full p-2 bg-[var(--input-bg)] border border-[var(--border)] rounded-lg text-[var(--foreground)]"
                    >
                      {preview.trades.map((t, idx) => (
                        <option key={idx} value={idx} disabled={idx > endIndex}>
                          #{idx + 1}: {t.symbol} {formatDate(t.entry_at)}
                        </option>
                      ))}
                    </select>
                  </div>
                  
                  <div>
                    <label className="block text-sm text-slate-400 mb-1">До позиции</label>
                    <select 
                      value={endIndex}
                      onChange={(e) => setEndIndex(Number(e.target.value))}
                      className="w-full p-2 bg-[var(--input-bg)] border border-[var(--border)] rounded-lg text-[var(--foreground)]"
                    >
                      {preview.trades.map((t, idx) => (
                        <option key={idx} value={idx} disabled={idx < startIndex}>
                          #{idx + 1}: {t.symbol} {formatDate(t.entry_at)}
                        </option>
                      ))}
                    </select>
                  </div>
                  
                  <div className="flex items-end gap-4">
                    <label className="flex items-center gap-2 cursor-pointer">
                      <input 
                        type="checkbox"
                        checked={skipDuplicates}
                        onChange={(e) => setSkipDuplicates(e.target.checked)}
                        className="w-4 h-4 rounded border-slate-600 text-indigo-600 focus:ring-indigo-500"
                      />
                      <span className="text-sm text-slate-300">Пропускать дубликаты</span>
                    </label>
                    
                    <label className="flex items-center gap-2 cursor-pointer">
                      <input 
                        type="checkbox"
                        checked={showOnlyNew}
                        onChange={(e) => setShowOnlyNew(e.target.checked)}
                        className="w-4 h-4 rounded border-slate-600 text-indigo-600 focus:ring-indigo-500"
                      />
                      <span className="text-sm text-slate-300">Только новые</span>
                    </label>
                  </div>
                </div>

                {/* Selection stats */}
                {selectionStats && (
                  <div className="text-sm text-slate-400 pt-2 border-t border-slate-600">
                    Выбрано: <span className="text-[var(--foreground)] font-medium">{selectionStats.total}</span> сделок
                    {' '}(новых: <span className="text-green-400">{selectionStats.newTrades}</span>,
                    дубликатов: <span className="text-yellow-400">{selectionStats.duplicates}</span>,
                    открытых: <span className="text-blue-400">{selectionStats.openTrades}</span>)
                  </div>
                )}
              </div>

              {/* Trades Table */}
              <div className="overflow-auto max-h-80 rounded-xl border border-slate-700">
                <table className="w-full text-sm">
                  <thead className="bg-slate-700 sticky top-0">
                    <tr>
                      <th className="text-left p-3 text-slate-300 font-medium">#</th>
                      <th className="text-left p-3 text-slate-300 font-medium">Статус</th>
                      <th className="text-left p-3 text-slate-300 font-medium">Тикер</th>
                      <th className="text-left p-3 text-slate-300 font-medium">Напр.</th>
                      <th className="text-left p-3 text-slate-300 font-medium">Вход</th>
                      <th className="text-left p-3 text-slate-300 font-medium">Выход</th>
                      <th className="text-right p-3 text-slate-300 font-medium">Цена входа</th>
                      <th className="text-right p-3 text-slate-300 font-medium">Цена выхода</th>
                      <th className="text-right p-3 text-slate-300 font-medium">Кол-во</th>
                      <th className="text-right p-3 text-slate-300 font-medium">P&L</th>
                    </tr>
                  </thead>
                  <tbody>
                    {displayedTrades.map((trade) => {
                      const inRange = trade.index >= startIndex && trade.index <= endIndex;
                      const rowClass = trade.is_duplicate 
                        ? 'bg-yellow-500/5 text-slate-500'
                        : inRange 
                          ? 'bg-slate-800/50' 
                          : 'bg-slate-800/20 text-slate-500';
                      
                      return (
                        <tr key={trade.index} className={`${rowClass} border-b border-slate-700/50 hover:bg-slate-700/30`}>
                          <td className="p-3">
                            <span className={inRange ? 'text-[var(--foreground)]' : 'text-slate-500'}>
                              {trade.index + 1}
                            </span>
                          </td>
                          <td className="p-3">
                            {trade.is_duplicate ? (
                              <span className="inline-flex items-center gap-1 px-2 py-1 bg-yellow-500/20 text-yellow-400 rounded text-xs">
                                <AlertTriangle className="w-3 h-3" />
                                Дубликат
                              </span>
                            ) : trade.is_open ? (
                              <span className="inline-flex items-center gap-1 px-2 py-1 bg-blue-500/20 text-blue-400 rounded text-xs">
                                Открыта
                              </span>
                            ) : (
                              <span className="inline-flex items-center gap-1 px-2 py-1 bg-green-500/20 text-green-400 rounded text-xs">
                                <Check className="w-3 h-3" />
                                Новая
                              </span>
                            )}
                          </td>
                          <td className="p-3 font-medium">{trade.symbol}</td>
                          <td className="p-3">
                            <span className={`inline-flex items-center gap-1 ${trade.direction === 'long' ? 'text-green-400' : 'text-red-400'}`}>
                              {trade.direction === 'long' ? <ArrowUp className="w-3 h-3" /> : <ArrowDown className="w-3 h-3" />}
                              {trade.direction}
                            </span>
                          </td>
                          <td className="p-3">{formatDate(trade.entry_at)}</td>
                          <td className="p-3">{formatDate(trade.exit_at)}</td>
                          <td className="p-3 text-right font-mono">{formatPrice(trade.entry_price)}</td>
                          <td className="p-3 text-right font-mono">{formatPrice(trade.exit_price)}</td>
                          <td className="p-3 text-right font-mono">{trade.quantity ?? '-'}</td>
                          <td className={`p-3 text-right font-mono font-medium ${
                            trade.pnl !== null && trade.pnl > 0 ? 'text-green-400' : 
                            trade.pnl !== null && trade.pnl < 0 ? 'text-red-400' : ''
                          }`}>
                            {trade.pnl !== null ? formatPrice(trade.pnl) : '-'}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between p-4 border-t border-slate-700 bg-slate-800/50">
          <div className="text-sm text-slate-400">
            {preview && selectionStats && (
              <>
                Будет импортировано: <span className="text-[var(--foreground)] font-medium">
                  {skipDuplicates ? selectionStats.newTrades : selectionStats.total}
                </span> сделок
              </>
            )}
          </div>
          <div className="flex gap-3">
            <button
              onClick={handleClose}
              className="px-4 py-2 text-slate-400 hover:text-white transition-colors"
            >
              Отмена
            </button>
            <button
              onClick={handleImport}
              disabled={!preview || importing || (skipDuplicates && selectionStats?.newTrades === 0)}
              className="px-6 py-2 bg-green-600 text-white rounded-lg hover:bg-green-500 disabled:opacity-50 disabled:cursor-not-allowed transition-colors font-medium"
            >
              {importing ? 'Импорт...' : 'Импортировать'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default ImportPreviewModal;
