"""
HTTP Request Logging Middleware — логирование всех HTTP запросов.
"""

import time
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
from logger import get_logger

log = get_logger("http")


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
        
        # Получаем IP клиента
        client_ip = request.headers.get("X-Forwarded-For", request.client.host if request.client else "unknown")
        if "," in client_ip:
            client_ip = client_ip.split(",")[0].strip()
        
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
