# Environment Variables Reference

Полный список ENV-переменных, которые читает backend.
Используй как чеклист при обновлении `backend/.env.example` и при подготовке prod-секретов.

---

## APP

| Variable | Required | Default | Notes |
|---|---|---|---|
| `APP_NAME` | no | `ATOM API` | |
| `APP_VERSION` | no | `0.2.0` | |
| `DEBUG` | no | `false` | **В проде ОБЯЗАТЕЛЬНО `false`** — иначе fallback-секреты и tracebacks |

## SECURITY (fail-fast в проде)

| Variable | Required | Default | Notes |
|---|---|---|---|
| `SECRET_KEY` | **prod: yes** | dev-random | Сгенерировать `python -c "import secrets; print(secrets.token_urlsafe(64))"` |
| `REFRESH_SECRET_KEY` | **prod: yes** | dev-random | **ДОЛЖЕН отличаться от SECRET_KEY**, иначе fail-fast |
| `BCRYPT_ROUNDS` | no | `14` | 12 — старый дефолт; 14 — рекомендация на 2026 |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | no | `30` | |
| `REFRESH_TOKEN_EXPIRE_DAYS` | no | `7` | |
| `ACCESS_TOKEN_COOKIE_NAME` | no | `atom_access_token` | |
| `REFRESH_TOKEN_COOKIE_NAME` | no | `atom_refresh_token` | |
| `CSRF_COOKIE_NAME` | no | `atom_csrf_token` | |
| `CSRF_HEADER_NAME` | no | `X-CSRF-Token` | |
| `AUTH_COOKIE_DOMAIN` | no | (none) | `.empirik.io` для cross-subdomain |
| `AUTH_COOKIE_PATH` | no | `/` | |
| `AUTH_COOKIE_SAMESITE` | no | `lax` | `none` если фронт на другом домене |
| `AUTH_COOKIE_SECURE` | no | true в проде | Требует HTTPS |

## DATABASE

| Variable | Required | Default | Notes |
|---|---|---|---|
| `DATABASE_URL` | yes | `sqlite:///./atom.db` | Prod: `postgresql://user:pass@host:5432/db` |
| `AUTO_INIT_DB` | no | true в DEBUG | В проде используй `alembic upgrade head` |
| `DB_POOL_SIZE` | no | `5` | Postgres only |
| `DB_MAX_OVERFLOW` | no | `10` | Postgres only |
| `DB_POOL_TIMEOUT` | no | `30` | Postgres only |
| `DB_POOL_RECYCLE` | no | `1800` | сек, обнуляет stale connections |
| `SQL_ECHO` | no | `false` | Логировать ВСЕ запросы (не для прода) |

## REDIS / RATE LIMITING

| Variable | Required | Default | Notes |
|---|---|---|---|
| `REDIS_URL` | **prod: yes** | (none) | Без Redis OAuth state и rate limiter — in-memory (некорректно с multi-worker) |
| `RATE_LIMIT_ENABLED` | no | `true` | |
| `RATE_LIMIT_STORAGE_URI` | no | `REDIS_URL` | можно отдельный DB-индекс |
| `RATE_LIMIT_STRATEGY` | no | `fixed-window` | `moving-window` точнее, дороже |

## CORS

| Variable | Required | Default | Notes |
|---|---|---|---|
| `CORS_ORIGINS` | yes (prod) | `localhost:3000` (dev) | Comma-separated. **Не используй `*` с allow_credentials** |
| `CORS_ORIGIN_REGEX` | no | github.dev pattern | Для PR-preview |

## LOGGING / OBSERVABILITY

| Variable | Required | Default | Notes |
|---|---|---|---|
| `LOG_LEVEL` | no | `INFO` | DEBUG/INFO/WARNING/ERROR |
| `LOG_FORMAT_MODE` | no | `text` | `json` для агрегаторов (Loki, ELK, Datadog) |
| `ENABLE_FILE_LOGGING` | no | `true` | Ротация 5×5MB |
| `LOG_DIR` | no | `<repo>/logs` | В контейнере: `/var/log/atom` |
| `SENTRY_DSN` | no | (none) | Если задан — инициализируется Sentry SDK |
| `SENTRY_ENVIRONMENT` | no | `production` | dev/staging/production |
| `SENTRY_TRACES_SAMPLE_RATE` | no | `0.05` | 0.0–1.0 (5% — разумный дефолт для прода) |
| `SENTRY_RELEASE` | no | (none) | Например, git sha — сильно помогает в Sentry UI |

## UPLOADS

| Variable | Required | Default | Notes |
|---|---|---|---|
| `MAX_UPLOAD_SIZE_MB` | no | `10` | Защита от xlsx-bomb |

## INTEGRATIONS

| Variable | Required | Default | Notes |
|---|---|---|---|
| `OAUTH_HTTP_TIMEOUT_SECONDS` | no | `15` | |
| `OPEN_POSITION_SYNC_LOOKBACK_DAYS` | no | `30` | |
| `OAUTH_REDIRECT_BASE_URL` | yes (если OAuth) | (none) | например `https://api.empirik.io` |
| `GOOGLE_CLIENT_ID` / `_SECRET` | no | (none) | Без них Google OAuth недоступен |
| `YANDEX_CLIENT_ID` / `_SECRET` | no | (none) | |
| `SBER_CLIENT_ID` / `_SECRET` | no | (none) | |
| `TINKOFF_CLIENT_ID` / `_SECRET` | no | (none) | |
| `OPENAI_API_KEY` | no | (none) | В РФ — через прокси / Yandex GPT / GigaChat |

## PROXY / IP

| Variable | Required | Default | Notes |
|---|---|---|---|
| `TRUSTED_PROXIES` | no | (empty) | Comma-separated CIDR. Иначе X-Forwarded-For игнорируется |

## ADMIN BOOTSTRAP

| Variable | Required | Default | Notes |
|---|---|---|---|
| `ADMIN_BOOTSTRAP_EMAIL` | no | (none) | Используется только при первом запуске init-скрипта |
| `ADMIN_BOOTSTRAP_PASSWORD` | no | (none) | NEVER коммить пароль |

---

## Минимальный prod `.env`

```ini
DEBUG=false
SECRET_KEY=<token_urlsafe(64)>
REFRESH_SECRET_KEY=<token_urlsafe(64) — другой!>
BCRYPT_ROUNDS=14
DATABASE_URL=postgresql://atom:atom@postgres:5432/atom
AUTO_INIT_DB=false
REDIS_URL=redis://redis:6379/0
CORS_ORIGINS=https://app.empirik.io
AUTH_COOKIE_SECURE=true
AUTH_COOKIE_SAMESITE=lax
LOG_FORMAT_MODE=json
SENTRY_DSN=https://...@sentry.io/...
OAUTH_REDIRECT_BASE_URL=https://api.empirik.io
```

## Минимальный dev `.env`

```ini
DEBUG=true
SECRET_KEY=devkey1234567890abcdefghijklmnopqrstuvwxyz
REFRESH_SECRET_KEY=devrefresh0987654321zyxwvutsrqponmlkj
DATABASE_URL=sqlite:///./atom.db
AUTO_INIT_DB=true
CORS_ORIGINS=http://localhost:3000
```
