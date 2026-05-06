import logging
import sys
from contextvars import ContextVar
from logging.handlers import RotatingFileHandler
from pathlib import Path

from config import settings

# Опциональная зависимость для JSON-логов (для прода).
# Если pkg не установлен — graceful fallback на текстовый формат.
try:  # pragma: no cover - environment-dependent
    from pythonjsonlogger import jsonlogger as _jsonlogger
except Exception:  # pragma: no cover
    _jsonlogger = None

LOGGER_NAME = "atom"
_request_id_ctx: ContextVar[str] = ContextVar("request_id", default="-")


class RequestIdFilter(logging.Filter):
    """Inject request_id from contextvars into every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = _request_id_ctx.get("-")
        return True


def set_request_id(request_id: str) -> None:
    _request_id_ctx.set(request_id)


def get_request_id() -> str:
    return _request_id_ctx.get("-")


def clear_request_id() -> None:
    _request_id_ctx.set("-")


def _resolve_level(level_name: str) -> int:
    return getattr(logging, level_name.upper(), logging.INFO)


def _build_formatter(json_mode: bool, *, file: bool) -> logging.Formatter:
    """
    Возвращает форматтер: text (dev) или JSON (prod-агрегаторы).

    JSON-режим включается через LOG_FORMAT_MODE=json и требует
    `python-json-logger` (опциональная зависимость).
    Если пакет не установлен — fallback на текстовый формат с warning.
    """
    if json_mode and _jsonlogger is not None:
        # Поля по rsyslog/ECS-конвенции: время, уровень, request_id, сообщение, координаты
        fmt = "%(asctime)s %(levelname)s %(name)s %(funcName)s %(lineno)d %(request_id)s %(message)s"
        return _jsonlogger.JsonFormatter(fmt, json_ensure_ascii=False, rename_fields={"asctime": "ts", "levelname": "level"})

    if file:
        return logging.Formatter(
            '%(asctime)s | %(levelname)-7s | [req=%(request_id)s] %(name)s:%(funcName)s:%(lineno)d | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S',
        )
    return logging.Formatter(
        '%(asctime)s | %(levelname)-7s | [req=%(request_id)s] %(message)s',
        datefmt='%H:%M:%S',
    )


def _configure_logger() -> logging.Logger:
    logger = logging.getLogger(LOGGER_NAME)

    if logger.handlers:
        return logger

    logger.setLevel(_resolve_level(settings.LOG_LEVEL))
    logger.propagate = False

    json_mode = getattr(settings, "LOG_FORMAT_MODE", "text") == "json"
    if json_mode and _jsonlogger is None:
        logger.warning(
            "LOG_FORMAT_MODE=json, но python-json-logger не установлен. "
            "Fallback на text. Установи pip install python-json-logger."
        )

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(_resolve_level(settings.LOG_LEVEL))
    console_handler.addFilter(RequestIdFilter())
    console_handler.setFormatter(_build_formatter(json_mode, file=False))
    logger.addHandler(console_handler)

    if settings.ENABLE_FILE_LOGGING:
        log_dir = Path(settings.LOG_DIR)
        log_dir.mkdir(parents=True, exist_ok=True)

        file_handler = RotatingFileHandler(
            log_dir / 'atom.log',
            maxBytes=5 * 1024 * 1024,
            backupCount=5,
            encoding='utf-8'
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.addFilter(RequestIdFilter())
        file_handler.setFormatter(_build_formatter(json_mode, file=True))
        logger.addHandler(file_handler)

    return logger


logger = _configure_logger()

def get_logger(name: str = "atom") -> logging.Logger:
    """Get a child logger with the given name."""
    _configure_logger()
    return logging.getLogger(f"atom.{name}")
