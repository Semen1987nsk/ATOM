# syntax=docker/dockerfile:1.7
# ============================================================================
#  Empirik Frontend — multi-stage Dockerfile (INFRA-06).
#  Финальный образ: node:20-alpine + .next/standalone, ~150MB вместо 1GB,
#  non-root, healthcheck через wget на корне (Next.js не имеет встроенного
#  /healthz, корневой / отвечает 200 после готовности).
#
#  next.config.ts: output: 'standalone' (Batch 2) — упаковывает только нужные
#  модули в `.next/standalone/`, остальное (devDependencies, source-maps до
#  upload, локализации moment и т.п.) выкидывается.
# ============================================================================

# ───────────────── Stage 1: deps ─────────────────
# Слой кешируется между билдами кода. Меняется только когда меняется
# package-lock.json — иначе npm ci пропускается из кэша.
FROM node:20-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

# ───────────────── Stage 2: builder ─────────────────
FROM node:20-alpine AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .

# Отключаем телеметрию Next.js — не нужно слать данные на vercel.com из CI.
ENV NEXT_TELEMETRY_DISABLED=1

# Sentry source-maps upload требует SENTRY_AUTH_TOKEN + SENTRY_ORG в CI.
# При локальной сборке без токена — `silent: !process.env.CI` пропускает upload.
RUN npm run build

# ───────────────── Stage 3: runner ─────────────────
FROM node:20-alpine AS runner
WORKDIR /app

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0

# wget уже есть в node:20-alpine (BusyBox); curl докинем только при необходимости.

# Non-root user — uid 1001, чтобы не пересекаться с типовым 1000 на хосте.
RUN addgroup -g 1001 -S nodejs && \
    adduser -u 1001 -S nextjs -G nodejs

# Standalone-сборка содержит сервер + минимальный набор node_modules.
# public/ и .next/static копируются отдельно: standalone их не вкладывает,
# чтобы избежать дублирования при scale (можно вынести в shared volume).
COPY --from=builder /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

USER nextjs
EXPOSE 3000

# wget --spider возвращает exit 0 если 2xx, иначе exit !=0.
# start-period 20s — Next.js хочет ~10-15с на init роутеров.
HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD wget --quiet --tries=1 --spider http://localhost:3000/ || exit 1

# server.js — entrypoint standalone-сборки, генерируется Next.js при build.
CMD ["node", "server.js"]
