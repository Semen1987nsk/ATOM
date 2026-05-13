"""
Integration-тесты `InstrumentRepository` (PR 5 Stage 1).

Проверяем:

* upsert / upsert_many round-trip,
* идемпотентность (повторный upsert тех же uid обновляет, не плодит),
* missing_uids возвращает разницу,
* type-specific поля (bond/futures/option) сохраняются и читаются.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from adapters.persistence.instrument_repo import InstrumentRepository
from domain.entities import Instrument
from domain.enums import InstrumentType
from models import Base, InstrumentORM


@pytest.fixture
def db_session_factory(tmp_path: Path):
    db_path = tmp_path / "test_instr_repo.db"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
        future=True,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    yield Session
    engine.dispose()


# ── builders ──


def _share(uid: str = "uid-sber") -> Instrument:
    return Instrument(
        uid=uid,
        figi="BBG004730N88",
        ticker="SBER",
        class_code="TQBR",
        instrument_type=InstrumentType.SHARE,
        isin="RU0009029540",
        name="Сбер",
        lot=10,
        currency="rub",
        min_price_increment=Decimal("0.01"),
    )


def _bond(uid: str = "uid-ofz") -> Instrument:
    return Instrument(
        uid=uid,
        figi="BBG00X3WDLQ7",
        ticker="SU26247RMFS5",
        instrument_type=InstrumentType.BOND,
        nominal=Decimal("1000"),
        coupon_quantity_per_year=2,
        amortization_flag=False,
        maturity_date=datetime(2039, 5, 11, tzinfo=timezone.utc),
    )


def _future(uid: str = "uid-si") -> Instrument:
    return Instrument(
        uid=uid,
        figi="FUTSI0625",
        ticker="Si-6.25",
        instrument_type=InstrumentType.FUTURES,
        min_price_increment=Decimal("1"),
        min_price_increment_amount=Decimal("10"),
        basic_asset_size=Decimal("1000"),
        expiration_date=datetime(2026, 6, 19, tzinfo=timezone.utc),
    )


def _option(uid: str = "uid-yndx-call") -> Instrument:
    return Instrument(
        uid=uid,
        instrument_type=InstrumentType.OPTION,
        strike_price=Decimal("4000"),
        option_direction="call",
        option_style="european",
        option_multiplier=100,
        expiration_date=datetime(2026, 6, 19, tzinfo=timezone.utc),
        basic_asset_uid="uid-yndx",
    )


# ── tests ──


def test_upsert_and_get(db_session_factory) -> None:
    repo = InstrumentRepository()
    with db_session_factory() as session:
        repo.upsert(session, _share())
        session.commit()

    with db_session_factory() as session:
        inst = repo.get_by_uid(session, "uid-sber")
    assert inst is not None
    assert inst.ticker == "SBER"
    assert inst.min_price_increment == Decimal("0.01")
    assert inst.lot == 10


def test_upsert_many_mixed_types(db_session_factory) -> None:
    repo = InstrumentRepository()
    items = [_share(), _bond(), _future(), _option()]
    with db_session_factory() as session:
        n = repo.upsert_many(session, items)
        session.commit()
    assert n == 4

    with db_session_factory() as session:
        bond = repo.get_by_uid(session, "uid-ofz")
        future = repo.get_by_uid(session, "uid-si")
        option = repo.get_by_uid(session, "uid-yndx-call")

    assert bond is not None and bond.coupon_quantity_per_year == 2
    assert future is not None and future.min_price_increment_amount == Decimal("10")
    assert option is not None
    assert option.strike_price == Decimal("4000")
    assert option.option_multiplier == 100
    # У опционов figi может быть None.
    assert option.figi in (None, "")


def test_upsert_idempotent(db_session_factory) -> None:
    repo = InstrumentRepository()
    with db_session_factory() as session:
        repo.upsert_many(session, [_share(), _bond()])
        session.commit()

    with db_session_factory() as session:
        repo.upsert_many(session, [_share(), _bond()])
        session.commit()

    with db_session_factory() as session:
        assert session.query(InstrumentORM).count() == 2


def test_upsert_updates_changed_fields(db_session_factory) -> None:
    repo = InstrumentRepository()
    initial = _share()
    with db_session_factory() as session:
        repo.upsert(session, initial)
        session.commit()

    # Тикер поменялся (бывает при ребрендинге).
    renamed = Instrument(
        uid=initial.uid,
        figi=initial.figi,
        ticker="NEW_TICKER",
        class_code=initial.class_code,
        instrument_type=initial.instrument_type,
        lot=initial.lot,
        currency=initial.currency,
        min_price_increment=initial.min_price_increment,
    )
    with db_session_factory() as session:
        repo.upsert(session, renamed)
        session.commit()

    with db_session_factory() as session:
        inst = repo.get_by_uid(session, initial.uid)
    assert inst is not None
    assert inst.ticker == "NEW_TICKER"


def test_get_many_by_uids(db_session_factory) -> None:
    repo = InstrumentRepository()
    with db_session_factory() as session:
        repo.upsert_many(session, [_share(), _bond(), _future()])
        session.commit()

    with db_session_factory() as session:
        result = repo.get_many_by_uids(
            session,
            ["uid-sber", "uid-ofz", "uid-nonexistent"],
        )
    assert set(result.keys()) == {"uid-sber", "uid-ofz"}
    assert result["uid-sber"].ticker == "SBER"


def test_missing_uids(db_session_factory) -> None:
    repo = InstrumentRepository()
    with db_session_factory() as session:
        repo.upsert_many(session, [_share()])
        session.commit()

    with db_session_factory() as session:
        missing = repo.missing_uids(session, ["uid-sber", "uid-other", "uid-third"])
    assert sorted(missing) == ["uid-other", "uid-third"]


def test_empty_inputs(db_session_factory) -> None:
    repo = InstrumentRepository()
    with db_session_factory() as session:
        assert repo.upsert_many(session, []) == 0
        assert repo.get_many_by_uids(session, []) == {}
        assert repo.missing_uids(session, []) == []
        assert repo.count(session) == 0
