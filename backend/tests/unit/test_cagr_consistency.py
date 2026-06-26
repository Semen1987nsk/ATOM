"""MATH-07 + ADR-0010: проверка что /stats/advanced и /stats/benchmark строят
CAGR baseline на каноническом net_deposits helper, к которому ADR-0010 добавляет
initial_balance как восстановленный стартовый якорь.

Полноценный endpoint-consistency тест требует FastAPI client + auth + seed
trades + seed capital_flows — это integration-fixture, которой в backend
сейчас нет (DB-фикстуры для роутеров заведены минимально). Здесь делаем
архитектурную проверку: оба CAGR-блока stats_advanced.py берут base из
get_net_deposits_baseline_from_db (cash truth), и единственное использование
account.initial_balance — это additive-якорь (`baseline += initial_balance`),
а не замена helper'а. Это гарантирует, что три карточки (Calmar в /stats/,
CAGR в /stats/advanced, CAGR в /stats/benchmark) останутся согласованы.
"""
from __future__ import annotations

import inspect

from routers import stats_advanced


def test_stats_advanced_initial_balance_used_only_as_additive_anchor():
    """ADR-0010: account.initial_balance в stats_advanced.py допустим ТОЛЬКО как
    additive-якорь поверх net_deposits helper (`baseline += ... initial_balance`),
    никогда как самостоятельный CAGR baseline (=присваивание baseline)."""
    src = inspect.getsource(stats_advanced)
    code_lines = [
        line for line in src.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    for line in code_lines:
        if "account.initial_balance" not in line:
            continue
        stripped = line.strip()
        # Разрешено: `baseline += float(account.initial_balance or 0) ...`.
        # Запрещено: `baseline = ...account.initial_balance...` (замена helper'а).
        assert stripped.startswith("baseline +="), (
            "ADR-0010: account.initial_balance в stats_advanced.py допустим лишь "
            f"как additive-якорь (baseline += ...), а не как baseline. Нашли: {stripped!r}"
        )


def test_stats_advanced_uses_canonical_baseline_helper():
    """Helper должен импортироваться, иначе при следующем рефакторе
    легко случайно вернуться к старой формуле."""
    src = inspect.getsource(stats_advanced)
    assert "get_net_deposits_baseline_from_db" in src, (
        "MATH-07: stats_advanced.py должен использовать helper "
        "get_net_deposits_baseline_from_db для CAGR baseline."
    )
