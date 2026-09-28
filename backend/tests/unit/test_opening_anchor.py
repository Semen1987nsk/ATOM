"""Unit: pure opening-balance anchor decision (ADR-0010). No I/O.

Oracles = acc#2 (Артём, 2135909232) snapshot, см. spec §3.
"""
from decimal import Decimal

from domain.pnl.opening_anchor import (
    ANCHOR_MAX_FACTOR,
    AnchorDecision,
    compute_candidate_anchor,
    decide_anchor,
    telescope_residual,
)

ACC2 = dict(
    incomplete_history=True,
    portfolio_value=Decimal("32938"),
    net_deposits=Decimal("8556"),
    journal_pnl=Decimal("-74713"),
    body_closed=Decimal("-70754"),
    varmargin_net=Decimal("-86799"),
    open_settled=Decimal("-7920"),
    gross_buy_peak=Decimal("93029.60"),
)


def test_candidate_formula_matches_acc2():
    got = compute_candidate_anchor(
        portfolio_value=Decimal("32938"),
        net_deposits=Decimal("8556"),
        journal_pnl=Decimal("-74713"),
    )
    assert got == Decimal("99095")


def test_telescope_residual_acc2():
    assert telescope_residual(
        body_closed=Decimal("-70754"),
        varmargin_net=Decimal("-86799"),
        open_settled=Decimal("-7920"),
    ) == Decimal("8125")


def test_acc2_anchors_with_healthy_futures():
    d = decide_anchor(**ACC2)
    assert d.should_anchor is True
    assert d.source == "inferred_anchor"
    assert d.value == Decimal("99095.00")


def test_complete_history_never_anchors():
    d = decide_anchor(**{**ACC2, "incomplete_history": False})
    assert d.should_anchor is False
    assert d.source == "complete"
    assert d.value == Decimal("0")


def test_g1_nonpositive_candidate_does_not_anchor():
    # journal >= cash → candidate <= 0 → nothing to restore (benign, not blocked).
    # source='inferred_skipped' (НЕ 'complete'): история неполная, заморозка держится.
    d = decide_anchor(
        **{**ACC2, "portfolio_value": Decimal("10000"), "journal_pnl": Decimal("5000")}
    )
    assert d.should_anchor is False
    assert d.source == "inferred_skipped"


def test_g2_telescope_failure_blocks_anchor():
    # pv x1000 bug: body inflated → residual >> tol → blocked, real bug stays visible.
    d = decide_anchor(**{**ACC2, "body_closed": Decimal("-70754000")})
    assert d.should_anchor is False
    assert d.source == "inferred_blocked"


def test_g3_implausible_candidate_blocks_anchor():
    # No futures (varmargin~0 skips G2), tiny buy peak → bound 50*100=5000 < 99095 → blocked.
    d = decide_anchor(
        **{
            **ACC2,
            "varmargin_net": Decimal("0"),
            "body_closed": Decimal("0"),
            "open_settled": Decimal("0"),
            "gross_buy_peak": Decimal("100"),
        }
    )
    assert d.should_anchor is False
    assert d.source == "inferred_blocked"


def test_pure_stocks_account_anchors_via_g3():
    # No futures → G2 skipped; plausible buy peak → G3 passes → anchored.
    d = decide_anchor(
        incomplete_history=True,
        portfolio_value=Decimal("90000"),
        net_deposits=Decimal("10000"),
        journal_pnl=Decimal("-20000"),
        body_closed=Decimal("0"),
        varmargin_net=Decimal("0"),
        open_settled=Decimal("0"),
        gross_buy_peak=Decimal("40000"),
    )
    assert d.should_anchor is True
    assert d.source == "inferred_anchor"
    assert d.value == Decimal("100000.00")


def test_stock_only_candidate_over_sum_of_buys_is_blocked():
    """S2-11: на stock-only счёте (G2 skip) якорь-кандидат больше суммарного
    gross_buy теперь блокируется (deposit-независимый гейт вместо только 50×peak).
    Пропущенные sell-операции раздувают candidate → раньше молча якорилось."""
    d = decide_anchor(
        incomplete_history=True,
        portfolio_value=Decimal("500000"),
        net_deposits=Decimal("10000"),
        journal_pnl=Decimal("-100000"),  # заниженный журнал → candidate=590000
        body_closed=Decimal("0"),
        varmargin_net=Decimal("0"),
        open_settled=Decimal("0"),
        gross_buy_peak=Decimal("40000"),
        gross_buy_sum=Decimal("60000"),  # candidate 590000 >> 5*60000=300000
    )
    assert d.should_anchor is False
    assert d.source == "inferred_blocked"


def test_stock_only_plausible_candidate_still_anchors():
    """Разумный candidate ≤ 5×Σgross_buy на stock-only — якорится (не regressed)."""
    d = decide_anchor(
        incomplete_history=True,
        portfolio_value=Decimal("90000"),
        net_deposits=Decimal("10000"),
        journal_pnl=Decimal("-20000"),
        body_closed=Decimal("0"),
        varmargin_net=Decimal("0"),
        open_settled=Decimal("0"),
        gross_buy_peak=Decimal("40000"),
        gross_buy_sum=Decimal("40000"),  # candidate 100000 ≤ 5*40000=200000
    )
    assert d.should_anchor is True
    assert d.source == "inferred_anchor"


def test_zero_buy_peak_blocks_when_no_futures():
    d = decide_anchor(
        **{
            **ACC2,
            "varmargin_net": Decimal("0"),
            "body_closed": Decimal("0"),
            "open_settled": Decimal("0"),
            "gross_buy_peak": Decimal("0"),
        }
    )
    assert d.should_anchor is False
    assert d.source == "inferred_blocked"


def test_anchor_max_factor_constant_is_50():
    assert ANCHOR_MAX_FACTOR == Decimal("50")


def test_g1_boundary_exactly_anchor_min_does_not_anchor():
    # candidate == ANCHOR_MIN (1) → <= boundary → no anchor, source 'inferred_skipped'.
    d = decide_anchor(
        **{**ACC2, "portfolio_value": Decimal("8557"), "journal_pnl": Decimal("0")}
    )
    # candidate = 8557 - 8556 - 0 = 1 == ANCHOR_MIN
    assert d.should_anchor is False
    assert d.source == "inferred_skipped"
