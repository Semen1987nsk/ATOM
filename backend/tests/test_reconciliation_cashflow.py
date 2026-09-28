"""S3-27: 'output' классифицируется как вывод; расширенные типы депозитов."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from domain.pnl.cash_flow_classification import (  # noqa: E402
    CashFlowCategory,
    operation_types_in,
)


def test_net_deposit_set_includes_output_and_swift():
    types = operation_types_in(CashFlowCategory.NET_DEPOSIT)
    assert "output" in types          # канонический вывод (был пропущен)
    assert "input_swift" in types     # был пропущен
    assert "inp_multi" in types       # был пропущен
    assert "input" in types


def test_hardcoded_sets_missed_output():
    # Характеризует корень: старый hardcoded-набор НЕ содержал 'output'.
    old_withdrawals = {"out", "pay_out", "withdrawal"}
    assert "output" not in old_withdrawals
