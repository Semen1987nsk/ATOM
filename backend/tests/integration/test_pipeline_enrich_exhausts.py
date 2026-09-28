"""S2-07: enrich резолвит ВСЕ missing инструменты за прогон (циклом по чанкам),
а не только первые max_instruments_per_run. Иначе сделки по инструментам 51+
на первом sync теряются навсегда.

Примечание: `_stage_enrich(operations)` принимает Sequence[Operation] и сам
извлекает уникальные instrument_uid через `_extract_unique_uids`. Поэтому вход
подаётся как mock-операции с атрибутом `.instrument_uid`, а `missing_uids` /
`upsert_many` репозитория подменяются.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from application.sync.pipeline import SyncPipeline


@pytest.mark.asyncio
async def test_enrich_resolves_all_missing_across_chunks(monkeypatch):
    # 120 missing uid'ов, лимит 50 — должны разрешиться все 120.
    missing_uids = [f"uid-{i}" for i in range(120)]

    operations = []
    for uid in missing_uids:
        op = MagicMock()
        op.instrument_uid = uid
        operations.append(op)

    pipe = SyncPipeline(
        account_id=1,
        broker_account_id="B1",
        token_plaintext="t",
        session_factory=MagicMock(),
        max_instruments_per_run=50,
    )

    # missing_uids() всегда возвращает ещё-не-разрешённые.
    resolved_uids: list[str] = []

    def _missing_uids(session, uids):
        return [u for u in missing_uids if u not in resolved_uids]

    monkeypatch.setattr(pipe._instrument_repo, "missing_uids", _missing_uids)
    monkeypatch.setattr(
        pipe._instrument_repo,
        "upsert_many",
        lambda session, insts: resolved_uids.extend(i.uid for i in insts),
    )

    async def _fake_get_instrument_by_uid(uid):
        inst = MagicMock()
        inst.uid = uid
        return inst

    with patch("application.sync.pipeline.client_factory") as cf, \
         patch("application.sync.pipeline.TinkoffInstrumentsClient") as ic:
        cf.async_client.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
        cf.async_client.return_value.__aexit__ = AsyncMock(return_value=False)
        ic.return_value.get_instrument_by_uid = _fake_get_instrument_by_uid

        total = await pipe._stage_enrich(operations)

    assert sorted(resolved_uids) == sorted(missing_uids)
    assert total == 120
