"""
InstrumentBootstrapService — массовая выгрузка справочника инструментов
из T-Invest API в локальный кэш (таблица `instruments`).

Зачем: pipeline.enrich (PR 5) делает per-uid вызов `get_instrument_by_uid()`
для каждой новой операции. На активных трейдерах с сотнями инструментов
это даёт сотни лишних RPC + риск упереться в лимит. Bootstrap один раз
вытягивает весь справочник пачкой:

* shares()      — ~3-5k акций
* bonds()       — ~10-30k облигаций
* etfs()        — ~500 ETF
* futures()     — ~2-5k фьючерсов (включая истёкшие серии в архиве)
* options()     — ~50-100k опционов (массовые)
* currencies()  — десятки валютных инструментов

Итого 60-150k записей. Длительность: 1-3 минуты (зависит от Tinkoff RPS).

Refresh: фьючерсы экспирируются, опционы появляются — раз в неделю
пересинхронизируем. Сценарий «1 раз в день инструмент пропал» — pipeline
вызовет `get_instrument_by_uid` как fallback (см. PR 5).

Token: bootstrap не привязан к конкретному пользователю — любой active
read-only-or-better token у Тинькофф даёт доступ к справочнику. Подходит
для системного refresh из scheduler.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Callable, Optional

from sqlalchemy.orm import Session

from adapters.persistence.instrument_repo import InstrumentRepository
from adapters.tinkoff.client_factory import client_factory
from adapters.tinkoff.instruments_client import TinkoffInstrumentsClient
from database import SessionLocal
from domain.entities import Instrument
from domain.enums import InstrumentType
from domain.exceptions import BrokerError
from logger import get_logger
from models import InstrumentORM
from utils.datetime_utils import utc_now_naive

log = get_logger("sync.instrument_bootstrap")


DEFAULT_REFRESH_INTERVAL = timedelta(days=7)
# Имя метода в TinkoffInstrumentsClient + соответствующий InstrumentType.
_TYPE_METHODS: tuple[tuple[InstrumentType, str], ...] = (
    (InstrumentType.SHARE, "list_shares"),
    (InstrumentType.BOND, "list_bonds"),
    (InstrumentType.ETF, "list_etfs"),
    (InstrumentType.FUTURES, "list_futures"),
    (InstrumentType.OPTION, "list_options"),
    (InstrumentType.CURRENCY, "list_currencies"),
)


@dataclass
class BootstrapReport:
    started_at: datetime
    finished_at: Optional[datetime] = None
    by_type: dict[str, int] = field(default_factory=dict)
    total: int = 0
    duration_sec: float = 0.0
    success: bool = False
    error_type: Optional[str] = None
    error_message: Optional[str] = None


class InstrumentBootstrapService:
    """
    Один экземпляр на процесс. Безопасно вызывать многократно — внутри
    защита от двойного запуска через `_in_progress` (если хочется можно
    делать пакетный refresh из scheduler без риска двух параллельных).
    """

    def __init__(
        self,
        *,
        instrument_repo: Optional[InstrumentRepository] = None,
        session_factory: Callable[[], Session] = SessionLocal,
    ) -> None:
        self._repo = instrument_repo or InstrumentRepository()
        self._session_factory = session_factory
        self._lock = asyncio.Lock()

    # ── публичный API ─────────────────────────────────────────────────

    async def bootstrap_all(
        self, token: str, *, skip_options: bool = False
    ) -> BootstrapReport:
        """
        Полный download справочника из API → UPSERT в БД.

        `skip_options=True` — пропустить опционы (их десятки тысяч,
        самая долгая часть). Полезно когда вы знаете что не будете торговать
        опционами.

        Лок — против параллельного запуска (например, scheduler решил
        refresh, а пользователь подключил новый токен → второй вызов).
        """
        # Не блокируем если уже в работе — возвращаем «no-op report».
        if self._lock.locked():
            log.info("bootstrap already running, skipping concurrent invocation")
            return BootstrapReport(
                started_at=utc_now_naive(),
                finished_at=utc_now_naive(),
                success=False,
                error_type="AlreadyRunning",
                error_message="another bootstrap in progress",
            )

        async with self._lock:
            return await self._do_bootstrap(token, skip_options=skip_options)

    async def refresh_if_stale(
        self,
        token: str,
        *,
        max_age: timedelta = DEFAULT_REFRESH_INTERVAL,
        skip_options: bool = False,
    ) -> Optional[BootstrapReport]:
        """
        Запускает bootstrap_all если самая старая запись `instruments` старше
        `max_age` — или если таблица пустая.

        Возвращает None если кэш свежий.
        """
        stale = await asyncio.to_thread(self._cache_is_stale, max_age)
        if not stale:
            return None
        log.info(
            "instrument cache is stale (max_age=%s) — triggering refresh", max_age
        )
        return await self.bootstrap_all(token, skip_options=skip_options)

    # ── внутреннее ────────────────────────────────────────────────────

    async def _do_bootstrap(self, token: str, *, skip_options: bool) -> BootstrapReport:
        report = BootstrapReport(started_at=utc_now_naive())
        started_mono = time.monotonic()

        try:
            async with client_factory.async_client(token) as services:
                client = TinkoffInstrumentsClient(services)
                for inst_type, method_name in _TYPE_METHODS:
                    if skip_options and inst_type == InstrumentType.OPTION:
                        log.info("skipping options by flag")
                        continue
                    items = await self._fetch_one_type(client, method_name)
                    report.by_type[inst_type.value] = len(items)
                    if items:
                        await asyncio.to_thread(self._persist, items)
                    log.info(
                        "bootstrap %s: %d items persisted",
                        inst_type.value,
                        len(items),
                    )
            report.total = sum(report.by_type.values())
            report.success = True
        except BrokerError as exc:
            report.error_type = type(exc).__name__
            report.error_message = exc.message
            log.warning(
                "bootstrap failed: %s — %s", type(exc).__name__, exc.message
            )
        except Exception as exc:
            report.error_type = type(exc).__name__
            report.error_message = str(exc)
            log.exception("bootstrap unexpected failure")
        finally:
            report.finished_at = utc_now_naive()
            report.duration_sec = round(time.monotonic() - started_mono, 2)

        log.info(
            "bootstrap done: total=%d duration=%.2fs success=%s",
            report.total,
            report.duration_sec,
            report.success,
        )
        return report

    @staticmethod
    async def _fetch_one_type(
        client: TinkoffInstrumentsClient, method_name: str
    ) -> list[Instrument]:
        method = getattr(client, method_name)
        return await method()

    def _persist(self, instruments: list[Instrument]) -> None:
        """UPSERT одной пачкой в БД. `InstrumentRepository` сам чанкует."""
        session = self._session_factory()
        try:
            self._repo.upsert_many(session, instruments)
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def _cache_is_stale(self, max_age: timedelta) -> bool:
        """Самая старая `cached_at` в таблице старше `max_age`?"""
        session = self._session_factory()
        try:
            oldest = (
                session.query(InstrumentORM.cached_at)
                .order_by(InstrumentORM.cached_at.asc())
                .limit(1)
                .first()
            )
            if oldest is None:
                # пустой кэш = stale
                return True
            return (utc_now_naive() - oldest[0]) > max_age
        finally:
            session.close()
