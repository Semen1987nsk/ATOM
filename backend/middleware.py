"""
HTTP Request Logging Middleware — логирование всех HTTP запросов.
"""

import time
from uuid import uuid4
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response, JSONResponse
from auth_service import is_cookie_authenticated_request, validate_csrf_request
from config import settings
from logger import clear_request_id, get_logger, get_request_id, set_request_id
from rate_limiter import get_client_ip

log = get_logger("http")
security_log = get_logger("security")


def get_request_id_from_request(request: Request) -> str:
    return getattr(request.state, "request_id", get_request_id())


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Назначает correlation/request id для каждого HTTP запроса."""

    HEADER_NAME = "X-Request-ID"

    async def dispatch(self, request: Request, call_next) -> Response:
        incoming_request_id = request.headers.get(self.HEADER_NAME, "").strip()
        request_id = incoming_request_id[:128] if incoming_request_id else uuid4().hex

        request.state.request_id = request_id
        set_request_id(request_id)

        try:
            response = await call_next(request)
        finally:
            clear_request_id()

        response.headers[self.HEADER_NAME] = request_id
        return response


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    Middleware для логирования HTTP запросов.
    
    Логирует:
    - Метод и путь запроса
    - Время выполнения
    - Статус-код ответа
    - IP клиента
    """
    
    async def dispatch(self, request: Request, call_next) -> Response:
        start_time = time.perf_counter()
        
        # Получаем IP клиента (через trusted-proxy logic)
        client_ip = get_client_ip(request)
        
        # Выполняем запрос
        response = await call_next(request)
        
        # Вычисляем время
        process_time = (time.perf_counter() - start_time) * 1000  # в миллисекундах
        
        # Формируем лог-сообщение
        status_emoji = "✅" if response.status_code < 400 else "⚠️" if response.status_code < 500 else "❌"
        
        # Пропускаем частые health-check запросы для чистоты логов
        if request.url.path not in ("/health", "/docs", "/openapi.json"):
            log.info(
                f"{status_emoji} {request.method} {request.url.path} "
                f"→ {response.status_code} ({process_time:.1f}ms) "
                f"[{client_ip}]"
            )
        
        # Добавляем заголовок с временем обработки
        response.headers["X-Process-Time"] = f"{process_time:.2f}ms"
        
        return response


class CSRFMiddleware(BaseHTTPMiddleware):
    """Double-submit CSRF защита для cookie-based auth запросов."""

    SAFE_METHODS = {"GET", "HEAD", "OPTIONS", "TRACE"}
    EXEMPT_PATHS = {
        "/auth/login",
        "/auth/register",
        "/auth/oauth/providers",
    }

    async def dispatch(self, request: Request, call_next) -> Response:
        if request.method in self.SAFE_METHODS:
            return await call_next(request)

        if request.url.path in self.EXEMPT_PATHS:
            return await call_next(request)

        if request.url.path.startswith("/auth/oauth/"):
            return await call_next(request)

        if not is_cookie_authenticated_request(request):
            return await call_next(request)

        if validate_csrf_request(request):
            return await call_next(request)

        security_log.warning(f"CSRF validation failed for {request.method} {request.url.path}")
        return JSONResponse(
            status_code=403,
            headers={"X-Request-ID": get_request_id_from_request(request)},
            content={
                "detail": "CSRF token missing or invalid",
                "error": "csrf_validation_failed",
                "header": settings.CSRF_HEADER_NAME,
                "request_id": get_request_id_from_request(request),
            }
        )
