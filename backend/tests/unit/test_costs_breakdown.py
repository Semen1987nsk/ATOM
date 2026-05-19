"""Unit tests для costs breakdown — disjoint и coverage invariants."""
from __future__ import annotations

from domain.pnl.cash_flow_classification import (
    CashFlowCategory,
    operation_types_in,
)
from domain.pnl.fee_attribution import (
    MARGIN_LIKE_FEE_TYPES,
    SERVICE_LIKE_FEE_TYPES,
)


def test_margin_and_service_fee_sets_are_disjoint():
    """MARGIN и SERVICE наборы не пересекаются — каждый op_type в ровно одно ведро."""
    overlap = MARGIN_LIKE_FEE_TYPES & SERVICE_LIKE_FEE_TYPES
    assert not overlap, (
        f"OperationType присутствует в обоих множествах: {overlap}. "
        f"Это сломает costs breakdown — будет double-count в стороне overlap."
    )


def test_all_attributable_fees_covered_by_margin_or_service():
    """Все op_types в категории ATTRIBUTABLE_FEE должны попадать в margin OR service.

    Если Тинькофф добавит новый OperationType (например, premium_fee) и
    положит его в ATTRIBUTABLE_FEE category, но забудет добавить либо в
    MARGIN_LIKE_FEE_TYPES либо в SERVICE_LIKE_FEE_TYPES — этот тест упадёт
    на CI, и costs breakdown в дашборде потеряет этот тип.
    """
    attributable = operation_types_in(CashFlowCategory.ATTRIBUTABLE_FEE)
    covered = MARGIN_LIKE_FEE_TYPES | SERVICE_LIKE_FEE_TYPES
    missing = attributable - covered
    assert not missing, (
        f"OperationType в ATTRIBUTABLE_FEE без бакета: {missing}. "
        f"Добавь либо в MARGIN_LIKE_FEE_TYPES либо в SERVICE_LIKE_FEE_TYPES "
        f"в backend/domain/pnl/fee_attribution.py."
    )
