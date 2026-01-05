"""
ATOM API — Главный файл приложения

Рефакторинг: endpoints перенесены в routers/
"""
from fastapi import FastAPI, Depends, Request
from fastapi.openapi.docs import get_swagger_ui_html, get_redoc_html
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from slowapi.errors import RateLimitExceeded

import database
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

log = get_logger("api")

# Инициализируем базу данных при запуске
database.init_db()

app = FastAPI(
    title="ATOM API",
    description="API для умного торгового дневника ATOM. "
                "Продвинутая аналитика торговых стратегий: Optimal f, SQN, MAE/MFE, Monte Carlo.",
    version="0.2.0",
    docs_url=None,
    redoc_url=None,
)

# Rate limiter state
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)

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
app.include_router(admin_router)
app.include_router(blog_router)
app.include_router(stats_router)
app.include_router(market_router)

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


# ==================== СОБЫТИЯ ====================

@app.on_event("startup")
async def startup_event():
    log.info("🚀 ATOM API v0.2.0 Starting...")
    log.info("📦 Routers loaded: auth, trades, admin, blog, stats, market")
    log.debug("Registered routes:")
    for route in app.routes:
        if hasattr(route, 'path'):
            log.debug(f"  → {route.path}")


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
