'use client';

import { useState, useEffect } from 'react';
import { useParams } from 'next/navigation';
import Link from 'next/link';
import { 
  ArrowLeft, Eye, Heart, Calendar, Tag, User, Share2, 
  Clock, ChevronRight, Newspaper, BookOpen, TrendingUp, 
  Lightbulb, Sparkles, Copy, Check
} from 'lucide-react';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

interface Article {
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
  meta_title?: string;
  meta_description?: string;
  related_articles?: Article[];
}

const categoryNames: Record<string, string> = {
  news: 'Новости',
  guides: 'Гайды',
  analytics: 'Аналитика',
  tips: 'Советы',
  updates: 'Обновления'
};

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

function estimateReadTime(content: string): number {
  const wordsPerMinute = 200;
  const words = content.split(/\s+/).length;
  return Math.max(1, Math.ceil(words / wordsPerMinute));
}

// Simple markdown renderer
function renderMarkdown(content: string): string {
  let html = content
    // Headers
    .replace(/^### (.*$)/gim, '<h3 class="text-xl font-semibold mt-6 mb-3">$1</h3>')
    .replace(/^## (.*$)/gim, '<h2 class="text-2xl font-bold mt-8 mb-4">$1</h2>')
    .replace(/^# (.*$)/gim, '<h1 class="text-3xl font-bold mt-8 mb-4">$1</h1>')
    // Bold & Italic
    .replace(/\*\*\*(.*?)\*\*\*/g, '<strong><em>$1</em></strong>')
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.*?)\*/g, '<em>$1</em>')
    // Code blocks
    .replace(/```(\w*)\n([\s\S]*?)```/g, '<pre class="bg-secondary p-4 rounded-lg overflow-x-auto my-4"><code>$2</code></pre>')
    .replace(/`([^`]+)`/g, '<code class="bg-secondary px-1.5 py-0.5 rounded text-accent">$1</code>')
    // Links
    .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" class="text-accent hover:underline" target="_blank" rel="noopener">$1</a>')
    // Lists
    .replace(/^\s*[-*]\s+(.*)$/gim, '<li class="ml-4">$1</li>')
    .replace(/(<li.*<\/li>\n?)+/g, '<ul class="list-disc list-inside my-4 space-y-1">$&</ul>')
    // Numbered lists
    .replace(/^\d+\.\s+(.*)$/gim, '<li class="ml-4">$1</li>')
    // Blockquotes
    .replace(/^>\s+(.*)$/gim, '<blockquote class="border-l-4 border-accent pl-4 italic my-4 text-muted-foreground">$1</blockquote>')
    // Horizontal rule
    .replace(/^---$/gim, '<hr class="my-8 border-border" />')
    // Paragraphs (simple version)
    .replace(/\n\n/g, '</p><p class="mb-4">')
    // Line breaks
    .replace(/\n/g, '<br />');
  
  return `<p class="mb-4">${html}</p>`;
}

function RelatedArticleCard({ article }: { article: Article }) {
  return (
    <Link href={`/blog/${article.slug}`} className="group">
      <article className="card p-0 overflow-hidden hover:border-accent/50 transition-all">
        <div className="aspect-video bg-secondary relative overflow-hidden">
          {article.cover_image ? (
            <img 
              src={article.cover_image} 
              alt={article.title}
              className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300"
            />
          ) : (
            <div className="w-full h-full flex items-center justify-center bg-gradient-to-br from-accent/20 to-purple-600/20">
              {categoryIcons[article.category] || <Newspaper size={32} />}
            </div>
          )}
        </div>
        <div className="p-3">
          <h4 className="font-medium text-sm group-hover:text-accent transition-colors line-clamp-2">
            {article.title}
          </h4>
          <span className="text-xs text-muted-foreground mt-1 flex items-center gap-1">
            <Eye size={12} />
            {article.views_count}
          </span>
        </div>
      </article>
    </Link>
  );
}

export default function ArticlePage() {
  const params = useParams();
  const slug = params.slug as string;
  
  const [article, setArticle] = useState<Article | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    loadArticle();
  }, [slug]);

  const loadArticle = async () => {
    setIsLoading(true);
    setError(null);
    
    try {
      const res = await fetch(`${API_URL}/blog/article/${slug}`);
      if (!res.ok) {
        if (res.status === 404) {
          setError('Статья не найдена');
        } else {
          setError('Ошибка загрузки статьи');
        }
        return;
      }
      setArticle(await res.json());
    } catch (err) {
      setError('Не удалось загрузить статью');
    } finally {
      setIsLoading(false);
    }
  };

  const handleShare = async () => {
    const url = window.location.href;
    
    if (navigator.share) {
      try {
        await navigator.share({
          title: article?.title,
          text: article?.excerpt,
          url: url
        });
      } catch (err) {
        // User cancelled or error
      }
    } else {
      // Fallback: copy to clipboard
      await navigator.clipboard.writeText(url);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  if (isLoading) {
    return (
      <div className="min-h-screen bg-background">
        <header className="border-b border-border bg-card/50 backdrop-blur-sm">
          <div className="max-w-4xl mx-auto px-4 py-4">
            <div className="h-6 bg-secondary rounded w-32 animate-pulse" />
          </div>
        </header>
        <main className="max-w-4xl mx-auto px-4 py-8">
          <div className="space-y-4 animate-pulse">
            <div className="h-8 bg-secondary rounded w-3/4" />
            <div className="h-6 bg-secondary rounded w-1/2" />
            <div className="aspect-video bg-secondary rounded-xl mt-8" />
            <div className="space-y-3 mt-8">
              {[1, 2, 3, 4, 5].map(i => (
                <div key={i} className="h-4 bg-secondary rounded" />
              ))}
            </div>
          </div>
        </main>
      </div>
    );
  }

  if (error || !article) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <div className="text-center">
          <Newspaper size={48} className="mx-auto mb-4 text-muted-foreground" />
          <h1 className="text-2xl font-bold mb-2">{error || 'Статья не найдена'}</h1>
          <p className="text-muted-foreground mb-4">
            Возможно, она была удалена или ещё не опубликована
          </p>
          <Link href="/blog" className="btn-primary inline-flex items-center gap-2">
            <ArrowLeft size={16} />
            Вернуться в блог
          </Link>
        </div>
      </div>
    );
  }

  const readTime = estimateReadTime(article.content);

  return (
    <div className="min-h-screen bg-background">
      {/* Header */}
      <header className="border-b border-border bg-card/50 backdrop-blur-sm sticky top-0 z-50">
        <div className="max-w-4xl mx-auto px-4 py-4 flex items-center justify-between">
          <Link 
            href="/blog" 
            className="flex items-center gap-2 text-muted-foreground hover:text-foreground transition-colors"
          >
            <ArrowLeft size={20} />
            <span>Блог</span>
          </Link>
          
          <div className="flex items-center gap-2">
            <button
              onClick={handleShare}
              className="p-2 hover:bg-secondary rounded-lg transition-colors flex items-center gap-2"
              title="Поделиться"
            >
              {copied ? <Check size={18} className="text-green-400" /> : <Share2 size={18} />}
              {copied && <span className="text-sm text-green-400">Скопировано!</span>}
            </button>
          </div>
        </div>
      </header>

      <main className="max-w-4xl mx-auto px-4 py-8">
        {/* Article Header */}
        <article>
          {/* Category & Meta */}
          <div className="flex flex-wrap items-center gap-3 mb-4">
            <span className={`inline-flex items-center gap-1 px-3 py-1 rounded-full text-sm font-medium border ${categoryColors[article.category]}`}>
              {categoryIcons[article.category]}
              {categoryNames[article.category]}
            </span>
            
            <span className="text-muted-foreground text-sm flex items-center gap-1">
              <Calendar size={14} />
              {article.published_at ? formatDate(article.published_at) : formatDate(article.created_at)}
            </span>
            
            <span className="text-muted-foreground text-sm flex items-center gap-1">
              <Clock size={14} />
              {readTime} мин чтения
            </span>
          </div>
          
          {/* Title */}
          <h1 className="text-3xl md:text-4xl font-bold mb-4">
            {article.title}
          </h1>
          
          {/* Excerpt */}
          {article.excerpt && (
            <p className="text-xl text-muted-foreground mb-6">
              {article.excerpt}
            </p>
          )}
          
          {/* Author & Stats */}
          <div className="flex items-center justify-between py-4 border-y border-border mb-8">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 bg-accent rounded-full flex items-center justify-center">
                <span className="text-lg font-bold text-white">
                  {(article.author_name || 'A')[0].toUpperCase()}
                </span>
              </div>
              <div>
                <p className="font-medium">{article.author_name || 'Редакция ATOM'}</p>
                <p className="text-sm text-muted-foreground">Автор статьи</p>
              </div>
            </div>
            
            <div className="flex items-center gap-4 text-muted-foreground">
              <span className="flex items-center gap-1">
                <Eye size={18} />
                {article.views_count}
              </span>
              <span className="flex items-center gap-1">
                <Heart size={18} />
                {article.likes_count}
              </span>
            </div>
          </div>
          
          {/* Cover Image */}
          {article.cover_image && (
            <div className="aspect-video rounded-xl overflow-hidden mb-8">
              <img 
                src={article.cover_image} 
                alt={article.title}
                className="w-full h-full object-cover"
              />
            </div>
          )}
          
          {/* Content */}
          <div 
            className="prose prose-invert max-w-none"
            dangerouslySetInnerHTML={{ __html: renderMarkdown(article.content) }}
          />
          
          {/* Tags */}
          {article.tags && article.tags.length > 0 && (
            <div className="mt-8 pt-6 border-t border-border">
              <div className="flex items-center gap-2 flex-wrap">
                <Tag size={16} className="text-muted-foreground" />
                {article.tags.map(tag => (
                  <Link 
                    key={tag}
                    href={`/blog?tag=${tag}`}
                    className="px-3 py-1 bg-secondary hover:bg-secondary/80 rounded-full text-sm transition-colors"
                  >
                    #{tag}
                  </Link>
                ))}
              </div>
            </div>
          )}
        </article>
        
        {/* Related Articles */}
        {article.related_articles && article.related_articles.length > 0 && (
          <section className="mt-12 pt-8 border-t border-border">
            <h2 className="text-xl font-bold mb-6">Похожие статьи</h2>
            <div className="grid md:grid-cols-3 gap-4">
              {article.related_articles.map(related => (
                <RelatedArticleCard key={related.id} article={related} />
              ))}
            </div>
          </section>
        )}
        
        {/* CTA */}
        <section className="mt-12 card bg-gradient-to-br from-accent/10 to-purple-600/10 border-accent/30 text-center">
          <h2 className="text-xl font-bold mb-2">Начните вести торговый дневник</h2>
          <p className="text-muted-foreground mb-4">
            Анализируйте сделки, улучшайте стратегию и зарабатывайте больше
          </p>
          <Link href="/register" className="btn-primary inline-flex items-center gap-2">
            Попробовать бесплатно
            <ChevronRight size={16} />
          </Link>
        </section>
      </main>
    </div>
  );
}
