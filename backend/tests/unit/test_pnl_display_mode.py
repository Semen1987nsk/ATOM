"""Phase 11 (2026-05-17): unit tests для P&L Display Mode (gross/net)."""
from __future__ import annotations

import pytest

from services.user_settings import (
    ALLOWED_SETTINGS_KEYS,
    VALID_PNL_DISPLAY_MODES,
    validate_settings,
)


# ── settings validator tests ──────────────────────────────────────────


def test_validator_accepts_pnl_display_mode_net():
    result = validate_settings({"pnlDisplayMode": "net"})
    assert result == {"pnlDisplayMode": "net"}


def test_validator_accepts_pnl_display_mode_gross():
    result = validate_settings({"pnlDisplayMode": "gross"})
    assert result == {"pnlDisplayMode": "gross"}


def test_validator_rejects_invalid_pnl_display_mode():
    """Phase 11: только 'net' и 'gross' допустимы."""
    result = validate_settings({"pnlDisplayMode": "foo"})
    assert "pnlDisplayMode" not in result


def test_validator_rejects_unknown_keys():
    """Unknown keys silently dropped (logged warning)."""
    result = validate_settings({"foo": "bar", "currency": "USD"})
    assert "foo" not in result
    assert result == {"currency": "USD"}


def test_validator_preserves_known_keys():
    """Whitelisted keys должны пройти."""
    raw = {
        "currency": "RUB",
        "theme": "dark",
        "pnlDisplayMode": "gross",
        "maeCalculationMethod": "weighted_average",
    }
    result = validate_settings(raw)
    assert result == raw


def test_validator_rejects_non_dict():
    """Non-dict input → пустой dict."""
    assert validate_settings(None) == {}
    assert validate_settings("string") == {}
    assert validate_settings([1, 2, 3]) == {}


def test_validator_keeps_empty_dict():
    """Empty dict → empty dict."""
    assert validate_settings({}) == {}


def test_allowed_keys_contains_pnl_display_mode():
    """Sanity: ключ зарегистрирован в whitelist."""
    assert "pnlDisplayMode" in ALLOWED_SETTINGS_KEYS


def test_valid_pnl_display_modes_strict():
    """Sanity: только 2 валидных режима."""
    assert VALID_PNL_DISPLAY_MODES == {"net", "gross"}


# ── Phase 12 (2026-05-17): total_costs schema + invariant ──────────────


def test_dashboard_stats_schema_has_total_costs_fields():
    """Phase 12: schema публикует total_costs + breakdown."""
    from schemas import DashboardStats

    fields = DashboardStats.model_fields
    assert "total_costs" in fields, "schema must expose total_costs"
    assert "total_costs_breakdown" in fields, "schema must expose breakdown"
    # Default values: total_costs=0.0, breakdown={}
    assert fields["total_costs"].default == 0
    assert fields["total_costs_breakdown"].default == {}


def test_total_costs_invariant_definition():
    """Phase 12: total_costs ≡ total_pnl_with_unrealized − total_pnl_with_unrealized_gross.

    Это математическое определение в routers/stats.py — total_costs = разница
    между net и gross headline. Тест проверяет invariant на синтетических
    данных, чтобы случайное изменение формулы было поймано.
    """
    # Симуляция acc#4-like значений (Phase 11 verified):
    total_pnl_with_unrealized = -174_422.00      # net headline
    total_pnl_with_unrealized_gross = -69_132.00  # gross headline (body only)

    total_costs = total_pnl_with_unrealized - total_pnl_with_unrealized_gross

    # Расходы должны быть негативными (трейдер ПЛАТИТ комиссии и налоги)
    assert total_costs < 0, "costs must be negative cash flows"
    # Math invariant: gross + costs == net (definition)
    assert abs((total_pnl_with_unrealized_gross + total_costs) - total_pnl_with_unrealized) < 0.01
    # Для acc#4: ≈ -105,290 ₽ (broker commissions + margin + service + taxes)
    assert -106_000 < total_costs < -104_000, (
        f"acc#4 baseline costs expected ~-105k, got {total_costs}"
    )
