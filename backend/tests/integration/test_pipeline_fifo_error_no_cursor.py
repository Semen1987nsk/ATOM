"""SYNC-08 / S2-08: если per-uid FIFO падает неожиданным исключением (не
InstrumentNotFound), pipeline НЕ двигает курсор и репортит error, а не success.
Раньше generic except глотал всё → курсор коммитился → протухшие сделки.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from application.sync.pipeline import SyncPipeline


@pytest.mark.asyncio
async def test_fifo_db_error_does_not_swallow(monkeypatch):
    pipe = SyncPipeline(
        account_id=1, broker_account_id="B1", token_plaintext="t",
        session_factory=MagicMock(),
    )

    op = MagicMock()
    op.instrument_uid = "uid-1"
    monkeypatch.setattr(pipe, "_extract_unique_uids", lambda ops: ["uid-1"])

    # instrument резолвится, но replace_for_instrument падает deadlock'ом.
    inst = MagicMock()
    monkeypatch.setattr(pipe._instrument_repo, "get_by_uid", lambda s, u: inst)
    monkeypatch.setattr(pipe._operation_repo, "fetch_for_instrument", lambda *a, **k: [])
    monkeypatch.setattr(pipe._position_repo, "get_open_lots", lambda *a, **k: ())
    monkeypatch.setattr(pipe._fifo_service, "match",
                        lambda **k: MagicMock(closed_trades=[], open_lots=[]))

    def _boom(*a, **k):
        raise RuntimeError("deadlock detected")

    monkeypatch.setattr(pipe._trade_repo, "replace_for_instrument", _boom)

    with pytest.raises(RuntimeError, match="deadlock"):
        await pipe._stage_fifo_match([op])
