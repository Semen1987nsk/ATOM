# Position = source of truth Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.

**Goal:** Position table становится единственной правдой для open positions / unrealized PnL. FIFO matcher отвечает только за closed trades. Новый этап sync pipeline закрывает phantom open Trade rows (когда брокер закрыл позицию, но SELL op задержалась).

**Architecture:** Добавляем `_stage_close_phantom_trades` после `_stage_mark_to_market`. FIFO matcher обрабатывает late SELL для свеженасвеченных trades (correction). Удаляем `/trades/unrealized-pnl` endpoint и Phase 6.5/6.6 frontend override.

**Tech Stack:** FastAPI + SQLAlchemy 2.0, pytest (backend), Next.js 16 + React 19 (frontend).

**Spec:** `docs/superpowers/specs/2026-05-19-position-source-of-truth-design.md`

---

### Task 1: Helpers — `_last_known_price` и `_has_recent_operations`

**Files:**
- Create: `backend/application/sync/phantom_sweep_helpers.py`
- Create: `backend/tests/unit/test_phantom_sweep_helpers.py`

- [ ] **Step 1: Failing test для `_last_known_price`**

```python
"""Helpers для phantom sweep: цены и проверка recent operations."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import models
from models import Base
from application.sync.phantom_sweep_helpers import (
    last_known_price, has_recent_operations,
)


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    s = Session()
    yield s
    s.close()


def test_last_known_price_from_position_current_price(session):
    """Если Position имеет current_price — возвращаем его."""
    pos = models.PositionORM(
        account_id=1, instrument_uid="uid-1", instrument_type="futures",
        quantity=Decimal("10"), avg_entry_price=Decimal("100"),
        current_price=Decimal("105"), unrealized_pnl=Decimal("50"),
    )
    session.add(pos)
    session.commit()

    assert last_known_price(session, "uid-1") == Decimal("105")


def test_last_known_price_returns_none_when_no_position(session):
    """Если Position строки нет (она удалена при закрытии позиции) — None."""
    assert last_known_price(session, "uid-missing") is None


def test_has_recent_operations_true_when_recent(session):
    """Recent operation в последние 24h → True (защита от Tinkoff blip)."""
    now = datetime(2026, 5, 19, 12, 0, tzinfo=timezone.utc).replace(tzinfo=None)
    op = models.OperationORM(
        operation_id="op-1", account_id=1, broker_account_id="ba-1",
        operation_type="buy", state="executed",
        payment_units=-1000, payment_nano=0,
        executed_at=now - timedelta(hours=2),
    )
    session.add(op)
    session.commit()

    assert has_recent_operations(session, 1, hours=24, now=now) is True


def test_has_recent_operations_false_when_old(session):
    """Нет recent ops в 24h → False (sweep можно делать смело)."""
    now = datetime(2026, 5, 19, 12, 0, tzinfo=timezone.utc).replace(tzinfo=None)
    op = models.OperationORM(
        operation_id="op-old", account_id=1, broker_account_id="ba-1",
        operation_type="buy", state="executed",
        payment_units=-1000, payment_nano=0,
        executed_at=now - timedelta(days=5),
    )
    session.add(op)
    session.commit()

    assert has_recent_operations(session, 1, hours=24, now=now) is False
```

- [ ] **Step 2: Run — expected FAIL (module не существует)**

```bash
cd backend && python -m pytest tests/unit/test_phantom_sweep_helpers.py -v 2>&1 | tail -10
```

Expected: `ImportError: No module named 'application.sync.phantom_sweep_helpers'`.

- [ ] **Step 3: Implement helpers**

```python
"""Helpers для _stage_close_phantom_trades.

Минимальный модуль, не тянет лишних зависимостей. Тестируется отдельно.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

import models


def last_known_price(session: Session, instrument_uid: str) -> Optional[Decimal]:
    """Последняя known цена инструмента из Position.current_price.

    Если позиция уже закрыта (Position row удалён) — возвращает None.
    Caller fallback'ит на Trade.entry_price.
    """
    pos = session.query(models.PositionORM).filter(
        models.PositionORM.instrument_uid == instrument_uid,
    ).first()
    if pos is None or pos.current_price is None:
        return None
    return Decimal(str(pos.current_price))


def has_recent_operations(
    session: Session, account_id: int, hours: int = 24,
    now: Optional[datetime] = None,
) -> bool:
    """Есть ли operations в последние `hours` часов для account.

    Используется как защита от Tinkoff Portfolio blip: если Position table
    стал пустым из-за временной ошибки API, а в Operations есть recent
    активность — sweep НЕ делаем.
    """
    cutoff = (now or datetime.utcnow()) - timedelta(hours=hours)
    count = session.query(models.OperationORM).filter(
        models.OperationORM.account_id == account_id,
        models.OperationORM.executed_at >= cutoff,
    ).limit(1).count()
    return count > 0
```

- [ ] **Step 4: Tests pass**

```bash
cd backend && python -m pytest tests/unit/test_phantom_sweep_helpers.py -v 2>&1 | tail -10
```

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/application/sync/phantom_sweep_helpers.py backend/tests/unit/test_phantom_sweep_helpers.py
git commit -m "feat(sync): helpers для phantom_sweep — last_known_price, has_recent_operations"
```

---

### Task 2: TDD главный sweep — `close_phantom_trades`

**Files:**
- Create: `backend/application/sync/phantom_sweep.py`
- Create: `backend/tests/unit/test_phantom_sweep.py`

- [ ] **Step 1: Failing test (happy path)**

```python
"""Tests для close_phantom_trades — закрытие open Trade rows без matching Position."""
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import models
from models import Base, TradeDirection
from application.sync.phantom_sweep import close_phantom_trades


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    s = Session()
    yield s
    s.close()


def _make_open_trade(session, instrument_uid: str, qty: int = 10, entry: Decimal = Decimal("100")):
    trade = models.Trade(
        account_id="1", instrument_uid=instrument_uid, instrument_figi="figi-" + instrument_uid,
        instrument_type="futures",
        direction=TradeDirection.LONG, quantity=qty,
        entry_price=entry, exit_price=None,
        entry_at=datetime(2026, 5, 1, 10, 0), exit_at=None,
        pnl=None, net_pnl=None,
        commission_total=Decimal("5"),
        entry_value=entry * qty,
    )
    session.add(trade)
    return trade


def test_closes_open_trade_without_position(session):
    """Phantom: open Trade + Position table пуста + есть recent ops → sweep пропускает (blip).
       Phantom: open Trade + Position table имеет ДРУГИЕ uids + не пуста → sweep закрывает."""
    # Real live position for другого инструмента — Position table не пустая
    live = models.PositionORM(
        account_id=1, instrument_uid="real-uid", instrument_type="futures",
        quantity=Decimal("5"), avg_entry_price=Decimal("100"),
        current_price=Decimal("105"), unrealized_pnl=Decimal("25"),
    )
    session.add(live)
    # Phantom trade — Position его не содержит
    phantom = _make_open_trade(session, "phantom-uid", qty=10, entry=Decimal("100"))
    session.commit()

    now = datetime(2026, 5, 19, 14, 0)
    count = close_phantom_trades(
        session, account_id=1,
        point_value_for=lambda uid: Decimal("1"),
        now=now,
    )

    assert count == 1
    session.refresh(phantom)
    assert phantom.exit_at == now
    assert phantom.exit_price == Decimal("100")  # no last_known, fallback на entry
    assert phantom.exit_reason == "phantom_sweep"
    assert "phantom_sweep" in (phantom.tags or [])
```

- [ ] **Step 2: Run — FAIL (close_phantom_trades нет)**

```bash
cd backend && python -m pytest tests/unit/test_phantom_sweep.py::test_closes_open_trade_without_position -v 2>&1 | tail -10
```

- [ ] **Step 3: Minimal implementation**

```python
"""close_phantom_trades: новый этап sync pipeline.

После _stage_mark_to_market закрывает Trade rows, у которых exit_at=None,
но соответствующей позиции нет в Position table. Это означает что Тинькофф
закрыл позицию, а SELL operation в Operations API задержалась.

Best-effort exit_price: last_known_price (из Position.current_price если
есть recent snapshot), fallback на entry_price (P&L = -commission).

Идемпотентно: повторный запуск не двигает уже закрытые Trade rows.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Callable, Optional

from sqlalchemy.orm import Session

import models
from logger import get_logger
from application.sync.phantom_sweep_helpers import (
    last_known_price, has_recent_operations,
)

log = get_logger("phantom_sweep")


def close_phantom_trades(
    session: Session,
    *,
    account_id: int,
    point_value_for: Callable[[Optional[str]], Decimal],
    now: datetime,
) -> int:
    """Закрыть Trade.exit_at=None если нет matching Position.

    Returns: количество закрытых phantom trades.
    """
    # Все live positions (qty != 0 — uids которые physically существуют у брокера)
    live_uids = {
        p.instrument_uid for p in session.query(models.PositionORM)
        .filter(
            models.PositionORM.account_id == account_id,
            models.PositionORM.quantity != 0,
        ).all()
    }

    # Защита от blip: пустой Position table + recent ops → skip
    if not live_uids and has_recent_operations(session, account_id, hours=24, now=now):
        log.warning(
            "phantom_sweep.skipped_empty_positions",
            extra={"account_id": account_id},
        )
        return 0

    open_trades = session.query(models.Trade).filter(
        models.Trade.account_id == str(account_id),
        models.Trade.exit_at.is_(None),
    ).all()
    phantoms = [t for t in open_trades if t.instrument_uid not in live_uids]
    if not phantoms:
        return 0

    closed = 0
    for trade in phantoms:
        exit_price = last_known_price(session, trade.instrument_uid)
        if exit_price is None:
            exit_price = Decimal(str(trade.entry_price))

        pv = point_value_for(trade.instrument_uid) if trade.instrument_uid else Decimal(1)
        body_pnl = (
            (exit_price - Decimal(str(trade.entry_price)))
            * Decimal(str(trade.quantity)) * pv
        )
        if trade.direction == models.TradeDirection.SHORT:
            body_pnl = -body_pnl

        commission = abs(Decimal(str(trade.commission_total or 0)))
        attributed = (
            Decimal(str(trade.varmargin_attributed or 0))
            + Decimal(str(trade.margin_fee_attributed or 0))
            + Decimal(str(trade.service_fee_attributed or 0))
            + Decimal(str(trade.other_fees_attributed or 0))
        )

        trade.exit_at = now
        trade.exit_price = exit_price
        trade.pnl = body_pnl
        trade.net_pnl = body_pnl - commission + attributed
        trade.exit_reason = "phantom_sweep"
        tags = list(trade.tags or [])
        if "phantom_sweep" not in tags:
            tags.append("phantom_sweep")
        trade.tags = tags

        log.warning(
            "phantom_trade_swept",
            extra={
                "trade_id": trade.id,
                "instrument_uid": trade.instrument_uid,
                "entry_price": str(trade.entry_price),
                "exit_price": str(exit_price),
                "net_pnl": str(trade.net_pnl),
            },
        )
        closed += 1

    session.flush()
    return closed
```

- [ ] **Step 4: Test passes**

```bash
cd backend && python -m pytest tests/unit/test_phantom_sweep.py -v 2>&1 | tail -10
```

Expected: 1 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/application/sync/phantom_sweep.py backend/tests/unit/test_phantom_sweep.py
git commit -m "feat(sync): close_phantom_trades — закрыть Trade.exit_at=None без matching Position"
```

---

### Task 3: Edge cases tests для phantom sweep

**Files:**
- Modify: `backend/tests/unit/test_phantom_sweep.py`

- [ ] **Step 1: Добавить 5 edge case тестов**

В конец файла:

```python
def test_no_sweep_when_position_exists(session):
    """Trade open + matching Position → НЕ sweep."""
    live = models.PositionORM(
        account_id=1, instrument_uid="uid-A", instrument_type="futures",
        quantity=Decimal("10"), avg_entry_price=Decimal("100"),
        current_price=Decimal("105"), unrealized_pnl=Decimal("50"),
    )
    trade = _make_open_trade(session, "uid-A", qty=10, entry=Decimal("100"))
    session.add(live)
    session.commit()

    count = close_phantom_trades(
        session, account_id=1,
        point_value_for=lambda uid: Decimal("1"),
        now=datetime(2026, 5, 19, 14, 0),
    )
    assert count == 0
    session.refresh(trade)
    assert trade.exit_at is None
    assert trade.exit_reason is None


def test_uses_last_known_price_when_available(session):
    """Если для phantom uid в Position есть current_price — используем его."""
    # Position для phantom uid с current_price (не должен быть, потому что qty=0,
    # но имеется в виду: history Position не удалён, qty=0, current_price есть)
    # Реалистично: при закрытии позиции Tinkoff обычно сохраняет current_price
    stale_pos = models.PositionORM(
        account_id=1, instrument_uid="closed-uid", instrument_type="futures",
        quantity=Decimal("0"),  # qty=0 — позиция закрыта
        avg_entry_price=Decimal("100"), current_price=Decimal("110"),
        unrealized_pnl=Decimal("0"),
    )
    # Real live position для другого инструмента — table не пустая
    other_live = models.PositionORM(
        account_id=1, instrument_uid="other-uid", instrument_type="futures",
        quantity=Decimal("5"), avg_entry_price=Decimal("100"),
        current_price=Decimal("105"), unrealized_pnl=Decimal("25"),
    )
    phantom = _make_open_trade(session, "closed-uid", qty=10, entry=Decimal("100"))
    session.add(stale_pos)
    session.add(other_live)
    session.commit()

    count = close_phantom_trades(
        session, account_id=1,
        point_value_for=lambda uid: Decimal("1"),
        now=datetime(2026, 5, 19, 14, 0),
    )
    assert count == 1
    session.refresh(phantom)
    # last_known_price нашёл stale_pos.current_price = 110
    assert phantom.exit_price == Decimal("110")
    # body_pnl = (110 - 100) * 10 * 1 = 100
    # net_pnl = 100 - 5 commission = 95
    assert phantom.pnl == Decimal("100")
    assert phantom.net_pnl == Decimal("95")


def test_short_direction_inverts_body_pnl(session):
    """SHORT phantom → body_pnl = -(exit - entry) × qty × pv (зеркально LONG)."""
    other_live = models.PositionORM(
        account_id=1, instrument_uid="other", instrument_type="futures",
        quantity=Decimal("1"), avg_entry_price=Decimal("100"),
        current_price=Decimal("100"), unrealized_pnl=Decimal("0"),
    )
    phantom = models.Trade(
        account_id="1", instrument_uid="short-uid", instrument_figi="figi-short",
        instrument_type="futures",
        direction=TradeDirection.SHORT, quantity=10,
        entry_price=Decimal("100"), exit_price=None,
        entry_at=datetime(2026, 5, 1), exit_at=None,
        pnl=None, net_pnl=None,
        commission_total=Decimal("0"),
        entry_value=Decimal("1000"),
    )
    session.add_all([other_live, phantom])
    session.commit()

    count = close_phantom_trades(
        session, account_id=1,
        point_value_for=lambda uid: Decimal("1"),
        now=datetime(2026, 5, 19, 14, 0),
    )
    assert count == 1
    session.refresh(phantom)
    # exit = entry (fallback) = 100, body = -(100-100)*10*1 = 0
    assert phantom.pnl == Decimal("0")


def test_skip_sweep_when_no_positions_but_recent_ops(session):
    """Tinkoff blip: Position table пуста, но в Operations есть recent ops → skip."""
    now = datetime(2026, 5, 19, 14, 0)
    op = models.OperationORM(
        operation_id="op-recent", account_id=1, broker_account_id="ba-1",
        operation_type="buy", state="executed",
        payment_units=-1000, payment_nano=0,
        executed_at=now,  # recent
    )
    phantom = _make_open_trade(session, "blip-uid")
    session.add(op)
    session.commit()

    count = close_phantom_trades(
        session, account_id=1,
        point_value_for=lambda uid: Decimal("1"),
        now=now,
    )
    assert count == 0
    session.refresh(phantom)
    assert phantom.exit_at is None  # NOT swept


def test_idempotent_already_closed_trade_untouched(session):
    """Идемпотентность: повторный запуск не трогает уже закрытые Trade."""
    other_live = models.PositionORM(
        account_id=1, instrument_uid="other", instrument_type="futures",
        quantity=Decimal("1"), avg_entry_price=Decimal("100"),
        current_price=Decimal("100"), unrealized_pnl=Decimal("0"),
    )
    already_closed = models.Trade(
        account_id="1", instrument_uid="closed-trade", instrument_figi="figi-x",
        instrument_type="futures",
        direction=TradeDirection.LONG, quantity=5,
        entry_price=Decimal("100"), exit_price=Decimal("105"),
        entry_at=datetime(2026, 5, 1), exit_at=datetime(2026, 5, 10),
        pnl=Decimal("25"), net_pnl=Decimal("20"),
        commission_total=Decimal("5"),
        entry_value=Decimal("500"),
    )
    session.add_all([other_live, already_closed])
    session.commit()

    count = close_phantom_trades(
        session, account_id=1,
        point_value_for=lambda uid: Decimal("1"),
        now=datetime(2026, 5, 19, 14, 0),
    )
    assert count == 0
    session.refresh(already_closed)
    assert already_closed.exit_at == datetime(2026, 5, 10)  # unchanged
    assert already_closed.exit_price == Decimal("105")
```

- [ ] **Step 2: Run tests — expected все 6 PASS**

```bash
cd backend && python -m pytest tests/unit/test_phantom_sweep.py -v 2>&1 | tail -15
```

- [ ] **Step 3: Commit**

```bash
git add backend/tests/unit/test_phantom_sweep.py
git commit -m "test(sync): edge cases для phantom_sweep — match Position, SHORT, blip, idempotent"
```

---

### Task 4: Регистрация stage в pipeline

**Files:**
- Modify: `backend/application/sync/pipeline.py`

- [ ] **Step 1: Найти `_stage_mark_to_market` в pipeline.py**

```bash
grep -n "_stage_mark_to_market\|def execute\|def _stage" /c/Users/Administrator/Eqio/ATOM/backend/application/sync/pipeline.py | head -15
```

- [ ] **Step 2: Добавить import + вызов после mark_to_market**

В начале файла (после других sync imports):
```python
from application.sync.phantom_sweep import close_phantom_trades
```

В `execute()` или эквивалентной orchestrator-функции, **после** `_stage_mark_to_market` и **до** `_stage_persist`:

```python
# Phase X (2026-05-19): закрыть phantom open Trades — позиций нет в Position table.
# Защита от случая когда Tinkoff закрыл позицию но SELL operation задержалась.
swept_count = close_phantom_trades(
    session=session,
    account_id=int(account.id),
    point_value_for=point_value_for,  # callback из orchestrator
    now=datetime.utcnow(),
)
if swept_count > 0:
    log.info(f"phantom_sweep closed {swept_count} trades for acc#{account.id}")
```

ПРИМЕЧАНИЕ: `point_value_for` уже передаётся в `_stage_mark_to_market` — реюзим тот же callback. Если он называется иначе — адаптировать.

- [ ] **Step 3: Запустить полные backend tests чтобы убедиться что pipeline не сломан**

```bash
cd backend && python -m pytest tests/ -x --tb=short -k "pipeline or sync" 2>&1 | tail -15
```

- [ ] **Step 4: Commit**

```bash
git add backend/application/sync/pipeline.py
git commit -m "feat(sync): register close_phantom_trades stage после mark_to_market"
```

---

### Task 5: FIFO matcher — correction для late SELL после sweep

**Files:**
- Modify: `backend/application/fifo_matching.py`
- Modify: `backend/tests/unit/test_fifo_matching.py`

- [ ] **Step 1: Failing test**

В `backend/tests/unit/test_fifo_matching.py` добавить:

```python
def test_late_sell_corrects_phantom_swept_trade():
    """Trade был swept с exit_price=100 (fallback на entry). Затем приходит
    реальная SELL operation с price=110. FIFO matcher должен перетереть
    swept values реальными + сменить exit_reason."""
    from datetime import datetime
    from decimal import Decimal
    from domain.entities import Trade, Operation
    from domain.enums import OperationType, TradeDirection
    from application.fifo_matching import FifoMatcher  # или эквивалентный класс

    # Swept trade
    swept = Trade(
        account_id="1", instrument_uid="uid-late",
        direction=TradeDirection.LONG, quantity=10,
        entry_price=Decimal("100"), exit_price=Decimal("100"),
        entry_at=datetime(2026, 5, 1), exit_at=datetime(2026, 5, 18),  # swept
        pnl=Decimal("0"), net_pnl=Decimal("-5"),  # body=0, comm=5
        commission_total=Decimal("5"),
        exit_reason="phantom_sweep",
        tags=["phantom_sweep"],
    )

    # Late SELL operation
    sell_op = Operation(
        operation_id="late-sell-1",
        operation_type=OperationType.SELL,
        instrument_uid="uid-late",
        executed_at=datetime(2026, 5, 19, 10, 0),
        quantity=10,
        price=110.0,
        payment=...,  # 1100 cash inflow
        commission=...,
    )

    # FIFO processing должен detect existing swept trade и correct
    # Точные API зависят от FifoMatcher интерфейса — детали в Step 3.
    # Pseudo: matcher.apply_late_sell(swept, sell_op) → swept with updated fields.
```

ПРИМЕЧАНИЕ: интерфейс FifoMatcher я не знаю точно без чтения файла. Implementer прочитает `application/fifo_matching.py` сначала.

- [ ] **Step 2: Прочитать `application/fifo_matching.py` для понимания структуры**

```bash
cd backend && grep -n "class FifoMatcher\|def match\|def _make_lot\|def _make_exit_fill" application/fifo_matching.py | head -10
```

- [ ] **Step 3: Implement correction logic**

Найти место в FIFO matcher где конструируется finalized closed Trade. Там добавить check:

```python
# Если matching swept trade существует — это late SELL после phantom_sweep.
# Перетереть exit_price/pnl реальными значениями + log conflict.
existing = session.query(models.Trade).filter(
    models.Trade.account_id == str(account_id),
    models.Trade.instrument_uid == instrument_uid,
    models.Trade.entry_at == lot.executed_at,
    models.Trade.exit_reason == "phantom_sweep",
).first()
if existing is not None:
    delta_pnl = float(real_net_pnl) - float(existing.net_pnl or 0)
    log.warning(
        "phantom_sweep_resolved_by_late_sell",
        extra={
            "trade_id": existing.id,
            "swept_exit_price": str(existing.exit_price),
            "actual_exit_price": str(real_exit_price),
            "delta_pnl": delta_pnl,
        },
    )
    existing.exit_price = real_exit_price
    existing.exit_at = real_exit_at
    existing.pnl = real_pnl
    existing.net_pnl = real_net_pnl
    existing.exit_reason = "sell_op_after_sweep"
    tags = list(existing.tags or [])
    if "sweep_corrected" not in tags:
        tags.append("sweep_corrected")
    existing.tags = tags
    return  # skip создание нового Trade row
```

Точная вставка зависит от текущей структуры FIFO matcher. Implementer прочитает и адаптирует.

- [ ] **Step 4: Test passes**

```bash
cd backend && python -m pytest tests/unit/test_fifo_matching.py -k "late_sell" -v 2>&1 | tail -10
```

- [ ] **Step 5: Commit**

```bash
git add backend/application/fifo_matching.py backend/tests/unit/test_fifo_matching.py
git commit -m "feat(fifo): handle late SELL для swept trades — correct values + log conflict"
```

---

### Task 6: Удалить `/trades/unrealized-pnl` endpoint + Phase 6.5 module

**Files:**
- Modify: `backend/routers/trades.py` (remove endpoint)
- Delete: `backend/domain/pnl/per_trade_unrealized.py`
- Delete: `backend/tests/unit/test_per_trade_unrealized.py`

- [ ] **Step 1: Найти endpoint в trades.py**

```bash
grep -n "/unrealized-pnl\|unrealized_pnl\|per_trade_unrealized\|compute_per_trade_pnl" /c/Users/Administrator/Eqio/ATOM/backend/routers/trades.py | head -10
```

- [ ] **Step 2: Удалить функцию-обработчик endpoint'а**

Найти `@router.get("/unrealized-pnl")` (или похожее) и удалить функцию целиком, включая декораторы.

Удалить также `from domain.pnl.per_trade_unrealized import ...` если есть.

- [ ] **Step 3: Удалить module + tests**

```bash
rm /c/Users/Administrator/Eqio/ATOM/backend/domain/pnl/per_trade_unrealized.py
rm /c/Users/Administrator/Eqio/ATOM/backend/tests/unit/test_per_trade_unrealized.py
```

- [ ] **Step 4: Прогнать tests чтобы убедиться что нет references**

```bash
cd backend && python -m pytest tests/ --tb=short 2>&1 | tail -10
```

Expected: все passed (или skipped). Если есть failures из-за missing import — fix.

- [ ] **Step 5: Commit**

```bash
git add -A backend/routers/trades.py backend/domain/pnl/per_trade_unrealized.py backend/tests/unit/test_per_trade_unrealized.py
git commit -m "refactor: удалить /trades/unrealized-pnl + per_trade_unrealized

Phase 6.5 был proxy для frontend Phase 6.6 override. С новым Position
source-of-truth подходом этот endpoint не нужен — frontend читает
unrealized напрямую из stats.py (Σ Position.unrealized_pnl)."
```

---

### Task 7: Frontend — `EquityCurveCard.tsx` убрать override

**Files:**
- Modify: `frontend/src/components/dashboard/EquityCurveCard.tsx`

- [ ] **Step 1: Удалить props `liveUnrealizedSum` и `snapshotUnrealized`**

В interface Props удалить:
```ts
liveUnrealizedSum?: number | null;
snapshotUnrealized?: number;
```

Из деструктуризации props удалить:
```ts
liveUnrealizedSum,
snapshotUnrealized,
```

- [ ] **Step 2: Удалить `dataAdjusted` useMemo**

Найти блок:
```tsx
const dataAdjusted = useMemo(() => {
  if (!data || data.length === 0) return data;
  if (liveUnrealizedSum === null || liveUnrealizedSum === undefined) return data;
  // ... override last point logic
}, [data, liveUnrealizedSum, snapshotUnrealized]);
```

Удалить целиком.

- [ ] **Step 3: Заменить все usages `dataAdjusted` на `data`**

В `merged` useMemo:
```ts
// Было: if (!dataAdjusted || dataAdjusted.length === 0) return [];
// Стало:
if (!data || data.length === 0) return [];
```

И далее везде `dataAdjusted` → `data`.

В `stats` useMemo аналогично.

В JSX внутри `<ComposedChart data={merged}>` — без изменений (merged уже строится из data).

`findClosest` тоже должен читать `data` вместо `dataAdjusted`.

- [ ] **Step 4: TS check**

```bash
cd frontend && npx tsc --noEmit 2>&1 | grep -E "EquityCurveCard|error TS" | head -10
```

Expected: только pre-existing layout.tsx error.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/dashboard/EquityCurveCard.tsx
git commit -m "refactor(equity-curve): убрать Phase 6.6 override last point

unrealized теперь добавляется к last point на backend-side (stats.py
_curve_tail_adjustment), фронт принимает data как есть. Это убирает
рассинхрон когда live unrealized содержит phantom мусор."
```

---

### Task 8: Frontend — `StatsGrid.tsx` убрать liveUnrealizedSum

**Files:**
- Modify: `frontend/src/components/dashboard/StatsGrid.tsx`

- [ ] **Step 1: Удалить prop**

В `StatsGridProps`:
```ts
// УДАЛИТЬ:
liveUnrealizedSum?: number | null;
```

Из function signature:
```ts
// БЫЛО: export function StatsGrid({ stats, hasData, liveUnrealizedSum }: ...) {
// СТАЛО:
export function StatsGrid({ stats, hasData }: StatsGridProps) {
```

- [ ] **Step 2: Удалить `headlineUnrealized` логику**

```ts
// УДАЛИТЬ:
const headlineUnrealized = (liveUnrealizedSum !== null && liveUnrealizedSum !== undefined)
  ? liveUnrealizedSum
  : (stats?.unrealized_pnl ?? 0);
```

Заменить usage в `displayTotalPnlWithUnrealized`:
```ts
const displayTotalPnlWithUnrealized = (displayTotalPnl ?? 0) + (stats?.unrealized_pnl ?? 0);
```

В subtitle (`Нереализ.: ${...}`) и tooltip:
```ts
// БЫЛО: parts.push(`Нереализ. ${compact(headlineUnrealized)}`);
// СТАЛО:
parts.push(`Нереализ. ${compact(stats?.unrealized_pnl ?? 0)}`);
```

И аналогично в `lines.push(...)` внутри tooltip.

- [ ] **Step 3: TS check**

```bash
cd frontend && npx tsc --noEmit 2>&1 | grep -E "StatsGrid|error TS" | head -10
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/dashboard/StatsGrid.tsx
git commit -m "refactor(stats-grid): убрать liveUnrealizedSum prop — читаем unrealized_pnl напрямую"
```

---

### Task 9: Frontend — `page.tsx` убрать fetch /trades/unrealized-pnl

**Files:**
- Modify: `frontend/src/app/page.tsx`

- [ ] **Step 1: Найти и удалить state + fetch**

```bash
grep -n "liveUnrealizedSum\|unrealized-pnl\|setLiveUnrealizedSum" /c/Users/Administrator/Eqio/ATOM/frontend/src/app/page.tsx | head -10
```

Удалить:
```tsx
const [liveUnrealizedSum, setLiveUnrealizedSum] = useState<number | null>(null);
```

Удалить useEffect / Promise.all блок что fetch'ит `/trades/unrealized-pnl`. Если он в Promise.all с другими fetch'ами — извлечь и оставить только остальные.

- [ ] **Step 2: Удалить props из children**

В JSX:
```tsx
// БЫЛО:
<EquityCurveCard
  ...,
  liveUnrealizedSum={liveUnrealizedSum}
  snapshotUnrealized={stats?.unrealized_pnl ?? 0}
  ...
/>
// СТАЛО:
<EquityCurveCard ... />  (без этих props)

// БЫЛО:
<StatsGrid stats={stats} hasData={hasData} liveUnrealizedSum={liveUnrealizedSum} />
// СТАЛО:
<StatsGrid stats={stats} hasData={hasData} />
```

- [ ] **Step 3: TS check**

```bash
cd frontend && npx tsc --noEmit 2>&1 | grep -E "page\.tsx|error TS" | head -10
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/app/page.tsx
git commit -m "refactor(page): убрать fetch /trades/unrealized-pnl + Phase 6.5 state

Endpoint удалён в backend. unrealized теперь приходит в /stats/ напрямую
(stats.unrealized_pnl = Σ Position.unrealized_pnl). Frontend ничего
не override'ит — единственный источник правды."
```

---

### Task 10: Manual smoke test + force-resync acc#4

**Files:** (без изменений)

- [ ] **Step 1: Restart uvicorn принудительно**

```bash
# В PowerShell:
Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object { $_.CommandLine -like '*uvicorn*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
Start-Sleep -Seconds 2
```

Запустить заново:
```bash
cd /c/Users/Administrator/Eqio/ATOM/backend
python -X utf8 -m uvicorn main:app --host 127.0.0.1 --port 8000 --reload > backend.out.log 2> backend.err.log &
```

Проверить:
```bash
sleep 5 && curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8000/health
```

- [ ] **Step 2: Force re-sync acc#4 через sync UI или admin endpoint**

В UI: нажать ↻ sync кнопку для acc#4. Альтернативно через admin:
```bash
# Найти sync trigger endpoint
grep -n "sync.*trigger\|force.*sync\|@router.*sync" /c/Users/Administrator/Eqio/ATOM/backend/routers/broker.py | head -5
```

Запустить sync — sweeper должен закрыть 10 phantom trades. В logs ожидаем:
```
phantom_trade_swept extra={trade_id: ..., instrument_uid: ...}
```

10 таких записей.

- [ ] **Step 3: Verify API возвращает корректное unrealized**

```bash
cd /c/Users/Administrator/Eqio/ATOM/backend
PYTHONIOENCODING=utf-8 python -c "
import requests
s = requests.Session()
s.post('http://localhost:8000/auth/login', json={'email': 'sarvanidi87@gmail.com', 'password': 'Olimp_2026!!!'})
r = s.get('http://localhost:8000/stats/?account_id=4')
d = r.json()
print(f'total_pnl: {d[\"total_pnl\"]:,.2f}')
print(f'unrealized_pnl: {d[\"unrealized_pnl\"]:,.2f}')
print(f'total_pnl_with_unrealized: {d[\"total_pnl_with_unrealized\"]:,.2f}')
"
```

Expected (acc#4 после закрытия 5 позиций, осталась 1 с unrealized -2k):
- total_pnl: около `-180k` (174k закрытых + ~5-6k от phantom_sweep на 10 трейдах)
- unrealized_pnl: около `-2,082`
- total_pnl_with_unrealized: около `-182k`

НЕ `-596k`, как было до фикса.

- [ ] **Step 4: Browser smoke check**

Ctrl+Shift+R на http://localhost:3000/. Проверить:
- Карточка «Общий PnL»: около -180k (не -596k)
- Equity curve last point: без спайка вниз
- Расхождение journal vs cash: 1-5% (orphan'ы + phantom_sweep estimation error)

- [ ] **Step 5: Финальный commit (если что-то фиксили в smoke)**

```bash
# Если нашли проблемы — отдельный commit. Иначе пропустить.
```

---

## Self-Review

**Spec coverage:**

| Spec секция | Task |
|---|---|
| Helpers (last_known_price, has_recent_operations) | Task 1 |
| close_phantom_trades main logic | Task 2 |
| Edge cases (no sweep, fallback, SHORT, blip, idempotent) | Task 3 |
| Register stage в pipeline | Task 4 |
| FIFO matcher correction для late SELL | Task 5 |
| Remove /trades/unrealized-pnl + per_trade_unrealized | Task 6 |
| Frontend EquityCurveCard | Task 7 |
| Frontend StatsGrid | Task 8 |
| Frontend page.tsx | Task 9 |
| Manual smoke + force resync | Task 10 |
| Защита от Tinkoff blip | Task 1 (helper) + Task 3 (test) |
| Audit tagging (exit_reason + tags) | Task 2 (impl) + Task 3 (test) |

Всё покрыто.

**Placeholder scan:** 

Один known soft spot — Task 5 FIFO matcher correction. Точный API класса FifoMatcher не знаю без чтения файла. Implementer прочитает в Step 2 и адаптирует. Указано явно.

Остальные шаги конкретные с кодом и командами.

**Type consistency:**

- `close_phantom_trades(session, *, account_id, point_value_for, now)` — одинаково в Task 2 (impl), Task 3 (tests), Task 4 (call from pipeline).
- `last_known_price(session, instrument_uid)` — одинаково в Task 1 + Task 2.
- `has_recent_operations(session, account_id, hours, now)` — одинаково.
- Trade fields: `exit_reason="phantom_sweep"` + `tags` — везде согласовано.
- Frontend: `liveUnrealizedSum` / `snapshotUnrealized` удаляются в Tasks 7-9 синхронно.
