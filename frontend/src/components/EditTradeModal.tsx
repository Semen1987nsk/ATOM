'use client';

import React, { useState } from 'react';
import { api, ApiError } from '@/lib/apiClient';
import { Modal } from '@/components/ui/Modal';
import { useToast } from '@/contexts/ToastContext';

interface EditTradeModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess: () => void;
  trade: EditableTrade | null;
}

export interface EditableTrade {
  id: number;
  symbol?: string;
  asset_name?: string | null;
  asset_type?: string | null;
  direction?: string;
  entry_price?: number | null;
  quantity?: number | null;
  leverage?: number | null;
  commission?: number | null;
  swap?: number | null;
  entry_at?: string | null;
  stop_loss?: number | null;
  take_profit?: number | null;
  risk_amount?: number | null;
  setup_name?: string | null;
  timeframe?: string | null;
  news_event?: string | null;
  screenshot_url?: string | null;
  notes?: string | null;
  tags?: string[] | null;
  exit_reason?: string | null;
  confidence?: number | null;
  entry_reason?: string | null;
}

type EditTradeModalContentProps = Omit<EditTradeModalProps, 'isOpen' | 'trade'> & {
  trade: EditableTrade;
};

type EditTradeFormState = {
  symbol: string;
  asset_name: string;
  asset_type: string;
  direction: string;
  entry_price: string;
  quantity: string;
  leverage: string;
  commission: string;
  swap: string;
  entry_at: string;
  stop_loss: string;
  take_profit: string;
  risk_amount: string;
  setup_name: string;
  timeframe: string;
  news_event: string;
  screenshot_url: string;
  notes: string;
  tags: string;
  exit_reason: string;
  confidence: string;
  entry_reason: string;
};

function buildInitialFormData(trade: EditableTrade): EditTradeFormState {
  return {
    symbol: trade.symbol || '',
    asset_name: trade.asset_name || '',
    asset_type: trade.asset_type || 'Stock',
    direction: trade.direction || 'long',
    entry_price: trade.entry_price?.toString() || '',
    quantity: trade.quantity?.toString() || '',
    leverage: trade.leverage?.toString() || '1',
    commission: trade.commission?.toString() || '',
    swap: trade.swap?.toString() || '',
    entry_at: trade.entry_at ? new Date(trade.entry_at).toISOString().slice(0, 16) : '',
    stop_loss: trade.stop_loss?.toString() || '',
    take_profit: trade.take_profit?.toString() || '',
    risk_amount: trade.risk_amount?.toString() || '',
    setup_name: trade.setup_name || '',
    timeframe: trade.timeframe || '1D',
    news_event: trade.news_event || '',
    screenshot_url: trade.screenshot_url || '',
    notes: trade.notes || '',
    tags: trade.tags ? trade.tags.join(', ') : '',
    exit_reason: trade.exit_reason || '',
    confidence: trade.confidence?.toString() || '',
    entry_reason: trade.entry_reason || '',
  };
}

export const EditTradeModal: React.FC<EditTradeModalProps> = ({ isOpen, onClose, onSuccess, trade }) => {
  if (!isOpen || !trade) return null;

  return (
    <EditTradeModalContent
      key={`edit-${trade.id}-${isOpen ? 'open' : 'closed'}`}
      onClose={onClose}
      onSuccess={onSuccess}
      trade={trade}
    />
  );
};

const EditTradeModalContent: React.FC<EditTradeModalContentProps> = ({ onClose, onSuccess, trade }) => {
  const [formData, setFormData] = useState<EditTradeFormState>(() => buildInitialFormData(trade));
  const [isSubmitting, setIsSubmitting] = useState(false);
  const toast = useToast();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (isSubmitting) return;
    setIsSubmitting(true);
    try {
      await api.patch(`/trades/${trade.id}`, {
        body: {
          ...formData,
          entry_price: parseFloat(formData.entry_price),
          quantity: parseFloat(formData.quantity),
          leverage: formData.leverage ? parseFloat(formData.leverage) : 1.0,
          commission: formData.commission ? parseFloat(formData.commission) : 0,
          swap: formData.swap ? parseFloat(formData.swap) : 0,
          stop_loss: formData.stop_loss ? parseFloat(formData.stop_loss) : null,
          take_profit: formData.take_profit ? parseFloat(formData.take_profit) : null,
          risk_amount: formData.risk_amount ? parseFloat(formData.risk_amount) : null,
          entry_at: new Date(formData.entry_at).toISOString(),
          tags: formData.tags.split(',').map(t => t.trim()).filter(t => t !== ''),
          confidence: formData.confidence ? parseInt(formData.confidence, 10) : null,
        }
      });
      toast.success('Сделка обновлена');
      onSuccess();
      onClose();
    } catch (error) {
      toast.error(error instanceof ApiError ? error.toUserMessage() : 'Не удалось сохранить сделку');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <Modal open onClose={onClose} title={`Редактирование #${trade.id}`} size="md">
      <form onSubmit={handleSubmit} className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-[10px] font-mono uppercase opacity-50 mb-1">Тикер</label>
              <input 
                required
                className="input-cyber"
                placeholder="BTC/USDT"
                value={formData.symbol}
                onChange={e => setFormData({...formData, symbol: e.target.value.toUpperCase()})}
              />
            </div>
            <div>
              <label className="block text-[10px] font-mono uppercase opacity-50 mb-1">Название</label>
              <input 
                className="input-cyber"
                placeholder="Bitcoin"
                value={formData.asset_name}
                onChange={e => setFormData({...formData, asset_name: e.target.value})}
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-[10px] font-mono uppercase opacity-50 mb-1">Тип</label>
              <select 
                className="input-cyber"
                value={formData.asset_type}
                onChange={e => setFormData({...formData, asset_type: e.target.value})}
              >
                <option value="Stock">Акция</option>
                <option value="Futures">Фьючерс</option>
                <option value="Bond">Облигация</option>
                <option value="Crypto">Крипто</option>
                <option value="Forex">Форекс</option>
              </select>
            </div>
            <div>
              <label className="block text-[10px] font-mono uppercase opacity-50 mb-1">Направление</label>
              <select 
                className="input-cyber"
                value={formData.direction}
                onChange={e => setFormData({...formData, direction: e.target.value})}
              >
                <option value="long">ЛОНГ</option>
                <option value="short">ШОРТ</option>
              </select>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-[10px] font-mono uppercase opacity-50 mb-1">Цена входа</label>
              <input 
                required
                type="number" step="any" min="0.00000001"
                className="input-cyber"
                value={formData.entry_price}
                onChange={e => setFormData({...formData, entry_price: e.target.value})}
              />
            </div>
            <div>
              <label className="block text-[10px] font-mono uppercase opacity-50 mb-1">Количество</label>
              <input 
                required
                type="number" step="any" min="0.00000001"
                className="input-cyber"
                value={formData.quantity}
                onChange={e => setFormData({...formData, quantity: e.target.value})}
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-[10px] font-mono uppercase opacity-50 mb-1">Плечо</label>
              <input 
                type="number" step="any" min="1"
                className="input-cyber"
                value={formData.leverage}
                onChange={e => setFormData({...formData, leverage: e.target.value})}
              />
            </div>
            <div>
              <label className="block text-[10px] font-mono uppercase opacity-50 mb-1">Комиссия</label>
              <input 
                type="number" step="any"
                className="input-cyber"
                value={formData.commission}
                onChange={e => setFormData({...formData, commission: e.target.value})}
              />
            </div>
          </div>

          <div>
            <label className="block text-[10px] font-mono uppercase opacity-50 mb-1">Своп / Перенос</label>
            <input 
              type="number" step="any"
              className="input-cyber"
              value={formData.swap}
              onChange={e => setFormData({...formData, swap: e.target.value})}
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-[10px] font-mono uppercase opacity-50 mb-1">Название сетапа</label>
              <input 
                className="input-cyber"
                placeholder="Пробой, Разворот..."
                value={formData.setup_name}
                onChange={e => setFormData({...formData, setup_name: e.target.value})}
              />
            </div>
            <div>
              <label className="block text-[10px] font-mono uppercase opacity-50 mb-1">Таймфрейм</label>
              <select 
                className="input-cyber"
                value={formData.timeframe}
                onChange={e => setFormData({...formData, timeframe: e.target.value})}
              >
                <option value="1m">1m</option>
                <option value="5m">5m</option>
                <option value="15m">15m</option>
                <option value="1H">1H</option>
                <option value="4H">4H</option>
                <option value="1D">1D</option>
                <option value="1W">1W</option>
              </select>
            </div>
          </div>

          <div>
            <label className="block text-[10px] font-mono uppercase opacity-50 mb-1">Причина выхода</label>
            <select 
              className="input-cyber"
              value={formData.exit_reason}
              onChange={e => setFormData({...formData, exit_reason: e.target.value})}
            >
              <option value="">— Выберите причину —</option>
              <option value="Manual">Ручной</option>
              <option value="Stop Loss">Стоп-лосс</option>
              <option value="Take Profit">Тейк-профит</option>
              <option value="Strategy">Сигнал стратегии</option>
              <option value="Time">По времени</option>
              <option value="Panic">Паника</option>
            </select>
          </div>

          <div>
            <label className="block text-[10px] font-mono uppercase opacity-50 mb-1">Дата входа</label>
            <input 
              type="datetime-local"
              max={new Date().toISOString().slice(0, 16)}
              className="input-cyber"
              value={formData.entry_at}
              onChange={e => setFormData({...formData, entry_at: e.target.value})}
            />
          </div>

          <div>
            <label className="block text-[10px] font-mono uppercase opacity-50 mb-1">Уверенность (1-5)</label>
            <div className="flex items-center gap-2">
              <input
                type="range"
                min="1"
                max="5"
                className="w-full accent-accent"
                value={formData.confidence || '5'}
                onChange={e => setFormData({...formData, confidence: e.target.value})}
              />
              <span className="font-mono text-accent w-6 text-center">{formData.confidence || '-'}</span>
            </div>
          </div>

          <div>
            <label className="block text-[10px] font-mono uppercase opacity-50 mb-1">📝 Причина входа (для ИИ анализа)</label>
            <textarea 
              className="input-cyber h-20"
              placeholder="Опишите логику входа в сделку: сигналы, паттерны, уровни, новости..."
              value={formData.entry_reason}
              onChange={e => setFormData({...formData, entry_reason: e.target.value})}
            />
          </div>

          <div>
            <label className="block text-[10px] font-mono uppercase opacity-50 mb-1">Заметки</label>
            <textarea 
              className="input-cyber h-20"
              placeholder="Логика сделки, эмоции..."
              value={formData.notes}
              onChange={e => setFormData({...formData, notes: e.target.value})}
            />
          </div>

          <div>
            <label className="block text-[10px] font-mono uppercase opacity-50 mb-1">Теги (через запятую)</label>
            <input 
              className="input-cyber"
              placeholder="FOMO, Новости, Тренд"
              value={formData.tags}
              onChange={e => setFormData({...formData, tags: e.target.value})}
            />
          </div>

          <div className="flex gap-3 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="btn-secondary flex-1 py-3 text-center justify-center"
            >
              Отмена
            </button>
            <button
              type="submit"
              disabled={isSubmitting}
              className="btn-primary flex-1 py-3 text-center justify-center disabled:opacity-60 disabled:cursor-not-allowed"
            >
              {isSubmitting ? 'Сохраняем…' : 'Обновить сделку'}
            </button>
          </div>
        </form>
    </Modal>
  );
};
