# API Versioning Strategy

## Текущее состояние (v0.2)

API эндпоинты живут БЕЗ префикса версии:
- `POST /auth/login`
- `GET /trades/`
- `GET /stats/`

Это работает пока у нас один клиент (наш Next.js фронт), но любой breaking change
ломает прод **в момент деплоя бэкенда**, до того как фронт успел обновить контракты.

## Целевое состояние (v0.3+)

Все «бизнес»-эндпоинты доступны под префиксом `/v1/`:
- `POST /v1/auth/login`
- `GET /v1/trades/`
- `GET /v1/stats/`

Эндпоинты, которые НЕ версионируются:
- `/health`, `/ready` — для оркестратора
- `/metrics` — для Prometheus
- `/docs`, `/redoc`, `/openapi.json` — meta

## Миграционный план (без downtime)

### Шаг 1 — dual-mount (1 релиз)
```python
# main.py
for r, prefix in (
    (auth_router, ""),
    (trades_router, ""),
    ...
):
    app.include_router(r, prefix=prefix)
    app.include_router(r, prefix=f"/v1{prefix}")  # дублируем под /v1
```
Бэкенд начинает отдавать оба варианта. Фронт продолжает использовать legacy-пути.

### Шаг 2 — переезд фронта (1–2 спринта)
В `frontend/src/lib/apiClient.ts` поменять `BASE_URL` или добавить `API_PREFIX = "/v1"`.
Деплой фронта. На этом этапе оба варианта в проде работают одинаково.

### Шаг 3 — добавить deprecation header на legacy (1 релиз)
```python
@app.middleware("http")
async def deprecate_legacy(request, call_next):
    response = await call_next(request)
    if not request.url.path.startswith(("/v1/", "/health", "/ready", "/docs", "/redoc")):
        response.headers["Deprecation"] = "true"
        response.headers["Sunset"] = "Mon, 01 Sep 2026 00:00:00 GMT"
        response.headers["Link"] = '</v1' + request.url.path + '>; rel="successor-version"'
    return response
```
Логировать каждый legacy-запрос — кто ещё пользуется (мобильный клиент? скрипт?).

### Шаг 4 — удалить legacy (через ≥30 дней после Sunset-даты)
Снести dual-mount, оставить только `/v1/...`.

## Когда заводить `/v2/`?

Только когда нужны breaking changes контракта (переименование полей, изменение
семантики, удаление endpoint'а). Аддитивные изменения (новый endpoint, новое
поле в ответе) — НЕ требуют v2.

## Чек-лист breaking change

Если изменение хоть в одном пункте — это breaking, нужна новая версия:
- Удалили поле из response
- Переименовали поле
- Поменяли тип поля (int → string)
- Сделали optional → required в request
- Удалили endpoint
- Поменяли HTTP status code на success
- Поменяли семантику параметра (например, `limit` теперь page-size, а не offset)
