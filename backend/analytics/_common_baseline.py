"""MATH-07: канонический CAGR baseline.

Spec cash-anchored: «касса — истина». Baseline для CAGR / Calmar / Sterling /
MAR — всегда `net_deposits` (сумма NET_DEPOSIT cash-flow operations за период),
а НЕ user-provided `account.initial_balance` — он часто врёт.

Три места это считают (`routers/stats.py::get_stats`,
`routers/stats_advanced.py::get_advanced_stats`,
`routers/stats_advanced.py::get_benchmark`). До MATH-07 каждое использовало
свой baseline → одна и та же сделка показывала разный CAGR в трёх карточках.

Используется в:
* `/stats/`           — Calmar / drawdown baseline
* `/stats/advanced`   — Sterling / MAR / CAGR
* `/stats/benchmark`  — CAGR для cohort-сравнения
"""
from __future__ import annotations

from decimal import Decimal
from typing import Iterable


def compute_cagr_baseline(capital_flows: Iterable) -> Decimal:
    """Сумма NET_DEPOSIT cash-flows — канонический baseline для CAGR/Calmar.

    Args:
        capital_flows: iterable of objects/dicts. Каждый элемент должен иметь
            ``category`` (или ключ ``"category"``) и ``amount`` (или ключ
            ``"amount"``). Учитываются только записи, где строковое
            представление category содержит подстроку ``"NET_DEPOSIT"`` —
            это совместимо и с CashFlowCategory enum, и с уже-сериализованной
            строкой ``"net_deposit"`` / ``"NET_DEPOSIT"``.

    Returns:
        Σ amount всех NET_DEPOSIT cash-flows (positive deposits + negative
        withdrawals, как в реконсайле). Decimal — чтобы не было float drift
        для крупных балансов.
    """
    total = Decimal("0")
    for flow in capital_flows:
        # Извлекаем category — поддерживаем object/dict.
        if hasattr(flow, "category"):
            category = flow.category
        elif isinstance(flow, dict):
            category = flow.get("category")
        else:
            continue
        category_str = str(category) if category is not None else ""
        if "NET_DEPOSIT" not in category_str.upper():
            continue
        # Извлекаем amount — поддерживаем object/dict.
        if hasattr(flow, "amount"):
            amount = flow.amount
        elif isinstance(flow, dict):
            amount = flow.get("amount")
        else:
            amount = None
        if amount is None:
            continue
        try:
            total += Decimal(str(amount))
        except Exception:
            # Невалидный amount — пропустить, не сломать sum (например,
            # тестовая фикстура с amount=None).
            continue
    return total


def get_net_deposits_baseline_from_db(db, account_id: int) -> Decimal:
    """DB-flavored helper: считает Σ NET_DEPOSIT payment по operations.

    Точная копия логики `routers/stats.py:516-526` — единственный путь правды.
    Используется в `stats_advanced.py`, где capital_flows in-memory нет, а
    идти за ними через ORM-relationship на каждый request слишком дорого:
    мы напрямую агрегируем OperationORM payment_units + payment_nano по
    `operation_type IN net_deposit_types`.

    Возвращает ``Decimal`` (абсолютная сумма — withdrawals already subtract
    через сами знаки payment_units).
    """
    from sqlalchemy import func
    from domain.pnl.cash_flow_classification import (
        CashFlowCategory as _CFC,
        operation_types_in as _op_types_in,
    )
    import models

    _dep_types = tuple(_op_types_in(_CFC.NET_DEPOSIT))
    if not _dep_types:
        return Decimal("0")
    row = (
        db.query(
            func.coalesce(func.sum(models.OperationORM.payment_units), 0),
            func.coalesce(func.sum(models.OperationORM.payment_nano), 0),
        )
        .filter(
            models.OperationORM.account_id == account_id,
            models.OperationORM.operation_type.in_(_dep_types),
            models.OperationORM.state == "executed",
        )
        .one()
    )
    # Σ NET_DEPOSITS — INPUT > 0 / OUTPUT < 0 (по знакам payment_units), но
    # для CAGR baseline нужна абсолютная "сколько вложено суммарно". Это и
    # есть то, что считает stats.py L526 через `abs(...)`. Для согласованности
    # делаем то же.
    total = Decimal(row[0] or 0) + Decimal(row[1] or 0) / Decimal(10**9)
    return abs(total)
