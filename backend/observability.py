"""
Observability bootstrap — Sentry SDK init.

Инициализируется в main.py lifespan. Если SENTRY_DSN не задан — модуль
ничего не делает (нулевые внешние сетевые вызовы), что важно для
изолированных тестов и локальной разработки без интернета.

PR 16: расширен `_before_send` — маскирует Tinkoff-токены (`t.XXXX...`)
в строках исключений и breadcrumb messages. Это защита на случай если
SDK или наш код случайно положит токен в exception message.

AU10 Phase 4b: `t-tech-investments 0.3.x` имеет хардкоженный Sentry DSN
(`error-hub.tbank.ru`) и инициализирует свой собственный Sentry Client
при первом RPC. Для compliance (152-ФЗ — никакая ошибка/телеметрия не
должна уходить на сторонний сервис без явного согласия пользователя)
и для предотвращения конфликта Hub'ов мы блокируем их auto-init через
`block_third_party_sentry_init()`. Наш Sentry (single Hub, наш DSN) —
единственный получатель ошибок приложения.
"""
from __future__ import annotations

import re
from typing import Any, Optional

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
    из тела request/headers + маскируем Tinkoff-токены в exception
    messages (PR 16).
    """
    sensitive_keys = {
        "password", "hashed_password", "token", "access_token",
        "refresh_token", "api_token", "secret", "authorization",
        "cookie", "x-csrf-token",
        # PR 16: добавлены поля наших новых интеграций.
        "tinkoff_live_token", "tinkoff_sandbox_token_test",
        "master_key_b64",
    }

    request = event.get("request") or {}
    if isinstance(request.get("data"), dict):
        request["data"] = _redact(request["data"], sensitive_keys)
    headers = request.get("headers")
    if isinstance(headers, dict):
        request["headers"] = _redact(headers, sensitive_keys)

    # PR 16: маскируем Tinkoff-токены в строках исключений и breadcrumb'ах.
    # Tinkoff-токены имеют формат `t.XXXXXXXXXXXXX...` ~88 символов.
    _mask_tokens_in_strings(event)
    return event


# `t.` + base64url-набор минимум 20 символов = «выглядит как Tinkoff-токен».
# Реальный длиной 80–90; ограничиваем нижнюю границу 20, чтобы не редактить
# короткие техслова типа "t.is_active".
_TINKOFF_TOKEN_RE = re.compile(r"\bt\.[A-Za-z0-9_-]{20,}\b")


def _mask_tokens_in_strings(event: dict) -> None:
    """
    Заменяет любые подстроки, похожие на Tinkoff-токен, на `t.****MASKED****`.
    Обходит exception values, breadcrumb messages, extra/tags.
    """

    def _maybe_mask(value: Any) -> Any:
        if isinstance(value, str):
            return _TINKOFF_TOKEN_RE.sub("t.****MASKED****", value)
        if isinstance(value, dict):
            return {k: _maybe_mask(v) for k, v in value.items()}
        if isinstance(value, list):
            return [_maybe_mask(v) for v in value]
        return value

    # exception values
    exc_block = event.get("exception", {})
    if isinstance(exc_block, dict):
        for entry in exc_block.get("values", []) or []:
            if isinstance(entry, dict) and "value" in entry:
                entry["value"] = _maybe_mask(entry["value"])

    # breadcrumbs
    breadcrumbs = event.get("breadcrumbs", {})
    if isinstance(breadcrumbs, dict):
        for bc in breadcrumbs.get("values", []) or []:
            if isinstance(bc, dict):
                if "message" in bc:
                    bc["message"] = _maybe_mask(bc["message"])
                if "data" in bc:
                    bc["data"] = _maybe_mask(bc["data"])

    # message + extra
    if "message" in event:
        event["message"] = _maybe_mask(event["message"])
    if isinstance(event.get("extra"), dict):
        event["extra"] = _maybe_mask(event["extra"])


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


# ── AU10 Phase 4b: T-Bank ErrorHub isolation ─────────────────────────────


# DSN-ы которые мы блокируем (Sentry-инициализации со стороны third-party SDK).
# T-Bank SDK 0.3.x хардкодит DSN `https://invest-piapi-errorhub@error-hub.tbank.ru/...`
# и инициализирует свой Client автоматически. Это конфликтует с нашим Sentry
# (один-default-Hub паттерн SDK) и нарушает 152-ФЗ data minimization.
_BLOCKED_SENTRY_DSN_FRAGMENTS = (
    "error-hub.tbank.ru",
    "error-hub.tinkoff.ru",  # на случай legacy DNS, если SDK когда-то откатится
)


def block_third_party_sentry_init() -> None:
    """Подменяет `sentry_sdk.init` чтобы no-op'ить попытки third-party init.

    Вызывается СРАЗУ после нашего `init_sentry()`. Наш Hub уже создан,
    последующие вызовы `sentry_sdk.init(dsn=...)` со стороны t-tech-investments
    отлавливаются по фрагменту DSN и игнорируются с логом.

    NB: НЕ блокирует наш собственный re-init (мы используем наш SENTRY_DSN
    из settings, который никак не пересекается с error-hub.tbank.ru).
    """
    try:
        import sentry_sdk
    except Exception:  # pragma: no cover
        return

    _real_init = sentry_sdk.init

    def _filtered_init(*args, **kwargs):
        dsn = kwargs.get("dsn") if "dsn" in kwargs else (args[0] if args else None)
        dsn_str = str(dsn or "")
        for fragment in _BLOCKED_SENTRY_DSN_FRAGMENTS:
            if fragment in dsn_str:
                log.info(
                    "sentry.third_party_init_blocked: fragment=%s "
                    "(t-tech-investments ErrorHub blocked for 152-ФЗ compliance)",
                    fragment,
                )
                return None
        return _real_init(*args, **kwargs)

    sentry_sdk.init = _filtered_init  # type: ignore[assignment]
    log.info("sentry.third_party_guard_installed")
