"""
Конфигурация приложения — настройки из переменных окружения.
"""

import os
from typing import List


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


class Settings:
    """Настройки приложения из переменных окружения"""
    
    # ==================== APP ====================
    APP_NAME: str = os.getenv("APP_NAME", "ATOM API")
    APP_VERSION: str = os.getenv("APP_VERSION", "0.2.0")
    DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"
    
    # ==================== SECURITY ====================
    SECRET_KEY: str = os.getenv("SECRET_KEY", os.getenv("JWT_SECRET_KEY", ""))
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "10080"))
    
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
