from __future__ import annotations

from decimal import Decimal
from datetime import datetime
from typing import Any, Optional, cast

from sqlalchemy.orm import Session

import models
from utils import utc_now_naive


SYNTHETIC_INITIAL_NOTE = "Backfilled initial deposit from account balance"


def has_broker_capital_operations(db: Session, account_id: int) -> bool:
    return db.query(models.CapitalOperation).filter(
        models.CapitalOperation.account_id == account_id,
    ).first() is not None


def get_net_deposit_as_of(db: Session, account_id: int, as_of: Optional[datetime] = None) -> float:
    if has_broker_capital_operations(db, account_id):
        deposits_query = db.query(models.CapitalOperation).filter(
            models.CapitalOperation.account_id == account_id,
            models.CapitalOperation.operation_type == "deposit",
        )
        withdrawals_query = db.query(models.CapitalOperation).filter(
            models.CapitalOperation.account_id == account_id,
            models.CapitalOperation.operation_type == "withdrawal",
        )
        if as_of is not None:
            deposits_query = deposits_query.filter(models.CapitalOperation.date <= as_of)
            withdrawals_query = withdrawals_query.filter(models.CapitalOperation.date <= as_of)

        deposits = sum(float(cast(Decimal, op.amount) or 0) for op in deposits_query.all())
        withdrawals = sum(float(cast(Decimal, op.amount) or 0) for op in withdrawals_query.all())
        return deposits - withdrawals

    history_query = db.query(models.DepositHistory).filter(
        models.DepositHistory.account_id == account_id,
    )
    if as_of is not None:
        history_query = history_query.filter(models.DepositHistory.date <= as_of)

    history = history_query.order_by(models.DepositHistory.date.asc(), models.DepositHistory.id.asc()).all()
    if not history:
        account = db.query(models.Account).filter(models.Account.id == account_id).first()
        if account is None:
            return 0.0
        return float(cast(Decimal | None, account.initial_balance) or 0)

    balance = 0.0
    for item in history:
        amount = float(cast(Decimal, item.amount) or 0)
        operation_type = cast(models.DepositOperationType, item.operation_type)
        if operation_type == models.DepositOperationType.INITIAL:
            balance = amount
        else:
            balance += amount
    return balance


def get_capital_flow_events(
    db: Session,
    account_id: int,
    *,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
) -> list[dict]:
    if has_broker_capital_operations(db, account_id):
        query = db.query(models.CapitalOperation).filter(
            models.CapitalOperation.account_id == account_id,
        )
        if start is not None:
            query = query.filter(models.CapitalOperation.date >= start)
        if end is not None:
            query = query.filter(models.CapitalOperation.date <= end)

        events = []
        for operation in query.order_by(models.CapitalOperation.date.asc(), models.CapitalOperation.id.asc()).all():
            amount = float(cast(Decimal, operation.amount) or 0)
            operation_type = cast(str, operation.operation_type)
            events.append({
                "date": cast(datetime, operation.date),
                "amount": amount if operation_type == "deposit" else -amount,
                "kind": operation_type,
            })
        return events

    query = db.query(models.DepositHistory).filter(
        models.DepositHistory.account_id == account_id,
    )
    if start is not None:
        query = query.filter(models.DepositHistory.date >= start)
    if end is not None:
        query = query.filter(models.DepositHistory.date <= end)

    events = []
    for item in query.order_by(models.DepositHistory.date.asc(), models.DepositHistory.id.asc()).all():
        operation_type = cast(models.DepositOperationType, item.operation_type)
        if operation_type == models.DepositOperationType.INITIAL:
            continue
        events.append({
            "date": cast(datetime, item.date),
            "amount": float(cast(Decimal, item.amount) or 0),
            "kind": operation_type.value,
        })
    return events


def _infer_initial_history_date(db: Session, account_id: int) -> datetime:
    earliest_snapshot = db.query(models.BalanceSnapshot).filter(
        models.BalanceSnapshot.account_id == account_id,
    ).order_by(models.BalanceSnapshot.date.asc()).first()
    if earliest_snapshot is not None:
        snapshot_date = cast(datetime | None, earliest_snapshot.date)
        if snapshot_date is not None:
            return snapshot_date

    earliest_trade = db.query(models.Trade).filter(
        models.Trade.account_id == account_id,
        models.Trade.entry_at.isnot(None),
    ).order_by(models.Trade.entry_at.asc()).first()
    if earliest_trade is not None:
        entry_at = cast(datetime | None, earliest_trade.entry_at)
        if entry_at is not None:
            return entry_at

    return utc_now_naive()


def sync_initial_balance(
    db: Session,
    account_id: int,
    amount: float,
    *,
    date: Optional[datetime] = None,
    note: Optional[str] = None,
    commit: bool = False,
) -> None:
    account = db.query(models.Account).filter(models.Account.id == account_id).first()
    if not account:
        return

    normalized_amount = float(amount or 0)
    setattr(account, "initial_balance", Decimal(str(normalized_amount)))

    existing = db.query(models.DepositHistory).filter(
        models.DepositHistory.account_id == account_id,
        models.DepositHistory.operation_type == models.DepositOperationType.INITIAL,
    ).first()

    if normalized_amount <= 0:
        if existing:
            db.delete(existing)
        if commit:
            db.commit()
        return

    existing_date = cast(datetime | None, existing.date) if existing is not None else None
    existing_note = cast(str | None, existing.note) if existing is not None else None
    operation_date = date or existing_date or _infer_initial_history_date(db, account_id)
    operation_note = note or existing_note or "Начальный депозит"
    normalized_decimal = Decimal(str(normalized_amount))

    if existing:
        setattr(existing, "amount", normalized_decimal)
        setattr(existing, "balance_after", normalized_decimal)
        setattr(existing, "date", operation_date)
        setattr(existing, "note", operation_note)
    else:
        db.add(models.DepositHistory(
            account_id=account_id,
            operation_type=models.DepositOperationType.INITIAL,
            amount=normalized_decimal,
            balance_after=normalized_decimal,
            date=operation_date,
            note=operation_note,
        ))

    if commit:
        db.commit()


def ensure_initial_balance_history(db: Session, account_id: int, *, commit: bool = False) -> None:
    account = db.query(models.Account).filter(models.Account.id == account_id).first()
    if not account:
        return

    has_capital_operations = db.query(models.CapitalOperation).filter(
        models.CapitalOperation.account_id == account_id,
    ).first()
    if has_capital_operations:
        return

    amount = float(cast(Decimal | None, account.initial_balance) or 0)
    if amount <= 0:
        return

    existing = db.query(models.DepositHistory).filter(
        models.DepositHistory.account_id == account_id,
        models.DepositHistory.operation_type == models.DepositOperationType.INITIAL,
    ).first()
    if existing:
        return

    sync_initial_balance(
        db,
        account_id,
        amount,
        note=SYNTHETIC_INITIAL_NOTE,
        commit=commit,
    )


def cleanup_synthetic_initial_balance_history(db: Session, account_id: int, *, commit: bool = False) -> None:
    has_capital_operations = db.query(models.CapitalOperation).filter(
        models.CapitalOperation.account_id == account_id,
    ).first()
    if not has_capital_operations:
        return

    synthetic_initial = db.query(models.DepositHistory).filter(
        models.DepositHistory.account_id == account_id,
        models.DepositHistory.operation_type == models.DepositOperationType.INITIAL,
        models.DepositHistory.note == SYNTHETIC_INITIAL_NOTE,
    ).first()
    if not synthetic_initial:
        return

    db.delete(synthetic_initial)
    if commit:
        db.commit()
