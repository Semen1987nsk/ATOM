// INFRA-02 (frontend): Next.js Instrumentation hook.
// Next 13.4+ runs `register()` once at server startup. Используется для
// инициализации Sentry на server runtime (Node) и edge runtime (если нужно).
//
// Edge runtime пока не настроен — добавим если миддлвары начнут жить на edge.
export async function register() {
  if (process.env.NEXT_RUNTIME === 'nodejs') {
    await import('./sentry.server.config');
  }
}
