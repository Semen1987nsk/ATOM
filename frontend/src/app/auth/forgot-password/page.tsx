'use client';

import { useState } from 'react';
import Link from 'next/link';
import { Mail, AlertCircle, CheckCircle, KeyRound } from 'lucide-react';
import { api, ApiError } from '@/lib/apiClient';
import { Button, Input } from '@/components/ui';

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState('');
  const [error, setError] = useState('');
  const [done, setDone] = useState(false);
  const [isLoading, setIsLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setIsLoading(true);
    try {
      await api.post('/auth/password-reset/request', {
        body: { email },
        noAuth: true,
      });
      setDone(true);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Не удалось отправить письмо');
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
            <span className="text-[var(--accent)]">Полистата</span>
          </Link>
          <p className="text-sm text-[var(--text-secondary)] mt-2">
            Восстановление пароля
          </p>
        </div>

        {/* Card */}
        <div className="cyber-card p-8">
          {done ? (
            <div className="text-center">
              <div className="flex items-center gap-2 px-3 py-2.5 mb-5 rounded-[var(--radius-md)] bg-[var(--success-soft)] text-[var(--success)] text-sm">
                <CheckCircle size={16} className="flex-shrink-0" />
                <span>Если такой email зарегистрирован — мы выслали ссылку. Проверьте почту.</span>
              </div>
              <Link
                href="/login"
                className="text-[var(--accent)] hover:text-[var(--accent-hover)] font-medium transition-colors"
              >
                ← На страницу входа
              </Link>
            </div>
          ) : (
            <>
              <div className="mb-6">
                <h1 className="text-2xl font-bold leading-tight">Забыли пароль?</h1>
                <p className="text-sm text-[var(--text-secondary)] mt-1">
                  Укажите email — пришлём ссылку для сброса пароля
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

                <Button
                  type="submit"
                  size="lg"
                  fullWidth
                  loading={isLoading}
                  leftIcon={!isLoading ? <KeyRound size={16} /> : undefined}
                  className="mt-2"
                >
                  {isLoading ? 'Отправка...' : 'Отправить ссылку'}
                </Button>
              </form>

              <div className="mt-6 pt-5 border-t border-[var(--border)] text-center">
                <p className="text-sm text-[var(--text-secondary)]">
                  Вспомнили пароль?{' '}
                  <Link
                    href="/login"
                    className="text-[var(--accent)] hover:text-[var(--accent-hover)] font-medium transition-colors"
                  >
                    Войти
                  </Link>
                </p>
              </div>
            </>
          )}
        </div>

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
