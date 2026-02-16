"""
Конфигурация приложения — настройки из переменных окружения.

Единственный источник правды для всех секретов и настроек.
Все модули ДОЛЖНЫ импортировать настройки отсюда:
    from config import settings
"""

import os
import warnings
import secrets
from pathlib import Path
from typing import List

from dotenv import load_dotenv

# Загружаем .env из директории backend/ (где лежит config.py).
# override=False — переменные окружения ОС имеют приоритет над .env.
_env_path = Path(__file__).resolve().parent / ".env"
load_dotenv(_env_path, override=False)


def _parse_cors_origins() -> List[str]:
    """Парсинг CORS origins из переменной окружения"""
    origins_env = os.getenv("CORS_ORIGINS", "")
    
    if origins_env == "*":
        return ["*"]
    
    if origins_env:
        return [origin.strip() for origin in origins_env.split(",") if origin.strip()]
    
    # Defaults for development
    return [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]


def _resolve_secret_key() -> str:
    """
    Единственная точка загрузки SECRET_KEY.
    
    - В production (DEBUG=false): ОБЯЗАТЕЛЕН через переменную окружения.
    - В development (DEBUG=true): используется сгенерированный dev-ключ с предупреждением.
    """
    key = os.getenv("SECRET_KEY") or os.getenv("JWT_SECRET_KEY")
    is_debug = os.getenv("DEBUG", "false").lower() == "true"
    
    if key:
        # Проверяем на плейсхолдеры
        weak_markers = ("change", "default", "placeholder", "example", "test", "dev-key")
        if any(marker in key.lower() for marker in weak_markers):
            warnings.warn(
                "\n⚠️  SECRET_KEY appears to be a default/placeholder value.\n"
                "   Generate a strong key: python -c 'import secrets; print(secrets.token_urlsafe(64))'",
                UserWarning,
                stacklevel=2
            )
        return key
    
    # Ключ НЕ задан
    if not is_debug:
        raise RuntimeError(
            "\n🚨 FATAL: SECRET_KEY is not set!\n"
            "   In production mode (DEBUG != true), SECRET_KEY MUST be set as an environment variable.\n"
            "   Generate one with: python -c 'import secrets; print(secrets.token_urlsafe(64))'\n"
            "   Then set: export SECRET_KEY='your-generated-key'"
        )
    
    # Dev mode: генерируем ключ для сессии
    dev_key = secrets.token_urlsafe(64)
    warnings.warn(
        "\n⚠️  SECRET_KEY not set — using auto-generated dev key.\n"
        "   This key changes on every restart. Sessions will be invalidated.\n"
        "   Set SECRET_KEY env var for persistent sessions in development.",
        UserWarning,
        stacklevel=2
    )
    return dev_key


class Settings:
    """Настройки приложения из переменных окружения"""
    
    # ==================== APP ====================
    APP_NAME: str = os.getenv("APP_NAME", "ATOM API")
    APP_VERSION: str = os.getenv("APP_VERSION", "0.2.0")
    DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"
    
    # ==================== SECURITY ====================
    # Единственный источник SECRET_KEY для всего приложения
    SECRET_KEY: str = _resolve_secret_key()
    REFRESH_SECRET_KEY: str = os.getenv("REFRESH_SECRET_KEY", SECRET_KEY + "_refresh_v2")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
    REFRESH_TOKEN_EXPIRE_DAYS: int = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))
    
    # ==================== DATABASE ====================
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./atom.db")
    
    # ==================== REDIS ====================
    REDIS_URL: str = os.getenv("REDIS_URL", "")
    
    # ==================== CORS ====================
    # Разделённый запятыми список origins, или * для разрешения всех
    CORS_ORIGINS: List[str] = _parse_cors_origins()
    CORS_ALLOW_CREDENTIALS: bool = True
    CORS_ORIGIN_REGEX: str = os.getenv("CORS_ORIGIN_REGEX", r"https://.*\.app\.github\.dev")
    
    # ==================== LOGGING ====================
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    LOG_FORMAT: str = os.getenv("LOG_FORMAT", "%(asctime)s - %(name)s - %(levelname)s - %(message)s")


# Глобальный экземпляр настроек
settings = Settings()
