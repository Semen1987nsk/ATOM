'use client';

import { useState, useEffect } from 'react';
import { useAuth } from '@/contexts/AuthContext';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { LogIn, Mail, Lock, Eye, EyeOff, AlertCircle, Loader2 } from 'lucide-react';
import { OAuthButtons } from '@/components/OAuthButtons';
import { Button, Input } from '@/components/ui';

export default function LoginPage() {
  const { login, refreshUser, isAuthenticated, isLoading: authLoading } = useAuth();
  const router = useRouter();

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(false);

  useEffect(() => {
    if (isAuthenticated && !authLoading) {
      router.push('/');
    }
  }, [isAuthenticated, authLoading, router]);

  if (authLoading) {
    return (
      <main className="min-h-screen flex items-center justify-center">
        <Loader2 className="w-8 h-8 animate-spin text-[var(--accent)]" />
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
    <main className="min-h-screen flex items-center justify-center p-6 relative overflow-hidden bg-mesh-soft">
      <div className="relative w-full max-w-[420px]">
        {/* Logo */}
        <div className="text-center mb-10">
          <Link
            href="/"
            className="inline-flex items-center gap-1 text-4xl font-bold tracking-tight"
          >
            <span className="text-[var(--accent)]">Эмпирик</span>
          </Link>
          <p className="text-sm text-[var(--text-secondary)] mt-2">
            Торговая аналитика на базе ИИ
          </p>
        </div>

        {/* Card */}
        <div className="cyber-card p-8">
          <div className="mb-6">
            <h1 className="text-2xl font-bold leading-tight">Вход в аккаунт</h1>
            <p className="text-sm text-[var(--text-secondary)] mt-1">
              Введите свои данные для продолжения
            </p>
          </div>

          {error && (
            <div className="flex items-center gap-2 px-3 py-2.5 mb-5 rounded-[var(--radius-md)] bg-[var(--danger-soft)] text-[var(--danger)] text-sm">
              <AlertCircle size={16} className="flex-shrink-0" />
              <span>{error}</span>
            </div>
          )}

          <form onSubmit={handleSubmit} className="flex flex-col gap-4">
            <Input
              label="Email"
              type="email"
              name="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="your@email.com"
              required
              leftIcon={<Mail size={16} />}
              autoComplete="email"
            />

            <Input
              label="Пароль"
              type={showPassword ? 'text' : 'password'}
              name="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
              required
              leftIcon={<Lock size={16} />}
              autoComplete="current-password"
              rightAddon={
                <button
                  type="button"
                  onClick={() => setShowPassword((v) => !v)}
                  className="p-1 hover:text-[var(--foreground)] transition-colors"
                  aria-label={showPassword ? 'Скрыть пароль' : 'Показать пароль'}
                >
                  {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
                </button>
              }
            />

            <Button
              type="submit"
              size="lg"
              fullWidth
              loading={isLoading}
              leftIcon={!isLoading ? <LogIn size={16} /> : undefined}
              className="mt-2"
            >
              {isLoading ? 'Вход...' : 'Войти'}
            </Button>
          </form>

          {/* OAuth */}
          <div className="mt-6">
            <OAuthButtons
              onSuccess={async () => {
                await refreshUser();
                router.push('/');
              }}
              onError={(err) => setError(err)}
            />
          </div>

          {/* Register link */}
          <div className="mt-6 pt-5 border-t border-[var(--border)] text-center">
            <p className="text-sm text-[var(--text-secondary)]">
              Нет аккаунта?{' '}
              <Link
                href="/register"
                className="text-[var(--accent)] hover:text-[var(--accent-hover)] font-medium transition-colors"
              >
                Зарегистрироваться
              </Link>
            </p>
          </div>
        </div>

        {/* Back to home */}
        <div className="mt-6 text-center">
          <Link
            href="/"
            className="text-sm text-[var(--text-tertiary)] hover:text-[var(--foreground)] transition-colors"
          >
            ← Вернуться на главную
          </Link>
        </div>
      </div>
    </main>
  );
}
