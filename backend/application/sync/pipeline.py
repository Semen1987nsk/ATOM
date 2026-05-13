"""
SyncPipeline — 5 идемпотентных стадий синхронизации одного аккаунта.

Стадии (см. план PR 5):

1. **fetch**         — паджинация `OperationsByCursor` от последнего курсора.
2. **enrich**        — для новых `instrument_uid` подгрузить справочник
                       через `instruments_client.get_instrument_by_uid()`
                       и сохранить в БД (`InstrumentRepository`).
3. **fifo_match**    — заглушка в PR 5. PR 7 поднимет FIFO-движок и заполнит
                       `trades` и `positions`.
4. **upsert**        — одной транзакцией: операции в `operations`,
                       обновление `sync_cursor`+`last_sync_at`.
5. **emit_events**   — заглушка в PR 5. PR 8 повесит handler'ы (пересчёт
                       позиций, уведомление пользователю).

Идемпотентность критична: pipeline может прерваться на любой стадии,
повторный запуск с тем же входом не должен порождать дубликаты или
несоответствия (`save_cursor` идёт в одной транзакции с `upsert_many`).

Архитектура:

* `TinkoffOperationsClient` / `TinkoffInstrumentsClient` — gRPC-клиенты,
  принимают готовый `services` объект (PR 3 контракт).
* `OperationRepository` / `InstrumentRepository` — sync SQLAlchemy.
  Вызываем их через `asyncio.to_thread()`, чтобы не блокировать event loop.
* `client_factory.async_client(token)` открывает gRPC-канал на время одного
  pipeline-вызова. Pool на токен не используем — каждый sync открывает
  свой канал. Это проще и для polling-режима (раз в 5-60 мин) — не критично.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from sqlalchemy import func
from datetime import datetime
from decimal import Decimal
from time import monotonic
from typing import Optional, Sequence

from sqlalchemy.orm import Session

from adapters.observability.sync_context import (
    bind_sync_context,
    clear_sync_context,
)
from adapters.persistence.instrument_repo import InstrumentRepository
from adapters.persistence.operation_repo import OperationRepository
from adapters.persistence.position_repo import PositionRepository
from adapters.persistence.trade_repo import TradeRepository
from adapters.tinkoff.client_factory import client_factory
from adapters.tinkoff.instruments_client import TinkoffInstrumentsClient
from adapters.tinkoff.marketdata_client import TinkoffMarketDataClient
from adapters.tinkoff.operations_client import TinkoffOperationsClient
from application.fifo_matching import DEFAULT_CALCULATORS, FIFOMatchingService
from database import SessionLocal
from domain.entities import Instrument, Operation, Trade
from domain.exceptions import BrokerError, InstrumentNotFound
from logger import get_logger
from utils.datetime_utils import utc_now_naive

log = get_logger("sync.pipeline")


# ── data classes ──────────────────────────────────────────────────────


@dataclass
class SyncReport:
    """Итог одного pipeline-прогона. Используется orchestrator'ом для
    обновления статуса BrokerConnection."""

    account_id: int
    broker_account_id: str
    started_at: datetime
    finished_at: Optional[datetime] = None
    operations_total: int = 0
    operations_new_or_updated: int = 0
    instruments_resolved: int = 0
    pages_fetched: int = 0
    last_cursor: Optional[str] = None
    trades_built: int = 0
    positions_open: int = 0
    # PR 9: варм-маржа аккумулируется по счёту, Tinkoff не привязывает её
    # к конкретному фьючерсу через uid/figi. Поэтому общий итог идёт
    # account-level метрикой (показываем в UI как «Realized varmargin» отдельно).
    account_varmargin_total: Decimal = field(default_factory=lambda: Decimal(0))
    success: bool = False
    error_type: Optional[str] = None
    error_message: Optional[str] = None
    duration_sec: float = 0.0

    @property
    def stale_started(self) -> datetime:
        return self.started_at


# ── pipeline ──────────────────────────────────────────────────────────


class SyncPipeline:
    """
    Один pipeline на один `(account_id, broker_account_id, token)`.
    Создаётся orchestrator'ом и живёт ровно одну sync-итерацию.
    """

    def __init__(
        self,
        *,
        account_id: int,
        broker_account_id: str,
        token_plaintext: str,
        operation_repo: Optional[OperationRepository] = None,
        instrument_repo: Optional[InstrumentRepository] = None,
        trade_repo: Optional[TradeRepository] = None,
        position_repo: Optional[PositionRepository] = None,
        fifo_service: Optional[FIFOMatchingService] = None,
        session_factory=None,
        page_size: int = 1000,
        # PR 6 поднимет до 100+; пока ограничиваем, чтобы один pipeline
        # не упёрся в Tinkoff RPS на enrich-стадии для активных трейдеров.
        max_instruments_per_run: int = 50,
    ) -> None:
        self._account_id = account_id
        self._broker_account_id = broker_account_id
        self._token = token_plaintext
        self._operation_repo = operation_repo or OperationRepository()
        self._instrument_repo = instrument_repo or InstrumentRepository()
        self._trade_repo = trade_repo or TradeRepository()
        self._position_repo = position_repo or PositionRepository()
        self._fifo_service = fifo_service or FIFOMatchingService()
        self._session_factory = session_factory or SessionLocal
        self._page_size = page_size
        self._max_instruments_per_run = max_instruments_per_run

    # ── public API ────────────────────────────────────────────────────

    async def run(self, *, full_sync: bool = False) -> SyncReport:
        """
        Полный sync для аккаунта.

        `full_sync=True` — игнорируем сохранённый cursor и берём с начала.
        Используется при первом подключении и в команде «пересинхронизировать
        историю» из UI (PR 13).

        PR 16: bind_sync_context — все log-записи внутри получают sync_id,
        account_hash, broker_account_id. Sentry breadcrumbs/issues тоже.
        """
        import uuid

        report = SyncReport(
            account_id=self._account_id,
            broker_account_id=self._broker_account_id,
            started_at=utc_now_naive(),
        )
        started_mono = monotonic()
        ctx_tokens = bind_sync_context(
            sync_id=uuid.uuid4().hex[:12],
            account_id=self._account_id,
            broker_account_id=self._broker_account_id,
        )

        try:
            initial_cursor = "" if full_sync else (await self._get_initial_cursor() or "")
            fetched_operations, last_cursor, pages = await self._stage_fetch(initial_cursor)
            report.pages_fetched = pages
            report.operations_total = len(fetched_operations)
            report.last_cursor = last_cursor

            resolved = await self._stage_enrich(fetched_operations)
            report.instruments_resolved = resolved

            # PR 4: upsert operations + save cursor (раньше). Сейчас сначала
            # сохраняем операции в БД, чтобы FIFO мог комбинировать новые
            # с уже хранящимися (для incremental sync).
            inserted = await self._stage_upsert(fetched_operations, last_cursor)
            report.operations_new_or_updated = inserted

            # PR 7: FIFO matching по каждому инструменту, сохранение Trade/Position.
            trades, positions = await self._stage_fifo_match(fetched_operations)
            report.trades_built = trades
            report.positions_open = positions

            # PR 9: account-level варм-маржа (varmargin не привязан к
            # инструменту в API). Считаем по ВСЕЙ истории операций счёта.
            report.account_varmargin_total = await asyncio.to_thread(
                self._compute_account_varmargin
            )

            # PR 11: mark-to-market открытых позиций.
            await self._stage_mark_to_market()

            # PR 8 — emit OperationsSyncedEvent. Сейчас no-op.
            await self._stage_emit_events(report)

            report.success = True
        except BrokerError as exc:
            report.error_type = type(exc).__name__
            report.error_message = exc.message
            # Сохраняем статус ошибки на BrokerConnection даже если
            # успели зафетчить операции — orchestrator решит как retry.
            await asyncio.to_thread(self._save_error_state, exc)
            raise
        except Exception as exc:
            report.error_type = type(exc).__name__
            report.error_message = str(exc)
            log.exception("pipeline failed unexpectedly")
            await asyncio.to_thread(self._save_error_state, exc)
            raise
        finally:
            report.finished_at = utc_now_naive()
            report.duration_sec = round(monotonic() - started_mono, 3)
            clear_sync_context(ctx_tokens)

        log.info(
            "sync.pipeline.done",
            extra={
                "account_id": self._account_id,
                "operations_total": report.operations_total,
                "instruments_resolved": report.instruments_resolved,
                "duration_sec": report.duration_sec,
            },
        )
        return report

    # ── stages ────────────────────────────────────────────────────────

    async def _get_initial_cursor(self) -> Optional[str]:
        def _get() -> Optional[str]:
            session = self._session_factory()
            try:
                return self._operation_repo.get_last_cursor(
                    session,
                    account_id=self._account_id,
                    broker_account_id=self._broker_account_id,
                )
            finally:
                session.close()

        return await asyncio.to_thread(_get)

    async def _stage_fetch(
        self, cursor: str
    ) -> tuple[list[Operation], str, int]:
        """Шаг 1: тянем все страницы операций от `cursor` до конца."""
        all_ops: list[Operation] = []
        pages = 0
        current = cursor
        async with client_factory.async_client(self._token) as services:
            ops_client = TinkoffOperationsClient(services)
            while True:
                page, next_cursor = await ops_client.fetch_operations_cursor(
                    self._broker_account_id,
                    cursor=current,
                    limit=self._page_size,
                )
                pages += 1
                all_ops.extend(page)
                # Финал — пустой next_cursor.
                if not next_cursor or next_cursor == current:
                    return all_ops, next_cursor or current, pages
                current = next_cursor
                # Безопасность — лимит страниц чтобы не зациклиться.
                if pages >= 1000:
                    log.warning(
                        "fetch reached page limit 1000 for account_id=%s",
                        self._account_id,
                    )
                    return all_ops, current, pages

    async def _stage_enrich(self, operations: Sequence[Operation]) -> int:
        """Шаг 2: подгрузить недостающие инструменты в кэш."""
        unique_uids = self._extract_unique_uids(operations)
        if not unique_uids:
            return 0

        def _missing() -> list[str]:
            session = self._session_factory()
            try:
                return self._instrument_repo.missing_uids(session, unique_uids)
            finally:
                session.close()

        missing = await asyncio.to_thread(_missing)
        if not missing:
            return 0

        targets = missing[: self._max_instruments_per_run]
        log.info(
            f"enrich: {len(missing)} missing instruments, resolving {len(targets)}"
        )

        async with client_factory.async_client(self._token) as services:
            instruments_client = TinkoffInstrumentsClient(services)
            resolved = []
            for uid in targets:
                try:
                    inst = await instruments_client.get_instrument_by_uid(uid)
                    resolved.append(inst)
                except InstrumentNotFound:
                    log.warning(f"enrich: instrument {uid} not found, skipping")
                except BrokerError as exc:
                    log.warning(f"enrich: {uid}: {type(exc).__name__} — {exc.message}")

        if resolved:
            def _persist() -> None:
                session = self._session_factory()
                try:
                    self._instrument_repo.upsert_many(session, resolved)
                    session.commit()
                finally:
                    session.close()

            await asyncio.to_thread(_persist)
        return len(resolved)

    async def _stage_fifo_match(
        self, operations: Sequence[Operation]
    ) -> tuple[int, int]:
        """
        Шаг 3 (PR 7): FIFO-матчинг по каждому затронутому инструменту.

        Берём полный набор операций по инструменту из БД (включая ранее
        сохранённые), плюс открытые лоты из `positions.extra.lots`, и
        пересчитываем закрытые сделки. Сохраняем как замену
        (`data_source='tinkoff_v2'`).

        Возвращает (total_trades_built, total_positions_open).
        """
        affected_uids = self._extract_unique_uids(operations)
        if not affected_uids:
            return 0, 0

        def _run_for_one(uid: str) -> tuple[int, int]:
            session = self._session_factory()
            try:
                # Снимок справочника.
                instrument = self._instrument_repo.get_by_uid(session, uid)
                if instrument is None:
                    return 0, 0

                # Полный набор операций по инструменту (для replace-стратегии).
                all_ops = self._operation_repo.fetch_for_instrument(
                    session,
                    account_id=self._account_id,
                    instrument_uid=uid,
                )
                # Лоты из позиции — если есть.
                existing_lots = self._position_repo.get_open_lots(
                    session,
                    account_id=self._account_id,
                    instrument_uid=uid,
                )

                # При replace-стратегии не используем existing_lots, чтобы
                # избежать двойного счёта (мы и так берём ВСЕ операции
                # инструмента из БД). PR 8+ возможно перейдёт к
                # incremental-режиму — тогда лоты будут использоваться.
                result = self._fifo_service.match(
                    account_id=self._account_id,
                    instrument=instrument,
                    operations=all_ops,
                    existing_open_lots=(),
                )

                # Replace trades.
                self._trade_repo.replace_for_instrument(
                    session,
                    account_id=self._account_id,
                    instrument_uid=uid,
                    trades=result.closed_trades,
                )
                # Save position (или удалить если пусто).
                self._position_repo.save(
                    session,
                    account_id=self._account_id,
                    instrument_uid=uid,
                    instrument_type=instrument.instrument_type,
                    open_lots=result.open_lots,
                    currency=(result.open_lots[0].currency if result.open_lots else "rub"),
                )
                session.commit()
                positions_open = 1 if result.open_lots else 0
                return len(result.closed_trades), positions_open
            except Exception:
                session.rollback()
                log.exception("fifo_match failed for uid=%s", uid)
                return 0, 0
            finally:
                session.close()

        total_trades = 0
        total_positions = 0
        for uid in affected_uids:
            trades, positions = await asyncio.to_thread(_run_for_one, uid)
            total_trades += trades
            total_positions += positions

        log.info(
            "fifo_match: instruments=%d trades=%d open_positions=%d",
            len(affected_uids),
            total_trades,
            total_positions,
        )
        return total_trades, total_positions

    async def _stage_upsert(
        self, operations: Sequence[Operation], cursor: str
    ) -> int:
        """Шаг 4: одна транзакция — операции + cursor."""

        def _commit() -> int:
            session = self._session_factory()
            try:
                inserted = self._operation_repo.upsert_many(
                    session,
                    account_id=self._account_id,
                    broker_account_id=self._broker_account_id,
                    operations=operations,
                )
                self._operation_repo.save_cursor(
                    session,
                    account_id=self._account_id,
                    broker_account_id=self._broker_account_id,
                    cursor=cursor,
                    last_sync_status="success",
                    last_sync_error=None,
                )
                session.commit()
                return inserted
            except Exception:
                session.rollback()
                raise
            finally:
                session.close()

        return await asyncio.to_thread(_commit)

    async def _stage_emit_events(self, report: SyncReport) -> None:
        """Шаг 5 — заглушка для PR 5. PR 8 поднимет in-process event bus."""
        return

    async def _stage_mark_to_market(self) -> None:
        """
        PR 11: для каждой открытой позиции получить current price и обновить
        `Position.current_price`, `unrealized_pnl`, `last_priced_at`.

        Один батч-вызов `get_last_prices(uids)` — щадящий по rate-limit
        (600/min для Quotes) и кэшированный 60 сек.
        """
        positions = await asyncio.to_thread(self._list_open_positions)
        if not positions:
            return

        uids = [p["instrument_uid"] for p in positions]
        async with client_factory.async_client(self._token) as services:
            md = TinkoffMarketDataClient(services)
            try:
                prices = await md.get_last_prices(uids)
            except BrokerError as exc:
                log.warning(
                    "mark_to_market: get_last_prices failed (%s) — skipping",
                    type(exc).__name__,
                )
                return

        if not prices:
            log.debug("mark_to_market: no prices returned")
            return

        await asyncio.to_thread(self._apply_mtm, positions, prices)

    def _list_open_positions(self) -> list[dict]:
        """Snapshot полей нужных для MTM (вне session)."""
        from models import PositionORM

        session = self._session_factory()
        try:
            rows = (
                session.query(PositionORM)
                .filter(PositionORM.account_id == self._account_id)
                .all()
            )
            return [
                {
                    "id": r.id,
                    "instrument_uid": r.instrument_uid,
                    "instrument_type": r.instrument_type,
                    "quantity": r.quantity,
                    "avg_entry_price": (
                        Decimal(str(r.avg_entry_price)) if r.avg_entry_price is not None else None
                    ),
                    "currency": r.currency,
                }
                for r in rows
            ]
        finally:
            session.close()

    def _apply_mtm(self, positions: list[dict], prices: dict[str, Decimal]) -> None:
        """Обновить current_price и unrealized_pnl в PositionORM."""
        from domain.enums import InstrumentType
        from models import PositionORM

        session = self._session_factory()
        try:
            for p in positions:
                uid = p["instrument_uid"]
                if uid not in prices:
                    continue
                price = prices[uid]
                if p["avg_entry_price"] is None or p["quantity"] == 0:
                    continue

                # Получить instrument для calculator.
                instrument = self._instrument_repo.get_by_uid(session, uid)
                if instrument is None:
                    continue
                calculator = DEFAULT_CALCULATORS.get(
                    instrument.instrument_type
                )
                if calculator is None:
                    continue

                unrealized = calculator.compute_unrealized(
                    instrument=instrument,
                    quantity_signed=p["quantity"],
                    avg_entry_price=p["avg_entry_price"],
                    current_price=price,
                )

                # UPDATE отдельным запросом — мы внутри одной транзакции.
                row = (
                    session.query(PositionORM)
                    .filter_by(id=p["id"])
                    .first()
                )
                if row is None:
                    continue
                row.current_price = price
                row.unrealized_pnl = unrealized
                row.last_priced_at = utc_now_naive()
            session.commit()
        except Exception:
            log.exception("mark_to_market apply failed")
            try:
                session.rollback()
            except Exception:
                pass
        finally:
            session.close()

    def _compute_account_varmargin(self) -> Decimal:
        """
        PR 9: Tinkoff не привязывает варм-маржу к инструменту, она аккумулирована
        по счёту. Считаем общий нетто (accruing - writing_off) за всю историю.

        Возвращается в UI как отдельная account-level метрика «Реализованная
        вариационная маржа» — рядом с body-PnL фьючерсных трейдов.
        """
        from models import OperationORM

        session = self._session_factory()
        try:
            rows = (
                session.query(
                    OperationORM.operation_type,
                    func.sum(OperationORM.payment_units),
                    func.sum(OperationORM.payment_nano),
                )
                .filter(
                    OperationORM.account_id == self._account_id,
                    OperationORM.operation_type.in_(
                        ("accruing_varmargin", "writing_off_varmargin")
                    ),
                    OperationORM.state == "executed",
                )
                .group_by(OperationORM.operation_type)
                .all()
            )
        finally:
            session.close()

        total = Decimal(0)
        for _, sum_units, sum_nano in rows:
            if sum_units is None and sum_nano is None:
                continue
            total += Decimal(int(sum_units or 0)) + Decimal(int(sum_nano or 0)) / Decimal(
                1_000_000_000
            )
        return total

    # ── helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _extract_unique_uids(operations: Sequence[Operation]) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for op in operations:
            if op.instrument_uid and op.instrument_uid not in seen:
                seen.add(op.instrument_uid)
                result.append(op.instrument_uid)
        return result

    # PR 15: circuit breaker thresholds.
    _CIRCUIT_BREAKER_FAIL_MAX = 5
    _CIRCUIT_BREAKER_RESET_MINUTES = 15

    def _save_error_state(self, exc: BaseException) -> None:
        """
        Записать факт ошибки в BrokerConnection (для UI и orchestrator'а).
        PR 15: при 5 ошибках подряд — circuit_open_until = now + 15 минут.
        """
        from datetime import timedelta

        session: Session = self._session_factory()
        try:
            from models import BrokerConnection

            conn = (
                session.query(BrokerConnection)
                .filter(
                    BrokerConnection.account_id == self._account_id,
                    BrokerConnection.broker_account_id == self._broker_account_id,
                    BrokerConnection.is_active.is_(True),
                )
                .first()
            )
            if conn is None:
                return
            conn.last_sync_at = utc_now_naive()
            conn.last_sync_status = "error"
            conn.last_sync_error = f"{type(exc).__name__}: {str(exc)[:400]}"
            conn.consecutive_failures = (conn.consecutive_failures or 0) + 1
            # PR 15: open circuit при достижении лимита.
            if conn.consecutive_failures >= self._CIRCUIT_BREAKER_FAIL_MAX:
                conn.circuit_open_until = utc_now_naive() + timedelta(
                    minutes=self._CIRCUIT_BREAKER_RESET_MINUTES
                )
                log.warning(
                    "circuit breaker OPEN: account_id=%s broker_account_id=%s "
                    "failures=%s until=%s",
                    self._account_id,
                    self._broker_account_id,
                    conn.consecutive_failures,
                    conn.circuit_open_until,
                )
            session.commit()
        except Exception:
            log.exception("failed to record error state")
            try:
                session.rollback()
            except Exception:
                pass
        finally:
            session.close()
