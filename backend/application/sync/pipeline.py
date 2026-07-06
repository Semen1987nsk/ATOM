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
from application.sync.health_audit import (
    SEVERITY_ERROR,
    SyncHealthAuditor,
)
from application.sync.phantom_sweep import close_phantom_trades
from database import SessionLocal
from domain.entities import Instrument, Operation, Trade
from domain.exceptions import BrokerError, InstrumentNotFound
from logger import get_logger
from utils.datetime_utils import utc_now_naive

log = get_logger("sync.pipeline")


def _is_stale_batch(max_in_batch, max_in_db) -> bool:
    """max(executed_at) батча строго старше max в БД (на >1ч) → stale cursor."""
    from datetime import timedelta
    if max_in_db is None or max_in_batch is None:
        return False
    return max_in_batch < max_in_db - timedelta(hours=1)


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
        # PR 20 (health audit): snapshot live position uids после mark_to_market,
        # для сверки с локальной БД в audit-стадии.
        self._last_live_position_uids: Optional[set[str]] = None
        self._auditor = SyncHealthAuditor()
        # PR 21: total_amount_portfolio (рубли) после последнего get_portfolio,
        # для автоподстановки initial_balance.
        self._last_portfolio_total_rub: Optional[Decimal] = None

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
        sync_id = uuid.uuid4().hex[:12]
        self._current_sync_id = sync_id  # PR 20: для health-audit log entry
        ctx_tokens = bind_sync_context(
            sync_id=sync_id,
            account_id=self._account_id,
            broker_account_id=self._broker_account_id,
        )

        # PR 26 Phase 1: SyncEventORM — фиксируем cursor_before до запуска
        # pipeline, чтобы при interrupt'е была запись о попытке.
        initial_cursor = "" if full_sync else (await self._get_initial_cursor() or "")
        sync_event_id = await asyncio.to_thread(
            self._record_sync_event_start, sync_id, initial_cursor
        )

        try:
            fetched_operations, last_cursor, pages = await self._stage_fetch(initial_cursor)
            report.pages_fetched = pages
            report.operations_total = len(fetched_operations)
            report.last_cursor = last_cursor

            resolved = await self._stage_enrich(fetched_operations)
            report.instruments_resolved = resolved

            # PR 4 + SYNC-08 (2026-05-26): upsert operations БЕЗ сдвига курсора.
            # Сначала сохраняем операции в БД, чтобы FIFO мог комбинировать
            # новые с уже хранящимися (для incremental sync). Курсор сдвигается
            # в самом конце через _stage_commit_cursor — только после того как
            # FIFO+positions+health прошли успешно. Иначе при падении на FIFO
            # стадии операции уже сохранены и cursor сдвинут, а trades/positions
            # не построены — следующий sync не сможет довосстановить с прежней
            # точки.
            inserted = await self._stage_upsert(fetched_operations)
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

            # TR1.3: распределение account-level fees (margin_fee, service_fee,
            # generic tax, varmargin без instrument_uid) по trades через
            # proportional time-window attribution. После этого
            # Trade.net_pnl содержит ВСЕ fees, и Σ Trade.net_pnl ≈ cash truth.
            await asyncio.to_thread(self._stage_attribute_fees)

            # PR 11+18: подменить локальные positions реальным портфелем с
            # Tinkoff (источник истины) + проставить current_price/unrealized.
            await self._stage_mark_to_market()
            # Счётчик positions_open для UI: число реальных позиций после
            # live-replace (FIFO-метрика была неточной — корпоративные действия).
            report.positions_open = await asyncio.to_thread(
                self._count_open_positions
            )

            # 2026-05-19: подтянуть ticker/name для UID-ов в живых позициях,
            # которых нет в instrument cache (новые серии фьючерсов / опционы).
            # Без этого UI показывает UUID вместо тикера.
            await self._stage_enrich_position_instruments()

            # Phase (2026-05-19): закрыть phantom open Trades — позиций нет в
            # Position table. Защита от случая когда Tinkoff закрыл позицию,
            # но SELL operation в Operations API задержалась.
            await asyncio.to_thread(self._stage_phantom_sweep)

            # PR 20: deep-audit здоровья импорта. Не падает если sync ОК —
            # просто наблюдение, результат пишется в sync_health_checks.
            await asyncio.to_thread(self._stage_health_audit)

            # ADR-0010: авто-якорь баланса открытия (неполная история депозитов).
            # ДО pnl_health_check, чтобы badge считался с эффективными депозитами.
            await asyncio.to_thread(self._stage_autoset_inferred_anchor)

            # Phase 10 (2026-05-17): P&L Health Check — сверка journal_pnl
            # с cash truth через две независимые методологии. Не блокирует
            # sync (non-fatal), результат кешируется на Account для UI badge.
            await asyncio.to_thread(self._stage_pnl_health_check)

            # PR 8 — emit OperationsSyncedEvent. Сейчас no-op.
            await self._stage_emit_events(report)

            # SYNC-08 (2026-05-26): сдвигаем cursor ТОЛЬКО после успешного
            # прохождения всех post-upsert стадий (fifo_match, attribute_fees,
            # mark_to_market, phantom_sweep, health_audit, pnl_health_check).
            # Если любая из них упала — мы попадаем в except-блок ниже,
            # `_save_error_state` фиксирует last_sync_status="error",
            # а sync_cursor остаётся прежним. На следующем sync с тем же
            # курсором перетянем те же операции (upsert идемпотентен) и заново
            # построим trades/positions.
            await self._stage_commit_cursor(last_cursor)

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
            # PR 17: после успешного sync — записываем счётчики в БД для UI.
            # При exception этот блок не вызывается (success остаётся False),
            # ошибочное состояние уже зафиксировал _save_error_state.
            if report.success:
                await asyncio.to_thread(self._save_sync_details, report)
            # PR 26 Phase 1: финализируем SyncEvent (успех/ошибка/прерывание)
            await asyncio.to_thread(self._record_sync_event_finish, sync_event_id, report)

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

    # ── SyncEventORM helpers (PR 26 Phase 1) ──────────────────────────

    def _record_sync_event_start(self, sync_id: str, cursor_before: str) -> Optional[int]:
        """Создать SyncEventORM запись о начале sync (best-effort)."""
        try:
            from models import SyncEventORM as _SyncEventORM

            session = self._session_factory()
            try:
                row = _SyncEventORM(
                    account_id=self._account_id,
                    broker_account_id=self._broker_account_id,
                    sync_id=sync_id,
                    started_at=utc_now_naive(),
                    status="running",
                    cursor_before=(cursor_before or "")[:256] or None,
                )
                session.add(row)
                session.commit()
                return row.id
            finally:
                session.close()
        except Exception:
            log.exception("record_sync_event_start failed (non-blocking)")
            return None

    def _record_sync_event_finish(self, event_id: Optional[int], report) -> None:
        """Финализировать SyncEvent при завершении pipeline (best-effort)."""
        if event_id is None:
            return
        try:
            from models import SyncEventORM as _SyncEventORM

            session = self._session_factory()
            try:
                row = session.query(_SyncEventORM).filter(_SyncEventORM.id == event_id).first()
                if row is None:
                    return
                row.finished_at = report.finished_at or utc_now_naive()
                if report.duration_sec is not None:
                    row.duration_ms = int(report.duration_sec * 1000)
                if report.success:
                    row.status = "success"
                elif report.error_type:
                    row.status = "failed"
                    row.error_type = (report.error_type or "")[:64] or None
                    row.error_message = (report.error_message or "")[:512] or None
                else:
                    row.status = "interrupted"
                row.cursor_after = (report.last_cursor or "")[:256] or None
                row.pages_fetched = report.pages_fetched or 0
                row.operations_total = report.operations_total or 0
                row.operations_new_or_updated = report.operations_new_or_updated or 0
                row.trades_built = report.trades_built or 0
                row.positions_open = report.positions_open or 0
                session.commit()
            finally:
                session.close()
        except Exception:
            log.exception("record_sync_event_finish failed (non-blocking)")

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

    async def _get_sync_from_date(self):
        """PR 24: возвращает BrokerConnection.sync_from_date (если задан).

        Tinkoff API учитывает `from_dt` только при cursor="" (первый запрос
        пагинации). После этого — отдаёт всю историю до текущего момента.
        Раньше поле было «мёртвым»: сохранялось, но в фильтр не попадало.
        """
        from models import BrokerConnection

        def _get():
            session = self._session_factory()
            try:
                conn = (
                    session.query(BrokerConnection)
                    .filter(BrokerConnection.account_id == self._account_id)
                    .filter(BrokerConnection.is_active.is_(True))
                    .first()
                )
                if conn is None:
                    return None
                # Tinkoff требует timezone-aware datetime в from_/to полях.
                dt = conn.sync_from_date
                if dt is None:
                    return None
                from datetime import timezone

                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt
            finally:
                session.close()

        return await asyncio.to_thread(_get)

    async def _get_max_executed_at(self):
        """AU3: возвращает max(executed_at) операций аккаунта для cursor fallback.

        Используется как опорная точка, когда сохранённый cursor застрял
        (возвращает пустой ответ). На следующем sync переходим с cursor на
        from_dt = (max_executed_at - 1 day) — потеряем ~24h уже-увиденных
        операций, но не потеряем новые. UPSERT идемпотентен, дубликатов нет.
        """
        from datetime import timezone

        def _get():
            session = self._session_factory()
            try:
                dt = self._operation_repo.get_max_executed_at(
                    session,
                    account_id=self._account_id,
                    broker_account_id=self._broker_account_id,
                )
                if dt is None:
                    return None
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt
            finally:
                session.close()

        return await asyncio.to_thread(_get)

    async def _stage_fetch(
        self, cursor: str
    ) -> tuple[list[Operation], str, int]:
        """Шаг 1: тянем все страницы операций от `cursor` до конца.

        PR 24: при cursor="" (full sync) передаём `sync_from_date` как `from_dt`.
        SDK документация говорит: from_dt учитывается только при первом запросе
        (cursor=""). Если у юзера задана дата отсечения — Tinkoff отдаст
        операции только с этой даты, экономя трафик и память.

        AU3: если cursor был не пустой, но первая страница ответа пустая И
        next_cursor совпал с current (зависший cursor) — выполняем fallback:
        cursor="" + from_dt = max(executed_at) − 24h. Это защищает от ситуации,
        когда T-API трактует cursor как пагинационный, а мы используем как
        durable checkpoint между sync-сессиями.
        """
        from datetime import timedelta

        all_ops: list[Operation] = []
        pages = 0
        current = cursor
        from_dt = await self._get_sync_from_date() if not cursor else None
        async with client_factory.async_client(self._token) as services:
            ops_client = TinkoffOperationsClient(services)
            while True:
                page, next_cursor = await ops_client.fetch_operations_cursor(
                    self._broker_account_id,
                    cursor=current,
                    limit=self._page_size,
                    from_dt=from_dt if current == "" else None,
                )
                pages += 1
                all_ops.extend(page)
                # Финал — пустой next_cursor.
                if not next_cursor or next_cursor == current:
                    # AU3+ (2026-05-19): cursor может застрять двумя способами:
                    # (1) Empty-batch: cursor невалиден → не отдаёт ops вообще.
                    # (2) Stale-batch: cursor валиден, но указывает на старую
                    #     точку в потоке — Tinkoff отдаёт N старых ops
                    #     (которые у нас уже в БД дубликатами) и говорит
                    #     next_cursor=None, "история закончилась". При этом
                    #     реальные свежие операции пропускаются.
                    # Оба случая лечатся одинаково: cursor="" + from_dt =
                    # последняя известная дата − 1 день.
                    needs_fallback = False
                    fallback_reason = None
                    if cursor and current == cursor and not all_ops:
                        needs_fallback = True
                        fallback_reason = "empty_batch"
                    elif all_ops:
                        # S2-14: stale-детект БЕЗУСЛОВНО, для любого числа
                        # страниц — многостраничный stale-ответ сдвигает
                        # current, но max(batch) < max(db) всё равно ловит.
                        max_in_batch = max(o.executed_at for o in all_ops)
                        max_in_db = await self._get_max_executed_at()
                        if _is_stale_batch(max_in_batch, max_in_db):
                            needs_fallback = True
                            fallback_reason = "stale_batch_older_than_db"
                            log.warning(
                                "cursor_returned_stale_data",
                                extra={
                                    "account_id": self._account_id,
                                    "stuck_cursor": (cursor or "")[:32],
                                    "batch_max_executed_at": max_in_batch.isoformat(),
                                    "db_max_executed_at": max_in_db.isoformat(),
                                    "ops_returned": len(all_ops),
                                },
                            )
                    if needs_fallback:
                        fallback_anchor = await self._get_max_executed_at()
                        if fallback_anchor is not None:
                            fallback_from = fallback_anchor - timedelta(days=1)
                            log.warning(
                                "cursor_stale_fallback",
                                extra={
                                    "account_id": self._account_id,
                                    "stuck_cursor": (cursor or "")[:32],
                                    "fallback_from": fallback_from.isoformat(),
                                    "reason": fallback_reason,
                                },
                            )
                            # Сбрасываем cursor и идём по from_dt.
                            # Также выбрасываем stale ops чтобы не смешать с
                            # фактически свежими (которые сейчас зафетчим).
                            current = ""
                            from_dt = fallback_from
                            all_ops = []
                            continue  # обратно в while-loop, теперь с cursor=""
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

        log.info(f"enrich: {len(missing)} missing instruments, resolving all in chunks")

        total_resolved = 0
        # S2-07: резолвим ВСЕ missing чанками по max_instruments_per_run —
        # rate-limiter client_factory + IP-cooldown gate защищают RPS. Раньше
        # брали только первый чанк → сделки по инструментам 51+ терялись навсегда.
        for start in range(0, len(missing), self._max_instruments_per_run):
            targets = missing[start : start + self._max_instruments_per_run]
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
                def _persist(_resolved=resolved) -> None:
                    session = self._session_factory()
                    try:
                        self._instrument_repo.upsert_many(session, _resolved)
                        session.commit()
                    finally:
                        session.close()

                await asyncio.to_thread(_persist)
                total_resolved += len(resolved)
        return total_resolved

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

        def _run_for_one(uid: str) -> tuple[int, int, list[int]]:
            session = self._session_factory()
            try:
                # Снимок справочника.
                instrument = self._instrument_repo.get_by_uid(session, uid)
                if instrument is None:
                    # Инструмент не разрешился в enrich (T-Bank NOT_FOUND) —
                    # пропускаем. Возвращаем 3-кортеж как остальные ветки:
                    # caller распаковывает (trades, positions, mae_ids).
                    return 0, 0, []

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

                # Replace trades. Передаём instrument чтобы Trade.symbol получил
                # человекочитаемый ticker (SBER/GAZP) вместо FIFO/UID.
                # T7 fix: добавляем open trades из несматченных лотов, чтобы
                # UI "Open positions" показывал actual entry'ы (раньше open lots
                # жили только в-памяти MatchResult и Trade.exit_at IS NULL
                # таблица была пустой для futures).
                from application.fifo_matching import FIFOMatchingService
                open_trades = FIFOMatchingService.open_trades_from_lots(
                    lots=result.open_lots,
                    instrument=instrument,
                    account_id=self._account_id,
                )
                self._trade_repo.replace_for_instrument(
                    session,
                    account_id=self._account_id,
                    instrument_uid=uid,
                    trades=list(result.closed_trades) + open_trades,
                    instrument=instrument,
                )
                # PR 18: PositionORM здесь больше не сохраняем — открытые позиции
                # будут переписаны live-данными из Tinkoff get_portfolio в
                # _stage_mark_to_market. FIFO-derived open_lots использовался
                # как proxy реального портфеля, но расходился при корпоративных
                # действиях (SECURITY_OUT, переводы между счетами).
                session.commit()
                # MAE-05: свежепересобранные закрытые сделки без MAE/MFE —
                # кандидаты на немедленный backfill. Раньше backfill дёргался
                # только из ручного импорта (/trades/import), а nightly-джоб
                # ограничен 30 днями — сделки из брокерского синка ждали
                # значения до суток, история старше месяца — навсегда.
                from models import Trade as _TradeORM
                need_mae_ids = [
                    row[0]
                    for row in session.query(_TradeORM.id)
                    .filter(
                        _TradeORM.account_id == self._account_id,
                        _TradeORM.instrument_uid == uid,
                        _TradeORM.data_source == "tinkoff_v2",
                        _TradeORM.exit_at.isnot(None),
                        _TradeORM.mae_price.is_(None),
                    )
                    .all()
                ]
                positions_open = len(open_trades)
                return len(result.closed_trades), positions_open, need_mae_ids
            except Exception:
                # S2-08 / SYNC-08: транзиентная ошибка БД (deadlock, IntegrityError
                # от конкурентного sync) НЕ должна молча возвращать 0 — иначе
                # _stage_commit_cursor сдвинет курсор при протухших сделках.
                # Осознанный skip выше — только для instrument is None.
                session.rollback()
                log.exception("fifo_match failed for uid=%s", uid)
                raise
            finally:
                session.close()

        total_trades = 0
        total_positions = 0
        need_backfill: list[int] = []
        for uid in affected_uids:
            trades, positions, mae_ids = await asyncio.to_thread(_run_for_one, uid)
            total_trades += trades
            total_positions += positions
            need_backfill.extend(mae_ids)

        if need_backfill:
            # Lazy-import: import_service тянет market_service/MOEX — не
            # хотим этой зависимости на module-level в sync-пайплайне.
            from import_service import schedule_mae_mfe_backfill

            schedule_mae_mfe_backfill(need_backfill)
            log.info("fifo_match: scheduled MAE/MFE backfill for %d trades", len(need_backfill))

        log.info(
            "fifo_match: instruments=%d trades=%d open_positions=%d",
            len(affected_uids),
            total_trades,
            total_positions,
        )
        return total_trades, total_positions

    async def _stage_upsert(self, operations: Sequence[Operation]) -> int:
        """Шаг 4 (SYNC-08 split): upsert операций БЕЗ сдвига курсора.

        Раньше этот метод коммитил cursor + last_sync_status='success' в той
        же транзакции что и upsert. При падении на FIFO стадии операции были
        сохранены, курсор сдвинут — но trades/positions не построены. На
        следующем sync с уже сдвинутого курсора Tinkoff не отдавал те же ops,
        и FIFO больше никогда не восстанавливался для этого окна.

        Теперь:
        * `_stage_upsert` — атомарный upsert только операций.
        * `_stage_commit_cursor` — отдельный метод, вызывается в конце
          `run()` после всех success-стадий.

        Upsert операций сам по себе идемпотентен (ON CONFLICT DO UPDATE),
        поэтому если курсор не сдвинется и Tinkoff повторно отдаст эти ops —
        ничего не сломается, просто будет no-op UPDATE.
        """

        def _commit() -> int:
            session = self._session_factory()
            try:
                inserted = self._operation_repo.upsert_many(
                    session,
                    account_id=self._account_id,
                    broker_account_id=self._broker_account_id,
                    operations=operations,
                )
                session.commit()
                return inserted
            except Exception:
                session.rollback()
                raise
            finally:
                session.close()

        return await asyncio.to_thread(_commit)

    async def _stage_commit_cursor(self, cursor: str) -> None:
        """SYNC-08: сдвиг cursor + last_sync_status='success'.

        Вызывается ТОЛЬКО после успешного выполнения всех пост-upsert стадий
        (fifo_match, attribute_fees, mark_to_market, phantom_sweep,
        health_audit, pnl_health_check, emit_events). Если любая из них
        бросила исключение — этот метод не вызывается, `_save_error_state`
        фиксирует ошибочный статус, sync_cursor остаётся на предыдущей точке.

        Гарантия: cursor сдвигается только когда trades/positions/health
        соответствуют новому состоянию operations.
        """

        def _save() -> None:
            session = self._session_factory()
            try:
                self._operation_repo.save_cursor(
                    session,
                    account_id=self._account_id,
                    broker_account_id=self._broker_account_id,
                    cursor=cursor,
                    last_sync_status="success",
                    last_sync_error=None,
                )
                session.commit()
            except Exception:
                session.rollback()
                raise
            finally:
                session.close()

        await asyncio.to_thread(_save)

    async def _stage_emit_events(self, report: SyncReport) -> None:
        """Шаг 5 — заглушка для PR 5. PR 8 поднимет in-process event bus."""
        return

    def _stage_health_audit(self) -> None:
        """
        PR 20: deep-audit состояния аккаунта после sync.

        - Запускает SyncHealthAuditor.audit_account
        - Сохраняет HealthReport в sync_health_checks
        - Если severity == 'error' — отправляет Sentry событие с тегами
          account_hash + issue_type
        - Никогда не падает: ошибки только логируются (audit — наблюдение).
        """
        from models import SyncHealthCheckORM

        session = self._session_factory()
        try:
            report = self._auditor.audit_account(
                session,
                account_id=self._account_id,
                broker_account_id=self._broker_account_id,
                sync_id=getattr(self, "_current_sync_id", None),
                live_position_uids=self._last_live_position_uids,
            )
            session.add(SyncHealthCheckORM(**report.to_db_fields()))
            session.commit()
            log.info(
                "health_audit done: account_id=%s status=%s trades_checked=%s issues=%s",
                self._account_id,
                report.status,
                report.total_trades_checked,
                len(report.issues),
            )
            if report.status == SEVERITY_ERROR:
                self._emit_sentry_health_alert(report)
        except Exception:
            log.exception("health_audit failed (non-blocking) account_id=%s", self._account_id)
            try:
                session.rollback()
            except Exception:
                pass
        finally:
            session.close()

    def _stage_phantom_sweep(self) -> None:
        """Phase (2026-05-19): закрыть Trade rows с exit_at=None для которых
        нет matching Position. Tinkoff закрыл позицию, но SELL operation
        ещё не пришла — FIFO matcher остался ни с чем.

        Идемпотентно. Best-effort: ошибки логируются, sync не падает.
        """
        session = self._session_factory()
        try:
            def _pv_for(uid: Optional[str]) -> Decimal:
                if not uid:
                    return Decimal(1)
                return self._get_point_value(session, uid)

            swept_count = close_phantom_trades(
                session=session,
                account_id=int(self._account_id),
                point_value_for=_pv_for,
                now=datetime.utcnow(),
            )
            if swept_count > 0:
                session.commit()
                log.info(
                    "phantom_sweep closed %d trades for acc#%s",
                    swept_count,
                    self._account_id,
                )
        except Exception:
            log.exception(
                "phantom_sweep failed (non-blocking) account_id=%s",
                self._account_id,
            )
            try:
                session.rollback()
            except Exception:
                pass
        finally:
            session.close()

    def _stage_pnl_health_check(self) -> None:
        """Phase 10 (2026-05-17): сверка journal_pnl vs cash_truth.

        Запускается после `_stage_attribute_fees` + `_stage_mark_to_market`,
        когда все Trade.net_pnl и Position.unrealized_pnl актуальные.
        Записывает результат в Account.last_pnl_health_* для UI badge.

        Non-fatal: ошибки только логируются, sync продолжается.
        """
        from services import pnl_health_service

        session = self._session_factory()
        try:
            result = pnl_health_service.compute_and_persist(session, self._account_id)
            log.info(
                "pnl_health_check done: account_id=%s status=%s diff_pct=%.4f diff_rub=%.2f duration_ms=%d",
                self._account_id,
                result.status,
                float(result.diff_pct),
                float(result.diff_rub),
                result.duration_ms,
            )
        except Exception:
            log.exception(
                "pnl_health_check failed (non-blocking) account_id=%s",
                self._account_id,
            )
            try:
                session.rollback()
            except Exception:
                pass
        finally:
            session.close()

    def _stage_autoset_inferred_anchor(self) -> None:
        """ADR-0010: восстановить opening-balance anchor для счёта с неполной
        историей депозитов. Запускается ПОСЛЕ phantom_sweep+mark_to_market
        (журнал и last_portfolio_value финальны), ДО pnl_health_check (badge
        считается уже с якорем). Non-fatal: ошибка логируется, sync не падает.
        """
        from services.opening_anchor_service import autoset_inferred_anchor

        session = self._session_factory()
        try:
            autoset_inferred_anchor(session, self._account_id)
        except Exception:
            log.exception(
                "opening_anchor failed (non-blocking) account_id=%s", self._account_id
            )
            try:
                session.rollback()
            except Exception:
                pass
        finally:
            session.close()

    @staticmethod
    def _emit_sentry_health_alert(report) -> None:
        """Отправить Sentry событие при error severity. Не валит pipeline."""
        try:
            import sentry_sdk  # type: ignore

            if sentry_sdk.Hub.current.client is None:
                return
            with sentry_sdk.push_scope() as scope:
                scope.set_tag("issue_type", report.main_issue or "unknown")
                scope.set_tag("broker_account_id", report.broker_account_id)
                scope.set_extra("issues", [i.to_dict() for i in report.issues])
                scope.set_extra("trades_with_issues", report.trades_with_issues)
                sentry_sdk.capture_message(
                    f"Sync health audit failed: {report.main_issue}",
                    level="error",
                )
        except Exception:
            log.exception("sentry health alert failed")

    async def _stage_mark_to_market(self) -> None:
        """
        PR 18 (live positions): источник истины для открытых позиций — это
        Tinkoff `get_portfolio()`. Раньше мы выводили позиции FIFO-движком,
        но это путало картину при корпоративных действиях (SECURITY_OUT /
        транзит между счетами / выкуп) — позиция оставалась "open" хотя на
        счёте её уже нет. Tinkoff API всегда отдаёт точное состояние.

        Алгоритм:
        1. fetch live portfolio (positions с qty, avg_price, current_price).
        2. REPLACE all PositionORM для аккаунта строго тем что вернул Tinkoff.
        3. unrealized_pnl = (current - avg) × qty (signed), валюта из позиции.

        FIFO-derived позиции, оставшиеся в БД от старого алгоритма, будут
        удалены этим replace'ом. Trade-журнал (закрытые сделки) остаётся
        нетронутым — он считается отдельно FIFO-движком.
        """
        try:
            async with client_factory.async_client(self._token) as services:
                ops = TinkoffOperationsClient(services)
                raw = await ops.get_portfolio_raw(self._broker_account_id)
        except BrokerError as exc:
            log.warning(
                "live_positions: get_portfolio failed (%s) — keeping previous snapshot",
                type(exc).__name__,
            )
            return

        positions = list(getattr(raw, "positions", []))
        # PR 20: запоминаем live UIDs для health-audit (сравнение DB vs Tinkoff).
        # Игнорируем currency-позиции (это cash-balance, не настоящая позиция).
        self._last_live_position_uids = {
            getattr(p, "instrument_uid", None)
            for p in positions
            if (
                getattr(p, "instrument_uid", None)
                and (getattr(p, "instrument_type", "") or "") != "currency"
                and getattr(p, "quantity", None) is not None
                and (
                    (getattr(p.quantity, "units", 0) or 0) != 0
                    or (getattr(p.quantity, "nano", 0) or 0) != 0
                )
            )
        }
        # PR 21: запоминаем total_amount_portfolio (рубли) — для autoset
        # initial_balance после первого sync.
        total_amount = getattr(raw, "total_amount_portfolio", None)
        if total_amount is not None:
            try:
                self._last_portfolio_total_rub = (
                    Decimal(total_amount.units or 0)
                    + Decimal(total_amount.nano or 0) / Decimal(1_000_000_000)
                )
            except Exception:
                self._last_portfolio_total_rub = None
        await asyncio.to_thread(self._replace_positions_from_live, positions)
        # PR 22: snapshot portfolio.total_amount в Account.last_portfolio_value —
        # это источник правды для compute_balance_at(date) (см. capital_service).
        # Заменяет broken-логику autoset initial_balance, которая не учитывала
        # INPUT/OUTPUT-операции и систематически завышала старт.
        await asyncio.to_thread(self._save_portfolio_snapshot)

    def _count_open_positions(self) -> int:
        """Сколько строк PositionORM у аккаунта (после live-replace)."""
        from models import PositionORM

        session = self._session_factory()
        try:
            return (
                session.query(PositionORM)
                .filter(PositionORM.account_id == self._account_id)
                .count()
            )
        finally:
            session.close()

    async def _stage_enrich_position_instruments(self) -> int:
        """
        Дотянуть ticker/name для инструментов в открытых позициях, которых
        нет в локальном instrument cache. Симптом без этой стадии — на
        странице «Открытые позиции» вместо тикера отображается UUID
        (новая серия фьючерсов / опцион, не попавший в bootstrap).

        Аналог `_stage_enrich`, но источник UID-ов — PositionORM, а не
        Operations. Делать пачкой нет смысла — обычно 0-1 missing.
        """
        from models import PositionORM

        def _gather_uids() -> list[str]:
            session = self._session_factory()
            try:
                rows = (
                    session.query(PositionORM.instrument_uid)
                    .filter(
                        PositionORM.account_id == self._account_id,
                        PositionORM.quantity != 0,
                    )
                    .all()
                )
                return [r[0] for r in rows if r[0]]
            finally:
                session.close()

        uids = await asyncio.to_thread(_gather_uids)
        if not uids:
            return 0

        def _missing() -> list[str]:
            session = self._session_factory()
            try:
                return self._instrument_repo.missing_uids(session, uids)
            finally:
                session.close()

        missing = await asyncio.to_thread(_missing)
        if not missing:
            return 0

        targets = missing[: self._max_instruments_per_run]
        log.info(
            "position_enrich: %d missing instruments for live positions, resolving %d",
            len(missing),
            len(targets),
        )

        async with client_factory.async_client(self._token) as services:
            instruments_client = TinkoffInstrumentsClient(services)
            resolved = []
            for uid in targets:
                try:
                    inst = await instruments_client.get_instrument_by_uid(uid)
                    resolved.append(inst)
                except InstrumentNotFound:
                    log.warning("position_enrich: instrument %s not found", uid)
                except BrokerError as exc:
                    log.warning(
                        "position_enrich: %s: %s — %s",
                        uid,
                        type(exc).__name__,
                        exc.message,
                    )

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

    def _save_portfolio_snapshot(self) -> None:
        """
        PR 22: сохранить актуальное `portfolio.total_amount_portfolio` (рубли) в
        `Account.last_portfolio_value` + timestamp. Это снимок «сколько денег
        у юзера сейчас по версии брокера» — обновляется при каждом sync.

        Используется `capital_service.compute_balance_at(date)`:
            balance_at(D) = last_portfolio_value − Σ payments(date > D)

        Заменяет PR 21 `_autoset_initial_balance_if_needed`, который имел
        системный баг: формула `portfolio - cumulative_realized` не учитывала
        INPUT/OUTPUT (депозиты/выводы) и из-за этого «стартовый капитал»
        получался завышенным на сумму всех пополнений за период sync.

        В новой модели `Account.initial_balance` для broker-юзера не
        используется как baseline; всё считается из `last_portfolio_value`
        и истории операций runtime.
        """
        from datetime import datetime as _dt

        if self._last_portfolio_total_rub is None:
            return

        from models import Account

        session = self._session_factory()
        try:
            account = (
                session.query(Account).filter(Account.id == self._account_id).first()
            )
            if account is None:
                return
            account.last_portfolio_value = self._last_portfolio_total_rub
            account.last_portfolio_at = _dt.utcnow()
            session.commit()
            log.info(
                "saved portfolio snapshot: account_id=%s value=%s",
                self._account_id,
                self._last_portfolio_total_rub,
            )
        except Exception:
            log.exception("save portfolio snapshot failed (non-blocking)")
            try:
                session.rollback()
            except Exception:
                pass
        finally:
            session.close()

    def _get_point_value(self, session, instrument_uid: str) -> Decimal:
        """PR 24: point_value = min_price_increment_amount / min_price_increment.

        Для фьючерсов цена в пунктах. point_value переводит в рубли.
        Fallback: 1.0 (если справочника нет; health-audit это поймает).
        """
        from models import InstrumentORM

        inst = (
            session.query(InstrumentORM)
            .filter(InstrumentORM.uid == instrument_uid)
            .first()
        )
        if inst is None:
            return Decimal("1")
        step = getattr(inst, "min_price_increment", None)
        step_amount = getattr(inst, "min_price_increment_amount", None)
        if step is None or step_amount is None:
            return Decimal("1")
        try:
            step_d = Decimal(str(step))
            amount_d = Decimal(str(step_amount))
            if step_d == 0:
                return Decimal("1")
            return amount_d / step_d
        except Exception:
            return Decimal("1")

    def _replace_positions_from_live(self, live_positions: list) -> None:
        """
        Заменить все PositionORM строки аккаунта тем, что вернул Tinkoff
        portfolio API. Это даёт точный snapshot реальных открытых позиций.

        SYNC-09 (2026-05-26): атомарность DELETE+INSERT гарантируется единым
        commit() в конце и rollback() в except — обе фазы в одной session,
        одна транзакция. Savepoint не нужен. Инвариант покрыт
        tests/integration/test_replace_positions_atomic.py::
        test_replace_positions_atomic_on_mid_insert_failure.
        """
        from models import PositionORM

        session = self._session_factory()
        try:
            # 1) Удаляем все наши накопленные FIFO-derived позиции.
            session.query(PositionORM).filter(
                PositionORM.account_id == self._account_id
            ).delete(synchronize_session=False)

            # 2) Вставляем то что реально на счёте.
            now = utc_now_naive()
            inserted = 0
            for p in live_positions:
                qty_obj = getattr(p, "quantity", None)
                if qty_obj is None:
                    continue
                qty_int = qty_obj.units or 0
                qty_nano = qty_obj.nano or 0
                # Округление до целого: Tinkoff позиции в инструментах все
                # дискретны (лотовые), nano у quantity почти всегда 0.
                # Currency-позиция (cash на счёте) — её игнорируем как
                # "позицию", она проходит через total_amount_currencies.
                itype = getattr(p, "instrument_type", "") or ""
                if itype == "currency":
                    continue
                if qty_int == 0 and qty_nano == 0:
                    continue
                quantity_signed = qty_int  # cash positions исключены выше

                uid = getattr(p, "instrument_uid", None)
                figi = getattr(p, "figi", None) or ""
                if not uid:
                    log.warning("live_positions: skip position without uid (figi=%s)", figi)
                    continue

                avg_obj = getattr(p, "average_position_price", None)
                if avg_obj is not None:
                    avg = Decimal(avg_obj.units or 0) + Decimal(avg_obj.nano or 0) / Decimal(1_000_000_000)
                else:
                    avg = Decimal(0)

                cur_obj = getattr(p, "current_price", None)
                if cur_obj is not None:
                    cur = Decimal(cur_obj.units or 0) + Decimal(cur_obj.nano or 0) / Decimal(1_000_000_000)
                else:
                    cur = None

                # Phase 7 (2026-05-17): authoritative fields from Tinkoff.
                # `expected_yield` — broker's official position P&L in RUB.
                # Для futures с FX-adjusted dynamic point_value (XIM6, ETM6
                # на USD-denomination) наша static-pv формула расходится с
                # broker. Берём expected_yield напрямую как source of truth.
                ey_obj = getattr(p, "expected_yield", None)
                expected_yield_rub: Optional[Decimal] = None
                if ey_obj is not None:
                    try:
                        expected_yield_rub = Decimal(ey_obj.units or 0) + Decimal(ey_obj.nano or 0) / Decimal(1_000_000_000)
                    except Exception:
                        expected_yield_rub = None

                vm_obj_raw = getattr(p, "var_margin", None)
                var_margin_rub: Optional[Decimal] = None
                if vm_obj_raw is not None:
                    try:
                        var_margin_rub = Decimal(vm_obj_raw.units or 0) + Decimal(vm_obj_raw.nano or 0) / Decimal(1_000_000_000)
                    except Exception:
                        var_margin_rub = None

                dy_obj = getattr(p, "daily_yield", None)
                daily_yield_rub: Optional[Decimal] = None
                if dy_obj is not None:
                    try:
                        daily_yield_rub = Decimal(dy_obj.units or 0) + Decimal(dy_obj.nano or 0) / Decimal(1_000_000_000)
                    except Exception:
                        daily_yield_rub = None

                # PR 24: для фьючерсов цены в ПУНКТАХ, не рублях. Чтобы получить
                # unrealized в ₽, умножаем на point_value = min_price_increment_amount
                # / min_price_increment (из справочника инструмента).
                #
                # Phase 7 (2026-05-17): для futures используем expected_yield_rub
                # (Tinkoff authoritative) — он точнее для USD-denominated контрактов
                # с dynamic FX-adjusted pv. Для shares/etf/bonds — fallback formula.
                unrealized = None
                point_value: Optional[Decimal] = None
                if itype in ("futures", "option") and expected_yield_rub is not None:
                    # Tinkoff's expected_yield is the canonical position P&L in RUB
                    unrealized = expected_yield_rub
                    # Still compute point_value for backward-compat / display
                    point_value = self._get_point_value(session, uid)
                elif cur is not None and avg is not None:
                    delta = cur - avg
                    if itype in ("futures", "option"):
                        # Fallback if expected_yield не пришёл — static pv formula
                        point_value = self._get_point_value(session, uid)
                        unrealized = delta * Decimal(quantity_signed) * point_value
                    else:
                        unrealized = delta * Decimal(quantity_signed)

                # Currency для отображения unrealized_pnl. avg_position_price.currency
                # у Tinkoff для фьючерсов = "pt" (пункты) — это техническая единица
                # цены контракта, а не валюта реальных денег. PnL/варм-маржа всегда
                # в рублях (для MOEX). Поэтому "pt"/"" нормализуем в "rub".
                raw_currency = (getattr(avg_obj, "currency", None) if avg_obj else None) or ""
                rc = raw_currency.lower().strip(".")
                if rc in ("pt", "point", "points", "пт", ""):
                    currency = "rub"
                elif rc == "rur":  # старый ISO код, ныне deprecated в пользу RUB
                    currency = "rub"
                else:
                    currency = rc

                extra: dict = {}
                if point_value is not None:
                    extra["point_value"] = str(point_value)
                # PortfolioPosition.var_margin теперь хранится в выделенной
                # колонке `var_margin_rub` (Phase 7, 2026-05-17). Это
                # «вариомаржа с момента последнего clearing» (intraday).

                row = PositionORM(
                    account_id=self._account_id,
                    instrument_uid=uid,
                    instrument_type=itype,
                    quantity=quantity_signed,
                    avg_entry_price=avg,
                    current_price=cur,
                    unrealized_pnl=unrealized,
                    expected_yield_rub=expected_yield_rub,
                    var_margin_rub=var_margin_rub,
                    daily_yield_rub=daily_yield_rub,
                    last_priced_at=now if cur is not None else None,
                    currency=currency,
                    extra=extra,
                )
                session.add(row)
                inserted += 1
            session.commit()
            log.info(
                "live_positions: replaced PositionORM for account_id=%s inserted=%d",
                self._account_id,
                inserted,
            )
        except Exception:
            # S2-17: сбой вставки live-позиций (кривой quantity/валюта) — не
            # осознанный degrade (тот только для BrokerError на fetch выше).
            # Стадия идёт ДО _stage_commit_cursor → проброс сохраняет SYNC-08:
            # курсор не двинется, sync репортит error, а не молчаливый success.
            log.exception("live_positions replace failed")
            try:
                session.rollback()
            except Exception:
                pass
            raise
        finally:
            session.close()

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

    def _stage_attribute_fees(self) -> None:
        """TR1.3: распределяет account-level fees по trades аккаунта.

        Алгоритм:
        1. Load all fee ops для аккаунта (varmargin, margin_fee, service_fee,
           generic tax).
        2. Load all Trade rows аккаунта (closed + open).
        3. Запустить `attribute_fees` — proportional by notional × time.
        4. Bulk UPDATE Trade rows с attributed values + recompute net_pnl.

        Идемпотентно — RESET attribution fields перед расчётом, потом fill.
        """
        from models import OperationORM, Trade as TradeORM, InstrumentORM
        from domain.pnl.fee_attribution import attribute_fees, apply_attribution_to_trade
        from domain.pnl.futures import _point_value as futures_point_value
        from domain.entities import Trade as DomainTrade, Operation as DomainOp, Instrument
        from domain.enums import InstrumentType, OperationType, OperationState, TradeDirection
        from domain.value_objects import MoneyValue
        from utils.datetime_utils import utc_now_naive

        session = self._session_factory()
        try:
            # 1. Fetch fee ops для ВСЕХ attributable категорий (Phase 3c, 2026-05-17).
            # До этой даты было hardcoded 5 типов — упускались tax_progressive,
            # benefit_tax, tax_repo*, track_*, success_fee, overnight, cash_fee
            # и др. → silent cash drift на тех аккаунтах.
            from domain.pnl.cash_flow_classification import (
                CashFlowCategory,
                operation_types_in,
            )
            fee_types_set: set[str] = (
                operation_types_in(CashFlowCategory.VARMARGIN)
                | operation_types_in(CashFlowCategory.ATTRIBUTABLE_FEE)
                | operation_types_in(CashFlowCategory.TAX)
                | operation_types_in(CashFlowCategory.INCOME)
                | operation_types_in(CashFlowCategory.INCOME_TAX)
            )
            fee_op_rows = (
                session.query(OperationORM)
                .filter(
                    OperationORM.account_id == self._account_id,
                    OperationORM.state == "executed",
                    OperationORM.operation_type.in_(tuple(fee_types_set)),
                )
                .order_by(OperationORM.executed_at)
                .all()
            )

            # 2. Fetch all Trade rows аккаунта.
            trade_rows = (
                session.query(TradeORM)
                .filter(TradeORM.account_id == self._account_id)
                .all()
            )

            if not trade_rows:
                return  # nothing to attribute to
            if not fee_op_rows:
                # Reset attribution columns to 0 если ничего нет
                for tr in trade_rows:
                    tr.varmargin_attributed = Decimal(0)
                    tr.margin_fee_attributed = Decimal(0)
                    tr.service_fee_attributed = Decimal(0)
                    tr.other_fees_attributed = Decimal(0)
                session.commit()
                return

            # 3. Build instrument lookup для point_value.
            uids = {tr.instrument_uid for tr in trade_rows if tr.instrument_uid}
            instr_rows = (
                session.query(InstrumentORM).filter(InstrumentORM.uid.in_(uids)).all()
                if uids
                else []
            )
            instr_by_uid = {i.uid: i for i in instr_rows}

            def pv_for(uid: Optional[str]) -> Decimal:
                if not uid or uid not in instr_by_uid:
                    return Decimal(1)
                i = instr_by_uid[uid]
                # Для futures используем formula min_price_increment_amount/min_price_increment
                if (i.instrument_type or "").lower() == "futures":
                    # Reuse futures._point_value — нужен Instrument entity
                    try:
                        instr_entity = Instrument(
                            uid=i.uid,
                            figi=i.figi,
                            ticker=i.ticker,
                            instrument_type=InstrumentType.FUTURES,
                            lot=i.lot or 1,
                            min_price_increment=Decimal(i.min_price_increment)
                            if i.min_price_increment
                            else None,
                            min_price_increment_amount=Decimal(i.min_price_increment_amount)
                            if i.min_price_increment_amount
                            else None,
                        )
                        return futures_point_value(instr_entity)
                    except Exception:
                        return Decimal(1)
                return Decimal(1)

            def instrument_type_for(uid: Optional[str]) -> Optional[str]:
                """Phase 3c: используется fee_attribution для restrict
                VARMARGIN-без-instrument_uid → только FUTURES (иначе phantom
                varmargin loss на shares, как в acc#4 audit -9,174₽)."""
                if not uid or uid not in instr_by_uid:
                    return None
                return instr_by_uid[uid].instrument_type

            # 4. Convert ORM rows → domain entities (frozen Pydantic).
            now = utc_now_naive()
            domain_trades: list[DomainTrade] = []
            for tr in trade_rows:
                try:
                    domain_trades.append(self._orm_trade_to_domain(tr))
                except Exception as exc:
                    log.warning(
                        "fee_attribution.skip_invalid_trade",
                        extra={"trade_id": tr.id, "error": str(exc)},
                    )
                    domain_trades.append(None)  # placeholder для index alignment

            domain_ops: list[DomainOp] = []
            for op in fee_op_rows:
                try:
                    domain_ops.append(self._orm_op_to_domain(op))
                except Exception:
                    continue  # skip malformed

            # 5. Filter None placeholders — attribute_fees им не нужны.
            valid_pairs = [(i, t) for i, t in enumerate(domain_trades) if t is not None]
            valid_trades = [t for _, t in valid_pairs]
            attributions = attribute_fees(
                fee_ops=domain_ops,
                trades=valid_trades,
                now=now,
                point_value_for=pv_for,
                instrument_type_for=instrument_type_for,
            )

            # 6. UPDATE Trade rows с attributed values.
            for (orig_idx, _), attr in zip(valid_pairs, attributions):
                tr = trade_rows[orig_idx]
                tr.varmargin_attributed = attr.varmargin
                tr.margin_fee_attributed = attr.margin_fee
                tr.service_fee_attributed = attr.service_fee
                tr.other_fees_attributed = attr.other
                # Recompute net_pnl для closed trades (open остаются с net_pnl=None).
                if tr.exit_at is not None and tr.net_pnl is not None:
                    # net_pnl в БД был computed FIFO calculator'ом БЕЗ этих fees.
                    # Чтобы избежать double-add при повторном attribution stage,
                    # храним base net_pnl в pnl (gross body) и attribution отдельно.
                    # Final net_pnl = gross body − commission + Σ attribution.
                    base = Decimal(tr.pnl or 0) - abs(Decimal(tr.commission or 0))
                    delta = attr.varmargin + attr.margin_fee + attr.service_fee + attr.other
                    tr.net_pnl = base + delta

            session.commit()
            log.info(
                "fee_attribution.stage_done",
                extra={
                    "account_id": self._account_id,
                    "fee_ops": len(domain_ops),
                    "trades": len(valid_trades),
                },
            )
        except Exception:
            session.rollback()
            log.exception("fee_attribution.stage_failed")
        finally:
            session.close()

    def _orm_trade_to_domain(self, orm_trade) -> "DomainTrade":
        """Конвертирует TradeORM → domain Trade (для attribution algorithm)."""
        from domain.entities import Trade as DomainTrade
        from domain.enums import InstrumentType, TradeDirection

        # Direction ORM enum → domain enum (string values совпадают).
        direction_str = (
            orm_trade.direction.value
            if hasattr(orm_trade.direction, "value")
            else str(orm_trade.direction).lower()
        )
        domain_direction = (
            TradeDirection.LONG if direction_str.lower() == "long" else TradeDirection.SHORT
        )

        # Instrument type fallback.
        itype_str = orm_trade.instrument_type_v2 or orm_trade.asset_type or "share"
        try:
            itype = InstrumentType(itype_str.lower())
        except Exception:
            itype = InstrumentType.SHARE

        return DomainTrade(
            account_id=str(orm_trade.account_id),
            instrument_uid=orm_trade.instrument_uid or "",
            instrument_figi=orm_trade.instrument_figi,
            instrument_type=itype,
            direction=domain_direction,
            quantity=int(orm_trade.quantity or 0),
            entry_price=Decimal(orm_trade.entry_price or 0),
            exit_price=Decimal(orm_trade.exit_price) if orm_trade.exit_price is not None else None,
            entry_at=orm_trade.entry_at,
            exit_at=orm_trade.exit_at,
            pnl=Decimal(orm_trade.pnl) if orm_trade.pnl is not None else None,
            net_pnl=Decimal(orm_trade.net_pnl) if orm_trade.net_pnl is not None else None,
            commission_total=Decimal(orm_trade.commission or 0),
            tax_total=Decimal(orm_trade.tax_total or 0) if hasattr(orm_trade, "tax_total") else Decimal(0),
            entry_value=Decimal(orm_trade.entry_value) if orm_trade.entry_value is not None else None,
            exit_value=Decimal(orm_trade.exit_value) if orm_trade.exit_value is not None else None,
            currency=orm_trade.currency or "rub",
        )

    def _orm_op_to_domain(self, orm_op):
        """Конвертирует OperationORM → domain Operation (только нужные поля)."""
        from domain.entities import Operation as DomainOp
        from domain.enums import InstrumentType, OperationState, OperationType
        from domain.value_objects import MoneyValue

        # Quantity → 0 для fee ops (они не trading).
        payment = None
        if orm_op.payment_units is not None or orm_op.payment_nano is not None:
            value = Decimal(int(orm_op.payment_units or 0)) + Decimal(
                int(orm_op.payment_nano or 0)
            ) / Decimal(1_000_000_000)
            payment = MoneyValue.from_decimal(value, orm_op.payment_currency or "rub")

        try:
            op_type = OperationType(orm_op.operation_type)
        except Exception:
            return None

        try:
            itype = InstrumentType(orm_op.instrument_type or "share")
        except Exception:
            itype = InstrumentType.SHARE

        return DomainOp(
            operation_id=orm_op.operation_id,
            account_id=str(orm_op.account_id),
            instrument_uid=orm_op.instrument_uid,
            instrument_figi=orm_op.instrument_figi,
            instrument_type=itype,
            operation_type=op_type,
            state=OperationState.EXECUTED,
            quantity=orm_op.quantity or 0,
            price=None,
            payment=payment,
            commission=None,
            executed_at=orm_op.executed_at,
        )

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

    def _save_sync_details(self, report: "SyncReport") -> None:
        """
        После успешного pipeline записать счётчики в BrokerConnection чтобы
        UI (/broker/sync-status, SyncStatusIndicator) показывал детализацию:
        кол-во операций, сделок, позиций, длительность.

        Также обнуляем consecutive_failures и circuit_open_until — sync
        прошёл, значит брокер доступен.
        """
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
            conn.last_sync_status = "success"
            conn.last_sync_error = None
            conn.consecutive_failures = 0
            conn.circuit_open_until = None
            conn.last_sync_operations_count = report.operations_new_or_updated
            conn.last_sync_trades_count = report.trades_built
            conn.last_sync_positions_count = report.positions_open
            conn.last_sync_duration_ms = int(report.duration_sec * 1000)
            session.commit()
        except Exception:
            log.exception("failed to record sync details")
            try:
                session.rollback()
            except Exception:
                pass
        finally:
            session.close()
