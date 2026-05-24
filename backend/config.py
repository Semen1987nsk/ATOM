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


def _resolve_refresh_secret_key(access_secret: str) -> str:
    """
    Загружает REFRESH_SECRET_KEY.

    - В production ОБЯЗАТЕЛЬНО задавать отдельной env-переменной.
    - Раньше fallback был `SECRET_KEY + "_refresh_v2"` — это не отдельный
      ключ, а derivative: компрометация одного компрометирует оба.
    - В DEBUG-режиме разрешаем deterministic fallback с громким warning,
      чтобы dev-сессии не инвалидировались на каждом рестарте.
    """
    key = os.getenv("REFRESH_SECRET_KEY")
    is_debug = os.getenv("DEBUG", "false").lower() == "true"

    if key:
        if key == access_secret:
            raise RuntimeError(
                "🚨 FATAL: REFRESH_SECRET_KEY MUST be different from SECRET_KEY."
            )
        return key

    if not is_debug:
        raise RuntimeError(
            "\n🚨 FATAL: REFRESH_SECRET_KEY is not set!\n"
            "   In production REFRESH_SECRET_KEY MUST be set as a SEPARATE env-var,\n"
            "   not derived from SECRET_KEY (single-key compromise risk).\n"
            "   Generate one with: python -c 'import secrets; print(secrets.token_urlsafe(64))'"
        )

    warnings.warn(
        "\n⚠️  REFRESH_SECRET_KEY not set — using auto-generated dev key.\n"
        "   This key changes on every restart. Refresh sessions will be invalidated.\n"
        "   Set REFRESH_SECRET_KEY env var (DIFFERENT from SECRET_KEY) for persistence.",
        UserWarning,
        stacklevel=2,
    )
    return secrets.token_urlsafe(64)


def _resolve_auto_init_db() -> bool:
    """Определяет, можно ли автоматически создавать таблицы при старте."""
    auto_init = os.getenv("AUTO_INIT_DB")
    if auto_init is not None:
        return auto_init.lower() == "true"

    is_debug = os.getenv("DEBUG", "false").lower() == "true"
    return is_debug


class Settings:
    """Настройки приложения из переменных окружения"""
    
    # ==================== APP ====================
    APP_NAME: str = os.getenv("APP_NAME", "ATOM API")
    APP_VERSION: str = os.getenv("APP_VERSION", "0.2.0")
    DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"
    
    # ==================== SECURITY ====================
    # Единственный источник SECRET_KEY для всего приложения
    SECRET_KEY: str = _resolve_secret_key()
    REFRESH_SECRET_KEY: str = _resolve_refresh_secret_key(SECRET_KEY)
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
    REFRESH_TOKEN_EXPIRE_DAYS: int = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))
    # bcrypt cost factor: 14 даёт ~250ms на современном CPU и защищает от GPU-bruteforce.
    # 12 (default) уже неприемлемо для финансового SaaS в 2026.
    BCRYPT_ROUNDS: int = int(os.getenv("BCRYPT_ROUNDS", "14"))
    # Лимит размера файла на импорт сделок (защита от xlsx-bomb / DoS).
    MAX_UPLOAD_SIZE_MB: int = int(os.getenv("MAX_UPLOAD_SIZE_MB", "10"))
    ACCESS_TOKEN_COOKIE_NAME: str = os.getenv("ACCESS_TOKEN_COOKIE_NAME", "atom_access_token")
    REFRESH_TOKEN_COOKIE_NAME: str = os.getenv("REFRESH_TOKEN_COOKIE_NAME", "atom_refresh_token")
    CSRF_COOKIE_NAME: str = os.getenv("CSRF_COOKIE_NAME", "atom_csrf_token")
    CSRF_HEADER_NAME: str = os.getenv("CSRF_HEADER_NAME", "X-CSRF-Token")
    AUTH_COOKIE_DOMAIN: str | None = os.getenv("AUTH_COOKIE_DOMAIN") or None
    AUTH_COOKIE_PATH: str = os.getenv("AUTH_COOKIE_PATH", "/")
    AUTH_COOKIE_SAMESITE: str = os.getenv("AUTH_COOKIE_SAMESITE", "lax")
    AUTH_COOKIE_SECURE: bool = os.getenv("AUTH_COOKIE_SECURE", "true" if os.getenv("DEBUG", "false").lower() != "true" else "false").lower() == "true"
    
    # ==================== DATABASE ====================
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./atom.db")
    AUTO_INIT_DB: bool = _resolve_auto_init_db()
    
    # ==================== REDIS ====================
    REDIS_URL: str = os.getenv("REDIS_URL", "")
    RATE_LIMIT_ENABLED: bool = os.getenv("RATE_LIMIT_ENABLED", "true").lower() == "true"
    RATE_LIMIT_STORAGE_URI: str = os.getenv("RATE_LIMIT_STORAGE_URI", os.getenv("REDIS_URL", ""))
    RATE_LIMIT_STRATEGY: str = os.getenv("RATE_LIMIT_STRATEGY", "fixed-window")
    
    # ==================== CORS ====================
    # Разделённый запятыми список origins, или * для разрешения всех
    CORS_ORIGINS: List[str] = _parse_cors_origins()
    CORS_ALLOW_CREDENTIALS: bool = True
    CORS_ORIGIN_REGEX: str = os.getenv("CORS_ORIGIN_REGEX", r"https://.*\.app\.github\.dev")
    
    # ==================== LOGGING ====================
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    LOG_FORMAT: str = os.getenv("LOG_FORMAT", "%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    # text — человекочитаемый (dev), json — для агрегаторов (prod)
    LOG_FORMAT_MODE: str = os.getenv("LOG_FORMAT_MODE", "text").lower()
    ENABLE_FILE_LOGGING: bool = os.getenv("ENABLE_FILE_LOGGING", "true").lower() == "true"
    LOG_DIR: str = os.getenv("LOG_DIR", str(Path(__file__).resolve().parent.parent / "logs"))

    # ==================== OBSERVABILITY (Sentry) ====================
    # Если SENTRY_DSN пуст — Sentry не инициализируется (нет внешних отправок).
    SENTRY_DSN: str = os.getenv("SENTRY_DSN", "")
    SENTRY_ENVIRONMENT: str = os.getenv("SENTRY_ENVIRONMENT", "production")
    SENTRY_TRACES_SAMPLE_RATE: float = float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.05"))
    SENTRY_RELEASE: str = os.getenv("SENTRY_RELEASE", "")

    # ==================== INTEGRATIONS ====================
    OAUTH_HTTP_TIMEOUT_SECONDS: float = float(os.getenv("OAUTH_HTTP_TIMEOUT_SECONDS", "15"))
    OPEN_POSITION_SYNC_LOOKBACK_DAYS: int = int(os.getenv("OPEN_POSITION_SYNC_LOOKBACK_DAYS", "30"))

    # ==================== BROKER SYNC V2 (greenfield Tinkoff rewrite) ====================
    # PR 0..16: пока флаг выключен, новый sync не запущен, старый удалён → broker
    # endpoints возвращают 503, scheduler — no-op. Включаем когда PR 5+ готовы.
    BROKER_SYNC_V2_ENABLED: bool = os.getenv("BROKER_SYNC_V2_ENABLED", "false").lower() == "true"

    # gRPC endpoints из официальной доки T-Bank Developer
    # (https://developer.tbank.ru/invest/intro/connection).
    # Sandbox-инстанс зеркален prod, выдаёт отдельные токены через UI Тинькофф.
    TINKOFF_API_ENDPOINT: str = os.getenv(
        "TINKOFF_API_ENDPOINT", "invest-public-api.tinkoff.ru:443"
    )
    TINKOFF_SANDBOX_ENDPOINT: str = os.getenv(
        "TINKOFF_SANDBOX_ENDPOINT", "sandbox-invest-public-api.tinkoff.ru:443"
    )
    # "prod" | "sandbox" — выбирает endpoint и режим работы (sandbox-методы
    # имеют отдельный namespace в SDK).
    TINKOFF_API_ENV: str = os.getenv("TINKOFF_API_ENV", "prod").lower()
    # App name отправляется в gRPC metadata; Тинькофф просит указывать в формате
    # "вендор.приложение" для отслеживания grade и issue-репортов.
    TINKOFF_APP_NAME: str = os.getenv("TINKOFF_APP_NAME", "empirik.journal")
    # Per-token rate-limit cap (запас от официальных 200/min для Operations).
    TINKOFF_RATE_LIMIT_PER_MIN: int = int(os.getenv("TINKOFF_RATE_LIMIT_PER_MIN", "60"))

    # ==================== TOKEN ENCRYPTION (PR 4) ====================
    # 32 байта в base64 — мастер-ключ AES-256-GCM. В prod ОБЯЗАТЕЛЕН.
    # В DEBUG-режиме допустима пустая строка (encryption-сервис подменит на
    # ephemeral dev-ключ с громким warning).
    MASTER_KEY_B64: str = os.getenv("MASTER_KEY_B64", "")
    # ID текущего ключа. При ротации — увеличиваем, прежний key_id остаётся
    # доступным для расшифровки старых записей через MASTER_KEY_<N>_B64.
    MASTER_KEY_ID: int = int(os.getenv("MASTER_KEY_ID", "1"))

    # ==================== PROXY / IP ====================
    # Comma-separated list of trusted proxy IPs/CIDRs.
    # X-Forwarded-For will ONLY be trusted from these sources.
    # Empty = trust no proxy (use socket IP directly).
    TRUSTED_PROXIES: List[str] = [
        p.strip() for p in os.getenv("TRUSTED_PROXIES", "").split(",") if p.strip()
    ]


# Глобальный экземпляр настроек
settings = Settings()
