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
from slowapi.errors import RateLimitExceeded
import traceback

import database
from contextlib import asynccontextmanager
from config import settings
from rate_limiter import limiter, rate_limit_exceeded_handler
from middleware import RequestLoggingMiddleware
from logger import get_logger

# Импорт роутеров
from routers import (
    auth_router,
    trades_router,
    admin_router,
    blog_router,
    stats_router,
    market_router,
)
from routers.deposits import router as deposits_router
from routers.setups import router as setups_router
from routers.broker import router as broker_router
from routers.real_pnl import router as real_pnl_router
from sync_scheduler import scheduler

log = get_logger("api")

# Инициализируем базу данных при запуске
database.init_db()


@asynccontextmanager
async def lifespan(app):
    """Application lifespan: startup and shutdown events."""
    log.info("🚀 ATOM API v0.2.0 Starting...")
    log.info(f"📦 Routers: auth, trades, deposits, setups, broker, admin, blog, stats, market, real_pnl")
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
        content={
            "detail": "Ошибка валидации данных",
            "errors": errors
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
            content={
                "detail": "Ошибка базы данных",
                "error": str(exc)
            }
        )
    
    return JSONResponse(
        status_code=500,
        content={"detail": "Внутренняя ошибка сервера"}
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
            content={
                "detail": "Необработанная ошибка",
                "error": str(exc),
                "traceback": traceback.format_exc()
            }
        )
    
    return JSONResponse(
        status_code=500,
        content={"detail": "Внутренняя ошибка сервера"}
    )


# ==================== MIDDLEWARE ====================

# Request logging
app.add_middleware(RequestLoggingMiddleware)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_origin_regex=settings.CORS_ORIGIN_REGEX,
    allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
    allow_methods=["*"],
    allow_headers=["*"],
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
app.include_router(market_router)
app.include_router(real_pnl_router, prefix="/real-pnl")

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


@app.get("/health")
async def health_check():
    """Health check для мониторинга"""
    return {"status": "healthy", "service": "atom-api"}


@app.get("/db-check")
def check_db(db: Session = Depends(database.get_db)):
    """Проверка подключения к БД"""
    return {"status": "Database is connected and tables are created"}
