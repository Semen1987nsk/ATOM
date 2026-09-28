"""
Database connection and session management.

Поддерживает SQLite (разработка) и PostgreSQL (продакшен).
"""
import os
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool, QueuePool, NullPool

# Импорт моделей для создания таблиц
import models
from config import settings

# ==================== КОНФИГУРАЦИЯ ====================

SQLALCHEMY_DATABASE_URL = settings.DATABASE_URL

# Определяем тип базы данных
IS_SQLITE = SQLALCHEMY_DATABASE_URL.startswith("sqlite")
IS_POSTGRES = SQLALCHEMY_DATABASE_URL.startswith("postgresql")


def _assert_db_safe_for_env(url: str, debug: bool) -> None:
    """PERF-01: SQLite не годится для прод-нагрузки (single writer, нет WAL
    durability под конкуренцией). В проде (DEBUG=false) требуем Postgres."""
    if url.startswith("sqlite") and not debug:
        raise RuntimeError(
            "\n🚨 FATAL: SQLite запрещён в production (DEBUG=false).\n"
            "   SQLite = один писатель → 'database is locked' под нагрузкой.\n"
            "   Установите DATABASE_URL=postgresql://user:pass@host:5432/db"
        )


# ==================== НАСТРОЙКА ENGINE ====================

def create_db_engine():
    """
    Создаёт engine с оптимальными настройками для типа БД.
    """
    _assert_db_safe_for_env(SQLALCHEMY_DATABASE_URL, settings.DEBUG)
    if IS_SQLITE:
        # SQLite + FastAPI + background tasks: NullPool (connection per checkout).
        # StaticPool разделяет ОДНУ connection между всеми потоками →
        # sqlite3.InterfaceError при race между HTTP requests и scheduler/stream_manager.
        # Для in-memory SQLite (тесты) StaticPool оставляем через ?cache=shared.
        is_memory = ":memory:" in SQLALCHEMY_DATABASE_URL
        return create_engine(
            SQLALCHEMY_DATABASE_URL,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool if is_memory else NullPool,
            echo=os.getenv("SQL_ECHO", "false").lower() == "true",
        )
    
    elif IS_POSTGRES:
        # PostgreSQL: connection pooling для продакшена
        return create_engine(
            SQLALCHEMY_DATABASE_URL,
            poolclass=QueuePool,
            pool_size=int(os.getenv("DB_POOL_SIZE", "5")),
            max_overflow=int(os.getenv("DB_MAX_OVERFLOW", "10")),
            pool_timeout=int(os.getenv("DB_POOL_TIMEOUT", "30")),
            pool_recycle=int(os.getenv("DB_POOL_RECYCLE", "1800")),  # 30 минут
            pool_pre_ping=True,  # Проверка соединения перед использованием
            echo=os.getenv("SQL_ECHO", "false").lower() == "true",
        )
    
    else:
        # Другие БД (MySQL, etc.)
        return create_engine(
            SQLALCHEMY_DATABASE_URL,
            pool_pre_ping=True,
            echo=os.getenv("SQL_ECHO", "false").lower() == "true",
        )


engine = create_db_engine()

# ==================== SESSION FACTORY ====================

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
    expire_on_commit=False,  # Не инвалидировать объекты после commit
)


# ==================== ИНИЦИАЛИЗАЦИЯ БД ====================

def init_db():
    """
    Инициализация базы данных.
    
    В продакшене рекомендуется использовать Alembic миграции вместо create_all().
    Эта функция подходит для:
    - Локальной разработки
    - Тестирования
    - Первоначального развертывания
    """
    # Создаём все таблицы, которых ещё нет
    models.Base.metadata.create_all(bind=engine)


# Для SQLite: включаем foreign keys (регистрируем ОДИН раз на уровне модуля)
if IS_SQLITE:
    _sqlite_is_memory = ":memory:" in SQLALCHEMY_DATABASE_URL

    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        if not _sqlite_is_memory:
            # WAL снижает писатель-блокировки в dev; busy_timeout вместо мгновенного
            # 'database is locked'. Для :memory: (тесты) WAL неприменим.
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()


def drop_all_tables():
    """
    Удаление всех таблиц. ОПАСНО! Только для тестов.
    """
    if os.getenv("ALLOW_DROP_TABLES", "false").lower() != "true":
        raise RuntimeError("drop_all_tables() blocked. Set ALLOW_DROP_TABLES=true to enable.")
    
    models.Base.metadata.drop_all(bind=engine)


# ==================== DEPENDENCY ДЛЯ FASTAPI ====================

def get_db() -> Generator[Session, None, None]:
    """
    Dependency для получения сессии БД в эндпоинтах FastAPI.
    
    Использование:
        @app.get("/items")
        def get_items(db: Session = Depends(get_db)):
            return db.query(Item).all()
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def get_db_session() -> Generator[Session, None, None]:
    """
    Context manager для использования вне FastAPI (скрипты, тесты).
    
    Использование:
        with get_db_session() as db:
            users = db.query(User).all()
    """
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


# ==================== HEALTH CHECK ====================

def check_db_connection() -> bool:
    """
    Проверка подключения к БД.
    
    Returns:
        True если подключение успешно, False иначе.
    """
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


def get_db_info() -> dict:
    """
    Информация о подключении к БД.
    """
    return {
        "database_type": "sqlite" if IS_SQLITE else "postgresql" if IS_POSTGRES else "other",
        "url_masked": SQLALCHEMY_DATABASE_URL.split("@")[-1] if "@" in SQLALCHEMY_DATABASE_URL else SQLALCHEMY_DATABASE_URL,
        "pool_size": engine.pool.size() if hasattr(engine.pool, 'size') else 1,
        "connected": check_db_connection(),
    }
