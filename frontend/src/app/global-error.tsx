'use client';

/**
 * FE-06 — App Router global error boundary.
 *
 * Срабатывает ТОЛЬКО когда упал сам root layout (см. `layout.tsx`) и
 * `error.tsx` не может отрендериться. Это означает «провайдеры сломаны»,
 * поэтому здесь нет доступа к LanguageProvider/SettingsProvider — текст
 * жёстко прописан. Файл обязан рендерить `<html>` и `<body>` сам.
 */
import { useEffect } from 'react';
import * as Sentry from '@sentry/nextjs';

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error('Global error:', error);
    Sentry.captureException(error);
  }, [error]);

  return (
    <html lang="ru">
      <body>
        <div className="min-h-screen flex items-center justify-center p-8">
          <div className="max-w-md text-center">
            <h2 className="text-2xl font-bold mb-2">Критическая ошибка</h2>
            <p className="mb-4">Перезагрузите страницу.</p>
            {error.digest && (
              <p className="text-xs mb-4">ID: {error.digest}</p>
            )}
            <button onClick={reset} className="btn-primary">
              Перезагрузить
            </button>
          </div>
        </div>
      </body>
    </html>
  );
}
