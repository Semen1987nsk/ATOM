# mypy: disable-error-code="arg-type,assignment"

"""
OperationRepository — sync UPSERT-репозиторий для таблицы `operations`.

Главный приём — batch UPSERT через `INSERT ... ON CONFLICT DO UPDATE`.
SQLite (3.24+) и PostgreSQL имеют это API через `sqlalchemy.dialects.*.insert`.
Идемпотентен: повторный sync с тем же cursor'ом просто обновит `synced_at`
у существующих записей и не вставит дубликатов.

`get_last_cursor` / `save_cursor` хранят cursor в `BrokerConnection.sync_cursor`
(поле добавлено в PR 2). Сохранение cursor'а — в одной транзакции с UPSERT
операций, чтобы при падении посередине не потерять progress.

Контракт для PR 5 pipeline (см. application/sync/pipeline.py): репозиторий
sync, вызывается из async кода через `asyncio.to_thread`.

Type-checker note: см. instrument_repo.py — тот же legacy SQLAlchemy стиль.
"""

from __future__ import annotations

from datetime import datetime
from typing import Iterable, Optional, Sequence

from sqlalchemy.orm import Session

from domain.entities import Operation
from domain.enums import InstrumentType, OperationState, OperationType
from domain.value_objects import MoneyValue
from logger import get_logger
from models import BrokerConnection, OperationORM
from utils.datetime_utils import utc_now_naive

log = get_logger("operation_repo")

# Чанкование UPSERT.
# SQLite по умолчанию SQLITE_MAX_VARIABLE_NUMBER=999 (в новых билдах 32766).
# PostgreSQL — bind parameter limit 65535. Используем консервативные значения.
# На колонку у нас ~25 параметров, поэтому батчи берём с запасом:
_UPSERT_CHUNK_SIZE_SQLITE = 30
_UPSERT_CHUNK_SIZE_POSTGRES = 500


# ── module-level helpers (используются и при upsert, и при чтении) ────


def _enum_value(maybe_enum) -> Optional[str]:
    """domain enum → строковое значение, безопасно к None."""
    if maybe_enum is None:
        return None
    return getattr(maybe_enum, "value", str(maybe_enum))


def _money_to_columns(m: Optional[MoneyValue], prefix: str) -> dict:
    """`MoneyValue` → три колонки {prefix}_units/_nano/_currency."""
    if m is None:
        return {f"{prefix}_units": None, f"{prefix}_nano": None, f"{prefix}_currency": None}
    return {
        f"{prefix}_units": m.units,
        f"{prefix}_nano": m.nano,
        f"{prefix}_currency": m.currency,
    }


def _columns_to_money(units, nano, currency) -> Optional[MoneyValue]:
    if units is None and nano is None and not currency:
        return None
    return MoneyValue(
        units=int(units or 0),
        nano=int(nano or 0),
        currency=currency or "",
    )


def _operation_to_row(
    *,
    account_id: int,
    broker_account_id: str,
    op: Operation,
    synced_at: datetime,
) -> dict:
    return {
        "account_id": account_id,
        "broker_account_id": broker_account_id,
        "operation_id": op.operation_id,
        "parent_operation_id": op.parent_operation_id,
        "instrument_uid": op.instrument_uid,
        "instrument_figi": op.instrument_figi,
        "instrument_type": _enum_value(op.instrument_type),
        "operation_type": op.operation_type.value,
        "state": op.state.value,
        "quantity": op.quantity or 0,
        **_money_to_columns(op.price, "price"),
        **_money_to_columns(op.payment, "payment"),
        **_money_to_columns(op.commission, "commission"),
        **_money_to_columns(op.asset_uid_aci, "aci"),
        "executed_at": op.executed_at.replace(tzinfo=None) if op.executed_at.tzinfo else op.executed_at,
        "description": (op.description[:512] if op.description else None),
        "synced_at": synced_at,
    }


def _row_to_operation(row: OperationORM) -> Operation:
    """ORM row → domain Operation."""
    return Operation(
        operation_id=row.operation_id,
        parent_operation_id=row.parent_operation_id,
        account_id=row.broker_account_id,
        instrument_uid=row.instrument_uid,
        instrument_figi=row.instrument_figi,
        instrument_type=(
            InstrumentType(row.instrument_type)
            if row.instrument_type and row.instrument_type in {it.value for it in InstrumentType}
            else None
        ),
        operation_type=OperationType(row.operation_type)
        if row.operation_type in {ot.value for ot in OperationType}
        else OperationType.UNSPECIFIED,
        state=OperationState(row.state)
        if row.state in {s.value for s in OperationState}
        else OperationState.UNSPECIFIED,
        quantity=row.quantity or 0,
        price=_columns_to_money(row.price_units, row.price_nano, row.price_currency),
        payment=_columns_to_money(row.payment_units, row.payment_nano, row.payment_currency),
        commission=_columns_to_money(row.commission_units, row.commission_nano, row.commission_currency),
        asset_uid_aci=_columns_to_money(row.aci_units, row.aci_nano, row.aci_currency),
        executed_at=row.executed_at if row.executed_at.tzinfo else row.executed_at.replace(tzinfo=__import__("datetime").timezone.utc),
        description=row.description,
        trades_id=None,
    )


# ── репозиторий ───────────────────────────────────────────────────────


class OperationRepository:
    """Sync-реализация. См. module docstring."""

    # Колонки, обновляемые при UPSERT (всё кроме PK и неизменяемого
    # account_id/broker_account_id/operation_id).
    _UPDATABLE_COLS = (
        "parent_operation_id",
        "instrument_uid",
        "instrument_figi",
        "instrument_type",
        "operation_type",
        "state",
        "quantity",
        "price_units",
        "price_nano",
        "price_currency",
        "payment_units",
        "payment_nano",
        "payment_currency",
        "commission_units",
        "commission_nano",
        "commission_currency",
        "aci_units",
        "aci_nano",
        "aci_currency",
        "executed_at",
        "description",
        "synced_at",
    )

    def upsert_many(
        self,
        session: Session,
        *,
        account_id: int,
        broker_account_id: str,
        operations: Sequence[Operation],
    ) -> int:
        """Вставить или обновить пачку операций. Возвращает кол-во обработанных.

        Чанкуем по диалекту: SQLite имеет жёсткий лимит параметров на запрос
        (~999 по умолчанию). Поймал live-тест с 3216 операциями × 25 столбцов.
        """
        if not operations:
            return 0

        now = utc_now_naive()
        rows = [
            _operation_to_row(
                account_id=account_id,
                broker_account_id=broker_account_id,
                op=op,
                synced_at=now,
            )
            for op in operations
        ]

        dialect = session.bind.dialect.name if session.bind else "sqlite"
        chunk_size = (
            _UPSERT_CHUNK_SIZE_POSTGRES
            if dialect == "postgresql"
            else _UPSERT_CHUNK_SIZE_SQLITE
        )

        for start in range(0, len(rows), chunk_size):
            chunk = rows[start : start + chunk_size]
            stmt = self._build_upsert_stmt(chunk, dialect=dialect)
            session.execute(stmt)
        return len(rows)

    def _build_upsert_stmt(self, rows: list[dict], *, dialect: str):
        if dialect == "postgresql":
            from sqlalchemy.dialects.postgresql import insert as pg_insert

            stmt = pg_insert(OperationORM).values(rows)
        else:
            from sqlalchemy.dialects.sqlite import insert as sqlite_insert

            stmt = sqlite_insert(OperationORM).values(rows)

        updateable = {
            col: getattr(stmt.excluded, col) for col in self._UPDATABLE_COLS
        }
        return stmt.on_conflict_do_update(
            index_elements=["account_id", "operation_id"],
            set_=updateable,
        )

    def get_last_cursor(
        self, session: Session, *, account_id: int, broker_account_id: str
    ) -> Optional[str]:
        """Курсор предыдущей успешной синхронизации (для OperationsByCursor)."""
        conn = (
            session.query(BrokerConnection)
            .filter(
                BrokerConnection.account_id == account_id,
                BrokerConnection.broker_account_id == broker_account_id,
                BrokerConnection.is_active.is_(True),
            )
            .first()
        )
        return conn.sync_cursor if conn else None

    def save_cursor(
        self,
        session: Session,
        *,
        account_id: int,
        broker_account_id: str,
        cursor: str,
        last_sync_status: str = "success",
        last_sync_error: Optional[str] = None,
    ) -> None:
        """
        Сохранить cursor + статус. Выполняется в той же транзакции что и
        `upsert_many`, иначе теряется progress при падении посередине.
        """
        conn = (
            session.query(BrokerConnection)
            .filter(
                BrokerConnection.account_id == account_id,
                BrokerConnection.broker_account_id == broker_account_id,
                BrokerConnection.is_active.is_(True),
            )
            .first()
        )
        if conn is None:
            log.warning(
                f"save_cursor: no active BrokerConnection for account_id={account_id} "
                f"broker_account_id={broker_account_id} — cursor not saved"
            )
            return
        conn.sync_cursor = cursor
        conn.last_sync_at = utc_now_naive()
        conn.last_sync_status = last_sync_status
        conn.last_sync_error = last_sync_error
        if last_sync_status == "success":
            conn.consecutive_failures = 0
            conn.circuit_open_until = None

    # ── чтение ────────────────────────────────────────────────────────

    def fetch_for_instrument(
        self,
        session: Session,
        *,
        account_id: int,
        instrument_uid: str,
        since: Optional[datetime] = None,
    ) -> list[Operation]:
        """Хронологически отсортированные операции по инструменту (для FIFO в PR 7).

        Отфильтровываем `state='canceled'`: это отменённые ордера от Tinkoff,
        они НЕ должны влиять на позицию или PnL. До фильтра FIFO считал такие
        операции как настоящие сделки → ошибочные Trade с неверным знаком и
        невозможные проценты (например OZON +369% от отменённого buy с
        положительным payment'ом).
        """
        query = session.query(OperationORM).filter(
            OperationORM.account_id == account_id,
            OperationORM.instrument_uid == instrument_uid,
            OperationORM.state != "canceled",
        )
        if since is not None:
            query = query.filter(OperationORM.executed_at >= since)
        rows = query.order_by(OperationORM.executed_at.asc()).all()
        return [_row_to_operation(r) for r in rows]

    def count_by_account(self, session: Session, *, account_id: int) -> int:
        """Сколько всего операций сохранено по счёту — для дашборда и smoke."""
        return (
            session.query(OperationORM)
            .filter(OperationORM.account_id == account_id)
            .count()
        )

    def get_max_executed_at(
        self,
        session: Session,
        *,
        account_id: int,
        broker_account_id: Optional[str] = None,
    ) -> Optional[datetime]:
        """Самая свежая executed_at для аккаунта — точка отсечения для cursor fallback (AU3).

        Используется когда сохранённый cursor «застрял» (API отдаёт пустой
        ответ при non-empty cursor): pipeline переключается с cursor на
        from_dt = (max_executed_at - 24h) и тянет операции по дате.
        """
        from sqlalchemy import func as sa_func

        query = session.query(sa_func.max(OperationORM.executed_at)).filter(
            OperationORM.account_id == account_id,
        )
        if broker_account_id is not None:
            query = query.filter(OperationORM.broker_account_id == broker_account_id)
        return query.scalar()

    def list_unique_instrument_uids(
        self, session: Session, *, account_id: int
    ) -> list[str]:
        """Уникальные UID для bootstrap instrument cache (PR 6)."""
        rows = (
            session.query(OperationORM.instrument_uid)
            .filter(
                OperationORM.account_id == account_id,
                OperationORM.instrument_uid.isnot(None),
            )
            .distinct()
            .all()
        )
        return [r[0] for r in rows if r[0]]
