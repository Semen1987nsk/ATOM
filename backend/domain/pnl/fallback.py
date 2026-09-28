"""
FallbackPnLCalculator — payment-based формула для инструментов, чей точный
расчёт ещё не реализован (Bond — PR 8, Future — PR 9, Option — PR 10).

Лучше иметь грубый PnL «BUY+SELL payments» чем None в журнале. Когда
PR 8-10 поднимут точные формулы, fallback заменится на полноценный
calculator в реестре `FIFOMatchingService`.
"""

from __future__ import annotations

from domain.pnl.shares import SharesPnLCalculator as _Shares


class FallbackPnLCalculator(_Shares):
    """Алиас на SharesPnL до появления точной формулы по типу."""

    pass
