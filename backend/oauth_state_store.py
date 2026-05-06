"""
OAuth State Store — хранилище состояний для OAuth-авторизации.

Поддерживает:
1. Redis (для production) — рекомендуется
2. In-memory dict (для разработки) — fallback

Для production установите REDIS_URL в переменных окружения:
    REDIS_URL=redis://localhost:6379/0

В production (DEBUG=false) Redis ОБЯЗАТЕЛЕН — иначе fail-fast
при создании стора. In-memory под несколько воркеров приведёт к
рассинхронизации state и обходу CSRF-защиты OAuth.
"""

import json
import os
import time
from dataclasses import asdict, dataclass
from typing import Optional, Any
from logger import get_logger
from config import settings

log = get_logger("oauth_store")

# Время жизни state в секундах (10 минут)
STATE_TTL = 600


@dataclass
class StateRecord:
    """
    Запись OAuth-state.

    Расширена под PKCE: храним code_verifier рядом со state, чтобы
    в callback-handler'е можно было передать его в token-exchange.
    """
    provider: str
    code_verifier: Optional[str] = None  # PKCE; None для legacy/без PKCE


def _serialize(record: StateRecord) -> str:
    return json.dumps(asdict(record), ensure_ascii=False)


def _deserialize(raw: Optional[str]) -> Optional[StateRecord]:
    if raw is None:
        return None
    # Backward-compat: если в Redis уже лежит «голая» строка-провайдер из старого формата.
    if not raw.startswith("{"):
        return StateRecord(provider=raw)
    try:
        data = json.loads(raw)
        return StateRecord(
            provider=data.get("provider"),
            code_verifier=data.get("code_verifier"),
        )
    except Exception:
        return None


class BaseStateStore:
    """Базовый интерфейс хранилища"""

    def set(self, state: str, provider: str, ttl: int = STATE_TTL,
            code_verifier: Optional[str] = None) -> None:
        raise NotImplementedError

    def get(self, state: str) -> Optional[StateRecord]:
        raise NotImplementedError

    def delete(self, state: str) -> None:
        raise NotImplementedError

    def consume(self, state: str, expected_provider: str) -> Optional[StateRecord]:
        """
        Атомарно: проверить state, убедиться что provider совпадает, удалить
        и вернуть запись (включая code_verifier для PKCE).

        Возвращает None если state невалиден / не совпал / истёк.
        """
        record = self.get(state)
        if record is None or record.provider != expected_provider:
            return None
        self.delete(state)
        return record

    # Legacy-метод — оставляем для обратной совместимости с auth.py
    def validate_and_delete(self, state: str, expected_provider: str) -> bool:
        return self.consume(state, expected_provider) is not None


class InMemoryStateStore(BaseStateStore):
    """
    In-memory хранилище для разработки.
    ⚠️ Не использовать в production с несколькими воркерами!
    """

    def __init__(self):
        self._store: dict[str, tuple[StateRecord, float]] = {}
        log.warning("⚠️ Using in-memory OAuth state store. Not suitable for production!")

    def set(self, state: str, provider: str, ttl: int = STATE_TTL,
            code_verifier: Optional[str] = None) -> None:
        expires_at = time.time() + ttl
        self._store[state] = (StateRecord(provider=provider, code_verifier=code_verifier), expires_at)
        self._cleanup()

    def get(self, state: str) -> Optional[StateRecord]:
        self._cleanup()
        item = self._store.get(state)
        if item is None:
            return None
        record, expires_at = item
        if time.time() > expires_at:
            del self._store[state]
            return None
        return record

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

    def set(self, state: str, provider: str, ttl: int = STATE_TTL,
            code_verifier: Optional[str] = None) -> None:
        record = StateRecord(provider=provider, code_verifier=code_verifier)
        self._client.setex(f"oauth_state:{state}", ttl, _serialize(record))

    def get(self, state: str) -> Optional[StateRecord]:
        raw = self._client.get(f"oauth_state:{state}")
        return _deserialize(raw)

    def delete(self, state: str) -> None:
        self._client.delete(f"oauth_state:{state}")


def create_state_store() -> BaseStateStore:
    """
    Создать хранилище состояний.

    Использует Redis если REDIS_URL задан. В DEBUG=false (production):
    - Если REDIS_URL пуст ИЛИ Redis недоступен → fail-fast.
      In-memory store с несколькими воркерами молчаливо ломает CSRF-защиту OAuth.
    - В DEBUG=true допустим fallback на in-memory с громким warning.
    """
    redis_url = os.getenv("REDIS_URL")

    if redis_url:
        try:
            return RedisStateStore(redis_url)
        except RuntimeError as e:
            if not settings.DEBUG:
                raise RuntimeError(
                    f"OAuth state store: Redis недоступен в production ({e}). "
                    "Multi-worker setup без Redis = обход CSRF-защиты OAuth. "
                    "Поправь REDIS_URL или временно DEBUG=true."
                )
            log.error(f"Failed to init Redis store: {e}. Falling back to in-memory (DEBUG mode).")

    if not settings.DEBUG:
        raise RuntimeError(
            "OAuth state store: REDIS_URL не задан в production. "
            "В multi-worker setup in-memory store ломает CSRF-защиту. "
            "Либо задай REDIS_URL, либо DEBUG=true для разработки."
        )

    return InMemoryStateStore()


# Глобальный экземпляр
_store: Optional[BaseStateStore] = None


def get_state_store() -> BaseStateStore:
    """Получить singleton экземпляр хранилища"""
    global _store
    if _store is None:
        _store = create_state_store()
    return _store
