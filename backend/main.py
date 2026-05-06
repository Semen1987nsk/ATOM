"""
ATOM API — Главный файл приложения

Рефакторинг: endpoints перенесены в routers/
"""
from fastapi import FastAPI, Depends, Request
from fastapi.openapi.docs import get_swagger_ui_html, get_redoc_html
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import text
from slowapi.errors import RateLimitExceeded
import traceback

import database
from contextlib import asynccontextmanager
from config import settings
from rate_limiter import limiter, rate_limit_exceeded_handler
from middleware import CSRFMiddleware, RequestContextMiddleware, RequestLoggingMiddleware, get_request_id_from_request
from logger import get_logger
from observability import init_sentry

# Импорт роутеров
from routers import (
    auth_router,
    trades_router,
    admin_router,
    blog_router,
    stats_router,
    market_router,
)
from routers.stats import tags_router
from routers.deposits import router as deposits_router
from routers.setups import router as setups_router
from routers.broker import router as broker_router
from routers.real_pnl import router as real_pnl_router
from routers.accounts import router as accounts_router
from routers.review import router as review_router
from routers.replay import router as replay_router
from sync_scheduler import scheduler

log = get_logger("api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: startup and shutdown events."""
    log.info("🚀 ATOM API v0.2.0 Starting...")
    log.info(f"📦 Routers: auth, trades, deposits, setups, broker, admin, blog, stats, market, real_pnl")

    # Sentry — раньше всего, чтобы стартовые ошибки тоже доезжали.
    init_sentry()

    if settings.AUTO_INIT_DB:
        database.init_db()
        log.warning("⚠️ AUTO_INIT_DB enabled: database schema ensured via SQLAlchemy create_all()")
    else:
        log.info("🗄️ AUTO_INIT_DB disabled: expecting schema to be managed via migrations")

    await scheduler.start()
    log.info("🔄 Auto-sync scheduler started")
    yield
    log.info("🛑 ATOM API shutting down...")
    await scheduler.stop()
    log.info("✅ Cleanup complete")


app = FastAPI(
    title="ATOM API",
    description="API для умного торгового дневника ATOM. "
                "Продвинутая аналитика торговых стратегий: Optimal f, SQN, MAE/MFE, Monte Carlo.",
    version="0.2.0",
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
)

# Rate limiter state
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)


# ==================== ГЛОБАЛЬНЫЕ ОБРАБОТЧИКИ ОШИБОК ====================

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """
    Обработчик ошибок валидации Pydantic.
    Возвращает понятные сообщения об ошибках.
    """
    errors = []
    for error in exc.errors():
        field = " -> ".join(str(loc) for loc in error["loc"])
        errors.append({
            "field": field,
            "message": error["msg"],
            "type": error["type"]
        })
    
    log.warning(f"Validation error on {request.url.path}: {errors}")
    
    return JSONResponse(
        status_code=422,
        headers={"X-Request-ID": get_request_id_from_request(request)},
        content={
            "detail": "Ошибка валидации данных",
            "errors": errors,
            "request_id": get_request_id_from_request(request),
        }
    )


@app.exception_handler(SQLAlchemyError)
async def sqlalchemy_exception_handler(request: Request, exc: SQLAlchemyError):
    """
    Обработчик ошибок SQLAlchemy.
    Скрывает детали БД в продакшене.
    """
    log.error(f"Database error on {request.url.path}: {exc}")
    
    if settings.DEBUG:
        return JSONResponse(
            status_code=500,
            headers={"X-Request-ID": get_request_id_from_request(request)},
            content={
                "detail": "Ошибка базы данных",
                "error": str(exc),
                "request_id": get_request_id_from_request(request),
            }
        )
    
    return JSONResponse(
        status_code=500,
        headers={"X-Request-ID": get_request_id_from_request(request)},
        content={
            "detail": "Внутренняя ошибка сервера",
            "request_id": get_request_id_from_request(request),
        }
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """
    Глобальный обработчик всех необработанных исключений.
    """
    log.error(f"Unhandled exception on {request.url.path}: {exc}")
    log.error(traceback.format_exc())
    
    if settings.DEBUG:
        return JSONResponse(
            status_code=500,
            headers={"X-Request-ID": get_request_id_from_request(request)},
            content={
                "detail": "Необработанная ошибка",
                "error": str(exc),
                "traceback": traceback.format_exc(),
                "request_id": get_request_id_from_request(request),
            }
        )
    
    return JSONResponse(
        status_code=500,
        headers={"X-Request-ID": get_request_id_from_request(request)},
        content={
            "detail": "Внутренняя ошибка сервера",
            "request_id": get_request_id_from_request(request),
        }
    )


# ==================== MIDDLEWARE ====================

# Request logging
app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(CSRFMiddleware)
app.add_middleware(RequestContextMiddleware)

# CORS — белый список методов/заголовков. Раньше было ["*"]/["*"], что
# с allow_credentials=True расширяет attack surface (любой preflight-friendly
# нестандартный метод/header проходит).
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_origin_regex=settings.CORS_ORIGIN_REGEX,
    allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=[
        "Authorization",
        "Content-Type",
        "Accept",
        "Origin",
        "X-Requested-With",
        "X-Request-ID",
        settings.CSRF_HEADER_NAME,
    ],
    expose_headers=["X-Request-ID", "X-Process-Time"],
)

# ==================== РОУТЕРЫ ====================

app.include_router(auth_router)
app.include_router(trades_router)
app.include_router(deposits_router)
app.include_router(setups_router)
app.include_router(broker_router)
app.include_router(admin_router)
app.include_router(blog_router)
app.include_router(stats_router, prefix="/stats")
app.include_router(tags_router)
app.include_router(market_router)
app.include_router(real_pnl_router, prefix="/real-pnl")
app.include_router(accounts_router)
app.include_router(review_router)
app.include_router(replay_router)

# ==================== СТАТИЧЕСКИЕ ФАЙЛЫ ====================
# Создаём папку uploads если её нет
uploads_dir = Path("uploads/screenshots")
uploads_dir.mkdir(parents=True, exist_ok=True)

# Монтируем папку uploads для отдачи скриншотов
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

# ==================== ДОКУМЕНТАЦИЯ ====================

@app.get("/docs", include_in_schema=False)
async def custom_swagger_ui_html():
    """Swagger UI с поддержкой HTTPS прокси (Codespaces)"""
    return get_swagger_ui_html(
        openapi_url=app.openapi_url,
        title=app.title + " - Swagger UI",
        oauth2_redirect_url=app.swagger_ui_oauth2_redirect_url,
        swagger_js_url="https://unpkg.com/swagger-ui-dist@5/swagger-ui-bundle.js",
        swagger_css_url="https://unpkg.com/swagger-ui-dist@5/swagger-ui.css",
    )


@app.get("/redoc", include_in_schema=False)
async def redoc_html():
    """ReDoc документация"""
    return get_redoc_html(
        openapi_url=app.openapi_url,
        title=app.title + " - ReDoc",
        redoc_js_url="https://unpkg.com/redoc@next/bundles/redoc.standalone.js",
    )


# ==================== КОРНЕВЫЕ ENDPOINTS ====================

@app.get("/")
async def read_root():
    """Корневой endpoint"""
    return {
        "message": "Добро пожаловать в ATOM API!",
        "version": "0.2.0",
        "docs": "/docs",
        "redoc": "/redoc"
    }


import schemas


@app.get("/health", response_model=schemas.HealthResponse)
async def health_check():
    """
    Liveness probe: процесс жив? Не делает дорогих проверок.
    Возвращает 200 пока процесс отвечает.
    """
    return JSONResponse(
        status_code=200,
        content={"status": "alive", "service": "atom-api", "version": settings.APP_VERSION},
    )


@app.get("/ready", response_model=schemas.ReadinessResponse, responses={503: {"model": schemas.ReadinessResponse}})
async def readiness_check():
    """
    Readiness probe: готов ли сервис принимать трафик?
    Проверяет ВСЕ критичные зависимости — DB обязательно, Redis если включён.

    Возвращает 503 если хоть одна зависимость недоступна — оркестратор
    (k8s/swarm/nginx) исключит инстанс из upstream до восстановления.
    """
    checks: dict = {}
    overall_ok = True

    # ── DB ──
    db_ok = database.check_db_connection()
    checks["database"] = {"ok": db_ok}
    overall_ok = overall_ok and db_ok

    # ── Redis (если используется) ──
    if settings.REDIS_URL:
        redis_ok = False
        redis_err = None
        try:
            import redis as redis_lib  # local import — opt-out если пакета нет
            client = redis_lib.from_url(settings.REDIS_URL, socket_connect_timeout=2, socket_timeout=2)
            redis_ok = bool(client.ping())
        except Exception as exc:
            redis_err = str(exc)
        checks["redis"] = {"ok": redis_ok}
        if redis_err:
            checks["redis"]["error"] = redis_err
        overall_ok = overall_ok and redis_ok
    else:
        checks["redis"] = {"ok": True, "note": "not configured"}

    status_code = 200 if overall_ok else 503
    return JSONResponse(
        status_code=status_code,
        content={
            "status": "ready" if overall_ok else "not_ready",
            "service": "atom-api",
            "version": settings.APP_VERSION,
            "checks": checks,
        },
    )


@app.get("/db-check")
def check_db(db: Session = Depends(database.get_db)):
    """Проверка подключения к БД"""
    try:
        db.execute(text("SELECT 1"))
        return {
            "status": "Database is connected",
            "connected": True,
        }
    except SQLAlchemyError as exc:
        log.warning(f"Database check failed: {exc}")
        return JSONResponse(
            status_code=503,
            content={
                "status": "Database connection failed",
                "connected": False,
            }
        )
