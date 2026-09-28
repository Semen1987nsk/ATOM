// INFRA-02 (frontend): Sentry client-side init.
//
// Активируется только если задан `NEXT_PUBLIC_SENTRY_DSN`. Без DSN —
// no-op, что позволяет dev/CI собирать билд без отправки событий в Sentry.
//
// Session Replay: 5% всех сессий + 100% при ошибке. Maskhouse: текст и
// медиа маскируются по умолчанию (PII safety).
import * as Sentry from '@sentry/nextjs';

const dsn = process.env.NEXT_PUBLIC_SENTRY_DSN;

if (dsn) {
  Sentry.init({
    dsn,
    environment: process.env.NEXT_PUBLIC_SENTRY_ENV || 'production',
    tracesSampleRate: 0.1,
    replaysSessionSampleRate: 0.05,
    replaysOnErrorSampleRate: 1.0,
    integrations: [
      Sentry.replayIntegration({
        maskAllText: true,
        blockAllMedia: true,
      }),
    ],
  });
}
