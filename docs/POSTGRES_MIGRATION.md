# PostgreSQL Migration Guide (PR 26)

Гайд по миграции Empirik с SQLite (dev) на PostgreSQL (prod). Для self-hosted
deployment на Yandex Cloud / Selectel / любой RU-region провайдер.

## Цель

До открытия публичной регистрации перейти на Postgres, чтобы:

1. Исчез риск SQLite `database is locked` под concurrent sync (P0 #87)
2. Backup через `pg_dump` стандартизирован (P0 #88)
3. Connection pooling сразу из коробки

## Pre-requisites

- PostgreSQL 14+ на RU-region cloud (Yandex Managed Postgres / Selectel)
- Доступ через `psql` с админ-правами для CREATE DATABASE
- Python пакеты: `psycopg2-binary` (или `psycopg[binary]` для psycopg3)

```bash
pip install psycopg2-binary
```

## Шаги миграции

### 1. Создать БД и user в Postgres

```sql
-- Подключитесь как admin
CREATE DATABASE empirik_prod ENCODING 'UTF8' LC_COLLATE 'C' LC_CTYPE 'C' TEMPLATE template0;
CREATE USER empirik_app WITH PASSWORD 'STRONG_PASSWORD_HERE';
GRANT ALL PRIVILEGES ON DATABASE empirik_prod TO empirik_app;
\c empirik_prod
GRANT ALL ON SCHEMA public TO empirik_app;
```

### 2. Установить env в production

```bash
DATABASE_URL=postgresql://empirik_app:STRONG_PASSWORD_HERE@your-host.ru:5432/empirik_prod
DB_POOL_SIZE=10
DB_MAX_OVERFLOW=20
DB_POOL_TIMEOUT=30
DB_POOL_RECYCLE=1800

# КРИТИЧНО для prod:
AUTO_INIT_DB=false  # Используем Alembic, не create_all()
DEBUG=false
SECRET_KEY=<generate via: python -c "import secrets; print(secrets.token_urlsafe(64))">
REFRESH_SECRET_KEY=<another one, DIFFERENT from SECRET_KEY>
BROKER_TOKEN_KEY_V2=<via: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())">
```

### 3. Прогнать Alembic миграции

```bash
cd backend
DATABASE_URL=postgresql://... alembic upgrade head
```

Ожидаемый результат: все 13 миграций (0001 → 0013) применяются без ошибок.

### 4. (Опционально) Перенести данные из dev SQLite

Для копирования начального набора (если уже были dev-юзеры):

```bash
# Дамп SQLite в CSV
python -c "
import sqlite3, csv
conn = sqlite3.connect('backend/database.db')
for table in ['users', 'accounts', 'subscriptions']:
    cur = conn.execute(f'SELECT * FROM {table}')
    cols = [d[0] for d in cur.description]
    with open(f'/tmp/{table}.csv', 'w') as f:
        w = csv.writer(f)
        w.writerow(cols)
        w.writerows(cur)
print('dumped to /tmp/')
"

# Загрузить в Postgres через \copy
psql $DATABASE_URL -c "\copy users FROM '/tmp/users.csv' CSV HEADER"
# и т.д.
```

**ВНИМАНИЕ**: trades, operations, positions — НЕ переносить, а перессинхронизироваться
через `python -m tools.live_pipeline_smoke --account-id N` (это даст чистый
state без legacy currency-mismatch и т.д.).

### 5. Verify

```bash
# 1. Migration check
DATABASE_URL=postgresql://... python -c "
from alembic.config import Config
from alembic.script import ScriptDirectory
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine
import os
cfg = Config('alembic.ini')
script = ScriptDirectory.from_config(cfg)
engine = create_engine(os.environ['DATABASE_URL'])
with engine.connect() as conn:
    ctx = MigrationContext.configure(conn)
    print('current:', ctx.get_current_revision())
print('head:', script.get_current_head())
"
# current и head должны совпадать

# 2. API startup
DATABASE_URL=postgresql://... DEBUG=false uvicorn main:app
# Должно увидеть в логах: "✅ Alembic head check passed"

# 3. Smoke test через API
curl http://localhost:8000/ready  # Должен вернуть 200

# 4. verify_user CLI на тестовом юзере
DATABASE_URL=postgresql://... python -m tools.verify_user --user-id 1 --no-live
```

## Known Postgres-specific quirks

### Boolean vs Integer (User.is_active, User.is_admin)

В SQLite SQLAlchemy хранит Integer (0/1). В Postgres — BOOLEAN.
Существующий код использует `== 1` сравнения — они **работают в обоих
диалектах** (Postgres coerce'ит true → 1 в context'е). НО:

- Не пишите `WHERE is_active = 1` в raw SQL — пишите `WHERE is_active IS TRUE`.
- В моделях используйте `Boolean` тип, не `Integer`.

### JSON columns (issues_json, details)

SQLite хранит TEXT. Postgres хранит JSON или JSONB. SQLAlchemy `JSON()`
auto-translate — оба работают. Но `JSONB` индексируется лучше:

```python
# Если хотим быстрый поиск по details:
from sqlalchemy.dialects.postgresql import JSONB
details = Column(JSONB, nullable=True)
```

В Phase 1 если admin-audit-log станет тяжёлым (>1М строк) — переключить
`AdminAuditLogORM.details` на JSONB.

### Decimal precision

Postgres `NUMERIC(18,8)` строже SQLite. Все наши financial columns уже
`Numeric(precision=18, scale=8)` — overflow на ±10¹⁰ ₽ маловероятен,
но проверьте чем тестировать.

### UPSERT (ON CONFLICT)

В `operation_repo.upsert` используется SQLAlchemy `merge()` — диалект-
агностично. Если потребуется raw ON CONFLICT, есть `sqlalchemy.dialects.postgresql.insert(...).on_conflict_do_update(...)`.

## Откат (rollback)

Если что-то идёт не так:

```bash
# 1. Восстановить SQLite (если ещё есть)
cp backend/database.db.backup backend/database.db
DATABASE_URL=sqlite:///./backend/database.db ...

# 2. ИЛИ rollback Alembic в Postgres
alembic downgrade -1
```

## Backup strategy (Phase 0.17)

Cron daily `pg_dump` + weekly restore-test (см. RUNBOOK.md).
