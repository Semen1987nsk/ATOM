'use client';

import Link from 'next/link';
import { useAuth } from '@/contexts/AuthContext';
import { Shield, HelpCircle, LogIn, Zap } from 'lucide-react';

export function AuthButton() {
  const { user, isLoading } = useAuth();
  
  if (isLoading) {
    return <div className="w-8 h-8 bg-secondary rounded-full animate-pulse" />;
  }
  
  if (user) {
    return (
      <div className="flex items-center gap-2">
        <Link 
          href="/help"
          className="flex items-center gap-1.5 px-3 py-1.5 text-cyan-400 hover:text-cyan-300 
                     border border-cyan-500/40 hover:border-cyan-400/60 rounded-lg 
                     bg-cyan-500/10 hover:bg-cyan-500/20 transition-all"
          title="Помощь"
        >
          <HelpCircle size={14} />
          <span className="hidden md:inline text-sm">Помощь</span>
        </Link>
        {user.is_admin && (
          <Link 
            href="/admin"
            className="btn-secondary p-2.5 aspect-square text-purple-400"
            title="Админ-панель"
          >
            <Shield size={14} />
          </Link>
        )}
        <Link 
          href="/profile"
          className="flex items-center gap-2 btn-secondary"
          title="Профиль"
        >
          <div className="w-5 h-5 bg-accent rounded-full flex items-center justify-center">
            <span className="text-xs font-bold text-white">
              {(user.name || user.email)[0].toUpperCase()}
            </span>
          </div>
          <span className="hidden md:inline text-sm">{user.name || 'Профиль'}</span>
        </Link>
      </div>
    );
  }
  
  return (
    <div className="flex items-center gap-3">
      <Link 
        href="/blog"
        className="px-3 py-1.5 text-sm text-muted-foreground hover:text-foreground 
                   border border-border hover:border-foreground/30 rounded-lg 
                   hover:bg-secondary transition-all"
      >
        Блог
      </Link>
      <Link 
        href="/help"
        className="px-3 py-1.5 text-sm text-muted-foreground hover:text-cyan-400 
                   border border-border hover:border-cyan-500/50 rounded-lg 
                   hover:bg-cyan-500/10 transition-all"
      >
        Помощь
      </Link>
      <Link 
        href="/pricing"
        className="flex items-center gap-1.5 px-3 py-1.5 text-sm text-purple-400 hover:text-purple-300 
                   border border-purple-500/30 hover:border-purple-500/50 rounded-lg 
                   hover:bg-purple-500/10 transition-all"
      >
        <Zap size={14} />
        <span className="hidden md:inline">Тарифы</span>
      </Link>
      <Link 
        href="/login"
        className="btn-primary flex items-center gap-2"
      >
        <LogIn size={14} />
        <span className="hidden md:inline">Войти</span>
      </Link>
    </div>
  );
}
