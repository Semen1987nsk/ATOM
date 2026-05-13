"""
Integration-тесты `InstrumentBootstrapService` (PR 6).

Полную сетевую интеграцию через реальный токен — отдельным smoke-скриптом
(`tools/live_instrument_bootstrap.py`). Здесь — с моком SDK-клиентов:

* bootstrap_all сохраняет инструменты по всем типам и считает totals,
* SDK-ошибки не валят весь bootstrap, отчёт собирается,
* refresh_if_stale: пустой кэш = stale, свежий = no-op,
* двойной запуск (concurrent) — второй возвращает early без действия.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from adapters.persistence.instrument_repo import InstrumentRepository
from application.sync.instrument_bootstrap import InstrumentBootstrapService
from domain.entities import Instrument
from domain.enums import InstrumentType
from models import Base, InstrumentORM


# ── fixtures ──────────────────────────────────────────────────────────


@pytest.fixture
def db_session_factory(tmp_path: Path):
    db_path = tmp_path / "test_instr_bootstrap.db"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
        future=True,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    yield Session
    engine.dispose()


def _instr(uid: str, t: InstrumentType) -> Instrument:
    return Instrument(uid=uid, instrument_type=t, ticker=f"T-{uid[-4:]}")


@pytest.fixture
def fake_client_calls():
    """
    Patcher для `client_factory.async_client` и `TinkoffInstrumentsClient`.
    Возвращает контролируемый набор инструментов по типам.
    """
    fake_responses = {
        "list_shares": [_instr("uid-share-1", InstrumentType.SHARE), _instr("uid-share-2", InstrumentType.SHARE)],
        "list_bonds": [_instr("uid-bond-1", InstrumentType.BOND)],
        "list_etfs": [_instr("uid-etf-1", InstrumentType.ETF)],
        "list_futures": [_instr("uid-fut-1", InstrumentType.FUTURES), _instr("uid-fut-2", InstrumentType.FUTURES)],
        "list_options": [_instr("uid-opt-1", InstrumentType.OPTION)],
        "list_currencies": [_instr("uid-cur-1", InstrumentType.CURRENCY)],
    }
    return fake_responses


def _build_patches(fake_responses: dict, fail_on: str | None = None):
    """Возвращает контекстные patcher'ы (client_factory + InstrumentsClient)."""
    from contextlib import asynccontextmanager
    from unittest.mock import AsyncMock, MagicMock

    @asynccontextmanager
    async def fake_async_client(token):
        yield MagicMock()

    factory_patch = patch(
        "application.sync.instrument_bootstrap.client_factory.async_client",
        side_effect=fake_async_client,
    )

    fake_client = MagicMock()
    # Сначала проставляем все методы как успешные AsyncMock'и.
    for method_name, items in fake_responses.items():
        setattr(fake_client, method_name, AsyncMock(return_value=items))

    # Затем, если fail_on задан — перезаписываем нужный метод на падающий.
    if fail_on:
        from domain.exceptions import BrokerError

        setattr(
            fake_client,
            fail_on,
            AsyncMock(side_effect=BrokerError("simulated")),
        )

    client_patch = patch(
        "application.sync.instrument_bootstrap.TinkoffInstrumentsClient",
        return_value=fake_client,
    )
    return factory_patch, client_patch


# ── tests ──


def test_bootstrap_all_persists_by_type(db_session_factory, fake_client_calls) -> None:
    factory_patch, client_patch = _build_patches(fake_client_calls)
    service = InstrumentBootstrapService(session_factory=db_session_factory)

    with factory_patch, client_patch:
        report = asyncio.run(service.bootstrap_all("t.fake"))

    assert report.success
    assert report.total == 8  # 2+1+1+2+1+1
    assert report.by_type == {
        "share": 2,
        "bond": 1,
        "etf": 1,
        "futures": 2,
        "option": 1,
        "currency": 1,
    }
    assert report.duration_sec >= 0

    with db_session_factory() as session:
        assert session.query(InstrumentORM).count() == 8


def test_skip_options(db_session_factory, fake_client_calls) -> None:
    factory_patch, client_patch = _build_patches(fake_client_calls)
    service = InstrumentBootstrapService(session_factory=db_session_factory)

    with factory_patch, client_patch:
        report = asyncio.run(service.bootstrap_all("t.fake", skip_options=True))

    assert "option" not in report.by_type
    assert report.total == 7  # 8 - 1 опцион


def test_broker_error_recorded_in_report(db_session_factory, fake_client_calls) -> None:
    """SDK падает на list_options → report.success=False, частичные данные сохранены."""
    factory_patch, client_patch = _build_patches(fake_client_calls, fail_on="list_options")
    service = InstrumentBootstrapService(session_factory=db_session_factory)

    with factory_patch, client_patch:
        report = asyncio.run(service.bootstrap_all("t.fake"))

    assert not report.success
    assert report.error_type == "BrokerError"
    # Те типы, которые до options успели — сохранены (shares, bonds, etfs, futures).
    with db_session_factory() as session:
        saved = session.query(InstrumentORM).count()
    assert saved >= 6  # shares + bonds + etfs + futures


def test_refresh_if_stale_empty_cache(db_session_factory, fake_client_calls) -> None:
    factory_patch, client_patch = _build_patches(fake_client_calls)
    service = InstrumentBootstrapService(session_factory=db_session_factory)

    with factory_patch, client_patch:
        # Кэш пустой → stale → должен выполнить bootstrap.
        report = asyncio.run(service.refresh_if_stale("t.fake"))
    assert report is not None
    assert report.success
    assert report.total == 8


def test_refresh_if_stale_fresh_cache(db_session_factory, fake_client_calls) -> None:
    factory_patch, client_patch = _build_patches(fake_client_calls)
    service = InstrumentBootstrapService(session_factory=db_session_factory)

    with factory_patch, client_patch:
        asyncio.run(service.bootstrap_all("t.fake"))
        # Сразу после bootstrap — cache свежий, refresh должен быть no-op.
        result = asyncio.run(service.refresh_if_stale("t.fake", max_age=timedelta(days=7)))
    assert result is None


def test_refresh_if_stale_old_cache(db_session_factory, fake_client_calls) -> None:
    factory_patch, client_patch = _build_patches(fake_client_calls)
    service = InstrumentBootstrapService(session_factory=db_session_factory)

    with factory_patch, client_patch:
        asyncio.run(service.bootstrap_all("t.fake"))

    # Состариваем кэш руками.
    with db_session_factory() as session:
        rows = session.query(InstrumentORM).all()
        for r in rows:
            r.cached_at = datetime.utcnow() - timedelta(days=8)
        session.commit()

    with factory_patch, client_patch:
        report = asyncio.run(
            service.refresh_if_stale("t.fake", max_age=timedelta(days=7))
        )
    assert report is not None
    assert report.success


def test_concurrent_bootstrap_skipped(db_session_factory, fake_client_calls) -> None:
    """Второй параллельный вызов не должен запустить второй bootstrap."""
    factory_patch, client_patch = _build_patches(fake_client_calls)
    service = InstrumentBootstrapService(session_factory=db_session_factory)

    async def run_two_in_parallel():
        await service._lock.acquire()  # имитируем что bootstrap уже идёт
        try:
            return await service.bootstrap_all("t.fake")
        finally:
            service._lock.release()

    with factory_patch, client_patch:
        report = asyncio.run(run_two_in_parallel())

    # Под локом первый вызов вернул "AlreadyRunning"
    assert not report.success
    assert report.error_type == "AlreadyRunning"
