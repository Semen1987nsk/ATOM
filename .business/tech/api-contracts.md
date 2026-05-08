# API контракты Eqio

> Краткий справочник по ключевым endpoint'ам. Полная OpenAPI — на `/docs` (FastAPI).

## Auth (`/auth`)

| Метод | Endpoint | Тело / Параметры | Ответ |
| --- | --- | --- | --- |
| POST | `/auth/register` | `{email, password (12+), name?, pd_consent: bool}` | `200 TokenPair` или `400` (consent), `422` (validation) |
| POST | `/auth/login` | `{email, password}` | `200 TokenPair`, `401`, `403` (deactivated) |
| POST | `/auth/refresh` | refresh cookie | `200 TokenPair` |
| POST | `/auth/logout` | — | `204` |
| GET | `/auth/me` | — (cookie auth) | `UserResponse` |
| PUT | `/auth/me` | `UserUpdate` | `UserResponse` |
| **DELETE** | **`/auth/me`** | **`{password, reason?}`** | **`202 deletion_requested` (152-ФЗ)** |
| **GET** | **`/auth/me/export`** | — (cookie auth) | **`UserDataExport` JSON со всеми ПД (152-ФЗ ст. 14, rate-limit 5/hour)** |
| POST | `/auth/change-password` | `{old_password, new_password}` | `200` или `400` |
| GET | `/auth/oauth/providers` | — | список включённых OAuth |
| GET | `/auth/oauth/{provider}/authorize` | `?redirect_uri=...` | URL для редиректа (PKCE) |
| POST | `/auth/oauth/{provider}/callback` | `{code, state, code_verifier}` | `TokenPair` |

## Trades (`/trades`)

| Метод | Endpoint | Назначение |
| --- | --- | --- |
| GET | `/trades/` | Список сделок, фильтры по периоду/тегу/символу |
| POST | `/trades/` | Создать сделку (manual entry) |
| PATCH | `/trades/{id}` | Обновить сделку |
| PATCH | `/trades/{id}/close` | Закрыть открытую сделку |
| DELETE | `/trades/{id}` | Удалить сделку |
| POST | `/import/tinkoff` | Импорт из Тинькофф (Excel) |

## Stats (`/stats` и `/stats/...`)

> God-router. Расщепляется. Текущее состояние:

| Метод | Endpoint | Что возвращает |
| --- | --- | --- |
| GET | `/stats/` | Главный дашборд: PnL, win rate, equity_curve, imoex_curve, initial_balance, базовые метрики |
| GET | `/stats/advanced` | Ulcer, K-Ratio, Sterling, Omega, Sharpe, Sortino, Calmar |
| GET | `/stats/benchmark` | Сравнение с когортой/индексом |
| GET | `/stats/setups` | Группировка по сетапам |
| GET | `/stats/calendar` | Daily PnL heatmap |
| GET | `/stats/mae-mfe-analysis` | MAE/MFE с группировкой по тегам/сетапам |
| GET | `/stats/audit` | Аудит сделок |
| GET | `/tags/` | Список тегов с статистикой (вынесено в `routers/stats_tags.py`) |
| GET | `/stats/tags/` | То же, под префиксом `/stats` (для совместимости) |

## Market (`/market`, `/replay`, `/real-pnl`)

| Метод | Endpoint | Что |
| --- | --- | --- |
| GET | `/market/quotes` | Текущие котировки |
| GET | `/market/candles` | Исторические свечи (для Trade Replay, MAE/MFE) |
| GET | `/replay/{trade_id}` | Свечи вокруг сделки |
| GET | `/real-pnl/{account_id}` | Реальный PnL из брокера |

## Blog / Admin / Subscription / Payments

— см. `routers/blog.py`, `routers/admin.py`, `routers/payments.py` (все имеют `response_model`, описаны в OpenAPI).

## Соглашения

1. **Все mutating endpoints** требуют CSRF (header `X-CSRF-Token` парный к cookie `atom_csrf_token`).
2. **Auth через httpOnly cookies** — `atom_access_token`, `atom_refresh_token`. Bearer-токен поддерживается как fallback.
3. **Rate limits** на login (5/min), register (3/min), AI (10/min).
4. **Ошибки** возвращают `{detail, error?, request_id}`. `request_id` — для корреляции с логами.
5. **Pagination** пока только в `/trades/` (limit/offset). В `/stats/...` без пагинации (TODO).

## Что ломаем при изменении

При **любом** изменении контракта — обновить:

1. `frontend/src/lib/api.generated.ts` (через `npm run gen:api-types:from-file`)
2. Этот файл
3. Тесты в `backend/tests/`

## Версионирование

API не версионировано (`/v1/...` нет). При breaking changes:

- предупредить в CHANGELOG
- добавить deprecated-warning в OpenAPI на 1 релиз
- удалить в следующем
