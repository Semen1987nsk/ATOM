# Миграция данных SQLite → PostgreSQL

Документ для разового переезда production-БД с SQLite на PostgreSQL.
**Не запускай скрипт без проверки на копии данных.**

---

## Зачем

SQLite в проде с FastAPI multi-worker имеет жёсткие ограничения:
- `StaticPool` отдаёт один коннект на всё приложение → `SQLITE_BUSY` при concurrent write.
- Нет встроенного `pool_recycle`, нет `pool_pre_ping`.
- WAL-mode помогает, но не решает: запись всегда сериализуется.

Postgres решает это и плюс даёт реальные UNIQUE-constraint, EXPLAIN ANALYZE, репликацию, бэкапы.

## Когда переезжать

Когда **любое** из:
- > 10 одновременных активных пользователей.
- > 100 000 строк в `trades`.
- Появилась нужда в read-репликах или бэкапе через `pg_dump`/WAL-archive.

Для одного пользователя на Windows-десктопе SQLite остаётся приемлемым.

## Stratagy: blue-green (zero-downtime)

### Шаг 0 — подготовка
```bash
# Бэкап SQLite
cp backend/atom.db backend/atom.db.backup-$(date +%Y%m%d)

# Поднять Postgres рядом (см. docker-compose.yml)
docker compose up -d postgres

# Создать схему через alembic в новой БД
DATABASE_URL=postgresql://atom:atom@localhost:5432/atom \
  alembic -c backend/alembic.ini upgrade head
```

### Шаг 1 — выгрузить данные из SQLite
Используем **pgloader** — единственный надёжный инструмент для SQLite→PG миграции,
корректно обрабатывает типы (Numeric, JSON, Enum) и автоматически escape'ит даты.

```bash
# Установить pgloader (Linux)
sudo apt-get install pgloader

# Или Docker:
docker run --rm \
  -v $(pwd)/backend:/data \
  --network host \
  dimitri/pgloader \
  pgloader --with "data only" \
           sqlite:///data/atom.db \
           postgresql://atom:atom@localhost:5432/atom
```

**Важно:** `--with "data only"` — схема уже создана через alembic, иначе pgloader перетрёт типы.

### Шаг 2 — sanity-check
```sql
-- Считаем строки в обеих БД и сравниваем
SELECT 'users' AS t, COUNT(*) FROM users
UNION ALL SELECT 'accounts', COUNT(*) FROM accounts
UNION ALL SELECT 'trades', COUNT(*) FROM trades
UNION ALL SELECT 'subscriptions', COUNT(*) FROM subscriptions
UNION ALL SELECT 'payments', COUNT(*) FROM payments
UNION ALL SELECT 'deposit_history', COUNT(*) FROM deposit_history
UNION ALL SELECT 'capital_operations', COUNT(*) FROM capital_operations
UNION ALL SELECT 'broker_connections', COUNT(*) FROM broker_connections
UNION ALL SELECT 'articles', COUNT(*) FROM articles;
```

```sql
-- Денежные суммы должны сходиться до копейки
SELECT SUM(net_pnl) FROM trades WHERE net_pnl IS NOT NULL;
SELECT SUM(amount) FROM deposit_history;
SELECT SUM(amount) FROM payments WHERE status = 'COMPLETED';
```

### Шаг 3 — синхронизировать sequence'ы
SQLite использует `INTEGER PRIMARY KEY AUTOINCREMENT` без отдельной sequence.
В Postgres после COPY надо выровнять SERIAL/IDENTITY:

```sql
DO $$ DECLARE r record;
BEGIN
  FOR r IN SELECT
    table_name,
    column_name,
    pg_get_serial_sequence(quote_ident(table_name), column_name) AS seq
  FROM information_schema.columns
  WHERE column_default LIKE 'nextval%'
  LOOP
    IF r.seq IS NOT NULL THEN
      EXECUTE format(
        'SELECT setval(%L, COALESCE((SELECT MAX(%I) FROM %I), 1))',
        r.seq, r.column_name, r.table_name
      );
    END IF;
  END LOOP;
END $$;
```

### Шаг 4 — переключить трафик
```bash
# В .env поменять:
DATABASE_URL=postgresql://atom:atom@postgres:5432/atom
# AUTO_INIT_DB=false  ← обязательно, иначе create_all() побьёт схему

# Перезапустить backend (zero-downtime через rolling restart, если behind LB)
docker compose up -d --no-deps --force-recreate backend
```

### Шаг 5 — мониторинг 24 ч
- `/ready` endpoint → проверять DB-пинг.
- Sentry → ловить любые `IntegrityError` (могут вылезти из-за UNIQUE-constraint, который SQLite молча игнорировал).
- `pg_stat_activity` → глазами проверить, что нет залипших коннектов.

### Шаг 6 — отключить SQLite
- Удалить `backend/atom.db` из деплоя (но **сохранить backup минимум 90 дней**).
- Удалить SQLite-специфичные ветки в `database.py:32-39` (когда уверен, что dev тоже на PG).

---

## Почему НЕ через `dump → restore`

`sqlite3 atom.db .dump > out.sql` + `psql < out.sql` НЕ сработает:
- SQLite использует другой синтаксис для PRIMARY KEY AUTOINCREMENT.
- BLOB и JSON колонки требуют разных escape-правил.
- Datetime в SQLite — TEXT, в Postgres — `timestamp without time zone`.

pgloader делает это автоматически.

---

## Откат

Если в течение 24 ч найдены проблемы:
```bash
# Вернуть .env на SQLite
DATABASE_URL=sqlite:///./atom.db

# Restore из бэкапа (только если в SQLite за это время писали — обычно нет)
cp backend/atom.db.backup-YYYYMMDD backend/atom.db

docker compose up -d --no-deps --force-recreate backend
```

Postgres-БД оставить — пригодится для повторной попытки.

---

## Чек-лист готовности

- [ ] Сделан backup `atom.db` с датой
- [ ] Postgres запущен и `alembic upgrade head` отработал
- [ ] pgloader перенёс данные
- [ ] Row counts совпадают
- [ ] Денежные суммы совпадают до копейки
- [ ] Sequence'ы выровнены
- [ ] `.env` обновлён, `AUTO_INIT_DB=false`
- [ ] Перезапуск backend, `/ready` отвечает 200
- [ ] Sentry в течение 1 ч не показал DB-ошибок
- [ ] Уведомлены пользователи (если потребовалось окно обслуживания)
