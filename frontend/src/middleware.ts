// SEC-14 (Sprint 6, Batch 3) — per-request CSP nonce.
//
// Next.js 16 переименовал middleware → proxy, но имя файла остаётся
// `src/middleware.ts` (стабильный entry-point, fully backward-compatible).
// Файл выставляет Content-Security-Policy для HTML-страниц с уникальным
// base64-nonce на каждый запрос, что позволяет убрать 'unsafe-inline' из
// script-src (главный смысл задачи).
//
// Архитектурное разделение:
//   - frontend middleware → CSP для HTML (этот файл, авторитативный)
//   - backend SecurityHeadersMiddleware → CSP для API JSON (strict default-src none)
//
// Nonce пробрасывается в server components через `headers().get('x-nonce')`
// и в свои скрипты Next.js инжектирует автоматически (SSR nonce injection
// читает CSP header и подставляет nonce= в <script>/<style>).
//
// matcher исключает API/_next-static/favicon — нет смысла генерить nonce
// для запросов без HTML; и исключает router prefetch чтобы не плодить
// мёртвые nonce'ы в HTTP-кэше.
import { NextRequest, NextResponse } from 'next/server';

export function middleware(request: NextRequest): NextResponse {
  // crypto.randomUUID() доступен в Edge Runtime (Web Crypto). Buffer тоже
  // доступен — Next.js полифилит для Edge.
  const nonce = Buffer.from(crypto.randomUUID()).toString('base64');

  // Dev-окружение: фронтенд на :3000 ходит на backend :8000 → разрешаем
  // localhost/127.0.0.1 в connect-src. В production это не подмешивается.
  const isDev = process.env.NODE_ENV !== 'production';
  const devConnect = isDev
    ? " http://localhost:8000 http://127.0.0.1:8000 ws://localhost:* ws://127.0.0.1:*"
    : "";

  // Multi-line источник схлопывается в одну строку для HTTP-заголовка.
  // - style-src оставляет 'unsafe-inline' — Tailwind / next/font / styled-jsx
  //   генерируют inline-styles, а strict style-src ломает рендер до того, как
  //   мы успеем мигрировать на nonce-style (отдельная задача после SEC-14).
  // - script-src получает 'nonce-...' + 'strict-dynamic' (любой script с
  //   правильным nonce может догрузить дочерние скрипты — Next.js chunks).
  // - hosts (Sentry / yookassa) сохранены для совместимости с виджетами
  //   и капчей платежей; при 'strict-dynamic' современные браузеры их
  //   игнорируют, но для legacy-fallback оставляем.
  const cspHeader = `
    default-src 'self';
    script-src 'self' 'nonce-${nonce}' 'strict-dynamic' https://*.ingest.sentry.io https://yookassa.ru;
    style-src 'self' 'unsafe-inline';
    img-src 'self' data: blob: https:;
    font-src 'self' data:;
    connect-src 'self' https://*.ingest.sentry.io https://api.yookassa.ru https://invest-public-api.tbank.ru https://invest-public-api.tinkoff.ru wss:${devConnect};
    frame-ancestors 'none';
    base-uri 'self';
    form-action 'self' https://yookassa.ru;
    object-src 'none';
  `
    .replace(/\s{2,}/g, ' ')
    .trim();

  // Пробрасываем nonce внутрь request.headers, чтобы Server Components
  // могли прочитать через `(await headers()).get('x-nonce')`.
  const requestHeaders = new Headers(request.headers);
  requestHeaders.set('x-nonce', nonce);

  const response = NextResponse.next({
    request: { headers: requestHeaders },
  });

  // Выставляем CSP в response — браузер enforce'ит. Также повторяем в
  // request-side (см. Next.js docs: required для SSR nonce injection в
  // некоторых runtime'ах).
  response.headers.set('Content-Security-Policy', cspHeader);

  return response;
}

export const config = {
  matcher: [
    // Применяем ко всем HTML-маршрутам, исключая API/static/prefetch.
    // Backend FastAPI отдаёт CSP для своих JSON-ответов через
    // SecurityHeadersMiddleware → strict default-src 'none'.
    {
      source: '/((?!api|_next/static|_next/image|favicon.ico).*)',
      missing: [
        { type: 'header', key: 'next-router-prefetch' },
        { type: 'header', key: 'purpose', value: 'prefetch' },
      ],
    },
  ],
};
