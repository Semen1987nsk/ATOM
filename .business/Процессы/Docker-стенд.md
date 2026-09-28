Статус: действует
Для кого: агент
Приоритетный способ: из Git Bash в корне репо — `docker compose -f docker-compose.yml -f "$TEMP/compose.localport.yml" up -d --wait postgres redis`, затем миграции и тесты backend на этом стенде
Запасные способы: без Docker — sqlite по процедуре [Сборка и тесты](Сборка-и-тесты.md); миграционные проверки на Postgres тогда не повторяются
Запрещено: трогать чужой Postgres на 5432 (`C:\dev\.worktrees\_pg15`); класть файл переопределения в репо; брать Sub CA с gu-st.ru — там выпуск, который индекс T-Bank не заверяет
Команда проверки применимости: `docker compose ps --format '{{.Name}} {{.Health}}'` → `atom-postgres healthy` и `atom-redis healthy`
Проверено: 2026-09-28
Годно до: 2027-03
Якоря: `docker-compose.yml` (сервисы postgres, redis, backend), `backend/alembic/versions/`, `backend/Dockerfile`, `backend/certs/`, `backend/requirements.lock`

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
7. Образ backend: `docker build -t atom-backend:local -f backend/Dockerfile backend` — около 5,5 минуты без кэша. Проверка: `docker run` в сети `polistata_atom-net` с `--env-file backend/.env` и переменными из блока `environment` сервиса backend в `docker-compose.yml` (включая `LOG_DIR`), порт `127.0.0.1:18000:8000` → `curl http://127.0.0.1:18000/health` отдаёт 200, `docker exec … id -un` → `atom`.
8. Остановить: `docker compose stop postgres redis`; данные остаются в томе.

## Почему так

- Порт 5432 на этой машине занят чужим Postgres, поэтому стенд слушает 55432. Тег `!override` заменяет список портов, а не дописывает к нему (Compose v2.24+).
- Индекс T-Bank отдаёт только свой сертификат, издатель — Russian Trusted Sub CA выпуска 2024 года (идентификатор ключа `77:3D:D9:…`, до 2029-07-19). Builder-стадия берёт корневой и этот Sub CA из `backend/certs/`. Сверка: `openssl verify -CAfile backend/certs/russian_trusted_root_ca.crt -untrusted backend/certs/russian_trusted_sub_ca.crt <сертификат сервера>` → OK.
- Образ ставит пакеты из `requirements.lock`, как CI. По `requirements.txt` резолв давал SQLAlchemy 2.1, которой для `postgresql://` нужен psycopg 3, и воркер падал при старте.

## Первое исполнение 2026-09-28

- Docker 29.8.0, Compose v5.5.1; atom-postgres и atom-redis — healthy.
- `alembic upgrade head` прошёл до `0031`. `alembic check` сначала показал дрейф: удалить `ix_trades_tags_gin` (индекс из миграции 0028 не описан в `models.py`); после описания индекса только для Postgres — чисто.
- Образ backend: с Sub CA с gu-st.ru — `CERTIFICATE_VERIFY_FAILED` на каждом пакете индекса; с Sub CA 2024 года — 0 таких ошибок, сборка 337 с. По `requirements.txt` в образ попадали SQLAlchemy 2.1.1 и alembic 1.20.0, воркер падал на `import psycopg`; по lock — 2.0.49 и 1.18.4, `/health` → 200 за 6 с.
- Тесты backend: 1414 прошло, 4 пропущено, 2 упало, 1 ошибка, 344 с. Упавшие `test_orchestrator.py::test_concurrent_calls_dont_double_sync`, `test_debug_warning.py::test_debug_true_logs_warning` и ошибка `test_market_service_async.py::test_get_client_returns_singleton` в одиночном прогоне зелёные — зависимость от порядка тестов.
