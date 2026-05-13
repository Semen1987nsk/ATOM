"""
Реальный PnL по счёту (PR 12 — переписан после PR 0).

Использует:
* live `TinkoffOperationsClient.get_portfolio_raw()` для текущего баланса,
* локальные `BrokerConnection` + `Trade` для realized PnL и истории.

Не использует битый `tinkoff_service_v2` (удалён в PR 0).
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

import models
from adapters.persistence.token_repo import TokenRepository
from adapters.security.token_encryption import (
    TokenEncryptionError,
    TokenEncryptionService,
)
from adapters.tinkoff.client_factory import client_factory
from adapters.tinkoff.operations_client import TinkoffOperationsClient
from auth_service import get_current_user, get_user_account
from config import settings
from database import get_db
from domain.exceptions import BrokerError, TokenInvalid
from logger import get_logger
from models import BrokerConnection, OperationORM
from utils.datetime_utils import utc_now_naive

log = get_logger("real_pnl")
router = APIRouter(prefix="/real-pnl", tags=["real_pnl"])


def _money_to_decimal(m) -> Decimal:
    if m is None:
        return Decimal(0)
    units = getattr(m, "units", 0) or 0
    nano = getattr(m, "nano", 0) or 0
    return Decimal(int(units)) + Decimal(int(nano)) / Decimal(1_000_000_000)


@router.get("/")
async def get_real_pnl(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """
    Полная сводка реального PnL: текущий баланс + разложение по компонентам
    из локальной БД операций.
    """
    if not settings.BROKER_SYNC_V2_ENABLED:
        raise HTTPException(status_code=503, detail="Broker sync v2 disabled")

    account = get_user_account(db, current_user)
    conn = (
        db.query(BrokerConnection)
        .filter(BrokerConnection.account_id == account.id, BrokerConnection.is_active.is_(True))
        .first()
    )
    if conn is None:
        raise HTTPException(status_code=404, detail="Нет активных подключений")

    # 1. Live портфель.
    try:
        encryption = TokenEncryptionService()
    except TokenEncryptionError as exc:
        raise HTTPException(status_code=500, detail=f"Encryption not configured: {exc}")
    repo = TokenRepository(encryption=encryption)
    try:
        token = repo.get_decrypted(db, account_id=account.id, broker_account_id=conn.broker_account_id)
    except TokenEncryptionError as exc:
        raise HTTPException(status_code=500, detail=f"Decrypt failed: {exc}")
    if not token:
        raise HTTPException(status_code=410, detail="Подключение повреждено")

    try:
        async with client_factory.async_client(token) as services:
            ops = TinkoffOperationsClient(services)
            portfolio = await ops.get_portfolio_raw(conn.broker_account_id)
    except TokenInvalid:
        raise HTTPException(status_code=401, detail="Токен невалиден")
    except BrokerError as exc:
        raise HTTPException(status_code=502, detail=f"Tinkoff API: {exc.message}")

    current_balance = float(_money_to_decimal(getattr(portfolio, "total_amount_portfolio", None)))
    cash = float(_money_to_decimal(getattr(portfolio, "total_amount_currencies", None)))

    # 2. Аггрегаты из БД операций (один запрос на все типы).
    breakdown = {
        "stocks_pnl": Decimal(0),
        "futures_varmargin": Decimal(0),
        "broker_fee": Decimal(0),
        "margin_fee": Decimal(0),
        "service_fee": Decimal(0),
        "tax": Decimal(0),
        "input_total": Decimal(0),
        "output_total": Decimal(0),
        "coupons": Decimal(0),
        "dividends": Decimal(0),
    }

    type_to_key = {
        "accruing_varmargin": "futures_varmargin",
        "writing_off_varmargin": "futures_varmargin",
        "broker_fee": "broker_fee",
        "margin_fee": "margin_fee",
        "service_fee": "service_fee",
        "tax": "tax",
        "tax_progressive": "tax",
        "input": "input_total",
        "output": "output_total",
        "coupon": "coupons",
        "dividend": "dividends",
    }

    rows = (
        db.query(
            OperationORM.operation_type,
            OperationORM.payment_units,
            OperationORM.payment_nano,
        )
        .filter(
            OperationORM.account_id == account.id,
            OperationORM.operation_type.in_(tuple(type_to_key.keys())),
            OperationORM.state == "executed",
        )
        .all()
    )
    for op_type, units, nano in rows:
        key = type_to_key.get(op_type)
        if key is None:
            continue
        if units is None and nano is None:
            continue
        amount = Decimal(int(units or 0)) + Decimal(int(nano or 0)) / Decimal(1_000_000_000)
        breakdown[key] += amount

    # 3. Real PnL = current_balance - net_deposit.
    net_deposit = float(breakdown["input_total"] + breakdown["output_total"])
    real_pnl = current_balance - net_deposit
    roi = (real_pnl / net_deposit * 100) if net_deposit > 0 else 0

    return {
        "current_balance": round(current_balance, 2),
        "cash": round(cash, 2),
        "net_deposit": round(net_deposit, 2),
        "real_pnl": round(real_pnl, 2),
        "roi": round(roi, 2),
        "breakdown": {k: float(v) for k, v in breakdown.items()},
        "updated_at": utc_now_naive().isoformat(),
    }
