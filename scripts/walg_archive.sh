#!/usr/bin/env bash
# scripts/walg_archive.sh — WAL-G base-backup + WAL push wrapper.
# Запускается из cron или systemd-таймера на хосте.
# INFRA-09 (Sprint 6, Batch 6): PITR через WAL-G на S3.
#
# Env required:
#   WALG_S3_PREFIX=s3://empirik-backups/walg
#   AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_REGION
#   WALG_LIBSODIUM_KEY=<base64> (для encryption-at-rest)
#   PGHOST, PGUSER, PGPASSWORD, PGDATABASE
set -euo pipefail

: "${WALG_S3_PREFIX:?WALG_S3_PREFIX env required}"

CMD="${1:-base-backup}"

case "$CMD" in
    base-backup)
        echo "Running WAL-G base backup..."
        wal-g backup-push /var/lib/postgresql/data
        echo "Base backup OK. Retention policy:"
        # Keep last 7 base backups + their WALs
        wal-g delete retain FULL 7 --confirm
        ;;
    list)
        wal-g backup-list
        ;;
    *)
        echo "Usage: $0 {base-backup|list}"
        exit 1
        ;;
esac
