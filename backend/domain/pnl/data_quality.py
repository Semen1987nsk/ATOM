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
    реальный cash. Если невязка велика — импорт неполон/задвоен.
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
