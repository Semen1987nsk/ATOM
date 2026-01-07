'use client';

import React, { useState, useEffect, useCallback } from 'react';
import { X, Plus, Minus, Wallet, TrendingUp, Calendar, Trash2, Edit2, DollarSign } from 'lucide-react';

interface DepositOperation {
  id: number;
  operation_type: string;
  amount: number;
  balance_after: number;
  date: string;
  note: string | null;
}

interface BalanceInfo {
  account_id: number;
  initial_balance: number;
  current_balance: number;
  total_deposits: number;
  total_withdrawals: number;
  total_pnl: number;
  currency: string;
}

interface DepositManagerModalProps {
  isOpen: boolean;
  onClose: () => void;
  onUpdate?: () => void;
}

export const DepositManagerModal: React.FC<DepositManagerModalProps> = ({ isOpen, onClose, onUpdate }) => {
  const [balance, setBalance] = useState<BalanceInfo | null>(null);
  const [history, setHistory] = useState<DepositOperation[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  
  // Форма добавления операции
  const [showForm, setShowForm] = useState(false);
  const [formType, setFormType] = useState<'initial' | 'deposit' | 'withdrawal'>('deposit');
  const [formAmount, setFormAmount] = useState('');
  const [formDate, setFormDate] = useState(new Date().toISOString().slice(0, 10));
  const [formNote, setFormNote] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const getApiUrl = (path: string) => {
    if (typeof window !== 'undefined' && window.location.hostname.includes('github.dev')) {
      const codespaceName = window.location.hostname.split('-3000')[0];
      return `https://${codespaceName}-8000.app.github.dev${path}`;
    }
    return `http://localhost:8000${path}`;
  };

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const [balanceRes, historyRes] = await Promise.all([
        fetch(getApiUrl('/deposits/balance')),
        fetch(getApiUrl('/deposits/history'))
      ]);
      
      if (balanceRes.ok) {
        setBalance(await balanceRes.json());
      }
      if (historyRes.ok) {
        setHistory(await historyRes.json());
      }
    } catch (err) {
      setError('Ошибка загрузки данных');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (isOpen) {
      fetchData();
    }
  }, [isOpen, fetchData]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!formAmount) return;
    
    setSubmitting(true);
    setError(null);
    
    try {
      let url = '';
      const params = new URLSearchParams();
      params.append('amount', formAmount);
      params.append('date', new Date(formDate).toISOString());
      if (formNote) params.append('note', formNote);
      
      if (formType === 'initial') {
        url = getApiUrl(`/deposits/initial?${params.toString()}`);
      } else if (formType === 'deposit') {
        url = getApiUrl(`/deposits/add?${params.toString()}`);
      } else {
        url = getApiUrl(`/deposits/withdraw?${params.toString()}`);
      }
      
      const response = await fetch(url, { method: 'POST' });
      
      if (!response.ok) {
        const err = await response.json();
        throw new Error(err.detail || 'Ошибка');
      }
      
      // Сбрасываем форму
      setFormAmount('');
      setFormNote('');
      setShowForm(false);
      
      // Обновляем данные
      await fetchData();
      onUpdate?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Неизвестная ошибка');
    } finally {
      setSubmitting(false);
    }
  };

  const handleDelete = async (id: number) => {
    if (!confirm('Удалить эту операцию?')) return;
    
    try {
      const response = await fetch(getApiUrl(`/deposits/${id}`), { method: 'DELETE' });
      if (response.ok) {
        await fetchData();
        onUpdate?.();
      }
    } catch (err) {
      setError('Ошибка при удалении');
    }
  };

  const formatCurrency = (amount: number) => {
    return new Intl.NumberFormat('ru-RU', {
      style: 'currency',
      currency: balance?.currency || 'RUB',
      minimumFractionDigits: 0,
      maximumFractionDigits: 0
    }).format(amount);
  };

  const formatDate = (dateStr: string) => {
    return new Date(dateStr).toLocaleDateString('ru-RU', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric'
    });
  };

  const getOperationLabel = (type: string) => {
    switch (type) {
      case 'initial': return 'Начальный депозит';
      case 'deposit': return 'Пополнение';
      case 'withdrawal': return 'Снятие';
      default: return type;
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-slate-800 rounded-xl w-full max-w-2xl max-h-[90vh] flex flex-col shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-slate-700">
          <div className="flex items-center gap-3">
            <Wallet className="w-6 h-6 text-green-400" />
            <h2 className="text-xl font-semibold text-white">Управление депозитом</h2>
          </div>
          <button 
            onClick={onClose}
            className="p-2 hover:bg-slate-700 rounded-lg transition-colors"
          >
            <X className="w-5 h-5 text-slate-400" />
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-auto p-4 space-y-4">
          {loading ? (
            <div className="text-center py-8 text-slate-400">Загрузка...</div>
          ) : (
            <>
              {/* Balance Cards */}
              {balance && (
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                  <div className="bg-slate-700/50 rounded-xl p-4">
                    <div className="text-sm text-slate-400 mb-1">Начальный</div>
                    <div className="text-lg font-bold text-white">
                      {formatCurrency(balance.initial_balance)}
                    </div>
                  </div>
                  <div className="bg-green-500/10 border border-green-500/30 rounded-xl p-4">
                    <div className="text-sm text-slate-400 mb-1">Текущий баланс</div>
                    <div className="text-lg font-bold text-green-400">
                      {formatCurrency(balance.current_balance)}
                    </div>
                  </div>
                  <div className="bg-blue-500/10 border border-blue-500/30 rounded-xl p-4">
                    <div className="text-sm text-slate-400 mb-1">Внесено</div>
                    <div className="text-lg font-bold text-blue-400">
                      +{formatCurrency(balance.total_deposits)}
                    </div>
                  </div>
                  <div className={`${balance.total_pnl >= 0 ? 'bg-green-500/10 border-green-500/30' : 'bg-red-500/10 border-red-500/30'} border rounded-xl p-4`}>
                    <div className="text-sm text-slate-400 mb-1">Прибыль</div>
                    <div className={`text-lg font-bold ${balance.total_pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                      {balance.total_pnl >= 0 ? '+' : ''}{formatCurrency(balance.total_pnl)}
                    </div>
                  </div>
                </div>
              )}

              {/* Error */}
              {error && (
                <div className="p-3 bg-red-500/10 border border-red-500/30 rounded-lg text-red-400 text-sm">
                  {error}
                </div>
              )}

              {/* Add Button */}
              {!showForm && (
                <div className="flex gap-2">
                  <button
                    onClick={() => { setFormType('initial'); setShowForm(true); }}
                    className="flex-1 flex items-center justify-center gap-2 p-3 bg-slate-700 hover:bg-slate-600 rounded-xl transition-colors text-slate-300"
                  >
                    <DollarSign className="w-4 h-4" />
                    Начальный депозит
                  </button>
                  <button
                    onClick={() => { setFormType('deposit'); setShowForm(true); }}
                    className="flex-1 flex items-center justify-center gap-2 p-3 bg-green-600 hover:bg-green-500 rounded-xl transition-colors text-white"
                  >
                    <Plus className="w-4 h-4" />
                    Пополнение
                  </button>
                  <button
                    onClick={() => { setFormType('withdrawal'); setShowForm(true); }}
                    className="flex-1 flex items-center justify-center gap-2 p-3 bg-red-600 hover:bg-red-500 rounded-xl transition-colors text-white"
                  >
                    <Minus className="w-4 h-4" />
                    Снятие
                  </button>
                </div>
              )}

              {/* Add Form */}
              {showForm && (
                <form onSubmit={handleSubmit} className="bg-slate-700/50 rounded-xl p-4 space-y-3">
                  <div className="flex items-center justify-between mb-2">
                    <h3 className="font-medium text-white">
                      {formType === 'initial' && '💰 Начальный депозит'}
                      {formType === 'deposit' && '➕ Пополнение'}
                      {formType === 'withdrawal' && '➖ Снятие'}
                    </h3>
                    <button
                      type="button"
                      onClick={() => setShowForm(false)}
                      className="text-slate-400 hover:text-white"
                    >
                      <X className="w-4 h-4" />
                    </button>
                  </div>
                  
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="block text-sm text-slate-400 mb-1">Сумма</label>
                      <input
                        type="number"
                        value={formAmount}
                        onChange={(e) => setFormAmount(e.target.value)}
                        placeholder="100000"
                        className="w-full p-2 bg-slate-800 border border-slate-600 rounded-lg text-white"
                        required
                        min="0"
                        step="0.01"
                      />
                    </div>
                    <div>
                      <label className="block text-sm text-slate-400 mb-1">Дата</label>
                      <input
                        type="date"
                        value={formDate}
                        onChange={(e) => setFormDate(e.target.value)}
                        className="w-full p-2 bg-slate-800 border border-slate-600 rounded-lg text-white"
                        required
                      />
                    </div>
                  </div>
                  
                  <div>
                    <label className="block text-sm text-slate-400 mb-1">Комментарий (опционально)</label>
                    <input
                      type="text"
                      value={formNote}
                      onChange={(e) => setFormNote(e.target.value)}
                      placeholder="Например: Пополнение с зарплаты"
                      className="w-full p-2 bg-slate-800 border border-slate-600 rounded-lg text-white"
                    />
                  </div>
                  
                  <button
                    type="submit"
                    disabled={submitting || !formAmount}
                    className={`w-full py-2 rounded-lg font-medium transition-colors ${
                      formType === 'withdrawal' 
                        ? 'bg-red-600 hover:bg-red-500 text-white'
                        : 'bg-green-600 hover:bg-green-500 text-white'
                    } disabled:opacity-50`}
                  >
                    {submitting ? 'Сохранение...' : 'Сохранить'}
                  </button>
                </form>
              )}

              {/* History */}
              <div className="space-y-2">
                <h3 className="font-medium text-slate-300 flex items-center gap-2">
                  <Calendar className="w-4 h-4" />
                  История операций
                </h3>
                
                {history.length === 0 ? (
                  <div className="text-center py-6 text-slate-500">
                    Нет операций. Добавьте начальный депозит.
                  </div>
                ) : (
                  <div className="space-y-2 max-h-64 overflow-auto">
                    {history.map((op) => (
                      <div 
                        key={op.id}
                        className="flex items-center justify-between p-3 bg-slate-700/30 rounded-lg hover:bg-slate-700/50 transition-colors"
                      >
                        <div className="flex items-center gap-3">
                          <div className={`w-8 h-8 rounded-full flex items-center justify-center ${
                            op.operation_type === 'initial' ? 'bg-blue-500/20 text-blue-400' :
                            op.operation_type === 'deposit' ? 'bg-green-500/20 text-green-400' :
                            'bg-red-500/20 text-red-400'
                          }`}>
                            {op.operation_type === 'initial' && <DollarSign className="w-4 h-4" />}
                            {op.operation_type === 'deposit' && <Plus className="w-4 h-4" />}
                            {op.operation_type === 'withdrawal' && <Minus className="w-4 h-4" />}
                          </div>
                          <div>
                            <div className="text-sm text-white">{getOperationLabel(op.operation_type)}</div>
                            <div className="text-xs text-slate-500">
                              {formatDate(op.date)}
                              {op.note && ` • ${op.note}`}
                            </div>
                          </div>
                        </div>
                        <div className="flex items-center gap-3">
                          <div className={`font-mono font-medium ${
                            op.amount >= 0 ? 'text-green-400' : 'text-red-400'
                          }`}>
                            {op.amount >= 0 ? '+' : ''}{formatCurrency(op.amount)}
                          </div>
                          <button
                            onClick={() => handleDelete(op.id)}
                            className="p-1 text-slate-500 hover:text-red-400 transition-colors"
                            title="Удалить"
                          >
                            <Trash2 className="w-4 h-4" />
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end p-4 border-t border-slate-700">
          <button
            onClick={onClose}
            className="px-4 py-2 bg-slate-700 hover:bg-slate-600 text-white rounded-lg transition-colors"
          >
            Закрыть
          </button>
        </div>
      </div>
    </div>
  );
};

export default DepositManagerModal;
