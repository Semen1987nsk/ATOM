'use client';

import { useState, useEffect } from 'react';
import { useAuth } from '@/contexts/AuthContext';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { LogIn, Mail, Lock, Eye, EyeOff, AlertCircle, Loader2 } from 'lucide-react';
import { OAuthButtons } from '@/components/OAuthButtons';

export default function LoginPage() {
  const { login, refreshUser, isAuthenticated, isLoading: authLoading } = useAuth();
  const router = useRouter();
  
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  
  // Если уже авторизован — редирект на главную
  useEffect(() => {
    if (isAuthenticated && !authLoading) {
      router.push('/');
    }
  }, [isAuthenticated, authLoading, router]);
  
  if (authLoading) {
    return (
      <main className="min-h-screen flex items-center justify-center">
        <Loader2 className="w-8 h-8 animate-spin text-accent" />
      </main>
    );
  }
  
  if (isAuthenticated) {
    return null;
  }
  
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setIsLoading(true);
    
    try {
      await login(email, password);
      router.push('/');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Ошибка входа');
    } finally {
      setIsLoading(false);
    }
  };
  
  return (
    <main className="min-h-screen flex items-center justify-center p-4 relative overflow-hidden">
      {/* Background Effects */}
      <div className="absolute inset-0 bg-gradient-to-br from-background via-background to-accent/5" />
      <div className="absolute top-1/4 left-1/4 w-96 h-96 bg-accent/10 rounded-full blur-3xl" />
      <div className="absolute bottom-1/4 right-1/4 w-80 h-80 bg-green-500/10 rounded-full blur-3xl" />
      
      <div className="relative w-full max-w-md">
        {/* Logo */}
        <div className="text-center mb-8">
          <Link href="/" className="inline-flex items-center gap-2 text-3xl font-black tracking-tight">
            <span className="text-accent">Eq</span>
            <span className="text-foreground">io</span>
          </Link>
          <p className="text-sm text-muted-foreground mt-2">
            Торговая аналитика на базе ИИ
          </p>
        </div>
        
        {/* Login Card */}
        <div className="cyber-card p-8">
          <div className="flex items-center gap-3 mb-6">
            <div className="p-2.5 bg-accent/20 rounded-lg">
              <LogIn size={24} className="text-accent" />
            </div>
            <div>
              <h1 className="text-xl font-bold">Вход в аккаунт</h1>
              <p className="text-xs text-muted-foreground">Введите свои данные для входа</p>
            </div>
          </div>
          
          {/* Error Message */}
          {error && (
            <div className="flex items-center gap-2 p-3 mb-6 bg-red-500/10 border border-red-500/20 rounded-lg text-red-400 text-sm">
              <AlertCircle size={16} />
              {error}
            </div>
          )}
          
          <form onSubmit={handleSubmit} className="space-y-4">
            {/* Email */}
            <div className="space-y-2">
              <label className="text-sm font-medium text-foreground">Email</label>
              <div className="relative">
                <Mail size={18} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="your@email.com"
                  required
                  className="w-full pl-10 pr-4 py-3 bg-secondary/50 border border-white/10 rounded-lg 
                           text-foreground placeholder:text-muted-foreground
                           focus:outline-none focus:ring-2 focus:ring-accent/50 focus:border-accent
                           transition-all"
                />
              </div>
            </div>
            
            {/* Password */}
            <div className="space-y-2">
              <label className="text-sm font-medium text-foreground">Пароль</label>
              <div className="relative">
                <Lock size={18} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
                <input
                  type={showPassword ? 'text' : 'password'}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••"
                  required
                  className="w-full pl-10 pr-12 py-3 bg-secondary/50 border border-white/10 rounded-lg 
                           text-foreground placeholder:text-muted-foreground
                           focus:outline-none focus:ring-2 focus:ring-accent/50 focus:border-accent
                           transition-all"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground transition-colors"
                >
                  {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
                </button>
              </div>
            </div>
            
            {/* Submit Button */}
            <button
              type="submit"
              disabled={isLoading}
              className="w-full py-3 bg-accent hover:bg-accent/90 text-white font-semibold rounded-lg
                       flex items-center justify-center gap-2 transition-all
                       disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {isLoading ? (
                <>
                  <Loader2 size={18} className="animate-spin" />
                  Вход...
                </>
              ) : (
                <>
                  <LogIn size={18} />
                  Войти
                </>
              )}
            </button>
          </form>
          
          {/* OAuth Buttons */}
          <div className="mt-6">
            <OAuthButtons 
              onSuccess={async () => {
                await refreshUser();
                router.push('/');
              }}
              onError={(err) => setError(err)}
            />
          </div>
          
          {/* Register Link */}
          <div className="mt-6 pt-6 border-t border-white/10 text-center">
            <p className="text-sm text-muted-foreground">
              Нет аккаунта?{' '}
              <Link href="/register" className="text-accent hover:underline font-medium">
                Зарегистрироваться
              </Link>
            </p>
          </div>
        </div>
        
        {/* Back to Home */}
        <div className="mt-6 text-center">
          <Link href="/" className="text-sm text-muted-foreground hover:text-foreground transition-colors">
            ← Вернуться на главную
          </Link>
        </div>
      </div>
    </main>
  );
}
