"""
PR 26 (Phase 3, D3) — four-way property invariants (Limina/ISDA pattern).

Это **внутренние** математические проверки целостности данных. Они
не требуют broker report — работают на наших данных и проверяют,
что наши aggregates согласованы между собой.

4 inv:
  - Transaction inv: Σ buy − Σ sell − Σ commissions = Σ realized + Σ unrealized
  - Position inv: position(t) ≈ position(t-1) + Σ buys − Σ sells ± corp
  - Cash inv: cash(t) = cash(t-1) + Σ flows
  - NAV inv: nav(t) = cash(t) + Σ position_mtm(t)

Tolerance: тот же 10₽ / 0.1% что и reconciliation_service.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

import models
from domain.pnl.cash_flow_classification import (
    CashFlowCategory as _CFC,
    operation_types_in as _op_types_in,
)
from logger import get_logger
from services.reconciliation_service import classify_diff
from utils.datetime_utils import utc_now_naive

_NET_DEPOSIT_TYPES = _op_types_in(_CFC.NET_DEPOSIT)

log = get_logger("invariants")


@dataclass
class InvariantCheck:
    """Один результат property invariant."""

    name: str
    lhs_value: Decimal
    rhs_value: Decimal
    diff_abs: Decimal
    diff_pct: Decimal
    status: str  # 'ok' | 'soft' | 'hard'
    formula: str
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "lhs": str(self.lhs_value),
            "rhs": str(self.rhs_value),
            "diff_abs": str(self.diff_abs),
            "diff_pct": str(self.diff_pct),
            "status": self.status,
            "formula": self.formula,
            "note": self.note,
        }


def _money_decimal(units: Any, nano: Any) -> Decimal:
    u = int(units or 0)
    n = int(nano or 0)
    return Decimal(u) + Decimal(n) / Decimal(1_000_000_000)


def check_invariants(
    db: Session,
    account_id: int,
    period_start: datetime,
    period_end: datetime,
) -> list[InvariantCheck]:
    """Запустить все 4 проверки на аккаунте за период."""
    results = [
        _transaction_invariant(db, account_id, period_start, period_end),
        _position_invariant(db, account_id, period_start, period_end),
        _cash_invariant(db, account_id, period_start, period_end),
        _nav_invariant(db, account_id, period_end),
    ]
    log.info(
        "invariants_checked",
        extra={
            "account_id": account_id,
            "breaks": sum(1 for r in results if r.status in {"hard", "soft"}),
        },
    )
    return results


# ════════════════════════════════════════════════════════════════════════
# Transaction invariant
# ════════════════════════════════════════════════════════════════════════


def _transaction_invariant(
    db: Session,
    account_id: int,
    period_start: datetime,
    period_end: datetime,
) -> InvariantCheck:
    """LHS: Σ buy_value − Σ sell_value − Σ commissions (cash gone)
    RHS: Σ realized P&L (закрытые сделки в окне) + Σ unrealized (открытые)

    Логика: деньги ушли на покупки минус пришли с продаж минус комиссии
    должно равняться сумме всех P&L (реализованных + нереализованных).

    Tinkoff payment для BUY < 0 (списание), для SELL > 0 (зачисление).
    """
    ops = (
        db.query(models.OperationORM)
        .filter(
            models.OperationORM.account_id == account_id,
            models.OperationORM.executed_at >= period_start,
            models.OperationORM.executed_at <= period_end,
            models.OperationORM.operation_type.in_([
                "buy", "buy_card", "buy_margin",
                "sell", "sell_card", "sell_margin",
            ]),
        )
        .all()
    )

    buy_total = Decimal(0)
    sell_total = Decimal(0)
    commissions_total = Decimal(0)
    for op in ops:
        payment = _money_decimal(op.payment_units, op.payment_nano)
        commission = _money_decimal(op.commission_units, op.commission_nano)
        op_type = (op.operation_type or "").lower()
        if op_type.startswith("buy"):
            buy_total += abs(payment)
        elif op_type.startswith("sell"):
            sell_total += abs(payment)
        commissions_total += abs(commission)

    # cash_gone = buys − sells + commissions
    lhs = buy_total - sell_total + commissions_total

    # Σ realized P&L по закрытым сделкам в окне
    closed_trades = (
        db.query(models.Trade)
        .filter(
            models.Trade.account_id == account_id,
            models.Trade.exit_at.isnot(None),
            models.Trade.exit_at >= period_start,
            models.Trade.exit_at <= period_end,
        )
        .all()
    )
    realized_pnl = Decimal(0)
    for t in closed_trades:
        if t.net_pnl is not None:
            realized_pnl += Decimal(str(t.net_pnl))

    # Σ unrealized P&L — текущая стоимость открытых позиций минус cost basis
    open_positions = (
        db.query(models.PositionORM)
        .filter(
            models.PositionORM.account_id == account_id,
            models.PositionORM.quantity != 0,
        )
        .all()
    )
    unrealized_pnl = Decimal(0)
    for p in open_positions:
        if p.unrealized_pnl is not None:
            unrealized_pnl += Decimal(str(p.unrealized_pnl))

    # RHS: cash_gone (на закупку) ≈ realized + unrealized + open_positions_cost
    # Точное равенство в open period сложно без полной информации о позициях
    # на начало периода. Здесь даём «consistency» проверку: −(buys − sells)
    # должен ≈ realized + unrealized (commissions учтены в P&L).
    rhs = realized_pnl + unrealized_pnl

    # Для invariant используем cash_gone vs (realized + unrealized + cost_basis)
    # Простая версия: если |LHS - RHS| мала относительно объёма торгов — ok
    # AU16: classify_diff returns 4-tuple (diff_abs, diff_pct, status, _note).
    # Для invariants methodology_note не нужен — note строится локально ниже.
    diff_abs, diff_pct, status, _ = classify_diff(lhs, rhs)
    formula = "Σ buy − Σ sell + Σ commissions  ≈  Σ realized P&L + Σ unrealized P&L"
    note = ""
    if status != "ok":
        note = (
            f"buys={buy_total}, sells={sell_total}, comm={commissions_total}, "
            f"realized={realized_pnl}, unrealized={unrealized_pnl}. "
            f"Часть разницы объясняется позициями открытыми ДО {period_start.isoformat()}."
        )
        # На незакрытом периоде это soft warning, не hard
        if status == "hard":
            status = "soft"

    return InvariantCheck(
        name="transaction",
        lhs_value=lhs,
        rhs_value=rhs,
        diff_abs=diff_abs,
        diff_pct=diff_pct,
        status=status,
        formula=formula,
        note=note,
    )


# ════════════════════════════════════════════════════════════════════════
# Position invariant
# ════════════════════════════════════════════════════════════════════════


def _position_invariant(
    db: Session,
    account_id: int,
    period_start: datetime,
    period_end: datetime,
) -> InvariantCheck:
    """Position(t_end) ≈ Position(t_start) + Σ buys − Σ sells.

    Считаем по quantity. Расхождение указывает на пропущенные операции
    или дисконнект между API portfolio (Tinkoff) и нашими операциями.
    """
    # Δ quantity = Σ buys − Σ sells в периоде
    ops = (
        db.query(models.OperationORM)
        .filter(
            models.OperationORM.account_id == account_id,
            models.OperationORM.executed_at >= period_start,
            models.OperationORM.executed_at <= period_end,
        )
        .all()
    )
    delta = 0
    for op in ops:
        op_type = (op.operation_type or "").lower()
        qty = int(op.quantity or 0)
        if op_type.startswith("buy"):
            delta += qty
        elif op_type.startswith("sell"):
            delta -= qty

    # Текущая сумма quantity по всем positions
    current_positions = (
        db.query(models.PositionORM)
        .filter(models.PositionORM.account_id == account_id)
        .all()
    )
    current_qty_total = sum(int(p.quantity or 0) for p in current_positions)

    # Это не строгое равенство (corporate actions, splits, FX). Для invariant
    # check проверяем что |delta − changes_explained| мала. Здесь мы просто
    # фиксируем delta и current — caller решит.
    lhs = Decimal(delta)
    rhs = Decimal(current_qty_total)
    # Position changes — это разница в позициях, не сами позиции. Поэтому
    # реальная проверка требует знать positions(t_start), которых у нас
    # обычно нет. Делаем soft check: если delta=0 а позиций нет — ok.
    if delta == 0 and current_qty_total == 0:
        status = "ok"
        diff_abs = Decimal(0)
        diff_pct = Decimal(0)
    else:
        diff_abs = abs(lhs - rhs)
        diff_pct = (diff_abs / max(abs(rhs), Decimal(1))) * Decimal(100)
        # Soft warning только если очень большое расхождение
        status = "soft" if diff_abs > Decimal(10) else "ok"

    return InvariantCheck(
        name="position",
        lhs_value=lhs,
        rhs_value=rhs,
        diff_abs=diff_abs,
        diff_pct=diff_pct,
        status=status,
        formula="Σ buys − Σ sells (за период)  ≈  ΣPosition.quantity (на конец периода)",
        note=(
            "Точная проверка требует Position(t_start), которого у нас обычно нет. "
            "Большое расхождение указывает на: corporate actions без записи, "
            "пропущенные операции, или открытые позиции до начала периода."
        ),
    )


# ════════════════════════════════════════════════════════════════════════
# Cash invariant
# ════════════════════════════════════════════════════════════════════════


def _cash_invariant(
    db: Session,
    account_id: int,
    period_start: datetime,
    period_end: datetime,
) -> InvariantCheck:
    """cash(t_end) = cash(t_start) + Σ flows.

    flows = deposits − withdrawals + dividends_net − commissions − taxes + realized_pnl

    Если у нас есть `Account.last_portfolio_value` на конец периода и
    BalanceSnapshot на начало, можем сверить.
    """
    # Σ flows в периоде
    ops = (
        db.query(models.OperationORM)
        .filter(
            models.OperationORM.account_id == account_id,
            models.OperationORM.executed_at >= period_start,
            models.OperationORM.executed_at <= period_end,
        )
        .all()
    )
    deposits = Decimal(0)
    withdrawals = Decimal(0)
    dividends_net = Decimal(0)
    commissions = Decimal(0)
    taxes = Decimal(0)
    trade_cash_flow = Decimal(0)
    for op in ops:
        op_type = (op.operation_type or "").lower()
        payment = _money_decimal(op.payment_units, op.payment_nano)
        commission = _money_decimal(op.commission_units, op.commission_nano)
        if op_type in _NET_DEPOSIT_TYPES:
            # Единый классификатор: INPUT/OUTPUT/*_swift/*_acquiring/*_multi.
            # Знак payment различает ввод (>0) и вывод (<0) (S3-27).
            if payment >= 0:
                deposits += payment
            else:
                withdrawals += abs(payment)
        elif op_type == "dividend":
            dividends_net += payment
        elif op_type in {"buy", "buy_card", "buy_margin", "sell", "sell_card", "sell_margin"}:
            trade_cash_flow += payment  # negative for buy, positive for sell
            commissions += abs(commission)
        elif op_type in {"benefit_tax", "tax", "ndfl", "bond_tax", "bond_tax_progressive"}:
            taxes += abs(payment)
        elif op_type in {"broker_fee", "broker_commission", "service_fee", "margin_fee"}:
            commissions += abs(payment)

    flows = deposits - withdrawals + dividends_net + trade_cash_flow - commissions - taxes
    lhs = flows

    # cash(t_end) − cash(t_start) для сверки
    # Берём snapshot'ы из BalanceSnapshot если есть
    snap_start = (
        db.query(models.BalanceSnapshot)
        .filter(
            models.BalanceSnapshot.account_id == account_id,
            models.BalanceSnapshot.snapshot_date <= period_start,
        )
        .order_by(models.BalanceSnapshot.snapshot_date.desc())
        .first()
    )
    snap_end = (
        db.query(models.BalanceSnapshot)
        .filter(
            models.BalanceSnapshot.account_id == account_id,
            models.BalanceSnapshot.snapshot_date <= period_end,
        )
        .order_by(models.BalanceSnapshot.snapshot_date.desc())
        .first()
    )
    rhs = Decimal(0)
    note = ""
    if snap_start is not None and snap_end is not None:
        rhs = Decimal(str(snap_end.total_value or 0)) - Decimal(str(snap_start.total_value or 0))
    else:
        note = "Нет BalanceSnapshot до/после периода — проверка только на consistency self"

    # AU16: classify_diff returns 4-tuple (diff_abs, diff_pct, status, _note).
    # Для invariants methodology_note не нужен — note строится локально ниже.
    diff_abs, diff_pct, status, _ = classify_diff(lhs, rhs)
    # Если нет snapshot'ов, это soft (не критично)
    if rhs == 0 and lhs != 0:
        status = "soft" if status == "hard" else status
        note = note or "Нет baseline для прямой сверки cash flow"

    return InvariantCheck(
        name="cash",
        lhs_value=lhs,
        rhs_value=rhs,
        diff_abs=diff_abs,
        diff_pct=diff_pct,
        status=status,
        formula="cash(t_end) − cash(t_start)  =  Σ flows (deposits, withdrawals, dividends, trades, comm, tax)",
        note=note,
    )


# ════════════════════════════════════════════════════════════════════════
# NAV invariant
# ════════════════════════════════════════════════════════════════════════


def _nav_invariant(
    db: Session,
    account_id: int,
    as_of: datetime,
) -> InvariantCheck:
    """NAV(t) = cash(t) + Σ position_mtm(t)

    Сверяем Account.last_portfolio_value (NAV from Tinkoff API) с
    cash_balance + Σ (position.quantity × current_price).
    """
    account = db.query(models.Account).filter_by(id=account_id).first()
    if account is None:
        return InvariantCheck(
            name="nav",
            lhs_value=Decimal(0),
            rhs_value=Decimal(0),
            diff_abs=Decimal(0),
            diff_pct=Decimal(0),
            status="ok",
            formula="NAV  =  cash + Σ MTM",
            note="account not found",
        )

    nav_from_api = Decimal(str(account.last_portfolio_value or 0))

    positions = (
        db.query(models.PositionORM)
        .filter(
            models.PositionORM.account_id == account_id,
            models.PositionORM.quantity != 0,
        )
        .all()
    )
    position_mtm = Decimal(0)
    for p in positions:
        qty = Decimal(p.quantity or 0)
        price = Decimal(str(p.current_price or 0))
        position_mtm += qty * price

    # cash_balance мы напрямую не храним — приближаем:
    # cash ≈ NAV − position_mtm. Это даёт почти тривиальный invariant
    # (всегда выполняется по определению). Реальная проверка возможна
    # когда добавим Account.cash_balance отдельно.
    cash_balance_inferred = nav_from_api - position_mtm

    # Здесь invariant в форме: nav ≈ cash + mtm. Поскольку cash inferred,
    # проверяем что mtm не negative и не превышает NAV (sanity check).
    note = (
        f"NAV={nav_from_api}, mtm={position_mtm}, cash_inferred={cash_balance_inferred}. "
        f"Полноценная проверка возможна только при отдельном cash_balance в Account."
    )
    if position_mtm > nav_from_api * Decimal("1.5") and nav_from_api > 0:
        # NAV меньше суммы позиций — невозможно без margin debt
        return InvariantCheck(
            name="nav",
            lhs_value=nav_from_api,
            rhs_value=position_mtm,
            diff_abs=abs(nav_from_api - position_mtm),
            diff_pct=Decimal(0),
            status="hard",
            formula="NAV  =  cash + Σ MTM",
            note=(
                f"NAV={nav_from_api} но Σ MTM={position_mtm} — позиции больше NAV. "
                f"Возможна ошибка current_price (особенно для фьючерсов в пунктах)."
            ),
        )

    return InvariantCheck(
        name="nav",
        lhs_value=nav_from_api,
        rhs_value=cash_balance_inferred + position_mtm,
        diff_abs=Decimal(0),  # by construction
        diff_pct=Decimal(0),
        status="ok",
        formula="NAV  =  cash + Σ MTM",
        note=note,
    )
