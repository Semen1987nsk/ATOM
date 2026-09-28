#!/usr/bin/env bash
# PR 26 (Phase 1.6) — nightly verify_user runner для cron.
#
# Запускает verify_user --all-users, пишет JSON в лог-файл, отправляет
# Slack alert если есть errors. Idempotent — можно запускать сколько угодно.
#
# Setup:
#   crontab -e
#   0 4 * * * /opt/empirik/scripts/verify_users_cron.sh
#
# Env:
#   EMPIRIK_HOME           — root (default /opt/empirik)
#   VERIFY_LOG_DIR      — куда писать JSON отчёты (default /var/log/empirik/verify)
#   VERIFY_SLACK_WEBHOOK — Slack incoming webhook URL для алертов (optional)
#   VERIFY_RETAIN_DAYS  — сколько дней хранить (default 30)

set -euo pipefail

EMPIRIK_HOME="${EMPIRIK_HOME:-/opt/empirik}"
VERIFY_LOG_DIR="${VERIFY_LOG_DIR:-/var/log/empirik/verify}"
RETAIN_DAYS="${VERIFY_RETAIN_DAYS:-30}"

mkdir -p "${VERIFY_LOG_DIR}"

TIMESTAMP=$(date -u +"%Y%m%d-%H%M%S")
JSON_FILE="${VERIFY_LOG_DIR}/verify-${TIMESTAMP}.json"
SUMMARY_FILE="${VERIFY_LOG_DIR}/verify-${TIMESTAMP}.summary.txt"

echo "[$(date -Iseconds)] Starting verify_user --all-users"

cd "${EMPIRIK_HOME}/backend"

# --no-live можно подменить env'ом для скоростного DB-only режима
VERIFY_FLAGS="${VERIFY_FLAGS:---no-live}"

# Запускаем; exit code 0=ok, 1=warn, 2=err
set +e
python -X utf8 -m tools.verify_user --all-users ${VERIFY_FLAGS} --json "${JSON_FILE}" > "${SUMMARY_FILE}" 2>&1
EXIT_CODE=$?
set -e

cat "${SUMMARY_FILE}"

# Cleanup старые отчёты
find "${VERIFY_LOG_DIR}" -name "verify-*.json" -mtime "+${RETAIN_DAYS}" -delete || true
find "${VERIFY_LOG_DIR}" -name "verify-*.summary.txt" -mtime "+${RETAIN_DAYS}" -delete || true

# Slack alert на errors
if [ ${EXIT_CODE} -eq 2 ] && [ -n "${VERIFY_SLACK_WEBHOOK:-}" ]; then
    # Извлекаем total errors из JSON
    ERR_COUNT=$(python -c "import json; print(json.load(open('${JSON_FILE}'))['total']['error'])" 2>/dev/null || echo "?")
    SUMMARY=$(tail -20 "${SUMMARY_FILE}" | tr '\n' ' ' | head -c 500)
    PAYLOAD=$(cat <<EOF
{
  "text": "🚨 Empirik verify_user: ${ERR_COUNT} errors detected",
  "attachments": [{
    "color": "danger",
    "title": "Nightly verification failed",
    "text": "${SUMMARY}",
    "footer": "verify-${TIMESTAMP}.json on host \$(hostname)"
  }]
}
EOF
)
    curl -s -X POST -H "Content-Type: application/json" \
        --data "${PAYLOAD}" "${VERIFY_SLACK_WEBHOOK}" || true
fi

exit ${EXIT_CODE}
