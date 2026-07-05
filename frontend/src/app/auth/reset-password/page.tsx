'use client';

import { Suspense, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import Link from 'next/link';
import { Lock, AlertCircle, CheckCircle } from 'lucide-react';
import { api, ApiError } from '@/lib/apiClient';
import { Button, Input } from '@/components/ui';

const PASSWORD_MIN = 12;

function ResetPasswordContent() {
  const router = useRouter();
  const token = useSearchParams().get('token') ?? '';

  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [error, setError] = useState('');
  const [isTokenError, setIsTokenError] = useState(false);
  const [done, setDone] = useState(false);
  const [isLoading, setIsLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setIsTokenError(false);

    if (password !== confirmPassword) {
      setError('Пароли не совпадают');
      return;
    }
    if (password.length < PASSWORD_MIN) {
      setError(`Пароль должен быть минимум ${PASSWORD_MIN} символов`);
      return;
    }

    setIsLoading(true);
    try {
      await api.post('/auth/password-reset/confirm', {
        body: { token, new_password: password },
        noAuth: true,
      });
      setDone(true);
      setTimeout(() => router.push('/login'), 2000);
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message);
        setIsTokenError(err.status === 400);
      } else {
        setError('Не удалось сбросить пароль');
      }
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
          {!token ? (
            <div className="text-center">
              <div className="flex items-center gap-2 px-3 py-2.5 mb-5 rounded-[var(--radius-md)] bg-[var(--danger-soft)] text-[var(--danger)] text-sm">
                <AlertCircle size={16} className="flex-shrink-0" />
                <span>Ссылка недействительна — токен отсутствует.</span>
              </div>
              <Link
                href="/auth/forgot-password"
                className="text-[var(--accent)] hover:text-[var(--accent-hover)] font-medium transition-colors"
              >
                Запросить новую ссылку
              </Link>
            </div>
          ) : done ? (
            <div className="text-center">
              <div className="flex items-center gap-2 px-3 py-2.5 mb-5 rounded-[var(--radius-md)] bg-[var(--success-soft)] text-[var(--success)] text-sm">
                <CheckCircle size={16} className="flex-shrink-0" />
                <span>Пароль успешно изменён. Перенаправляем на вход…</span>
              </div>
              <Link
                href="/login"
                className="text-[var(--accent)] hover:text-[var(--accent-hover)] font-medium transition-colors"
              >
                Войти сейчас
              </Link>
            </div>
          ) : (
            <>
              <div className="mb-6">
                <h1 className="text-2xl font-bold leading-tight">Новый пароль</h1>
                <p className="text-sm text-[var(--text-secondary)] mt-1">
                  Придумайте новый пароль для входа
                </p>
              </div>

              {error && (
                <div className="flex flex-col gap-2 px-3 py-2.5 mb-5 rounded-[var(--radius-md)] bg-[var(--danger-soft)] text-[var(--danger)] text-sm">
                  <div className="flex items-center gap-2">
                    <AlertCircle size={16} className="flex-shrink-0" />
                    <span>{error}</span>
                  </div>
                  {isTokenError && (
                    <Link
                      href="/auth/forgot-password"
                      className="text-[var(--accent)] hover:text-[var(--accent-hover)] font-medium transition-colors self-start"
                    >
                      Запросить новую ссылку
                    </Link>
                  )}
                </div>
              )}

              <form onSubmit={handleSubmit} className="flex flex-col gap-4">
                <Input
                  label="Новый пароль"
                  type="password"
                  name="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder={`Минимум ${PASSWORD_MIN} символов`}
                  required
                  leftIcon={<Lock size={16} />}
                  autoComplete="new-password"
                />

                <Input
                  label="Подтвердите пароль"
                  type="password"
                  name="confirm_password"
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  placeholder="Повторите пароль"
                  required
                  leftIcon={<Lock size={16} />}
                  autoComplete="new-password"
                />

                <Button
                  type="submit"
                  size="lg"
                  fullWidth
                  loading={isLoading}
                  className="mt-2"
                >
                  {isLoading ? 'Сохранение...' : 'Сохранить пароль'}
                </Button>
              </form>
            </>
          )}
        </div>

        <div className="mt-6 text-center">
          <Link
            href="/login"
            className="text-sm text-[var(--text-tertiary)] hover:text-[var(--foreground)] transition-colors"
          >
            ← Вернуться ко входу
          </Link>
        </div>
      </div>
    </main>
  );
}

export default function ResetPasswordPage() {
  return (
    <Suspense fallback={<main className="min-h-screen bg-mesh-soft" />}>
      <ResetPasswordContent />
    </Suspense>
  );
}
