"""
PR 26 (Phase 3, D9) — Golden master regression tests.

Каждая фикстура в `tests/fixtures/golden_broker_reports/` — это
анонимизированный broker report с expected_metrics. Тест:
1. Загружает фикстуру
2. Прогоняет через aggregate_broker_report
3. Сверяет что вычисленные totals совпадают с expected_metrics

CI gate: ЛЮБОЕ изменение в reconciliation_service / pnl-расчёте — все
5 фикстур должны давать identical totals. Это даёт уверенность что мы
не сломали ничего в трансформации при рефакторинге.
"""

from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from domain.entities import BrokerReportTradeRow
from services.reconciliation_service import aggregate_broker_report


_FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "golden_broker_reports"


def _parse_iso(s: str) -> datetime:
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    return datetime.fromisoformat(s)


def _row_from_fixture(row_dict: dict[str, Any]) -> BrokerReportTradeRow:
    """Конвертирует JSON-фикстуру в BrokerReportTradeRow для теста."""
    def _dec(v) -> Decimal | None:
        return Decimal(v) if v is not None else None

    return BrokerReportTradeRow(
        trade_id=row_dict["trade_id"],
        direction=row_dict.get("direction"),
        ticker=row_dict.get("ticker"),
        name=row_dict.get("name"),
        trade_datetime=_parse_iso(row_dict["trade_datetime"]),
        quantity=row_dict.get("quantity", 0),
        price=_dec(row_dict.get("price")),
        order_amount=_dec(row_dict.get("order_amount")),
        total_order_amount=_dec(row_dict.get("total_order_amount")),
        aci_value=_dec(row_dict.get("aci_value")),
        broker_commission=_dec(row_dict.get("broker_commission")),
        exchange_commission=_dec(row_dict.get("exchange_commission")),
        exchange_clearing_commission=_dec(row_dict.get("exchange_clearing_commission")),
        currency=row_dict.get("currency", "rub"),
    )


def _foreign_div(d: dict[str, Any]) -> dict[str, Any]:
    """Imitate Tinkoff foreign dividend proto for aggregate_broker_report."""
    from dataclasses import dataclass

    @dataclass
    class _MV:
        units: int = 0
        nano: int = 0

    def _to_mv(value):
        if value is None:
            return None
        dec = Decimal(value)
        sign = -1 if dec < 0 else 1
        abs_dec = abs(dec)
        units = int(abs_dec)
        nano = int((abs_dec - Decimal(units)) * Decimal(1_000_000_000))
        return _MV(units=sign * units, nano=sign * nano)

    return {
        "dividend_gross": _to_mv(d.get("dividend_gross")),
        "tax": _to_mv(d.get("tax")),
        "dividend_amount": _to_mv(d.get("dividend_amount")),
        "security_name": d.get("security_name"),
        "isin": d.get("isin"),
    }


def _list_fixtures() -> list[Path]:
    return sorted(_FIXTURES_DIR.glob("*.json"))


@pytest.mark.parametrize("fixture_path", _list_fixtures(), ids=lambda p: p.stem)
def test_golden_broker_report_aggregates(fixture_path: Path) -> None:
    """Каждая фикстура: aggregate_broker_report должен давать ожидаемые totals."""
    with open(fixture_path, "r", encoding="utf-8") as f:
        fixture = json.load(f)

    rows = [_row_from_fixture(r) for r in fixture["broker_report"]]
    foreign_divs = [_foreign_div(d) for d in fixture.get("foreign_dividends", [])]

    result = aggregate_broker_report(rows, foreign_divs)

    expected = fixture["expected_metrics"]
    # Strict-compare keys, presented in expected:
    if "broker_commission_total" in expected:
        assert result["broker_commission_total"] == Decimal(expected["broker_commission_total"]), \
            f"broker_commission_total mismatch in {fixture_path.name}"
    if "exchange_commission_total" in expected:
        assert result["exchange_commission_total"] == Decimal(expected["exchange_commission_total"]), \
            f"exchange_commission_total mismatch in {fixture_path.name}"
    if "clearing_commission_total" in expected:
        assert result["clearing_commission_total"] == Decimal(expected["clearing_commission_total"]), \
            f"clearing_commission_total mismatch in {fixture_path.name}"
    if "dividends_gross" in expected:
        assert result["dividends_gross"] == Decimal(expected["dividends_gross"]), \
            f"dividends_gross mismatch in {fixture_path.name}"
    if "ndfl_withheld" in expected:
        assert result["ndfl_withheld"] == Decimal(expected["ndfl_withheld"]), \
            f"ndfl_withheld mismatch in {fixture_path.name}"

    # realized_pnl_approximate — мягкая проверка с tolerance 1₽
    if "realized_pnl_approximate" in expected:
        actual = result["realized_pnl"]
        expected_pnl = Decimal(expected["realized_pnl_approximate"])
        assert abs(actual - expected_pnl) <= Decimal("1"), \
            f"realized_pnl mismatch in {fixture_path.name}: actual={actual} expected≈{expected_pnl}"


def test_fixtures_exist() -> None:
    """Должно быть как минимум 5 фикстур (per план Phase 3)."""
    fixtures = _list_fixtures()
    assert len(fixtures) >= 5, f"Expected ≥5 golden fixtures, found {len(fixtures)}"


def test_all_fixtures_have_required_fields() -> None:
    """Каждая фикстура должна иметь description, broker_report, expected_metrics."""
    for path in _list_fixtures():
        with open(path, "r", encoding="utf-8") as f:
            fixture = json.load(f)
        assert "description" in fixture, f"{path.name}: missing description"
        assert "broker_report" in fixture, f"{path.name}: missing broker_report"
        assert "expected_metrics" in fixture, f"{path.name}: missing expected_metrics"
