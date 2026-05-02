'use client';

import { useState, useEffect } from 'react';
import { useAuth } from '@/contexts/AuthContext';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { UserPlus, Mail, Lock, Eye, EyeOff, AlertCircle, Loader2, User, CheckCircle } from 'lucide-react';
import { OAuthButtons } from '@/components/OAuthButtons';

export default function RegisterPage() {
  const { register, refreshUser, isAuthenticated } = useAuth();
  const router = useRouter();
  
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  
  // Если уже авторизован — редирект на главную
  useEffect(() => {
    if (isAuthenticated) {
      router.push('/');
    }
  }, [isAuthenticated, router]);
  
  // Показываем null пока идёт редирект
  if (isAuthenticated) {
    return null;
  }
  
  const validatePassword = (pwd: string) => {
    return {
      minLength: pwd.length >= 6,
      hasNumber: /\d/.test(pwd),
    };
  };
  
  const passwordChecks = validatePassword(password);
  const passwordsMatch = password === confirmPassword && password.length > 0;
  
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    
    // Валидация
    if (password !== confirmPassword) {
      setError('Пароли не совпадают');
      return;
    }
    
    if (password.length < 6) {
      setError('Пароль должен быть минимум 6 символов');
      return;
    }
    
    setIsLoading(true);
    
    try {
      await register(email, password, name || undefined);
      router.push('/');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Ошибка регистрации');
    } finally {
      setIsLoading(false);
    }
  };
  
  return (
    <main className="min-h-screen flex items-center justify-center p-4 relative overflow-hidden">
      {/* Background Effects */}
      <div className="absolute inset-0 bg-gradient-to-br from-background via-background to-accent/5" />
      <div className="absolute top-1/4 right-1/4 w-96 h-96 bg-accent/10 rounded-full blur-3xl" />
      <div className="absolute bottom-1/4 left-1/4 w-80 h-80 bg-green-500/10 rounded-full blur-3xl" />
      
      <div className="relative w-full max-w-md">
        {/* Logo */}
        <div className="text-center mb-8">
          <Link href="/" className="inline-flex items-center gap-2 text-3xl font-black tracking-tight">
            <span className="text-accent">Eq</span>
            <span className="text-foreground">io</span>
          </Link>
          <p className="text-sm text-muted-foreground mt-2">
            Создайте аккаунт для начала работы
          </p>
        </div>
        
        {/* Register Card */}
        <div className="cyber-card p-8">
          <div className="flex items-center gap-3 mb-6">
            <div className="p-2.5 bg-green-500/20 rounded-lg">
              <UserPlus size={24} className="text-green-400" />
            </div>
            <div>
              <h1 className="text-xl font-bold">Регистрация</h1>
              <p className="text-xs text-muted-foreground">Бесплатно, за 30 секунд</p>
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
            {/* Name */}
            <div className="space-y-2">
              <label className="text-sm font-medium text-foreground">
                Имя <span className="text-muted-foreground">(опционально)</span>
              </label>
              <div className="relative">
                <User size={18} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
                <input
                  type="text"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="Ваше имя"
                  className="w-full pl-10 pr-4 py-3 bg-secondary/50 border border-white/10 rounded-lg 
                           text-foreground placeholder:text-muted-foreground
                           focus:outline-none focus:ring-2 focus:ring-accent/50 focus:border-accent
                           transition-all"
                />
              </div>
            </div>
            
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
                  placeholder="Минимум 6 символов"
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
              
              {/* Password Requirements */}
              {password.length > 0 && (
                <div className="flex gap-4 text-xs mt-2">
                  <span className={`flex items-center gap-1 ${passwordChecks.minLength ? 'text-green-400' : 'text-muted-foreground'}`}>
                    <CheckCircle size={12} />
                    6+ символов
                  </span>
                </div>
              )}
            </div>
            
            {/* Confirm Password */}
            <div className="space-y-2">
              <label className="text-sm font-medium text-foreground">Подтвердите пароль</label>
              <div className="relative">
                <Lock size={18} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
                <input
                  type={showPassword ? 'text' : 'password'}
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  placeholder="Повторите пароль"
                  required
                  className={`w-full pl-10 pr-12 py-3 bg-secondary/50 border rounded-lg 
                           text-foreground placeholder:text-muted-foreground
                           focus:outline-none focus:ring-2 focus:ring-accent/50 focus:border-accent
                           transition-all
                           ${confirmPassword.length > 0 
                             ? passwordsMatch 
                               ? 'border-green-500/50' 
                               : 'border-red-500/50' 
                             : 'border-white/10'
                           }`}
                />
                {confirmPassword.length > 0 && (
                  <span className={`absolute right-3 top-1/2 -translate-y-1/2 ${passwordsMatch ? 'text-green-400' : 'text-red-400'}`}>
                    {passwordsMatch ? <CheckCircle size={18} /> : <AlertCircle size={18} />}
                  </span>
                )}
              </div>
            </div>
            
            {/* Submit Button */}
            <button
              type="submit"
              disabled={isLoading || !passwordChecks.minLength || !passwordsMatch}
              className="w-full py-3 bg-accent hover:bg-accent/90 text-white font-semibold rounded-lg
                       flex items-center justify-center gap-2 transition-all
                       disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {isLoading ? (
                <>
                  <Loader2 size={18} className="animate-spin" />
                  Регистрация...
                </>
              ) : (
                <>
                  <UserPlus size={18} />
                  Создать аккаунт
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
          
          {/* Login Link */}
          <div className="mt-6 pt-6 border-t border-white/10 text-center">
            <p className="text-sm text-muted-foreground">
              Уже есть аккаунт?{' '}
              <Link href="/login" className="text-accent hover:underline font-medium">
                Войти
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
