'use client';

import { useState, useEffect, useCallback } from 'react';
import { useAuth, RequireAuth } from '@/contexts/AuthContext';
import { api, ApiError } from '@/lib/apiClient';
import NextImage from 'next/image';
import Link from 'next/link';
import { AppShell } from '@/components/AppShell';
import { 
  Users, TrendingUp, Activity, Target, Shield, ArrowLeft,
  Search, ChevronDown, UserCheck, UserX, Crown,
  BarChart3, PieChart, AlertTriangle,
  RefreshCw, Loader2, DollarSign, CreditCard,
  Zap, TrendingDown, Repeat, FileText, Plus, Edit, Trash2, Eye, 
  EyeOff, Save, X, Image as ImageIcon
} from 'lucide-react';
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, PieChart as RechartsPie, Pie, Cell,
  BarChart, Bar
} from '@/lib/lazy-recharts';
import { PnLHealthTab } from './PnLHealthTab';

// Цвета для графиков
const COLORS = ['#d4a13a', '#22c55e', '#f59e0b', '#ef4444', '#8b5cf6', '#06b6d4'];
const SOURCE_COLORS: Record<string, string> = {
  email: '#d4a13a',
  google: '#ea4335',
  yandex: '#fc3f1d',
  sber: '#21a038',
  tinkoff: '#ffdd2d',
};

interface AdminStats {
  users: {
    total: number;
    new_today: number;
    new_this_week: number;
    new_this_month: number;
  };
  activity: {
    dau: number;
    wau: number;
    mau: number;
    dau_mau_ratio: number;
  };
  engagement: {
    total_trades: number;
    trades_today: number;
    trades_this_week: number;
    avg_trades_per_user: number;
  };
}

interface UserData {
  id: number;
  email: string;
  name: string | null;
  is_active: boolean;
  is_admin: boolean;
  created_at: string;
  last_login: string | null;
  registration_source: string;
  trades_count: number;
  accounts_count: number;
  utm_source: string | null;
  utm_campaign: string | null;
}

interface SourceData {
  source: string;
  count: number;
  percentage: number;
}

interface GrowthData {
  date: string;
  new_users: number;
  total_users: number;
}

interface FunnelStep {
  name: string;
  count: number;
  rate: number;
}

type ChartDatum = Record<string, string | number>;

type ActiveTab = 'overview' | 'users' | 'revenue' | 'analytics' | 'blog' | 'pnl-health';

const ADMIN_TABS = [
  { id: 'overview', label: 'Обзор', icon: BarChart3 },
  { id: 'revenue', label: 'Выручка', icon: DollarSign },
  { id: 'users', label: 'Пользователи', icon: Users },
  { id: 'pnl-health', label: 'P&L Health', icon: Shield },
  { id: 'blog', label: 'Блог', icon: FileText },
  { id: 'analytics', label: 'Аналитика', icon: PieChart },
] as const satisfies ReadonlyArray<{ id: ActiveTab; label: string; icon: typeof BarChart3 }>;

interface RevenueStats {
  overview: {
    total_users: number;
    paid_users: number;
    free_users: number;
    conversion_rate: number;
  };
  revenue: {
    total: number;
    this_month: number;
    today: number;
    avg_payment: number;
    mrr: number;
    arr: number;
  };
  plans: {
    free: number;
    pro: number;
    corporate: number;
  };
  health: {
    churn_rate: number;
    churned_this_month: number;
    new_paid_this_month: number;
    total_payments: number;
  };
}

interface RevenueGrowth {
  date: string;
  revenue: number;
  payments: number;
  cumulative: number;
}

interface SubscriptionAnalytics {
  payment_methods: { method: string; count: number; amount: number }[];
  auto_renew: { enabled: number; disabled: number; rate: number };
  expiring_soon: number;
  ltv: number;
  paying_users_total: number;
}

interface TopPayingUser {
  id: number;
  email: string;
  name: string | null;
  total_paid: number;
  payments_count: number;
  created_at: string;
  last_login: string | null;
}

interface ArticleData {
  id: number;
  slug: string;
  title: string;
  excerpt?: string;
  content: string;
  cover_image?: string;
  category: string;
  tags: string[];
  author_id: number;
  author_name?: string;
  is_published: boolean;
  is_featured: boolean;
  views_count: number;
  likes_count: number;
  created_at: string;
  updated_at: string;
  published_at?: string;
}

function AdminDashboard() {
  const { user, isAuthenticated } = useAuth();
  
  const [stats, setStats] = useState<AdminStats | null>(null);
  const [users, setUsers] = useState<UserData[]>([]);
  const [usersTotal, setUsersTotal] = useState(0);
  const [sources, setSources] = useState<SourceData[]>([]);
  const [growth, setGrowth] = useState<GrowthData[]>([]);
  const [funnel, setFunnel] = useState<FunnelStep[]>([]);
  const [revenue, setRevenue] = useState<RevenueStats | null>(null);
  const [revenueGrowth, setRevenueGrowth] = useState<RevenueGrowth[]>([]);
  const [subscriptionAnalytics, setSubscriptionAnalytics] = useState<SubscriptionAnalytics | null>(null);
  const [topPayingUsers, setTopPayingUsers] = useState<TopPayingUser[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  
  // Filters
  const [searchQuery, setSearchQuery] = useState('');
  const [sourceFilter, setSourceFilter] = useState('');
  const [sortBy, setSortBy] = useState('created_at');
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('desc');
  const [currentPage, setCurrentPage] = useState(0);
  const pageSize = 20;
  
  // Active tab
  const [activeTab, setActiveTab] = useState<ActiveTab>('overview');
  
  // Blog state
  const [articles, setArticles] = useState<ArticleData[]>([]);
  const [editingArticle, setEditingArticle] = useState<ArticleData | null>(null);
  const [isCreatingArticle, setIsCreatingArticle] = useState(false);
  const [articleForm, setArticleForm] = useState({
    title: '',
    slug: '',
    excerpt: '',
    content: '',
    cover_image: '',
    category: 'news',
    tags: '',
    is_published: false,
    is_featured: false
  });

  const registrationSourceChartData: ChartDatum[] = sources.map((item) => ({
    source: item.source,
    count: item.count,
    percentage: item.percentage,
  }));

  const fetchData = useCallback(async () => {
    if (!isAuthenticated) return;
    
    setLoading(true);
    setError(null);
    
    try {
      // Fetch all data in parallel
      const [statsData, usersData, sourcesData, growthData, funnelData, revenueData, revenueGrowthData, subAnalyticsData, topPayingData] = await Promise.all([
        api.get<AdminStats>('/admin/stats'),
        api.get<{users: UserData[]; total: number}>(`/admin/users?skip=${currentPage * pageSize}&limit=${pageSize}&sort_by=${sortBy}&sort_order=${sortOrder}&search=${searchQuery}&registration_source=${sourceFilter}`),
        api.get<SourceData[]>('/admin/registration-sources'),
        api.get<GrowthData[]>('/admin/growth?days=30'),
        api.get<{steps: FunnelStep[]}>('/admin/funnel'),
        api.get<RevenueStats>('/admin/revenue'),
        api.get<RevenueGrowth[]>('/admin/revenue-growth?days=30'),
        api.get<SubscriptionAnalytics>('/admin/subscription-analytics'),
        api.get<TopPayingUser[]>('/admin/top-paying-users?limit=10'),
      ]);
      
      setStats(statsData);
      setUsers(usersData.users);
      setUsersTotal(usersData.total);
      setSources(sourcesData);
      setGrowth(growthData);
      setFunnel(funnelData.steps);
      setRevenue(revenueData);
      setRevenueGrowth(revenueGrowthData);
      setSubscriptionAnalytics(subAnalyticsData);
      setTopPayingUsers(topPayingData);
      
      // Fetch articles
      try {
        const articlesData = await api.get<ArticleData[]>('/admin/articles');
        setArticles(articlesData);
      } catch {
        // Articles fetch is non-critical
      }
    } catch (err) {
      if (err instanceof ApiError && err.status === 403) {
        setError('Нет прав доступа к админ-панели');
      } else {
        setError(err instanceof Error ? err.message : 'Ошибка');
      }
    } finally {
      setLoading(false);
    }
  }, [isAuthenticated, currentPage, sortBy, sortOrder, searchQuery, sourceFilter]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const toggleUserAdmin = async (userId: number, isAdmin: boolean) => {
    try {
      await api.post(`/admin/users/${userId}/toggle-admin`, { params: { is_admin: isAdmin } });
      fetchData();
    } catch (err) {
      console.error(err);
    }
  };

  const toggleUserActive = async (userId: number) => {
    try {
      await api.post(`/admin/users/${userId}/toggle-active`);
      fetchData();
    } catch (err) {
      console.error(err);
    }
  };

  // Blog functions
  const resetArticleForm = () => {
    setArticleForm({
      title: '',
      slug: '',
      excerpt: '',
      content: '',
      cover_image: '',
      category: 'news',
      tags: '',
      is_published: false,
      is_featured: false
    });
  };

  const openCreateArticle = () => {
    resetArticleForm();
    setEditingArticle(null);
    setIsCreatingArticle(true);
  };

  const openEditArticle = (article: ArticleData) => {
    setArticleForm({
      title: article.title,
      slug: article.slug,
      excerpt: article.excerpt || '',
      content: article.content,
      cover_image: article.cover_image || '',
      category: article.category,
      tags: article.tags.join(', '),
      is_published: article.is_published,
      is_featured: article.is_featured
    });
    setEditingArticle(article);
    setIsCreatingArticle(true);
  };

  const closeArticleEditor = () => {
    setIsCreatingArticle(false);
    setEditingArticle(null);
    resetArticleForm();
  };

  const saveArticle = async () => {
    try {
      const payload = {
        title: articleForm.title,
        slug: articleForm.slug || undefined,
        excerpt: articleForm.excerpt || undefined,
        content: articleForm.content,
        cover_image: articleForm.cover_image || undefined,
        category: articleForm.category,
        tags: articleForm.tags.split(',').map(t => t.trim()).filter(Boolean),
        is_published: articleForm.is_published,
        is_featured: articleForm.is_featured
      };

      if (editingArticle) {
        await api.put(`/admin/articles/${editingArticle.id}`, { body: payload });
      } else {
        await api.post('/admin/articles', { body: payload });
      }

      closeArticleEditor();
      fetchData();
    } catch (err) {
      if (err instanceof ApiError) {
        alert(err.detail || 'Ошибка сохранения');
      } else {
        console.error(err);
        alert('Ошибка сохранения статьи');
      }
    }
  };

  const deleteArticle = async (id: number) => {
    if (!confirm('Удалить статью?')) return;
    
    try {
      await api.delete(`/admin/articles/${id}`);
      fetchData();
    } catch (err) {
      console.error(err);
    }
  };

  const togglePublish = async (id: number, isPublished: boolean) => {
    try {
      await api.post(`/admin/articles/${id}/${isPublished ? 'unpublish' : 'publish'}`);
      fetchData();
    } catch (err) {
      console.error(err);
    }
  };

  const formatDate = (dateStr: string | null) => {
    if (!dateStr) return '—';
    return new Date(dateStr).toLocaleDateString('ru-RU', {
      day: 'numeric',
      month: 'short',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    });
  };

  const getSourceLabel = (source: string) => {
    const labels: Record<string, string> = {
      email: 'Email',
      google: 'Google',
      yandex: 'Яндекс',
      sber: 'Сбер ID',
      tinkoff: 'Тинькофф'
    };
    return labels[source] || source;
  };

  if (!user?.is_admin) {
    return (
      <main className="min-h-screen flex items-center justify-center p-8">
        <div className="cyber-card p-8 max-w-md text-center">
          <Shield size={48} className="text-red-400 mx-auto mb-4" />
          <h1 className="text-xl font-bold mb-2">Доступ запрещён</h1>
          <p className="text-muted-foreground mb-4">
            У вас нет прав для доступа к административной панели.
          </p>
          <Link href="/" className="btn-primary">
            Вернуться на главную
          </Link>
        </div>
      </main>
    );
  }

  if (error) {
    return (
      <main className="min-h-screen flex items-center justify-center p-8">
        <div className="cyber-card p-8 max-w-md text-center">
          <AlertTriangle size={48} className="text-yellow-400 mx-auto mb-4" />
          <h1 className="text-xl font-bold mb-2">Ошибка</h1>
          <p className="text-muted-foreground mb-4">{error}</p>
          <button onClick={fetchData} className="btn-primary">
            Попробовать снова
          </button>
        </div>
      </main>
    );
  }

  return (
    <AppShell pageTitle="Админ-панель">
    <main className="p-6 md:p-8">
      <div className="relative max-w-7xl mx-auto">
        {/* Header */}
        <header className="flex items-center justify-between mb-8">
          <div className="flex items-center gap-4">
            <Link 
              href="/" 
              className="p-2 hover:bg-secondary rounded-lg transition-colors"
            >
              <ArrowLeft size={20} />
            </Link>
            <div>
              <h1 className="text-2xl font-bold flex items-center gap-2">
                <Shield className="text-purple-400" />
                Админ-панель
              </h1>
              <p className="text-sm text-muted-foreground">
                Метрики и управление пользователями
              </p>
            </div>
          </div>
          
          <button 
            onClick={fetchData}
            disabled={loading}
            className="btn-secondary flex items-center gap-2"
          >
            <RefreshCw size={16} className={loading ? 'animate-spin' : ''} />
            Обновить
          </button>
        </header>

        {/* Tabs */}
        <div className="flex gap-2 mb-6 border-b border-white/10 pb-2 overflow-x-auto">
          {ADMIN_TABS.map(tab => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`flex items-center gap-2 px-4 py-2 rounded-lg transition-colors ${
                activeTab === tab.id 
                  ? 'bg-purple-500/20 text-purple-400' 
                  : 'hover:bg-secondary text-muted-foreground'
              }`}
            >
              <tab.icon size={16} />
              {tab.label}
            </button>
          ))}
        </div>

        {loading && !stats ? (
          <div className="flex items-center justify-center py-20">
            <Loader2 className="w-8 h-8 animate-spin text-purple-400" />
          </div>
        ) : (
          <>
            {/* Overview Tab */}
            {activeTab === 'overview' && stats && (
              <div className="space-y-6">
                {/* PR 26 Phase 2: Quick links на новые admin pages */}
                <div className="cyber-card p-4">
                  <div className="text-xs uppercase text-muted-foreground mb-3">Operations</div>
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
                    <a href="/admin/health" className="px-3 py-2 bg-slate-800/50 hover:bg-slate-700/50 rounded text-sm flex items-center gap-2 transition-colors">
                      <span className="text-blue-400">●</span> Sync Health
                    </a>
                    <a href="/admin/api-health" className="px-3 py-2 bg-slate-800/50 hover:bg-slate-700/50 rounded text-sm flex items-center gap-2 transition-colors">
                      <span className="text-purple-400">●</span> API Health
                    </a>
                    <a href="/admin/audit" className="px-3 py-2 bg-slate-800/50 hover:bg-slate-700/50 rounded text-sm flex items-center gap-2 transition-colors">
                      <span className="text-yellow-400">●</span> Audit Log
                    </a>
                    <a href="/admin/infra" className="px-3 py-2 bg-slate-800/50 hover:bg-slate-700/50 rounded text-sm flex items-center gap-2 transition-colors">
                      <span className="text-green-400">●</span> Infra
                    </a>
                  </div>
                  <div className="text-[11px] text-slate-500 mt-2">
                    Tip: на странице «Пользователи» → клик по строке → User 360 / Verify / Force resync
                  </div>
                </div>

                {/* KPI Cards - Row 1 */}
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                  <div className="cyber-card p-4">
                    <div className="flex items-center gap-2 text-muted-foreground mb-2">
                      <Users size={16} />
                      <span className="text-xs">Всего пользователей</span>
                    </div>
                    <div className="text-3xl font-bold">{stats.users.total}</div>
                    <div className="text-xs text-green-400">+{stats.users.new_this_week} за неделю</div>
                  </div>
                  
                  <div className="cyber-card p-4">
                    <div className="flex items-center gap-2 text-muted-foreground mb-2">
                      <CreditCard size={16} className="text-green-400" />
                      <span className="text-xs">Платных</span>
                    </div>
                    <div className="text-3xl font-bold text-green-400">{revenue?.overview.paid_users || 0}</div>
                    <div className="text-xs text-muted-foreground">
                      {revenue?.overview.conversion_rate || 0}% конверсия
                    </div>
                  </div>
                  
                  <div className="cyber-card p-4">
                    <div className="flex items-center gap-2 text-muted-foreground mb-2">
                      <DollarSign size={16} className="text-yellow-400" />
                      <span className="text-xs">MRR</span>
                    </div>
                    <div className="text-3xl font-bold text-yellow-400">
                      ₽{(revenue?.revenue.mrr || 0).toLocaleString()}
                    </div>
                    <div className="text-xs text-muted-foreground">
                      ARR: ₽{((revenue?.revenue.arr || 0) / 1000).toFixed(0)}k
                    </div>
                  </div>
                  
                  <div className="cyber-card p-4">
                    <div className="flex items-center gap-2 text-muted-foreground mb-2">
                      <Activity size={16} />
                      <span className="text-xs">DAU / MAU</span>
                    </div>
                    <div className="text-3xl font-bold">
                      {stats.activity.dau} / {stats.activity.mau}
                    </div>
                    <div className="text-xs text-purple-400">
                      Stickiness: {stats.activity.dau_mau_ratio}%
                    </div>
                  </div>
                  
                  <div className="cyber-card p-4">
                    <div className="flex items-center gap-2 text-muted-foreground mb-2">
                      <TrendingUp size={16} />
                      <span className="text-xs">Всего сделок</span>
                    </div>
                    <div className="text-3xl font-bold">{stats.engagement.total_trades}</div>
                    <div className="text-xs text-blue-400">
                      +{stats.engagement.trades_this_week} за неделю
                    </div>
                  </div>
                  
                  <div className="cyber-card p-4">
                    <div className="flex items-center gap-2 text-muted-foreground mb-2">
                      <Target size={16} />
                      <span className="text-xs">Сделок на юзера</span>
                    </div>
                    <div className="text-3xl font-bold">{stats.engagement.avg_trades_per_user}</div>
                    <div className="text-xs text-muted-foreground">в среднем</div>
                  </div>
                </div>

                {/* Charts Row */}
                <div className="grid md:grid-cols-2 gap-6">
                  {/* User Growth Chart */}
                  <div className="cyber-card p-4">
                    <h3 className="font-bold mb-4 flex items-center gap-2">
                      <TrendingUp size={16} className="text-green-400" />
                      Рост пользователей (30 дней)
                    </h3>
                    <ResponsiveContainer width="100%" height={250}>
                      <LineChart data={growth}>
                        <CartesianGrid strokeDasharray="3 3" stroke="#333" />
                        <XAxis 
                          dataKey="date" 
                          tick={{ fontSize: 10, fill: '#888' }}
                          tickFormatter={(v) => new Date(v).toLocaleDateString('ru-RU', { day: 'numeric', month: 'short' })}
                        />
                        <YAxis tick={{ fontSize: 10, fill: '#888' }} />
                        <Tooltip 
                          contentStyle={{ background: '#1a1a2e', border: '1px solid #333' }}
                          labelFormatter={(v) => new Date(v).toLocaleDateString('ru-RU')}
                        />
                        <Line 
                          type="monotone" 
                          dataKey="total_users" 
                          stroke="#22c55e" 
                          strokeWidth={2}
                          dot={false}
                          name="Всего"
                        />
                        <Line 
                          type="monotone" 
                          dataKey="new_users" 
                          stroke="#d4a13a" 
                          strokeWidth={2}
                          dot={false}
                          name="Новых"
                        />
                      </LineChart>
                    </ResponsiveContainer>
                  </div>

                  {/* Registration Sources */}
                  <div className="cyber-card p-4">
                    <h3 className="font-bold mb-4 flex items-center gap-2">
                      <PieChart size={16} className="text-purple-400" />
                      Источники регистрации
                    </h3>
                    <div className="flex items-center gap-4">
                      <ResponsiveContainer width="50%" height={200}>
                        <RechartsPie>
                          <Pie
                            data={registrationSourceChartData}
                            dataKey="count"
                            nameKey="source"
                            cx="50%"
                            cy="50%"
                            innerRadius={40}
                            outerRadius={80}
                          >
                            {sources.map((entry, index) => (
                              <Cell 
                                key={entry.source} 
                                fill={SOURCE_COLORS[entry.source] || COLORS[index % COLORS.length]} 
                              />
                            ))}
                          </Pie>
                          <Tooltip 
                            contentStyle={{ background: '#1a1a2e', border: '1px solid #333' }}
                            formatter={(value, name) => [value, getSourceLabel(String(name))]}
                          />
                        </RechartsPie>
                      </ResponsiveContainer>
                      <div className="space-y-2">
                        {sources.map(s => (
                          <div key={s.source} className="flex items-center gap-2 text-sm">
                            <div 
                              className="w-3 h-3 rounded-full" 
                              style={{ background: SOURCE_COLORS[s.source] || '#d4a13a' }}
                            />
                            <span>{getSourceLabel(s.source)}</span>
                            <span className="text-muted-foreground">
                              {s.count} ({s.percentage}%)
                            </span>
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>
                </div>

                {/* Conversion Funnel */}
                <div className="cyber-card p-4">
                  <h3 className="font-bold mb-4 flex items-center gap-2">
                    <Target size={16} className="text-blue-400" />
                    Воронка конверсии
                  </h3>
                  <div className="grid grid-cols-4 gap-4">
                    {funnel.map((step, i) => (
                      <div 
                        key={step.name}
                        className="relative p-4 rounded-lg text-center"
                        style={{ 
                          background: `linear-gradient(135deg, rgba(99, 102, 241, ${0.3 - i * 0.05}) 0%, rgba(99, 102, 241, ${0.1 - i * 0.02}) 100%)` 
                        }}
                      >
                        <div className="text-2xl font-bold">{step.count}</div>
                        <div className="text-xs text-muted-foreground mt-1">{step.name}</div>
                        <div className="text-xs text-purple-400 mt-1">{step.rate}%</div>
                        {i < funnel.length - 1 && (
                          <div className="absolute -right-2 top-1/2 -translate-y-1/2 text-muted-foreground">
                            →
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            )}

            {/* Revenue Tab */}
            {activeTab === 'revenue' && revenue && (
              <div className="space-y-6">
                {/* Revenue KPI Cards */}
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                  <div className="cyber-card p-4 border-l-4 border-green-500">
                    <div className="flex items-center gap-2 text-muted-foreground mb-2">
                      <DollarSign size={16} />
                      <span className="text-xs">Выручка за месяц</span>
                    </div>
                    <div className="text-3xl font-bold text-green-400">
                      ₽{revenue.revenue.this_month.toLocaleString()}
                    </div>
                    <div className="text-xs text-muted-foreground">
                      Всего: ₽{revenue.revenue.total.toLocaleString()}
                    </div>
                  </div>
                  
                  <div className="cyber-card p-4 border-l-4 border-yellow-500">
                    <div className="flex items-center gap-2 text-muted-foreground mb-2">
                      <Repeat size={16} />
                      <span className="text-xs">MRR</span>
                    </div>
                    <div className="text-3xl font-bold text-yellow-400">
                      ₽{revenue.revenue.mrr.toLocaleString()}
                    </div>
                    <div className="text-xs text-muted-foreground">
                      ARR: ₽{(revenue.revenue.arr / 1000).toFixed(0)}k
                    </div>
                  </div>
                  
                  <div className="cyber-card p-4 border-l-4 border-purple-500">
                    <div className="flex items-center gap-2 text-muted-foreground mb-2">
                      <CreditCard size={16} />
                      <span className="text-xs">Средний чек</span>
                    </div>
                    <div className="text-3xl font-bold">
                      ₽{revenue.revenue.avg_payment.toLocaleString()}
                    </div>
                    <div className="text-xs text-muted-foreground">
                      {revenue.health.total_payments} платежей
                    </div>
                  </div>
                  
                  <div className="cyber-card p-4 border-l-4 border-red-500">
                    <div className="flex items-center gap-2 text-muted-foreground mb-2">
                      <TrendingDown size={16} />
                      <span className="text-xs">Churn Rate</span>
                    </div>
                    <div className="text-3xl font-bold text-red-400">
                      {revenue.health.churn_rate}%
                    </div>
                    <div className="text-xs text-muted-foreground">
                      -{revenue.health.churned_this_month} за месяц
                    </div>
                  </div>
                </div>

                {/* Revenue Chart + Plan Distribution */}
                <div className="grid md:grid-cols-2 gap-6">
                  {/* Revenue Growth Chart */}
                  <div className="cyber-card p-4">
                    <h3 className="font-bold mb-4 flex items-center gap-2">
                      <TrendingUp size={16} className="text-green-400" />
                      Динамика выручки (30 дней)
                    </h3>
                    <ResponsiveContainer width="100%" height={250}>
                      <BarChart data={revenueGrowth}>
                        <CartesianGrid strokeDasharray="3 3" stroke="#333" />
                        <XAxis 
                          dataKey="date" 
                          tick={{ fontSize: 10, fill: '#888' }}
                          tickFormatter={(v) => v ? new Date(v).toLocaleDateString('ru-RU', { day: 'numeric', month: 'short' }) : ''}
                        />
                        <YAxis tick={{ fontSize: 10, fill: '#888' }} />
                        <Tooltip 
                          contentStyle={{ background: '#1a1a2e', border: '1px solid #333' }}
                          labelFormatter={(v) => v ? new Date(v).toLocaleDateString('ru-RU') : ''}
                          formatter={(value) => [`₽${(value || 0).toLocaleString()}`, 'Выручка']}
                        />
                        <Bar dataKey="revenue" fill="#22c55e" radius={[4, 4, 0, 0]} />
                      </BarChart>
                    </ResponsiveContainer>
                  </div>

                  {/* Plan Distribution */}
                  <div className="cyber-card p-4">
                    <h3 className="font-bold mb-4 flex items-center gap-2">
                      <PieChart size={16} className="text-purple-400" />
                      Распределение по тарифам
                    </h3>
                    <div className="space-y-4">
                      {[
                        { key: 'free', label: 'Free', color: '#6b7280', price: 0 },
                        { key: 'pro', label: 'Pro', color: '#d4a13a', price: 399 },
                        { key: 'corporate', label: 'Corporate', color: '#f59e0b', price: null },
                      ].map(plan => {
                        const count = revenue.plans[plan.key as keyof typeof revenue.plans];
                        const total = Object.values(revenue.plans).reduce((a, b) => a + b, 0);
                        const percent = total > 0 ? (count / total * 100) : 0;
                        return (
                          <div key={plan.key} className="space-y-1">
                            <div className="flex justify-between text-sm">
                              <span className="flex items-center gap-2">
                                <span className="w-3 h-3 rounded" style={{ background: plan.color }} />
                                {plan.label}
                                {plan.price !== null && plan.price > 0 && (
                                  <span className="text-muted-foreground">₽{plan.price}/мес</span>
                                )}
                                {plan.price === null && (
                                  <span className="text-muted-foreground text-xs">индивидуально</span>
                                )}
                              </span>
                              <span className="font-bold">{count}</span>
                            </div>
                            <div className="h-2 bg-secondary rounded-full overflow-hidden">
                              <div 
                                className="h-full rounded-full transition-all"
                                style={{ width: `${percent}%`, background: plan.color }}
                              />
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                </div>

                {/* Additional Metrics Row */}
                <div className="grid md:grid-cols-3 gap-4">
                  {/* Subscription Health */}
                  <div className="cyber-card p-4">
                    <h4 className="font-bold mb-3 flex items-center gap-2">
                      <Zap size={16} className="text-yellow-400" />
                      Здоровье подписок
                    </h4>
                    <div className="space-y-3">
                      <div className="flex justify-between">
                        <span className="text-muted-foreground">LTV</span>
                        <span className="font-bold">₽{subscriptionAnalytics?.ltv.toLocaleString()}</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-muted-foreground">Платящих всего</span>
                        <span className="font-bold">{subscriptionAnalytics?.paying_users_total}</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-muted-foreground">Auto-renew %</span>
                        <span className="font-bold text-green-400">{subscriptionAnalytics?.auto_renew.rate}%</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-muted-foreground">Истекает скоро</span>
                        <span className={`font-bold ${(subscriptionAnalytics?.expiring_soon || 0) > 0 ? 'text-yellow-400' : ''}`}>
                          {subscriptionAnalytics?.expiring_soon}
                        </span>
                      </div>
                    </div>
                  </div>

                  {/* New vs Churned */}
                  <div className="cyber-card p-4">
                    <h4 className="font-bold mb-3 flex items-center gap-2">
                      <Activity size={16} className="text-blue-400" />
                      Динамика за месяц
                    </h4>
                    <div className="space-y-3">
                      <div className="flex justify-between items-center">
                        <span className="text-muted-foreground">Новых платных</span>
                        <span className="font-bold text-green-400">+{revenue.health.new_paid_this_month}</span>
                      </div>
                      <div className="flex justify-between items-center">
                        <span className="text-muted-foreground">Ушло (churn)</span>
                        <span className="font-bold text-red-400">-{revenue.health.churned_this_month}</span>
                      </div>
                      <div className="border-t border-white/10 pt-2">
                        <div className="flex justify-between items-center">
                          <span className="text-muted-foreground">Net</span>
                          <span className={`font-bold ${
                            revenue.health.new_paid_this_month - revenue.health.churned_this_month >= 0 
                              ? 'text-green-400' : 'text-red-400'
                          }`}>
                            {revenue.health.new_paid_this_month - revenue.health.churned_this_month >= 0 ? '+' : ''}
                            {revenue.health.new_paid_this_month - revenue.health.churned_this_month}
                          </span>
                        </div>
                      </div>
                    </div>
                  </div>

                  {/* Payment Methods */}
                  <div className="cyber-card p-4">
                    <h4 className="font-bold mb-3 flex items-center gap-2">
                      <CreditCard size={16} className="text-purple-400" />
                      Способы оплаты
                    </h4>
                    {subscriptionAnalytics?.payment_methods.length ? (
                      <div className="space-y-2">
                        {subscriptionAnalytics.payment_methods.map(pm => (
                          <div key={pm.method} className="flex justify-between text-sm">
                            <span className="capitalize">{pm.method}</span>
                            <span>
                              <span className="font-bold">{pm.count}</span>
                              <span className="text-muted-foreground ml-2">
                                ₽{pm.amount.toLocaleString()}
                              </span>
                            </span>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <p className="text-muted-foreground text-sm">Нет данных о платежах</p>
                    )}
                  </div>
                </div>

                {/* Top Paying Users */}
                {topPayingUsers.length > 0 && (
                  <div className="cyber-card p-4">
                    <h3 className="font-bold mb-4 flex items-center gap-2">
                      <Crown size={16} className="text-yellow-400" />
                      Топ платящих пользователей
                    </h3>
                    <div className="overflow-x-auto">
                      <table className="w-full text-sm">
                        <thead>
                          <tr className="border-b border-white/10">
                            <th className="text-left p-2 text-muted-foreground">#</th>
                            <th className="text-left p-2 text-muted-foreground">Пользователь</th>
                            <th className="text-right p-2 text-muted-foreground">Платежей</th>
                            <th className="text-right p-2 text-muted-foreground">Сумма</th>
                          </tr>
                        </thead>
                        <tbody>
                          {topPayingUsers.map((u, i) => (
                            <tr key={u.id} className="border-b border-white/5">
                              <td className="p-2 text-muted-foreground">{i + 1}</td>
                              <td className="p-2">
                                <div className="font-medium">{u.name || u.email}</div>
                                {u.name && <div className="text-xs text-muted-foreground">{u.email}</div>}
                              </td>
                              <td className="p-2 text-right">{u.payments_count}</td>
                              <td className="p-2 text-right font-bold text-green-400">
                                ₽{u.total_paid.toLocaleString()}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* Users Tab */}
            {activeTab === 'users' && (
              <div className="space-y-4">
                {/* Filters */}
                <div className="cyber-card p-4 flex flex-wrap gap-4 items-center">
                  <div className="relative flex-1 min-w-[200px]">
                    <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
                    <input
                      type="text"
                      placeholder="Поиск по email или имени..."
                      value={searchQuery}
                      onChange={(e) => setSearchQuery(e.target.value)}
                      className="w-full pl-10 pr-4 py-2 bg-secondary/50 border border-white/10 rounded-lg
                               text-sm focus:outline-none focus:ring-2 focus:ring-purple-500/50"
                    />
                  </div>
                  
                  <select
                    value={sourceFilter}
                    onChange={(e) => setSourceFilter(e.target.value)}
                    className="px-3 py-2 bg-secondary/50 border border-white/10 rounded-lg text-sm"
                  >
                    <option value="">Все источники</option>
                    <option value="email">Email</option>
                    <option value="google">Google</option>
                    <option value="yandex">Яндекс</option>
                    <option value="sber">Сбер ID</option>
                    <option value="tinkoff">Тинькофф</option>
                  </select>
                  
                  <select
                    value={`${sortBy}-${sortOrder}`}
                    onChange={(e) => {
                      const [field, order] = e.target.value.split('-');
                      setSortBy(field);
                      setSortOrder(order as 'asc' | 'desc');
                    }}
                    className="px-3 py-2 bg-secondary/50 border border-white/10 rounded-lg text-sm"
                  >
                    <option value="created_at-desc">Новые первыми</option>
                    <option value="created_at-asc">Старые первыми</option>
                    <option value="last_login-desc">По активности</option>
                  </select>
                  
                  <div className="text-sm text-muted-foreground">
                    Найдено: {usersTotal}
                  </div>
                </div>

                {/* Users Table */}
                <div className="cyber-card overflow-hidden">
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="border-b border-white/10">
                          <th className="text-left p-3 text-muted-foreground font-medium">Пользователь</th>
                          <th className="text-left p-3 text-muted-foreground font-medium">Источник</th>
                          <th className="text-left p-3 text-muted-foreground font-medium">Регистрация</th>
                          <th className="text-left p-3 text-muted-foreground font-medium">Последний вход</th>
                          <th className="text-center p-3 text-muted-foreground font-medium">Сделок</th>
                          <th className="text-center p-3 text-muted-foreground font-medium">Статус</th>
                          <th className="text-right p-3 text-muted-foreground font-medium">Действия</th>
                        </tr>
                      </thead>
                      <tbody>
                        {users.map(u => (
                          <tr key={u.id} className="border-b border-white/5 hover:bg-secondary/30">
                            <td className="p-3">
                              <div className="flex items-center gap-3">
                                <div className="w-8 h-8 rounded-full bg-purple-500/20 flex items-center justify-center">
                                  <span className="text-xs font-bold text-purple-400">
                                    {(u.name || u.email)[0].toUpperCase()}
                                  </span>
                                </div>
                                <div>
                                  <div className="font-medium flex items-center gap-1">
                                    {u.name || '—'}
                                    {u.is_admin && <Crown size={12} className="text-yellow-400" />}
                                  </div>
                                  <div className="text-xs text-muted-foreground">{u.email}</div>
                                </div>
                              </div>
                            </td>
                            <td className="p-3">
                              <span 
                                className="px-2 py-1 rounded text-xs font-medium"
                                style={{ 
                                  background: `${SOURCE_COLORS[u.registration_source] || '#d4a13a'}20`,
                                  color: SOURCE_COLORS[u.registration_source] || '#d4a13a'
                                }}
                              >
                                {getSourceLabel(u.registration_source)}
                              </span>
                            </td>
                            <td className="p-3 text-muted-foreground text-xs">
                              {formatDate(u.created_at)}
                            </td>
                            <td className="p-3 text-muted-foreground text-xs">
                              {formatDate(u.last_login)}
                            </td>
                            <td className="p-3 text-center">
                              <span className={u.trades_count > 0 ? 'text-green-400' : 'text-muted-foreground'}>
                                {u.trades_count}
                              </span>
                            </td>
                            <td className="p-3 text-center">
                              {u.is_active ? (
                                <span className="text-green-400 text-xs">Активен</span>
                              ) : (
                                <span className="text-red-400 text-xs">Заблокирован</span>
                              )}
                            </td>
                            <td className="p-3 text-right">
                              <div className="flex gap-1 justify-end">
                                {/* PR 26 Phase 2: ссылка на User 360 detail page */}
                                <a
                                  href={`/admin/users/${u.id}`}
                                  className="p-1.5 rounded hover:bg-blue-500/20 hover:text-blue-400 text-muted-foreground transition-colors"
                                  title="Открыть User 360"
                                >
                                  <Activity size={14} />
                                </a>
                                <button
                                  onClick={() => toggleUserAdmin(u.id, !u.is_admin)}
                                  className={`p-1.5 rounded transition-colors ${
                                    u.is_admin
                                      ? 'bg-yellow-500/20 text-yellow-400'
                                      : 'hover:bg-secondary text-muted-foreground'
                                  }`}
                                  title={u.is_admin ? 'Снять админа' : 'Сделать админом'}
                                >
                                  <Crown size={14} />
                                </button>
                                <button
                                  onClick={() => toggleUserActive(u.id)}
                                  className={`p-1.5 rounded transition-colors ${
                                    u.is_active
                                      ? 'hover:bg-red-500/20 hover:text-red-400 text-muted-foreground'
                                      : 'bg-red-500/20 text-red-400'
                                  }`}
                                  title={u.is_active ? 'Заблокировать' : 'Разблокировать'}
                                >
                                  {u.is_active ? <UserX size={14} /> : <UserCheck size={14} />}
                                </button>
                              </div>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  
                  {/* Pagination */}
                  {usersTotal > pageSize && (
                    <div className="flex items-center justify-between p-3 border-t border-white/10">
                      <button
                        onClick={() => setCurrentPage(p => Math.max(0, p - 1))}
                        disabled={currentPage === 0}
                        className="btn-secondary text-sm disabled:opacity-50"
                      >
                        ← Назад
                      </button>
                      <span className="text-sm text-muted-foreground">
                        Стр. {currentPage + 1} из {Math.ceil(usersTotal / pageSize)}
                      </span>
                      <button
                        onClick={() => setCurrentPage(p => p + 1)}
                        disabled={(currentPage + 1) * pageSize >= usersTotal}
                        className="btn-secondary text-sm disabled:opacity-50"
                      >
                        Вперёд →
                      </button>
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* Phase 10 (2026-05-17): P&L Health Check Tab */}
            {activeTab === 'pnl-health' && (
              <PnLHealthTab />
            )}

            {/* Blog Tab */}
            {activeTab === 'blog' && (
              <div className="space-y-6">
                {/* Article Editor Modal */}
                {isCreatingArticle && (
                  <div className="fixed inset-0 bg-black/70 backdrop-blur-sm z-50 flex items-start justify-center overflow-y-auto py-8">
                    <div className="cyber-card w-full max-w-4xl mx-4">
                      <div className="flex items-center justify-between p-4 border-b border-white/10">
                        <h2 className="text-xl font-bold">
                          {editingArticle ? 'Редактирование статьи' : 'Новая статья'}
                        </h2>
                        <button onClick={closeArticleEditor} className="p-2 hover:bg-secondary rounded-lg">
                          <X size={20} />
                        </button>
                      </div>
                      
                      <div className="p-4 space-y-4 max-h-[70vh] overflow-y-auto">
                        {/* Title */}
                        <div>
                          <label className="block text-sm font-medium mb-1">Заголовок *</label>
                          <input
                            type="text"
                            value={articleForm.title}
                            onChange={(e) => setArticleForm({...articleForm, title: e.target.value})}
                            className="w-full p-3 bg-secondary border border-white/10 rounded-lg"
                            placeholder="Как вести торговый дневник"
                          />
                        </div>
                        
                        {/* Slug */}
                        <div>
                          <label className="block text-sm font-medium mb-1">URL (slug)</label>
                          <input
                            type="text"
                            value={articleForm.slug}
                            onChange={(e) => setArticleForm({...articleForm, slug: e.target.value})}
                            className="w-full p-3 bg-secondary border border-white/10 rounded-lg"
                            placeholder="kak-vesti-torgovyy-dnevnik (auto)"
                          />
                        </div>
                        
                        {/* Category & Cover */}
                        <div className="grid md:grid-cols-2 gap-4">
                          <div>
                            <label className="block text-sm font-medium mb-1">Категория</label>
                            <select
                              value={articleForm.category}
                              onChange={(e) => setArticleForm({...articleForm, category: e.target.value})}
                              className="w-full p-3 bg-secondary border border-white/10 rounded-lg"
                            >
                              <option value="news">Новости</option>
                              <option value="guides">Гайды</option>
                              <option value="analytics">Аналитика</option>
                              <option value="tips">Советы</option>
                              <option value="updates">Обновления</option>
                            </select>
                          </div>
                          <div>
                            <label className="block text-sm font-medium mb-1">Обложка (URL)</label>
                            <input
                              type="text"
                              value={articleForm.cover_image}
                              onChange={(e) => setArticleForm({...articleForm, cover_image: e.target.value})}
                              className="w-full p-3 bg-secondary border border-white/10 rounded-lg"
                              placeholder="https://example.com/image.jpg"
                            />
                          </div>
                        </div>
                        
                        {/* Excerpt */}
                        <div>
                          <label className="block text-sm font-medium mb-1">Краткое описание</label>
                          <textarea
                            value={articleForm.excerpt}
                            onChange={(e) => setArticleForm({...articleForm, excerpt: e.target.value})}
                            className="w-full p-3 bg-secondary border border-white/10 rounded-lg h-20"
                            placeholder="Краткое описание для превью статьи..."
                          />
                        </div>
                        
                        {/* Content */}
                        <div>
                          <label className="block text-sm font-medium mb-1">Содержимое * (Markdown)</label>
                          <textarea
                            value={articleForm.content}
                            onChange={(e) => setArticleForm({...articleForm, content: e.target.value})}
                            className="w-full p-3 bg-secondary border border-white/10 rounded-lg h-64 font-mono text-sm"
                            placeholder="# Заголовок&#10;&#10;Текст статьи...&#10;&#10;## Подзаголовок&#10;&#10;**Жирный текст** и *курсив*"
                          />
                        </div>
                        
                        {/* Tags */}
                        <div>
                          <label className="block text-sm font-medium mb-1">Теги (через запятую)</label>
                          <input
                            type="text"
                            value={articleForm.tags}
                            onChange={(e) => setArticleForm({...articleForm, tags: e.target.value})}
                            className="w-full p-3 bg-secondary border border-white/10 rounded-lg"
                            placeholder="трейдинг, психология, риск-менеджмент"
                          />
                        </div>
                        
                        {/* Flags */}
                        <div className="flex items-center gap-6">
                          <label className="flex items-center gap-2 cursor-pointer">
                            <input
                              type="checkbox"
                              checked={articleForm.is_published}
                              onChange={(e) => setArticleForm({...articleForm, is_published: e.target.checked})}
                              className="w-4 h-4 rounded"
                            />
                            <span>Опубликовать</span>
                          </label>
                          <label className="flex items-center gap-2 cursor-pointer">
                            <input
                              type="checkbox"
                              checked={articleForm.is_featured}
                              onChange={(e) => setArticleForm({...articleForm, is_featured: e.target.checked})}
                              className="w-4 h-4 rounded"
                            />
                            <span>В избранное</span>
                          </label>
                        </div>
                      </div>
                      
                      {/* Actions */}
                      <div className="flex items-center justify-end gap-3 p-4 border-t border-white/10">
                        <button onClick={closeArticleEditor} className="btn-secondary">
                          Отмена
                        </button>
                        <button 
                          onClick={saveArticle} 
                          className="btn-primary flex items-center gap-2"
                          disabled={!articleForm.title || !articleForm.content}
                        >
                          <Save size={16} />
                          {editingArticle ? 'Сохранить' : 'Создать'}
                        </button>
                      </div>
                    </div>
                  </div>
                )}

                {/* Header */}
                <div className="flex items-center justify-between">
                  <div>
                    <h2 className="text-xl font-bold">Управление статьями</h2>
                    <p className="text-sm text-muted-foreground">
                      {articles.length} статей • {articles.filter(a => a.is_published).length} опубликовано
                    </p>
                  </div>
                  <button onClick={openCreateArticle} className="btn-primary flex items-center gap-2">
                    <Plus size={16} />
                    Новая статья
                  </button>
                </div>
                
                {/* Articles List */}
                <div className="cyber-card overflow-hidden">
                  <div className="overflow-x-auto">
                    <table className="w-full">
                      <thead className="bg-secondary/50 border-b border-white/10">
                        <tr>
                          <th className="text-left p-3 font-medium">Статья</th>
                          <th className="text-left p-3 font-medium">Категория</th>
                          <th className="text-center p-3 font-medium">Статус</th>
                          <th className="text-center p-3 font-medium">Просмотры</th>
                          <th className="text-left p-3 font-medium">Дата</th>
                          <th className="text-right p-3 font-medium">Действия</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-white/5">
                        {articles.length === 0 ? (
                          <tr>
                            <td colSpan={6} className="p-8 text-center text-muted-foreground">
                              <FileText size={32} className="mx-auto mb-2 opacity-50" />
                              Статей пока нет. Создайте первую!
                            </td>
                          </tr>
                        ) : articles.map(article => (
                          <tr key={article.id} className="hover:bg-secondary/30">
                            <td className="p-3">
                              <div className="flex items-start gap-3">
                                {article.cover_image ? (
                                  <NextImage
                                    src={article.cover_image}
                                    alt={article.title}
                                    width={64}
                                    height={40}
                                    // FE-09: admin-input URL (arbitrary CDN), domain not predictable.
                                    unoptimized
                                    className="w-16 h-10 object-cover rounded"
                                  />
                                ) : (
                                  <div className="w-16 h-10 bg-secondary rounded flex items-center justify-center">
                                    <ImageIcon size={16} className="text-muted-foreground" />
                                  </div>
                                )}
                                <div>
                                  <p className="font-medium line-clamp-1">{article.title}</p>
                                  <p className="text-xs text-muted-foreground">/blog/{article.slug}</p>
                                </div>
                              </div>
                            </td>
                            <td className="p-3">
                              <span className={`px-2 py-1 rounded text-xs ${
                                article.category === 'news' ? 'bg-blue-500/20 text-blue-400' :
                                article.category === 'guides' ? 'bg-green-500/20 text-green-400' :
                                article.category === 'analytics' ? 'bg-purple-500/20 text-purple-400' :
                                article.category === 'tips' ? 'bg-yellow-500/20 text-yellow-400' :
                                'bg-cyan-500/20 text-cyan-400'
                              }`}>
                                {article.category === 'news' ? 'Новости' :
                                 article.category === 'guides' ? 'Гайды' :
                                 article.category === 'analytics' ? 'Аналитика' :
                                 article.category === 'tips' ? 'Советы' : 'Обновления'}
                              </span>
                              {article.is_featured && (
                                <span className="ml-1 px-1.5 py-0.5 bg-yellow-500/20 text-yellow-400 rounded text-xs">★</span>
                              )}
                            </td>
                            <td className="p-3 text-center">
                              {article.is_published ? (
                                <span className="inline-flex items-center gap-1 text-green-400 text-xs">
                                  <Eye size={12} /> Опубликовано
                                </span>
                              ) : (
                                <span className="inline-flex items-center gap-1 text-muted-foreground text-xs">
                                  <EyeOff size={12} /> Черновик
                                </span>
                              )}
                            </td>
                            <td className="p-3 text-center text-muted-foreground">
                              {article.views_count}
                            </td>
                            <td className="p-3 text-sm text-muted-foreground">
                              {formatDate(article.created_at)}
                            </td>
                            <td className="p-3">
                              <div className="flex gap-1 justify-end">
                                <button
                                  onClick={() => togglePublish(article.id, article.is_published)}
                                  className={`p-1.5 rounded transition-colors ${
                                    article.is_published 
                                      ? 'hover:bg-yellow-500/20 hover:text-yellow-400' 
                                      : 'hover:bg-green-500/20 hover:text-green-400'
                                  } text-muted-foreground`}
                                  title={article.is_published ? 'Снять с публикации' : 'Опубликовать'}
                                >
                                  {article.is_published ? <EyeOff size={14} /> : <Eye size={14} />}
                                </button>
                                <button
                                  onClick={() => openEditArticle(article)}
                                  className="p-1.5 rounded hover:bg-blue-500/20 hover:text-blue-400 text-muted-foreground transition-colors"
                                  title="Редактировать"
                                >
                                  <Edit size={14} />
                                </button>
                                <button
                                  onClick={() => deleteArticle(article.id)}
                                  className="p-1.5 rounded hover:bg-red-500/20 hover:text-red-400 text-muted-foreground transition-colors"
                                  title="Удалить"
                                >
                                  <Trash2 size={14} />
                                </button>
                                <Link
                                  href={`/blog/${article.slug}`}
                                  target="_blank"
                                  className="p-1.5 rounded hover:bg-secondary text-muted-foreground transition-colors"
                                  title="Открыть"
                                >
                                  <ChevronDown size={14} className="rotate-[-90deg]" />
                                </Link>
                              </div>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
                
                {/* Quick Stats */}
                <div className="grid md:grid-cols-4 gap-4">
                  <div className="cyber-card p-4 text-center">
                    <p className="text-2xl font-bold text-blue-400">{articles.filter(a => a.category === 'news').length}</p>
                    <p className="text-sm text-muted-foreground">Новостей</p>
                  </div>
                  <div className="cyber-card p-4 text-center">
                    <p className="text-2xl font-bold text-green-400">{articles.filter(a => a.category === 'guides').length}</p>
                    <p className="text-sm text-muted-foreground">Гайдов</p>
                  </div>
                  <div className="cyber-card p-4 text-center">
                    <p className="text-2xl font-bold text-purple-400">{articles.reduce((sum, a) => sum + a.views_count, 0)}</p>
                    <p className="text-sm text-muted-foreground">Всего просмотров</p>
                  </div>
                  <div className="cyber-card p-4 text-center">
                    <p className="text-2xl font-bold text-yellow-400">{articles.filter(a => a.is_featured).length}</p>
                    <p className="text-sm text-muted-foreground">В избранном</p>
                  </div>
                </div>
              </div>
            )}

            {/* Analytics Tab */}
            {activeTab === 'analytics' && stats && (
              <div className="space-y-6">
                {/* Detailed Metrics */}
                <div className="grid md:grid-cols-3 gap-4">
                  <div className="cyber-card p-4">
                    <h4 className="text-sm text-muted-foreground mb-3">Новые пользователи</h4>
                    <div className="space-y-2">
                      <div className="flex justify-between">
                        <span>Сегодня</span>
                        <span className="font-bold text-green-400">+{stats.users.new_today}</span>
                      </div>
                      <div className="flex justify-between">
                        <span>За неделю</span>
                        <span className="font-bold text-green-400">+{stats.users.new_this_week}</span>
                      </div>
                      <div className="flex justify-between">
                        <span>За месяц</span>
                        <span className="font-bold text-green-400">+{stats.users.new_this_month}</span>
                      </div>
                    </div>
                  </div>
                  
                  <div className="cyber-card p-4">
                    <h4 className="text-sm text-muted-foreground mb-3">Активность</h4>
                    <div className="space-y-2">
                      <div className="flex justify-between">
                        <span>DAU</span>
                        <span className="font-bold">{stats.activity.dau}</span>
                      </div>
                      <div className="flex justify-between">
                        <span>WAU</span>
                        <span className="font-bold">{stats.activity.wau}</span>
                      </div>
                      <div className="flex justify-between">
                        <span>MAU</span>
                        <span className="font-bold">{stats.activity.mau}</span>
                      </div>
                    </div>
                  </div>
                  
                  <div className="cyber-card p-4">
                    <h4 className="text-sm text-muted-foreground mb-3">Вовлечённость</h4>
                    <div className="space-y-2">
                      <div className="flex justify-between">
                        <span>Сделок сегодня</span>
                        <span className="font-bold">{stats.engagement.trades_today}</span>
                      </div>
                      <div className="flex justify-between">
                        <span>Сделок за неделю</span>
                        <span className="font-bold">{stats.engagement.trades_this_week}</span>
                      </div>
                      <div className="flex justify-between">
                        <span>Stickiness</span>
                        <span className="font-bold text-purple-400">{stats.activity.dau_mau_ratio}%</span>
                      </div>
                    </div>
                  </div>
                </div>

                {/* Info */}
                <div className="cyber-card p-4 border-purple-500/20">
                  <h4 className="font-bold mb-2">📊 Ключевые метрики для стартапа</h4>
                  <div className="grid md:grid-cols-2 gap-4 text-sm text-muted-foreground">
                    <div>
                      <p><strong className="text-foreground">DAU/MAU (Stickiness)</strong> — показывает насколько часто пользователи возвращаются. Хороший показатель: 20%+</p>
                      <p className="mt-2"><strong className="text-foreground">Retention</strong> — сколько пользователей остаются активными со временем</p>
                    </div>
                    <div>
                      <p><strong className="text-foreground">Конверсия воронки</strong> — показывает где теряются пользователи</p>
                      <p className="mt-2"><strong className="text-foreground">Источники</strong> — какие каналы привлечения работают лучше</p>
                    </div>
                  </div>
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </main>
    </AppShell>
  );
}

export default function AdminPage() {
  return (
    <RequireAuth>
      <AdminDashboard />
    </RequireAuth>
  );
}
