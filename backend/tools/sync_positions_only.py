"""Phase 7 helper: запустить ТОЛЬКО _stage_mark_to_market без full re-sync.

Это populate новые Position поля (expected_yield_rub, var_margin_rub,
daily_yield_rub) из живого Tinkoff portfolio API без полной перекачки
operations history.

Usage:
    python -X utf8 -m tools.sync_positions_only --account-id 4
"""
from __future__ import annotations

import argparse
import asyncio
import sys

import database
import models
from adapters.persistence.token_repo import TokenRepository
from adapters.security.token_encryption import TokenEncryptionService


async def main_async(account_id: int) -> int:
    from application.sync.pipeline import SyncPipeline

    session = database.SessionLocal()
    try:
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
        enc = TokenEncryptionService()
        repo = TokenRepository(encryption=enc)
        token = repo.get_decrypted(
            session, account_id=account_id, broker_account_id=conn.broker_account_id
        )
        if not token:
            print("Token missing")
            return 2
        broker_account_id = conn.broker_account_id
    finally:
        session.close()

    pipeline = SyncPipeline.__new__(SyncPipeline)
    pipeline._account_id = account_id
    pipeline._broker_account_id = broker_account_id
    pipeline._token = token
    pipeline._session_factory = database.SessionLocal
    pipeline._last_live_position_uids = set()
    pipeline._last_portfolio_total_rub = None

    await pipeline._stage_mark_to_market()
    print(f"acc#{account_id}: _stage_mark_to_market done")
    return 0


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--account-id", type=int, required=True)
    args = p.parse_args()
    return asyncio.run(main_async(args.account_id))


if __name__ == "__main__":
    sys.exit(main())
