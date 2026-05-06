"""
Параметризованные тесты под фиксы Phase 1.

Гарантируют, что:
- Profit Factor возвращает None (не магическое 99.99) при отсутствии убытков.
- Sortino возвращает None при нулевой downside deviation.
- SQN не клипуется к sqrt(min(N,100)) — sqn растёт с √N, а sqn_n100 остаётся
  стабильным для совместимости со шкалой Ван Тарпа.
- Edge cases: 0/1 сделка, all-wins, all-losses, NaN/Inf на входе.
"""
from __future__ import annotations

import math
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import analytics  # noqa: E402


# ──────────────────────────────────────────────
#  Profit Factor — нет больше магических 99.99
# ──────────────────────────────────────────────


@pytest.mark.parametrize(
    "pnl, expected",
    [
        # Только прибыли → PF математически не определён → None
        ([100.0, 50.0, 25.0], None),
        ([10.0], None),
        # Нормальный кейс: PF = wins/losses
        ([100.0, -50.0], 2.0),
        ([200.0, -100.0, -100.0], 1.0),
        # Только убытки → PF = 0
        ([-50.0, -25.0], 0.0),
        # Пустой массив → 0
        ([], 0.0),
    ],
)
def test_profit_factor_no_magic_constants(pnl, expected):
    risk = [0] * len(pnl)
    res = analytics.calculate_advanced_stats(pnl, risk)
    assert res["profit_factor"] == expected, (
        f"Profit Factor для {pnl}: ожидали {expected}, получили {res['profit_factor']}"
    )


# ──────────────────────────────────────────────
#  Recovery Factor — None при нулевой просадке
# ──────────────────────────────────────────────


def test_recovery_factor_no_drawdown_returns_none():
    """Только прибыли → нет просадок → recovery_factor = None, не 99.99."""
    res = analytics.calculate_advanced_stats([100, 50, 25], [0, 0, 0])
    assert res["recovery_factor"] is None


def test_recovery_factor_with_drawdown():
    """Есть просадка → нормальное число."""
    res = analytics.calculate_advanced_stats([100, -50, 30], [0, 0, 0])
    assert isinstance(res["recovery_factor"], (int, float))
    assert res["recovery_factor"] > 0


# ──────────────────────────────────────────────
#  Sortino — None вместо 99.99 при downside_dev=0
# ──────────────────────────────────────────────


def test_sortino_no_downside_returns_none():
    """Все доходности > 0 → downside_dev = 0 → Sortino не определён."""
    res = analytics.calculate_sharpe_sortino([10.0, 20.0, 5.0, 15.0])
    assert res["sortino_ratio"] is None
    # Sharpe при этом валиден
    assert res["sharpe_ratio"] > 0


def test_sortino_with_downside():
    res = analytics.calculate_sharpe_sortino([10.0, -5.0, 15.0, -3.0])
    assert res["sortino_ratio"] is not None
    assert isinstance(res["sortino_ratio"], (int, float))


# ──────────────────────────────────────────────
#  SQN — больше нет min(N, 100)
# ──────────────────────────────────────────────


def test_sqn_scales_with_sqrt_n():
    """sqn должен расти как √N (а не плато после N=100)."""
    base_pnl = [10, -5, 15, -3, 8] * 30  # 150 сделок одинакового профиля
    risk = [10] * len(base_pnl)
    res_150 = analytics.calculate_sqn(base_pnl, risk)

    base_pnl_50 = base_pnl[:50]
    risk_50 = risk[:50]
    res_50 = analytics.calculate_sqn(base_pnl_50, risk_50)

    assert "sqn" in res_150 and "sqn" in res_50
    # √(150/50) ≈ 1.732 — sqn должен вырасти примерно во столько же раз
    ratio = res_150["sqn"] / res_50["sqn"]
    assert 1.5 < ratio < 2.0, (
        f"SQN должен масштабироваться как √N, а вырос только в {ratio:.2f}× — "
        "проверь, что min(N,100) убран"
    )

    # sqn_n100 при N≥100 должен быть стабилен по множителю √100, а различия идут
    # только от выборочной mean/std. На однородном профиле рост sqn_n100 с N=150
    # к N=100 должен быть < 5%.
    res_100 = analytics.calculate_sqn(base_pnl[:100], risk[:100])
    n100_drift = abs(res_150["sqn_n100"] - res_100["sqn_n100"]) / res_100["sqn_n100"]
    assert n100_drift < 0.05, (
        f"sqn_n100 нестабилен между N=100 и N=150: дрейф {n100_drift:.2%}"
    )


def test_sqn_returns_n_field():
    """Размер выборки должен быть в ответе для прозрачности."""
    res = analytics.calculate_sqn([10, -5, 15, -3, 8], [10] * 5)
    assert res.get("n") == 5


# ──────────────────────────────────────────────
#  Payoff / Tail / Kelly — None при отсутствии убытков
# ──────────────────────────────────────────────


def test_payoff_ratio_no_losses_returns_none():
    res = analytics.calculate_win_loss_stats([10, 20, 30])
    assert res["payoff_ratio"] is None


def test_payoff_ratio_with_losses():
    res = analytics.calculate_win_loss_stats([20, -10, 30, -10])
    assert res["payoff_ratio"] == pytest.approx(2.5, rel=1e-3)


def test_tail_ratio_when_bottom_decile_is_zero():
    """Если bottom-10% ровно нулевые → метрика не определена (раньше было 99.99)."""
    # 10 элементов: топ-10% = 1 элемент (1000), bottom-10% = 1 элемент (0).
    res = analytics.calculate_tail_ratio([1000, 50, 40, 30, 20, 10, 5, 3, 1, 0])
    assert res["tail_ratio"] is None


def test_tail_ratio_normal_case():
    """С реальными убытками возвращает положительное число."""
    res = analytics.calculate_tail_ratio([100, 50, 30, 20, 10, -5, -10, -20, -30, -100])
    assert res["tail_ratio"] is not None
    assert res["tail_ratio"] > 0


def test_kelly_negative_is_preserved():
    """Отрицательный Kelly валиден (= не торгуй) — не должен клиповаться к 0/100."""
    # Win-rate 30%, payoff 1 → Kelly = 0.3 - 0.7/1 = -0.4 (-40%)
    pnl = [100, -100, -100, 100, -100, -100, 100, -100, -100, -100]  # 30% wins
    res = analytics.calculate_kelly_criterion(pnl)
    assert res["kelly_pct"] is not None
    assert res["kelly_pct"] < 0
    assert "Отрицательный" in res["message"]


# ──────────────────────────────────────────────
#  Edge cases — пустые/одна/all-wins/all-losses не падают
# ──────────────────────────────────────────────


@pytest.mark.parametrize(
    "pnl",
    [
        [],
        [100.0],
        [100.0, 200.0, 50.0],  # all wins
        [-100.0, -50.0, -25.0],  # all losses
        [0.0, 0.0, 0.0],  # все нули
    ],
)
def test_advanced_stats_no_crash(pnl):
    """calculate_advanced_stats должен корректно отрабатывать на любом входе."""
    risk = [0] * len(pnl)
    res = analytics.calculate_advanced_stats(pnl, risk)
    assert "profit_factor" in res
    assert "recovery_factor" in res
    # Никаких inf/nan в числовых полях (None допустимо)
    for key in ("max_drawdown",):
        v = res.get(key)
        if v is not None:
            assert not math.isnan(v) and not math.isinf(v)


@pytest.mark.parametrize(
    "pnl",
    [
        [],
        [100.0],  # одна сделка — большинство метрик вернёт «недостаточно данных»
        [10.0] * 5,  # все равны — std=0
    ],
)
def test_sharpe_sortino_no_crash(pnl):
    res = analytics.calculate_sharpe_sortino(pnl)
    assert "sharpe_ratio" in res and "sortino_ratio" in res


# ──────────────────────────────────────────────
#  _sanitize — NaN/Inf превращаются в None
# ──────────────────────────────────────────────


@pytest.mark.parametrize(
    "value, expected",
    [
        (None, None),
        (float("nan"), None),
        (float("inf"), None),
        (float("-inf"), None),
        (0.0, 0.0),
        (1.5, 1.5),
        ("abc", None),
    ],
)
def test_sanitize(value, expected):
    assert analytics._sanitize(value) == expected
