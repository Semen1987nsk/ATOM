# P&L Cash-Anchored Reconciliation + 6-Layer Data-Quality Control — Backend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Сделать итог дневника тождественно равным реальным деньгам (касса) через именованную строку «клиринговая корректировка», и заменить одинокий «mismatch»-бейдж на 6-слойный контроль качества данных, который ловит грубые ошибки (×1000) громко, а нормальный фьючерсный дрейф — тихо.

**Architecture:** Чистые функции в `domain/pnl/` (тестируются без БД) + агрегатор в `services/pnl_health_service.py` (читает БД, собирает статус из слоёв) + переиспользование `reconciliation_service` (слой 5). Headline P&L = `portfolio − net_deposits`; разложение `realized + unrealized + clearing_adjustment = headline` тождественно.

**Tech Stack:** Python 3.14, SQLAlchemy 2.0, pytest, Decimal-арифметика. Frontend — отдельным планом.

**Scope:** Только backend (числа + контроль + API + ADR). Frontend (headline=касса, строка корректировки, per-layer бейдж) — отдельный план после стабилизации API.

**Спека:** [2026-05-20-pnl-cash-anchored-reconciliation-design.md](../specs/2026-05-20-pnl-cash-anchored-reconciliation-design.md)

---

## Task 1: 4 новых типа операций (слой 6, данные)

**Files:**
- Modify: `domain/enums.py` (class `OperationType`, после `ADVICE_FEE`)
- Modify: `domain/pnl/cash_flow_classification.py` (`CASH_FLOW_MAP`)
- Test: `tests/unit/test_cash_flow_classification.py`

- [ ] **Step 1: Failing test — 4 новых типа классифицированы**

В `tests/unit/test_cash_flow_classification.py` добавь в параметризацию `test_classify_canonical` строки:

```python
        (OperationType.OTHER_FEE, CashFlowCategory.ATTRIBUTABLE_FEE),
        (OperationType.OTHER, CashFlowCategory.UNKNOWN),
        (OperationType.DFA_REDEMPTION, CashFlowCategory.INCOME),
        (OperationType.PRIMARY_ORDER, CashFlowCategory.TRADE),
```

- [ ] **Step 2: Run — fail (AttributeError: OTHER_FEE)**

Run: `python -X utf8 -m pytest tests/unit/test_cash_flow_classification.py -q`
Expected: FAIL (`OperationType` has no `OTHER_FEE`).

- [ ] **Step 3: Add enum members**

В `domain/enums.py`, в `class OperationType`, сразу после строки `ADVICE_FEE = "advice_fee"`:

```python
    OTHER_FEE = "other_fee"
    OTHER = "other"
    DFA_REDEMPTION = "dfa_redemption"
    PRIMARY_ORDER = "primary_order"
```

(Proto-имена `OPERATION_TYPE_OTHER_FEE` и т.д. восстанавливаются парсером через `f"OPERATION_TYPE_{value.upper()}"` — значения совпадают.)

- [ ] **Step 4: Add CASH_FLOW_MAP entries**

В `domain/pnl/cash_flow_classification.py`, в `CASH_FLOW_MAP`, в соответствующие секции:

```python
    # OTHER_FEE — account-level сбор → распределяется как ATTRIBUTABLE_FEE
    OperationType.OTHER_FEE.value: CashFlowCategory.ATTRIBUTABLE_FEE,
    # PRIMARY_ORDER — первичное размещение → трактуем как сделку
    OperationType.PRIMARY_ORDER.value: CashFlowCategory.TRADE,
    # DFA_REDEMPTION — погашение ЦФА → денежный приток как INCOME
    OperationType.DFA_REDEMPTION.value: CashFlowCategory.INCOME,
    # OTHER — семантика неизвестна, намеренно UNKNOWN (видно в unknown-мониторинге)
    OperationType.OTHER.value: CashFlowCategory.UNKNOWN,
```

- [ ] **Step 5: Run — pass (coverage + classify)**

Run: `python -X utf8 -m pytest tests/unit/test_cash_flow_classification.py -q`
Expected: PASS (включая `test_coverage_invariant`, `test_no_extra_keys`).

- [ ] **Step 6: Commit**

```bash
git add domain/enums.py domain/pnl/cash_flow_classification.py tests/unit/test_cash_flow_classification.py
git commit -m "feat(pnl): classify 4 new T-Invest op types (OTHER_FEE/OTHER/DFA_REDEMPTION/PRIMARY_ORDER)"
```

---

## Task 2: `clearing_adjustment` + cash-anchored headline в dashboard_pnl

**Files:**
- Modify: `domain/pnl/dashboard_pnl.py`
- Test: `tests/unit/test_dashboard_pnl_headline.py`

- [ ] **Step 1: Failing test — новые поля headline_cash + clearing_adjustment + тождество**

В `tests/unit/test_dashboard_pnl_headline.py` добавь:

```python
def test_headline_cash_equals_cash_truth():
    result = compute_pnl_headline(**ACC4_INPUTS)
    assert result["headline_cash"] == result["cash_truth_pnl"]


def test_clearing_adjustment_closes_identity():
    """realized + unrealized + clearing_adjustment == headline_cash (до копейки)."""
    result = compute_pnl_headline(**ACC4_INPUTS)
    lhs = (ACC4_INPUTS["realized_closed"]
           + ACC4_INPUTS["unrealized_position_based"]
           + result["clearing_adjustment"])
    assert abs(lhs - result["headline_cash"]) < Decimal("0.01")


def test_clearing_adjustment_equals_natural_residual():
    """clearing_adjustment — это именованный natural_residual (тот же знак/величина)."""
    result = compute_pnl_headline(**ACC4_INPUTS)
    assert result["clearing_adjustment"] == result["natural_residual"]
```

- [ ] **Step 2: Run — fail (KeyError: headline_cash)**

Run: `python -X utf8 -m pytest tests/unit/test_dashboard_pnl_headline.py -q`
Expected: FAIL.

- [ ] **Step 3: Add fields to DashboardHeadline + compute**

В `domain/pnl/dashboard_pnl.py`:

В `TypedDict DashboardHeadline` добавь:

```python
    headline_cash: Decimal
    clearing_adjustment: Decimal
```

В `compute_pnl_headline`, перед `return`, после `natural_residual = ...`:

```python
    # Cash-anchored headline: главное число = реальные деньги.
    headline_cash = cash_truth_pnl
    # clearing_adjustment — именованный natural_residual: неразложимая по сделкам
    # фьючерсная вариационная маржа (API не привязывает её к контракту, см. ADR-0008).
    # Тождество: realized + unrealized + clearing_adjustment == headline_cash.
    clearing_adjustment = natural_residual
```

И в возвращаемый dict добавь:

```python
        "headline_cash": headline_cash,
        "clearing_adjustment": clearing_adjustment,
```

- [ ] **Step 4: Run — pass (новые + старые тесты)**

Run: `python -X utf8 -m pytest tests/unit/test_dashboard_pnl_headline.py -q`
Expected: PASS (старые тесты не сломаны — поля добавлены, не изменены).

- [ ] **Step 5: Commit**

```bash
git add domain/pnl/dashboard_pnl.py tests/unit/test_dashboard_pnl_headline.py
git commit -m "feat(pnl): cash-anchored headline + named clearing_adjustment line"
```

---

## Task 3: `data_quality.py` — слой 1 (cash-reconstruction residual)

**Files:**
- Create: `domain/pnl/data_quality.py`
- Test: `tests/unit/test_data_quality.py`

- [ ] **Step 1: Failing test**

Create `tests/unit/test_data_quality.py`:

```python
from decimal import Decimal
from domain.pnl.data_quality import cash_reconstruction_residual, ReconStatus


def test_cash_reconstruction_matches_within_tolerance():
    # net_deposits + Σ всех остальных категорий должно == portfolio_value
    res = cash_reconstruction_residual(
        portfolio_value=Decimal("36351.39"),
        net_deposits=Decimal("308035.79"),
        non_deposit_cash=Decimal("-271707.77"),  # сумма trade/vm/comm/fee/income/tax
    )
    assert abs(res.residual) < Decimal("100")
    assert res.status == ReconStatus.OK


def test_cash_reconstruction_flags_missing_operations():
    # пропала операция на 50k → невязка > порога → RED
    res = cash_reconstruction_residual(
        portfolio_value=Decimal("36351.39"),
        net_deposits=Decimal("308035.79"),
        non_deposit_cash=Decimal("-221707.77"),  # на 50k меньше расходов учтено
    )
    assert abs(res.residual) > Decimal("100")
    assert res.status == ReconStatus.RED
```

- [ ] **Step 2: Run — fail (ModuleNotFoundError)**

Run: `python -X utf8 -m pytest tests/unit/test_data_quality.py -q`
Expected: FAIL.

- [ ] **Step 3: Implement layer 1**

Create `domain/pnl/data_quality.py`:

```python
"""Слои контроля качества P&L-данных (чистые функции, без I/O).

ADR-0008: 6-слойная defense-in-depth проверка вместо одного «mismatch».
Каждая функция возвращает результат со status; агрегатор в
services/pnl_health_service.py берёт худший статус и указывает сработавший слой.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

# Слой 1 — допуск невязки кассовой реконструкции.
CASH_RECON_ABS_TOLERANCE = Decimal("100")   # ₽
CASH_RECON_PCT_TOLERANCE = Decimal("0.5")   # % от portfolio_value


class ReconStatus(str, Enum):
    OK = "ok"
    RED = "red"


@dataclass(frozen=True)
class LayerResult:
    layer: str
    status: ReconStatus
    residual: Decimal
    detail: str


def cash_reconstruction_residual(
    *,
    portfolio_value: Decimal,
    net_deposits: Decimal,
    non_deposit_cash: Decimal,
) -> LayerResult:
    """Слой 1: net_deposits + Σ(не-депозитные cash flows) должно == portfolio_value.

    non_deposit_cash = Σ payment всех executed операций КРОМЕ NET_DEPOSIT
    (trade+varmargin+commission+fee+income+tax+delivery). Для фьючерсных
    buy/sell payment ≈ notional (не реальный cash) — caller обязан подавать
    реальный cash (см. pnl_health_service: futures trade payments исключаются,
    их P&L идёт через varmargin). Если невязка велика — импорт неполон/задвоен.
    """
    reconstructed = net_deposits + non_deposit_cash
    residual = portfolio_value - reconstructed
    pct = (abs(residual) / abs(portfolio_value) * Decimal(100)) if portfolio_value else Decimal(0)
    ok = abs(residual) <= CASH_RECON_ABS_TOLERANCE or pct <= CASH_RECON_PCT_TOLERANCE
    return LayerResult(
        layer="cash_reconstruction",
        status=ReconStatus.OK if ok else ReconStatus.RED,
        residual=residual,
        detail=f"portfolio={portfolio_value} reconstructed={reconstructed} residual={residual}",
    )
```

- [ ] **Step 4: Run — pass**

Run: `python -X utf8 -m pytest tests/unit/test_data_quality.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add domain/pnl/data_quality.py tests/unit/test_data_quality.py
git commit -m "feat(pnl): layer 1 cash-reconstruction residual check"
```

---

## Task 4: `data_quality.py` — слой 2 (ratio-санити, анти-×1000)

**Files:**
- Modify: `domain/pnl/data_quality.py`
- Test: `tests/unit/test_data_quality.py`

- [ ] **Step 1: Failing test**

Добавь в `tests/unit/test_data_quality.py`:

```python
from domain.pnl.data_quality import ratio_sanity


def test_ratio_sanity_normal_drift_ok():
    # journal -249072, cash -271684 → ratio 0.917 → OK (нормальный 8% дрейф)
    res = ratio_sanity(journal_pnl=Decimal("-249072.79"), cash_pnl=Decimal("-271684.40"))
    assert res.status == ReconStatus.OK


def test_ratio_sanity_catches_1000x():
    # pv-баг ×1000: journal в миллионах при кассе в тысячах → RED
    res = ratio_sanity(journal_pnl=Decimal("-10261399"), cash_pnl=Decimal("-271684.40"))
    assert res.status == ReconStatus.RED


def test_ratio_sanity_na_when_cash_tiny():
    res = ratio_sanity(journal_pnl=Decimal("5"), cash_pnl=Decimal("0.5"))
    assert res.status == ReconStatus.OK  # |cash| < 1 ₽ → не судим (na-как-ok)
```

- [ ] **Step 2: Run — fail (ImportError: ratio_sanity)**

Run: `python -X utf8 -m pytest tests/unit/test_data_quality.py::test_ratio_sanity_catches_1000x -q`
Expected: FAIL.

- [ ] **Step 3: Implement layer 2**

В `domain/pnl/data_quality.py` добавь константы и функцию:

```python
# Слой 2 — допустимый коридор отношения journal/cash. Вне него = грубая
# ошибка расчёта (pv ×1000, знак, единицы). Нормальный фьючерсный дрейф ~8%
# (ratio ~0.9) внутри коридора.
RATIO_LOW = Decimal("0.3")
RATIO_HIGH = Decimal("3.0")
RATIO_NA_CASH_FLOOR = Decimal("1")  # |cash| < этого → не судим


def ratio_sanity(*, journal_pnl: Decimal, cash_pnl: Decimal) -> LayerResult:
    """Слой 2: |journal| / |cash| вне [RATIO_LOW..RATIO_HIGH] → RED.

    Ловит катастрофы класса ×1000 (раздутый body из-за point_value), знак,
    единицы. Невосприимчив к нормальному фьючерсному дрейфу (~8%).
    """
    if abs(cash_pnl) < RATIO_NA_CASH_FLOOR:
        return LayerResult("ratio_sanity", ReconStatus.OK, Decimal(0), "cash too small to judge")
    ratio = abs(journal_pnl) / abs(cash_pnl)
    ok = RATIO_LOW <= ratio <= RATIO_HIGH
    return LayerResult(
        layer="ratio_sanity",
        status=ReconStatus.OK if ok else ReconStatus.RED,
        residual=ratio,
        detail=f"|journal|/|cash| = {ratio:.3f} (band [{RATIO_LOW}..{RATIO_HIGH}])",
    )
```

- [ ] **Step 4: Run — pass**

Run: `python -X utf8 -m pytest tests/unit/test_data_quality.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add domain/pnl/data_quality.py tests/unit/test_data_quality.py
git commit -m "feat(pnl): layer 2 ratio sanity (anti-1000x guard)"
```

---

## Task 5: `data_quality.py` — слой 4 (per-trade outlier)

**Files:**
- Modify: `domain/pnl/data_quality.py`
- Test: `tests/unit/test_data_quality.py`

- [ ] **Step 1: Failing test**

Добавь:

```python
from domain.pnl.data_quality import trade_outliers


def test_trade_outliers_flags_oversized():
    # deposits=308035; трейд с |net_pnl|=200000 > 0.5×deposits → флаг
    flags = trade_outliers(
        trades=[("BBZ4", Decimal("-200000")), ("GAZP", Decimal("5000"))],
        net_deposits=Decimal("308035.79"),
        ratio_threshold=Decimal("0.5"),
    )
    assert flags == ["BBZ4"]


def test_trade_outliers_none_when_normal():
    flags = trade_outliers(
        trades=[("GAZP", Decimal("5000")), ("LKOH", Decimal("-3000"))],
        net_deposits=Decimal("308035.79"),
        ratio_threshold=Decimal("0.5"),
    )
    assert flags == []
```

- [ ] **Step 2: Run — fail**

Run: `python -X utf8 -m pytest tests/unit/test_data_quality.py::test_trade_outliers_flags_oversized -q`
Expected: FAIL.

- [ ] **Step 3: Implement layer 4**

```python
def trade_outliers(
    *,
    trades: list[tuple[str, Decimal]],
    net_deposits: Decimal,
    ratio_threshold: Decimal = Decimal("0.5"),
) -> list[str]:
    """Слой 4: символы сделок, чей |net_pnl| > ratio_threshold × |net_deposits|.

    Грубый индикатор «одна сделка съела/принесла нереалистичную долю капитала»
    — частый симптом pv/единиц-бага на конкретном инструменте.
    """
    if abs(net_deposits) < Decimal("1"):
        return []
    cap = ratio_threshold * abs(net_deposits)
    return [sym for sym, pnl in trades if abs(pnl) > cap]
```

- [ ] **Step 4: Run — pass**

Run: `python -X utf8 -m pytest tests/unit/test_data_quality.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add domain/pnl/data_quality.py tests/unit/test_data_quality.py
git commit -m "feat(pnl): layer 4 per-trade outlier detector"
```

---

## Task 6: pnl_health_service — пороги ADR-0007 (слой 3) + clearing_adjustment

**Files:**
- Modify: `services/pnl_health_service.py`
- Modify: `tests/unit/test_pnl_health.py` (существующие threshold-тесты меняются)
- Test: `tests/unit/test_pnl_health.py`

- [ ] **Step 1: Update existing threshold tests к ADR-0007 (5/25)**

В `tests/unit/test_pnl_health.py` ЗАМЕНИ значения порогов. Конкретно:

`test_threshold_constants_match_spec`:
```python
def test_threshold_constants_match_spec():
    """ADR-0008: пороги слоя 3 (клиринг-band) = ADR-0007 (5/25)."""
    assert THRESHOLD_OK_PCT == Decimal("5.0")
    assert THRESHOLD_WARNING_PCT == Decimal("25.0")
```

`test_status_ok_below_one_percent` → переименуй и поправь:
```python
def test_status_ok_below_five_percent():
    assert _status_from_diff_pct(Decimal("0.0"), Decimal("100000")) == "ok"
    assert _status_from_diff_pct(Decimal("4.99"), Decimal("100000")) == "ok"
```

`test_status_warning_between_one_and_five` →:
```python
def test_status_warning_between_five_and_twentyfive():
    assert _status_from_diff_pct(Decimal("5.0"), Decimal("100000")) == "warning"
    assert _status_from_diff_pct(Decimal("24.99"), Decimal("100000")) == "warning"
```

`test_status_mismatch_above_five_percent` →:
```python
def test_status_investigate_above_twentyfive_percent():
    assert _status_from_diff_pct(Decimal("25.0"), Decimal("100000")) == "investigate"
    assert _status_from_diff_pct(Decimal("100.0"), Decimal("100000")) == "investigate"
```

`test_status_negative_diff_uses_absolute` →:
```python
def test_status_negative_diff_uses_absolute():
    assert _status_from_diff_pct(Decimal("-4.0"), Decimal("100000")) == "ok"
    assert _status_from_diff_pct(Decimal("-10.0"), Decimal("100000")) == "warning"
    assert _status_from_diff_pct(Decimal("-30.0"), Decimal("100000")) == "investigate"
```

`test_journal_proxy_is_realized_plus_unrealized_only` — последняя строка (2% → mismatch) меняется: при 2% теперь `ok`:
```python
    assert result.diff_rub == Decimal("-100")
    assert abs(result.diff_pct - Decimal("2.0")) < Decimal("0.01")
    assert result.status == "ok"   # ADR-0008: 2% в пределах 5% band
```

`test_health_status_ok_when_small_residual` — 1% теперь `ok` (а не warning):
```python
    assert result.status == "ok"   # ADR-0008: 1% < 5% OK band
    assert abs(result.diff_pct - Decimal("1.0")) < Decimal("0.01")
```

- [ ] **Step 2: Run — fail (старые пороги)**

Run: `python -X utf8 -m pytest tests/unit/test_pnl_health.py -q`
Expected: FAIL (значения порогов/статусов не совпадают).

- [ ] **Step 3: Update thresholds + status literal в pnl_health_service.py**

В `services/pnl_health_service.py`:

```python
HealthStatus = Literal["ok", "warning", "investigate", "na", "stale"]
```

```python
# ADR-0008: пороги слоя 3 (клиринг-band) = ADR-0007.
# Нормальная фьючерсная клиринговая корректировка до 5% — ok, до 25% — warning.
THRESHOLD_OK_PCT = Decimal("5.0")
THRESHOLD_WARNING_PCT = Decimal("25.0")
```

В `_status_from_diff_pct` замени финальный `return "mismatch"` на `return "investigate"`.

- [ ] **Step 4: Run — pass**

Run: `python -X utf8 -m pytest tests/unit/test_pnl_health.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add services/pnl_health_service.py tests/unit/test_pnl_health.py
git commit -m "refactor(pnl): layer 3 thresholds to ADR-0007 (5/25), mismatch->investigate"
```

---

## Task 7: pnl_health_service — интеграция слоёв 1+2+4 (worst-of статус)

**Files:**
- Modify: `services/pnl_health_service.py`
- Test: `tests/unit/test_pnl_health.py`

- [ ] **Step 1: Failing test — компоненты слоёв в результате**

Добавь в `tests/unit/test_pnl_health.py` (использует `in_memory_session`):

```python
def test_health_includes_layer_components(in_memory_session):
    user = models.User(id=1, email="t@t.com")
    acc = models.Account(id=1, user_id=1, name="t", last_portfolio_value=Decimal("105000"))
    in_memory_session.add(user); in_memory_session.add(acc)
    closed = models.Trade(
        account_id=1, symbol="LKOH", direction="LONG",
        entry_price=100, exit_price=103, quantity=1000,
        pnl=Decimal("3000"), net_pnl=Decimal("2900"), commission=Decimal("100"),
        entry_at=datetime(2026, 5, 1), exit_at=datetime(2026, 5, 10),
    )
    op = models.OperationORM(
        operation_id="op-1", account_id=1, broker_account_id="ba-1",
        operation_type="input", state="executed",
        payment_units=100000, payment_nano=0, executed_at=datetime(2026, 4, 1),
    )
    in_memory_session.add(closed); in_memory_session.add(op)
    in_memory_session.commit()
    result = pnl_health_service.compute_health(in_memory_session, account_id=1)
    assert "clearing_adjustment" in result.components
    assert "layers" in result.components
    layers = result.components["layers"]
    assert "ratio_sanity" in layers and "cash_reconstruction" in layers
```

- [ ] **Step 2: Run — fail (no 'layers' in components)**

Run: `python -X utf8 -m pytest tests/unit/test_pnl_health.py::test_health_includes_layer_components -q`
Expected: FAIL.

- [ ] **Step 3: Wire layers into compute_health**

В `services/pnl_health_service.py` импортируй:

```python
from domain.pnl.data_quality import (
    cash_reconstruction_residual,
    ratio_sanity,
    ReconStatus,
)
```

В `compute_health`, после вычисления `journal_pnl`, `cash_pnl`, `diff_pct`, `status` (слой 3), добавь сбор слоёв 1 и 2 и worst-of. Для слоя 1 нужен `non_deposit_cash` — сумма payment всех executed ops КРОМЕ NET_DEPOSIT, причём для фьючерсных buy/sell payment исключается (futures P&L идёт через varmargin, не через notional buy/sell payment). Реализация:

```python
    # Слой 1 — non-deposit cash (futures buy/sell payments исключены: notional, не cash).
    net_deposit_types = tuple(operation_types_in(CashFlowCategory.NET_DEPOSIT))
    fut_trade_types = ("buy", "sell", "buy_card", "sell_card", "buy_margin", "sell_margin")
    non_dep_row = session.query(
        func.coalesce(func.sum(models.OperationORM.payment_units), 0),
        func.coalesce(func.sum(models.OperationORM.payment_nano), 0),
    ).filter(
        models.OperationORM.account_id == account_id,
        models.OperationORM.state == "executed",
        models.OperationORM.operation_type.notin_(net_deposit_types),
        ~(
            models.OperationORM.operation_type.in_(fut_trade_types)
            & (models.OperationORM.instrument_type == "futures")
        ),
    ).one()
    non_deposit_cash = (
        Decimal(int(non_dep_row[0] or 0))
        + Decimal(int(non_dep_row[1] or 0)) / Decimal(1_000_000_000)
    )

    layer1 = cash_reconstruction_residual(
        portfolio_value=portfolio_value,
        net_deposits=net_deposits,
        non_deposit_cash=non_deposit_cash,
    )
    layer2 = ratio_sanity(journal_pnl=journal_pnl, cash_pnl=cash_pnl)

    # Слой 4 — per-trade outliers (символ + net_pnl закрытых).
    from domain.pnl.data_quality import trade_outliers
    trade_rows = session.query(
        models.Trade.symbol, models.Trade.net_pnl,
    ).filter(
        models.Trade.account_id == account_id,
        models.Trade.exit_at.isnot(None),
    ).all()
    outlier_symbols = trade_outliers(
        trades=[(s, Decimal(p or 0)) for s, p in trade_rows],
        net_deposits=net_deposits,
    )

    band_status = status  # слой 3 (diff_pct band), вычислен выше
    # worst-of: RED любого слоя → 'investigate' (громкая страховка от ×1000)
    if ReconStatus.RED in (layer1.status, layer2.status):
        status = "investigate"
    elif outlier_symbols and status == "ok":
        status = "warning"
```

И в `components` добавь:

```python
        "clearing_adjustment": diff_rub,
        "layers": {
            "clearing_band": band_status,      # слой 3 (исходный diff_pct band)
            "cash_reconstruction": layer1.status.value,
            "ratio_sanity": layer2.status.value,
            "trade_outliers": "warning" if outlier_symbols else "ok",
        },
        "cash_reconstruction_residual": layer1.residual,
        "ratio": layer2.residual,
        "outlier_symbols": outlier_symbols,
```

(Примечание: `band_status` = статус слоя 3 ДО worst-of, чтобы в `layers["clearing_band"]` попал именно band-статус, а итоговый `status` = worst-of по всем слоям.)

- [ ] **Step 4: Run — pass (+ регрессия health)**

Run: `python -X utf8 -m pytest tests/unit/test_pnl_health.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add services/pnl_health_service.py tests/unit/test_pnl_health.py
git commit -m "feat(pnl): integrate layers 1+2 (cash-recon, ratio) into health, worst-of status"
```

---

## Task 8: слой 6 — unknown-типы как warning в health

**Files:**
- Modify: `services/pnl_health_service.py`
- Test: `tests/unit/test_pnl_health.py`

- [ ] **Step 1: Failing test**

```python
def test_health_flags_unknown_op_with_cash(in_memory_session):
    user = models.User(id=1, email="t@t.com")
    acc = models.Account(id=1, user_id=1, name="t", last_portfolio_value=Decimal("100000"))
    in_memory_session.add(user); in_memory_session.add(acc)
    in_memory_session.add(models.OperationORM(
        operation_id="op-d", account_id=1, broker_account_id="ba",
        operation_type="input", state="executed",
        payment_units=100000, payment_nano=0, executed_at=datetime(2026, 4, 1)))
    # неизвестный тип с cash-эффектом
    in_memory_session.add(models.OperationORM(
        operation_id="op-x", account_id=1, broker_account_id="ba",
        operation_type="totally_new_2099", state="executed",
        payment_units=-500, payment_nano=0, executed_at=datetime(2026, 4, 2)))
    in_memory_session.commit()
    result = pnl_health_service.compute_health(in_memory_session, account_id=1)
    assert result.components["layers"]["unknown_types"] in ("warning", "red")
    assert "totally_new_2099" in str(result.components.get("unknown_types_detail", ""))
```

- [ ] **Step 2: Run — fail**

Run: `python -X utf8 -m pytest tests/unit/test_pnl_health.py::test_health_flags_unknown_op_with_cash -q`
Expected: FAIL.

- [ ] **Step 3: Implement layer 6 in compute_health**

В `compute_health` добавь (после слоёв 1,2), импортнув `from domain.pnl.cash_flow_classification import CASH_FLOW_MAP`:

```python
    # Слой 6 — операции с cash-эффектом, тип которых не в CASH_FLOW_MAP.
    known_types = tuple(CASH_FLOW_MAP.keys())
    unknown_rows = session.query(
        models.OperationORM.operation_type,
        func.count(),
    ).filter(
        models.OperationORM.account_id == account_id,
        models.OperationORM.state == "executed",
        models.OperationORM.operation_type.notin_(known_types),
    ).group_by(models.OperationORM.operation_type).all()
    unknown_detail = {t: int(c) for t, c in unknown_rows}
    unknown_status = "warning" if unknown_detail else "ok"
    if unknown_detail and status == "ok":
        status = "warning"
```

И добавь в `components["layers"]`:
```python
            "unknown_types": unknown_status,
```
и в `components`:
```python
        "unknown_types_detail": unknown_detail,
```

- [ ] **Step 4: Run — pass**

Run: `python -X utf8 -m pytest tests/unit/test_pnl_health.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add services/pnl_health_service.py tests/unit/test_pnl_health.py
git commit -m "feat(pnl): layer 6 unknown op-type warning in health"
```

---

## Task 9: слой 5 — surface reconciliation_service в health

**Files:**
- Modify: `services/pnl_health_service.py`
- Test: `tests/unit/test_pnl_health.py`

**Контекст:** `services/reconciliation_service.py` уже сравнивает наши агрегаты vs broker_report (commission, trade_count, realized) и возвращает `ReconciliationResult` со статусом hard/soft/ok. Слой 5 = прочитать ПОСЛЕДНИЙ `ReconciliationRunORM` для аккаунта и поднять его статус в health-агрегат (без повторного запуска тяжёлой сверки).

- [ ] **Step 1: Failing test**

```python
def test_health_surfaces_last_reconciliation(in_memory_session):
    import json
    user = models.User(id=1, email="t@t.com")
    acc = models.Account(id=1, user_id=1, name="t", last_portfolio_value=Decimal("100000"))
    in_memory_session.add(user); in_memory_session.add(acc)
    in_memory_session.add(models.OperationORM(
        operation_id="op", account_id=1, broker_account_id="ba",
        operation_type="input", state="executed",
        payment_units=100000, payment_nano=0, executed_at=datetime(2026, 4, 1)))
    in_memory_session.add(models.ReconciliationRunORM(
        account_id=1, status="break", breaks_count=1,
        started_at=datetime(2026, 5, 20), finished_at=datetime(2026, 5, 20),
        metrics=json.dumps({"trade_count": {"ours": "5", "broker": "6", "status": "hard"}})))
    in_memory_session.commit()
    result = pnl_health_service.compute_health(in_memory_session, account_id=1)
    assert result.components["layers"]["three_way_recon"] in ("break", "warning", "ok")
```

- [ ] **Step 2: Run — fail**

Run: `python -X utf8 -m pytest tests/unit/test_pnl_health.py::test_health_surfaces_last_reconciliation -q`
Expected: FAIL.

- [ ] **Step 3: Implement layer 5 surfacing**

В `compute_health`:

```python
    # Слой 5 — последний прогон трёхсторонней сверки (operations↔broker_report↔portfolio).
    last_recon = (
        session.query(models.ReconciliationRunORM)
        .filter(models.ReconciliationRunORM.account_id == account_id)
        .order_by(models.ReconciliationRunORM.started_at.desc())
        .first()
    )
    if last_recon is None:
        recon_status = "na"
    elif last_recon.status == "break":
        recon_status = "break"
        if status == "ok":
            status = "warning"
    else:
        recon_status = last_recon.status
```

Добавь в `components["layers"]`:
```python
            "three_way_recon": recon_status,
```

(Проверь точное имя ORM-класса в `models.py` — `ReconciliationRunORM`; если иначе, используй фактическое.)

- [ ] **Step 4: Run — pass**

Run: `python -X utf8 -m pytest tests/unit/test_pnl_health.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add services/pnl_health_service.py tests/unit/test_pnl_health.py
git commit -m "feat(pnl): layer 5 surface last three-way reconciliation into health"
```

---

## Task 10: endpoint отдаёт clearing_adjustment + per-layer health

**Files:**
- Modify: `routers/real_pnl.py` (или dashboard endpoint, который кормит headline)
- Test: `tests/integration/test_real_pnl_endpoint.py` (создать если нет — следуй паттерну существующих integration-тестов с TestClient)

- [ ] **Step 1: Failing test**

Создай/дополни integration-тест, который мокает live `get_portfolio_raw` и проверяет, что ответ содержит `clearing_adjustment` и `health_layers`. (Следуй паттерну существующих integration-тестов: `tests/integration/` + FastAPI `TestClient` + override `get_db`/`get_current_user`.)

```python
def test_real_pnl_returns_clearing_adjustment_and_layers(client_with_acc4_data, mock_portfolio):
    resp = client_with_acc4_data.get("/real-pnl/")
    assert resp.status_code == 200
    body = resp.json()
    assert "clearing_adjustment" in body
    assert "health_layers" in body
```

- [ ] **Step 2: Run — fail**

Run: `python -X utf8 -m pytest tests/integration/test_real_pnl_endpoint.py -q`
Expected: FAIL.

- [ ] **Step 3: Add fields to endpoint response**

В `routers/real_pnl.py` после вычисления `real_pnl`, вызови `pnl_health_service.compute_health(db, account.id)` и добавь в return:

```python
        "clearing_adjustment": round(float(health.components.get("clearing_adjustment", 0)), 2),
        "health_status": health.status,
        "health_layers": health.components.get("layers", {}),
```

(Импортируй `from services import pnl_health_service`.)

- [ ] **Step 4: Run — pass**

Run: `python -X utf8 -m pytest tests/integration/test_real_pnl_endpoint.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add routers/real_pnl.py tests/integration/test_real_pnl_endpoint.py
git commit -m "feat(pnl): expose clearing_adjustment + per-layer health in /real-pnl"
```

---

## Task 11: ADR-0008 + reconcile-тулза consistency

**Files:**
- Create: `.business/tech/decisions/0008-pnl-cash-anchored-6layer-control.md`
- Modify: `tools/reconcile_journal_vs_cash.py` (вывести clearing_adjustment строкой)
- Modify: `docs/PNL_PLAYBOOK.md` (ссылка на ADR-0008 + 6 слоёв)

- [ ] **Step 1: Write ADR-0008**

Создай `.business/tech/decisions/0008-pnl-cash-anchored-6layer-control.md` со структурой ADR (Статус: Принято; Контекст: расследование 2026-05-20, per-contract VM недоступна через API — проверено вживую; Решение: headline=касса + clearing_adjustment + 6-слойный контроль; пороги слоя 3 амендят Инв.1 ADR-0007 на 5/25; Что НЕЛЬЗЯ менять: убирать слой 2 ratio-санити; Вне scope: self-reconstruction VM по ценам 19:00+FX как будущая опция).

- [ ] **Step 2: Update reconcile tool output**

В `tools/reconcile_journal_vs_cash.py::print_result`, в секции `[Diff]`, добавь строку:
```python
    print(f"  clearing_adjustment (= diff):   {d['abs']:>16,.2f} ₽  ← неразложимая фьюч. вармаржа")
```

- [ ] **Step 3: Verify reconcile on acc#4 (manual, чтение)**

Run: `python -X utf8 -m tools.reconcile_journal_vs_cash --account-id 4`
Expected: выводит journal/cash/diff и строку clearing_adjustment; diff ≈ 22 611 ₽.

- [ ] **Step 4: Commit**

```bash
git add .business/tech/decisions/0008-pnl-cash-anchored-6layer-control.md tools/reconcile_journal_vs_cash.py docs/PNL_PLAYBOOK.md
git commit -m "docs(pnl): ADR-0008 cash-anchored + 6-layer control; reconcile tool clearing line"
```

---

## Финальная проверка (после всех задач)

- [ ] **Полный прогон P&L-тестов**

Run:
```bash
python -X utf8 -m pytest tests/unit/test_pnl_calculators.py tests/unit/test_pnl_health.py tests/unit/test_journal_cash_reconcile.py tests/unit/test_dashboard_pnl_headline.py tests/unit/test_cash_flow_classification.py tests/unit/test_data_quality.py -q
```
Expected: всё зелёное.

- [ ] **Sanity на acc#4 (mandatory, memory feedback_pnl_cash_sanity_check)**

Run: `python -X utf8 -m tools.reconcile_journal_vs_cash --account-id 4`
Expected: `realized + unrealized + clearing_adjustment == cash` (тождество); ratio в норме; нет новых HARD breaks.

- [ ] **Backend импортится**

Run: `python -X utf8 -c "from main import app; print('ok')"`
Expected: `ok`.
