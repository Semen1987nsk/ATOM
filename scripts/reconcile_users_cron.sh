#!/usr/bin/env bash
# PR 26 (Phase 3, D8) — Nightly reconciliation cron.
#
# Запускает 3-way reconciliation для всех active юзеров за последние 30 дней.
# Отдельный от verify_users_cron.sh — verify это consistency check,
# reconciliation это correctness check (P&L vs broker report).
#
# Cron entry:
#   0 5 * * * /opt/eqio/scripts/reconcile_users_cron.sh
#
# Env vars:
#   BACKEND_DIR        — корень backend (default /opt/eqio/backend)
#   LOG_DIR            — куда писать JSON отчёт (default /var/log/eqio)
#   PYTHON_BIN         — путь к python (default python3)
#   SLACK_WEBHOOK      — Slack webhook URL для алертов (опционально)
#   RECONCILE_DAYS     — окно reconciliation в днях (default 30)

set -euo pipefail

BACKEND_DIR="${BACKEND_DIR:-/opt/eqio/backend}"
LOG_DIR="${LOG_DIR:-/var/log/eqio}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
RECONCILE_DAYS="${RECONCILE_DAYS:-30}"

mkdir -p "$LOG_DIR"
OUTPUT_JSON="${LOG_DIR}/reconcile-$(date +%F).json"

cd "$BACKEND_DIR"

set +e
"$PYTHON_BIN" -m tools.reconcile_users \
    --all-users \
    --days "$RECONCILE_DAYS" \
    --json "$OUTPUT_JSON" \
    ${SLACK_WEBHOOK:+--slack-webhook "$SLACK_WEBHOOK"}
EXIT_CODE=$?
set -e

# Логи: stdout уже выведен tool'ом, JSON в LOG_DIR.
# Exit code:
#   0 — ok, 1 — warnings, 2 — hard breaks (slack alert уже отправлен)
echo "reconcile_users exited with code $EXIT_CODE"
exit "$EXIT_CODE"
