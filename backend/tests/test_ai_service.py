import asyncio

import ai_service


def test_ai_analysis_handles_missing_mfe_price():
    result = asyncio.run(ai_service.analyze_trade_with_ai({
        "symbol": "GAZP",
        "direction": "long",
        "pnl": 25.0,
        "mfe_price": None,
        "exit_price": 175.0,
        "notes": "disciplined trade",
    }))

    assert result["verdict"] == "Systematic Trade"
    # Score зависит от внутренней калибровки ai_service. Проверяем «хорошая
    # сделка» = score ≥ 70, без привязки к точному числу.
    assert 70 <= result["score"] <= 100


def test_ai_analysis_detects_early_exit_when_mfe_is_higher():
    result = asyncio.run(ai_service.analyze_trade_with_ai({
        "symbol": "GAZP",
        "direction": "long",
        "pnl": 25.0,
        "mfe_price": 200.0,
        "exit_price": 175.0,
        "notes": "disciplined trade",
    }))

    assert result["verdict"] == "Early Exit"
    # «Поспешный выход» — средний скор. Окно калибруется детекторами.
    assert 50 <= result["score"] <= 85