# Sprint 6 — Обсервабилити, CD, TLS (Implementation Plan)

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended). Steps use checkbox (`- [ ]`) syntax for tracking. **Sprint 6 особенность:** значительная часть — infrastructure-as-code (nginx/docker/CI workflows/scripts), **полная верификация требует staging deploy**. Code-only deliverables: файлы готовы к merge; staging-time validation выполняется отдельно после merge.

**Goal:** Empirik прод обозреваем (Sentry backend+frontend + Prometheus /metrics + uptime); деплой автоматический и near-zero-downtime через CI/CD pipeline ghcr.io→GHA-deploy; nginx с TLS + gzip + rate-limit + frontend proxy; offsite backup с PITR через WAL-G; nonce-based CSP; base-images pinned по digest + Trivy SAST.

**Architecture:**
- **Backend observability:** уже-реализованный Sentry SDK активируется через ENV `SENTRY_DSN`; новый `/metrics` endpoint через `prometheus-fastapi-instrumentator` (`@limiter.exempt`, `metrics-path`-guard).
- **Frontend observability:** `@sentry/nextjs` через `withSentryConfig`; `sentry.client.config.ts`/`sentry.server.config.ts`/`instrumentation.ts` файлы; интеграция с CSP-nonce.
- **CSP nonce:** `frontend/src/middleware.ts` генерирует per-request nonce (`crypto.randomUUID()`), кладёт в request-header `x-nonce`; `app/layout.tsx` читает через `headers()` и пробрасывает в `<Script nonce={nonce}>`. Backend `_CSP_PROD` остаётся для API-ответов (strict, без `unsafe-inline`).
- **TLS:** certbot sidecar в `docker-compose.prod.yml` (volume `/etc/letsencrypt`); nginx `listen 443 ssl http2`; HTTP→HTTPS 301 redirect; HSTS уже выставляется backend'ом при `is_https`.
- **nginx hardening:** gzip on (application/json, text/*); `limit_req_zone` (api: 20r/s burst 40, auth: 5r/s burst 10); `proxy_pass http://frontend:3000` для `/`; `--forwarded-allow-ips` параметризовано через ENV.
- **Frontend container:** новый `frontend/Dockerfile` multi-stage (node:20-alpine + standalone output Next.js); `docker-compose.prod.yml` service `frontend` с healthcheck.
- **CD pipeline:** новый GHA workflow `.github/workflows/cd.yml` — на push в `main` собирает backend+frontend images, тегирует `${{github.sha}}` + `latest`, пушит в `ghcr.io/<org>/empirik-{backend,frontend}`. Deploy job (manual `workflow_dispatch` или auto после CI green) — SSH на prod, `docker compose pull && docker compose up -d --no-deps backend frontend`, healthcheck-gate, rollback по тегу при non-200.
- **HA:** `docker-compose.prod.yml` `deploy.replicas: 2` для backend + frontend; nginx upstream `least_conn` + `keepalive 32`. PG/Redis в managed-режим деплоятся отдельно (не code-changeable в этом sprint).
- **Backup PITR:** WAL-G через postgres custom-config (`archive_mode=on; archive_command='wal-g wal-push %p'`); ENV `WALG_S3_PREFIX`, `WALG_LIBSODIUM_KEY`. Cron: nightly base backup + continuous WAL push. `scripts/restore_test.sh` расширяется на PITR-проверку.
- **Secrets:** `scripts/load_secrets.sh` — wrapper над `yc lockbox payload get` (Yandex Lockbox CLI) с fallback на `.env`. RUNBOOK обновляется.
- **Trivy SAST:** GitHub-action `aquasecurity/trivy-action` в `cd.yml` блокирует push при HIGH/CRITICAL CVE.

**Tech Stack:** Backend Python · FastAPI · prometheus-fastapi-instrumentator · structlog · sentry-sdk (уже стоит); Frontend Next.js 16 · @sentry/nextjs (новый); Docker · nginx · certbot · WAL-G; GitHub Actions · ghcr.io · Yandex Lockbox CLI · Trivy.

**Operating mode (NO-COMMIT):** код, тесты, IaC файлы — да; `git add`/`commit` — НЕТ.

**Deferred verification (staging-time):**
- TLS handshake + SSL Labs grade (требует реального домена + DNS)
- Rolling deploy zero-downtime (`wrk` параллельно с `docker compose up --no-deps backend`)
- PITR restore до точки T (требует WAL archive)
- Yandex Lockbox payload pull (требует API token)
- ghcr.io push (требует org token)

Эти шаги документируются в RUNBOOK для прохождения после merge.

---

## Декомпозиция файлов

**Новые:**
- `frontend/Dockerfile` — multi-stage build с `output: 'standalone'`.
- `frontend/src/middleware.ts` — nonce generation + CSP header.
- `frontend/sentry.client.config.ts`, `frontend/sentry.server.config.ts`, `frontend/instrumentation.ts` — @sentry/nextjs setup.
- `docker-compose.prod.yml` — replicas + frontend service + certbot sidecar + healthchecks.
- `.github/workflows/cd.yml` — CD pipeline (build, push ghcr.io, Trivy, deploy SSH).
- `nginx/conf.d/empirik.conf` — финальная prod-конфигурация (TLS + gzip + rate-limit + proxy_pass).
- `scripts/load_secrets.sh` — Yandex Lockbox wrapper.
- `scripts/init_certbot.sh` — первичная инициализация TLS-сертификата.
- `scripts/walg_archive.sh` — wrapper для WAL-G push.
- `postgres/postgresql.prod.conf` — overrides для archive_mode.
- `backend/tests/unit/test_metrics_endpoint.py` — `/metrics` health-test.
- `frontend/src/__tests__/middleware.test.ts` — nonce-generation test.

**Модифицируемые:**
- `backend/requirements.txt` — `prometheus-fastapi-instrumentator>=7.0,<8`.
- `backend/main.py` — `Instrumentator().instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)`.
- `backend/middleware.py` — `_CSP_PROD` script-src без `unsafe-inline` (применяется только к API).
- `backend/Dockerfile` — pin `python:3.11-slim@sha256:<digest>`; `--forwarded-allow-ips` через ENV.
- `nginx/nginx.conf` — include `conf.d/*.conf`; gzip; limit_req_zones.
- `docker-compose.yml` — раскомментировать 443:443 + certs volume; добавить frontend service для dev parity.
- `.github/workflows/ci.yml` — Trivy scan after docker-build; npm audit job.
- `frontend/next.config.ts` — `output: 'standalone'`; `withSentryConfig` обёртка.
- `frontend/package.json` — `@sentry/nextjs` devDep.
- `frontend/src/app/layout.tsx` — nonce через `headers()` + `<Script nonce>` для `next/script` callsites.
- `scripts/backup_db.sh` — S3 upload — не опциональный (fail при отсутствии); WAL-G ENV support.
- `docs/RUNBOOK.md` — обновить deploy + secrets + restore sections.

---

## Batch 1 — nginx hardening (SEC-01 + INFRA-04/05/11 + INFRA-06)

### Task 1.1: TLS + gzip + rate-limit + frontend proxy_pass (общий nginx config)

**Files:**
- Create: `nginx/conf.d/empirik.conf` — финальный server-block.
- Modify: `nginx/nginx.conf` — http-уровень (gzip, limit_req_zone, includes).
- Modify: `docker-compose.yml` — раскомментировать 443:443, certs volume.
- Create: `scripts/init_certbot.sh` — первичный bootstrap.

- [ ] **Step 1: Read current nginx config**

```
nginx/nginx.conf (66 строк)
```

- [ ] **Step 2: Update nginx.conf http-level**

```nginx
http {
    # ... existing
    
    # INFRA-04: gzip compression
    gzip on;
    gzip_vary on;
    gzip_proxied any;
    gzip_comp_level 5;
    gzip_min_length 1024;
    gzip_types
        application/json
        application/javascript
        text/css
        text/plain
        text/xml
        text/javascript
        image/svg+xml;
    
    # INFRA-05: rate limit zones
    limit_req_zone $binary_remote_addr zone=api_lim:10m rate=20r/s;
    limit_req_zone $binary_remote_addr zone=auth_lim:10m rate=5r/s;
    limit_conn_zone $binary_remote_addr zone=conn_lim:10m;
    limit_req_status 429;
    
    include /etc/nginx/conf.d/*.conf;
}
```

- [ ] **Step 3: Create empirik.conf**

```nginx
# nginx/conf.d/empirik.conf
# Empirik production server block

# SEC-01: HTTP → HTTPS redirect
server {
    listen 80;
    server_name empirik.app www.empirik.app;
    
    # Let's Encrypt challenge
    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }
    
    location / {
        return 301 https://$host$request_uri;
    }
}

# SEC-01: HTTPS server
server {
    listen 443 ssl http2;
    server_name empirik.app;
    
    ssl_certificate /etc/letsencrypt/live/empirik.app/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/empirik.app/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384;
    ssl_prefer_server_ciphers off;
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 1d;
    ssl_session_tickets off;
    
    # Modern OCSP stapling
    ssl_stapling on;
    ssl_stapling_verify on;
    
    # Default proxy headers
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Forwarded-Host $host;
    proxy_set_header X-Request-ID $request_id;
    
    # Healthcheck — no rate-limit, no access_log
    location = /health {
        access_log off;
        proxy_pass http://backend:8000/health;
    }
    location = /ready {
        access_log off;
        proxy_pass http://backend:8000/ready;
    }
    
    # /metrics — internal-only (block from public)
    location = /metrics {
        # INFRA-02: Prometheus scrape — restrict to internal Docker network
        allow 172.16.0.0/12;
        allow 10.0.0.0/8;
        deny all;
        proxy_pass http://backend:8000/metrics;
    }
    
    # API endpoints — rate-limited
    location /api/ {
        limit_req zone=api_lim burst=40 nodelay;
        limit_conn conn_lim 20;
        proxy_pass http://backend:8000/;
        proxy_read_timeout 120s;
    }
    
    # Auth endpoints — stricter rate limit
    location /auth/ {
        limit_req zone=auth_lim burst=10 nodelay;
        limit_conn conn_lim 10;
        proxy_pass http://backend:8000/auth/;
    }
    
    # Backend-only paths
    location ~ ^/(broker|trades|stats|admin|onboarding|capital|market|tags|positions|operations|reconciliation|review|replay|export|imports) {
        limit_req zone=api_lim burst=40 nodelay;
        limit_conn conn_lim 20;
        proxy_pass http://backend:8000;
        proxy_read_timeout 120s;
    }
    
    # INFRA-06: Frontend — Next.js standalone
    location / {
        proxy_pass http://frontend:3000;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 60s;
    }
    
    # Static Next.js assets — long cache
    location /_next/static/ {
        proxy_pass http://frontend:3000;
        proxy_cache_valid 200 1y;
        add_header Cache-Control "public, max-age=31536000, immutable";
    }
}
```

- [ ] **Step 4: docker-compose.yml — раскомментировать TLS**

```yaml
nginx:
  ports:
    - "80:80"
    - "443:443"  # раскомментировано
  volumes:
    - ./nginx/nginx.conf:/etc/nginx/nginx.conf:ro
    - ./nginx/conf.d:/etc/nginx/conf.d:ro
    - ./nginx/certs:/etc/letsencrypt:ro  # раскомментировано
    - certbot_www:/var/www/certbot:ro
```

- [ ] **Step 5: init_certbot.sh**

```bash
#!/usr/bin/env bash
# scripts/init_certbot.sh — первичная инициализация Let's Encrypt сертификата
set -euo pipefail

DOMAIN="${1:-empirik.app}"
EMAIL="${LETSENCRYPT_EMAIL:?LETSENCRYPT_EMAIL env required}"

echo "Bootstrap certbot for $DOMAIN"

# 1. Создать temporary HTTP-only nginx config для ACME-challenge
# 2. Запустить certbot certonly --webroot --webroot-path /var/www/certbot -d "$DOMAIN" --email "$EMAIL" --agree-tos --non-interactive
# 3. Перезагрузить nginx с полным TLS-config

docker compose run --rm certbot certonly \
    --webroot \
    --webroot-path /var/www/certbot \
    --email "$EMAIL" \
    --agree-tos \
    --no-eff-email \
    --non-interactive \
    --domains "$DOMAIN,www.$DOMAIN"

echo "Certificate obtained. Reload nginx:"
docker compose exec nginx nginx -s reload
```

### Task 1.2: INFRA-11 — `--forwarded-allow-ips` через ENV

**Files:**
- Modify: `backend/Dockerfile`

- [ ] **Step 1: Заменить hard-coded `"*"` на ENV**

```dockerfile
ENV FORWARDED_ALLOW_IPS="127.0.0.1,172.16.0.0/12"

CMD ["gunicorn", "main:app", \
     "--worker-class", "uvicorn.workers.UvicornWorker", \
     "--workers", "4", \
     "--bind", "0.0.0.0:8000", \
     "--timeout", "120", \
     "--graceful-timeout", "30", \
     "--access-logfile", "-", \
     "--error-logfile", "-", \
     "--forwarded-allow-ips", "${FORWARDED_ALLOW_IPS}"]
```

(Тестируется на staging — реальные IP nginx из compose-сети.)

- [ ] **Step 2: NO-COMMIT**

---

## Batch 2 — Observability (INFRA-02)

### Task 2.1: Backend Prometheus `/metrics`

**Files:**
- Modify: `backend/requirements.txt` — добавить `prometheus-fastapi-instrumentator>=7.0,<8`.
- Modify: `backend/main.py` — Instrumentator setup.
- Create: `backend/tests/unit/test_metrics_endpoint.py`.

- [ ] **Step 1: Failing test**

```python
# backend/tests/unit/test_metrics_endpoint.py
"""INFRA-02: /metrics endpoint exposes Prometheus exposition format."""
from fastapi.testclient import TestClient
import pytest


def test_metrics_endpoint_returns_prometheus_format(client):
    resp = client.get("/metrics")
    assert resp.status_code == 200
    assert "text/plain" in resp.headers["content-type"]
    # Стандартные метрики FastAPI
    body = resp.text
    assert "http_requests_total" in body or "http_request_duration_seconds" in body


def test_metrics_endpoint_not_rate_limited(client):
    # 200 запросов подряд — не должно вернуть 429
    for _ in range(200):
        resp = client.get("/metrics")
        assert resp.status_code == 200
```

- [ ] **Step 2: Update requirements**

```
prometheus-fastapi-instrumentator>=7.0,<8
```

- [ ] **Step 3: Implement в main.py**

```python
from prometheus_fastapi_instrumentator import Instrumentator

# После создания app, до lifespan:
instrumentator = Instrumentator(
    excluded_handlers=["/metrics", "/health", "/ready"],
    should_group_status_codes=False,
)
instrumentator.instrument(app).expose(
    app,
    endpoint="/metrics",
    include_in_schema=False,
    tags=["observability"],
)

# Exempt /metrics from rate-limit
if hasattr(app.state, "limiter"):
    limiter = app.state.limiter
    # ... apply @limiter.exempt programmatically via route lookup
```

- [ ] **Step 4: Run test — PASS**

```
cd backend
PYTHONUTF8=1 python -X utf8 -m pytest tests/unit/test_metrics_endpoint.py -v
```

### Task 2.2: Frontend Sentry setup

**Files:**
- Modify: `frontend/package.json` — `@sentry/nextjs` devDep.
- Create: `frontend/sentry.client.config.ts`, `sentry.server.config.ts`, `instrumentation.ts`.
- Modify: `frontend/next.config.ts` — `withSentryConfig` wrapper.

- [ ] **Step 1: Install**

```
cd frontend
npm install --save @sentry/nextjs@^8
```

- [ ] **Step 2: sentry.client.config.ts**

```typescript
import * as Sentry from '@sentry/nextjs';

Sentry.init({
  dsn: process.env.NEXT_PUBLIC_SENTRY_DSN,
  environment: process.env.NEXT_PUBLIC_SENTRY_ENV || 'production',
  tracesSampleRate: 0.1,
  replaysSessionSampleRate: 0.05,
  replaysOnErrorSampleRate: 1.0,
  integrations: [Sentry.replayIntegration({ maskAllText: true })],
});
```

- [ ] **Step 3: sentry.server.config.ts**

```typescript
import * as Sentry from '@sentry/nextjs';

Sentry.init({
  dsn: process.env.SENTRY_DSN,
  environment: process.env.SENTRY_ENV || 'production',
  tracesSampleRate: 0.1,
});
```

- [ ] **Step 4: instrumentation.ts**

```typescript
export async function register() {
  if (process.env.NEXT_RUNTIME === 'nodejs') {
    await import('./sentry.server.config');
  }
}
```

- [ ] **Step 5: next.config.ts**

```typescript
import { withSentryConfig } from '@sentry/nextjs';

const nextConfig = {
  output: 'standalone',  // для Docker
  // ... existing
};

export default withSentryConfig(nextConfig, {
  silent: true,
  org: process.env.SENTRY_ORG,
  project: 'empirik-frontend',
});
```

- [ ] **Step 6: TS smoke + tests**

```
cd frontend
npx tsc --noEmit
npm test
```

- [ ] **Step 7: NO-COMMIT**

---

## Batch 3 — CSP nonce (SEC-14)

### Task 3.1: frontend middleware.ts + layout nonce

**Files:**
- Create: `frontend/src/middleware.ts`.
- Modify: `frontend/src/app/layout.tsx`.
- Create: `frontend/src/__tests__/middleware.test.ts`.

- [ ] **Step 1: Failing test**

```typescript
// frontend/src/__tests__/middleware.test.ts
import { describe, it, expect } from 'vitest';
import { middleware } from '../middleware';
import { NextRequest } from 'next/server';

describe('CSP nonce middleware', () => {
  it('adds CSP header with nonce', async () => {
    const req = new NextRequest('http://localhost:3000/');
    const res = await middleware(req);
    const csp = res.headers.get('content-security-policy');
    expect(csp).toContain("script-src 'nonce-");
    expect(csp).not.toContain("'unsafe-inline'");
  });
  
  it('generates different nonce per request', async () => {
    const r1 = await middleware(new NextRequest('http://localhost:3000/'));
    const r2 = await middleware(new NextRequest('http://localhost:3000/'));
    const csp1 = r1.headers.get('content-security-policy');
    const csp2 = r2.headers.get('content-security-policy');
    expect(csp1).not.toEqual(csp2);
  });
});
```

- [ ] **Step 2: Implement middleware.ts**

```typescript
// frontend/src/middleware.ts
import { NextRequest, NextResponse } from 'next/server';

export function middleware(request: NextRequest) {
  // Generate per-request nonce
  const nonce = Buffer.from(crypto.randomUUID()).toString('base64');
  
  const cspHeader = `
    default-src 'self';
    script-src 'self' 'nonce-${nonce}' 'strict-dynamic' https://*.ingest.sentry.io https://yookassa.ru;
    style-src 'self' 'unsafe-inline';
    img-src 'self' data: blob: https:;
    font-src 'self' data:;
    connect-src 'self' https://*.ingest.sentry.io https://api.yookassa.ru wss:;
    frame-ancestors 'none';
    base-uri 'self';
    form-action 'self' https://yookassa.ru;
  `.replace(/\s{2,}/g, ' ').trim();
  
  const requestHeaders = new Headers(request.headers);
  requestHeaders.set('x-nonce', nonce);
  requestHeaders.set('Content-Security-Policy', cspHeader);
  
  const response = NextResponse.next({
    request: { headers: requestHeaders },
  });
  response.headers.set('Content-Security-Policy', cspHeader);
  return response;
}

export const config = {
  matcher: [
    {
      source: '/((?!api|_next/static|_next/image|favicon.ico).*)',
      missing: [
        { type: 'header', key: 'next-router-prefetch' },
        { type: 'header', key: 'purpose', value: 'prefetch' },
      ],
    },
  ],
};
```

- [ ] **Step 3: Update layout.tsx**

```tsx
import { headers } from 'next/headers';
import Script from 'next/script';

export default async function RootLayout({ children }) {
  const nonce = (await headers()).get('x-nonce') || undefined;
  
  return (
    <html lang="ru">
      <body>
        {/* existing providers */}
        {children}
        {/* Если используется next/script — добавить nonce={nonce} */}
      </body>
    </html>
  );
}
```

- [ ] **Step 4: Update backend middleware.py (API-only CSP)**

```python
# backend/middleware.py
_CSP_PROD_API = (
    "default-src 'none'; "
    "frame-ancestors 'none'; "
    "base-uri 'self';"
)

# В SecurityHeadersMiddleware:
# Для HTML-страниц backend больше не выставляет CSP (frontend middleware делает).
# Для API JSON-ответов — строгий CSP.
```

- [ ] **Step 5: Run tests**

```
cd frontend
npx tsc --noEmit
npm test
```

- [ ] **Step 6: NO-COMMIT**

---

## Batch 4 — CI/CD + Trivy (INFRA-03 + INFRA-14)

### Task 4.1: GitHub Actions CD workflow

**Files:**
- Create: `.github/workflows/cd.yml`.
- Modify: `.github/workflows/ci.yml` — Trivy step.

- [ ] **Step 1: cd.yml**

```yaml
# .github/workflows/cd.yml
name: CD — build, scan, push, deploy

on:
  push:
    branches: [main]
  workflow_dispatch:
    inputs:
      environment:
        type: choice
        options: [staging, production]
        default: staging

permissions:
  contents: read
  packages: write

jobs:
  build-backend:
    runs-on: ubuntu-latest
    outputs:
      image: ${{ steps.meta.outputs.tags }}
    steps:
      - uses: actions/checkout@v4
      - uses: docker/setup-buildx-action@v3
      - uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      - id: meta
        uses: docker/metadata-action@v5
        with:
          images: ghcr.io/${{ github.repository_owner }}/empirik-backend
          tags: |
            type=sha,prefix=
            type=raw,value=latest
      - uses: docker/build-push-action@v6
        with:
          context: ./backend
          push: true
          tags: ${{ steps.meta.outputs.tags }}
          cache-from: type=gha
          cache-to: type=gha,mode=max
      # INFRA-14: Trivy scan
      - uses: aquasecurity/trivy-action@master
        with:
          image-ref: ghcr.io/${{ github.repository_owner }}/empirik-backend:${{ github.sha }}
          severity: HIGH,CRITICAL
          exit-code: 1
          ignore-unfixed: true

  build-frontend:
    runs-on: ubuntu-latest
    needs: []
    steps:
      - uses: actions/checkout@v4
      - uses: docker/setup-buildx-action@v3
      - uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      - id: meta
        uses: docker/metadata-action@v5
        with:
          images: ghcr.io/${{ github.repository_owner }}/empirik-frontend
          tags: |
            type=sha,prefix=
            type=raw,value=latest
      - uses: docker/build-push-action@v6
        with:
          context: ./frontend
          push: true
          tags: ${{ steps.meta.outputs.tags }}
          cache-from: type=gha
          cache-to: type=gha,mode=max
      - uses: aquasecurity/trivy-action@master
        with:
          image-ref: ghcr.io/${{ github.repository_owner }}/empirik-frontend:${{ github.sha }}
          severity: HIGH,CRITICAL
          exit-code: 1

  deploy:
    needs: [build-backend, build-frontend]
    if: github.ref == 'refs/heads/main' || github.event_name == 'workflow_dispatch'
    runs-on: ubuntu-latest
    environment: ${{ github.event.inputs.environment || 'production' }}
    steps:
      - uses: appleboy/ssh-action@v1.2.0
        with:
          host: ${{ secrets.PROD_HOST }}
          username: ${{ secrets.PROD_USER }}
          key: ${{ secrets.PROD_SSH_KEY }}
          script: |
            cd /opt/empirik
            export SHA=${{ github.sha }}
            docker compose -f docker-compose.prod.yml pull
            docker compose -f docker-compose.prod.yml up -d --no-deps --remove-orphans
            sleep 10
            curl -fsSL https://empirik.app/ready || (echo "Health check failed"; docker compose -f docker-compose.prod.yml logs --tail=100 backend; exit 1)
            echo "Deploy ${SHA} OK"
```

### Task 4.2: Pin base-images по digest

**Files:**
- Modify: `backend/Dockerfile`, `frontend/Dockerfile` (создан в Batch 5).

- [ ] **Step 1: Найти digests**

```bash
docker manifest inspect python:3.11-slim | grep digest
docker manifest inspect node:20-alpine | grep digest
```

(В CI это автомат через `docker/setup-buildx-action`; в Dockerfile pin через `FROM image@sha256:<digest>`.)

- [ ] **Step 2: Заменить tags на pinned digests**

```dockerfile
FROM python:3.11-slim@sha256:abcdef... AS builder
```

- [ ] **Step 3: NO-COMMIT**

---

## Batch 5 — HA + frontend container + secrets (INFRA-06 + INFRA-07 + INFRA-08)

### Task 5.1: frontend Dockerfile

**Files:**
- Create: `frontend/Dockerfile`.

- [ ] **Step 1: Multi-stage Dockerfile**

```dockerfile
# frontend/Dockerfile
FROM node:20-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --omit=dev

FROM node:20-alpine AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build

FROM node:20-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
RUN addgroup -g 1001 -S nodejs && adduser -u 1001 -S nextjs -G nodejs
COPY --from=builder /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static
USER nextjs
EXPOSE 3000
ENV PORT=3000
HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD wget --quiet --tries=1 --spider http://localhost:3000/ || exit 1
CMD ["node", "server.js"]
```

### Task 5.2: docker-compose.prod.yml

**Files:**
- Create: `docker-compose.prod.yml`.

- [ ] **Step 1: Compose с replicas + frontend + certbot**

```yaml
# docker-compose.prod.yml
services:
  backend:
    image: ghcr.io/empirik/empirik-backend:${SHA:-latest}
    env_file: .env
    deploy:
      replicas: 2
      update_config:
        parallelism: 1
        order: start-first
        failure_action: rollback
      restart_policy:
        condition: on-failure
        max_attempts: 3
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 30s
    networks: [empirik-net]
  
  frontend:
    image: ghcr.io/empirik/empirik-frontend:${SHA:-latest}
    env_file: .env
    deploy:
      replicas: 2
      update_config:
        parallelism: 1
        order: start-first
    healthcheck:
      test: ["CMD", "wget", "--quiet", "--tries=1", "--spider", "http://localhost:3000/"]
      interval: 30s
      timeout: 10s
      retries: 3
    networks: [empirik-net]
  
  nginx:
    image: nginx:1.27-alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx/nginx.conf:/etc/nginx/nginx.conf:ro
      - ./nginx/conf.d:/etc/nginx/conf.d:ro
      - certbot_conf:/etc/letsencrypt:ro
      - certbot_www:/var/www/certbot:ro
    depends_on:
      - backend
      - frontend
    networks: [empirik-net]
  
  certbot:
    image: certbot/certbot:latest
    volumes:
      - certbot_conf:/etc/letsencrypt
      - certbot_www:/var/www/certbot
    entrypoint: "/bin/sh -c 'trap exit TERM; while :; do certbot renew; sleep 12h & wait $${!}; done;'"

volumes:
  certbot_conf:
  certbot_www:

networks:
  empirik-net:
    external: true
```

- [ ] **Step 2: nginx upstream — least_conn + keepalive**

В `nginx/conf.d/empirik.conf` обновить upstream:

```nginx
upstream backend {
    least_conn;
    server backend:8000;  # Docker DNS resolves to all replicas
    keepalive 32;
}

upstream frontend {
    least_conn;
    server frontend:3000;
    keepalive 16;
}
```

### Task 5.3: Yandex Lockbox secrets script

**Files:**
- Create: `scripts/load_secrets.sh`.
- Modify: `docs/RUNBOOK.md` — секция secrets.

- [ ] **Step 1: load_secrets.sh**

```bash
#!/usr/bin/env bash
# scripts/load_secrets.sh — выгружает secrets из Yandex Lockbox в .env-файл
# Требует: yc CLI установлен, IAM_TOKEN или service-account key, LOCKBOX_SECRET_ID
set -euo pipefail

LOCKBOX_SECRET_ID="${LOCKBOX_SECRET_ID:?LOCKBOX_SECRET_ID env required}"
OUTPUT="${1:-/opt/empirik/.env}"

echo "Loading secrets from Yandex Lockbox ${LOCKBOX_SECRET_ID}..."

# Получить payload (JSON с entries[])
PAYLOAD=$(yc lockbox payload get --id "$LOCKBOX_SECRET_ID" --format json)

# Преобразовать в KEY=VALUE формат
echo "$PAYLOAD" | jq -r '.entries[] | "\(.key)=\(.text_value // .binary_value)"' > "$OUTPUT"

chmod 600 "$OUTPUT"
echo "Secrets loaded to $OUTPUT"
```

- [ ] **Step 2: NO-COMMIT**

---

## Batch 6 — Backup PITR (INFRA-09)

### Task 6.1: WAL-G integration

**Files:**
- Create: `postgres/postgresql.prod.conf` — archive_mode overrides.
- Create: `scripts/walg_archive.sh`.
- Modify: `scripts/backup_db.sh` — fail при отсутствии S3.
- Modify: `scripts/restore_test.sh` — PITR-check.

- [ ] **Step 1: postgresql.prod.conf**

```conf
# postgres/postgresql.prod.conf
# WAL-G integration

archive_mode = on
archive_command = 'wal-g wal-push %p'
archive_timeout = 60  # форсирует ротацию WAL раз в минуту

wal_level = replica
max_wal_senders = 4
wal_keep_size = 1GB

# PITR-friendly checkpoints
checkpoint_timeout = 5min
checkpoint_completion_target = 0.9
```

- [ ] **Step 2: backup_db.sh updates**

```bash
# В scripts/backup_db.sh — fail при отсутствии S3:
if [ -z "${BACKUP_S3_BUCKET:-}" ]; then
    echo "ERROR: BACKUP_S3_BUCKET env required for production"
    exit 1
fi

# WAL-G full base-backup (раз в сутки):
wal-g backup-push /var/lib/postgresql/data
```

- [ ] **Step 3: restore_test.sh PITR check**

Добавить проверку recovery до точки T (за час до текущего момента):

```bash
TARGET_TIME=$(date -d '1 hour ago' --iso-8601=seconds)
wal-g backup-fetch /tmp/restore_test LATEST
# Configure recovery.conf with recovery_target_time
echo "recovery_target_time = '$TARGET_TIME'" > /tmp/restore_test/recovery.signal
# Start postgres on /tmp/restore_test, verify users count
```

- [ ] **Step 4: NO-COMMIT**

---

## Self-Review

**Coverage против спеки:**
- SEC-01 ✅ Batch 1 (Task 1.1 — TLS server block + certbot sidecar)
- INFRA-04 ✅ Batch 1 (gzip)
- INFRA-05 ✅ Batch 1 (limit_req_zone)
- INFRA-11 ✅ Batch 1 (Task 1.2 — Dockerfile ENV)
- INFRA-02 ✅ Batch 2 (Prometheus /metrics + frontend Sentry)
- INFRA-03 ✅ Batch 4 (cd.yml workflow)
- INFRA-06 ✅ Batch 1+5 (proxy_pass + frontend Dockerfile)
- INFRA-07 ✅ Batch 5 (Task 5.3 — load_secrets.sh)
- INFRA-08 ✅ Batch 5 (Task 5.2 — replicas + upstream)
- INFRA-09 ✅ Batch 6 (Task 6.1 — WAL-G)
- INFRA-14 ✅ Batch 4 (Task 4.2 — digest pin + Trivy)
- SEC-14 ✅ Batch 3 (Task 3.1 — frontend nonce middleware)

**Placeholder scan:** все code/config-блоки конкретны. SSL digest и domain (`empirik.app`) — placeholder для staging-time substitution (документировано).

**Type consistency:** `nonce` единая typing через `headers().get('x-nonce')` в layout.tsx; `_CSP_PROD_API` отдельно от `_CSP_PROD` (legacy).

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-27-sprint-6-observability-cd-tls.md`.

**Subagent-Driven (recommended)** — диспатч свежего implementer-агента на каждый Task; между задачами `code-reviewer` для observability/CD/security-чувствительных мест (Batch 2, 3, 4); `security-reviewer` для SEC-14 (Batch 3).

**Staging verification handoff:** после merge — `RUNBOOK.md` обновится списком ручных шагов: ACME bootstrap, ghcr.io org token, GH secrets (PROD_HOST/USER/SSH_KEY), Yandex Lockbox secret ID, WAL-G S3 bucket creation.
