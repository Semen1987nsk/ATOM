"""
Утилиты безопасного логирования: маскирование токенов и чистка словарей.

Используется в `tools/live_smoke.py` и любых других standalone-скриптах,
которые работают с реальными секретами.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping

# Ключи, значения которых считаем секретами и заменяем на '***'.
DEFAULT_REDACT_KEYS: tuple[str, ...] = (
    "token",
    "api_token",
    "access_token",
    "refresh_token",
    "secret",
    "password",
    "authorization",
    "tinkoff_live_token",
    "tinkoff_sandbox_token_test",
)


def mask_token(token: str | None, *, visible_prefix: int = 4, visible_suffix: int = 4) -> str:
    """
    `t.XXXXXXXXXXXX...YYYY` → `t.XX…YYYY`.

    Никогда не печатает середину. Для очень коротких/None — возвращает
    `<empty>` или `<short>`, чтобы случайно не подсветить структуру.
    """
    if not token:
        return "<empty>"
    if len(token) < (visible_prefix + visible_suffix + 4):
        return "<short>"
    return f"{token[:visible_prefix]}…{token[-visible_suffix:]}"


def redact_dict_keys(
    obj: Any,
    *,
    keys_to_redact: Iterable[str] = DEFAULT_REDACT_KEYS,
    placeholder: str = "***",
) -> Any:
    """
    Глубоко обходит dict/list и заменяет значения по match'у имени ключа
    (case-insensitive). Возвращает новый объект — оригинал не мутируется.

    Используется перед JSON-сериализацией для `--save-report`.
    """
    keys_lower = {k.lower() for k in keys_to_redact}

    def _walk(value: Any) -> Any:
        if isinstance(value, Mapping):
            return {
                k: (placeholder if k.lower() in keys_lower else _walk(v))
                for k, v in value.items()
            }
        if isinstance(value, list):
            return [_walk(item) for item in value]
        if isinstance(value, tuple):
            return tuple(_walk(item) for item in value)
        return value

    return _walk(obj)
