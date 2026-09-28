// INFRA-02 (frontend): Sentry server-side init (Node runtime).
//
// Подключается через `instrumentation.ts` → register() при NEXT_RUNTIME=nodejs.
// Без `SENTRY_DSN` — no-op (dev/CI билды без внешних отправок).
import * as Sentry from '@sentry/nextjs';

const dsn = process.env.SENTRY_DSN;

if (dsn) {
  Sentry.init({
    dsn,
    environment: process.env.SENTRY_ENV || 'production',
    tracesSampleRate: 0.1,
  });
}
