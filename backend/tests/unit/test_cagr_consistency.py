"""MATH-07: проверка что /stats/advanced и /stats/benchmark используют
канонический net_deposits baseline (не account.initial_balance).

Полноценный endpoint-consistency тест требует FastAPI client + auth + seed
trades + seed capital_flows — это integration-fixture, которой в backend
сейчас нет (DB-фикстуры для роутеров заведены минимально). Здесь делаем
архитектурную проверку: ни в одном из CAGR-блоков stats_advanced.py больше
не читается account.initial_balance, а используется helper из
_common_baseline. Это гарантирует, что три карточки (Calmar в /stats/,
CAGR в /stats/advanced, CAGR в /stats/benchmark) останутся согласованы.
"""
from __future__ import annotations

import inspect

from routers import stats_advanced


def test_stats_advanced_does_not_read_initial_balance_for_cagr():
    """MATH-07: account.initial_balance больше не должен использоваться как
    CAGR baseline ни в /stats/advanced, ни в /stats/benchmark."""
    src = inspect.getsource(stats_advanced)
    # Игнорируем строки-комментарии (там осталась объяснение «больше не
    # account.initial_balance»). Проверяем только исполняемый код.
    code_lines = [
        line for line in src.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    code_only = "\n".join(code_lines)
    assert "account.initial_balance" not in code_only, (
        "MATH-07: routers/stats_advanced.py больше не должен читать "
        "account.initial_balance для CAGR — используй "
        "get_net_deposits_baseline_from_db (cash truth)."
    )


def test_stats_advanced_uses_canonical_baseline_helper():
    """Helper должен импортироваться, иначе при следующем рефакторе
    легко случайно вернуться к старой формуле."""
    src = inspect.getsource(stats_advanced)
    assert "get_net_deposits_baseline_from_db" in src, (
        "MATH-07: stats_advanced.py должен использовать helper "
        "get_net_deposits_baseline_from_db для CAGR baseline."
    )
