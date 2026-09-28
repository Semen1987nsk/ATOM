"""Phase 7.0 (2026-05-17): Дамп ВСЕХ полей Tinkoff PortfolioResponse для acc#4.

Цель — увидеть точные значения `var_margin`, `expected_yield`, `daily_yield`
для каждой открытой позиции и сравнить с нашей текущей формулой
`(current - avg) × qty × pv`.

Usage:
    python -X utf8 -m tools.dump_live_portfolio --account-id 4
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime
from decimal import Decimal

import database
import models
from adapters.persistence.token_repo import TokenRepository
from adapters.security.token_encryption import (
    TokenEncryptionError,
    TokenEncryptionService,
)
from adapters.tinkoff.client_factory import client_factory
from adapters.tinkoff.operations_client import TinkoffOperationsClient


def money_to_decimal(m) -> dict | None:
    """MoneyValue {units, nano, currency} → dict с decimal value."""
    if m is None:
        return None
    units = getattr(m, "units", 0) or 0
    nano = getattr(m, "nano", 0) or 0
    currency = getattr(m, "currency", "") or ""
    value = Decimal(int(units)) + Decimal(int(nano)) / Decimal(1_000_000_000)
    return {"value": float(value), "currency": currency, "units": int(units), "nano": int(nano)}


def quotation_to_decimal(q) -> dict | None:
    """Quotation {units, nano} → dict с decimal value. Может быть % или абсолют."""
    if q is None:
        return None
    units = getattr(q, "units", 0) or 0
    nano = getattr(q, "nano", 0) or 0
    value = Decimal(int(units)) + Decimal(int(nano)) / Decimal(1_000_000_000)
    return {"value": float(value), "units": int(units), "nano": int(nano)}


def position_to_dict(p) -> dict:
    """Все 14 полей PortfolioPosition."""
    return {
        "figi": getattr(p, "figi", None),
        "ticker": getattr(p, "ticker", None),
        "instrument_type": getattr(p, "instrument_type", None),
        "instrument_uid": getattr(p, "instrument_uid", None),
        "position_uid": getattr(p, "position_uid", None),
        "quantity": quotation_to_decimal(getattr(p, "quantity", None)),
        "quantity_lots": quotation_to_decimal(getattr(p, "quantity_lots", None)),
        "average_position_price": money_to_decimal(getattr(p, "average_position_price", None)),
        "average_position_price_fifo": money_to_decimal(getattr(p, "average_position_price_fifo", None)),
        "current_price": money_to_decimal(getattr(p, "current_price", None)),
        "current_nkd": money_to_decimal(getattr(p, "current_nkd", None)),
        "expected_yield": quotation_to_decimal(getattr(p, "expected_yield", None)),
        "expected_yield_fifo": quotation_to_decimal(getattr(p, "expected_yield_fifo", None)),
        "var_margin": money_to_decimal(getattr(p, "var_margin", None)),
        "daily_yield": money_to_decimal(getattr(p, "daily_yield", None)),
        "blocked": getattr(p, "blocked", None),
        "blocked_lots": quotation_to_decimal(getattr(p, "blocked_lots", None)),
    }


def portfolio_to_dict(raw) -> dict:
    """Все top-level поля PortfolioResponse + positions[]."""
    return {
        "account_id": getattr(raw, "account_id", None),
        "total_amount_shares": money_to_decimal(getattr(raw, "total_amount_shares", None)),
        "total_amount_bonds": money_to_decimal(getattr(raw, "total_amount_bonds", None)),
        "total_amount_etf": money_to_decimal(getattr(raw, "total_amount_etf", None)),
        "total_amount_currencies": money_to_decimal(getattr(raw, "total_amount_currencies", None)),
        "total_amount_futures": money_to_decimal(getattr(raw, "total_amount_futures", None)),
        "total_amount_options": money_to_decimal(getattr(raw, "total_amount_options", None)),
        "total_amount_sp": money_to_decimal(getattr(raw, "total_amount_sp", None)),
        "total_amount_portfolio": money_to_decimal(getattr(raw, "total_amount_portfolio", None)),
        "expected_yield": quotation_to_decimal(getattr(raw, "expected_yield", None)),
        "daily_yield": money_to_decimal(getattr(raw, "daily_yield", None)),
        "daily_yield_relative": quotation_to_decimal(getattr(raw, "daily_yield_relative", None)),
        "positions": [position_to_dict(p) for p in getattr(raw, "positions", [])],
    }


async def main_async(account_id: int) -> int:
    session = database.SessionLocal()
    try:
        account = session.get(models.Account, account_id)
        if account is None:
            print(f"Account {account_id} not found")
            return 2

        conn = (
            session.query(models.BrokerConnection)
            .filter(
                models.BrokerConnection.account_id == account_id,
                models.BrokerConnection.is_active.is_(True),
            )
            .first()
        )
        if conn is None:
            print(f"No active BrokerConnection for account {account_id}")
            return 2

        try:
            enc = TokenEncryptionService()
        except TokenEncryptionError as e:
            print(f"Encryption setup failed: {e}")
            return 2
        repo = TokenRepository(encryption=enc)
        try:
            token = repo.get_decrypted(session, account_id=account_id, broker_account_id=conn.broker_account_id)
        except TokenEncryptionError as e:
            print(f"Token decrypt failed: {e}")
            return 2
        if not token:
            print("Token missing")
            return 2

        broker_account_id = conn.broker_account_id
    finally:
        session.close()

    async with client_factory.async_client(token) as services:
        ops = TinkoffOperationsClient(services)
        raw = await ops.get_portfolio_raw(broker_account_id)

    dump = portfolio_to_dict(raw)
    dump["_meta"] = {
        "account_id": account_id,
        "broker_account_id": broker_account_id,
        "dumped_at": datetime.utcnow().isoformat(),
    }
    return dump


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--account-id", type=int, required=True)
    p.add_argument("--output", type=str, default=None, help="JSON output file (default: stdout)")
    args = p.parse_args()

    result = asyncio.run(main_async(args.account_id))
    if isinstance(result, int):
        return result

    text = json.dumps(result, indent=2, ensure_ascii=False)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"Saved to {args.output}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
