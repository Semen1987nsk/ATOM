"""
ATOM API — Главный файл приложения

Рефакторинг: endpoints перенесены в routers/
"""
from fastapi import FastAPI, Request
from fastapi.openapi.docs import get_swagger_ui_html, get_redoc_html
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from sqlalchemy.exc import SQLAlchemyError
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
import traceback

import database
from contextlib import asynccontextmanager
from config import settings
from rate_limiter import limiter, rate_limit_exceeded_handler
from middleware import (
    CSRFMiddleware,
    RequestContextMiddleware,
    RequestLoggingMiddleware,
    SecurityHeadersMiddleware,
    get_request_id_from_request,
)
from logger import get_logger
from observability import init_sentry, block_third_party_sentry_init

# Импорт роутеров
from routers import (
    auth_router,
    trades_router,
    admin_router,
    blog_router,
    stats_router,
    market_router,
)
from routers.stats_tags import (
    router as tags_router,
    stats_prefixed_router as stats_tags_router,
)
from routers.stats_advanced import router as stats_advanced_router
from routers.deposits import router as deposits_router
from routers.setups import router as setups_router
from routers.broker import router as broker_router
from routers.real_pnl import router as real_pnl_router  # PR 12: восстановлен
from routers.positions import router as positions_router  # PR 12: новый
from routers.accounts import router as accounts_router
from routers.review import router as review_router
from routers.replay import router as replay_router
from routers.payments import router as payments_router
from routers.onboarding import router as onboarding_router
from sync_scheduler import scheduler

log = get_logger("api")


def _check_alembic_head() -> None:
    """PR 26: refuse to start если есть pending Alembic миграции.

    В prod схема должна управляться через `alembic upgrade head` ПЕРЕД
    запуском API. Если миграции не применены — модели могут быть несовместимы
    с реальной БД, что приводит к 500-кам в рантайме.
    """
    try:
        from alembic.config import Config
        from alembic.runtime.migration import MigrationContext
        from alembic.script import ScriptDirectory
        from sqlalchemy import create_engine

        alembic_cfg = Config("alembic.ini")
        script = ScriptDirectory.from_config(alembic_cfg)
        head_rev = script.get_current_head()

        engine = create_engine(settings.DATABASE_URL)
        with engine.connect() as conn:
            context = MigrationContext.configure(conn)
            current_rev = context.get_current_revision()

        if current_rev != head_rev:
            raise RuntimeError(
                f"⛔ Alembic schema out of sync: db at {current_rev!r}, "
                f"head is {head_rev!r}. Run `alembic upgrade head` before starting."
            )
        log.info("✅ Alembic head check passed (revision=%s)", current_rev)
    except RuntimeError:
        raise
    except Exception:
        log.exception("alembic head check failed (non-blocking in dev)")


def _warn_if_debug() -> None:
    """API-12: предупреждаем на старте если DEBUG=true (НЕ для продакшна)."""
    if settings.DEBUG:
        log.warning(
            "⚠️ DEBUG=true — НЕ для продакшна (traceback'и gated на DEBUG, "
            "но проверь окружение перед деплоем)"
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: startup and shutdown events."""
    log.info("🚀 ATOM API v0.2.0 Starting...")
    log.info("📦 Routers: auth, trades, deposits, setups, broker, admin, blog, stats, market, real_pnl, positions")
    _warn_if_debug()

    # Sentry — раньше всего, чтобы стартовые ошибки тоже доезжали.
    init_sentry()
    # AU10 Phase 4b: блокируем third-party Sentry-init (t-tech-investments
    # ErrorHub автоматически зовёт sentry_sdk.init с DSN error-hub.tbank.ru).
    # Должно идти ПОСЛЕ нашего init_sentry — наш Hub уже создан, фильтр
    # подменяет sentry_sdk.init для последующих вызовов.
    block_third_party_sentry_init()

    if settings.AUTO_INIT_DB:
        database.init_db()
        log.warning("⚠️ AUTO_INIT_DB enabled: database schema ensured via SQLAlchemy create_all()")
    else:
        log.info("🗄️ AUTO_INIT_DB disabled: expecting schema to be managed via migrations")
        # PR 26: в prod проверяем что Alembic on head; иначе схема может быть
        # рассогласована с моделями → ranking time bombs.
        if not settings.DEBUG:
            _check_alembic_head()

    await scheduler.start()
    log.info("🔄 Auto-sync scheduler started")

    # Sprint 1A: краткий readiness-снимок (тип БД, наличие Redis, роль воркера).
    from worker_role import is_scheduler_worker
    import database as _db
    log.info(
        "🩺 Readiness: db=%s redis=%s scheduler_worker=%s",
        "postgres" if _db.IS_POSTGRES else "sqlite" if _db.IS_SQLITE else "other",
        "set" if settings.REDIS_URL else "MISSING",
        is_scheduler_worker(),
    )

    # AU-stream Phase 1+: запускаем real-time stream tasks для connections
    # с stream_enabled=True. Cursor-based polling продолжает работать для
    # всех connections как catch-up + safety net.
    # SYNC-01: stream-consumers — singleton-фоновая работа. Без этого гарда
    # они стартуют на КАЖДОМ gunicorn-воркере → N×500 gRPC-стримов →
    # IP-cooldown T-Bank в первую минуту мульти-воркер деплоя.
    # (is_scheduler_worker уже импортирован выше для readiness-лога.)
    if is_scheduler_worker():
        try:
            from application.sync.stream_manager import stream_manager
            started = await stream_manager.start_all_enabled()
            if started > 0:
                log.info("📡 Stream consumers started: %d", started)
        except Exception:
            log.exception("Failed to start stream_manager (non-blocking)")
    else:
        log.info("⏭️ Stream consumers skipped on this worker (IS_SCHEDULER_WORKER=false)")

    yield
    log.info("🛑 ATOM API shutting down...")
    # Stream первым — он держит долгоживущие gRPC соединения; даём им
    # graceful shutdown ДО того как scheduler.stop() закроет connections.
    try:
        from application.sync.stream_manager import stream_manager
        await stream_manager.stop_all(timeout_s=10.0)
    except Exception:
        log.exception("Failed to stop stream_manager (non-blocking)")
    await scheduler.stop()
    # PERF-04: закрываем общий httpx.AsyncClient для MOEX (services/moex_async).
    # Идемпотентно: если ни одного запроса не было, no-op.
    try:
        from services import moex_async
        await moex_async.close_client()
    except Exception:
        log.exception("Failed to close moex_async client (non-blocking)")
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

# ==================== OBSERVABILITY: PROMETHEUS /metrics ====================
# INFRA-02: prometheus-fastapi-instrumentator оборачивает app, регистрирует
# `/metrics` (text/plain exposition) для Grafana stack scraping.
#
# Регистрация ДО `SlowAPIMiddleware` — чтобы:
#   1) Сам endpoint попадал в маршрутизатор раньше middleware-стека;
#   2) Мы могли пометить роут exempt в `limiter._exempt_routes` ДО того, как
#      slowapi начнёт читать default_limits на первый запрос.
#
# /metrics exempt-фактоид: Prometheus scrape (15s интервал = 4 req/min) сам по
# себе под default_limit=120/min не падает, НО за minute-окно слетают здоровья
# по health-check'ам Grafana, ServiceMonitor recheck'ам и т.п. Лучше exempt'нуть
# явно, чтобы scraper жил независимо от user-RPS.
from prometheus_fastapi_instrumentator import Instrumentator

_instrumentator = Instrumentator(
    excluded_handlers=["/metrics", "/health", "/ready"],
    should_group_status_codes=False,
    should_ignore_untemplated=True,
)
_instrumentator.instrument(app).expose(
    app,
    endpoint="/metrics",
    include_in_schema=False,
    tags=["observability"],
)
# Exempt из slowapi rate-limit: имя callable, которое expose() регистрирует
# на роуте /metrics, — `<module>.<func>` = "prometheus_fastapi_instrumentator
# .instrumentation.metrics". Добавляем напрямую в `_exempt_routes` (set),
# т.к. сам декоратор limiter.exempt применять некуда (endpoint регистрируется
# внутри библиотеки императивно).
for _route in app.routes:
    if getattr(_route, "path", None) == "/metrics":
        _endpoint = getattr(_route, "endpoint", None)
        if _endpoint is not None:
            _exempt_key = f"{_endpoint.__module__}.{_endpoint.__name__}"
            limiter._exempt_routes.add(_exempt_key)
        break


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

# API-03: SlowAPIMiddleware применяет default_limits (READ_RATE_LIMIT) ко ВСЕМ
# роутам без явного @limiter.limit. Добавлен ПЕРВЫМ → innermost, чтобы 429
# проходил обратно через CORS + SecurityHeaders (получает их заголовки).
# Probe-роуты (/health, /ready, /) помечены @limiter.exempt, чтобы оркестратор
# не упирался в лимит. В Starlette первым добавленный middleware = outermost
# в списке, но build_middleware_stack оборачивает reversed → innermost.
app.add_middleware(SlowAPIMiddleware)

# PR 26: security headers — outermost, чтобы покрыть ВСЕ ответы (включая
# 4xx/5xx от CSRF/Auth middleware ниже). В Starlette первым добавленный
# middleware = outermost layer.
app.add_middleware(SecurityHeadersMiddleware)

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
    expose_headers=["X-Request-ID", "X-Process-Time", "X-Total-Count"],
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
app.include_router(stats_tags_router, prefix="/stats")
app.include_router(stats_advanced_router)  # уже имеет prefix="/stats"
app.include_router(tags_router)
app.include_router(market_router)
app.include_router(real_pnl_router)  # PR 12
app.include_router(positions_router)  # PR 12
app.include_router(accounts_router)
app.include_router(review_router)
app.include_router(replay_router)
app.include_router(payments_router)
app.include_router(onboarding_router)  # PR 26 Phase 3: reconciliation wizard

# ==================== СТАТИЧЕСКИЕ ФАЙЛЫ ====================
# Создаём папку uploads если её нет
uploads_dir = Path("uploads/screenshots")
uploads_dir.mkdir(parents=True, exist_ok=True)

# Монтируем папку uploads для отдачи скриншотов
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

# ==================== ДОКУМЕНТАЦИЯ ====================
#
# PR 26: /docs, /redoc, /openapi.json доступны ТОЛЬКО при DEBUG=true.
# В prod они возвращают 404 — иначе любой может увидеть полную карту
# внутренних endpoints, схем, валидаций (помогает атакующим).

from fastapi import HTTPException


def _docs_guard() -> None:
    if not settings.DEBUG:
        raise HTTPException(status_code=404)


@app.get("/docs", include_in_schema=False)
async def custom_swagger_ui_html():
    """Swagger UI с поддержкой HTTPS прокси (Codespaces). Гейтится за DEBUG."""
    _docs_guard()
    return get_swagger_ui_html(
        openapi_url=app.openapi_url,
        title=app.title + " - Swagger UI",
        oauth2_redirect_url=app.swagger_ui_oauth2_redirect_url,
        swagger_js_url="https://unpkg.com/swagger-ui-dist@5/swagger-ui-bundle.js",
        swagger_css_url="https://unpkg.com/swagger-ui-dist@5/swagger-ui.css",
    )


@app.get("/redoc", include_in_schema=False)
async def redoc_html():
    """ReDoc документация. Гейтится за DEBUG."""
    _docs_guard()
    return get_redoc_html(
        openapi_url=app.openapi_url,
        title=app.title + " - ReDoc",
        redoc_js_url="https://unpkg.com/redoc@next/bundles/redoc.standalone.js",
    )


# openapi.json тоже надо защитить — иначе схема доступна напрямую.
_original_openapi = app.openapi


def _gated_openapi():
    if not settings.DEBUG:
        raise HTTPException(status_code=404)
    return _original_openapi()


app.openapi = _gated_openapi


# ==================== КОРНЕВЫЕ ENDPOINTS ====================

@app.get("/")
@limiter.exempt
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
@limiter.exempt
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
@limiter.exempt
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
        try:
            import redis as redis_lib  # local import — opt-out если пакета нет
            client = redis_lib.from_url(settings.REDIS_URL, socket_connect_timeout=2, socket_timeout=2)
            redis_ok = bool(client.ping())
        except Exception as exc:
            # Деталь (внутренний host:port) — только в серверный лог, НЕ в тело
            # ответа: /ready неаутентифицирован, str(exc) даёт recon-подсказку.
            log.warning("readiness redis check failed: %s", exc)
        checks["redis"] = {"ok": redis_ok}
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
