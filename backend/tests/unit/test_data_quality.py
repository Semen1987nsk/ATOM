from decimal import Decimal
from domain.pnl.data_quality import cash_reconstruction_residual, ReconStatus


def test_cash_reconstruction_matches_within_tolerance():
    res = cash_reconstruction_residual(
        portfolio_value=Decimal("36351.39"),
        net_deposits=Decimal("308035.79"),
        non_deposit_cash=Decimal("-271707.77"),
    )
    assert abs(res.residual) < Decimal("100")
    assert res.status == ReconStatus.OK


def test_cash_reconstruction_flags_missing_operations():
    res = cash_reconstruction_residual(
        portfolio_value=Decimal("36351.39"),
        net_deposits=Decimal("308035.79"),
        non_deposit_cash=Decimal("-221707.77"),
    )
    assert abs(res.residual) > Decimal("100")
    assert res.status == ReconStatus.RED


from domain.pnl.data_quality import ratio_sanity


def test_ratio_sanity_normal_drift_ok():
    res = ratio_sanity(journal_pnl=Decimal("-249072.79"), cash_pnl=Decimal("-271684.40"))
    assert res.status == ReconStatus.OK


def test_ratio_sanity_catches_1000x():
    res = ratio_sanity(journal_pnl=Decimal("-10261399"), cash_pnl=Decimal("-271684.40"))
    assert res.status == ReconStatus.RED


def test_ratio_sanity_na_when_cash_tiny():
    res = ratio_sanity(journal_pnl=Decimal("5"), cash_pnl=Decimal("0.5"))
    assert res.status == ReconStatus.OK


from domain.pnl.data_quality import trade_outliers


def test_trade_outliers_flags_oversized():
    flags = trade_outliers(
        trades=[("BBZ4", Decimal("-200000")), ("GAZP", Decimal("5000"))],
        net_deposits=Decimal("308035.79"),
        ratio_threshold=Decimal("0.5"),
    )
    assert flags == ["BBZ4"]


def test_trade_outliers_none_when_normal():
    flags = trade_outliers(
        trades=[("GAZP", Decimal("5000")), ("LKOH", Decimal("-3000"))],
        net_deposits=Decimal("308035.79"),
        ratio_threshold=Decimal("0.5"),
    )
    assert flags == []
