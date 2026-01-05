"""
OAuth State Store — хранилище состояний для OAuth-авторизации.

Поддерживает:
1. Redis (для production) — рекомендуется
2. In-memory dict (для разработки) — fallback

Для production установите REDIS_URL в переменных окружения:
    REDIS_URL=redis://localhost:6379/0
"""

import os
import time
from typing import Optional, Any
from logger import get_logger

log = get_logger("oauth_store")

# Время жизни state в секундах (10 минут)
STATE_TTL = 600


class BaseStateStore:
    """Базовый интерфейс хранилища"""
    
    def set(self, state: str, provider: str, ttl: int = STATE_TTL) -> None:
        raise NotImplementedError
    
    def get(self, state: str) -> Optional[str]:
        raise NotImplementedError
    
    def delete(self, state: str) -> None:
        raise NotImplementedError
    
    def validate_and_delete(self, state: str, expected_provider: str) -> bool:
        """Проверить state и удалить его. Возвращает True если валидный."""
        provider = self.get(state)
        if provider is None or provider != expected_provider:
            return False
        self.delete(state)
        return True


class InMemoryStateStore(BaseStateStore):
    """
    In-memory хранилище для разработки.
    ⚠️ Не использовать в production с несколькими воркерами!
    """
    
    def __init__(self):
        self._store: dict[str, tuple[str, float]] = {}
        log.warning("⚠️ Using in-memory OAuth state store. Not suitable for production!")
    
    def set(self, state: str, provider: str, ttl: int = STATE_TTL) -> None:
        expires_at = time.time() + ttl
        self._store[state] = (provider, expires_at)
        self._cleanup()
    
    def get(self, state: str) -> Optional[str]:
        self._cleanup()
        item = self._store.get(state)
        if item is None:
            return None
        provider, expires_at = item
        if time.time() > expires_at:
            del self._store[state]
            return None
        return provider
    
    def delete(self, state: str) -> None:
        self._store.pop(state, None)
    
    def _cleanup(self) -> None:
        """Удалить истёкшие записи"""
        now = time.time()
        expired = [k for k, (_, exp) in self._store.items() if now > exp]
        for k in expired:
            del self._store[k]


class RedisStateStore(BaseStateStore):
    """
    Redis-хранилище для production.
    Поддерживает несколько воркеров и автоматическое истечение.
    """
    _client: Any  # redis.Redis
    
    def __init__(self, redis_url: str):
        try:
            import redis  # type: ignore[import-not-found]
            self._client = redis.from_url(redis_url, decode_responses=True)
            # Проверяем соединение
            self._client.ping()
            log.info(f"✅ Connected to Redis for OAuth state storage")
        except ImportError:
            raise RuntimeError("Redis package not installed. Run: pip install redis")
        except Exception as e:
            raise RuntimeError(f"Failed to connect to Redis: {e}")
    
    def set(self, state: str, provider: str, ttl: int = STATE_TTL) -> None:
        self._client.setex(f"oauth_state:{state}", ttl, provider)
    
    def get(self, state: str) -> Optional[str]:
        return self._client.get(f"oauth_state:{state}")
    
    def delete(self, state: str) -> None:
        self._client.delete(f"oauth_state:{state}")


def create_state_store() -> BaseStateStore:
    """
    Создать хранилище состояний.
    Использует Redis если REDIS_URL задан, иначе in-memory.
    """
    redis_url = os.getenv("REDIS_URL")
    
    if redis_url:
        try:
            return RedisStateStore(redis_url)
        except RuntimeError as e:
            log.error(f"Failed to init Redis store: {e}. Falling back to in-memory.")
    
    return InMemoryStateStore()


# Глобальный экземпляр
_store: Optional[BaseStateStore] = None


def get_state_store() -> BaseStateStore:
    """Получить singleton экземпляр хранилища"""
    global _store
    if _store is None:
        _store = create_state_store()
    return _store
