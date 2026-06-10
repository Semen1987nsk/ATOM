# backend/tests/unit/test_operations_client_timeout.py
"""SYNC-03: зависший gRPC RPC обрывается call-level таймаутом и поднимается
как BrokerUnavailable (retryable), не вешает лимитер/семафор навсегда."""
from __future__ import annotations

import asyncio

import pytest

from adapters.tinkoff.operations_client import TinkoffOperationsClient
from domain.exceptions import BrokerUnavailable


class _NoopLimiter:
    async def __aenter__(self): return self
    async def __aexit__(self, *a): return None


class _HangingOps:
    async def get_portfolio(self, account_id):
        await asyncio.sleep(60)  # «зависает»


class _Services:
    def __init__(self):
        self.limiter = _NoopLimiter()
        self.broker_report_limiter = _NoopLimiter()
        self.operations = _HangingOps()


@pytest.mark.asyncio
async def test_hanging_rpc_times_out_as_broker_unavailable(monkeypatch):
    monkeypatch.setattr(
        "adapters.tinkoff.operations_client.settings.TINKOFF_GRPC_CALL_TIMEOUT_SECONDS",
        0.05,
        raising=False,
    )
    # tenacity ретраит BrokerUnavailable 5x — урезаем до 1 попытки для скорости.
    monkeypatch.setattr(
        "adapters.tinkoff.operations_client._retry_policy",
        lambda: __import__("tenacity").AsyncRetrying(
            stop=__import__("tenacity").stop_after_attempt(1), reraise=True
        ),
    )
    client = TinkoffOperationsClient(_Services())
    with pytest.raises(BrokerUnavailable):
        await asyncio.wait_for(client.get_portfolio_raw("acc"), timeout=2.0)
