"""SYNC-09: атомарность `_replace_positions_from_live`.

Инвариант: при exception в середине цикла INSERT (после DELETE и нескольких
add()), состояние таблицы `positions` для аккаунта должно остаться
**неизменным** — rollback откатывает и DELETE, и накопленные INSERT'ы
(всё внутри одной session, единый commit() в конце).

Текущая реализация (на 2026-05-26):

```python
session = self._session_factory()
try:
    session.query(PositionORM).filter(...).delete(...)   # DELETE
    for p in live_positions:
        ...
        session.add(row)                                  # INSERT (накапливается)
    session.commit()                                      # единый commit
except Exception:
    log.exception(...)
    try: session.rollback()
    except Exception: pass
finally:
    session.close()
```

Если этот тест зелёный без правок — атомарность гарантируется текущим
кодом, и SYNC-09 finding закрыт по факту.

Замечание про except: текущий код **пробрасывает** исключение (`raise` в
except после rollback). Поэтому тест оборачивает вызов в `pytest.raises` —
мы проверяем и семантику пропагации, и state-инвариант (позиции не
изменились после отката).
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from application.sync.pipeline import SyncPipeline
from models import Account, Base, PositionORM, User


# ── фейковая Quotation (substitute для tinkoff MoneyValue) ────────────


class _FakeQuotation:
    __slots__ = ("units", "nano", "currency")

    def __init__(self, units: int, nano: int = 0, currency: str = "rub") -> None:
        self.units = units
        self.nano = nano
        self.currency = currency


class _FakeLivePosition:
    """Минимальная утка под `_replace_positions_from_live`.

    Атрибуты, которые читает код:
        instrument_uid, figi, instrument_type, quantity, average_position_price,
        current_price, expected_yield, var_margin, daily_yield.
    """

    def __init__(
        self,
        *,
        uid: str,
        itype: str = "share",
        qty: int = 1,
        avg_price: int = 100,
        cur_price: int = 105,
    ) -> None:
        self.instrument_uid = uid
        self.figi = ""
        self.instrument_type = itype
        self.quantity = _FakeQuotation(qty)
        self.average_position_price = _FakeQuotation(avg_price)
        self.current_price = _FakeQuotation(cur_price)
        self.expected_yield = _FakeQuotation(0)
        self.var_margin = _FakeQuotation(0)
        self.daily_yield = _FakeQuotation(0)


# ── фикстуры ──────────────────────────────────────────────────────────


@pytest.fixture
def db_session_factory(tmp_path: Path):
    db_path = tmp_path / "test_replace_positions_atomic.db"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
        future=True,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    try:
        yield Session
    finally:
        engine.dispose()


@pytest.fixture
def account_with_3_positions(db_session_factory):
    """Создаёт user + account и 3 PositionORM-строки.

    Возвращает (account_id, snapshot list[(uid, qty, avg_price)]).
    """
    with db_session_factory() as s:
        user = User(email="sync09@test.local", name="t", is_active=1)
        s.add(user)
        s.flush()
        account = Account(user_id=user.id, name="A", currency="RUB")
        s.add(account)
        s.flush()
        # Три baseline-позиции — это «pre-existing state», который не должен
        # исчезнуть при exception в _replace_positions_from_live.
        positions_spec = [
            ("uid-aaa", 10, Decimal("100.00")),
            ("uid-bbb", 5, Decimal("250.50")),
            ("uid-ccc", 7, Decimal("33.33")),
        ]
        for uid, qty, avg in positions_spec:
            s.add(
                PositionORM(
                    account_id=account.id,
                    instrument_uid=uid,
                    instrument_type="share",
                    quantity=qty,
                    avg_entry_price=avg,
                    current_price=None,
                    unrealized_pnl=None,
                    currency="rub",
                )
            )
        s.commit()
        return account.id, [
            (uid, qty, float(avg)) for uid, qty, avg in positions_spec
        ]


@pytest.fixture
def pipeline_factory(db_session_factory):
    def _make(account_id: int) -> SyncPipeline:
        return SyncPipeline(
            account_id=account_id,
            broker_account_id="acc-1",
            token_plaintext="t.fake",
            session_factory=db_session_factory,
        )

    return _make


# ── тест ──────────────────────────────────────────────────────────────


def _snapshot(session_factory, account_id: int) -> list[tuple]:
    with session_factory() as s:
        rows = (
            s.query(PositionORM)
            .filter(PositionORM.account_id == account_id)
            .order_by(PositionORM.instrument_uid)
            .all()
        )
        return [
            (r.instrument_uid, r.quantity, float(r.avg_entry_price)) for r in rows
        ]


def test_replace_positions_atomic_on_mid_insert_failure(
    db_session_factory, account_with_3_positions, pipeline_factory
) -> None:
    """SYNC-09: при exception в середине INSERT-цикла, существующие позиции не теряются.

    Сценарий:
        1. В таблице — 3 baseline-позиции (uid-aaa/bbb/ccc).
        2. `_replace_positions_from_live` получает 4 «свежих» позиции (uid-XXX-N).
        3. На 2-м `session.add()` мы выбрасываем RuntimeError.
        4. Ожидание: rollback откатил DELETE и накопленный INSERT.
           Snapshot ПОСЛЕ == snapshot ДО.
    """
    account_id, before = account_with_3_positions
    assert len(before) == 3

    pipeline = pipeline_factory(account_id)

    live_positions = [
        _FakeLivePosition(uid=f"uid-NEW-{i}", qty=i + 1, avg_price=200 + i)
        for i in range(4)
    ]

    # Симулируем падение на 2-м add(). К этому моменту:
    # - DELETE уже выполнен (на flush будет применён),
    # - 1 INSERT уже накоплен в session,
    # - 2-й add() выбрасывает RuntimeError → except → rollback().
    real_add = type(db_session_factory()).add
    call_count = {"n": 0}

    def failing_add(self_session, instance, *args, **kwargs):
        # Падаем именно на PositionORM-add'ах. Любые служебные add'ы
        # (внутри ORM relationship resolution и т.п.) — пропускаем как есть.
        if isinstance(instance, PositionORM):
            call_count["n"] += 1
            if call_count["n"] == 2:
                raise RuntimeError("simulated failure mid-INSERT")
        return real_add(self_session, instance, *args, **kwargs)

    with patch.object(type(db_session_factory()), "add", failing_add):
        # _replace_positions_from_live пробрасывает exception (rollback + raise
        # в except). Ловим его — важна и пропагация, и post-state после отката.
        with pytest.raises(RuntimeError, match="simulated failure mid-INSERT"):
            pipeline._replace_positions_from_live(live_positions)

    # Убеждаемся, что падение действительно произошло (2-й add упал).
    assert call_count["n"] == 2, (
        f"ожидали что 2-й PositionORM.add упадёт; counter={call_count['n']}"
    )

    after = _snapshot(db_session_factory, account_id)
    assert after == before, (
        f"SYNC-09 violation: при exception состояние позиций должно остаться "
        f"неизменным.\n  before={before}\n  after={after}"
    )


def test_replace_positions_happy_path_replaces_all(
    db_session_factory, account_with_3_positions, pipeline_factory
) -> None:
    """SYNC-09 regression: при успешном прогоне старые позиции удалены,
    новые — записаны. Гарантирует, что fix не сломал happy-path."""
    account_id, before = account_with_3_positions
    pipeline = pipeline_factory(account_id)

    live_positions = [
        _FakeLivePosition(uid="uid-NEW-1", qty=11, avg_price=500),
        _FakeLivePosition(uid="uid-NEW-2", qty=22, avg_price=600),
    ]
    pipeline._replace_positions_from_live(live_positions)

    after = _snapshot(db_session_factory, account_id)
    expected = [("uid-NEW-1", 11, 500.0), ("uid-NEW-2", 22, 600.0)]
    assert after == expected, (
        f"happy-path: ожидали полную замену\n  expected={expected}\n  after={after}"
    )
