# Архитектура Empirik

> Эталонный высокоуровневый обзор. Низкоуровневые решения — в `decisions/`.

## Топология

```
┌─────────────┐         ┌──────────────┐         ┌─────────────┐
│  Browser    │ ──────► │  Next.js 16  │ ──────► │  FastAPI    │
│ (React 19)  │         │   :3000      │         │  :8000/8003 │
└─────────────┘         └──────────────┘         └─────────────┘
                          │ Server fetch                │
                          │ httpOnly cookies            │
                          │ passthrough                 │
                                                  ┌─────┴─────┐
                                                  │ SQLite    │ dev
                                                  │ /Postgres │ prod
                                                  └───────────┘
                                                  ┌───────────┐
                                                  │ Redis     │ prod
                                                  └───────────┘
                                                  ┌───────────┐
                                                  │ MOEX ISS  │ external
                                                  │ Tinkoff   │ external
                                                  └───────────┘
```

## Backend (`backend/`)

- **FastAPI 0.109+** на gunicorn (4 workers, tini PID 1, non-root)
- **SQLAlchemy 2.0** ORM, **Alembic** миграции
- **Структура:**
  - `main.py` — точка входа, lifespan, error handlers
  - `routers/` — 16 файлов: `auth`, `trades`, `stats`, `stats_tags`, `accounts`, `admin`, `blog`, `broker`, `deposits`, `market`, `payments`, `real_pnl`, `replay`, `review`, `setups`
  - `services/` — `pd_deletion`, `stats_cache`
  - `analytics/` — Optimal f, SQN, Z-Score, Sharpe, Sortino, Calmar, Ulcer, K-Ratio, Sterling, Omega, Monte Carlo, MAE/MFE
  - `models.py` — единый файл, все доменные сущности
  - `schemas.py` — Pydantic v2 схемы
  - `config.py` — единый источник env-настроек

## Frontend (`frontend/`)

- **Next.js 16.1** App Router + **React 19.2**
- **TypeScript strict**, **Tailwind v4**, **Recharts**, **TanStack Query**
- **Структура:**
  - `src/app/` — 25+ роутов (page.tsx, login/, register/, history/, journal/, calculator/, analysis/* (8 подстраниц), review/, blog/[slug]/, manual/, help/, pricing/, profile/, admin/, privacy/, dashboard-demo/)
  - `src/components/` — AppShell, CommandPalette (Cmd+K), 7 Modal'ов, dashboard/, ui/
  - `src/contexts/` — Auth, Settings (Language)
  - `src/lib/` — apiClient (Client), serverApiClient (Server), QueryProvider
  - `src/i18n/` — ru/en JSON

## Интеграции

| Сервис | Назначение | Файл |
|---|---|---|
| MOEX ISS | Котировки, свечи, IMOEX | `market_service.py`, `moex_service.py` |
| Tinkoff Invest API | Sync сделок (FIFO, дедупликация, 60s интервал) | `tinkoff_service.py` |
| Anthropic API | AI-инсайты (опц.) | `ai_service.py` |
| Yandex/Sber/Tinkoff/Google OAuth | Регистрация/вход | `oauth_service.py`, PKCE-compliant |
| ЮKassa | Платежи (stub, не реализовано) | `routers/payments.py` |

## Безопасность (контур)

- JWT HS256, bcrypt cost=14
- Раздельные ключи `SECRET_KEY` / `REFRESH_SECRET_KEY` (enforced different)
- httpOnly + secure (prod) + samesite=lax cookies
- CSRF double-submit (cookie + X-CSRF-Token header)
- CORS whitelist + методы whitelist
- Rate limit (slowapi + Redis или memory fallback)
- Sentry с PII-фильтром

## Тесты

- 363 backend (pytest), 0 frontend
- Smoke-тесты в `backend/scripts/_smoke_*.py`

## Не охвачено документацией пока

- Деплой-пайплайн (см. `operations/deployment.md`)
- Мониторинг (см. `operations/monitoring.md`)
- Schema контрактов (см. `tech/api-contracts.md`)
