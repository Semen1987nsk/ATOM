"""
PnL для ETF — те же payment-based формулы что для акций.

Зачем отдельный модуль если код тот же? Чтобы PR 8+ могли добавлять
type-specific корректировки (например, для активно-управляемых ETF в
будущем). Сейчас — простая reexport-обёртка.
"""

from __future__ import annotations

from domain.pnl.shares import SharesPnLCalculator as _Shares


class EtfsPnLCalculator(_Shares):
    """ETF торгуется как акция — наследуемся для семантической ясности."""

    pass
