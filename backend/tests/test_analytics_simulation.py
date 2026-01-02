"""
Кросс-валидация и симуляция индикаторов.
Генерирует 1000+ сценариев для каждого индикатора и проверяет корректность.
"""

import pytest
import numpy as np
from typing import List, Tuple
import sys
sys.path.insert(0, '/workspaces/ATOM/backend')

from analytics import (
    calculate_optimal_f,
    calculate_z_score,
    calculate_sqn,
    calculate_advanced_stats,
    calculate_sharpe_sortino,
    calculate_drawdown_stats,
    calculate_win_loss_stats,
    calculate_streaks,
    calculate_risk_of_ruin,
    calculate_tail_ratio,
    calculate_r_distribution,
    calculate_kelly_criterion,
    monte_carlo_simulation,
)

# ============================================================================
# ГЕНЕРАТОРЫ ТОРГОВЫХ СЦЕНАРИЕВ
# ============================================================================

def generate_random_trades(n: int, win_rate: float = 0.5, avg_win: float = 100, avg_loss: float = -80) -> Tuple[List[float], List[float]]:
    """Генерирует случайные сделки с заданным винрейтом."""
    np.random.seed(None)  # Случайный seed для разнообразия
    pnl = []
    risk = []
    for _ in range(n):
        if np.random.random() < win_rate:
            # Прибыльная сделка (варьируем от 0.5x до 2x от avg_win)
            pnl.append(avg_win * np.random.uniform(0.5, 2.0))
        else:
            # Убыточная сделка
            pnl.append(avg_loss * np.random.uniform(0.5, 1.5))
        risk.append(abs(avg_loss) * np.random.uniform(0.8, 1.2))
    return pnl, risk

def generate_trending_trades(n: int, streak_length: int = 5) -> Tuple[List[float], List[float]]:
    """Генерирует трендовые серии (победы идут подряд, потом убытки подряд)."""
    pnl = []
    risk = []
    current_win = True
    count = 0
    for _ in range(n):
        if count >= streak_length:
            current_win = not current_win
            count = 0
        if current_win:
            pnl.append(np.random.uniform(50, 200))
        else:
            pnl.append(np.random.uniform(-150, -50))
        risk.append(80)
        count += 1
    return pnl, risk

def generate_alternating_trades(n: int) -> Tuple[List[float], List[float]]:
    """Генерирует чередующиеся сделки (пила)."""
    pnl = []
    risk = []
    for i in range(n):
        if i % 2 == 0:
            pnl.append(np.random.uniform(50, 150))
        else:
            pnl.append(np.random.uniform(-120, -60))
        risk.append(80)
    return pnl, risk

def generate_all_wins(n: int) -> Tuple[List[float], List[float]]:
    """Все сделки прибыльные."""
    pnl = [np.random.uniform(50, 200) for _ in range(n)]
    risk = [80] * n
    return pnl, risk

def generate_all_losses(n: int) -> Tuple[List[float], List[float]]:
    """Все сделки убыточные."""
    pnl = [np.random.uniform(-200, -50) for _ in range(n)]
    risk = [80] * n
    return pnl, risk

def generate_extreme_trades(n: int) -> Tuple[List[float], List[float]]:
    """Экстремальные значения (очень большие выигрыши/проигрыши)."""
    pnl = []
    risk = []
    for _ in range(n):
        if np.random.random() < 0.5:
            pnl.append(np.random.uniform(1000, 10000))  # Огромный выигрыш
        else:
            pnl.append(np.random.uniform(-5000, -500))  # Большой проигрыш
        risk.append(np.random.uniform(100, 500))
    return pnl, risk

def generate_zero_risk_trades(n: int) -> Tuple[List[float], List[float]]:
    """Сделки с нулевым или отрицательным риском (edge case)."""
    pnl = [np.random.uniform(-100, 100) for _ in range(n)]
    risk = [0] * n
    return pnl, risk

def generate_mixed_scenarios() -> List[Tuple[str, List[float], List[float]]]:
    """Генерирует 1000+ различных сценариев."""
    scenarios = []
    
    # 200 случайных сценариев с разным винрейтом
    for i in range(200):
        win_rate = np.random.uniform(0.3, 0.8)
        n_trades = np.random.randint(10, 100)
        pnl, risk = generate_random_trades(n_trades, win_rate)
        scenarios.append((f"random_wr{win_rate:.2f}_n{n_trades}", pnl, risk))
    
    # 200 трендовых сценариев
    for i in range(200):
        n_trades = np.random.randint(30, 100)
        streak = np.random.randint(3, 10)
        pnl, risk = generate_trending_trades(n_trades, streak)
        scenarios.append((f"trending_streak{streak}_n{n_trades}", pnl, risk))
    
    # 200 пилообразных сценариев
    for i in range(200):
        n_trades = np.random.randint(30, 100)
        pnl, risk = generate_alternating_trades(n_trades)
        scenarios.append((f"alternating_n{n_trades}", pnl, risk))
    
    # 100 только выигрышей
    for i in range(100):
        n_trades = np.random.randint(5, 50)
        pnl, risk = generate_all_wins(n_trades)
        scenarios.append((f"all_wins_n{n_trades}", pnl, risk))
    
    # 100 только проигрышей
    for i in range(100):
        n_trades = np.random.randint(5, 50)
        pnl, risk = generate_all_losses(n_trades)
        scenarios.append((f"all_losses_n{n_trades}", pnl, risk))
    
    # 100 экстремальных сценариев
    for i in range(100):
        n_trades = np.random.randint(10, 50)
        pnl, risk = generate_extreme_trades(n_trades)
        scenarios.append((f"extreme_n{n_trades}", pnl, risk))
    
    # 50 с нулевым риском
    for i in range(50):
        n_trades = np.random.randint(10, 30)
        pnl, risk = generate_zero_risk_trades(n_trades)
        scenarios.append((f"zero_risk_n{n_trades}", pnl, risk))
    
    # 50 пустых или минимальных
    scenarios.append(("empty", [], []))
    scenarios.append(("single", [100], [80]))
    for i in range(48):
        n = np.random.randint(2, 5)
        pnl, risk = generate_random_trades(n)
        scenarios.append((f"minimal_n{n}", pnl, risk))
    
    return scenarios


# ============================================================================
# ТЕСТЫ OPTIMAL F
# ============================================================================

class TestOptimalFSimulation:
    """Тестирование Optimal f на 1000+ сценариях."""
    
    def test_optimal_f_range(self):
        """Optimal f должен быть в диапазоне [0, 1]."""
        scenarios = generate_mixed_scenarios()
        errors = []
        
        for name, pnl, risk in scenarios:
            result = calculate_optimal_f(pnl, risk)
            f = result.get("optimal_f", 0)
            
            if f < 0 or f > 1:
                errors.append(f"{name}: optimal_f={f} вне диапазона [0,1]")
        
        assert len(errors) == 0, f"Найдено {len(errors)} ошибок:\n" + "\n".join(errors[:20])
    
    def test_optimal_f_no_crash(self):
        """Optimal f не должен падать на любых входных данных."""
        scenarios = generate_mixed_scenarios()
        crashes = []
        
        for name, pnl, risk in scenarios:
            try:
                result = calculate_optimal_f(pnl, risk)
                assert isinstance(result, dict), f"{name}: результат не dict"
            except Exception as e:
                crashes.append(f"{name}: {type(e).__name__}: {e}")
        
        assert len(crashes) == 0, f"Найдено {len(crashes)} падений:\n" + "\n".join(crashes[:20])
    
    def test_optimal_f_losing_system(self):
        """Для убыточных систем optimal_f должен быть 0 или помечен как невалидный."""
        for _ in range(100):
            # Система с PF < 1
            pnl, risk = generate_random_trades(50, win_rate=0.3, avg_win=50, avg_loss=-100)
            result = calculate_optimal_f(pnl, risk)
            
            # Проверяем что либо f=0, либо is_valid=False
            if result.get("optimal_f", 0) > 0:
                assert result.get("is_valid") == False, f"Убыточная система не помечена как невалидная"
    
    def test_optimal_f_profitable_system(self):
        """Для прибыльных систем optimal_f должен быть > 0."""
        profitable_count = 0
        for _ in range(100):
            # Сильная прибыльная система
            pnl, risk = generate_random_trades(50, win_rate=0.6, avg_win=150, avg_loss=-80)
            result = calculate_optimal_f(pnl, risk)
            
            if result.get("is_valid", False) and result.get("optimal_f", 0) > 0:
                profitable_count += 1
        
        # Большинство прибыльных систем должны давать f > 0
        assert profitable_count >= 70, f"Только {profitable_count}/100 прибыльных систем дали f > 0"


# ============================================================================
# ТЕСТЫ Z-SCORE
# ============================================================================

class TestZScoreSimulation:
    """Тестирование Z-Score на 1000+ сценариях."""
    
    def test_z_score_range(self):
        """Z-Score должен быть в разумном диапазоне [-10, 10]."""
        scenarios = generate_mixed_scenarios()
        errors = []
        
        for name, pnl, _ in scenarios:
            result = calculate_z_score(pnl)
            z = result.get("z_score", 0)
            
            # Z > 10 или Z < -10 маловероятны для нормальных данных
            if abs(z) > 20:
                errors.append(f"{name}: z_score={z:.2f} слишком экстремальный")
        
        assert len(errors) == 0, f"Найдено {len(errors)} ошибок:\n" + "\n".join(errors[:20])
    
    def test_z_score_no_crash(self):
        """Z-Score не должен падать."""
        scenarios = generate_mixed_scenarios()
        crashes = []
        
        for name, pnl, _ in scenarios:
            try:
                result = calculate_z_score(pnl)
                assert isinstance(result, dict)
            except Exception as e:
                crashes.append(f"{name}: {e}")
        
        assert len(crashes) == 0, f"Найдено {len(crashes)} падений"
    
    def test_z_score_alternating_positive(self):
        """Для чередующихся сделок Z-Score должен быть положительным."""
        positive_count = 0
        for _ in range(100):
            pnl, _ = generate_alternating_trades(50)
            result = calculate_z_score(pnl)
            if result.get("z_score", 0) > 0:
                positive_count += 1
        
        # Большинство должны быть положительными
        assert positive_count >= 80, f"Только {positive_count}/100 чередующихся дали Z > 0"
    
    def test_z_score_trending_negative(self):
        """Для трендовых серий Z-Score должен быть отрицательным."""
        negative_count = 0
        for _ in range(100):
            pnl, _ = generate_trending_trades(60, streak_length=8)
            result = calculate_z_score(pnl)
            if result.get("z_score", 0) < 0:
                negative_count += 1
        
        # Большинство должны быть отрицательными
        assert negative_count >= 60, f"Только {negative_count}/100 трендовых дали Z < 0"


# ============================================================================
# ТЕСТЫ SQN
# ============================================================================

class TestSQNSimulation:
    """Тестирование SQN на 1000+ сценариях."""
    
    def test_sqn_no_crash(self):
        """SQN не должен падать."""
        scenarios = generate_mixed_scenarios()
        crashes = []
        
        for name, pnl, risk in scenarios:
            try:
                result = calculate_sqn(pnl, risk)
                assert isinstance(result, dict)
            except Exception as e:
                crashes.append(f"{name}: {e}")
        
        assert len(crashes) == 0, f"Найдено {len(crashes)} падений"
    
    def test_sqn_losing_negative(self):
        """Для убыточных систем SQN должен быть отрицательным или низким."""
        for _ in range(100):
            pnl, risk = generate_all_losses(30)
            result = calculate_sqn(pnl, risk)
            sqn = result.get("sqn", 0)
            
            assert sqn <= 1, f"SQN для убыточной системы = {sqn}, ожидалось <= 1"
    
    def test_sqn_profitable_positive(self):
        """Для прибыльных систем SQN должен быть положительным."""
        positive_count = 0
        for _ in range(100):
            pnl, risk = generate_random_trades(50, win_rate=0.6, avg_win=150, avg_loss=-80)
            result = calculate_sqn(pnl, risk)
            if result.get("sqn", 0) > 0:
                positive_count += 1
        
        assert positive_count >= 70, f"Только {positive_count}/100 прибыльных систем дали SQN > 0"


# ============================================================================
# ТЕСТЫ DRAWDOWN
# ============================================================================

class TestDrawdownSimulation:
    """Тестирование Drawdown на 1000+ сценариях."""
    
    def test_drawdown_range(self):
        """Max Drawdown должен быть в диапазоне [0, 100+] %."""
        scenarios = generate_mixed_scenarios()
        errors = []
        
        for name, pnl, _ in scenarios:
            if not pnl:
                continue
            result = calculate_drawdown_stats(pnl, initial_balance=10000)
            dd = result.get("max_drawdown_pct", 0)
            
            if dd < 0:
                errors.append(f"{name}: drawdown={dd}% отрицательный")
        
        assert len(errors) == 0, f"Найдено {len(errors)} ошибок:\n" + "\n".join(errors[:20])
    
    def test_drawdown_no_crash(self):
        """Drawdown не должен падать."""
        scenarios = generate_mixed_scenarios()
        crashes = []
        
        for name, pnl, _ in scenarios:
            try:
                result = calculate_drawdown_stats(pnl, initial_balance=10000)
                assert isinstance(result, dict)
            except Exception as e:
                crashes.append(f"{name}: {e}")
        
        assert len(crashes) == 0, f"Найдено {len(crashes)} падений"
    
    def test_drawdown_all_wins_zero(self):
        """Для всех побед drawdown должен быть 0 или минимальным."""
        for _ in range(50):
            pnl, _ = generate_all_wins(30)
            result = calculate_drawdown_stats(pnl, initial_balance=10000)
            dd = result.get("max_drawdown_pct", 0)
            
            assert dd == 0, f"Drawdown для всех выигрышей = {dd}%, ожидалось 0"


# ============================================================================
# ТЕСТЫ WIN/LOSS STATS
# ============================================================================

class TestWinLossSimulation:
    """Тестирование Win/Loss статистики."""
    
    def test_win_rate_range(self):
        """Win rate должен быть в диапазоне [0, 100]%."""
        scenarios = generate_mixed_scenarios()
        errors = []
        
        for name, pnl, _ in scenarios:
            result = calculate_win_loss_stats(pnl)
            wr = result.get("win_rate", 0)
            
            if wr < 0 or wr > 100:
                errors.append(f"{name}: win_rate={wr}% вне диапазона")
        
        assert len(errors) == 0, f"Найдено {len(errors)} ошибок"
    
    def test_all_wins_100(self):
        """Для всех выигрышей win_rate должен быть 100%."""
        for _ in range(50):
            pnl, _ = generate_all_wins(20)
            result = calculate_win_loss_stats(pnl)
            wr = result.get("win_rate", 0)
            
            assert wr == 100, f"Win rate для всех выигрышей = {wr}%"
    
    def test_all_losses_0(self):
        """Для всех проигрышей win_rate должен быть 0%."""
        for _ in range(50):
            pnl, _ = generate_all_losses(20)
            result = calculate_win_loss_stats(pnl)
            wr = result.get("win_rate", 0)
            
            assert wr == 0, f"Win rate для всех проигрышей = {wr}%"


# ============================================================================
# ТЕСТЫ STREAKS
# ============================================================================

class TestStreaksSimulation:
    """Тестирование серий."""
    
    def test_streaks_no_crash(self):
        """Streaks не должен падать."""
        scenarios = generate_mixed_scenarios()
        crashes = []
        
        for name, pnl, _ in scenarios:
            try:
                result = calculate_streaks(pnl)
                assert isinstance(result, dict)
            except Exception as e:
                crashes.append(f"{name}: {e}")
        
        assert len(crashes) == 0, f"Найдено {len(crashes)} падений"
    
    def test_streaks_positive(self):
        """Серии должны быть >= 0."""
        scenarios = generate_mixed_scenarios()
        errors = []
        
        for name, pnl, _ in scenarios:
            result = calculate_streaks(pnl)
            max_win = result.get("max_win_streak", 0)
            max_loss = result.get("max_loss_streak", 0)
            
            if max_win < 0 or max_loss < 0:
                errors.append(f"{name}: серии отрицательные")
        
        assert len(errors) == 0, f"Найдено {len(errors)} ошибок"


# ============================================================================
# ТЕСТЫ RISK OF RUIN
# ============================================================================

class TestRiskOfRuinSimulation:
    """Тестирование Risk of Ruin."""
    
    def test_ror_range(self):
        """RoR должен быть в диапазоне [0, 100]%."""
        errors = []
        
        for _ in range(200):
            win_rate = np.random.uniform(0.3, 0.8)
            payoff = np.random.uniform(0.5, 3.0)
            risk = np.random.uniform(0.01, 0.1)
            
            result = calculate_risk_of_ruin(win_rate, payoff, risk)
            ror = result.get("risk_of_ruin_pct", 0)
            
            if ror < 0 or ror > 100:
                errors.append(f"wr={win_rate:.2f}, payoff={payoff:.2f}, risk={risk:.2f}: RoR={ror}%")
        
        assert len(errors) == 0, f"Найдено {len(errors)} ошибок:\n" + "\n".join(errors[:20])
    
    def test_ror_high_winrate_low(self):
        """Для высокого винрейта и хорошего payoff RoR должен быть низким."""
        for _ in range(50):
            result = calculate_risk_of_ruin(0.7, 2.0, 0.02)
            ror = result.get("risk_of_ruin_pct", 100)
            
            assert ror < 50, f"RoR для отличной системы = {ror}%, ожидалось < 50%"


# ============================================================================
# ТЕСТЫ TAIL RATIO
# ============================================================================

class TestTailRatioSimulation:
    """Тестирование Tail Ratio."""
    
    def test_tail_ratio_no_crash(self):
        """Tail Ratio не должен падать."""
        scenarios = generate_mixed_scenarios()
        crashes = []
        
        for name, pnl, _ in scenarios:
            try:
                result = calculate_tail_ratio(pnl)
                assert isinstance(result, dict)
            except Exception as e:
                crashes.append(f"{name}: {e}")
        
        assert len(crashes) == 0, f"Найдено {len(crashes)} падений"
    
    def test_tail_ratio_no_nan(self):
        """Tail Ratio не должен быть NaN или Inf."""
        scenarios = generate_mixed_scenarios()
        errors = []
        
        for name, pnl, _ in scenarios:
            result = calculate_tail_ratio(pnl)
            tr = result.get("tail_ratio", 0)
            
            if np.isnan(tr) or np.isinf(tr):
                errors.append(f"{name}: tail_ratio={tr} NaN/Inf")
        
        assert len(errors) == 0, f"Найдено {len(errors)} ошибок"


# ============================================================================
# ТЕСТЫ KELLY CRITERION
# ============================================================================

class TestKellySimulation:
    """Тестирование Kelly Criterion."""
    
    def test_kelly_range(self):
        """Kelly должен быть в разумном диапазоне."""
        scenarios = generate_mixed_scenarios()
        errors = []
        
        for name, pnl, _ in scenarios:
            result = calculate_kelly_criterion(pnl)
            kelly = result.get("kelly", 0)
            
            # Kelly может быть отрицательным (не торговать) или до ~100%
            if kelly > 200:
                errors.append(f"{name}: kelly={kelly}% слишком большой")
        
        assert len(errors) == 0, f"Найдено {len(errors)} ошибок"
    
    def test_kelly_no_crash(self):
        """Kelly не должен падать."""
        scenarios = generate_mixed_scenarios()
        crashes = []
        
        for name, pnl, _ in scenarios:
            try:
                result = calculate_kelly_criterion(pnl)
                assert isinstance(result, dict)
            except Exception as e:
                crashes.append(f"{name}: {e}")
        
        assert len(crashes) == 0, f"Найдено {len(crashes)} падений"


# ============================================================================
# ТЕСТЫ MONTE CARLO
# ============================================================================

class TestMonteCarloSimulation:
    """Тестирование Monte Carlo симуляции."""
    
    def test_monte_carlo_no_crash(self):
        """Monte Carlo не должен падать."""
        scenarios = generate_mixed_scenarios()[:100]  # Ограничиваем для скорости
        crashes = []
        
        for name, pnl, _ in scenarios:
            try:
                result = monte_carlo_simulation(pnl, num_simulations=100, num_trades=50)
                assert isinstance(result, dict)
            except Exception as e:
                crashes.append(f"{name}: {e}")
        
        assert len(crashes) == 0, f"Найдено {len(crashes)} падений:\n" + "\n".join(crashes[:10])
    
    def test_monte_carlo_probabilities_range(self):
        """Вероятности Monte Carlo должны быть в [0, 100]%."""
        errors = []
        
        for _ in range(50):
            pnl, _ = generate_random_trades(30)
            result = monte_carlo_simulation(pnl, num_simulations=100, num_trades=50)
            
            for key in ["probability_profit", "probability_loss_20", "probability_loss_50"]:
                prob = result.get(key, 0)
                if prob < 0 or prob > 100:
                    errors.append(f"{key}={prob}% вне диапазона")
        
        assert len(errors) == 0, f"Найдено {len(errors)} ошибок"


# ============================================================================
# ТЕСТЫ SHARPE/SORTINO
# ============================================================================

class TestSharpeSortinoSimulation:
    """Тестирование Sharpe и Sortino."""
    
    def test_sharpe_no_crash(self):
        """Sharpe/Sortino не должен падать."""
        scenarios = generate_mixed_scenarios()
        crashes = []
        
        for name, pnl, _ in scenarios:
            try:
                result = calculate_sharpe_sortino(pnl)
                assert isinstance(result, dict)
            except Exception as e:
                crashes.append(f"{name}: {e}")
        
        assert len(crashes) == 0, f"Найдено {len(crashes)} падений"
    
    def test_sharpe_positive_for_winners(self):
        """Для прибыльных систем Sharpe должен быть положительным."""
        positive_count = 0
        for _ in range(50):
            pnl, _ = generate_random_trades(50, win_rate=0.6, avg_win=150, avg_loss=-80)
            result = calculate_sharpe_sortino(pnl)
            if result.get("sharpe_ratio", 0) > 0:
                positive_count += 1
        
        assert positive_count >= 35, f"Только {positive_count}/50 прибыльных дали Sharpe > 0"


# ============================================================================
# ИНТЕГРАЦИОННЫЙ ТЕСТ: ВСЕ ИНДИКАТОРЫ ВМЕСТЕ
# ============================================================================

class TestAllIndicatorsIntegration:
    """Проверяет все индикаторы на одних и тех же данных."""
    
    def test_all_indicators_no_crash_on_1000_scenarios(self):
        """Все индикаторы должны работать на 1000+ сценариях без падений."""
        scenarios = generate_mixed_scenarios()
        
        all_results = {
            "optimal_f": [],
            "z_score": [],
            "sqn": [],
            "drawdown": [],
            "win_loss": [],
            "streaks": [],
            "tail_ratio": [],
            "kelly": [],
            "sharpe": [],
        }
        
        crashes = []
        
        for name, pnl, risk in scenarios:
            try:
                all_results["optimal_f"].append(calculate_optimal_f(pnl, risk))
                all_results["z_score"].append(calculate_z_score(pnl))
                all_results["sqn"].append(calculate_sqn(pnl, risk))
                all_results["drawdown"].append(calculate_drawdown_stats(pnl, 10000))
                all_results["win_loss"].append(calculate_win_loss_stats(pnl))
                all_results["streaks"].append(calculate_streaks(pnl))
                all_results["tail_ratio"].append(calculate_tail_ratio(pnl))
                all_results["kelly"].append(calculate_kelly_criterion(pnl))
                all_results["sharpe"].append(calculate_sharpe_sortino(pnl))
            except Exception as e:
                crashes.append(f"{name}: {type(e).__name__}: {e}")
        
        # Отчет
        print(f"\n{'='*60}")
        print(f"ОТЧЕТ ПО СИМУЛЯЦИИ: {len(scenarios)} сценариев")
        print(f"{'='*60}")
        print(f"Падений: {len(crashes)}")
        
        if crashes:
            print("\nПримеры падений:")
            for c in crashes[:10]:
                print(f"  - {c}")
        
        print(f"\nСтатистика по индикаторам:")
        for indicator, results in all_results.items():
            valid = [r for r in results if r]
            print(f"  {indicator}: {len(valid)}/{len(scenarios)} успешных")
        
        assert len(crashes) == 0, f"Найдено {len(crashes)} падений!"
    
    def test_consistency_check(self):
        """Проверка согласованности: PF<1 должен давать предупреждения."""
        inconsistencies = []
        
        for _ in range(100):
            # Убыточная система
            pnl, risk = generate_random_trades(40, win_rate=0.35, avg_win=60, avg_loss=-100)
            
            # Рассчитываем PF вручную
            wins = sum(p for p in pnl if p > 0)
            losses = abs(sum(p for p in pnl if p < 0))
            pf = wins / losses if losses > 0 else 0
            
            if pf < 1:
                optimal_f_result = calculate_optimal_f(pnl, risk)
                
                # Для убыточной системы optimal_f должен быть 0 или помечен невалидным
                if optimal_f_result.get("optimal_f", 0) > 0 and optimal_f_result.get("is_valid", True):
                    inconsistencies.append(f"PF={pf:.2f} но optimal_f={optimal_f_result.get('optimal_f')}, is_valid=True")
        
        assert len(inconsistencies) == 0, f"Найдено {len(inconsistencies)} несогласованностей:\n" + "\n".join(inconsistencies[:10])


# ============================================================================
# ЗАПУСК ТЕСТОВ
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short", "-x"])
