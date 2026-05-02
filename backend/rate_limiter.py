"""
Rate Limiting — защита от brute-force атак и DDoS.

Использует slowapi с Redis backend для production.
Fallback на in-memory для разработки.
"""

from ipaddress import ip_address, ip_network
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from fastapi import Request
from fastapi.responses import JSONResponse
from logger import get_logger
from config import settings

log = get_logger("ratelimit")

RATE_LIMIT_STORAGE_URI = settings.RATE_LIMIT_STORAGE_URI

# Pre-parse trusted proxy networks once at module load
_TRUSTED_NETWORKS = []
for _cidr in settings.TRUSTED_PROXIES:
    try:
        _TRUSTED_NETWORKS.append(ip_network(_cidr, strict=False))
    except ValueError:
        log.warning(f"Invalid TRUSTED_PROXIES entry ignored: {_cidr}")


def _is_trusted_proxy(addr: str) -> bool:
    """Check if the given IP address belongs to a trusted proxy network."""
    if not _TRUSTED_NETWORKS:
        return False
    try:
        ip = ip_address(addr)
        return any(ip in net for net in _TRUSTED_NETWORKS)
    except ValueError:
        return False


def get_client_ip(request: Request) -> str:
    """
    Extract the real client IP, trusting X-Forwarded-For ONLY
    if the direct connection comes from a configured trusted proxy.
    """
    # Direct socket IP
    socket_ip = request.client.host if request.client else "unknown"

    if not _is_trusted_proxy(socket_ip):
        # Not from a trusted proxy — ignore forwarding headers
        return socket_ip

    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        # Rightmost untrusted IP = real client
        parts = [p.strip() for p in forwarded_for.split(",")]
        # Walk from the right, skip trusted proxies
        for part in reversed(parts):
            if not _is_trusted_proxy(part):
                return part
        # All IPs are trusted proxies — fall back to leftmost
        return parts[0]

    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()

    return socket_ip


def get_rate_limit_key(request: Request) -> str:
    """Rate-limit key based on real client IP."""
    return get_client_ip(request)


if settings.RATE_LIMIT_ENABLED and RATE_LIMIT_STORAGE_URI:
    # Redis backend для production
    limiter = Limiter(
        key_func=get_rate_limit_key,
        storage_uri=RATE_LIMIT_STORAGE_URI,
        strategy=settings.RATE_LIMIT_STRATEGY,
    )
    log.info("✅ Rate limiter using Redis backend")
else:
    # In-memory backend для разработки
    limiter = Limiter(
        key_func=get_rate_limit_key,
        strategy=settings.RATE_LIMIT_STRATEGY,
        enabled=settings.RATE_LIMIT_ENABLED,
    )
    if settings.RATE_LIMIT_ENABLED:
        log.warning("⚠️ Rate limiter using in-memory storage (not suitable for production)")
    else:
        log.warning("⚠️ Rate limiter disabled by configuration")


def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded):
    """
    Обработчик превышения лимита запросов.
    Возвращает JSON с понятным сообщением.
    """
    log.warning(f"Rate limit exceeded for {get_rate_limit_key(request)}: {exc.detail}")
    return JSONResponse(
        status_code=429,
        content={
            "detail": "Слишком много запросов. Попробуйте позже.",
            "error": "rate_limit_exceeded",
            "retry_after": str(exc.detail).split()[-1] if exc.detail else "60"
        }
    )


def reset_rate_limiter_storage() -> None:
    """Сбросить storage limiter — полезно для изоляции тестов."""
    storage = getattr(limiter, "_storage", None)
    if storage is None:
        return

    reset = getattr(storage, "reset", None)
    if callable(reset):
        reset()
        return

    clear = getattr(storage, "clear", None)
    if callable(clear):
        clear()


# ==================== RATE LIMIT PRESETS ====================
# Используйте как декораторы на endpoints

# Для авторизации (строгий лимит)
AUTH_LIMIT = "5/minute"  # 5 попыток в минуту

# Для регистрации (очень строгий)
REGISTER_LIMIT = "3/minute"  # 3 регистрации в минуту

# Для API (умеренный)
API_LIMIT = "60/minute"  # 60 запросов в минуту

# Для импорта файлов (редкие операции)
IMPORT_LIMIT = "10/minute"  # 10 импортов в минуту

# Для AI запросов (дорогие операции)
AI_LIMIT = "5/minute"  # 5 AI анализов в минуту
