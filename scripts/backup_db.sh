#!/usr/bin/env bash
# PR 26 — Nightly PostgreSQL backup script.
#
# Usage (cron):
#   0 3 * * * /opt/empirik/scripts/backup_db.sh >> /var/log/empirik/backup.log 2>&1
#
# Expected env vars:
#   DATABASE_URL      — postgres://user:pass@host:5432/empirik_prod
#   BACKUP_DIR        — target directory (default /var/lib/empirik/backups)
#   BACKUP_S3_BUCKET  — RU S3 bucket name (Yandex Object Storage / Selectel) — optional
#   BACKUP_RETENTION_DAYS — keep N days locally (default 7)
#
# Output:
#   - <BACKUP_DIR>/empirik-YYYYMMDD-HHMMSS.sql.gz
#   - (если BACKUP_S3_BUCKET задан) s3://<bucket>/empirik-YYYYMMDD-HHMMSS.sql.gz
#   - Запись в `backup_runs` таблицу (если SQL клиент доступен)
#
# Exit codes:
#   0 — success
#   1 — pg_dump failed
#   2 — upload failed
#   3 — env not configured

set -euo pipefail

: "${DATABASE_URL:?DATABASE_URL not set}"
BACKUP_DIR="${BACKUP_DIR:-/var/lib/empirik/backups}"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-7}"

mkdir -p "${BACKUP_DIR}"

TIMESTAMP=$(date -u +"%Y%m%d-%H%M%S")
FILENAME="empirik-${TIMESTAMP}.sql.gz"
FILEPATH="${BACKUP_DIR}/${FILENAME}"

echo "[$(date -Iseconds)] Starting backup → ${FILEPATH}"

# pg_dump → gzip pipeline; --no-owner --no-acl чтобы restore работал в чужой DB.
if ! pg_dump --no-owner --no-acl "${DATABASE_URL}" | gzip -9 > "${FILEPATH}"; then
    echo "[$(date -Iseconds)] ❌ pg_dump failed"
    rm -f "${FILEPATH}"
    exit 1
fi

SIZE=$(stat -c%s "${FILEPATH}" 2>/dev/null || stat -f%z "${FILEPATH}")
echo "[$(date -Iseconds)] ✅ dump complete: ${SIZE} bytes"

# S3 upload (optional)
if [ -n "${BACKUP_S3_BUCKET:-}" ]; then
    echo "[$(date -Iseconds)] Uploading to s3://${BACKUP_S3_BUCKET}/${FILENAME}"
    if ! aws s3 cp "${FILEPATH}" "s3://${BACKUP_S3_BUCKET}/${FILENAME}"; then
        echo "[$(date -Iseconds)] ❌ S3 upload failed"
        exit 2
    fi
    echo "[$(date -Iseconds)] ✅ uploaded"
fi

# Cleanup: удаляем старые дампы (>RETENTION_DAYS дней)
find "${BACKUP_DIR}" -name "empirik-*.sql.gz" -mtime "+${RETENTION_DAYS}" -delete

# PR 26 Phase 3: запись в backup_runs (best-effort, не fatal)
S3_FLAG=$([ -n "${BACKUP_S3_BUCKET:-}" ] && echo "true" || echo "false")
psql "${DATABASE_URL}" -c "
INSERT INTO backup_runs (started_at, finished_at, status, kind, filename, size_bytes, s3_uploaded)
VALUES (now(), now(), 'success', 'nightly_backup', '${FILENAME}', ${SIZE}, ${S3_FLAG});
" 2>/dev/null || true

echo "[$(date -Iseconds)] Backup done: ${FILENAME} (${SIZE} bytes)"
exit 0
