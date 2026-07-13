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
      <body style={{ margin: 0, background: '#0b0b0d', color: '#f5f5f5', fontFamily: 'system-ui, sans-serif' }}>
        <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 32 }}>
          <div style={{ maxWidth: 420, textAlign: 'center' }}>
            <h2 style={{ fontSize: 24, fontWeight: 700, marginBottom: 8 }}>Критическая ошибка</h2>
            <p style={{ marginBottom: 16, opacity: 0.85 }}>Перезагрузите страницу.</p>
            {error.digest && (
              <p style={{ fontSize: 12, marginBottom: 16, opacity: 0.6 }}>ID: {error.digest}</p>
            )}
            <button
              onClick={() => window.location.reload()}
              style={{
                background: '#E2521C', color: '#fff', border: 'none', borderRadius: 8,
                padding: '10px 20px', fontSize: 14, cursor: 'pointer',
              }}
            >
              Перезагрузить
            </button>
          </div>
        </div>
      </body>
    </html>
  );
}
