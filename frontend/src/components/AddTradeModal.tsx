'use client';

import React, { useState, useEffect, useRef } from 'react';
import NextImage from 'next/image';
import { X, Brain, Target, Smile, CheckCircle, Upload, Image as ImageIcon, Trash2 } from 'lucide-react';
import { api } from '@/lib/apiClient';

interface AddTradeModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess: () => void;
}

export const AddTradeModal: React.FC<AddTradeModalProps> = ({ isOpen, onClose, onSuccess }) => {
  const [formData, setFormData] = useState({
    symbol: '',
    asset_name: '',
    asset_type: 'Stock',
    direction: 'long',
    entry_price: '',
    quantity: '',
    leverage: '1',
    commission: '',
    entry_at: new Date().toISOString().slice(0, 16),
    stop_loss: '',
    take_profit: '',
    risk_amount: '',
    setup_name: '',
    setup_id: '',
    timeframe: '1D',
    news_event: '',
    screenshot_url: '',
    notes: '',
    tags: '',
    // Психо-трекер
    confidence: '3',  // 1-5
    mood: '3',        // 1-5: 😤😟😐😊🚀
    discipline: '3'   // 1-5
  });
  
  interface Setup {
    id: number;
    name: string;
    icon: string;
    color: string;
  }
  const [setups, setSetups] = useState<Setup[]>([]);
  const [screenshotFile, setScreenshotFile] = useState<File | null>(null);
  const [screenshotPreview, setScreenshotPreview] = useState<string | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  
  // Загрузка сетапов
  useEffect(() => {
    if (isOpen) {
      api.get<Setup[]>('/setups/')
        .then(data => setSetups(data))
        .catch(() => setSetups([]));
    }
  }, [isOpen]);

  if (!isOpen) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const createdTrade = await api.post<{ id: number }>('/trades/', {
        body: {
          ...formData,
          entry_price: parseFloat(formData.entry_price),
          quantity: parseFloat(formData.quantity),
          leverage: formData.leverage ? parseFloat(formData.leverage) : 1.0,
          commission: formData.commission ? parseFloat(formData.commission) : 0,
          stop_loss: formData.stop_loss ? parseFloat(formData.stop_loss) : null,
          take_profit: formData.take_profit ? parseFloat(formData.take_profit) : null,
          risk_amount: formData.risk_amount ? parseFloat(formData.risk_amount) : null,
          entry_at: new Date(formData.entry_at).toISOString(),
          tags: formData.tags.split(',').map(t => t.trim()).filter(t => t !== ''),
          // Психо-трекер
          confidence: parseInt(formData.confidence) || 3,
          mood: parseInt(formData.mood) || 3,
          discipline: parseInt(formData.discipline) || 3,
          setup_id: formData.setup_id ? parseInt(formData.setup_id) : null
        }
      });

      // Загружаем скриншот если есть
      if (screenshotFile && createdTrade.id) {
        const formDataUpload = new FormData();
        formDataUpload.append('file', screenshotFile);
        await api.upload(`/trades/${createdTrade.id}/screenshot`, formDataUpload);
      }
      
      onSuccess();
      onClose();
      // Сбрасываем скриншот
      clearScreenshot();
    } catch (error) {
      console.error('Failed to add trade:', error);
    }
  };
  
  // Emoji шкалы для психо-трекера
  const moodEmojis = ['😤', '😟', '😐', '😊', '🚀'];
  const disciplineLabels = ['Нарушил', 'Частично', 'Нейтрально', 'Следовал', 'Идеально'];
  const confidenceLabels = ['Сомневаюсь', 'Неуверен', 'Нейтрально', 'Уверен', 'Очень уверен'];
  
  // Обработка скриншота
  const handleScreenshotSelect = (file: File) => {
    if (!file.type.startsWith('image/')) return;
    setScreenshotFile(file);
    const reader = new FileReader();
    reader.onload = (e) => setScreenshotPreview(e.target?.result as string);
    reader.readAsDataURL(file);
  };
  
  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };
  
  const handleDragLeave = () => setIsDragging(false);
  
  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    const file = e.dataTransfer.files[0];
    if (file) handleScreenshotSelect(file);
  };
  
  const clearScreenshot = () => {
    setScreenshotFile(null);
    setScreenshotPreview(null);
  };

  return (
    <div className="fixed inset-0 bg-black/80 backdrop-blur-sm flex items-center justify-center z-50 p-4 animate-fadeIn">
      <div className="cyber-card w-full max-w-md bg-[#0d0d0d] p-6 relative animate-scaleIn overflow-hidden">
        {/* Background glow */}
        <div className="absolute -top-32 -right-32 w-64 h-64 bg-accent/10 rounded-full blur-3xl pointer-events-none" />
        <div className="absolute -bottom-32 -left-32 w-64 h-64 bg-accent-secondary/10 rounded-full blur-3xl pointer-events-none" />
        
        <button onClick={onClose} className="absolute top-4 right-4 opacity-50 hover:opacity-100 hover:text-accent transition-colors z-10">
          <X size={20} />
        </button>
        
        <h2 className="text-xl font-bold mb-6 text-neon italic relative z-10">НОВАЯ ПОЗИЦИЯ</h2>
        
        <form onSubmit={handleSubmit} className="space-y-4 relative z-10">
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
                type="number" step="any"
                className="input-cyber"
                value={formData.entry_price}
                onChange={e => setFormData({...formData, entry_price: e.target.value})}
              />
            </div>
            <div>
              <label className="block text-[10px] font-mono uppercase opacity-50 mb-1">Количество</label>
              <input 
                required
                type="number" step="any"
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
                type="number" step="any"
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

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-[10px] font-mono uppercase opacity-50 mb-1">Сетап / Стратегия</label>
              {setups.length > 0 ? (
                <select 
                  className="input-cyber"
                  value={formData.setup_id}
                  onChange={e => setFormData({...formData, setup_id: e.target.value})}
                >
                  <option value="">— Выбрать —</option>
                  {setups.map(s => (
                    <option key={s.id} value={s.id}>{s.icon} {s.name}</option>
                  ))}
                </select>
              ) : (
                <input 
                  className="input-cyber"
                  placeholder="Пробой, Разворот..."
                  value={formData.setup_name}
                  onChange={e => setFormData({...formData, setup_name: e.target.value})}
                />
              )}
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

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-[10px] font-mono uppercase opacity-50 mb-1">Стоп-лосс</label>
              <input 
                type="number" step="any"
                className="input-cyber"
                value={formData.stop_loss}
                onChange={e => setFormData({...formData, stop_loss: e.target.value})}
              />
            </div>
            <div>
              <label className="block text-[10px] font-mono uppercase opacity-50 mb-1">Сумма риска</label>
              <input 
                type="number" step="any"
                className="input-cyber"
                value={formData.risk_amount}
                onChange={e => setFormData({...formData, risk_amount: e.target.value})}
              />
            </div>
          </div>

          {/* Психо-трекер */}
          <div className="p-3 bg-white/5 rounded-lg space-y-3">
            <div className="flex items-center gap-2 text-[10px] font-mono uppercase opacity-50">
              <Brain size={12} />
              Психо-трекер
            </div>
            
            {/* Настроение */}
            <div>
              <label className="block text-[10px] opacity-60 mb-1 flex items-center gap-1">
                <Smile size={10} /> Настроение при входе
              </label>
              <div className="flex gap-1">
                {moodEmojis.map((emoji, i) => (
                  <button
                    key={i}
                    type="button"
                    onClick={() => setFormData({...formData, mood: String(i + 1)})}
                    className={`flex-1 py-2 text-xl rounded transition-all ${
                      parseInt(formData.mood) === i + 1
                        ? 'bg-accent/20 border-accent scale-110'
                        : 'bg-white/5 border-transparent hover:bg-white/10'
                    } border`}
                  >
                    {emoji}
                  </button>
                ))}
              </div>
            </div>
            
            {/* Уверенность */}
            <div>
              <label className="block text-[10px] opacity-60 mb-1 flex items-center gap-1">
                <Target size={10} /> Уверенность в сетапе
              </label>
              <div className="flex gap-1">
                {confidenceLabels.map((label, i) => (
                  <button
                    key={i}
                    type="button"
                    onClick={() => setFormData({...formData, confidence: String(i + 1)})}
                    className={`flex-1 py-1.5 text-[9px] rounded transition-all ${
                      parseInt(formData.confidence) === i + 1
                        ? 'bg-accent/20 border-accent text-accent'
                        : 'bg-white/5 border-transparent hover:bg-white/10 opacity-60'
                    } border`}
                  >
                    {label}
                  </button>
                ))}
              </div>
            </div>
            
            {/* Дисциплина */}
            <div>
              <label className="block text-[10px] opacity-60 mb-1 flex items-center gap-1">
                <CheckCircle size={10} /> Следование плану
              </label>
              <div className="flex gap-1">
                {disciplineLabels.map((label, i) => (
                  <button
                    key={i}
                    type="button"
                    onClick={() => setFormData({...formData, discipline: String(i + 1)})}
                    className={`flex-1 py-1.5 text-[9px] rounded transition-all ${
                      parseInt(formData.discipline) === i + 1
                        ? i >= 3 ? 'bg-green-500/20 border-green-500 text-green-400' : i <= 1 ? 'bg-red-500/20 border-red-500 text-red-400' : 'bg-yellow-500/20 border-yellow-500 text-yellow-400'
                        : 'bg-white/5 border-transparent hover:bg-white/10 opacity-60'
                    } border`}
                  >
                    {label}
                  </button>
                ))}
              </div>
            </div>
          </div>

          <div>
            <label className="block text-[10px] font-mono uppercase opacity-50 mb-1">Заметки / Стратегия</label>
            <textarea 
              className="input-cyber h-20 resize-none"
              placeholder="Почему входишь в эту сделку?"
              value={formData.notes}
              onChange={e => setFormData({...formData, notes: e.target.value})}
            />
          </div>
          
          {/* Скриншот */}
          <div>
            <label className="block text-[10px] font-mono uppercase opacity-50 mb-1 flex items-center gap-1">
              <ImageIcon size={10} /> Скриншот графика
            </label>
            {screenshotPreview ? (
              <div className="relative group">
                <NextImage
                  src={screenshotPreview} 
                  alt="Preview" 
                  width={512}
                  height={128}
                  unoptimized
                  className="w-full h-32 object-cover rounded-lg border border-border"
                />
                <button
                  type="button"
                  onClick={clearScreenshot}
                  className="absolute top-2 right-2 p-1.5 bg-red-500/80 hover:bg-red-500 rounded-full opacity-0 group-hover:opacity-100 transition-opacity"
                >
                  <Trash2 size={12} />
                </button>
              </div>
            ) : (
              <div
                onDragOver={handleDragOver}
                onDragLeave={handleDragLeave}
                onDrop={handleDrop}
                onClick={() => fileInputRef.current?.click()}
                className={`border-2 border-dashed rounded-lg p-4 text-center cursor-pointer transition-all ${
                  isDragging 
                    ? 'border-accent bg-accent/10' 
                    : 'border-border hover:border-accent/50 hover:bg-white/5'
                }`}
              >
                <Upload size={24} className="mx-auto mb-2 opacity-40" />
                <p className="text-[10px] opacity-40">
                  Перетащите изображение или кликните
                </p>
                <input
                  ref={fileInputRef}
                  type="file"
                  accept="image/*"
                  className="hidden"
                  onChange={(e) => e.target.files?.[0] && handleScreenshotSelect(e.target.files[0])}
                />
              </div>
            )}
          </div>

          <div>
            <label className="block text-[10px] font-mono uppercase opacity-50 mb-1">Теги (через запятую)</label>
            <input 
              className="input-cyber"
              placeholder="Тренд, FOMO, Пробой"
              value={formData.tags}
              onChange={e => setFormData({...formData, tags: e.target.value})}
            />
          </div>

          <button 
            type="submit"
            className="btn-primary w-full py-3 text-center justify-center"
          >
            Открыть позицию
          </button>
        </form>
      </div>
    </div>
  );
};
