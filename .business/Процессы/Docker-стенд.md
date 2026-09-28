Статус: действует
Для кого: агент
Приоритетный способ: из Git Bash в корне репо — `docker compose -f docker-compose.yml -f "$TEMP/compose.localport.yml" up -d --wait postgres redis`, затем миграции и тесты backend на этом стенде
Запасные способы: без Docker — sqlite по процедуре [Сборка и тесты](Сборка-и-тесты.md); миграционные проверки на Postgres тогда не повторяются
Запрещено: трогать чужой Postgres на 5432 (`C:\dev\.worktrees\_pg15`); класть файл переопределения в репо; поднимать `backend` и `nginx` из compose — образ backend не собирается (см. «Почему так»)
Команда проверки применимости: `docker compose ps --format '{{.Name}} {{.Health}}'` → `atom-postgres healthy` и `atom-redis healthy`
Проверено: 2026-09-28
Годно до: 2027-03
Якоря: `docker-compose.yml` (сервисы postgres и redis), `backend/alembic/versions/`, `backend/Dockerfile`

## Порядок

1. Docker Desktop запущен. Его `docker` не в PATH: `export PATH="/c/Users/Семен/AppData/Local/Programs/DockerDesktop/resources/bin:$PATH"`.
2. Файл переопределения порта вне репо, `$TEMP/compose.localport.yml`:
   ```yaml
   services:
     postgres:
       ports: !override
         - "127.0.0.1:55432:5432"
   ```
3. `docker compose -f docker-compose.yml -f "$TEMP/compose.localport.yml" up -d --wait postgres redis` — около минуты при первом скачивании образов.
4. Переменные для backend в той же оболочке: `DATABASE_URL=postgresql://atom:atom@127.0.0.1:55432/atom`, `REDIS_URL=redis://127.0.0.1:6379/0`.
5. Из `backend/`: `.venv/Scripts/python -m alembic upgrade head`, затем `.venv/Scripts/python -m alembic check` → «No new upgrade operations detected».
6. Тесты backend на стенде — команда из процедуры [Сборка и тесты](Сборка-и-тесты.md) с переменными шага 4, около 6 минут.
7. Остановить: `docker compose stop postgres redis`; данные остаются в томе.

## Почему так

- Порт 5432 на этой машине занят чужим Postgres, поэтому стенд слушает 55432. Тег `!override` заменяет список портов, а не дописывает к нему (Compose v2.24+).
- Образ backend не собирается: `pip install` внутри `python:3.11-slim` падает на TLS индекса T-Bank, в образе нет Russian Trusted Root/Sub CA. Правка `backend/Dockerfile` — релизный артефакт, решение владельца.

## Первое исполнение 2026-09-28

- Docker 29.8.0, Compose v5.5.1; atom-postgres и atom-redis — healthy.
- `alembic upgrade head` прошёл до `0031`. `alembic check` сначала показал дрейф: удалить `ix_trades_tags_gin` (индекс из миграции 0028 не описан в `models.py`); после описания индекса только для Postgres — чисто.
- Тесты backend: 1414 прошло, 4 пропущено, 2 упало, 1 ошибка, 344 с. Упавшие `test_orchestrator.py::test_concurrent_calls_dont_double_sync`, `test_debug_warning.py::test_debug_true_logs_warning` и ошибка `test_market_service_async.py::test_get_client_returns_singleton` в одиночном прогоне зелёные — зависимость от порядка тестов.
