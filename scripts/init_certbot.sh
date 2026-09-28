#!/usr/bin/env bash
# scripts/init_certbot.sh — первичная инициализация Let's Encrypt сертификата для empirik.app.
#
# Prereq:
#   1. DNS empirik.app + www.empirik.app указывает на этот хост.
#   2. nginx запущен (docker compose up -d nginx) и слушает :80 с локацией
#      /.well-known/acme-challenge/ → root /var/www/certbot (см. nginx/conf.d/empirik.conf).
#   3. ENV LETSENCRYPT_EMAIL задан (admin email для уведомлений о ренью/expiry).
#
# Usage:
#   LETSENCRYPT_EMAIL=ops@empirik.app ./scripts/init_certbot.sh
#   LETSENCRYPT_EMAIL=ops@empirik.app ./scripts/init_certbot.sh staging.empirik.app
#
# После успеха: cert лежит в /etc/letsencrypt/live/<domain>/ внутри certbot-контейнера,
# проброшенный на ./nginx/certs хоста. Nginx читает его как :ro mount.
# Renewal — отдельный cron: docker compose run --rm certbot renew && docker compose exec nginx nginx -s reload.

set -euo pipefail

DOMAIN="${1:-empirik.app}"
EMAIL="${LETSENCRYPT_EMAIL:?LETSENCRYPT_EMAIL env required (admin email for Let's Encrypt notifications)}"

# Использовать staging Let's Encrypt API для тестов: STAGING=1 ./scripts/init_certbot.sh
STAGING_FLAG=""
if [[ "${STAGING:-0}" == "1" ]]; then
    STAGING_FLAG="--staging"
    echo "WARNING: using Let's Encrypt STAGING — сертификат будет не доверенным (только для smoke-теста ACME flow)."
fi

echo "Bootstrap certbot for ${DOMAIN} (email: ${EMAIL})"
echo "Webroot challenge через nginx — убедись что http://${DOMAIN}/.well-known/acme-challenge/ доступен извне."

docker compose run --rm certbot certonly \
    --webroot \
    --webroot-path /var/www/certbot \
    --email "${EMAIL}" \
    --agree-tos \
    --no-eff-email \
    --non-interactive \
    --rsa-key-size 4096 \
    ${STAGING_FLAG} \
    --domains "${DOMAIN},www.${DOMAIN}"

echo "Certificate obtained. Reloading nginx..."
docker compose exec nginx nginx -s reload

echo "Done. Verify: curl -sSI https://${DOMAIN}/health"
