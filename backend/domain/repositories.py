"""
Protocol-интерфейсы репозиториев. Используются:

* Application-слоем (orchestrator, fifo_matching) — чтобы не зависеть от
  SQLAlchemy / asyncpg / drivers.
* Тестами — для подмены реальных репозиториев на in-memory fakes.

Реализации живут в `adapters/persistence/*` (PR 5+). Здесь — только
контракт.

Используем `typing.Protocol` (а не ABC), потому что:
* Не нужно явное наследование — любой класс с подходящими методами проходит.
* Поддерживается structural subtyping при mypy / pyright.
* Легче делать fake'и в тестах — обычный класс без `extends`.
"""

from __future__ import annotations

from datetime import datetime
from typing import Iterable, Optional, Protocol, Sequence

from domain.entities import Instrument, Operation, Position, Trade


class OperationRepository(Protocol):
    """UPSERT по `(account_id, instrument_uid, operation_id)`. Идемпотентен."""

    async def upsert_many(self, operations: Sequence[Operation]) -> int:
        """Вставить новые / обновить существующие операции. Возвращает кол-во затронутых."""
        ...

    async def get_last_cursor(self, account_id: str) -> Optional[str]:
        """Курсор последней успешной синхронизации (для OperationsByCursor)."""
        ...

    async def save_cursor(self, account_id: str, cursor: str) -> None:
        """Сохранить cursor после успешной транзакции."""
        ...

    async def fetch_for_instrument(
        self,
        account_id: str,
        instrument_uid: str,
        *,
        since: Optional[datetime] = None,
    ) -> list[Operation]:
        """Все операции по инструменту в хронологическом порядке."""
        ...


class TradeRepository(Protocol):
    """Хранилище FIFO-сматченных сделок."""

    async def replace_for_instrument(
        self,
        account_id: str,
        instrument_uid: str,
        trades: Sequence[Trade],
    ) -> None:
        """Перезаписать все Trade-записи по инструменту (новый snapshot из FIFO).

        Заметка: если бы мы делали инкрементальное обновление, пришлось бы
        диффить trades по operation_ids — это сложнее и подвержено багам.
        Replace-стратегия безопаснее для PR 5 MVP.
        """
        ...

    async def list_by_account(
        self,
        account_id: str,
        *,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
        limit: int = 1000,
        offset: int = 0,
    ) -> list[Trade]:
        ...


class PositionRepository(Protocol):
    """Текущие открытые позиции (mark-to-market)."""

    async def upsert(self, position: Position) -> None:
        ...

    async def upsert_many(self, positions: Iterable[Position]) -> int:
        ...

    async def get(self, account_id: str, instrument_uid: str) -> Optional[Position]:
        ...

    async def list_by_account(self, account_id: str) -> list[Position]:
        ...

    async def delete_zero_quantity(self, account_id: str) -> int:
        """Удалить позиции с quantity=0 (для уборки после закрытия)."""
        ...


class InstrumentRepository(Protocol):
    """Кэш справочника. UID — primary key."""

    async def upsert(self, instrument: Instrument) -> None:
        ...

    async def upsert_many(self, instruments: Iterable[Instrument]) -> int:
        ...

    async def get_by_uid(self, uid: str) -> Optional[Instrument]:
        ...

    async def get_many_by_uids(self, uids: Iterable[str]) -> dict[str, Instrument]:
        ...


class TokenRepository(Protocol):
    """Зашифрованные брокерские токены + audit log (PR 4).

    Здесь только контракт; реализация AESGCM-шифрования — в
    `adapters/security/token_encryption.py`.
    """

    async def store(self, account_id: str, plaintext: str, *, scope: str = "read-only") -> None:
        ...

    async def get_decrypted(self, account_id: str) -> Optional[str]:
        ...

    async def deactivate(self, account_id: str, reason: str) -> None:
        ...

    async def log_usage(
        self,
        *,
        account_id: str,
        method: str,
        endpoint: str,
        status_code: int,
        latency_ms: int,
    ) -> None:
        """Запись в token_audit_log без сохранения самого токена."""
        ...
