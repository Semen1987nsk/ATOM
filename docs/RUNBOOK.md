# Empirik Operations Runbook (PR 26)

Playbook для типичных инцидентов и операций — собран до того, как кто-то
будет ловить 03:00 на проде без полной картины.

> **TL;DR**: что делать когда что-то сломалось. Не для read-once, а
> для копирования команд под звуковой сигнал Sentry.

## Содержание

1. [Deploy / release](#deploy)
2. [Rollback](#rollback)
3. [Database backup / restore](#backup)
4. [Security incident: token leak](#token-leak)
5. [Security incident: account compromise](#account-compromise)
6. [Tinkoff API down](#tinkoff-down)
7. [Sync stuck on user](#sync-stuck)
8. [Payment dispute / refund](#refund)
9. [Disable broker sync globally](#disable-sync)
10. [Disk fill (logs / uploads)](#disk-fill)
11. [Secret management (Yandex Lockbox)](#secret-management)

---

<a id="deploy"></a>
## 1. Deploy / release

```bash
# 1. Pull новый код
ssh prod
cd /opt/empirik
git fetch origin
git log HEAD..origin/main --oneline  # что прилетит

# 2. Backup ДО миграции
/opt/empirik/scripts/backup_db.sh

# 3. Применить миграции (если есть)
cd backend
alembic current  # текущая версия
alembic heads    # доступные
alembic upgrade head

# 4. Обновить код + restart
git pull origin main
systemctl restart empirik-backend
systemctl restart empirik-frontend  # если frontend меняли

# 5. Smoke
curl https://empirik.app/ready  # 200 ожидаем
curl https://empirik.app/health
tail -f /var/log/empirik/api.log  # 1 минута — ошибок быть не должно
```

**Окно деплоя**: пн–чт, 10:00–17:00 MSK. Не деплоить в пятницу.

### Одноразовый шаг после деплоя Sprint 6.5 (MAE-01)

Фикс таймзоны MAE/MFE (naive=UTC вместо МСК) меняет окно расчёта для ВСЕХ
сделок — старые значения посчитаны по сдвинутому на −3ч окну и обязаны быть
пересчитаны один раз после деплоя:

```bash
# для каждого активного аккаунта (или admin-скриптом по всем):
curl -X POST https://empirik.app/trades/calculate-mae-mfe \
  -H "Authorization: Bearer <admin-or-user-token>" \
  -H "Content-Type: application/json" \
  -d '{"force_all": true}'
# либо дождаться nightly mae_mfe_backfill (покрывает только сделки <30 дней!)
```

Прогресс контролировать по coverage-виджету MAE/MFE.

### Ре-стамп после переименования 0023 (S1-02)

Если dev/stage БД застамплена на старый id `0023_position_authoritative_fields`
(alembic upgrade head падает "Can't locate revision"):
```sql
UPDATE alembic_version SET version_num='0023_position_auth_fields'
 WHERE version_num='0023_position_authoritative_fields';
```
Затем `alembic upgrade head`.

---

<a id="rollback"></a>
## 2. Rollback

```bash
# 1. Найти предыдущий commit
cd /opt/empirik && git log --oneline -10

# 2. Revert
git checkout <previous-sha>
systemctl restart empirik-backend empirik-frontend

# 3. Если миграция сломала схему — откат
cd backend
alembic downgrade -1  # или конкретный revision

# 4. Если миграция повредила данные — RESTORE
/opt/empirik/scripts/restore_from_backup.sh /var/lib/empirik/backups/empirik-LAST.sql.gz
```

---

<a id="backup"></a>
## 3. Database backup / restore

### Manual backup
```bash
/opt/empirik/scripts/backup_db.sh
ls -la /var/lib/empirik/backups/ | tail -5
```

### Manual restore (full)
```bash
# 1. Stop API
systemctl stop empirik-backend

# 2. Create fresh DB (или DROP existing — ОПАСНО!)
psql "${ADMIN_URL}" -c "DROP DATABASE IF EXISTS empirik_prod;"
psql "${ADMIN_URL}" -c "CREATE DATABASE empirik_prod;"

# 3. Restore
gunzip -c /var/lib/empirik/backups/empirik-YYYYMMDD-HHMMSS.sql.gz | psql "${DATABASE_URL}"

# 4. Verify
DATABASE_URL=... python -m tools.verify_user --all-users --no-live

# 5. Start API
systemctl start empirik-backend
```

### Verify backup health (weekly)
Автоматически через cron: `/opt/empirik/scripts/restore_test.sh` (sun 05:00).
Email-алерт если падает.

### Point-in-Time Recovery (PITR) — INFRA-09 Sprint 6

**Setup на проде:**

1. Создать S3-bucket `empirik-backups` в Yandex Object Storage (RU-локация для 152-ФЗ).
2. Сгенерировать libsodium key:
   ```bash
   openssl rand -base64 32 > /opt/empirik/walg.key
   chmod 600 /opt/empirik/walg.key
   ```
3. Добавить в `.env` (или Lockbox):
   ```
   WALG_S3_PREFIX=s3://empirik-backups/walg
   WALG_LIBSODIUM_KEY=<base64 from walg.key>
   AWS_REGION=ru-central1
   AWS_ENDPOINT=https://storage.yandexcloud.net
   ```
4. Установить wal-g в postgres-контейнер (custom Dockerfile или через volume mount бинаря). Текущий `postgres:16-alpine` НЕ содержит wal-g — нужен custom image `empirik-postgres-walg`.
5. Перезапустить postgres с `postgresql.prod.conf` (включает `archive_command = 'wal-g wal-push %p'`).

**Daily base-backup (cron на хосте):**

```cron
0 3 * * * docker exec postgres bash -c '. /etc/postgresql/walg.env && wal-g backup-push /var/lib/postgresql/data'
```

**Восстановление до точки T:**

1. Остановить backend (compose stop backend).
2. Создать новый postgres-instance:
   ```bash
   docker compose -f docker-compose.prod.yml stop postgres
   docker volume rm empirik_postgres_data
   docker compose -f docker-compose.prod.yml up -d postgres
   ```
3. Восстановить из last base-backup:
   ```bash
   docker exec postgres wal-g backup-fetch /var/lib/postgresql/data LATEST
   ```
4. Configure PITR target:
   ```bash
   docker exec postgres bash -c "cat >> /var/lib/postgresql/data/postgresql.auto.conf <<EOF
   restore_command = 'wal-g wal-fetch %f %p'
   recovery_target_time = '2026-05-27T12:00:00+03:00'
   recovery_target_action = 'promote'
   EOF"
   docker exec postgres touch /var/lib/postgresql/data/recovery.signal
   ```
5. Restart postgres:
   ```bash
   docker compose -f docker-compose.prod.yml restart postgres
   ```
6. Verify: `psql -c "SELECT pg_is_in_recovery();"` → false (after replay).
7. Resume backend:
   ```bash
   docker compose -f docker-compose.prod.yml up -d backend
   ```

**Restore-тест:** `scripts/restore_test.sh` запускается еженедельно (Sun 05:00) и проверяет PITR-flow на staging.

---

## 3a. Connection pool vs postgres max_connections (S2-02)

**Инвариант:**

```
replicas × workers × (DB_POOL_SIZE + DB_MAX_OVERFLOW) < max_connections
```

**Текущая топология:** `replicas(2) × workers(4) = 8` процессов backend.
Каждый процесс держит собственный SQLAlchemy-пул `DB_POOL_SIZE + DB_MAX_OVERFLOW`
соединений под пиком. Если сумма ≥ `max_connections`, postgres отвечает
`FATAL: sorry, too many clients already` — падают и запросы, и healthcheck
`/ready` (SELECT 1).

**Защита (defense-in-depth, два независимых слоя):**

1. `docker-compose.prod.yml` — `command: postgres -c max_connections=200`
   (postgres:16-alpine иначе стартует с default `max_connections=100`).
2. `.env.production.example` — `DB_POOL_SIZE=5`, `DB_MAX_OVERFLOW=5` →
   `8 × (5 + 5) = 80 < 100`; запас держится даже без слоя (1).

**При изменении replicas / --workers / пула — пересчитать неравенство.**
Долгосрочно (при росте числа процессов) — вынести пул в pgbouncer
(transaction pooling), тогда backend-процессы делят общий набор бэкенд-соединений.

---

<a id="token-leak"></a>
## 4. Security incident: token leak

Если есть подозрение что Tinkoff token (`BROKER_TOKEN_KEY_V2`) утёк:

```bash
# 1. Сгенерировать новый ключ
NEW_KEY=$(python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
echo "BROKER_TOKEN_KEY_V3=$NEW_KEY" >> /opt/empirik/.env

# 2. Двигаем активную версию в crypto_utils.py:
#    _ACTIVE_VERSION = "v3"
# (или сделать через env var в будущем)

# 3. Restart
systemctl restart empirik-backend

# 4. Background migration: перешифровать все BrokerConnection.api_token
DATABASE_URL=... python -c "
import database, models
from crypto_utils import decrypt_token, encrypt_token
s = database.SessionLocal()
for c in s.query(models.BrokerConnection).all():
    try:
        plain = decrypt_token(c.api_token)  # старым v1/v2 ключом
        c.api_token = encrypt_token(plain)  # новым v3
    except Exception as e:
        print(f'SKIP conn {c.id}: {e}')
s.commit()
"

# 5. После того как всё перешифровано — убрать BROKER_TOKEN_KEY_V2 из env.
```

При утечке JWT secret (`SECRET_KEY`):
```bash
# Сменить SECRET_KEY → автоматически все access tokens становятся invalid
# Юзеры перевойдут заново
```

---

<a id="account-compromise"></a>
## 5. Account compromise

Если юзер сообщил что аккаунт взломан:

```bash
# 1. Сразу инвалидируем все его сессии — revoke по user_id
DATABASE_URL=... python -c "
import database, models
from datetime import datetime, timedelta
s = database.SessionLocal()
u = s.query(models.User).filter(models.User.email=='X@Y.Z').first()
# Все его JWT (можно записать в revoked_tokens, но мы не знаем jti старых)
# → проще сменить SECRET_KEY (затронет всех) ИЛИ деактивировать user
u.is_active = 0
s.commit()
"

# 2. Force password reset (insert PasswordResetTokenORM) ИЛИ юзер сам делает.

# 3. Проверить activity:
DATABASE_URL=... python -m tools.verify_user --user-id <ID>

# 4. Audit log: что делал?
psql "${DATABASE_URL}" -c "
SELECT actor_user_id, action, target_user_id, ip_address, created_at
FROM admin_audit_log
WHERE target_user_id = <ID> OR actor_user_id = <ID>
ORDER BY created_at DESC LIMIT 50;
"
```

---

<a id="tinkoff-down"></a>
## 6. Tinkoff API down

Если broker.tinkoff недоступен (массовые 5xx в логах):

```bash
# 1. Проверить статус Tinkoff
curl https://invest-public-api.tinkoff.ru/rest/tinkoff.public.invest.api.contract.v1.UsersService/GetInfo

# 2. Глобально отключить sync чтобы не накапливать failures
# Можно через флаг или просто остановив scheduler:
systemctl stop empirik-sync-scheduler

# 3. UI banner на dashboard через feature flag (Phase 2):
DATABASE_URL=... python -c "
# выставить global flag 'tinkoff_outage' = true
# Frontend читает и показывает 'Тинькоф API временно недоступен'
"

# 4. Когда восстановится — start обратно
systemctl start empirik-sync-scheduler
```

---

<a id="sync-stuck"></a>
## 7. Sync stuck on user

Юзер пишет «синхронизация висит с утра»:

```bash
# 1. Diagnose
DATABASE_URL=... python -m tools.diagnose_account --account-id <ID>

# 2. Если circuit_open_until в будущем — ручной reset:
psql "${DATABASE_URL}" -c "
UPDATE broker_connections
SET circuit_open_until=NULL, consecutive_failures=0
WHERE account_id = <ID>;
"

# 3. Force resync через admin endpoint:
curl -X POST http://localhost:8000/admin/users/<UID>/force-resync \
  -H "Authorization: Bearer <ADMIN_JWT>"

# 4. Если sync_cursor сломан — full reset:
curl -X POST "http://localhost:8000/admin/users/<UID>/reset-broker?account_id=<AID>&confirm=<AID>" \
  -H "Authorization: Bearer <ADMIN_JWT>"
```

---

<a id="refund"></a>
## 8. Payment dispute / refund

```bash
# 1. Найти платёж в admin panel или:
psql "${DATABASE_URL}" -c "
SELECT * FROM payment_attempts WHERE user_id = <UID> ORDER BY created_at DESC;
"

# 2. В YooKassa личном кабинете — refund (manual).

# 3. YooKassa пришлёт webhook → автоматически deactivate Subscription
# (см. payments.py:_deactivate_subscription).

# 4. Если webhook не пришёл — manual deactivate:
psql "${DATABASE_URL}" -c "
UPDATE subscriptions SET is_active=0 WHERE user_id = <UID>;
"
```

---

<a id="disable-sync"></a>
## 9. Disable broker sync globally

В случае массового инцидента (Tinkoff API broken responses → corrupted data):

```bash
# В env:
BROKER_SYNC_V2_ENABLED=false

systemctl restart empirik-backend
# Все /broker/sync endpoints возвращают 503
# Scheduler становится no-op
```

---

<a id="disk-fill"></a>
## 10. Disk fill (logs / uploads)

```bash
# 1. Что съело
df -h
du -sh /var/log/empirik/* /opt/empirik/uploads/* | sort -h

# 2. Truncate старые логи (logrotate сделать это автоматически)
truncate -s 0 /var/log/empirik/api.log

# 3. Старые screenshots без trade
DATABASE_URL=... python -c "
import database, models, os
s = database.SessionLocal()
referenced = set(t.screenshot_url for t in s.query(models.Trade).filter(models.Trade.screenshot_url.isnot(None)))
referenced = {os.path.basename(u) for u in referenced}
files = os.listdir('/opt/empirik/uploads/screenshots')
orphans = [f for f in files if f not in referenced]
for f in orphans:
    os.remove(f'/opt/empirik/uploads/screenshots/{f}')
print(f'removed {len(orphans)} orphan screenshots')
"
```

## Часто используемые admin commands

## Email verification (PR 26 Phase 3)

После регистрации юзеру шлётся письмо с magic-link. Token валиден 24 часа.

```bash
# Если SMTP не настроен → письма не идут, юзер не может подтвердить.
# Workaround: проставить email_verified=true вручную для критичных юзеров:
psql "${DATABASE_URL}" -c "
UPDATE users SET email_verified=true, email_verification_token=NULL
WHERE id=<UID>;
"

# Перевыпустить ссылку (если юзер сам потерял письмо):
curl -X POST https://empirik.app/auth/resend-verification \
  -H "Cookie: access_token=<JWT>"
```

## Backup tracking (PR 26 Phase 3)

`backup_runs` таблица заполняется автоматически из `scripts/backup_db.sh`
и `scripts/restore_test.sh`. Admin UI `/admin/infra` показывает last
backup + last restore-test.

```bash
# Manual write если cron не работает:
psql "${DATABASE_URL}" -c "
INSERT INTO backup_runs (started_at, finished_at, status, kind, filename, size_bytes)
VALUES (now(), now(), 'success', 'nightly_backup', 'manual-2026-05-14.sql.gz', 12345678);
"
```

## Deploy window (PR 26 Phase 3)

```bash
# Перед каждым deploy:
bash scripts/deploy_window_check.sh
# Возвращает exit 1 если пятница после 14:00 / выходные / ночь
# Override (use sparingly): DEPLOY_FORCE=1 bash scripts/deploy_window_check.sh
```

## 2FA для admin (PR 26 Phase 2)

```bash
# Включить:
# 1. Установить pyotp
pip install pyotp

# 2. Через UI:
#    /settings → "Включить 2FA" → отсканировать QR в Google Authenticator
#    → ввести 6-digit код → подтверждение

# Через API (для админа):
curl -X POST https://empirik.app/auth/2fa/enable -H "Cookie: access_token=..."
# Получаем secret + provisioning_uri
# Добавляем в authenticator app
curl -X POST https://empirik.app/auth/2fa/verify -d '{"code":"123456"}'

# Сбросить если потерял access к authenticator:
psql "${DATABASE_URL}" -c "
UPDATE users SET totp_enabled=0, totp_secret=NULL WHERE id=<UID>;
"
```

## SLA pledge (укажите в TOS / Privacy)

```
- Response time: 24 часа на запросы через support@empirik.app
- Uptime target: 99% по SLO (см. /status)
- Backup retention: 7 дней (см. RUNBOOK)
- Data deletion: 30 дней grace period (152-ФЗ ст. 21)
- Security incident notification: 72 часа с момента обнаружения
```

## Часто используемые admin commands

```bash
# Список юзеров с проблемами
DATABASE_URL=... python -m tools.verify_user --all-users --no-live --json /tmp/v.json
jq '.reports[] | select(.summary.error>0)' /tmp/v.json

# Активные подписки
psql "${DATABASE_URL}" -c "
SELECT COUNT(*) plan, plan FROM subscriptions WHERE is_active=1 GROUP BY plan;
"

# Top errors за день
grep ERROR /var/log/empirik/api.log | tail -50 | sort | uniq -c | sort -rn | head

# DB size
psql "${DATABASE_URL}" -c "SELECT pg_size_pretty(pg_database_size(current_database()));"
```

---

<a id="au10-rollback"></a>
## 11. AU10 SDK rollback (t-tech-investments → tinkoff-investments)

Если после AU10 SDK migration broker sync ломается у юзеров — быстрый откат
за 5 минут:

```bash
ssh prod
cd /opt/empirik

# 1. Откат кода
git log --oneline -10 | grep -i "AU10\|t_tech\|t-tech"  # найти commit AU10
git revert <au10-commit-sha> --no-edit
git push origin main

# 2. Pin старый SDK обратно (если pip lockfile)
cd backend
# В requirements.txt вернуть строку:
#   tinkoff-investments @ git+https://github.com/RussianInvestments/invest-python.git@0.2.0-beta117
sed -i 's|^t-tech-investments==.*|tinkoff-investments @ git+https://github.com/RussianInvestments/invest-python.git@0.2.0-beta117|' requirements.txt

# 3. Pin grpcio обратно (старый SDK работал с 1.6x, новый требует 1.75+)
# protobuf тоже понизить если cascade-блокатор:
pip install 'grpcio>=1.59.3,<1.70' 'protobuf>=5.27,<6' --force-reinstall

# 4. Перезапуск
systemctl restart empirik-api
journalctl -fu empirik-api | head -20  # проверить старт
```

Время до восстановления: ~5 мин.

---

<a id="au10-tls-setup"></a>
## 12. AU10 TLS setup (Russian Trusted CA для grpcio 1.80+)

**Problem**: после AU10 (grpcio 1.6x → 1.80) TLS handshake к
`invest-public-api.tbank.ru:443` падает с
`CERTIFICATE_VERIFY_FAILED: self signed certificate in certificate chain`.

**Root cause**: T-Bank после санкций перешёл на Russian Trusted Root CA
(Минцифры). Старый grpcio имел legacy bundle с этой CA; новый — нет.
grpcio (BoringSSL stack) НЕ использует Windows trust store и НЕ читает
certifi автоматически — нужен явный `GRPC_DEFAULT_SSL_ROOTS_FILE_PATH`.

**Setup на новой prod-машине** (один раз):

```bash
# 1. Сгенерировать combined PEM (certifi + Russian Trusted Root + Sub).
#    Скрипт скачивает CA с gu-st.ru (Минцифры). На Linux — bash, на
#    Windows — PowerShell:
#    pwsh scripts/build_grpc_ca_bundle.ps1
#    → backend/.local/combined_ca_bundle.pem (~290 KB, ~70 root CAs + 2 RU)

# Linux вариант:
mkdir -p /opt/empirik/backend/.local
cat $(python -c "import certifi; print(certifi.where())") > /opt/empirik/backend/.local/combined_ca_bundle.pem
curl -s https://gu-st.ru/content/Other/doc/russian_trusted_root_ca.cer | openssl x509 -inform DER -outform PEM >> /opt/empirik/backend/.local/combined_ca_bundle.pem
curl -s https://gu-st.ru/content/Other/doc/russian_trusted_sub_ca.cer | openssl x509 -inform DER -outform PEM >> /opt/empirik/backend/.local/combined_ca_bundle.pem

# 2. Установить env-var в systemd unit / docker-compose / pm2:
# Например, /etc/systemd/system/empirik-api.service:
#   Environment="TINKOFF_GRPC_CA_BUNDLE=/opt/empirik/backend/.local/combined_ca_bundle.pem"
#
# config.py:35-43 транслирует эту переменную в GRPC_DEFAULT_SSL_ROOTS_FILE_PATH
# ДО первого импорта grpcio.

# 3. Verify (после рестарта backend):
INVEST_TOKEN=<sandbox> python -c "
import os
os.environ['GRPC_DEFAULT_SSL_ROOTS_FILE_PATH'] = '/opt/empirik/backend/.local/combined_ca_bundle.pem'
import asyncio
from t_tech.invest import AsyncClient
async def m():
    async with AsyncClient('${INVEST_TOKEN}', target='sandbox-invest-public-api.tbank.ru:443') as c:
        print(await c.users.get_accounts())
asyncio.run(m())
"
# Если выводит accounts list → TLS работает.
# Если падает CERTIFICATE_VERIFY_FAILED → bundle не подцепился, проверь env-var.
```

**Тревожный сигнал**: в Sentry массовые `BrokerUnavailable: TLS handshake failed`.

---

<a id="t1-futures-specs"></a>
## 13. T1: Futures без min_price_increment_amount

**Problem**: Tinkoff API возвращает `min_price_increment_amount=0` для
большинства futures (особенно для российских tickers). Без корректного
значения `FuturesPnLCalculator` использует fallback `point_value=1.0`,
что даёт **×100 занижение P&L** для контрактов типа BR (Brent), GD (Gold),
ET (Ethereum), XI (Xiaomi).

**Симптом**: юзер видит подозрительно маленькие P&L по фьючерсам.
Transformation audit показывает `[T1]` warning.

**Fix** (после AU10):

```bash
# 1. Audit — посмотреть scope
python -X utf8 -m tools.refresh_missing_instrument_specs --account-id <ID> --dry-run

# 2. Refresh: Tinkoff API + MOEX ISS fallback + KNOWN_FUTURES_SPECS таблица
python -X utf8 -m tools.refresh_missing_instrument_specs --account-id <ID>

# 3. Force-resync чтобы пересчитать Trade.net_pnl с новыми specs:
python -X utf8 -m tools.reset_broker_account --account-id <ID> --yes
# Дальше через UI или прямой trigger:
curl -X POST http://127.0.0.1:8000/broker/trigger-sync/<connection_id>
```

Throttle: tool делает 1.5s между RPC — 37 instruments ~55 секунд. T-Bank
backend банит IP при burst ≥30 RPC за секунду.

Если в `KNOWN_FUTURES_SPECS` нет какого-то base_code — лог WARNING.
Добавить в `backend/moex_service.py:KNOWN_FUTURES_SPECS` запись формата:

```python
"XY": {"minstep": Decimal(1), "stepprice": Decimal(1), "point_value": Decimal(1)},
```

(Для российских акционных фьючерсов point_value=1 — 1 пип = 1 RUB.)

---

<a id="secret-management"></a>
## 11. Secret management (Yandex Lockbox)

Production secrets хранятся в Yandex Lockbox. На сервере `/opt/empirik/.env`
никогда не редактируется руками — он перегенерируется из Lockbox через
`scripts/load_secrets.sh` (см. INFRA-07).

### Bootstrap (первый запуск или после rebuild VM)

```bash
# 1. Установить yc CLI + аутентифицироваться:
curl https://storage.yandexcloud.net/yandexcloud-yc/install.sh | bash
yc init  # OAuth-token + cloud + folder

# 2. Поставить jq (нужен скрипту для парсинга payload).
apt-get install -y jq

# 3. Узнать ID секрета в console.yandex.cloud → Lockbox → empirik-prod
export LOCKBOX_SECRET_ID=e6q12345abcdef...

# 4. Выгрузить secrets в /opt/empirik/.env (атомарно, mode 600).
/opt/empirik/scripts/load_secrets.sh

# 5. Поднять стек:
cd /opt/empirik
export SHA=$(git rev-parse HEAD)
docker compose -f docker-compose.prod.yml pull
docker compose -f docker-compose.prod.yml up -d
```

### Required keys (минимум для старта backend в prod)

| Ключ | Назначение |
|---|---|
| `SECRET_KEY` | JWT access-token signing (HS256). |
| `REFRESH_SECRET_KEY` | JWT refresh-token signing (separate secret). |
| `MASTER_KEY_B64` | AES-256-GCM ключ (base64) для шифровки T-Bank токенов. |
| `DATABASE_URL` | `postgresql://user:pass@postgres:5432/empirik` |
| `REDIS_URL` | `redis://:pass@redis:6379/0` |
| `POSTGRES_PASSWORD` | используется compose-файлом для init postgres-сервиса. |
| `REDIS_PASSWORD` | requirepass для redis-сервиса. |

Если кого-то нет — `load_secrets.sh` выведет WARNING и backend упадёт при
старте (FastAPI fail-fast на отсутствии конфига).

### Optional keys (фичи активируются если ENV выставлен)

| Ключ | Что включает |
|---|---|
| `SENTRY_DSN` | Backend Sentry — ошибки + perf. |
| `NEXT_PUBLIC_SENTRY_DSN` | Frontend Sentry (NEXT_PUBLIC = bundled в клиент). |
| `SENTRY_AUTH_TOKEN`, `SENTRY_ORG` | source-map upload в CD-пайплайне. |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD` | email notifications. |
| `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET` | Google sign-in. |
| `YANDEX_OAUTH_CLIENT_ID`, `YANDEX_OAUTH_CLIENT_SECRET` | Yandex sign-in. |
| `BACKUP_S3_BUCKET`, `WALG_S3_PREFIX`, `WALG_LIBSODIUM_KEY` | PITR-backup через WAL-G. |
| `BROKER_TOKEN_KEY_V2`, `BROKER_TOKEN_KEY_V3` | legacy + active версии ключа T-Bank токенов (см. §4 token leak). |

### Ротация секрета (любая причина — leak, scheduled, новый сервис)

```bash
# 1. В console.yandex.cloud → Lockbox → empirik-prod → Edit → новый entry
#    или поменять text_value у существующего. ID секрета остаётся прежним;
#    Lockbox создаёт новую версию payload автоматически (старые versions —
#    rollback-fallback на 1 год).

# 2. На прод-сервере перегенерировать .env:
ssh prod
sudo -u empirik /opt/empirik/scripts/load_secrets.sh

# 3. Restart затронутых сервисов (graceful, replicas: 2 → 0 downtime):
cd /opt/empirik
docker compose -f docker-compose.prod.yml restart backend frontend

# 4. Smoke:
curl -fsSL https://empirik.app/ready
```

### Что НЕ кладётся в Lockbox

- `GITHUB_REPOSITORY_OWNER` — публичен, в compose env.
- `SHA` — git commit hash, ставится через export перед deploy.
- `LOG_LEVEL`, `FORWARDED_ALLOW_IPS` — не secrets, в compose или env_file
  можно положить literal, но не в Lockbox (audit-noise).

### Disaster recovery

Если Lockbox сам недоступен (Yandex Cloud outage) — у каждого on-call инженера
должен быть offline-копия .env в bitwarden-сейфе организации
(plaintext, encrypted at-rest браузерным расширением). Только для break-glass
сценария — обычная работа через Lockbox.
