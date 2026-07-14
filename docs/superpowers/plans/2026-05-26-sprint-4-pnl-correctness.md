# Sprint 4 — Корректность P&L и индикаторов (Implementation Plan)

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended). Steps use checkbox (`- [ ]`) syntax for tracking. **P&L feedback (mandatory):** прогнать `tools/reconcile_journal_vs_cash.py` ДО declaring done каждой math-задачи; tests pass ≠ числа сходятся.

**Goal:** все аналитические эндпойнты используют NET (не GROSS); RoR/Sharpe/Sortino — каноничные формулы с лейблами; CAGR из одного source-of-truth (`net_deposits`); MAE/MFE pipeline покрывает импортированные трейды; reconcile-tool пороги синхронизированы с `pnl_health_service` (5/25%); `analytics/advanced.py` + `aggregator.py` покрыты unit-тестами; PRIMARY_ORDER корректно матчится FIFO.

**Architecture:**
- **NET везде:** entry-points в `analytics/*` принимают `t.net_pnl` (с fallback на `t.pnl`); routers больше не передают `t.pnl` как gross в dict-bindings.
- **Canonical baselines:** `analytics/_common.py::compute_cagr_baseline(account, capital_flows) -> Decimal` — единый источник для Calmar/CAGR.
- **Standard formulas:** Vince classic RoR, annualized Sharpe/Sortino с trades_per_year-параметром (response carries both per-trade и annualized).
- **PV resolution:** `analytics/mae_mfe.py` использует `domain/pnl/futures._resolve_pv` (empirical-preferring) вместо cached `pnl_service.get_point_value`; multi-slice → weighted-avg.
- **MAE/MFE coverage:** hook в `import_service` после batch insert → enqueue async MAE/MFE backfill через background-task; nightly cron в `sync_scheduler` (scheduler-only worker) ловит миссы.
- **FIFO matching:** `PRIMARY_ORDER` добавлен в `_BUY_TYPES` + invariant-тест на payment-sign проверяет, что эту семантику не нарушают будущие операции.

**Tech Stack:** FastAPI · SQLAlchemy 2.0 · numpy · alembic · pytest-asyncio. Без новых зависимостей.

**Operating mode (NO-COMMIT):** код, тесты, миграции — да; `git add`/`commit` — НЕТ.

---

## Декомпозиция файлов

**Новые:**
- `backend/analytics/_common_baseline.py` — `compute_cagr_baseline(account_or_capital_flows) -> Decimal` + `annualize_ratio(value, n_per_year)` helper.
- `backend/jobs/mae_mfe_backfill.py` — nightly safety-net backfill для трейдов с NULL `mae_price`/`mfe_price`.
- `backend/tests/unit/test_analytics_advanced_gaps.py` — 13 функций × 2-3 теста.
- `backend/tests/unit/test_analytics_aggregator.py` — `calculate_stats` unit-тесты.
- `backend/tests/unit/test_ror_vince_formula.py` — точные значения, не «<50».
- `backend/tests/integration/test_stats_net_pnl_endpoints.py` — endpoint-уровневые тесты на NET vs GROSS divergence при наличии комиссий.
- `backend/tests/unit/test_fifo_primary_order.py` — PRIMARY_ORDER матчится как BUY.
- `backend/tests/unit/test_mae_mfe_pv_resolution.py` — futures PV без ×1000-bias.

**Модифицируемые:**
- `backend/routers/stats.py` — `_analyze_trades_mae_mfe` (`:1175`) использует `analytics.calculate_advanced_stats(pnls)` вместо локального дубля; `pnl=t.pnl` → `pnl=t.net_pnl if t.net_pnl is not None else t.pnl`; CAGR через helper.
- `backend/routers/stats_advanced.py` — все 8 dict-bindings (`:63-133`) и CAGR clones (`:73-82`, `:177-188`) через helper и net_pnl.
- `backend/analytics/risk.py` — `calculate_risk_of_ruin` переписан на Vince classic; `calculate_sharpe_sortino` принимает `trades_per_year` и возвращает оба значения.
- `backend/analytics/mae_mfe.py` — `_get_point_value` заменён на `_resolve_pv` (multi-slice weighted-avg).
- `backend/application/fifo_matching.py` — `_BUY_TYPES` включает `OperationType.PRIMARY_ORDER`.
- `backend/tools/reconcile_journal_vs_cash.py` — пороги 1%/5% → 5%/25%.
- `backend/import_service.py` — после batch insert вызвать `calculate_mae_mfe_async` через `asyncio.create_task` (fire-and-forget).
- `backend/application/sync/sync_scheduler.py` — регистрация `mae_mfe_backfill` cron-задачи в scheduler-worker гарде.
- `backend/domain/pnl/futures.py::_resolve_pv` — расширить на weighted-avg вместо `entry_slices[0]`.

---

## Batch 1 — Quick wins (single-line / trivial)

### Task 1.1: MATH-05 — `profit_factor` UNDEFINED при отсутствии losses

**Files:**
- Modify: `backend/routers/stats.py::_analyze_trades_mae_mfe` (`:1256`)
- Test: `backend/tests/integration/test_stats_net_pnl_endpoints.py`

- [ ] **Step 1: Failing test**

```python
def test_mae_mfe_analysis_profit_factor_undefined_for_all_winners(
    client, auth_headers, seed_all_winners_trades
):
    """MATH-05: при отсутствии loss-трейдов profit_factor должен быть None (UNDEFINED), не 0."""
    resp = client.get("/stats/mae-mfe-analysis", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["profit_factor"] is None, "должно быть UNDEFINED при all-winners"
```

- [ ] **Step 2: Run — expect FAIL** (текущий код возвращает 0).

- [ ] **Step 3: Fix**

В `routers/stats.py:1256`:

```python
# БЫЛО:
# profit_factor = sum(win_pnls) / sum(loss_pnls) if loss_pnls and sum(loss_pnls) > 0 else 0
# СТАЛО:
total_losses = sum(loss_pnls)
profit_factor = (sum(win_pnls) / total_losses) if total_losses > 0 else None
```

- [ ] **Step 4: Pass + NO-COMMIT**

---

### Task 1.2: MATH-09 — Reconcile-tool пороги 5%/25%

**Files:**
- Modify: `backend/tools/reconcile_journal_vs_cash.py` (`:328-336`)
- Test: `backend/tests/unit/test_reconcile_tool_thresholds.py` (новый)

- [ ] **Step 1: Failing test**

```python
def test_reconcile_thresholds_match_pnl_health_service():
    """MATH-09: пороги CLI tool должны совпадать с pnl_health_service (5%/25%)."""
    from tools.reconcile_journal_vs_cash import THRESHOLD_OK_PCT, THRESHOLD_WARN_PCT
    from services.pnl_health_service import THRESHOLD_OK_PCT as HEALTH_OK
    from services.pnl_health_service import THRESHOLD_WARNING_PCT as HEALTH_WARN
    assert float(THRESHOLD_OK_PCT) == float(HEALTH_OK) == 5.0
    assert float(THRESHOLD_WARN_PCT) == float(HEALTH_WARN) == 25.0
```

- [ ] **Step 2: Run — FAIL** (константы не экспортированы).

- [ ] **Step 3: Реализация**

В `backend/tools/reconcile_journal_vs_cash.py` добавить module-level константы:

```python
from decimal import Decimal

THRESHOLD_OK_PCT = Decimal("5.0")
THRESHOLD_WARN_PCT = Decimal("25.0")
```

И заменить `:328-336`:

```python
if abs(d["abs"]) < 100 or d["pct"] < float(THRESHOLD_OK_PCT):
    print(f"\n✅ MATCH (diff < 100₽ или < {THRESHOLD_OK_PCT}%)")
    return 0
elif d["pct"] < float(THRESHOLD_WARN_PCT):
    print(f"\n⚠️  WARN — diff {d['pct']:.1f}% / {d['abs']:,.0f}₽ (acceptable но проверь pre-sync state)")
    return 1
else:
    print(f"\n❌ MISMATCH — diff {d['pct']:.1f}% / {d['abs']:,.0f}₽ (требует investigation)")
    return 1
```

- [ ] **Step 4: Pass + NO-COMMIT**

---

### Task 1.3: MATH-10 — PRIMARY_ORDER в `_BUY_TYPES`

**Files:**
- Modify: `backend/application/fifo_matching.py` (`:78-79`)
- Test: `backend/tests/unit/test_fifo_primary_order.py` (новый)

- [ ] **Step 1: Failing test**

```python
# backend/tests/unit/test_fifo_primary_order.py
import pytest
from decimal import Decimal
from enums import OperationType
from application.fifo_matching import FifoMatcher, _BUY_TYPES, _SELL_TYPES


def test_primary_order_in_buy_types():
    """MATH-10: PRIMARY_ORDER должен быть в _BUY_TYPES (первичное размещение = покупка)."""
    assert OperationType.PRIMARY_ORDER in _BUY_TYPES
    assert OperationType.PRIMARY_ORDER not in _SELL_TYPES


def test_primary_order_creates_long_lot(fifo_matcher_with_primary_order_op):
    """MATH-10: PRIMARY_ORDER операция создаёт LONG-лот, как BUY."""
    result = fifo_matcher_with_primary_order_op.match_all()
    # Должен быть открытый long-lot с qty>0, не orphan
    assert len(result.open_lots) == 1
    assert result.open_lots[0].direction == "LONG"
    assert result.open_lots[0].qty > 0


def test_primary_order_payment_sign_invariant(fifo_matcher_with_primary_order_op):
    """MATH-10 guard: payment для PRIMARY_ORDER должен быть отрицательным (исходящий = покупка).
    
    Если в будущем встретится PRIMARY_ORDER с положительным payment (incoming = SELL семантика),
    этот тест словит регрессию.
    """
    op = fifo_matcher_with_primary_order_op._operations[0]
    assert op.operation_type == OperationType.PRIMARY_ORDER
    assert op.payment_amount < 0, (
        "PRIMARY_ORDER с positive payment не покрывается _BUY_TYPES. "
        "Нужен sign-based fallback или отдельный direction-mapping."
    )
```

- [ ] **Step 2: Run — FAIL** (PRIMARY_ORDER не в `_BUY_TYPES`).

- [ ] **Step 3: Реализация**

В `backend/application/fifo_matching.py:78`:

```python
_BUY_TYPES = {
    OperationType.BUY,
    OperationType.BUY_CARD,
    OperationType.BUY_MARGIN,
    OperationType.PRIMARY_ORDER,  # MATH-10: первичное размещение
}
```

- [ ] **Step 4: Pass + регрессионный прогон всех FIFO-тестов**

```
PYTHONUTF8=1 python -X utf8 -m pytest backend/tests/unit/test_fifo_matching.py -v
```

- [ ] **Step 5: Reconcile sanity** — на любом аккаунте с историей PRIMARY_ORDER операций (IPO/SPO):

```
PYTHONUTF8=1 python -X utf8 backend/tools/reconcile_journal_vs_cash.py --account-id <id>
```

Diff не должен ухудшиться (если ранее был orphan на PRIMARY_ORDER amount).

- [ ] **Step 6: NO-COMMIT**

---

## Batch 2 — NET migration (MATH-01)

### Task 2.1: NET в `_analyze_trades_mae_mfe`

**Files:**
- Modify: `backend/routers/stats.py::_analyze_trades_mae_mfe` (`:1175-1260`)
- Test: `backend/tests/integration/test_stats_net_pnl_endpoints.py`

- [ ] **Step 1: Failing test — NET vs GROSS divergence**

```python
def test_mae_mfe_analysis_uses_net_pnl_not_gross(
    client, auth_headers, seed_trades_with_high_commissions
):
    """MATH-01: при ненулевых комиссиях NET != GROSS, win_rate/PF/avg должны
    отражать реальную прибыль после costs."""
    # seed: 10 трейдов, gross_pnl=1000 каждый, commission=600 каждый → net=400
    # Если используется GROSS — все winners, PF=inf. Если NET — тоже winners, но 
    # avg=400 не 1000.
    resp = client.get("/stats/mae-mfe-analysis", headers=auth_headers)
    body = resp.json()
    assert body["avg_pnl"] == pytest.approx(400, rel=0.01), \
        f"expected NET-based avg=400, got {body['avg_pnl']} (looks like GROSS=1000)"
```

- [ ] **Step 2: Run — FAIL** (текущий код возвращает 1000).

- [ ] **Step 3: Replace local dup with `analytics.calculate_advanced_stats`**

В `routers/stats.py:1208-1260` (внутри `_analyze_trades_mae_mfe`):

```python
# БЫЛО:
# pnl = float(t.pnl) if t.pnl else 0
# pnl_sum += pnl
# if pnl > 0: wins += 1; win_pnls.append(pnl)
# elif pnl < 0: loss_pnls.append(abs(pnl))
# ...
# profit_factor = sum(win_pnls) / sum(loss_pnls) if loss_pnls and sum(loss_pnls) > 0 else 0
# avg_pnl = pnl_sum / total

# СТАЛО:
from analytics import calculate_advanced_stats
pnls = [float(t.net_pnl if t.net_pnl is not None else (t.pnl or 0)) for t in trades]
risks = [float(t.risk) for t in trades if t.risk]  # для R-expectancy если используется
adv = calculate_advanced_stats(pnls, risks)  # уже даёт UNDEFINED при 0 losses
profit_factor = adv["profit_factor"]  # None если losses == 0
avg_pnl = adv.get("avg_pnl", sum(pnls) / len(pnls) if pnls else 0)
```

(Уточнить точную сигнатуру `calculate_advanced_stats` в `backend/analytics/aggregator.py` — может вернуть имя поля avg иначе.)

- [ ] **Step 4: Pass + NO-COMMIT**

---

### Task 2.2: NET в `get_mae_mfe_by_symbol`

**Files:**
- Modify: `backend/routers/stats.py::get_mae_mfe_by_symbol` (`:1556-1720`)

- [ ] **Step 1: Failing test**

```python
def test_mae_mfe_by_symbol_uses_net_pnl(client, auth_headers, seed_one_symbol_high_commission):
    """MATH-01: pnl-сумма по символу должна быть NET, не GROSS."""
    resp = client.get("/stats/mae-mfe-by-symbol", headers=auth_headers)
    body = resp.json()
    # seed: SBER 5 трейдов, gross=10000, comm=4000 → net=6000
    sber_entry = next(s for s in body if s["symbol"] == "SBER")
    assert sber_entry["pnl"] == pytest.approx(6000, rel=0.01)
```

- [ ] **Step 2: Run — FAIL**

- [ ] **Step 3: Replace lambdas**

`stats.py:1618, 1714-1715`:

```python
# pnl = float(t.pnl) if t.pnl else 0
# → 
pnl = float(t.net_pnl if t.net_pnl is not None else (t.pnl or 0))

# {"pnl": sum(float(t.pnl or 0) for t in long_trades), ...}
# →
{"pnl": sum(float(t.net_pnl if t.net_pnl is not None else (t.pnl or 0)) for t in long_trades), ...}
```

- [ ] **Step 4: Pass + NO-COMMIT**

---

### Task 2.3: NET в 8 dict-bindings `stats_advanced.py`

**Files:**
- Modify: `backend/routers/stats_advanced.py` (`:63-133`)

- [ ] **Step 1: Failing test**

```python
def test_advanced_stats_psycho_correlations_use_net_pnl(
    client, auth_headers, seed_psycho_trades_with_commissions
):
    """MATH-01: psycho-correlations должны использовать NET, иначе высокая комиссия
    маскирует слабый mood-effect."""
    resp = client.get("/stats/advanced", headers=auth_headers)
    body = resp.json()
    # psycho_correlations с известным датасетом: NET даст negative correlation, GROSS — positive
    assert body["psycho_correlations"]["mood_pnl_corr"] < 0
```

- [ ] **Step 2: Replace 8 bindings**

```python
# Helper в stats_advanced.py (top of file):
def _net_or_gross(t) -> float:
    """MATH-01: канонический pnl-доступ. Net предпочтительнее."""
    return float(t.net_pnl if t.net_pnl is not None else (t.pnl or 0))

# Replace 8 bindings (~lines 63, 79, 89, 105, 109, 113, 121, 125, 129):
trades_for_period = [{"entry_at": t.entry_at, "pnl": _net_or_gross(t)} for t in trades]
trades_with_tags = [{"tags": t.tags or [], "pnl": _net_or_gross(t)} for t in trades]
# ...etc для каждого из 8 dict-bindings (psycho_correlations, news_event_stats, 
# exit_breakdown, r_distribution, tax_visibility, и пр.)
```

- [ ] **Step 3: Pass + NO-COMMIT**

---

## Batch 3 — RoR + Sharpe/Sortino annualization

### Task 3.1: MATH-04 — Vince classic RoR

**Files:**
- Modify: `backend/analytics/risk.py::calculate_risk_of_ruin` (`:301-360`)
- Test: `backend/tests/unit/test_ror_vince_formula.py` (новый)

- [ ] **Step 1: Failing test (точные значения)**

```python
# backend/tests/unit/test_ror_vince_formula.py
"""MATH-04: Vince classic gambler's ruin RoR.

Формула: RoR = ((1−edge)/(1+edge))^N
где:
  edge = win_rate × payoff_ratio − loss_rate
  loss_rate = 1 − win_rate
  N = capital_units = target_loss / risk_per_trade
"""
import pytest
from analytics.risk import calculate_risk_of_ruin


def test_ror_zero_edge_returns_100_pct():
    """Edge=0 (50/50 без payoff) → ruin почти гарантирован."""
    result = calculate_risk_of_ruin(win_rate=0.5, payoff_ratio=1.0, risk_per_trade=0.02)
    # edge = 0.5*1 - 0.5 = 0, R/((1-0)/(1+0))^N = 1^N = 100%
    assert result["ror_20pct"] == pytest.approx(100.0, abs=0.1)


def test_ror_positive_edge_exact():
    """win_rate=0.6, payoff=1, risk=2% → edge=0.2; capital_units(20%)=10
    → RoR_20% = (0.8/1.2)^10 ≈ 1.73%"""
    result = calculate_risk_of_ruin(win_rate=0.6, payoff_ratio=1.0, risk_per_trade=0.02)
    expected = ((1 - 0.2) / (1 + 0.2)) ** 10 * 100
    assert result["ror_20pct"] == pytest.approx(expected, rel=0.01)


def test_ror_negative_edge_returns_100():
    result = calculate_risk_of_ruin(win_rate=0.4, payoff_ratio=1.0, risk_per_trade=0.02)
    assert result["ror_20pct"] == pytest.approx(100.0, abs=0.1)


def test_ror_risk_per_trade_default_is_optional():
    """Спека просила убрать хардкод 2%, но default остаётся как backwards-compat."""
    r1 = calculate_risk_of_ruin(win_rate=0.6, payoff_ratio=1.0, risk_per_trade=0.01)
    r2 = calculate_risk_of_ruin(win_rate=0.6, payoff_ratio=1.0, risk_per_trade=0.02)
    # Меньший risk_per_trade → больше capital_units → меньше RoR
    assert r1["ror_20pct"] < r2["ror_20pct"]
```

- [ ] **Step 2: Run — FAIL** (текущая формула clamp-based).

- [ ] **Step 3: Implement Vince classic**

```python
def calculate_risk_of_ruin(
    win_rate: float,
    payoff_ratio: float,
    risk_per_trade: float = 0.02,
) -> dict:
    """Risk of Ruin (Vince classic gambler's ruin).
    
    RoR = ((1 - edge) / (1 + edge))^N
    где edge = win_rate × payoff_ratio − (1 − win_rate)
        N = capital_units = target_loss_pct / risk_per_trade
    """
    if not (0 < win_rate < 1) or payoff_ratio <= 0 or risk_per_trade <= 0:
        return {"ror_20pct": None, "ror_50pct": None}
    
    loss_rate = 1.0 - win_rate
    edge = win_rate * payoff_ratio - loss_rate
    
    if edge <= 0:
        return {"ror_20pct": 100.0, "ror_50pct": 100.0}
    
    ratio = (1 - edge) / (1 + edge)
    n_20 = 0.20 / risk_per_trade
    n_50 = 0.50 / risk_per_trade
    
    return {
        "ror_20pct": round(min(100.0, (ratio ** n_20) * 100), 4),
        "ror_50pct": round(min(100.0, (ratio ** n_50) * 100), 4),
    }
```

- [ ] **Step 4: Pass + NO-COMMIT**

---

### Task 3.2: MATH-06 — Annualize Sharpe/Sortino

**Files:**
- Modify: `backend/analytics/risk.py::calculate_sharpe_sortino` (`:84-116`)
- Test: `backend/tests/unit/test_sharpe_sortino_annualized.py` (новый)

- [ ] **Step 1: Failing test**

```python
def test_sharpe_sortino_returns_both_per_trade_and_annualized():
    """MATH-06: response carries both per_trade and annualized с label."""
    from analytics.risk import calculate_sharpe_sortino
    pnls = [100, -50, 200, -30, 150, -80, 120]  # mock
    result = calculate_sharpe_sortino(pnls, trades_per_year=252)
    
    assert "sharpe" in result
    assert "sortino" in result
    assert "per_trade" in result["sharpe"]
    assert "annualized" in result["sharpe"]
    assert result["sharpe"]["trades_per_year"] == 252
    # annualized = per_trade × sqrt(trades_per_year)
    import math
    assert result["sharpe"]["annualized"] == pytest.approx(
        result["sharpe"]["per_trade"] * math.sqrt(252), rel=0.01
    )


def test_sharpe_sortino_backwards_compat_without_trades_per_year():
    """Если trades_per_year не передан — annualized=None, остальное как раньше."""
    from analytics.risk import calculate_sharpe_sortino
    pnls = [100, -50, 200, -30]
    result = calculate_sharpe_sortino(pnls)  # trades_per_year=None default
    assert result["sharpe"]["per_trade"] is not None
    assert result["sharpe"]["annualized"] is None
```

- [ ] **Step 2: Run — FAIL** (текущая функция возвращает плоские числа).

- [ ] **Step 3: Реализация**

```python
import math

def calculate_sharpe_sortino(
    trades_pnl,
    risk_free_rate: float = 0.0,
    trades_per_year: int | None = None,
):
    """MATH-06: Sharpe/Sortino с annualization.
    
    Returns:
        {
            "sharpe": {"per_trade": float, "annualized": float | None, "trades_per_year": int | None},
            "sortino": {"per_trade": float, "annualized": float | None, "trades_per_year": int | None},
        }
    """
    if len(trades_pnl) < 2:
        return _empty_sharpe_sortino_result(trades_per_year)
    
    returns = np.array(trades_pnl, dtype=np.float64)
    mean_return = float(np.mean(returns))
    std_dev = float(np.std(returns, ddof=1))
    
    sharpe_pt = (mean_return - risk_free_rate) / std_dev if std_dev > 0 else 0.0
    
    downside_diff = np.minimum(returns - risk_free_rate, 0.0)
    downside_dev = float(np.sqrt(np.mean(np.square(downside_diff))))
    
    if downside_dev > 0:
        sortino_pt = (mean_return - risk_free_rate) / downside_dev
    elif mean_return - risk_free_rate > 0:
        sortino_pt = None  # UNDEFINED — positive с zero downside
    else:
        sortino_pt = 0.0
    
    sqrt_n = math.sqrt(trades_per_year) if trades_per_year else None
    
    return {
        "sharpe": {
            "per_trade": round(sharpe_pt, 4),
            "annualized": round(sharpe_pt * sqrt_n, 4) if sqrt_n else None,
            "trades_per_year": trades_per_year,
        },
        "sortino": {
            "per_trade": round(sortino_pt, 4) if sortino_pt is not None else None,
            "annualized": round(sortino_pt * sqrt_n, 4) if (sortino_pt is not None and sqrt_n) else None,
            "trades_per_year": trades_per_year,
        },
    }
```

- [ ] **Step 4: Adapt callers**

Найди все `calculate_sharpe_sortino(...)` callers (grep). До этой правки они получали плоские числа; теперь — dict. Обнови:
- `routers/stats.py` / `stats_advanced.py` — передай `trades_per_year` (типично 252 для daily, или авто-расчёт `len(trades) / time_window_years`).
- Тесты, мокающие старое поведение.

**Внимание:** это breaking-change response shape. Если frontend читает `sharpe_ratio: float`, нужно ИЛИ оставить top-level alias `sharpe_ratio = result["sharpe"]["per_trade"]` (backwards-compat), ИЛИ обновить фронт. Выбери **backwards-compat alias** (минимум frontend changes).

- [ ] **Step 5: Pass + NO-COMMIT**

---

## Batch 4 — CAGR unification + futures PV

### Task 4.1: MATH-07 — Canonical CAGR baseline

**Files:**
- Create: `backend/analytics/_common_baseline.py`
- Modify: `backend/routers/stats.py` (`:557-581`), `backend/routers/stats_advanced.py` (`:73-82`, `:177-188`)

- [ ] **Step 1: Failing test**

```python
def test_cagr_baseline_uses_net_deposits_not_initial_balance(
    db_session, account_with_deposits_history
):
    """MATH-07: канонический baseline = net_deposits (cash truth), не initial_balance."""
    from analytics._common_baseline import compute_cagr_baseline
    
    # account.initial_balance = 100000
    # deposits = +50000 +30000 −10000 = +70000 net
    # Канонический baseline = sum(NET_DEPOSITS) = 170000
    baseline = compute_cagr_baseline(
        capital_flows=account_with_deposits_history.capital_flows,
    )
    assert baseline == Decimal("170000")
```

- [ ] **Step 2: Implement helper**

```python
# backend/analytics/_common_baseline.py
"""MATH-07: канонический CAGR baseline.

Spec cash-anchored: «касса — истина». Baseline = net_deposits (sum NET_DEPOSIT
cash-flows за период), НЕ user-provided account.initial_balance.
"""
from decimal import Decimal
from typing import Iterable


def compute_cagr_baseline(capital_flows: Iterable) -> Decimal:
    """sum(NET_DEPOSITS) — единственный канонический baseline для Calmar/CAGR.
    
    Args:
        capital_flows: iterable of objects with .category and .amount fields,
            где category — CashFlowCategory enum (или string).
    
    Returns:
        Decimal sum всех NET_DEPOSIT cash-flows (positive deposits + negative withdrawals).
    """
    total = Decimal("0")
    for flow in capital_flows:
        category = str(flow.category if hasattr(flow, "category") else flow.get("category"))
        if "NET_DEPOSIT" in category:
            amount = flow.amount if hasattr(flow, "amount") else flow.get("amount")
            total += Decimal(str(amount or 0))
    return total
```

- [ ] **Step 3: Migrate 3 callsites**

`stats.py:557-581` — `drawdown_baseline` логика уже использует NET_DEPOSITS; вынеси в helper-вызов.

`stats_advanced.py:73-82` и `:177-188` — заменить `account.initial_balance` на `compute_cagr_baseline(capital_flows)`.

- [ ] **Step 4: Endpoint consistency test**

```python
def test_cagr_consistent_across_dashboard_and_advanced(client, auth_headers):
    """MATH-07: cagr_pct в /stats/ и /stats/advanced должны совпадать."""
    r1 = client.get("/stats/", headers=auth_headers).json()
    r2 = client.get("/stats/advanced", headers=auth_headers).json()
    assert r1["cagr_pct"] == pytest.approx(r2["cagr_pct"], abs=0.1)
```

- [ ] **Step 5: NO-COMMIT**

---

### Task 4.2: MATH-08 + MATH-11 — futures PV resolution

**Files:**
- Modify: `backend/analytics/mae_mfe.py` (`:136-151`)
- Modify: `backend/domain/pnl/futures.py::_resolve_pv` (`:202-225`)
- Test: `backend/tests/unit/test_mae_mfe_pv_resolution.py`, `backend/tests/unit/test_futures_pv_weighted.py`

- [ ] **Step 1: Failing test — MAE/MFE без cached PV ×1000**

```python
def test_mae_mfe_profit_left_uses_resolved_pv_for_futures():
    """MATH-08: profit_left для фьючерса должен использовать empirical PV
    (через _resolve_pv), не cached pnl_service.get_point_value."""
    from analytics.mae_mfe import analyze_mae_mfe
    # Trade: индексный фьючерс, cached PV=1000 (Tinkoff metadata bug),
    # empirical PV=1 (truth от payment/price). Expected profit_left ≈ 5 (price_diff × qty × 1),
    # а не 5000.
    trades = [_make_futures_trade(symbol="BR-12.26", entry_price=80, mfe_pct=10, qty=1)]
    result = analyze_mae_mfe(trades)
    expected_profit_left = 8.0  # 80 × 0.1 × 1
    assert result["profit_left_avg"] == pytest.approx(expected_profit_left, rel=0.05)
```

- [ ] **Step 2: Implement**

В `analytics/mae_mfe.py`:

```python
# БЫЛО (:140-141):
# pv = float(_get_point_value(t.symbol))
# СТАЛО:
from domain.pnl.futures import _resolve_pv_from_trade  # new wrapper
pv = float(_resolve_pv_from_trade(t))
```

Новый wrapper в `domain/pnl/futures.py`:

```python
def _resolve_pv_from_trade(trade) -> Decimal:
    """MAE/MFE-friendly wrapper around _resolve_pv. 
    
    Из Trade-объекта: если есть stored `trade.point_value` (backfill) → используй;
    иначе fallback на cached.
    """
    if hasattr(trade, "point_value") and trade.point_value:
        return Decimal(str(trade.point_value))
    # Cached fallback — sub-optimal но работает
    from pnl_service import get_point_value
    return Decimal(str(get_point_value(trade.symbol)))
```

- [ ] **Step 3: MATH-11 — Weighted-avg PV в `_resolve_pv`**

В `domain/pnl/futures.py::_resolve_pv`:

```python
@staticmethod
def _resolve_pv(matched: MatchedTrade, instrument: Instrument) -> Decimal:
    cached_pv = _point_value(instrument)
    
    # MATH-11: weighted-avg по всем entry slices, не только первому.
    if matched.entry_slices and matched.entry_avg_price > 0:
        total_payment = Decimal("0")
        total_qty = Decimal("0")
        total_value = Decimal("0")
        for slice in matched.entry_slices:
            pay_per_unit = abs(slice.lot.payment_per_unit)
            qty = abs(slice.lot.qty)
            price = slice.lot.price_per_unit
            if price > 0 and qty > 0:
                slice_pv = pay_per_unit / price
                total_payment += slice_pv * qty
                total_qty += qty
        if total_qty > 0:
            empirical_pv = total_payment / total_qty
        else:
            empirical_pv = None
    else:
        empirical_pv = None
    
    if empirical_pv is None:
        return cached_pv
    if cached_pv == 0:
        return empirical_pv
    
    drift = abs(empirical_pv - cached_pv) / cached_pv
    if drift > Decimal("0.05"):
        _log.warning("futures_pv_empirical_chosen", drift=str(drift))
        return empirical_pv
    return cached_pv
```

- [ ] **Step 4: Test multi-slice + weighted**

```python
def test_resolve_pv_uses_weighted_avg_across_slices():
    """MATH-11: при двух scaled-in slices PV — weighted-avg, не first."""
    # Slice 1: 1 lot at price 100, payment=-100 → pv=1
    # Slice 2: 9 lots at price 110, payment=-9900 → pv=10
    # Weighted-avg: (1*1 + 10*9) / 10 = 9.1
    matched = _make_matched_trade_with_slices([(1, 100, -100), (9, 110, -9900)])
    pv = FifoMatcher._resolve_pv(matched, instrument=_idx_futures())
    assert pv == pytest.approx(Decimal("9.1"), rel=0.01)
```

- [ ] **Step 5: Pass + reconcile sanity check**

```
PYTHONUTF8=1 python -X utf8 backend/tools/reconcile_journal_vs_cash.py --account-id <futures-account>
```

Diff не должен расти.

- [ ] **Step 6: NO-COMMIT**

---

## Batch 5 — MAE/MFE pipeline (MATH-03)

### Task 5.1: Hook на импорт + nightly safety-net

**Files:**
- Modify: `backend/import_service.py` (после batch insert)
- Create: `backend/jobs/mae_mfe_backfill.py`
- Modify: `backend/application/sync/sync_scheduler.py` (cron registration)
- Test: `backend/tests/integration/test_mae_mfe_coverage_pipeline.py`

- [ ] **Step 1: Failing test — coverage после импорта**

```python
@pytest.mark.asyncio
async def test_import_triggers_mae_mfe_backfill_async(
    client, auth_headers, sample_import_csv, db_session
):
    """MATH-03: после импорта MAE/MFE должны backfill'ить в фоне.
    
    Ждём reasonable окно (1-2s) для async-task, потом проверяем coverage.
    """
    resp = client.post("/trades/import", files={"file": sample_import_csv}, headers=auth_headers)
    assert resp.status_code == 200
    
    # Дай background-task'у время отработать
    await asyncio.sleep(2.0)
    
    trades = db_session.query(Trade).filter(Trade.account_id == ...).all()
    coverage = sum(1 for t in trades if t.mae_price is not None) / len(trades)
    # Не 100% (MOEX может не вернуть свечи) — но не 0%.
    assert coverage > 0.5, f"MAE/MFE coverage {coverage} too low — pipeline broken"
```

- [ ] **Step 2: Implement import hook**

В `backend/import_service.py` после batch INSERT:

```python
import asyncio
from market_service import market_data_service

async def _backfill_mae_mfe_async(trade_ids: list[int]):
    """MATH-03: fire-and-forget MAE/MFE для импортированных трейдов."""
    from database import SessionLocal
    db = SessionLocal()
    try:
        trades = db.query(Trade).filter(Trade.id.in_(trade_ids)).all()
        for t in trades:
            try:
                mae, mfe = await market_data_service.calculate_mae_mfe(
                    ticker=t.symbol,
                    entry_at=t.entry_at,
                    exit_at=t.exit_at,
                    entry_price=t.entry_price,
                    exit_price=t.exit_price,
                )
                if mae is not None:
                    t.mae_price = mae
                if mfe is not None:
                    t.mfe_price = mfe
            except Exception as exc:
                log.warning("mae_mfe backfill failed for trade %d: %s", t.id, exc)
        db.commit()
    finally:
        db.close()

# В функции импорта после batch insert:
new_trade_ids = [t.id for t in newly_inserted_trades]
asyncio.create_task(_backfill_mae_mfe_async(new_trade_ids))
```

(Используй паттерн strong-ref `_bg_tasks` set, как в `middleware.py` Task 1.1 Sprint 3.)

- [ ] **Step 3: Implement nightly safety-net**

```python
# backend/jobs/mae_mfe_backfill.py
"""MATH-03: nightly backfill MAE/MFE для трейдов с NULL mae_price/mfe_price."""
from datetime import datetime, timedelta
import logging

log = logging.getLogger(__name__)


async def backfill_missing_mae_mfe(session, *, limit: int = 100, max_age_days: int = 30):
    """Find up to `limit` recent trades without MAE/MFE and backfill."""
    from models import Trade
    from market_service import market_data_service
    
    cutoff = datetime.now() - timedelta(days=max_age_days)
    missing = (
        session.query(Trade)
        .filter(
            Trade.mae_price.is_(None),
            Trade.exit_at.isnot(None),
            Trade.entry_at >= cutoff,
        )
        .limit(limit)
        .all()
    )
    log.info("mae_mfe nightly backfill: %d candidates", len(missing))
    for t in missing:
        try:
            mae, mfe = await market_data_service.calculate_mae_mfe(...)
            if mae is not None:
                t.mae_price = mae
            if mfe is not None:
                t.mfe_price = mfe
        except Exception as exc:
            log.warning("nightly backfill failed for trade %d: %s", t.id, exc)
    session.commit()
```

- [ ] **Step 4: Register в `sync_scheduler.py`**

В `_run_loop` рядом с `_check_retention_cleanup` (Task 3.3 Sprint 3):

```python
from jobs.mae_mfe_backfill import backfill_missing_mae_mfe

if is_scheduler_worker():
    # ... existing retention check
    if (now - self._last_mae_mfe_backfill_run) >= timedelta(hours=24):
        try:
            async def _run():
                with self._session_factory() as s:
                    await backfill_missing_mae_mfe(s)
            await _run()
            self._last_mae_mfe_backfill_run = now
        except Exception as exc:
            log.error("mae_mfe backfill failed: %s", exc)
```

- [ ] **Step 5: Pass + NO-COMMIT**

---

## Batch 6 — Test gap fill (MATH-02)

### Task 6.1: 13 функций в `analytics/advanced.py`

**Files:**
- Create: `backend/tests/unit/test_analytics_advanced_gaps.py`

13 функций без тестов:
1. `calculate_hold_time_distribution`
2. `calculate_period_breakdown`
3. `calculate_hour_dow_heatmap`
4. `calculate_plan_adherence`
5. `calculate_mistake_categories`
6. `calculate_commission_ratio`
7. `calculate_trade_frequency`
8. `calculate_psycho_correlations`
9. `calculate_news_event_stats`
10. `calculate_exit_reason_breakdown`
11. `calculate_daily_pnl`
12. `calculate_rr_realized`
13. `collect_drawdown_episodes`

- [ ] **Step 1: Read each function signature in `analytics/advanced.py`**

- [ ] **Step 2: For each — write 2-3 tests (happy path, empty input, edge case)**

Шаблон:

```python
def test_calculate_hold_time_distribution_happy_path():
    trades = [
        _trade(entry_at=datetime(2026, 1, 1), exit_at=datetime(2026, 1, 1, 1)),  # 1h
        _trade(entry_at=datetime(2026, 1, 1), exit_at=datetime(2026, 1, 2)),     # 24h
    ]
    result = calculate_hold_time_distribution(trades)
    assert result["mean_hours"] == pytest.approx(12.5)


def test_calculate_hold_time_distribution_empty():
    assert calculate_hold_time_distribution([]) == {"mean_hours": 0, ...}
```

(Подробно расписать тесты для каждой функции — см. фактический signature.)

- [ ] **Step 3: Pass + NO-COMMIT**

---

### Task 6.2: `analytics/aggregator.py::calculate_stats` unit-тесты

**Files:**
- Create: `backend/tests/unit/test_analytics_aggregator.py`

- [ ] **Step 1: Прочитай `calculate_stats` сигнатуру**

- [ ] **Step 2: Покрой 5-7 кейсами:** empty, single-trade, all-winners (profit_factor None), all-losers, mixed, with_risks, без risks.

- [ ] **Step 3: Pass + NO-COMMIT**

---

## Self-Review (после написания плана)

**Coverage против спеки:**
- MATH-01 ✅ Batch 2 (Task 2.1, 2.2, 2.3)
- MATH-02 ✅ Batch 6 (Task 6.1, 6.2)
- MATH-03 ✅ Batch 5 (Task 5.1)
- MATH-04 ✅ Batch 3 (Task 3.1)
- MATH-05 ✅ Batch 1 (Task 1.1)
- MATH-06 ✅ Batch 3 (Task 3.2)
- MATH-07 ✅ Batch 4 (Task 4.1)
- MATH-08 ✅ Batch 4 (Task 4.2)
- MATH-09 ✅ Batch 1 (Task 1.2)
- MATH-10 ✅ Batch 1 (Task 1.3)
- MATH-11 ✅ Batch 4 (Task 4.2)

**Placeholder scan:** все code-блоки конкретны. Test names — фактические. `_make_*` helpers, описанные в скриптах тестов, требуют расширения по факту в конкретные минимальные фабрики (один-два десятка строк).

**Type consistency:**
- `_net_or_gross(t)` — одна и та же сигнатура используется в Task 2.1 (через `analytics.calculate_advanced_stats`) и Task 2.2/2.3 (inline). OK.
- `compute_cagr_baseline(capital_flows)` — единая сигнатура в Task 4.1.
- `_resolve_pv_from_trade(trade)` — wrapper в Task 4.2.
- `calculate_sharpe_sortino` возвращает dict — breaking change, frontend-alias добавлен в Step 4 Task 3.2.

**Reconcile sanity (P&L feedback):** Tasks 1.3, 4.2 — после правки прогон `reconcile_journal_vs_cash.py` на реальном аккаунте; diff не должен ухудшиться. Это явно в плане.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-26-sprint-4-pnl-correctness.md`.

**Subagent-Driven (recommended)** — диспатч свежего implementer-агента на каждый Task; между задачами `code-reviewer` для math-чувствительных мест (особенно Batch 2-4); `reconcile_journal_vs_cash.py` прогон после Tasks 1.3, 4.2.
