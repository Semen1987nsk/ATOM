'use client';

/**
 * Email verification page — PR 26 Phase 3.
 * URL: /auth/verify-email?token=XXX
 *
 * Шаги:
 * 1. Извлекаем token из query params
 * 2. GET /auth/verify-email?token=XXX
 * 3. Показываем результат (success/expired/invalid)
 * 4. Кнопка → перенаправить на dashboard
 */

import { useEffect, useState, Suspense } from 'react';
import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import { CheckCircle, AlertCircle, Loader2 } from 'lucide-react';
import { api } from '@/lib/apiClient';

function VerifyEmailContent() {
  const params = useSearchParams();
  const token = params?.get('token');

  const [state, setState] = useState<'loading' | 'success' | 'invalid' | 'expired' | 'error'>('loading');
  const [message, setMessage] = useState<string>('');

  useEffect(() => {
    if (!token) {
      setState('invalid');
      setMessage('В ссылке отсутствует токен.');
      return;
    }
    api.get<{ ok: boolean; message: string }>(
      `/auth/verify-email?token=${encodeURIComponent(token)}`,
    )
      .then((r) => {
        setState('success');
        setMessage(r.message || 'Email подтверждён.');
      })
      .catch((e: { status?: number; detail?: string; message?: string }) => {
        if (e.status === 404) {
          setState('invalid');
          setMessage(e.detail || 'Ссылка недействительна.');
        } else if (e.status === 400 && /истек/i.test(e.detail ?? '')) {
          setState('expired');
          setMessage(e.detail || 'Ссылка истекла.');
        } else {
          setState('error');
          setMessage(e.detail || e.message || 'Ошибка проверки.');
        }
      });
  }, [token]);

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex items-center justify-center p-6">
      <div className="max-w-md w-full">
        <div className="rounded-xl border border-slate-700/50 bg-slate-800/30 p-8 text-center">
          {state === 'loading' && (
            <>
              <Loader2 size={48} className="text-blue-400 animate-spin mx-auto mb-4" />
              <h1 className="text-xl font-semibold mb-2">Подтверждаем email...</h1>
            </>
          )}
          {state === 'success' && (
            <>
              <CheckCircle size={48} className="text-green-400 mx-auto mb-4" />
              <h1 className="text-xl font-semibold mb-2">Email подтверждён</h1>
              <p className="text-slate-400 mb-6 text-sm">{message}</p>
              <Link
                href="/"
                className="inline-block px-6 py-2 bg-blue-500 hover:bg-blue-600 text-white rounded-md transition-colors"
              >
                В дашборд
              </Link>
            </>
          )}
          {(state === 'invalid' || state === 'expired' || state === 'error') && (
            <>
              <AlertCircle
                size={48}
                className={`mx-auto mb-4 ${state === 'expired' ? 'text-orange-400' : 'text-red-400'}`}
              />
              <h1 className="text-xl font-semibold mb-2">
                {state === 'expired' ? 'Ссылка истекла' : 'Ссылка недействительна'}
              </h1>
              <p className="text-slate-400 mb-6 text-sm">{message}</p>
              {state === 'expired' && (
                <p className="text-xs text-slate-500 mb-4">
                  Войдите в аккаунт — на странице профиля будет кнопка «Отправить письмо повторно».
                </p>
              )}
              <Link
                href="/"
                className="inline-block px-6 py-2 border border-slate-700 text-slate-300 hover:bg-slate-800 rounded-md transition-colors"
              >
                На главную
              </Link>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

export default function VerifyEmailPage() {
  return (
    <Suspense fallback={<div className="min-h-screen bg-slate-950" />}>
      <VerifyEmailContent />
    </Suspense>
  );
}
