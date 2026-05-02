"""
Tests for analytics module (Optimal f, SQN, Z-Score, etc.)
"""
import pytest
import sys
import os
from datetime import datetime
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import analytics


class TestOptimalF:
    """Tests for Optimal f calculation (Ralph Vince)."""
    
    def test_optimal_f_insufficient_data(self):
        """Should return 0 with insufficient data."""
        result = analytics.calculate_optimal_f([], [])
        assert result["optimal_f"] == 0
        
        result = analytics.calculate_optimal_f([100], [50])
        assert result["optimal_f"] == 0
    
    def test_optimal_f_no_losses(self):
        """Should handle all-winning scenario."""
        pnl = [100, 200, 150, 50]
        risk = [50, 100, 75, 25]
        result = analytics.calculate_optimal_f(pnl, risk)
        # With no losses, algorithm should still work
        assert result["optimal_f"] >= 0
    
    def test_optimal_f_mixed_results(self):
        """Should calculate optimal f for mixed results."""
        pnl = [100, -50, 80, -30, 120, -40]
        risk = [50, 50, 40, 30, 60, 40]
        result = analytics.calculate_optimal_f(pnl, risk)
        assert 0 < result["optimal_f"] <= 1
        assert "geometric_mean" in result


class TestSQN:
    """Tests for SQN (System Quality Number) calculation."""
    
    def test_sqn_insufficient_data(self):
        """Should return 0 with insufficient data."""
        result = analytics.calculate_sqn([], [])
        assert result["sqn"] == 0
    
    def test_sqn_calculation(self):
        """Should correctly calculate SQN."""
        # Good system: many small wins, few small losses
        pnl = [10, 15, -5, 20, 12, -3, 18, 14, -6, 22]
        risk = [10] * 10
        result = analytics.calculate_sqn(pnl, risk)
        assert result["sqn"] > 0
        assert "rating" in result
    
    def test_sqn_rating_scale(self):
        """Should assign correct ratings based on SQN value."""
        # Poor system
        pnl = [-10, 5, -12, 3, -8, 2]
        risk = [10] * 6
        result = analytics.calculate_sqn(pnl, risk)
        assert "Poor" in result["rating"] or result["sqn"] < 2.0


class TestZScore:
    """Tests for Z-Score (serial correlation) calculation."""
    
    def test_zscore_insufficient_data(self):
        """Should indicate insufficient data for small samples."""
        result = analytics.calculate_z_score([100, -50, 100])
        assert result["confidence"] == "Low" or result["z_score"] == 0
    
    def test_zscore_random_distribution(self):
        """Random sequence should have Z-score near 0."""
        import random
        random.seed(42)
        pnl = [random.choice([100, -50]) for _ in range(100)]
        result = analytics.calculate_z_score(pnl)
        # Random should be between -1.96 and 1.96
        assert -3 < result["z_score"] < 3


class TestAdvancedStats:
    """Tests for Profit Factor, R-Expectancy, Recovery Factor."""
    
    def test_profit_factor(self):
        """Should correctly calculate profit factor."""
        pnl = [100, 50, -30, 80, -20]  # Gross Profit = 230, Gross Loss = 50
        risk = [50] * 5
        result = analytics.calculate_advanced_stats(pnl, risk)
        assert result["profit_factor"] == 4.6  # 230 / 50
    
    def test_profit_factor_no_losses(self):
        """Should handle no-loss scenario."""
        pnl = [100, 50, 80]
        risk = [50] * 3
        result = analytics.calculate_advanced_stats(pnl, risk)
        assert result["profit_factor"] == 99.99
    
    def test_r_expectancy(self):
        """Should correctly calculate R-expectancy."""
        pnl = [100, -50, 100, -50]  # Avg = 25
        risk = [50, 50, 50, 50]  # R = [2, -1, 2, -1], Avg R = 0.5
        result = analytics.calculate_advanced_stats(pnl, risk)
        assert result["r_expectancy"] == 0.5
    
    def test_recovery_factor(self):
        """Should correctly calculate recovery factor."""
        pnl = [100, -50, -30, 80, 100]  # Net = 200, Max DD = 80
        risk = [50] * 5
        result = analytics.calculate_advanced_stats(pnl, risk)
        assert result["recovery_factor"] == 2.5  # 200 / 80


class TestMAEMFEAnalysis:
    """Tests for MAE/MFE analysis."""
    
    def test_mae_mfe_empty(self):
        """Should handle empty trades list."""
        result = analytics.analyze_mae_mfe([])
        assert "recommendations" in result

    def test_mae_mfe_uses_net_pnl_for_winner_classification(self):
        """Winner/loser buckets should follow net_pnl when commissions turn a gross win into a net loss."""
        trades = [
            SimpleNamespace(
                entry_at=datetime(2025, 1, 6, 10, 0),
                exit_at=datetime(2025, 1, 6, 12, 0),
                entry_price=100,
                exit_price=101,
                mae_price=97,
                mfe_price=105,
                quantity=10,
                pnl=10,
                net_pnl=-5,
                direction=SimpleNamespace(value='long'),
                operations=[],
            ),
            SimpleNamespace(
                entry_at=datetime(2025, 1, 7, 10, 0),
                exit_at=datetime(2025, 1, 7, 12, 0),
                entry_price=100,
                exit_price=110,
                mae_price=98,
                mfe_price=112,
                quantity=10,
                pnl=100,
                net_pnl=95,
                direction=SimpleNamespace(value='long'),
                operations=[],
            ),
        ]
        result = analytics.analyze_mae_mfe(trades)
        assert result["winners_vs_losers"]["winners"]["count"] == 1
        assert result["winners_vs_losers"]["losers"]["count"] == 1


class TestTimePatterns:
    """Tests for time-pattern aggregation."""

    def test_time_patterns_exact_aggregates(self):
        """Should aggregate day, hour and month stats from net PnL values."""
        trades = [
            SimpleNamespace(entry_at=datetime(2025, 1, 6, 10, 0), pnl=100, net_pnl=95),
            SimpleNamespace(entry_at=datetime(2025, 1, 6, 11, 0), pnl=-50, net_pnl=-55),
            SimpleNamespace(entry_at=datetime(2025, 2, 4, 10, 0), pnl=70, net_pnl=70),
        ]
        result = analytics.analyze_time_patterns(trades)
        assert result["day_stats"] == [
            {"day": "Пн", "total_pnl": 40.0, "trades": 2, "win_rate": 50.0},
            {"day": "Вт", "total_pnl": 70.0, "trades": 1, "win_rate": 100.0},
        ]
        assert result["hour_stats"] == [
            {"hour": "10:00", "total_pnl": 165.0, "trades": 2, "win_rate": 100.0},
            {"hour": "11:00", "total_pnl": -55.0, "trades": 1, "win_rate": 0.0},
        ]
        assert result["month_stats"] == [
            {"month": "Янв", "total_pnl": 40.0, "trades": 2, "win_rate": 50.0},
            {"month": "Фев", "total_pnl": 70.0, "trades": 1, "win_rate": 100.0},
        ]
        assert result["best_day"]["day"] == "Вт"
        assert result["worst_day"]["day"] == "Пн"


class TestSharpeSortino:
    """Tests for Sharpe and Sortino ratios."""
    
    def test_sharpe_insufficient_data(self):
        """Should return 0 with insufficient data."""
        result = analytics.calculate_sharpe_sortino([])
        assert result["sharpe_ratio"] == 0
    
    def test_sharpe_positive(self):
        """Should calculate positive Sharpe for profitable trades."""
        pnl = [100, 50, 80, -20, 120, 90]
        result = analytics.calculate_sharpe_sortino(pnl)
        assert result["sharpe_ratio"] > 0
        # Sortino should also be calculable
        assert "sortino_ratio" in result
    
    def test_sortino_calculation(self):
        """Sortino should handle downside deviation correctly."""
        pnl = [100, 120, 80, -10, -15, 90, 110]  # Multiple losses
        result = analytics.calculate_sharpe_sortino(pnl)
        assert result["sortino_ratio"] > 0
        assert result["sharpe_ratio"] > 0

    def test_sortino_uses_standard_downside_deviation(self):
        """Sortino should use downside deviation over all periods, not std of only losing trades."""
        pnl = [100, -50, 80, -30]
        result = analytics.calculate_sharpe_sortino(pnl)
        assert result["sortino_ratio"] == 0.86


class TestDrawdownStats:
    """Tests for drawdown calculations."""
    
    def test_drawdown_empty(self):
        """Should return 0 for empty data."""
        result = analytics.calculate_drawdown_stats([])
        assert result["max_drawdown_pct"] == 0
    
    def test_max_drawdown_calculation(self):
        """Should correctly calculate max drawdown."""
        pnl = [100, 50, -80, -50, 100, 50]  # Peak at 150, then drops to 20
        result = analytics.calculate_drawdown_stats(pnl, initial_balance=0)
        # Peak = 150, Trough = 20, DD = 130
        assert result["max_drawdown_abs"] == 130

    def test_current_drawdown_uses_latest_balance_vs_peak(self):
        """Should calculate current drawdown from the latest balance relative to the historical peak."""
        pnl = [100, -40, 20, -10]  # Peak balance = 1100, final balance = 1070
        result = analytics.calculate_drawdown_stats(pnl, initial_balance=1000)
        assert result["max_drawdown_abs"] == 40
        assert result["current_drawdown_pct"] == 2.73


class TestCalmarRatio:
    """Tests for Calmar Ratio calculation."""

    def test_calmar_ratio_exact_values(self):
        """Should calculate exact CAGR, drawdown and Calmar ratio on a controlled dataset."""
        pnl = [100, -50, -30, 80, 100]
        result = analytics.calculate_calmar_ratio(pnl, initial_balance=1000, period_years=1.0)
        assert result["cagr_pct"] == 20.0
        assert result["max_drawdown_pct"] == 7.27
        assert result["calmar_ratio"] == 2.75
        assert result["rating"] == "Отлично"

    def test_calmar_ratio_requires_positive_initial_balance(self):
        """Should not divide by zero when starting balance is missing."""
        pnl = [100, -50, -30, 80, 100]
        result = analytics.calculate_calmar_ratio(pnl, initial_balance=0, period_years=1.0)
        assert result["calmar_ratio"] == 0
        assert result["rating"] == "Недостаточно данных"


class TestWinLossStats:
    """Tests for win/loss statistics."""
    
    def test_avg_win_loss(self):
        """Should correctly calculate averages."""
        pnl = [100, 50, -30, -20]
        result = analytics.calculate_win_loss_stats(pnl)
        assert result["avg_win"] == 75  # (100+50)/2
        assert result["avg_loss"] == 25  # (30+20)/2
        assert result["payoff_ratio"] == 3.0  # 75/25
    
    def test_largest_win_loss(self):
        """Should find largest win and loss."""
        pnl = [100, 50, -30, -80, 200]
        result = analytics.calculate_win_loss_stats(pnl)
        assert result["largest_win"] == 200
        assert result["largest_loss"] == -80


class TestStreaks:
    """Tests for win/loss streak calculations."""
    
    def test_streaks_empty(self):
        """Should return 0 for empty data."""
        result = analytics.calculate_streaks([])
        assert result["max_win_streak"] == 0
    
    def test_max_streaks(self):
        """Should correctly count max streaks."""
        pnl = [10, 20, 30, -5, -10, 15, 25, 35, 45]  # 3 wins, 2 losses, 4 wins
        result = analytics.calculate_streaks(pnl)
        assert result["max_win_streak"] == 4
        assert result["max_loss_streak"] == 2
        assert result["current_streak"] == 4
        assert result["current_streak_type"] == "WIN"

    def test_current_loss_streak_ignores_breakeven_trades(self):
        """Breakeven trades should not reset the current streak; the latest non-zero streak should be returned."""
        pnl = [5, -1, -2, 0]
        result = analytics.calculate_streaks(pnl)
        assert result["max_win_streak"] == 1
        assert result["max_loss_streak"] == 2
        assert result["current_streak"] == 2
        assert result["current_streak_type"] == "LOSS"


class TestKellyCriterion:
    """Tests for Kelly Criterion calculation."""
    
    def test_kelly_insufficient_data(self):
        """Should return 0 with insufficient data."""
        result = analytics.calculate_kelly_criterion([100, 50])
        assert result["kelly_pct"] == 0
    
    def test_kelly_positive(self):
        """Should calculate positive Kelly for edge."""
        pnl = [100, 50, -30, 80, -20, 120, -40, 90]  # Positive expectancy
        result = analytics.calculate_kelly_criterion(pnl)
        assert result["kelly_pct"] > 0
        assert result["half_kelly"] == result["kelly_pct"] / 2


class TestMonteCarlo:
    """Tests for Monte Carlo simulation."""
    
    def test_monte_carlo_insufficient_data(self):
        """Should return message with insufficient data."""
        result = analytics.monte_carlo_simulation([100, 50, -30])
        assert "message" in result
    
    def test_monte_carlo_runs(self):
        """Should run simulation and return stats."""
        pnl = [100, 50, -30, 80, -20, 120, -40, 90, 60, -10]
        result = analytics.monte_carlo_simulation(pnl, num_simulations=100)
        assert result["simulations_run"] == 100
        assert "median_return" in result
        assert "worst_case_5pct" in result
        assert "best_case_95pct" in result

    def test_monte_carlo_seeded_contract(self):
        """Seeded Monte Carlo run should remain stable for the current vectorized implementation."""
        pnl = [100, 50, -30, 80, -20, 120, -40, 90, 60, -10]
        analytics.np.random.seed(42)
        result = analytics.monte_carlo_simulation(pnl, num_simulations=100, num_trades=10)
        assert result["median_return"] == 400.0
        assert result["worst_case_5pct"] == 59.5
        assert result["best_case_95pct"] == 691.5
        assert result["avg_max_drawdown"] == 60.3
        assert result["ruin_probability"] == 0.0


class TestRiskOfRuin:
    """Tests for Risk of Ruin calculation."""
    
    def test_ror_positive_edge(self):
        """Should calculate low RoR for positive edge system."""
        # Win rate 60%, payoff 1.5 = good edge
        result = analytics.calculate_risk_of_ruin(0.60, 1.5, risk_per_trade=0.02)
        assert result["ror_50pct"] < 50  # Should be low
    
    def test_ror_negative_edge(self):
        """Should return 100% for negative edge."""
        # Win rate 30%, payoff 1.0 = negative edge
        result = analytics.calculate_risk_of_ruin(0.30, 1.0, risk_per_trade=0.02)
        assert result["ror_50pct"] == 100.0


class TestTailRatio:
    """Tests for Tail Ratio calculation."""
    
    def test_tail_ratio_empty(self):
        """Should return 0 for insufficient data."""
        result = analytics.calculate_tail_ratio([100, 50, -30])
        assert result["tail_ratio"] == 0
    
    def test_tail_ratio_calculation(self):
        """Should calculate tail ratio correctly."""
        pnl = [500, 300, 200, 100, 50, -20, -50, -100, -150, -400]
        result = analytics.calculate_tail_ratio(pnl)
        assert result["tail_ratio"] > 0
        assert "avg_top_10pct_win" in result
        assert "avg_top_10pct_loss" in result

    def test_tail_ratio_exact_top_decile_values(self):
        """Tail ratio should use the average of the best and worst deciles."""
        pnl = [100, 80, 60, 40, 20, 10, -5, -10, -20, -50]
        result = analytics.calculate_tail_ratio(pnl)
        assert result["avg_top_10pct_win"] == 100
        assert result["avg_top_10pct_loss"] == 50
        assert result["tail_ratio"] == 2.0


class TestRDistribution:
    """Tests for R-distribution analysis."""
    
    def test_r_distribution_empty(self):
        """Should return 0 for empty data."""
        result = analytics.calculate_r_distribution([], [])
        assert result["pct_positive_r"] == 0
    
    def test_r_distribution_calculation(self):
        """Should calculate R percentages."""
        pnl = [100, 200, 50, -30, -50, 150]
        risk = [50, 100, 50, 50, 50, 50]  # R = [2, 2, 1, -0.6, -1, 3]
        result = analytics.calculate_r_distribution(pnl, risk)
        assert result["pct_positive_r"] > 0
        assert result["pct_above_1r"] > 0
        assert result["pct_above_2r"] >= 0

    def test_r_distribution_exact_percentages(self):
        """Should calculate exact R-distribution percentages on a controlled sample."""
        pnl = [100, -50, 40, 0]
        risk = [50, 50, 20, 10]
        result = analytics.calculate_r_distribution(pnl, risk)
        assert result["pct_positive_r"] == 50.0
        assert result["pct_above_1r"] == 50.0
        assert result["pct_above_2r"] == 50.0


class TestTradeDuration:
    """Tests for Trade Duration analysis."""
    
    def test_trade_duration_empty(self):
        """Should return 0 for empty trades."""
        result = analytics.calculate_trade_duration([])
        assert result["avg_duration_hours"] == 0

    def test_trade_duration_exact_values(self):
        """Should calculate exact average and median durations from closed trades."""
        trades = [
            SimpleNamespace(entry_at=datetime(2025, 1, 1, 10, 0), exit_at=datetime(2025, 1, 1, 12, 0), pnl=100, net_pnl=95),
            SimpleNamespace(entry_at=datetime(2025, 1, 2, 10, 0), exit_at=datetime(2025, 1, 2, 13, 30), pnl=-50, net_pnl=-55),
            SimpleNamespace(entry_at=datetime(2025, 1, 3, 10, 0), exit_at=datetime(2025, 1, 3, 11, 0), pnl=20, net_pnl=20),
        ]
        result = analytics.calculate_trade_duration(trades)
        assert result["avg_duration_hours"] == 2.2
        assert result["avg_win_duration_hours"] == 1.5
        assert result["avg_loss_duration_hours"] == 3.5
        assert result["median_duration_hours"] == 2.0
        assert result["total_closed_trades"] == 3
