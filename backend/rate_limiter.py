"""
Rate Limiting — защита от brute-force атак и DDoS.

Использует slowapi с Redis backend для production.
Fallback на in-memory для разработки.
"""

import os
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from fastapi import Request
from fastapi.responses import JSONResponse
from logger import get_logger

log = get_logger("ratelimit")

# Определяем storage backend
REDIS_URL = os.getenv("REDIS_URL")

if REDIS_URL:
    from slowapi.middleware import SlowAPIMiddleware
    # Redis backend для production
    limiter = Limiter(
        key_func=get_remote_address,
        storage_uri=REDIS_URL,
        strategy="fixed-window"
    )
    log.info("✅ Rate limiter using Redis backend")
else:
    # In-memory backend для разработки
    limiter = Limiter(key_func=get_remote_address)
    log.warning("⚠️ Rate limiter using in-memory storage (not suitable for production)")


def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded):
    """
    Обработчик превышения лимита запросов.
    Возвращает JSON с понятным сообщением.
    """
    log.warning(f"Rate limit exceeded for {get_remote_address(request)}: {exc.detail}")
    return JSONResponse(
        status_code=429,
        content={
            "detail": "Слишком много запросов. Попробуйте позже.",
            "error": "rate_limit_exceeded",
            "retry_after": str(exc.detail).split()[-1] if exc.detail else "60"
        }
    )


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
