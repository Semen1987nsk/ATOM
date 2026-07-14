#!/usr/bin/env bash
# PR 26 Phase 3 — Self-imposed deploy window guard.
#
# Запускается через `git push` hook ИЛИ вручную перед deploy:
#   bash scripts/deploy_window_check.sh
#
# Правила:
# - Деплоить разрешено: пн-чт 10:00-17:00 MSK
# - Пятница после 14:00, выходные, ночи 23:00-09:00 → блок
# - Override: `DEPLOY_FORCE=1 bash scripts/deploy_window_check.sh`
#
# Идея: founder-solo не должен деплоить в пятницу вечером и в воскресенье
# в 3 часа ночи. Если deploy ломает прод, починить будет некому.
set -euo pipefail

if [ "${DEPLOY_FORCE:-0}" = "1" ]; then
    echo "⚠️  DEPLOY_FORCE=1 — skipping window check"
    exit 0
fi

# MSK = UTC+3
HOUR=$(TZ=Europe/Moscow date +%H)
DOW=$(TZ=Europe/Moscow date +%u)  # 1=Mon ... 7=Sun

reason=""
if [ "${DOW}" -ge 6 ]; then
    reason="weekend (DOW=${DOW})"
elif [ "${DOW}" -eq 5 ] && [ "${HOUR}" -ge 14 ]; then
    reason="friday after 14:00 MSK"
elif [ "${HOUR}" -lt 9 ] || [ "${HOUR}" -ge 17 ]; then
    reason="outside business hours (now ${HOUR}:00 MSK)"
fi

if [ -n "${reason}" ]; then
    echo ""
    echo "🚫 Deploy window violation: ${reason}"
    echo ""
    echo "Разрешённое окно: пн-чт 09:00-17:00 MSK, пт 09:00-14:00."
    echo "Override: DEPLOY_FORCE=1 $0"
    echo ""
    exit 1
fi

echo "✅ Deploy window OK (DOW=${DOW}, hour=${HOUR} MSK)"
exit 0
