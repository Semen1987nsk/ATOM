"""Сбор входов из БД + персист opening-balance anchor (ADR-0010).

Чистое решение — в domain/pnl/opening_anchor.py. Здесь только I/O:
read inputs -> decide -> write Account (freeze + manual-priority).
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
    # Legacy-счёт (баланс задан вручную до ADR-0010, source=NULL) трактуем
    # как manual, иначе авто-якорь молча уничтожит пользовательский ввод.
    if account.initial_balance_source == "manual" or (
        account.initial_balance_source is None
        and Decimal(str(account.initial_balance or 0)) > 0
    ):
        return AnchorDecision(
            False, Decimal(str(account.initial_balance or 0)), "manual", "manual source frozen"
        )

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
    gross_buy_sum = sum(
        (abs(_payment(u, n)) for u, n in buy_rows), Decimal(0)
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
        gross_buy_sum=gross_buy_sum,
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
