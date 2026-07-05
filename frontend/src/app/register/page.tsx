'use client';

import { useState, useEffect } from 'react';
import { useAuth } from '@/contexts/AuthContext';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { UserPlus, Mail, Lock, Eye, EyeOff, AlertCircle, User, CheckCircle } from 'lucide-react';
import { OAuthButtons } from '@/components/OAuthButtons';
import { Button, Input } from '@/components/ui';

// Согласовано с backend (schemas.UserCreate min_length=12) — Phase 2 update.
const PASSWORD_MIN = 12;

export default function RegisterPage() {
  const { register, refreshUser, isAuthenticated } = useAuth();
  const router = useRouter();

  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [pdConsent, setPdConsent] = useState(false);
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(false);

  useEffect(() => {
    if (isAuthenticated) {
      router.push('/');
    }
  }, [isAuthenticated, router]);

  if (isAuthenticated) return null;

  const passwordOk = password.length >= PASSWORD_MIN;
  const passwordsMatch = password === confirmPassword && password.length > 0;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');

    if (password !== confirmPassword) {
      setError('Пароли не совпадают');
      return;
    }
    if (!passwordOk) {
      setError(`Пароль должен быть минимум ${PASSWORD_MIN} символов`);
      return;
    }
    if (!pdConsent) {
      setError('Необходимо согласие на обработку персональных данных (152-ФЗ)');
      return;
    }

    setIsLoading(true);
    try {
      await register(email, password, name || undefined, pdConsent);
      router.push('/');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Ошибка регистрации');
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
            Создайте аккаунт за 30 секунд
          </p>
        </div>

        {/* Card */}
        <div className="cyber-card p-8">
          <div className="mb-6">
            <h1 className="text-2xl font-bold leading-tight">Регистрация</h1>
            <p className="text-sm text-[var(--text-secondary)] mt-1">
              Бесплатно, без карты
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
              label="Имя (опционально)"
              type="text"
              name="name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Ваше имя"
              leftIcon={<User size={16} />}
              autoComplete="name"
            />

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

            <div>
              <Input
                label="Пароль"
                type={showPassword ? 'text' : 'password'}
                name="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder={`Минимум ${PASSWORD_MIN} символов`}
                required
                leftIcon={<Lock size={16} />}
                autoComplete="new-password"
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
              {password.length > 0 && (
                <span
                  className={`mt-2 inline-flex items-center gap-1 text-[12px] ${
                    passwordOk
                      ? 'text-[var(--success)]'
                      : 'text-[var(--text-tertiary)]'
                  }`}
                >
                  <CheckCircle size={12} /> {PASSWORD_MIN}+ символов
                </span>
              )}
            </div>

            <Input
              label="Подтвердите пароль"
              type={showPassword ? 'text' : 'password'}
              name="confirm_password"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              placeholder="Повторите пароль"
              required
              leftIcon={<Lock size={16} />}
              autoComplete="new-password"
              rightAddon={
                confirmPassword.length > 0 ? (
                  <span
                    className={
                      passwordsMatch
                        ? 'text-[var(--success)]'
                        : 'text-[var(--danger)]'
                    }
                  >
                    {passwordsMatch ? (
                      <CheckCircle size={16} />
                    ) : (
                      <AlertCircle size={16} />
                    )}
                  </span>
                ) : undefined
              }
            />

            {/* 152-ФЗ ст. 9: явное согласие на обработку ПД при регистрации.
                Текст ссылается на политику с указанием версии — критично для аудита РКН. */}
            <label className="flex items-start gap-2.5 text-[13px] cursor-pointer mt-1 text-[var(--text-secondary)]">
              <input
                type="checkbox"
                name="pd_consent"
                checked={pdConsent}
                onChange={(e) => setPdConsent(e.target.checked)}
                required
                aria-required="true"
                className="mt-0.5 w-4 h-4 accent-[var(--accent)] cursor-pointer flex-shrink-0"
              />
              <span>
                Я даю{' '}
                <Link
                  href="/privacy"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-[var(--accent)] hover:text-[var(--accent-hover)] underline"
                >
                  согласие на обработку персональных данных
                </Link>{' '}
                в соответствии с политикой Полистаты (версия v1)
              </span>
            </label>

            <Button
              type="submit"
              size="lg"
              fullWidth
              loading={isLoading}
              disabled={!passwordOk || !passwordsMatch || !pdConsent}
              leftIcon={!isLoading ? <UserPlus size={16} /> : undefined}
              className="mt-2"
            >
              {isLoading ? 'Регистрация...' : 'Создать аккаунт'}
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

          {/* Login link */}
          <div className="mt-6 pt-5 border-t border-[var(--border)] text-center">
            <p className="text-sm text-[var(--text-secondary)]">
              Уже есть аккаунт?{' '}
              <Link
                href="/login"
                className="text-[var(--accent)] hover:text-[var(--accent-hover)] font-medium transition-colors"
              >
                Войти
              </Link>
            </p>
          </div>
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
