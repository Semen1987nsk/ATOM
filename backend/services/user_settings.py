"""Phase 11 (2026-05-17): валидация User.settings JSON.

Защита от storage abuse — `PUT /auth/me { settings: {...} }` принимает только
whitelisted keys с правильными типами/значениями. Unknown keys silently dropped
с warning лог, чтобы старые версии фронта не ломали backend.

Used by:
  - auth_service.update_user() при PATCH User.settings
"""
from __future__ import annotations

from typing import Any, Set

from logger import get_logger

log = get_logger("user_settings")


# Whitelist валидных ключей User.settings (всё что не в списке — отбрасывается).
ALLOWED_SETTINGS_KEYS: Set[str] = {
    # UI preferences
    "currency",                  # "RUB" | "USD" | "EUR" | etc
    "currencySymbol",
    "theme",                     # "dark" | "light" | "system"
    "language",                  # "ru" | "en"
    # Analytics preferences
    "maeCalculationMethod",
    "tradesStartDate",
    # Phase 11 (2026-05-17): P&L display mode
    "pnlDisplayMode",            # "net" | "gross"
}


VALID_PNL_DISPLAY_MODES = {"net", "gross"}


def validate_settings(raw_settings: Any) -> dict:
    """Sanitize incoming settings dict.

    - Non-dict input → пустой {}.
    - Unknown keys → dropped (logged).
    - Known keys с invalid values → dropped (logged).
    - Known keys с valid values → kept.

    Возвращает новый dict (не мутирует input).
    """
    if not isinstance(raw_settings, dict):
        log.warning("user_settings.invalid_type", extra={"type": type(raw_settings).__name__})
        return {}

    sanitized: dict = {}
    for key, value in raw_settings.items():
        if key not in ALLOWED_SETTINGS_KEYS:
            log.info("user_settings.unknown_key_dropped", extra={"key": key})
            continue

        # Per-key validation для критичных полей.
        if key == "pnlDisplayMode":
            if value not in VALID_PNL_DISPLAY_MODES:
                log.warning(
                    "user_settings.invalid_pnl_display_mode",
                    extra={"value": str(value)[:50]},
                )
                continue

        sanitized[key] = value

    return sanitized
