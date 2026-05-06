'use client';

import { useState, useEffect, useCallback } from 'react';
import Image from 'next/image';
import Link from 'next/link';
import { getApiUrl } from '@/lib/apiClient';
import { AppShell } from '@/components/AppShell';
import { 
  ArrowLeft, Search, Eye, Heart, Calendar, User,
  Newspaper, BookOpen, TrendingUp, Lightbulb, Sparkles,
  ChevronRight
} from 'lucide-react';

interface Article {
  id: number;
  slug: string;
  title: string;
  excerpt?: string;
  cover_image?: string;
  category: string;
  tags: string[];
  author_name?: string;
  views_count: number;
  likes_count: number;
  created_at: string;
  published_at?: string;
}

interface Category {
  id: string;
  name: string;
  count: number;
}

const categoryIcons: Record<string, React.ReactNode> = {
  news: <Newspaper size={16} />,
  guides: <BookOpen size={16} />,
  analytics: <TrendingUp size={16} />,
  tips: <Lightbulb size={16} />,
  updates: <Sparkles size={16} />
};

const categoryColors: Record<string, string> = {
  news: 'bg-blue-500/20 text-blue-400 border-blue-500/30',
  guides: 'bg-green-500/20 text-green-400 border-green-500/30',
  analytics: 'bg-purple-500/20 text-purple-400 border-purple-500/30',
  tips: 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30',
  updates: 'bg-cyan-500/20 text-cyan-400 border-cyan-500/30'
};

function formatDate(dateString: string) {
  const date = new Date(dateString);
  return date.toLocaleDateString('ru-RU', { 
    day: 'numeric', 
    month: 'long', 
    year: 'numeric' 
  });
}

function ArticleCard({ article }: { article: Article }) {
  return (
    <Link href={`/blog/${article.slug}`} className="group">
      <article className="card p-0 overflow-hidden hover:border-accent/50 transition-all h-full flex flex-col">
        {/* Cover Image */}
        <div className="aspect-video bg-secondary relative overflow-hidden">
          {article.cover_image ? (
            <Image
              src={article.cover_image} 
              alt={article.title}
              fill
              sizes="(max-width: 768px) 100vw, 33vw"
              unoptimized
              className="object-cover group-hover:scale-105 transition-transform duration-300"
            />
          ) : (
            <div className="w-full h-full flex items-center justify-center bg-gradient-to-br from-accent/20 to-purple-600/20">
              {categoryIcons[article.category] || <Newspaper size={48} className="text-muted-foreground" />}
            </div>
          )}
          
          {/* Category Badge */}
          <div className={`absolute top-3 left-3 px-2 py-1 rounded-md text-xs font-medium border ${categoryColors[article.category] || 'bg-secondary text-foreground'}`}>
            <div className="flex items-center gap-1">
              {categoryIcons[article.category]}
              <span>{article.category === 'news' ? 'Новости' : 
                     article.category === 'guides' ? 'Гайды' :
                     article.category === 'analytics' ? 'Аналитика' :
                     article.category === 'tips' ? 'Советы' : 'Обновления'}</span>
            </div>
          </div>
        </div>
        
        {/* Content */}
        <div className="p-4 flex-1 flex flex-col">
          <h3 className="font-semibold text-lg mb-2 group-hover:text-accent transition-colors line-clamp-2">
            {article.title}
          </h3>
          
          {article.excerpt && (
            <p className="text-muted-foreground text-sm mb-4 line-clamp-2 flex-1">
              {article.excerpt}
            </p>
          )}
          
          {/* Tags */}
          {article.tags && article.tags.length > 0 && (
            <div className="flex flex-wrap gap-1 mb-3">
              {article.tags.slice(0, 3).map(tag => (
                <span key={tag} className="px-2 py-0.5 bg-secondary rounded text-xs text-muted-foreground">
                  #{tag}
                </span>
              ))}
            </div>
          )}
          
          {/* Meta */}
          <div className="flex items-center justify-between text-xs text-muted-foreground pt-3 border-t border-border">
            <div className="flex items-center gap-3">
              <span className="flex items-center gap-1">
                <Calendar size={12} />
                {article.published_at ? formatDate(article.published_at) : formatDate(article.created_at)}
              </span>
            </div>
            <div className="flex items-center gap-3">
              <span className="flex items-center gap-1">
                <Eye size={12} />
                {article.views_count}
              </span>
              <span className="flex items-center gap-1">
                <Heart size={12} />
                {article.likes_count}
              </span>
            </div>
          </div>
        </div>
      </article>
    </Link>
  );
}

function FeaturedArticle({ article }: { article: Article }) {
  return (
    <Link href={`/blog/${article.slug}`} className="group">
      <article className="card p-0 overflow-hidden hover:border-accent/50 transition-all">
        <div className="grid md:grid-cols-2 gap-0">
          {/* Cover Image */}
          <div className="aspect-video md:aspect-auto bg-secondary relative overflow-hidden">
            {article.cover_image ? (
              <Image
                src={article.cover_image} 
                alt={article.title}
                fill
                sizes="(max-width: 768px) 100vw, 50vw"
                unoptimized
                className="object-cover group-hover:scale-105 transition-transform duration-300"
              />
            ) : (
              <div className="w-full h-full flex items-center justify-center bg-gradient-to-br from-accent/30 to-purple-600/30 min-h-[200px]">
                <Sparkles size={64} className="text-accent" />
              </div>
            )}
          </div>
          
          {/* Content */}
          <div className="p-6 flex flex-col justify-center">
            <div className={`inline-flex w-fit items-center gap-1 px-2 py-1 rounded-md text-xs font-medium border mb-3 ${categoryColors[article.category] || 'bg-secondary text-foreground'}`}>
              {categoryIcons[article.category]}
              <span>Избранное</span>
            </div>
            
            <h2 className="font-bold text-2xl mb-3 group-hover:text-accent transition-colors">
              {article.title}
            </h2>
            
            {article.excerpt && (
              <p className="text-muted-foreground mb-4 line-clamp-3">
                {article.excerpt}
              </p>
            )}
            
            <div className="flex items-center gap-4 text-sm text-muted-foreground">
              {article.author_name && (
                <span className="flex items-center gap-1">
                  <User size={14} />
                  {article.author_name}
                </span>
              )}
              <span className="flex items-center gap-1">
                <Calendar size={14} />
                {article.published_at ? formatDate(article.published_at) : formatDate(article.created_at)}
              </span>
              <span className="flex items-center gap-1">
                <Eye size={14} />
                {article.views_count} просмотров
              </span>
            </div>
          </div>
        </div>
      </article>
    </Link>
  );
}

export default function BlogPage() {
  const [articles, setArticles] = useState<Article[]>([]);
  const [featuredArticles, setFeaturedArticles] = useState<Article[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);
  const [popularArticles, setPopularArticles] = useState<Article[]>([]);
  const [selectedCategory, setSelectedCategory] = useState<string | null>(null);
  const [searchInput, setSearchInput] = useState('');
  const [appliedSearchQuery, setAppliedSearchQuery] = useState('');
  const [isLoading, setIsLoading] = useState(true);

  const loadData = useCallback(async () => {
    setIsLoading(true);
    try {
      const params = new URLSearchParams();
      if (selectedCategory) params.append('category', selectedCategory);
      if (appliedSearchQuery) params.append('search', appliedSearchQuery);
      
      const [articlesRes, featuredRes, categoriesRes, popularRes] = await Promise.all([
        fetch(getApiUrl(`/blog/articles?${params}`)),
        fetch(getApiUrl('/blog/articles?featured=true&limit=1')),
        fetch(getApiUrl('/blog/categories')),
        fetch(getApiUrl('/blog/popular?limit=5'))
      ]);
      
      if (articlesRes.ok) setArticles(await articlesRes.json());
      if (featuredRes.ok) setFeaturedArticles(await featuredRes.json());
      if (categoriesRes.ok) setCategories(await categoriesRes.json());
      if (popularRes.ok) setPopularArticles(await popularRes.json());
    } catch (error) {
      console.error('Error loading blog:', error);
    } finally {
      setIsLoading(false);
    }
  }, [selectedCategory, appliedSearchQuery]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    setAppliedSearchQuery(searchInput.trim());
  };

  const totalArticles = categories.reduce((sum, cat) => sum + cat.count, 0);

  // Page-specific header right: поиск по статьям блога
  const blogHeaderRight = (
    <form onSubmit={handleSearch} className="hidden md:flex items-center gap-2">
      <div className="relative">
        <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-[var(--text-tertiary)]" />
        <input
          type="text"
          placeholder="Поиск по блогу…"
          value={searchInput}
          onChange={(e) => setSearchInput(e.target.value)}
          className="input-cyber pl-8 py-1.5 w-56 text-[13px]"
        />
      </div>
    </form>
  );

  return (
    <AppShell pageTitle="Блог" headerRight={blogHeaderRight}>
    <div className="bg-[var(--background)]">
      <main className="max-w-7xl mx-auto px-4 md:px-6 py-6 md:py-8">
        <div className="mb-6">
          <h1 className="text-3xl font-bold tracking-tight">Блог</h1>
          <p className="text-sm text-[var(--text-secondary)] mt-1">
            {totalArticles} {totalArticles === 1 ? 'статья' : 'статей'} · обзоры, кейсы, метрики
          </p>
        </div>
        {/* Categories */}
        <div className="flex gap-2 overflow-x-auto pb-4 mb-8">
          <button
            onClick={() => setSelectedCategory(null)}
            className={`px-4 py-2 rounded-full text-sm font-medium whitespace-nowrap transition-all ${
              !selectedCategory 
                ? 'bg-accent text-white' 
                : 'bg-secondary hover:bg-secondary/80'
            }`}
          >
            Все статьи
          </button>
          {categories.map(cat => (
            <button
              key={cat.id}
              onClick={() => setSelectedCategory(cat.id)}
              className={`px-4 py-2 rounded-full text-sm font-medium whitespace-nowrap transition-all flex items-center gap-2 ${
                selectedCategory === cat.id 
                  ? 'bg-accent text-white' 
                  : 'bg-secondary hover:bg-secondary/80'
              }`}
            >
              {categoryIcons[cat.id]}
              {cat.name}
              <span className="text-xs opacity-70">({cat.count})</span>
            </button>
          ))}
        </div>

        {isLoading ? (
          <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6">
            {[1, 2, 3, 4, 5, 6].map(i => (
              <div key={i} className="card p-0 animate-pulse">
                <div className="aspect-video bg-secondary" />
                <div className="p-4 space-y-3">
                  <div className="h-6 bg-secondary rounded w-3/4" />
                  <div className="h-4 bg-secondary rounded w-full" />
                  <div className="h-4 bg-secondary rounded w-2/3" />
                </div>
              </div>
            ))}
          </div>
        ) : articles.length === 0 ? (
          <div className="text-center py-16">
            <Newspaper size={48} className="mx-auto mb-4 text-muted-foreground" />
            <h2 className="text-xl font-semibold mb-2">Статей пока нет</h2>
            <p className="text-muted-foreground">
              {appliedSearchQuery ? 'По вашему запросу ничего не найдено' : 'Скоро здесь появятся интересные материалы'}
            </p>
          </div>
        ) : (
          <div className="grid lg:grid-cols-3 gap-8">
            {/* Main Content */}
            <div className="lg:col-span-2 space-y-8">
              {/* Featured */}
              {!selectedCategory && featuredArticles.length > 0 && (
                <section>
                  <FeaturedArticle article={featuredArticles[0]} />
                </section>
              )}
              
              {/* Articles Grid */}
              <section>
                <h2 className="text-lg font-semibold mb-4">
                  {selectedCategory 
                    ? categories.find(c => c.id === selectedCategory)?.name || 'Статьи'
                    : 'Последние статьи'}
                </h2>
                <div className="grid md:grid-cols-2 gap-6">
                  {articles.map(article => (
                    <ArticleCard key={article.id} article={article} />
                  ))}
                </div>
              </section>
            </div>
            
            {/* Sidebar */}
            <aside className="space-y-6">
              {/* Popular Articles */}
              <div className="card">
                <h3 className="font-semibold mb-4 flex items-center gap-2">
                  <TrendingUp size={18} className="text-accent" />
                  Популярное
                </h3>
                <div className="space-y-3">
                  {popularArticles.map((article, index) => (
                    <Link 
                      key={article.id} 
                      href={`/blog/${article.slug}`}
                      className="flex gap-3 group"
                    >
                      <span className="text-2xl font-bold text-muted-foreground/50 group-hover:text-accent transition-colors">
                        {index + 1}
                      </span>
                      <div className="flex-1">
                        <h4 className="text-sm font-medium group-hover:text-accent transition-colors line-clamp-2">
                          {article.title}
                        </h4>
                        <span className="text-xs text-muted-foreground flex items-center gap-1 mt-1">
                          <Eye size={12} />
                          {article.views_count} просмотров
                        </span>
                      </div>
                    </Link>
                  ))}
                </div>
              </div>
              
              {/* Subscribe Card */}
              <div className="card bg-gradient-to-br from-accent/10 to-purple-600/10 border-accent/30">
                <h3 className="font-semibold mb-2">Подписка на обновления</h3>
                <p className="text-sm text-muted-foreground mb-4">
                  Получайте лучшие статьи о трейдинге на почту
                </p>
                <input
                  type="email"
                  placeholder="your@email.com"
                  className="w-full px-3 py-2 bg-background/50 border border-border rounded-lg text-sm mb-3"
                />
                <button className="btn-primary w-full py-2">
                  Подписаться
                </button>
              </div>
              
              {/* Quick Links */}
              <div className="card">
                <h3 className="font-semibold mb-3">Полезные ссылки</h3>
                <div className="space-y-2">
                  <Link href="/help" className="flex items-center justify-between text-sm hover:text-accent transition-colors">
                    <span>Центр помощи</span>
                    <ChevronRight size={16} />
                  </Link>
                  <Link href="/pricing" className="flex items-center justify-between text-sm hover:text-accent transition-colors">
                    <span>Тарифы</span>
                    <ChevronRight size={16} />
                  </Link>
                  <Link href="/" className="flex items-center justify-between text-sm hover:text-accent transition-colors">
                    <span>Торговый дневник</span>
                    <ChevronRight size={16} />
                  </Link>
                </div>
              </div>
            </aside>
          </div>
        )}
      </main>
    </div>
    </AppShell>
  );
}
