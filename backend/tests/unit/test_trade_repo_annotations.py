"""
DATA-02: re-sync (replace_for_instrument) не должен стирать пользовательские
аннотации (notes/tags/mood/discipline/confidence/setup_id/screenshot_url)
с sync-сделок. FIFO-пересборка пересоздаёт строки — аннотации обязаны
переехать на новые строки по натуральному ключу.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from adapters.persistence.trade_repo import TradeRepository
from domain.entities import Instrument, Trade
from domain.enums import InstrumentType, TradeDataSource, TradeDirection
from models import Trade as TradeORM

ACCOUNT_ID = 1
UID = "uid-sber"


def _make_instrument(**overrides) -> Instrument:
    base = dict(
        uid=UID,
        figi="BBG004730N88",
        ticker="SBER",
        name="Сбер Банк",
        instrument_type=InstrumentType.SHARE,
        lot=10,
    )
    base.update(overrides)
    return Instrument(**base)


def _make_trade(**overrides) -> Trade:
    base = dict(
        account_id=str(ACCOUNT_ID),
        instrument_uid=UID,
        instrument_figi="BBG004730N88",
        instrument_type=InstrumentType.SHARE,
        direction=TradeDirection.LONG,
        quantity=100,
        entry_price=Decimal("270"),
        exit_price=Decimal("275"),
        entry_at=datetime(2026, 5, 9, 10, 0, tzinfo=timezone.utc),
        exit_at=datetime(2026, 5, 9, 13, 30, tzinfo=timezone.utc),
        pnl=Decimal("500"),
        net_pnl=Decimal("500"),
        commission_total=Decimal("0"),
        entry_value=Decimal("27000"),
        exit_value=Decimal("27500"),
        currency="rub",
    )
    base.update(overrides)
    return Trade(**base)


ANNOTATIONS = dict(
    notes="вход по плану, отскок от поддержки",
    tags=["FOMO", "Trend"],
    mood=4,
    discipline=5,
    confidence=3,
    setup_id=7,
    screenshot_url="/screenshots/sber-1.png",
)


@pytest.fixture
def repo() -> TradeRepository:
    return TradeRepository()


def _seed_annotated_trade(db_session, repo: TradeRepository) -> TradeORM:
    """Первый sync + пользователь аннотировал сделку через PATCH."""
    repo.replace_for_instrument(
        db_session,
        account_id=ACCOUNT_ID,
        instrument_uid=UID,
        trades=[_make_trade()],
        instrument=_make_instrument(),
    )
    row = db_session.query(TradeORM).one()
    for field, value in ANNOTATIONS.items():
        setattr(row, field, value)
    db_session.flush()
    return row


def _resynced_row(db_session) -> TradeORM:
    return db_session.query(TradeORM).filter(
        TradeORM.data_source == TradeDataSource.TINKOFF_V2.value
    ).one()


class TestAnnotationCarryOver:
    def test_exact_match_carries_annotations(self, db_session, repo) -> None:
        """Re-sync с тем же (entry_at, exit_at, direction, quantity) —
        все аннотации переезжают на новую строку."""
        _seed_annotated_trade(db_session, repo)

        repo.replace_for_instrument(
            db_session,
            account_id=ACCOUNT_ID,
            instrument_uid=UID,
            trades=[_make_trade(net_pnl=Decimal("480"))],
            instrument=_make_instrument(),
        )

        row = _resynced_row(db_session)
        for field, value in ANNOTATIONS.items():
            assert getattr(row, field) == value, field
        # P&L при этом обновился из пересборки.
        assert row.net_pnl == Decimal("480")

    def test_changed_exit_falls_back_to_entry_direction(self, db_session, repo) -> None:
        """Брокер дослал операцию — exit_at сместился. Аннотация прикрепляется
        к сделке с тем же entry_at + direction (единственный кандидат)."""
        _seed_annotated_trade(db_session, repo)

        repo.replace_for_instrument(
            db_session,
            account_id=ACCOUNT_ID,
            instrument_uid=UID,
            trades=[
                _make_trade(
                    exit_at=datetime(2026, 5, 9, 14, 15, tzinfo=timezone.utc),
                    exit_price=Decimal("276"),
                )
            ],
            instrument=_make_instrument(),
        )

        row = _resynced_row(db_session)
        for field, value in ANNOTATIONS.items():
            assert getattr(row, field) == value, field

    def test_vanished_trade_drops_annotations_silently(self, db_session, repo) -> None:
        """Сделка исчезла из пересборки совсем — аннотация теряется молча,
        replace не падает."""
        _seed_annotated_trade(db_session, repo)

        inserted = repo.replace_for_instrument(
            db_session,
            account_id=ACCOUNT_ID,
            instrument_uid=UID,
            trades=[
                _make_trade(
                    entry_at=datetime(2026, 5, 12, 11, 0, tzinfo=timezone.utc),
                    exit_at=datetime(2026, 5, 12, 15, 0, tzinfo=timezone.utc),
                    direction=TradeDirection.SHORT,
                )
            ],
            instrument=_make_instrument(),
        )

        assert inserted == 1
        row = _resynced_row(db_session)
        assert row.notes is None
        assert row.mood is None
        assert row.setup_id is None

    def test_unannotated_trades_not_matched(self, db_session, repo) -> None:
        """Строки без аннотаций не участвуют в переносе (пустые notes/tags
        не считаются аннотацией)."""
        repo.replace_for_instrument(
            db_session,
            account_id=ACCOUNT_ID,
            instrument_uid=UID,
            trades=[_make_trade()],
            instrument=_make_instrument(),
        )

        repo.replace_for_instrument(
            db_session,
            account_id=ACCOUNT_ID,
            instrument_uid=UID,
            trades=[_make_trade()],
            instrument=_make_instrument(),
        )

        row = _resynced_row(db_session)
        assert row.notes is None
        assert row.tags in (None, [])
