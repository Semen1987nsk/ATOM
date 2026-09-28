"""Diagnose broker_report response shape для AU10 verification."""

from __future__ import annotations

import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

import models
from adapters.persistence.token_repo import TokenRepository
from adapters.security.token_encryption import TokenEncryptionService
from adapters.tinkoff.client_factory import client_factory
from database import SessionLocal


async def main():
    if len(sys.argv) < 2:
        print("Usage: python -m tools.diagnose_broker_report <account_id>")
        sys.exit(1)
    account_id = int(sys.argv[1])

    db = SessionLocal()
    try:
        conn = db.query(models.BrokerConnection).filter_by(
            account_id=account_id, is_active=True
        ).first()
        if not conn:
            print(f"No active BrokerConnection for account_id={account_id}")
            sys.exit(1)

        token_repo = TokenRepository(encryption=TokenEncryptionService())
        token = token_repo.decrypt(conn.api_token)
        print(f"Token decrypted OK (length {len(token)})")
        print(f"broker_account_id={conn.broker_account_id}")
    finally:
        db.close()

    from t_tech.invest.schemas import GenerateBrokerReportRequest

    now = datetime.now(timezone.utc)
    from_dt = now - timedelta(days=30)
    request = GenerateBrokerReportRequest(
        account_id=conn.broker_account_id,
        from_=from_dt,
        to=now,
    )

    async with client_factory.async_client(token) as services:
        print(f"Calling get_broker_report(generate_broker_report_request=...)")
        resp = await services.operations.get_broker_report(
            generate_broker_report_request=request,
        )
        print(f"\nResponse type: {type(resp).__name__}")
        print(f"Response repr:\n  {resp!r}")
        print()
        print("Attributes available on response:")
        for name in dir(resp):
            if name.startswith("_"):
                continue
            val = getattr(resp, name, None)
            if callable(val):
                continue
            print(f"  .{name} = {val!r}")


if __name__ == "__main__":
    asyncio.run(main())
