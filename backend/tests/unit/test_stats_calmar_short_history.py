from routers import stats as stats_router


def test_calmar_gated_on_short_history():
    # Прямой юнит на хелпер-гейт (см. Step 3). trading_days < 90 → None/недостаточно.
    result = stats_router._calmar_with_history_gate(
        pnls_sorted=[1000.0] * 6,
        calmar_initial_balance=100000.0,
        period_years=0.1,
        trading_days=7,
    )
    assert result["calmar_ratio"] is None
    assert result["rating"] == "Недостаточно истории"


def test_calmar_computed_on_long_history():
    # Нужна реальная просадка: у all-positive серии max_drawdown=0 → Calmar None
    # независимо от истории. Данные с просадкой доказывают, что гейт (>90 дней)
    # пропускает расчёт, а не то, что Calmar в принципе считается.
    result = stats_router._calmar_with_history_gate(
        pnls_sorted=[1000.0, -5000.0, -3000.0, 2000.0, 1500.0, 4000.0],
        calmar_initial_balance=100000.0,
        period_years=1.0,
        trading_days=200,
    )
    assert result["calmar_ratio"] is not None
