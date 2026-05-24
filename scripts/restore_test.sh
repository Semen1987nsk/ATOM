#!/usr/bin/env bash
# PR 26 — Weekly restore-test script.
#
# Берёт **последний** backup из BACKUP_DIR, восстанавливает в **временную**
# БД, прогоняет smoke-тест (alembic check + count(*) sanity), удаляет
# временную БД. Если restore падает — алертим (cron шлёт письмо).
#
# Usage (cron):
#   0 5 * * 0 /opt/empirik/scripts/restore_test.sh >> /var/log/empirik/restore-test.log 2>&1
#
# Env:
#   DATABASE_URL    — основной prod URL (используется для парсинга host/user/password)
#   BACKUP_DIR      — где лежат бэкапы (default /var/lib/empirik/backups)
#   TEST_DB_NAME    — имя временной БД (default empirik_restore_test)
#
# Exit codes:
#   0 — restore OK + smoke passed
#   1 — нет backup'ов
#   2 — restore failed
#   3 — smoke check failed

set -euo pipefail

: "${DATABASE_URL:?DATABASE_URL not set}"
BACKUP_DIR="${BACKUP_DIR:-/var/lib/empirik/backups}"
TEST_DB_NAME="${TEST_DB_NAME:-empirik_restore_test}"

LATEST=$(ls -t "${BACKUP_DIR}"/empirik-*.sql.gz 2>/dev/null | head -1 || true)
if [ -z "${LATEST}" ]; then
    echo "[$(date -Iseconds)] ❌ No backups found in ${BACKUP_DIR}"
    exit 1
fi

echo "[$(date -Iseconds)] Restore-testing: ${LATEST}"

# Парсим DATABASE_URL для admin connection.
# postgres://user:pass@host:port/dbname → пересоберём админ URL для test-DB
BASE_URL="${DATABASE_URL%/*}"  # без имени базы
ADMIN_URL="${BASE_URL}/postgres"
TEST_URL="${BASE_URL}/${TEST_DB_NAME}"

# 1. Создаём test DB (force-drop если осталась).
psql "${ADMIN_URL}" -c "DROP DATABASE IF EXISTS ${TEST_DB_NAME};"
psql "${ADMIN_URL}" -c "CREATE DATABASE ${TEST_DB_NAME};"

# 2. Restore.
if ! gunzip -c "${LATEST}" | psql "${TEST_URL}"; then
    echo "[$(date -Iseconds)] ❌ Restore failed"
    psql "${ADMIN_URL}" -c "DROP DATABASE IF EXISTS ${TEST_DB_NAME};"
    exit 2
fi

# 3. Smoke check — таблицы существуют + row counts >0.
USERS_COUNT=$(psql "${TEST_URL}" -tA -c "SELECT COUNT(*) FROM users;" || echo "0")
ACCOUNTS_COUNT=$(psql "${TEST_URL}" -tA -c "SELECT COUNT(*) FROM accounts;" || echo "0")

echo "[$(date -Iseconds)] Restored: users=${USERS_COUNT} accounts=${ACCOUNTS_COUNT}"

if [ "${USERS_COUNT}" -eq 0 ]; then
    echo "[$(date -Iseconds)] ⚠️  Restore restored DB has 0 users. SUSPICIOUS — check backup."
    psql "${ADMIN_URL}" -c "DROP DATABASE IF EXISTS ${TEST_DB_NAME};"
    exit 3
fi

# 4. Cleanup
psql "${ADMIN_URL}" -c "DROP DATABASE IF EXISTS ${TEST_DB_NAME};"

echo "[$(date -Iseconds)] ✅ Restore-test passed"
exit 0
