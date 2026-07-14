"""Unit-тесты TinkoffOperationsClient.get_dividends_foreign_issuer.

Регрессия (pre-existing баг, найден при апгрейде SDK 0.3.5->1.49.2): метод строил
`GetDividendsForeignIssuerRequest(account_id=...)` и звал `get_dividends_foreign_issuer(request)`
позиционно. Но SDK-метод — keyword-only oneof (generate_div_foreign_issuer_report= /
get_div_foreign_issuer_report=) и в 0.3.5, и в 1.49.2 -> TypeError всегда.
Корректный flow зеркалит fetch_full_broker_report: generate (-> task_id) затем
get по task_id постранично. Отчёт генерируется асинхронно -> поллинг "not ready".
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

from adapters.tinkoff.operations_client import TinkoffOperationsClient
from domain.exceptions import BrokerError


def _money(units: int, nano: int = 0) -> SimpleNamespace:
    return SimpleNamespace(units=units, nano=nano)


def _row(name: str, gross_units: int, tax_units: int) -> SimpleNamespace:
    return SimpleNamespace(
        record_date=None,
        payment_date=None,
        security_name=name,
        isin=f"ISIN-{name}",
        issuer_country="US",
        quantity=1,
        dividend=_money(gross_units),
        dividend_gross=_money(gross_units),
        external_commission=_money(0),
        tax=_money(tax_units),
        dividend_amount=_money(gross_units - tax_units),
        currency="usd",
    )


def _get_wrapper(rows: list, *, pages_count: int = 1, page: int = 0) -> SimpleNamespace:
    return SimpleNamespace(
        div_foreign_issuer_report=SimpleNamespace(
            dividends_foreign_issuer_report=rows,
            itemsCount=len(rows),
            pagesCount=pages_count,
            page=page,
        )
    )


def _generate_resp(task_id: str) -> SimpleNamespace:
    return SimpleNamespace(
        generate_div_foreign_issuer_report_response=SimpleNamespace(task_id=task_id),
        div_foreign_issuer_report=None,
    )


def test_two_step_generate_then_get_returns_mapped_rows() -> None:
    """generate -> task_id, get(page=0) -> строки, маппинг в dict с dividend_gross/tax."""
    rows = [_row("AAPL", 10, 2), _row("MSFT", 5, 1)]
    page0 = _get_wrapper(rows, pages_count=1)
    calls = {"generate": 0, "get_pages": []}
    services = MagicMock()

    async def fake(*, generate_div_foreign_issuer_report=None, get_div_foreign_issuer_report=None):
        if generate_div_foreign_issuer_report is not None:
            calls["generate"] += 1
            # generate-запрос построен правильным классом с from_/to (не падает)
            assert generate_div_foreign_issuer_report.account_id == "acc-1"
            return _generate_resp("task-1")
        assert get_div_foreign_issuer_report is not None
        assert get_div_foreign_issuer_report.task_id == "task-1"
        calls["get_pages"].append(get_div_foreign_issuer_report.page)
        return page0

    services.operations.get_dividends_foreign_issuer = fake
    client = TinkoffOperationsClient(services)

    result = asyncio.run(
        client.get_dividends_foreign_issuer(
            "acc-1", from_dt=datetime(2026, 1, 1), to_dt=datetime(2026, 3, 31)
        )
    )

    assert calls["generate"] == 1
    assert calls["get_pages"] == [0]
    assert [r["security_name"] for r in result] == ["AAPL", "MSFT"]
    assert result[0]["dividend_gross"].units == 10
    assert result[0]["tax"].units == 2
    assert result[1]["dividend_gross"].units == 5
    assert result[1]["currency"] == "usd"


def test_polls_until_report_ready(monkeypatch) -> None:
    """Первый get -> not_ready (30058) -> backoff -> второй get -> готово."""
    import adapters.tinkoff.operations_client as opmod

    rows = [_row("AAPL", 10, 2)]
    page0 = _get_wrapper(rows, pages_count=1)
    state = {"gets": 0}
    services = MagicMock()

    async def fake(*, generate_div_foreign_issuer_report=None, get_div_foreign_issuer_report=None):
        if generate_div_foreign_issuer_report is not None:
            return _generate_resp("t9")
        state["gets"] += 1
        if state["gets"] == 1:
            raise BrokerError("dividends report not_ready (code 30058)")
        return page0

    services.operations.get_dividends_foreign_issuer = fake

    async def _no_sleep(*_a, **_k):
        return None

    monkeypatch.setattr(opmod.asyncio, "sleep", _no_sleep)
    client = TinkoffOperationsClient(services)

    result = asyncio.run(
        client.get_dividends_foreign_issuer(
            "acc", from_dt=datetime(2026, 1, 1), to_dt=datetime(2026, 3, 31)
        )
    )

    assert state["gets"] == 2
    assert len(result) == 1
    assert result[0]["security_name"] == "AAPL"


def test_no_task_id_returns_empty() -> None:
    """Generate без task_id (пустой отчёт) -> пустой список, без падения."""
    services = MagicMock()

    async def fake(*, generate_div_foreign_issuer_report=None, get_div_foreign_issuer_report=None):
        if generate_div_foreign_issuer_report is not None:
            return _generate_resp("")
        raise AssertionError("get must not be called without task_id")

    services.operations.get_dividends_foreign_issuer = fake
    client = TinkoffOperationsClient(services)

    result = asyncio.run(
        client.get_dividends_foreign_issuer(
            "acc", from_dt=datetime(2026, 1, 1), to_dt=datetime(2026, 3, 31)
        )
    )
    assert result == []
