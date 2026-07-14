# Inferred Opening-Balance Anchor — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Auto-restore an opening-balance anchor for broker accounts whose deposit history is incomplete, so headline P&L, return %, and the reconcile badge are correct without manual entry and without hiding real journal bugs.

**Architecture:** A pure decision module (`domain/pnl/opening_anchor.py`) computes `candidate = portfolio − net_deposits − journal` and passes a deposit-independent safety-gate (G1 sign, G2 futures-telescoping, G3 plausibility bound). A thin I/O service (`services/opening_anchor_service.py`) gathers DB inputs, calls the decision, and persists `Account.initial_balance` + `initial_balance_source` with freeze/manual-priority. A non-fatal pipeline stage runs it each sync after the journal is finalized. Downstream callers (`pnl_health_service`, `routers/stats.py`) switch from `net_deposits` to `effective_deposits = net_deposits + initial_balance`. The frontend labels honesty by source.

**Tech Stack:** Python 3.14 / SQLAlchemy 2.0 (sync) / Pydantic v2 backend; Next.js 16 / React 19 / TanStack Query / vitest frontend; pytest backend tests.

## Global Constraints

- **Spec:** `docs/superpowers/specs/2026-06-26-inferred-opening-balance-anchor-design.md` (committed `1b8a0bc`). Every task implements part of it.
- **ADR-0007 (immutable, 8 invariants)** and **ADR-0008 (cash-anchored 6-layer)** MUST stay green. Read `.business/tech/decisions/0007-pnl-methodology-invariants.md` + `docs/PNL_PLAYBOOK.md` before touching any P&L math.
- **No DB migration.** `Account.initial_balance` (Numeric) and `Account.initial_balance_source` (`String(32)`) already exist (migrations `0010`/`0011`). New source literals `inferred_anchor` (14), `inferred_blocked` (16), `complete` (8) fit in 32 chars.
- **Source literals (exact):** `'inferred_anchor'`, `'inferred_blocked'`, `'complete'`, `'manual'`. Legacy `'tinkoff_derived'` accounts are NOT protected by freeze and will be healed (recomputed) by the new stage — intended.
- **Pure vs I/O split:** `domain/pnl/opening_anchor.py` takes/returns only `Decimal`/bool/str — NO session, NO ORM. All DB access lives in `services/opening_anchor_service.py`.
- **Backend python:** `C:\Python314\python.exe`. Run tests with `PYTHONUTF8=1`. Backend must still import: `python -c "from main import app"`.
- **Frontend:** vitest on this host runs with `--maxWorkers=1`. No emojis in files.
- **Commits:** local only, stage **explicit own-file paths** (never `git add -A`/`.` — the working tree holds ~40 unrelated WIP files). **Pushing requires explicit user approval** — do not push.
- **acc#2 reference numbers** (Артём, broker_account_id `2135909232`), used as test oracles:
  - `portfolio_value = 32938`, `net_deposits = 8556`, `journal_pnl = -74713`
  - `candidate = 32938 − 8556 − (−74713) = 99095`
  - `body_closed = -70754`, `varmargin_net = -86799`, `open_settled = -7920`
  - `telescope_residual = |−70754 − (−86799 − (−7920))| = |−70754 + 78879| = 8125`; tol `= 0.25 × 86799 = 21699.75` → PASS (8125 ≤ 21699.75)
  - `gross_buy_peak = 93029.60`; G3 bound `= 50 × 93029.60` → PASS
  - Expected after: `initial_balance ≈ 99095`, headline cash `≈ −74713`, badge diff_pct `≈ 0%` at T0, доходность `≈ −69%` (base `= 99095 + 8556 = 107651`).

---

### Task 1: Pure anchor decision module

**Files:**
- Create: `backend/domain/pnl/opening_anchor.py`
- Test: `backend/tests/unit/test_opening_anchor.py`

**Interfaces:**
- Produces:
  - `ANCHOR_MIN: Decimal`, `TELESCOPE_TOL_PCT: Decimal`, `ANCHOR_MAX_FACTOR: Decimal`, `VARMARGIN_FLOOR: Decimal`
  - `@dataclass(frozen=True) AnchorDecision(should_anchor: bool, value: Decimal, source: str, reason: str)`
  - `compute_candidate_anchor(*, portfolio_value: Decimal, net_deposits: Decimal, journal_pnl: Decimal) -> Decimal`
  - `telescope_residual(*, body_closed: Decimal, varmargin_net: Decimal, open_settled: Decimal) -> Decimal`
  - `decide_anchor(*, incomplete_history: bool, portfolio_value: Decimal, net_deposits: Decimal, journal_pnl: Decimal, body_closed: Decimal, varmargin_net: Decimal, open_settled: Decimal, gross_buy_peak: Decimal) -> AnchorDecision`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/unit/test_opening_anchor.py`:

```python
"""Unit: pure opening-balance anchor decision (ADR-0010). No I/O.

Oracles = acc#2 (Артём, 2135909232) snapshot, см. spec §3.
"""
from decimal import Decimal

import pytest

from domain.pnl.opening_anchor import (
    ANCHOR_MAX_FACTOR,
    AnchorDecision,
    compute_candidate_anchor,
    decide_anchor,
    telescope_residual,
)

ACC2 = dict(
    incomplete_history=True,
    portfolio_value=Decimal("32938"),
    net_deposits=Decimal("8556"),
    journal_pnl=Decimal("-74713"),
    body_closed=Decimal("-70754"),
    varmargin_net=Decimal("-86799"),
    open_settled=Decimal("-7920"),
    gross_buy_peak=Decimal("93029.60"),
)


def test_candidate_formula_matches_acc2():
    got = compute_candidate_anchor(
        portfolio_value=Decimal("32938"),
        net_deposits=Decimal("8556"),
        journal_pnl=Decimal("-74713"),
    )
    assert got == Decimal("99095")


def test_telescope_residual_acc2():
    assert telescope_residual(
        body_closed=Decimal("-70754"),
        varmargin_net=Decimal("-86799"),
        open_settled=Decimal("-7920"),
    ) == Decimal("8125")


def test_acc2_anchors_with_healthy_futures():
    d = decide_anchor(**ACC2)
    assert d.should_anchor is True
    assert d.source == "inferred_anchor"
    assert d.value == Decimal("99095.00")


def test_complete_history_never_anchors():
    d = decide_anchor(**{**ACC2, "incomplete_history": False})
    assert d.should_anchor is False
    assert d.source == "complete"
    assert d.value == Decimal("0")


def test_g1_nonpositive_candidate_does_not_anchor():
    # journal >= cash → candidate <= 0 → nothing to restore (benign, not blocked).
    d = decide_anchor(
        **{**ACC2, "portfolio_value": Decimal("10000"), "journal_pnl": Decimal("5000")}
    )
    assert d.should_anchor is False
    assert d.source == "complete"


def test_g2_telescope_failure_blocks_anchor():
    # pv x1000 bug: body inflated → residual >> tol → blocked, real bug stays visible.
    d = decide_anchor(**{**ACC2, "body_closed": Decimal("-70754000")})
    assert d.should_anchor is False
    assert d.source == "inferred_blocked"


def test_g3_implausible_candidate_blocks_anchor():
    # No futures (varmargin~0 skips G2), tiny buy peak → bound 50*100=5000 < 99095 → blocked.
    d = decide_anchor(
        **{
            **ACC2,
            "varmargin_net": Decimal("0"),
            "body_closed": Decimal("0"),
            "open_settled": Decimal("0"),
            "gross_buy_peak": Decimal("100"),
        }
    )
    assert d.should_anchor is False
    assert d.source == "inferred_blocked"


def test_pure_stocks_account_anchors_via_g3():
    # No futures → G2 skipped; plausible buy peak → G3 passes → anchored.
    d = decide_anchor(
        incomplete_history=True,
        portfolio_value=Decimal("90000"),
        net_deposits=Decimal("10000"),
        journal_pnl=Decimal("-20000"),
        body_closed=Decimal("0"),
        varmargin_net=Decimal("0"),
        open_settled=Decimal("0"),
        gross_buy_peak=Decimal("40000"),
    )
    assert d.should_anchor is True
    assert d.source == "inferred_anchor"
    assert d.value == Decimal("100000.00")


def test_zero_buy_peak_blocks_when_no_futures():
    d = decide_anchor(
        **{
            **ACC2,
            "varmargin_net": Decimal("0"),
            "body_closed": Decimal("0"),
            "open_settled": Decimal("0"),
            "gross_buy_peak": Decimal("0"),
        }
    )
    assert d.should_anchor is False
    assert d.source == "inferred_blocked"


def test_anchor_max_factor_constant_is_50():
    assert ANCHOR_MAX_FACTOR == Decimal("50")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && PYTHONUTF8=1 C:/Python314/python.exe -m pytest tests/unit/test_opening_anchor.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'domain.pnl.opening_anchor'`

- [ ] **Step 3: Write the module**

Create `backend/domain/pnl/opening_anchor.py`:

```python
"""Opening-balance anchor decision (ADR-0010, amends ADR-0008). Pure — no I/O.

При неполной истории депозитов брокерского счёта стартовое финансирование вне
окна sync. candidate = portfolio − net_deposits − journal восстанавливает
опорную базу. Гейтим тремя deposit-НЕзависимыми проверками, чтобы не спрятать
реальный баг расчёта журнала (pv×1000 и т.п.). См. spec §3.2.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

# G1 — минимально осмысленный якорь (₽). <= → журнал ≥ кассы, восстанавливать нечего.
ANCHOR_MIN = Decimal("1")
# G2 — допуск телескопирования фьючерсного body против фактической варм-маржи.
TELESCOPE_TOL_PCT = Decimal("0.25")
# G2 отключается на счёте без фьючерсов (|varmargin_net| < этого).
VARMARGIN_FLOOR = Decimal("1")
# G3 — потолок правдоподобия: якорь не больше N× крупнейшей buy-операции.
ANCHOR_MAX_FACTOR = Decimal("50")


@dataclass(frozen=True)
class AnchorDecision:
    should_anchor: bool
    value: Decimal       # округлённый якорь (0 если не якорим)
    source: str          # 'inferred_anchor' | 'inferred_blocked' | 'complete'
    reason: str


def compute_candidate_anchor(
    *, portfolio_value: Decimal, net_deposits: Decimal, journal_pnl: Decimal
) -> Decimal:
    """Пропущенный стартовый депозит = касса − депозиты − журнал (spec §3.1)."""
    return portfolio_value - net_deposits - journal_pnl


def telescope_residual(
    *, body_closed: Decimal, varmargin_net: Decimal, open_settled: Decimal
) -> Decimal:
    """|body закрытых фьючерсов − (нетто варм-маржа − осевшая ВМ открытых)| (spec §3.2 G2)."""
    return abs(body_closed - (varmargin_net - open_settled))


def decide_anchor(
    *,
    incomplete_history: bool,
    portfolio_value: Decimal,
    net_deposits: Decimal,
    journal_pnl: Decimal,
    body_closed: Decimal,
    varmargin_net: Decimal,
    open_settled: Decimal,
    gross_buy_peak: Decimal,
) -> AnchorDecision:
    if not incomplete_history:
        return AnchorDecision(False, Decimal("0"), "complete", "first op is a deposit")

    candidate = compute_candidate_anchor(
        portfolio_value=portfolio_value,
        net_deposits=net_deposits,
        journal_pnl=journal_pnl,
    )

    # G1 — знак.
    if candidate <= ANCHOR_MIN:
        return AnchorDecision(False, Decimal("0"), "complete", "candidate<=min; nothing to restore")

    # G2 — телескоп фьючерсов (только если на счёте есть варм-маржа).
    if abs(varmargin_net) >= VARMARGIN_FLOOR:
        residual = telescope_residual(
            body_closed=body_closed, varmargin_net=varmargin_net, open_settled=open_settled
        )
        if residual > TELESCOPE_TOL_PCT * abs(varmargin_net):
            return AnchorDecision(
                False, Decimal("0"), "inferred_blocked",
                f"telescope gate failed: residual={residual} > tol",
            )

    # G3 — потолок правдоподобия.
    if candidate > ANCHOR_MAX_FACTOR * abs(gross_buy_peak):
        return AnchorDecision(
            False, Decimal("0"), "inferred_blocked",
            f"candidate={candidate} exceeds {ANCHOR_MAX_FACTOR}x buy peak",
        )

    return AnchorDecision(
        True, candidate.quantize(Decimal("0.01")), "inferred_anchor", "anchored"
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && PYTHONUTF8=1 C:/Python314/python.exe -m pytest tests/unit/test_opening_anchor.py -q`
Expected: PASS (10 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/domain/pnl/opening_anchor.py backend/tests/unit/test_opening_anchor.py
git commit -m "feat(pnl): pure opening-balance anchor decision (ADR-0010)"
```

---

### Task 2: Anchor service + pipeline stage

**Files:**
- Create: `backend/services/opening_anchor_service.py`
- Modify: `backend/application/sync/pipeline.py` (add `_stage_autoset_inferred_anchor`; call it in `run()` between `_stage_health_audit` (line ~243) and `_stage_pnl_health_check` (line ~248))
- Test: `backend/tests/integration/test_opening_anchor_service.py`

**Interfaces:**
- Consumes: `domain.pnl.opening_anchor.decide_anchor`, `AnchorDecision`; `domain.pnl.cash_flow_classification.{CashFlowCategory, operation_types_in}`.
- Produces: `autoset_inferred_anchor(session: Session, account_id: int) -> AnchorDecision` — gathers inputs, applies freeze/manual-priority, writes `Account.initial_balance` + `initial_balance_source`, commits; returns the decision (with `should_anchor=False, source` unchanged when frozen/manual).

- [ ] **Step 1: Write the failing integration tests**

Create `backend/tests/integration/test_opening_anchor_service.py`:

```python
"""Integration: anchor service against seeded in-memory DB (ADR-0010).

Покрывает: incomplete-history+healthy-futures → anchored; complete-history →
no-anchor; pv×1000 → blocked; freeze на re-sync; manual-priority.
"""
import os
import sys
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from models import Account, Base, OperationORM, PositionORM, Trade, User
from services.opening_anchor_service import autoset_inferred_anchor


@pytest.fixture
def session():
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(bind=engine)
    s = sessionmaker(bind=engine)()
    yield s
    s.close()


def _money(units):
    return int(units), 0


def _account(session, *, portfolio):
    u = User(email="anchor@test.com", hashed_password="x", is_active=1)
    session.add(u)
    session.commit()
    acc = Account(user_id=u.id, name="Main", currency="RUB", initial_balance=Decimal("0"))
    acc.last_portfolio_value = Decimal(str(portfolio))
    session.add(acc)
    session.commit()
    return acc


def _op(session, acc_id, op_type, payment_units, executed_at):
    units, nano = _money(payment_units)
    session.add(OperationORM(
        account_id=acc_id, operation_type=op_type, state="executed",
        payment_units=units, payment_nano=nano, executed_at=executed_at,
    ))


def _seed_acc2(session, *, first_op_type="buy"):
    from datetime import datetime
    acc = _account(session, portfolio=32938)
    # Стартовая операция — НЕ депозит → incomplete history.
    _op(session, acc.id, first_op_type, -93030, datetime(2026, 1, 5))
    # Депозиты позже (24-26 июня), нетто +8556 (упрощённо одной операцией).
    _op(session, acc.id, "input", 8556, datetime(2026, 6, 24))
    # Варм-маржа: нетто -86799 (accruing + writing_off).
    _op(session, acc.id, "accruing_varmargin", 10000, datetime(2026, 2, 1))
    _op(session, acc.id, "writing_off_varmargin", -96799, datetime(2026, 3, 1))
    # Закрытый фьючерсный трейд: body -70754, net -74713 (с учётом fee distribution).
    session.add(Trade(
        account_id=acc.id, symbol="MXI", instrument_type_v2="futures",
        entry_at=datetime(2026, 1, 5), exit_at=datetime(2026, 2, 5),
        pnl=Decimal("-70754"), net_pnl=Decimal("-74713"),
    ))
    # Открытая фьючерсная позиция: осевшая ВМ -7920, unrealized 0 (для простоты).
    session.add(PositionORM(
        account_id=acc.id, instrument_uid="u-mxi", unrealized_pnl=Decimal("0"),
        var_margin_rub=Decimal("-7920"),
    ))
    session.commit()
    return acc


def test_incomplete_history_healthy_futures_anchors(session):
    acc = _seed_acc2(session)
    d = autoset_inferred_anchor(session, acc.id)
    assert d.source == "inferred_anchor"
    session.refresh(acc)
    assert abs(Decimal(str(acc.initial_balance)) - Decimal("99095")) < Decimal("1")
    assert acc.initial_balance_source == "inferred_anchor"


def test_complete_history_does_not_anchor(session):
    acc = _seed_acc2(session, first_op_type="input")  # первая op = депозит
    d = autoset_inferred_anchor(session, acc.id)
    assert d.source == "complete"
    session.refresh(acc)
    assert Decimal(str(acc.initial_balance)) == Decimal("0")
    assert acc.initial_balance_source == "complete"


def test_pv_x1000_bug_is_blocked_not_hidden(session):
    acc = _seed_acc2(session)
    # Раздуваем body закрытого фьючерса в 1000x — телескоп-гейт обязан заблокировать.
    t = session.query(Trade).filter(Trade.account_id == acc.id).first()
    t.pnl = Decimal("-70754000")
    session.commit()
    d = autoset_inferred_anchor(session, acc.id)
    assert d.source == "inferred_blocked"
    session.refresh(acc)
    assert Decimal(str(acc.initial_balance)) == Decimal("0")
    assert acc.initial_balance_source == "inferred_blocked"


def test_anchor_frozen_on_resync(session):
    acc = _seed_acc2(session)
    autoset_inferred_anchor(session, acc.id)
    session.refresh(acc)
    first_value = Decimal(str(acc.initial_balance))
    # Меняется портфель (новый sync) — якорь НЕ должен пересчитаться.
    acc.last_portfolio_value = Decimal("50000")
    session.commit()
    autoset_inferred_anchor(session, acc.id)
    session.refresh(acc)
    assert Decimal(str(acc.initial_balance)) == first_value


def test_manual_source_never_overwritten(session):
    acc = _seed_acc2(session)
    acc.initial_balance = Decimal("123456")
    acc.initial_balance_source = "manual"
    session.commit()
    autoset_inferred_anchor(session, acc.id)
    session.refresh(acc)
    assert Decimal(str(acc.initial_balance)) == Decimal("123456")
    assert acc.initial_balance_source == "manual"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && PYTHONUTF8=1 C:/Python314/python.exe -m pytest tests/integration/test_opening_anchor_service.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'services.opening_anchor_service'`

- [ ] **Step 3: Write the service**

Create `backend/services/opening_anchor_service.py`:

```python
"""Сбор входов из БД + персист opening-balance anchor (ADR-0010).

Чистое решение — в domain/pnl/opening_anchor.py. Здесь только I/O:
read inputs → decide → write Account (freeze + manual-priority).
"""
from __future__ import annotations

import logging
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

import models
from domain.pnl.cash_flow_classification import CashFlowCategory, operation_types_in
from domain.pnl.opening_anchor import AnchorDecision, decide_anchor

log = logging.getLogger(__name__)

_BUY_TYPES = ("buy", "buy_card", "buy_margin")
_VARMARGIN_TYPES = ("accruing_varmargin", "writing_off_varmargin")


def _payment(units, nano) -> Decimal:
    return Decimal(int(units or 0)) + Decimal(int(nano or 0)) / Decimal(1_000_000_000)


def _sum_payment(session: Session, account_id: int, op_types: tuple[str, ...]) -> Decimal:
    if not op_types:
        return Decimal(0)
    row = session.query(
        func.coalesce(func.sum(models.OperationORM.payment_units), 0),
        func.coalesce(func.sum(models.OperationORM.payment_nano), 0),
    ).filter(
        models.OperationORM.account_id == account_id,
        models.OperationORM.state == "executed",
        models.OperationORM.operation_type.in_(op_types),
    ).one()
    return _payment(row[0], row[1])


def autoset_inferred_anchor(session: Session, account_id: int) -> AnchorDecision:
    account = session.get(models.Account, account_id)
    if account is None:
        return AnchorDecision(False, Decimal("0"), "complete", "account not found")

    # Manual имеет приоритет — никогда не перетираем (spec §3.4).
    if account.initial_balance_source == "manual":
        return AnchorDecision(False, Decimal("0"), "manual", "manual source frozen")

    # --- detect incomplete history: первая executed-операция не депозит ---
    net_dep_types = tuple(operation_types_in(CashFlowCategory.NET_DEPOSIT))
    first_op = session.query(models.OperationORM.operation_type).filter(
        models.OperationORM.account_id == account_id,
        models.OperationORM.state == "executed",
    ).order_by(models.OperationORM.executed_at.asc()).first()
    incomplete_history = first_op is not None and first_op[0] not in net_dep_types

    # --- gather inputs ---
    portfolio_value = Decimal(str(account.last_portfolio_value or 0))
    net_deposits = _sum_payment(session, account_id, net_dep_types)

    realized_closed = Decimal(str(
        session.query(func.coalesce(func.sum(models.Trade.net_pnl), 0)).filter(
            models.Trade.account_id == account_id,
            models.Trade.exit_at.isnot(None),
        ).scalar() or 0
    ))
    unrealized = Decimal(str(
        session.query(func.coalesce(func.sum(models.PositionORM.unrealized_pnl), 0)).filter(
            models.PositionORM.account_id == account_id,
        ).scalar() or 0
    ))
    journal_pnl = realized_closed + unrealized

    body_closed = Decimal(str(
        session.query(func.coalesce(func.sum(models.Trade.pnl), 0)).filter(
            models.Trade.account_id == account_id,
            models.Trade.instrument_type_v2 == "futures",
            models.Trade.exit_at.isnot(None),
        ).scalar() or 0
    ))
    varmargin_net = _sum_payment(session, account_id, _VARMARGIN_TYPES)
    open_settled = Decimal(str(
        session.query(func.coalesce(func.sum(models.PositionORM.var_margin_rub), 0)).filter(
            models.PositionORM.account_id == account_id,
        ).scalar() or 0
    ))

    buy_rows = session.query(
        models.OperationORM.payment_units, models.OperationORM.payment_nano,
    ).filter(
        models.OperationORM.account_id == account_id,
        models.OperationORM.state == "executed",
        models.OperationORM.operation_type.in_(_BUY_TYPES),
    ).all()
    gross_buy_peak = max(
        (abs(_payment(u, n)) for u, n in buy_rows), default=Decimal(0)
    )

    decision = decide_anchor(
        incomplete_history=incomplete_history,
        portfolio_value=portfolio_value,
        net_deposits=net_deposits,
        journal_pnl=journal_pnl,
        body_closed=body_closed,
        varmargin_net=varmargin_net,
        open_settled=open_settled,
        gross_buy_peak=gross_buy_peak,
    )

    # Freeze: раз поставленный inferred_anchor не двигаем, пока история не стала
    # полной (decision.source == 'complete' = появился реальный стартовый депозит).
    if account.initial_balance_source == "inferred_anchor" and decision.source != "complete":
        return AnchorDecision(False, Decimal(str(account.initial_balance or 0)),
                              "inferred_anchor", "frozen")

    account.initial_balance = decision.value
    account.initial_balance_source = decision.source
    session.commit()
    log.info(
        "opening_anchor: account_id=%s source=%s value=%s reason=%s",
        account_id, decision.source, decision.value, decision.reason,
    )
    return decision
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && PYTHONUTF8=1 C:/Python314/python.exe -m pytest tests/integration/test_opening_anchor_service.py -q`
Expected: PASS (5 passed)

> If a seeded column name mismatches your `models.py` (e.g. `Trade`/`PositionORM`/`OperationORM` required NOT-NULL fields), adjust the test seed to satisfy the schema — do NOT change the service queries (they are spec-locked).

- [ ] **Step 5: Wire the stage into the pipeline**

In `backend/application/sync/pipeline.py`, add the stage method next to `_stage_pnl_health_check` (after its definition, ~line 904):

```python
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
```

Then in `run()`, insert the call between `_stage_health_audit` and `_stage_pnl_health_check` (currently lines ~243 and ~248). After:

```python
            await asyncio.to_thread(self._stage_health_audit)
```

add:

```python
            # ADR-0010: авто-якорь баланса открытия (неполная история депозитов).
            # ДО pnl_health_check, чтобы badge считался с эффективными депозитами.
            await asyncio.to_thread(self._stage_autoset_inferred_anchor)
```

- [ ] **Step 6: Verify pipeline imports and ordering**

Run: `cd backend && PYTHONUTF8=1 C:/Python314/python.exe -c "from application.sync.pipeline import *; import inspect, application.sync.pipeline as p; src=inspect.getsource(p); a=src.index('_stage_autoset_inferred_anchor'); h=src.index('_stage_pnl_health_check'); print('OK order' if src.index('await asyncio.to_thread(self._stage_autoset_inferred_anchor)') < src.index('await asyncio.to_thread(self._stage_pnl_health_check)') else 'BAD order')"`
Expected: `OK order`

Run: `cd backend && PYTHONUTF8=1 C:/Python314/python.exe -m pytest tests/integration/test_pipeline_idempotency.py -q`
Expected: PASS (no regression)

- [ ] **Step 7: Commit**

```bash
git add backend/services/opening_anchor_service.py backend/tests/integration/test_opening_anchor_service.py backend/application/sync/pipeline.py
git commit -m "feat(pnl): persist inferred opening-balance anchor in sync pipeline (ADR-0010)"
```

---

### Task 3: Health-check cash truth uses effective deposits

**Files:**
- Modify: `backend/services/pnl_health_service.py:195-197` (cash_pnl) and `:229-233` (layer 1 base)
- Test: `backend/tests/unit/test_pnl_health.py` (add cases)

**Interfaces:**
- Consumes: `Account.initial_balance` (already loaded as `account` at `:171`).
- Produces: `compute_health` cash_pnl = `portfolio_value − net_deposits − initial_balance`; layer-1 reconstruction base = `net_deposits + initial_balance`.

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/unit/test_pnl_health.py` (append; reuse its existing in-memory session fixture — match the fixture name already in that file):

```python
def test_anchor_corrects_cash_pnl_and_badge(<session_fixture>):
    """ADR-0010: с initial_balance(anchor) cash_pnl = portfolio − net_dep − anchor,
    badge diff_pct схлопывается (acc#2: 406% → ~0)."""
    from decimal import Decimal
    from services import pnl_health_service
    from models import Account, OperationORM, PositionORM, Trade, User

    s = <session_fixture>
    u = User(email="h@test.com", hashed_password="x", is_active=1); s.add(u); s.commit()
    acc = Account(user_id=u.id, name="M", currency="RUB",
                  initial_balance=Decimal("99095"), initial_balance_source="inferred_anchor")
    acc.last_portfolio_value = Decimal("32938"); s.add(acc); s.commit()
    s.add(OperationORM(account_id=acc.id, operation_type="input", state="executed",
                       payment_units=8556, payment_nano=0))
    s.add(Trade(account_id=acc.id, symbol="MXI", instrument_type_v2="futures",
                pnl=Decimal("-70754"), net_pnl=Decimal("-74713"),
                exit_at=__import__("datetime").datetime(2026, 2, 5)))
    s.commit()

    result = pnl_health_service.compute_health(s, acc.id)
    # cash_pnl = 32938 − 8556 − 99095 = −74713 → equals journal → diff ~0.
    assert abs(result.cash_pnl - Decimal("-74713")) < Decimal("1")
    assert result.diff_pct < Decimal("25")
```

Replace `<session_fixture>` with the actual fixture used elsewhere in `test_pnl_health.py`.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && PYTHONUTF8=1 C:/Python314/python.exe -m pytest tests/unit/test_pnl_health.py::test_anchor_corrects_cash_pnl_and_badge -q`
Expected: FAIL — `cash_pnl` is `32938 − 8556 = 24382` (no anchor subtracted), diff_pct huge.

- [ ] **Step 3: Apply the fix**

In `backend/services/pnl_health_service.py`, change lines 195-197 from:

```python
    net_deposits = _sum_cash_category(session, account_id, CashFlowCategory.NET_DEPOSIT)
    portfolio_value = Decimal(account.last_portfolio_value or 0)
    cash_pnl = portfolio_value - net_deposits
```

to:

```python
    net_deposits = _sum_cash_category(session, account_id, CashFlowCategory.NET_DEPOSIT)
    portfolio_value = Decimal(account.last_portfolio_value or 0)
    # ADR-0010: эффективные депозиты = реальные + восстановленный баланс открытия
    # (для счёта с неполной историей). source='inferred_anchor'/'manual' → база
    # включает initial_balance; иначе initial_balance=0 → формула неизменна.
    initial_balance = Decimal(account.initial_balance or 0)
    effective_deposits = net_deposits + initial_balance
    cash_pnl = portfolio_value - effective_deposits
```

Then update layer-1 (line 229-233) to reconstruct against the effective base:

```python
    layer1 = cash_reconstruction_residual(
        portfolio_value=portfolio_value,
        net_deposits=effective_deposits,
        non_deposit_cash=non_deposit_cash,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && PYTHONUTF8=1 C:/Python314/python.exe -m pytest tests/unit/test_pnl_health.py -q`
Expected: PASS (new test green + all existing green — accounts with `initial_balance=0` unchanged byte-for-byte in math).

- [ ] **Step 5: Commit**

```bash
git add backend/services/pnl_health_service.py backend/tests/unit/test_pnl_health.py
git commit -m "fix(pnl): health cash-truth uses effective deposits (net + anchor) (ADR-0010)"
```

---

### Task 4: Dashboard stats — headline, ROI base, drawdown base

**Files:**
- Modify: `backend/routers/stats.py` — headline caller (`:680`), broker ROI branch (`:376-380`, `:389`), drawdown base (`:510-532`)
- Test: `backend/tests/integration/test_stats_net_pnl_endpoints.py` (add an anchored-account case; match its existing fixtures)

**Interfaces:**
- Consumes: `account_initial_balance` (= `float(account.initial_balance or 0)`, defined at `:180`); `starting_net_deposit` (`:374`); `raw_deposits` (`:671`).
- Produces: `cash_truth_pnl` correct; `total_roi` non-null for anchored broker users; `period_start_balance` set; `drawdown_baseline` includes anchor.

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/integration/test_stats_net_pnl_endpoints.py` a test that seeds a broker account with `initial_balance=99095, initial_balance_source='inferred_anchor'`, `last_portfolio_value=32938`, one `input` op of 8556, and a closed futures trade `pnl=-70754, net_pnl=-74713`; calls `GET /stats/`; asserts:

```python
    assert abs(body["cash_truth_pnl"] - (-74713)) < 2            # headline cash correct
    assert body["period_start_balance_reliable"] is True
    assert abs(body["period_start_balance"] - 107651) < 2        # 99095 + 8556
    assert body["total_roi"] is not None                         # доходность restored
```

(Mirror the TestClient + in-memory DB + auth-header setup already present in that test file; reuse its `_user_account_conn`-style helper if available, otherwise `test_broker_sync_error_handling.py`'s pattern.)

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && PYTHONUTF8=1 C:/Python314/python.exe -m pytest tests/integration/test_stats_net_pnl_endpoints.py -q -k anchor`
Expected: FAIL — `cash_truth_pnl ≈ 24382` (anchor not subtracted), `total_roi is None`, `period_start_balance` None.

- [ ] **Step 3a: Headline cash-truth — effective deposits**

In `backend/routers/stats.py`, in the `compute_pnl_headline(...)` call (line ~680) change:

```python
            net_deposits=Decimal(str(raw_deposits)),
```

to:

```python
            # ADR-0010: эффективные депозиты = реальные + восстановленный баланс открытия.
            net_deposits=Decimal(str(raw_deposits + account_initial_balance)),
```

- [ ] **Step 3b: Broker ROI base — make anchored capital reliable**

Replace the broker branch (lines ~376-380):

```python
    if is_broker_user:
        # Equity curve начинается от 0; ROI скрыт.
        starting_balance = 0.0
        period_start_balance_source = "broker_cumulative_pnl"
        period_start_balance_reliable = False  # signal к UI: ROI не показывать
```

with:

```python
    if is_broker_user:
        if account_initial_balance > 0:
            # ADR-0010: есть опорная база капитала (anchor или manual) → ROI честен.
            starting_balance = account_initial_balance + starting_net_deposit
            period_start_balance_source = "anchored_capital_base"
            period_start_balance_reliable = True
        else:
            # Без якоря базы нет — ROI по-прежнему скрыт.
            starting_balance = 0.0
            period_start_balance_source = "broker_cumulative_pnl"
            period_start_balance_reliable = False
```

Then change line ~389:

```python
    public_period_start_balance = starting_balance if not is_broker_user else None
```

to:

```python
    public_period_start_balance = (
        starting_balance if (not is_broker_user or period_start_balance_reliable) else None
    )
```

- [ ] **Step 3c: Drawdown / Calmar base — add anchor to deployed capital**

In `backend/routers/stats.py`, after the broker `drawdown_baseline` block (the `if is_broker_user:` ... ending at line ~528, right before `elif starting_balance > 0:` at line ~529), add the anchor to the deployed-capital base. Change lines ~526-528 from:

```python
            drawdown_baseline = abs(float(_row[0] or 0) + float(_row[1] or 0) / 1e9)
        if drawdown_baseline <= 0 and starting_net_deposit > 0:
            drawdown_baseline = starting_net_deposit
```

to:

```python
            drawdown_baseline = abs(float(_row[0] or 0) + float(_row[1] or 0) / 1e9)
        if drawdown_baseline <= 0 and starting_net_deposit > 0:
            drawdown_baseline = starting_net_deposit
        # ADR-0010: включаем восстановленный баланс открытия в развёрнутый капитал
        # → drawdown%/Calmar считаются от реальной базы (acc#2: 8556 → 107651).
        if account_initial_balance > 0:
            drawdown_baseline += account_initial_balance
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && PYTHONUTF8=1 C:/Python314/python.exe -m pytest tests/integration/test_stats_net_pnl_endpoints.py tests/integration/test_stats_advanced_baseline.py tests/unit/test_cagr_baseline.py -q`
Expected: PASS (new anchor case green; existing non-anchor accounts unchanged since `account_initial_balance == 0` skips every new branch).

- [ ] **Step 5: Live verification (UI numbers — mandatory per ATOM CLAUDE.md)**

Backend must import and `/stats/` must return corrected numbers for acc#2. With backend running on :8000 (env from `backend/.env.local`):

Run: `cd backend && PYTHONUTF8=1 C:/Python314/python.exe -c "from main import app; print('import ok')"`
Expected: `import ok`

Then, after a sync of acc#2 (or against current DB), confirm via the live dashboard that the equity headline % reads ≈ −69% (not −873%), `total_roi` ≈ −69%, and the equity-curve shape is unchanged (only the % base moved, not the curve). If the equity curve visibly shifts, STOP — the `starting_balance` change leaked into curve construction; revert 3b and expose a separate `roi_base` field instead.

- [ ] **Step 6: Commit**

```bash
git add backend/routers/stats.py backend/tests/integration/test_stats_net_pnl_endpoints.py
git commit -m "fix(pnl): dashboard headline/ROI/drawdown use effective deposits (ADR-0010)"
```

---

### Task 5: Frontend honesty labels by anchor source

**Files:**
- Modify: `frontend/src/app/DashboardHome.tsx` (the reconciliation/capital area near `:432-466`; `initial_balance_source` already in the `DashboardData` type at `:80`)
- Test: `frontend/src/app/__tests__/DashboardHome.anchor.test.tsx` (new) — or extend an existing DashboardHome test if present

**Interfaces:**
- Consumes: `stats.initial_balance_source` (`'inferred_anchor' | 'inferred_blocked' | 'manual' | 'complete' | null`).
- Produces: a caption rendered under the broker capital line keyed on source.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/app/__tests__/DashboardHome.anchor.test.tsx` with a small pure helper test. First add an exported pure helper to `DashboardHome.tsx` (top-level, above the component):

```tsx
export function anchorSourceLabel(source?: string | null): string | null {
  switch (source) {
    case 'inferred_anchor':
      return 'База открытия восстановлена автоматически (не подтверждена депозитами)';
    case 'inferred_blocked':
      return 'Журнал требует проверки: автоякорь не применён';
    default:
      return null;
  }
}
```

Test:

```tsx
import { describe, it, expect } from 'vitest';
import { anchorSourceLabel } from '../DashboardHome';

describe('anchorSourceLabel', () => {
  it('inferred_anchor → honest auto-restored caption', () => {
    expect(anchorSourceLabel('inferred_anchor')).toMatch(/восстановлена автоматически/);
  });
  it('inferred_blocked → journal-needs-review caption', () => {
    expect(anchorSourceLabel('inferred_blocked')).toMatch(/Журнал требует проверки/);
  });
  it('manual / complete / null → no caption', () => {
    expect(anchorSourceLabel('manual')).toBeNull();
    expect(anchorSourceLabel('complete')).toBeNull();
    expect(anchorSourceLabel(null)).toBeNull();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/app/__tests__/DashboardHome.anchor.test.tsx --maxWorkers=1`
Expected: FAIL — `anchorSourceLabel` not exported.

- [ ] **Step 3: Render the caption**

The helper from Step 1 satisfies the unit test. Now surface it in the broker capital block. In `DashboardHome.tsx`, inside the `{isBrokerUser && currentCashBalance !== null && (` block (around `:432-447`), after the existing wallet/balance line, add:

```tsx
              {anchorSourceLabel(stats?.initial_balance_source) && (
                <span className="block text-[11px] text-[var(--muted-foreground)] mt-1">
                  {anchorSourceLabel(stats?.initial_balance_source)}
                </span>
              )}
```

(Match the surrounding JSX structure exactly — wrap in the same parent the wallet line uses; do not break the existing `<span>`/fragment boundaries. Verify the diff renders one extra caption line only.)

- [ ] **Step 4: Run test + typecheck**

Run: `cd frontend && npx vitest run src/app/__tests__/DashboardHome.anchor.test.tsx --maxWorkers=1`
Expected: PASS (3 passed)

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 5: Visual check**

Open the dashboard for acc#2 in the browser. Confirm the caption "База открытия восстановлена автоматически (не подтверждена депозитами)" appears under the portfolio capital line, and the reconcile badge no longer screams 406%.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/app/DashboardHome.tsx frontend/src/app/__tests__/DashboardHome.anchor.test.tsx
git commit -m "feat(dashboard): honesty labels for inferred opening-balance anchor (ADR-0010)"
```

---

### Task 6: ADR-0010 + reconcile sanity gate + memory

**Files:**
- Create: `.business/tech/decisions/0010-inferred-opening-balance-anchor.md`
- Modify: `docs/ERROR_CATALOG.md` (cross-link the false-alarm pattern, if an ERR slot fits)
- Verify: `backend/reconcile_journal_vs_cash.py` against acc#2

- [ ] **Step 1: Write ADR-0010**

Create `.business/tech/decisions/0010-inferred-opening-balance-anchor.md` from the spec §7 outline. Required sections (ADR template, append-only):
- **Status:** Accepted. **Supersedes:** none. **Amends:** ADR-0008 (§1 headline cash now nets `initial_balance`; §3 thresholds unchanged but `diff_pct` now measures drift-from-anchor).
- **Context:** broker accounts begin trading outside the sync window → `net_deposits` incomplete → ADR-0008 `cash_truth = portfolio − net_deposits` false-positive (acc#2: +24 383 vs journal −74 713; badge 406%).
- **Decision:** `cash_truth = portfolio − (net_deposits + initial_balance)`; `initial_balance` auto-set via `candidate = portfolio − net_deposits − journal`, gated by deposit-independent G1/G2/G3 (G2 futures-telescope replaces the role of ADR-0008 layers 2/4 for the anchored case, which depend on the broken baseline).
- **Identity preserved:** `realized + unrealized + clearing_adjustment == cash_truth`; sign of `clearing_adjustment` unchanged.
- **Must NOT change without a new ADR:** removing G2; back-computing the anchor without subtracting deposits (the PR-21 `tinkoff_derived` bug); auto-overwriting `manual`.

- [ ] **Step 2: Run the full P&L regression suite**

Run: `cd backend && PYTHONUTF8=1 C:/Python314/python.exe -m pytest tests/unit/test_pnl_calculators.py tests/unit/test_pnl_health.py tests/unit/test_dashboard_pnl_headline.py tests/unit/test_opening_anchor.py tests/integration/test_opening_anchor_service.py tests/integration/test_pipeline_idempotency.py -q`
Expected: PASS (all).

- [ ] **Step 3: Reconcile sanity gate (ADR-0007 Invariant 1, mandatory)**

Run: `cd backend && PYTHONUTF8=1 C:/Python314/python.exe reconcile_journal_vs_cash.py --account-id 2`
Expected: `diff_pct` drops from ~406% to <25% (≈9% structural futures drift); `clearing_adjustment` ≈ real residual varmargin; headline cash ≈ −74 713. If `diff_pct` is still huge → the anchor did not persist (check `Account.initial_balance` for acc#2) — debug before declaring done.

- [ ] **Step 4: Commit**

```bash
git add .business/tech/decisions/0010-inferred-opening-balance-anchor.md docs/ERROR_CATALOG.md
git commit -m "docs(adr): ADR-0010 inferred opening-balance anchor (amends ADR-0008)"
```

- [ ] **Step 5: Memory note**

Append a one-line pointer to the project-state memory and (optionally) a new `project_state_2026_06_26_opening_anchor_anchor.md` snapshot describing: the false-alarm root cause (incomplete deposit baseline), the candidate formula, the deposit-independent gate, and the reconcile result for acc#2.

---

## Self-Review

**1. Spec coverage**
- §3.1 candidate formula → Task 1 (`compute_candidate_anchor`).
- §3.2 G1/G2/G3 deposit-independent gate → Task 1 (`decide_anchor`).
- §3.3 incomplete-history detect → Task 2 (`first_op not in NET_DEPOSIT`).
- §3.4 freeze + manual-priority + source values → Task 2 (service freeze logic).
- §3.5 effective_deposits in `pnl_health_service`, `dashboard_pnl` caller, stats % base → Tasks 3 & 4.
- §3.6 new pipeline stage placement (after phantom_sweep/health_audit, before pnl_health_check) → Task 2 Step 5-6.
- §3.7 UI honesty labels → Task 5.
- §4 components table → Tasks 1-5 file map.
- §5 edge cases → Task 1 tests (G1, pure-stocks, blocked, complete) + Task 2 tests (resync freeze, manual).
- §6 TDD (unit/integration/regression/sanity) → Tasks 1-6.
- §7 ADR-0010 → Task 6.
- §8 acc#2 effect (headline, badge, доходность, clearing) → Tasks 3-4 + Task 6 reconcile gate.

**2. Placeholder scan** — two intentional `<…>` markers in test seeds (`<session_fixture>` in Task 3, the helper reuse note in Task 4) point the engineer to a real existing fixture rather than inventing one; both are flagged inline with the exact substitution. No `TODO`/`TBD`/"handle edge cases".

**3. Type consistency** — `decide_anchor` keyword params identical across Task 1 (def + tests) and Task 2 (service call site). `AnchorDecision(should_anchor, value, source, reason)` consistent. Source literals identical everywhere (`inferred_anchor`/`inferred_blocked`/`complete`/`manual`). `effective_deposits = net_deposits + initial_balance` identical in Task 3 (health) and Task 4 (stats headline). Field names verified against code: `Trade.instrument_type_v2 == "futures"`, `Trade.pnl`, `Trade.net_pnl`, `PositionORM.var_margin_rub`, `PositionORM.unrealized_pnl`, `OperationORM.{payment_units,payment_nano,operation_type,state,executed_at}`, `Account.{initial_balance,initial_balance_source,last_portfolio_value}`.

**Open risk (flagged, not a gap):** Task 4 Step 3b changes `starting_balance` for broker users; if curve construction reads `starting_balance`, the equity curve could shift. Task 4 Step 5 verifies the curve is unchanged and gives the fallback (separate `roi_base` field). This is the one place needing live confirmation — consistent with ATOM's "UI change → browser verify" rule.
