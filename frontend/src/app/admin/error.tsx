'use client';

/**
 * FE-06 — per-route error boundary для /admin/*.
 *
 * Админ-панель чувствительна: ошибки в health/users/audit-табах не должны
 * валить весь app. Логируем + предлагаем повторить рендер.
 */
import { useEffect } from 'react';

export default function AdminError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error('Admin route error:', error);
  }, [error]);

  return (
    <div className="min-h-screen flex items-center justify-center p-8">
      <div className="max-w-md text-center">
        <h2 className="text-2xl font-bold mb-2">Ошибка в админ-панели</h2>
        <p className="text-muted mb-4">Не удалось загрузить раздел. Попробуйте повторить.</p>
        {error.digest && (
          <p className="text-xs text-muted mb-4">ID: {error.digest}</p>
        )}
        <button onClick={reset} className="btn-primary">
          Повторить
        </button>
      </div>
    </div>
  );
}
