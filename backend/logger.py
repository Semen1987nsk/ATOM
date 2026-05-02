import logging
import sys
from contextvars import ContextVar
from logging.handlers import RotatingFileHandler
from pathlib import Path

from config import settings

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


def _configure_logger() -> logging.Logger:
    logger = logging.getLogger(LOGGER_NAME)

    if logger.handlers:
        return logger

    logger.setLevel(_resolve_level(settings.LOG_LEVEL))
    logger.propagate = False

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(_resolve_level(settings.LOG_LEVEL))
    console_handler.addFilter(RequestIdFilter())
    console_format = logging.Formatter(
        '%(asctime)s | %(levelname)-7s | [req=%(request_id)s] %(message)s',
        datefmt='%H:%M:%S'
    )
    console_handler.setFormatter(console_format)
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
        file_format = logging.Formatter(
            '%(asctime)s | %(levelname)-7s | [req=%(request_id)s] %(name)s:%(funcName)s:%(lineno)d | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(file_format)
        logger.addHandler(file_handler)

    return logger


logger = _configure_logger()

def get_logger(name: str = "atom") -> logging.Logger:
    """Get a child logger with the given name."""
    _configure_logger()
    return logging.getLogger(f"atom.{name}")
