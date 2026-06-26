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
from services import pnl_health_service
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

    # 2. Аггрегаты из БД операций — по категориям из единого классификатора.
    # До 2026-05-17 здесь был hardcoded type_to_key с 8 типами, упускавший
    # input_swift, output_swift, input_acquiring, output_acquiring, out_multi
    # — пользователи с такими пополнениями получали real_pnl = current_balance
    # (P&L завышен на сумму неучтённых пополнений). См. plan B1.
    from domain.pnl.cash_flow_classification import (
        CASH_FLOW_MAP,
        CashFlowCategory,
    )

    breakdown_by_category: dict[CashFlowCategory, Decimal] = {
        cat: Decimal(0) for cat in CashFlowCategory
    }

    rows = (
        db.query(
            OperationORM.operation_type,
            OperationORM.payment_units,
            OperationORM.payment_nano,
        )
        .filter(
            OperationORM.account_id == account.id,
            OperationORM.state == "executed",
        )
        .all()
    )
    unknown_types: dict[str, int] = {}
    for op_type, units, nano in rows:
        if units is None and nano is None:
            continue
        category = CASH_FLOW_MAP.get(op_type)
        if category is None:
            unknown_types[op_type] = unknown_types.get(op_type, 0) + 1
            category = CashFlowCategory.UNKNOWN
        amount = Decimal(int(units or 0)) + Decimal(int(nano or 0)) / Decimal(1_000_000_000)
        breakdown_by_category[category] += amount

    if unknown_types:
        log.warning(
            "real_pnl.unknown_operation_types",
            extra={"account_id": account.id, "types": unknown_types},
        )

    # 3. Real PnL = current_balance - net_deposit. net_deposit = все каналы
    # NET_DEPOSIT (input, output, swift, acquiring, multi). НЕ включает
    # internal_transfer (trans_iis_bs/trans_bs_bs — зеркальные записи) и
    # security_transfer (input_securities/output_securities — без cash).
    net_deposit = float(breakdown_by_category[CashFlowCategory.NET_DEPOSIT])
    # ADR-0010: effective_deposits = net_deposits + initial_balance (восстановленный
    # стартовый якорь для broker-счёта с неполной историей). На счёте без якоря
    # (initial_balance==0) это тождественно прежнему net_deposit.
    eff_deposit = net_deposit + float(account.initial_balance or 0)
    real_pnl = current_balance - eff_deposit
    roi = (real_pnl / eff_deposit * 100) if eff_deposit > 0 else 0

    health = pnl_health_service.compute_health(db, account.id)
    clearing_adjustment = health.components.get("clearing_adjustment", 0)

    # Pretty breakdown для UI: legacy ключи + категорий-агрегаты.
    breakdown_legacy: dict[str, float] = {
        "stocks_pnl": 0.0,  # требует FIFO matcher result — рекомендуем читать через /stats
        "futures_varmargin": float(breakdown_by_category[CashFlowCategory.VARMARGIN]),
        "broker_fee": float(breakdown_by_category[CashFlowCategory.BROKER_COMMISSION]),
        "margin_fee": 0.0,  # уже в attributable_fee, см. ниже
        "service_fee": 0.0,
        "tax": float(breakdown_by_category[CashFlowCategory.TAX]
                     + breakdown_by_category[CashFlowCategory.INCOME_TAX]),
        "input_total": net_deposit if net_deposit >= 0 else 0.0,
        "output_total": 0.0,
        "coupons": 0.0,  # часть income
        "dividends": 0.0,  # часть income
        "attributable_fee_total": float(breakdown_by_category[CashFlowCategory.ATTRIBUTABLE_FEE]),
        "income_total": float(breakdown_by_category[CashFlowCategory.INCOME]),
        "internal_transfer_total": float(breakdown_by_category[CashFlowCategory.INTERNAL_TRANSFER]),
        "unknown_total": float(breakdown_by_category[CashFlowCategory.UNKNOWN]),
    }

    return {
        "current_balance": round(current_balance, 2),
        "cash": round(cash, 2),
        "net_deposit": round(net_deposit, 2),
        "real_pnl": round(real_pnl, 2),
        "roi": round(roi, 2),
        "breakdown": breakdown_legacy,
        "breakdown_by_category": {
            cat.value: float(amt) for cat, amt in breakdown_by_category.items() if abs(amt) > Decimal("0.01")
        },
        "clearing_adjustment": round(float(clearing_adjustment), 2),
        "health_status": health.status,
        "health_layers": health.components.get("layers", {}),
        "updated_at": utc_now_naive().isoformat(),
    }
