"""S2-17: сбой ВСТАВКИ live-позиций (не BrokerError на fetch) пробрасывается,
а не глотается — иначе sync репортит success с протухшим снапшотом позиций.
"""
from unittest.mock import MagicMock

import pytest

from application.sync.pipeline import SyncPipeline


def test_replace_positions_insert_error_propagates(monkeypatch):
    pipe = SyncPipeline(
        account_id=1, broker_account_id="B1", token_plaintext="t",
        session_factory=MagicMock(),
    )
    bad_session = MagicMock()
    bad_session.commit.side_effect = RuntimeError("bad quantity")
    monkeypatch.setattr(pipe, "_session_factory", lambda: bad_session)

    positions = [{"instrument_uid": "u1", "quantity": 1}]  # форма по факту метода
    with pytest.raises(RuntimeError, match="bad quantity"):
        pipe._replace_positions_from_live(positions)
