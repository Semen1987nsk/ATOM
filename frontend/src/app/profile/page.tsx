'use client';

import { useState, useEffect } from 'react';
import { useAuth, RequireAuth } from '@/contexts/AuthContext';
import { api } from '@/lib/apiClient';
import Link from 'next/link';
import {
  User, Mail, Calendar, Settings, LogOut, Save,
  ArrowLeft, Loader2, CheckCircle, AlertCircle,
  TrendingUp, BarChart3, Target, Shield, Crown, Zap, Building2, ArrowUpRight, HelpCircle,
  Download
} from 'lucide-react';
import { AppShell } from '@/components/AppShell';

interface Subscription {
  plan: 'free' | 'pro' | 'corporate';
  is_active: boolean;
  started_at: string | null;
  expires_at: string | null;
  auto_renew: boolean;
  limits: {
    max_trades: number | null;
    max_accounts: number;
    ai_analysis: boolean;
  };
}

function ProfileContent() {
  const { user, isAuthenticated, logout, updateProfile, isLoading: authLoading } = useAuth();
  
  const [name, setName] = useState(user?.name || '');
  const [isEditing, setIsEditing] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const [subscription, setSubscription] = useState<Subscription | null>(null);
  const [isExporting, setIsExporting] = useState(false);
  
  // Синхронизация с user
  useEffect(() => {
    if (user) {
      setName(user.name || '');
    }
  }, [user]);
  
  // Загрузка подписки
  useEffect(() => {
    if (isAuthenticated) {
      api.get<Subscription>('/auth/subscription')
        .then(data => setSubscription(data))
        .catch(err => console.error('Failed to load subscription:', err));
    }
  }, [isAuthenticated]);
  
  const handleSave = async () => {
    setIsSaving(true);
    setMessage(null);
    
    try {
      await updateProfile({ name: name || undefined });
      setMessage({ type: 'success', text: 'Профиль сохранён!' });
      setIsEditing(false);
    } catch (err) {
      setMessage({ type: 'error', text: err instanceof Error ? err.message : 'Ошибка сохранения' });
    } finally {
      setIsSaving(false);
    }
  };
  
  const handleLogout = () => {
    logout();
    window.location.href = '/';
  };

  // 152-ФЗ ст. 14: право на доступ. Скачиваем JSON-снапшот всех ПД пользователя.
  const handleExportData = async () => {
    setIsExporting(true);
    setMessage(null);
    try {
      const data = await api.get<unknown>('/auth/me/export');
      const json = JSON.stringify(data, null, 2);
      const blob = new Blob([json], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      const stamp = new Date().toISOString().slice(0, 10);
      a.download = `eqio-export-${stamp}.json`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      setMessage({ type: 'success', text: 'Экспорт скачан' });
    } catch (err) {
      const text = err instanceof Error ? err.message : 'Не удалось скачать экспорт';
      setMessage({ type: 'error', text });
    } finally {
      setIsExporting(false);
    }
  };
  
  if (authLoading || !user) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <Loader2 className="w-8 h-8 animate-spin text-accent" />
      </div>
    );
  }
  
  const createdDate = new Date(user.created_at).toLocaleDateString('ru-RU', {
    year: 'numeric',
    month: 'long',
    day: 'numeric'
  });
  
  return (
    <AppShell pageTitle="Профиль">
    <main className="p-6 md:p-8 max-w-7xl mx-auto">
      {/* Background Effects */}
      <div className="absolute inset-0 bg-gradient-to-br from-background via-background to-accent/5" />
      <div className="absolute top-20 right-20 w-80 h-80 bg-accent/10 rounded-full blur-3xl" />
      <div className="absolute bottom-20 left-20 w-60 h-60 bg-green-500/10 rounded-full blur-3xl" />
      
      <div className="relative max-w-4xl mx-auto">
        {/* Header */}
        <div className="flex items-center justify-between mb-8">
          <Link 
            href="/" 
            className="flex items-center gap-2 text-muted-foreground hover:text-foreground transition-colors"
          >
            <ArrowLeft size={20} />
            <span>Назад</span>
          </Link>
          
          <div className="flex items-center gap-2">
            <Link
              href="/help"
              className="flex items-center gap-2 px-4 py-2 text-cyan-400 hover:bg-cyan-500/10 rounded-lg transition-colors"
            >
              <HelpCircle size={18} />
              <span className="hidden md:inline">Помощь</span>
            </Link>
            {user.is_admin && (
              <Link
                href="/admin"
                className="flex items-center gap-2 px-4 py-2 text-purple-400 hover:bg-purple-500/10 rounded-lg transition-colors"
              >
                <Shield size={18} />
                Админ-панель
              </Link>
            )}
            <button
              onClick={handleLogout}
              className="flex items-center gap-2 px-4 py-2 text-red-400 hover:bg-red-500/10 rounded-lg transition-colors"
            >
              <LogOut size={18} />
              Выйти
            </button>
          </div>
        </div>
        
        {/* Profile Card */}
        <div className="cyber-card p-8 mb-6">
          <div className="flex items-start gap-6">
            {/* Avatar */}
            <div className="w-24 h-24 bg-gradient-to-br from-accent to-accent/50 rounded-2xl flex items-center justify-center shrink-0">
              <span className="text-3xl font-black text-white">
                {(user.name || user.email)[0].toUpperCase()}
              </span>
            </div>
            
            {/* Info */}
            <div className="flex-1">
              <div className="flex items-center gap-3 mb-2">
                <h1 className="text-2xl font-bold">{user.name || 'Трейдер'}</h1>
                {user.is_active && (
                  <span className="px-2 py-0.5 bg-green-500/20 text-green-400 text-xs rounded-full">
                    Активен
                  </span>
                )}
                {/* Plan Badge */}
                {subscription && (
                  <span className={`flex items-center gap-1 px-2 py-0.5 text-xs rounded-full ${
                    subscription.plan === 'pro' 
                      ? 'bg-purple-500/20 text-purple-400' 
                      : subscription.plan === 'corporate'
                      ? 'bg-amber-500/20 text-amber-400'
                      : 'bg-gray-500/20 text-gray-400'
                  }`}>
                    {subscription.plan === 'pro' && <Crown size={12} />}
                    {subscription.plan === 'corporate' && <Building2 size={12} />}
                    {subscription.plan === 'free' && <Zap size={12} />}
                    {subscription.plan.toUpperCase()}
                  </span>
                )}
              </div>
              
              <div className="flex flex-wrap gap-4 text-sm text-muted-foreground">
                <div className="flex items-center gap-1.5">
                  <Mail size={14} />
                  {user.email}
                </div>
                <div className="flex items-center gap-1.5">
                  <Calendar size={14} />
                  С {createdDate}
                </div>
              </div>
            </div>
          </div>
        </div>
        
        {/* Subscription Card */}
        {subscription && (
          <div className={`cyber-card p-6 mb-6 border-l-4 ${
            subscription.plan === 'pro' ? 'border-purple-500' : 
            subscription.plan === 'corporate' ? 'border-amber-500' : 'border-gray-500'
          }`}>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-4">
                <div className={`p-3 rounded-xl ${
                  subscription.plan === 'pro' 
                    ? 'bg-gradient-to-br from-purple-500 to-indigo-600' 
                    : subscription.plan === 'corporate'
                    ? 'bg-gradient-to-br from-amber-500 to-orange-600'
                    : 'bg-gradient-to-br from-gray-500 to-gray-600'
                }`}>
                  {subscription.plan === 'pro' && <Crown size={24} className="text-white" />}
                  {subscription.plan === 'corporate' && <Building2 size={24} className="text-white" />}
                  {subscription.plan === 'free' && <Zap size={24} className="text-white" />}
                </div>
                <div>
                  <h3 className="font-bold text-lg">
                    {subscription.plan === 'pro' ? 'Pro' : 
                     subscription.plan === 'corporate' ? 'Corporate' : 'Free'} Plan
                  </h3>
                  <div className="text-sm text-muted-foreground">
                    {subscription.plan === 'free' ? (
                      <>До {subscription.limits.max_trades} сделок/мес · {subscription.limits.max_accounts} счёт</>
                    ) : subscription.plan === 'pro' ? (
                      <>Безлимит сделок · До {subscription.limits.max_accounts} счетов · AI-анализ</>
                    ) : (
                      <>Безлимит всего · Приоритетная поддержка</>
                    )}
                  </div>
                  {subscription.expires_at && (
                    <div className="text-xs text-muted-foreground mt-1">
                      Активна до {new Date(subscription.expires_at).toLocaleDateString('ru-RU')}
                      {subscription.auto_renew && <span className="text-green-400 ml-2">· Автопродление</span>}
                    </div>
                  )}
                </div>
              </div>
              
              {subscription.plan === 'free' && (
                <Link
                  href="/pricing"
                  className="btn-primary flex items-center gap-2"
                >
                  <Crown size={16} />
                  Улучшить до Pro
                  <ArrowUpRight size={16} />
                </Link>
              )}
              {subscription.plan === 'pro' && (
                <Link
                  href="/pricing"
                  className="btn-secondary flex items-center gap-2 text-sm"
                >
                  Управление подпиской
                </Link>
              )}
            </div>
          </div>
        )}
        
        {/* Message */}
        {message && (
          <div className={`flex items-center gap-2 p-3 mb-6 rounded-lg text-sm ${
            message.type === 'success' 
              ? 'bg-green-500/10 border border-green-500/20 text-green-400' 
              : 'bg-red-500/10 border border-red-500/20 text-red-400'
          }`}>
            {message.type === 'success' ? <CheckCircle size={16} /> : <AlertCircle size={16} />}
            {message.text}
          </div>
        )}
        
        <div className="grid md:grid-cols-2 gap-6">
          {/* Edit Profile */}
          <div className="cyber-card p-6">
            <div className="flex items-center gap-3 mb-6">
              <div className="p-2 bg-accent/20 rounded-lg">
                <Settings size={20} className="text-accent" />
              </div>
              <h2 className="text-lg font-bold">Редактировать профиль</h2>
            </div>
            
            <div className="space-y-4">
              {/* Name */}
              <div className="space-y-2">
                <label className="text-sm font-medium text-foreground">Имя</label>
                <div className="relative">
                  <User size={18} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
                  <input
                    type="text"
                    value={name}
                    onChange={(e) => { setName(e.target.value); setIsEditing(true); }}
                    placeholder="Ваше имя"
                    className="w-full pl-10 pr-4 py-3 bg-secondary/50 border border-white/10 rounded-lg 
                             text-foreground placeholder:text-muted-foreground
                             focus:outline-none focus:ring-2 focus:ring-accent/50 focus:border-accent
                             transition-all"
                  />
                </div>
              </div>
              
              {/* Email (read-only) */}
              <div className="space-y-2">
                <label className="text-sm font-medium text-muted-foreground">Email</label>
                <div className="relative">
                  <Mail size={18} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
                  <input
                    type="email"
                    value={user.email}
                    disabled
                    className="w-full pl-10 pr-4 py-3 bg-secondary/30 border border-white/5 rounded-lg 
                             text-muted-foreground cursor-not-allowed"
                  />
                </div>
                <p className="text-xs text-muted-foreground">Email изменить нельзя</p>
              </div>
              
              {/* Save Button */}
              <button
                onClick={handleSave}
                disabled={!isEditing || isSaving}
                className="w-full py-3 bg-accent hover:bg-accent/90 text-white font-semibold rounded-lg
                         flex items-center justify-center gap-2 transition-all
                         disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {isSaving ? (
                  <>
                    <Loader2 size={18} className="animate-spin" />
                    Сохранение...
                  </>
                ) : (
                  <>
                    <Save size={18} />
                    Сохранить изменения
                  </>
                )}
              </button>
            </div>
          </div>
          
          {/* Quick Stats */}
          <div className="cyber-card p-6">
            <div className="flex items-center gap-3 mb-6">
              <div className="p-2 bg-green-500/20 rounded-lg">
                <BarChart3 size={20} className="text-green-400" />
              </div>
              <h2 className="text-lg font-bold">Быстрая статистика</h2>
            </div>
            
            <div className="space-y-4">
              <div className="flex items-center justify-between p-3 bg-secondary/30 rounded-lg">
                <div className="flex items-center gap-2 text-muted-foreground">
                  <TrendingUp size={16} />
                  <span>Всего сделок</span>
                </div>
                <span className="font-bold text-foreground">—</span>
              </div>
              
              <div className="flex items-center justify-between p-3 bg-secondary/30 rounded-lg">
                <div className="flex items-center gap-2 text-muted-foreground">
                  <Target size={16} />
                  <span>Win Rate</span>
                </div>
                <span className="font-bold text-foreground">—</span>
              </div>
              
              <div className="flex items-center justify-between p-3 bg-secondary/30 rounded-lg">
                <div className="flex items-center gap-2 text-muted-foreground">
                  <BarChart3 size={16} />
                  <span>Общий P&L</span>
                </div>
                <span className="font-bold text-foreground">—</span>
              </div>
              
              <p className="text-xs text-muted-foreground text-center">
                Статистика появится после добавления сделок
              </p>
            </div>
          </div>
        </div>
        
        {/* Персональные данные (152-ФЗ ст. 14 — право доступа) */}
        <div className="mt-6 cyber-card p-6">
          <h3 className="text-lg font-bold mb-1">Персональные данные</h3>
          <p className="text-sm text-[var(--text-secondary)] mb-4">
            Согласно ст. 14 152-ФЗ вы можете получить копию всех своих данных в JSON.
          </p>
          <div className="flex items-center justify-between">
            <div>
              <p className="font-medium">Скачать мои данные</p>
              <p className="text-sm text-[var(--text-secondary)]">
                Профиль, сделки, согласия, платежи — всё в одном файле.
              </p>
            </div>
            <button
              onClick={handleExportData}
              disabled={isExporting}
              className="px-4 py-2 bg-[var(--surface-2)] hover:bg-[var(--surface-3)] text-[var(--foreground)] rounded-lg transition-colors flex items-center gap-2 disabled:opacity-60"
            >
              {isExporting ? (
                <Loader2 size={16} className="animate-spin" />
              ) : (
                <Download size={16} />
              )}
              {isExporting ? 'Готовим…' : 'Скачать JSON'}
            </button>
          </div>
        </div>

        {/* Danger Zone */}
        <div className="mt-6 cyber-card p-6 border-red-500/20">
          <h3 className="text-lg font-bold text-red-400 mb-4">Опасная зона</h3>
          <div className="flex items-center justify-between">
            <div>
              <p className="font-medium">Выйти из аккаунта</p>
              <p className="text-sm text-muted-foreground">Вы будете разлогинены на этом устройстве</p>
            </div>
            <button
              onClick={handleLogout}
              className="px-4 py-2 bg-red-500/10 hover:bg-red-500/20 text-red-400 rounded-lg transition-colors"
            >
              Выйти
            </button>
          </div>
        </div>
      </div>
    </main>
    </AppShell>
  );
}

export default function ProfilePage() {
  return (
    <RequireAuth>
      <ProfileContent />
    </RequireAuth>
  );
}
