'use client';

/**
 * FE-06 — App Router root error boundary.
 *
 * Next.js рендерит этот файл, когда любая страница / layout под `app/` бросает
 * исключение. Соседний `global-error.tsx` срабатывает только если упал сам
 * root layout — здесь ловим всё остальное. Кнопка `reset` пытается ре-рендерить
 * сегмент без полного reload.
 */
import { useEffect } from 'react';

export default function RootError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error('Root error:', error);
  }, [error]);

  return (
    <div className="min-h-screen flex items-center justify-center p-8">
      <div className="max-w-md text-center">
        <h2 className="text-2xl font-bold mb-2">Что-то пошло не так</h2>
        <p className="text-muted mb-4">Попробуйте обновить страницу или повторить.</p>
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
