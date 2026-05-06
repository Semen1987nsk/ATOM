"""
Observability bootstrap — Sentry SDK init.

Инициализируется в main.py lifespan. Если SENTRY_DSN не задан — модуль
ничего не делает (нулевые внешние сетевые вызовы), что важно для
изолированных тестов и локальной разработки без интернета.
"""
from __future__ import annotations

from typing import Optional

from config import settings
from logger import get_logger

log = get_logger("observability")


def init_sentry() -> bool:
    """
    Инициализирует Sentry SDK, если SENTRY_DSN задан.

    Возвращает True, если SDK инициализирован, иначе False.
    """
    if not settings.SENTRY_DSN:
        log.info("Sentry: SENTRY_DSN пуст — мониторинг ошибок не активирован.")
        return False

    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.starlette import StarletteIntegration
        from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
    except Exception as exc:  # pragma: no cover
        log.warning("Sentry SDK не установлен (%s). pip install 'sentry-sdk[fastapi]'", exc)
        return False

    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        environment=settings.SENTRY_ENVIRONMENT,
        release=settings.SENTRY_RELEASE or None,
        traces_sample_rate=settings.SENTRY_TRACES_SAMPLE_RATE,
        # Рекомендация для финансовых SaaS: НЕ отправлять PII (email, ip)
        # пока юристы не сделали DPA. Включай send_default_pii=True осознанно.
        send_default_pii=False,
        attach_stacktrace=True,
        integrations=[
            FastApiIntegration(),
            StarletteIntegration(),
            SqlalchemyIntegration(),
        ],
        before_send=_before_send,
    )
    log.info(
        "Sentry: initialized (env=%s, traces_rate=%.2f, release=%s)",
        settings.SENTRY_ENVIRONMENT,
        settings.SENTRY_TRACES_SAMPLE_RATE,
        settings.SENTRY_RELEASE or "(unset)",
    )
    return True


def _before_send(event, hint):
    """
    Pre-send фильтр: вырезаем потенциально чувствительные поля
    из тела request/headers перед отправкой в Sentry.
    """
    sensitive_keys = {
        "password", "hashed_password", "token", "access_token",
        "refresh_token", "api_token", "secret", "authorization",
        "cookie", "x-csrf-token",
    }

    request = event.get("request") or {}
    if isinstance(request.get("data"), dict):
        request["data"] = _redact(request["data"], sensitive_keys)
    headers = request.get("headers")
    if isinstance(headers, dict):
        request["headers"] = _redact(headers, sensitive_keys)
    return event


def _redact(d: dict, sensitive_keys: set) -> dict:
    out = {}
    for k, v in d.items():
        if k.lower() in sensitive_keys:
            out[k] = "***"
        elif isinstance(v, dict):
            out[k] = _redact(v, sensitive_keys)
        else:
            out[k] = v
    return out
