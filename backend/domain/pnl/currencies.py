"""
PnL для валютных инструментов (CNYRUB, USDRUB и т.п.).

Формула та же что у акций: payment-based. Особенность только в `lot`
(обычно 1000 единиц = 1 лот), но это уже учтено в `quantity` операций
Tinkoff API — там приходит количество в единицах, не в лотах.
"""

from __future__ import annotations

from domain.pnl.shares import SharesPnLCalculator as _Shares


class CurrenciesPnLCalculator(_Shares):
    pass
