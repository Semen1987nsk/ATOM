import type { NextConfig } from "next";
import { withSentryConfig } from "@sentry/nextjs";

const nextConfig: NextConfig = {
  // INFRA-06: standalone output даёт минимальную Docker-сборку (только
  // `.next/standalone` + `node_modules` нужных пакетов). Образ ~150MB
  // вместо 1GB при копировании всей `node_modules`.
  output: 'standalone',
  images: {
    // FE-09: разрешаем оптимизацию для известных источников.
    // - localhost:8000 — dev-backend (uploads, screenshots сделок)
    // - empirik.io / api.empirik.io — prod-backend через nginx-proxy
    // Произвольные user-input URLs (article.cover_image, blob:/data: previews)
    // остаются с `unoptimized` — см. соответствующие комментарии в JSX.
    remotePatterns: [
      { protocol: 'http', hostname: 'localhost', port: '8000', pathname: '/uploads/**' },
      { protocol: 'http', hostname: 'localhost', port: '8000', pathname: '/api/**' },
      { protocol: 'https', hostname: 'empirik.io', pathname: '/uploads/**' },
      { protocol: 'https', hostname: 'empirik.io', pathname: '/api/**' },
      { protocol: 'https', hostname: 'api.empirik.io', pathname: '/uploads/**' },
      { protocol: 'https', hostname: 'api.empirik.io', pathname: '/**' },
    ],
  },
};

// INFRA-02 (frontend): withSentryConfig оборачивает Next.js конфиг, добавляет
// инструментацию (autoInstrumentServerFunctions, серверный middleware,
// source-map upload в CI). Без SENTRY_DSN сборка проходит, sources не
// аплоадятся (silent fail by design).
//
// Sentry SDK v10: `hideSourceMaps` устарел → используем
// `sourcemaps.deleteSourcemapsAfterUpload: true`, чтобы карты не лежали в
// `.next/static` после билда (security: source code recovery prevention).
export default withSentryConfig(nextConfig, {
  silent: !process.env.CI,
  org: process.env.SENTRY_ORG,
  project: 'empirik-frontend',
  sourcemaps: {
    deleteSourcemapsAfterUpload: true,
  },
});
