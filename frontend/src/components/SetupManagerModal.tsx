'use client';

import React, { useState, useEffect } from 'react';
import { X, Plus, Trash2, Edit2, Target, Save } from 'lucide-react';
import { api, ApiError } from '@/lib/apiClient';
import { useToast } from '@/contexts/ToastContext';

interface Setup {
  id: number;
  name: string;
  description: string | null;
  rules: string | null;
  color: string;
  icon: string;
  is_active: boolean;
  trades_count: number;
  win_rate: number;
  avg_pnl: number;
  total_pnl: number;
}

interface SetupManagerModalProps {
  isOpen: boolean;
  onClose: () => void;
}

const ICONS = ['📈', '📉', '🚀', '↩️', '⚡', '🎯', '💎', '🔥', '⭐', '🛡️', '⬆️', '⬇️'];
const COLORS = ['#00d4aa', '#f59e0b', '#3b82f6', '#8b5cf6', '#ec4899', '#06b6d4', '#ef4444', '#22c55e'];

export const SetupManagerModal: React.FC<SetupManagerModalProps> = ({ isOpen, onClose }) => {
  const [setups, setSetups] = useState<Setup[]>([]);
  const [loading, setLoading] = useState(false);
  const [editingSetup, setEditingSetup] = useState<Setup | null>(null);
  const [isAddingNew, setIsAddingNew] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const toast = useToast();

  const [formData, setFormData] = useState({
    name: '',
    description: '',
    rules: '',
    icon: '📈',
    color: '#00d4aa'
  });

  const fetchSetups = async () => {
    setLoading(true);
    try {
      const data = await api.get<Setup[]>('/setups/');
      setSetups(data);
    } catch (e) {
      console.error('Failed to fetch setups:', e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (isOpen) {
      fetchSetups();
    }
  }, [isOpen]);

  const handleSave = async () => {
    if (!formData.name.trim() || isSubmitting) return;
    setIsSubmitting(true);
    try {
      if (editingSetup) {
        await api.put(`/setups/${editingSetup.id}`, { body: formData });
        setEditingSetup(null);
      } else {
        await api.post('/setups/', { body: formData });
        setIsAddingNew(false);
      }
      fetchSetups();
      resetForm();
    } catch (e) {
      toast.error(e instanceof ApiError ? e.toUserMessage() : 'Не удалось сохранить сетап');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleDelete = async (id: number) => {
    if (!confirm('Удалить этот сетап? Сделки не будут удалены.')) return;
    
    try {
      await api.delete(`/setups/${id}`);
      fetchSetups();
    } catch (e) {
      toast.error(e instanceof ApiError ? e.toUserMessage() : 'Не удалось удалить сетап');
    }
  };

  const handleEdit = (setup: Setup) => {
    setEditingSetup(setup);
    setFormData({
      name: setup.name,
      description: setup.description || '',
      rules: setup.rules || '',
      icon: setup.icon,
      color: setup.color
    });
    setIsAddingNew(false);
  };

  const resetForm = () => {
    setFormData({ name: '', description: '', rules: '', icon: '📈', color: '#00d4aa' });
    setEditingSetup(null);
    setIsAddingNew(false);
  };

  const initPresets = async () => {
    try {
      await api.post('/setups/init-presets');
      fetchSetups();
    } catch (e) {
      toast.error(e instanceof ApiError ? e.toUserMessage() : 'Не удалось инициализировать пресеты');
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black/80 backdrop-blur-sm flex items-center justify-center z-50 p-4 animate-fadeIn">
      <div className="cyber-card w-full max-w-2xl bg-[var(--surface-1)] p-6 relative animate-scaleIn overflow-hidden max-h-[90vh] overflow-y-auto">
        <button onClick={onClose} className="absolute top-4 right-4 opacity-50 hover:opacity-100 hover:text-accent transition-colors z-10">
          <X size={20} />
        </button>
        
        <h2 className="text-xl font-bold mb-6 text-accent italic flex items-center gap-2 relative z-10">
          <Target size={20} />
          Управление Сетапами
        </h2>
        
        {/* Форма добавления/редактирования */}
        {(isAddingNew || editingSetup) && (
          <div className="mb-6 p-4 bg-white/5 rounded-lg space-y-4">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-medium">
                {editingSetup ? 'Редактирование' : 'Новый сетап'}
              </h3>
              <button onClick={resetForm} className="text-xs opacity-50 hover:opacity-100">
                Отмена
              </button>
            </div>
            
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-[10px] font-mono uppercase opacity-50 mb-1">Название</label>
                <input 
                  className="input-cyber"
                  placeholder="Пробой, Возврат к среднему..."
                  value={formData.name}
                  onChange={e => setFormData({...formData, name: e.target.value})}
                />
              </div>
              <div>
                <label className="block text-[10px] font-mono uppercase opacity-50 mb-1">Описание</label>
                <input 
                  className="input-cyber"
                  placeholder="Краткое описание"
                  value={formData.description}
                  onChange={e => setFormData({...formData, description: e.target.value})}
                />
              </div>
            </div>
            
            <div>
              <label className="block text-[10px] font-mono uppercase opacity-50 mb-1">Правила входа/выхода</label>
              <textarea 
                className="input-cyber h-16 resize-none"
                placeholder="Условия для входа и выхода..."
                value={formData.rules}
                onChange={e => setFormData({...formData, rules: e.target.value})}
              />
            </div>
            
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-[10px] font-mono uppercase opacity-50 mb-1">Иконка</label>
                <div className="flex flex-wrap gap-1">
                  {ICONS.map(icon => (
                    <button
                      key={icon}
                      type="button"
                      onClick={() => setFormData({...formData, icon})}
                      className={`w-8 h-8 text-lg rounded transition-all ${
                        formData.icon === icon 
                          ? 'bg-accent/20 border-accent' 
                          : 'bg-white/5 border-transparent hover:bg-white/10'
                      } border`}
                    >
                      {icon}
                    </button>
                  ))}
                </div>
              </div>
              <div>
                <label className="block text-[10px] font-mono uppercase opacity-50 mb-1">Цвет</label>
                <div className="flex flex-wrap gap-1">
                  {COLORS.map(color => (
                    <button
                      key={color}
                      type="button"
                      onClick={() => setFormData({...formData, color})}
                      className={`w-8 h-8 rounded transition-all ${
                        formData.color === color ? 'ring-2 ring-white scale-110' : ''
                      }`}
                      style={{ backgroundColor: color }}
                    />
                  ))}
                </div>
              </div>
            </div>
            
            <button
              onClick={handleSave}
              disabled={isSubmitting || !formData.name.trim()}
              className="btn-primary w-full justify-center disabled:opacity-50"
            >
              <Save size={14} />
              {editingSetup ? 'Сохранить изменения' : 'Создать сетап'}
            </button>
          </div>
        )}
        
        {/* Список сетапов */}
        <div className="space-y-3">
          {loading ? (
            <div className="text-center opacity-50 py-8">Загрузка...</div>
          ) : setups.length === 0 ? (
            <div className="text-center py-8">
              <div className="opacity-50 mb-4">Нет сетапов</div>
              <button onClick={initPresets} className="btn-secondary">
                Создать стандартные сетапы
              </button>
            </div>
          ) : (
            setups.map(setup => (
              <div 
                key={setup.id} 
                className="p-4 bg-white/5 rounded-lg flex items-center gap-4 hover:bg-white/10 transition-colors"
                style={{ borderLeft: `3px solid ${setup.color}` }}
              >
                <div className="text-2xl">{setup.icon}</div>
                <div className="flex-1">
                  <div className="font-medium">{setup.name}</div>
                  {setup.description && (
                    <div className="text-[11px] opacity-50">{setup.description}</div>
                  )}
                </div>
                
                {/* Статистика */}
                <div className="flex gap-4 text-xs">
                  <div className="text-center">
                    <div className="opacity-50">Сделок</div>
                    <div className="font-bold">{setup.trades_count}</div>
                  </div>
                  <div className="text-center">
                    <div className="opacity-50">Винрейт</div>
                    <div className={`font-bold ${setup.win_rate >= 50 ? 'text-green-400' : 'text-red-400'}`}>
                      {setup.win_rate}%
                    </div>
                  </div>
                  <div className="text-center">
                    <div className="opacity-50">Всего</div>
                    <div className={`font-bold ${setup.total_pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                      {setup.total_pnl >= 0 ? '+' : ''}{setup.total_pnl.toLocaleString()}
                    </div>
                  </div>
                </div>
                
                {/* Действия */}
                <div className="flex gap-2">
                  <button 
                    onClick={() => handleEdit(setup)}
                    className="p-2 hover:bg-white/10 rounded transition-colors"
                  >
                    <Edit2 size={14} />
                  </button>
                  <button 
                    onClick={() => handleDelete(setup.id)}
                    className="p-2 hover:bg-red-500/20 text-red-400 rounded transition-colors"
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
              </div>
            ))
          )}
        </div>
        
        {/* Кнопка добавления */}
        {!isAddingNew && !editingSetup && (
          <button
            onClick={() => setIsAddingNew(true)}
            className="mt-4 w-full p-3 border-2 border-dashed border-border hover:border-accent/50 rounded-lg flex items-center justify-center gap-2 text-sm opacity-60 hover:opacity-100 transition-all"
          >
            <Plus size={16} />
            Добавить сетап
          </button>
        )}
      </div>
    </div>
  );
};
