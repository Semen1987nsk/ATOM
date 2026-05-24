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


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    PR 26 — стандартные security headers для всех HTTP ответов.

    Закрывает риски из аудита:
    - XSS: CSP запрещает inline-скрипты и сторонние источники
    - Clickjacking: X-Frame-Options блокирует встраивание в iframe
    - MIME-sniffing: X-Content-Type-Options
    - Downgrade attack: HSTS форсит HTTPS на 1 год
    - Referer leakage: Referrer-Policy
    - FLoC: Permissions-Policy отключает интрузивные browser APIs

    CSP подобран под Next.js + Sentry CDN. unsafe-inline в style-src — это
    Tailwind/styled JSX limitation; в API responses (где нет HTML) CSP
    можно сделать строже, но Next.js рендерит inline styles.
    """

    # Включаем HSTS только если HTTPS — иначе ломаем dev на http://localhost.
    _HSTS_VALUE = "max-age=31536000; includeSubDomains"

    # Production CSP. В dev (DEBUG=true) расслабляем для HMR.
    _CSP_PROD = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://*.ingest.sentry.io https://yookassa.ru; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: blob: https:; "
        "font-src 'self' data:; "
        "connect-src 'self' https://*.ingest.sentry.io https://api.yookassa.ru https://invest-public-api.tbank.ru https://invest-public-api.tinkoff.ru wss:; "
        "frame-ancestors 'none'; "
        "base-uri 'self'; "
        "form-action 'self' https://yookassa.ru;"
    )
    _CSP_DEV = (
        "default-src 'self' 'unsafe-inline' 'unsafe-eval' data: blob:; "
        "connect-src 'self' http://localhost:* ws://localhost:* https:;"
    )

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)

        # HSTS — только под HTTPS (request.url.scheme == https) или за прокси
        # с X-Forwarded-Proto=https. В dev по http не выставляем чтобы не
        # ломать локальный браузер.
        is_https = (
            request.url.scheme == "https"
            or request.headers.get("x-forwarded-proto", "").lower() == "https"
        )
        if is_https:
            response.headers.setdefault("Strict-Transport-Security", self._HSTS_VALUE)

        # X-Frame-Options + frame-ancestors дублируют защиту (Frame-Ancestors
        # в CSP — современный стандарт, X-Frame-Options — legacy для старых
        # браузеров; оба не повредят).
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault(
            "Permissions-Policy",
            "interest-cohort=(), browsing-topics=()",
        )

        # CSP отдельный для HTML-ответов. JSON-ответы могут не содержать CSP,
        # но если в браузер открыть напрямую — он применит. Поэтому ставим
        # везде; для API это nop, для HTML — защита.
        csp = self._CSP_DEV if settings.DEBUG else self._CSP_PROD
        response.headers.setdefault("Content-Security-Policy", csp)

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
    
    # PR 26 Phase 2: 10% sampling в AccessLogORM для admin debugging.
    # Skip-path для health-check, чтобы не засорять.
    _SKIP_LOG_PATHS = frozenset({"/health", "/ready", "/db-check", "/docs", "/redoc", "/openapi.json"})

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
        if request.url.path not in self._SKIP_LOG_PATHS:
            log.info(
                f"{status_emoji} {request.method} {request.url.path} "
                f"→ {response.status_code} ({process_time:.1f}ms) "
                f"[{client_ip}]"
            )

            # PR 26 Phase 2: 1/10 sample → AccessLogORM (best-effort, не падает).
            # ВСЕ 4xx/5xx записываем (важно для debug). 2xx — 10%.
            should_persist = (
                response.status_code >= 400
                or (int(time.time() * 1000) % 10 == 0)
            )
            if should_persist:
                try:
                    self._persist_access_log(
                        request=request,
                        status_code=response.status_code,
                        duration_ms=int(process_time),
                        client_ip=client_ip,
                    )
                except Exception:
                    pass  # never break the request

        # Добавляем заголовок с временем обработки
        response.headers["X-Process-Time"] = f"{process_time:.2f}ms"

        return response

    def _persist_access_log(self, request, status_code, duration_ms, client_ip):
        """Записать sampled запись в access_log (sync, через context manager)."""
        from database import SessionLocal
        from models import AccessLogORM
        from utils.datetime_utils import utc_now_naive

        user_id = None
        # Берём user_id из request.state если auth middleware его проставил
        try:
            user_id = getattr(request.state, "user_id", None)
        except Exception:
            pass

        ua = request.headers.get("user-agent", "")[:256] or None
        request_id = getattr(request.state, "request_id", None)

        db = SessionLocal()
        try:
            db.add(AccessLogORM(
                user_id=user_id,
                method=request.method[:8],
                path=str(request.url.path)[:256],
                status_code=status_code,
                duration_ms=duration_ms,
                request_id=(request_id or "")[:64] or None,
                ip_address=(client_ip or "")[:64] or None,
                user_agent=ua,
                created_at=utc_now_naive(),
            ))
            db.commit()
        finally:
            db.close()


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
