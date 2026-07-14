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


import pytest
from datetime import datetime, timezone
from sqlalchemy import create_engine, func
from sqlalchemy.orm import sessionmaker

import models
from models import Base


@pytest.fixture
def db_session():
    """In-memory SQLite session для unit-тестов sumсложения."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    s = Session()
    yield s
    s.close()


def _add_op(session, account_id: int, op_type: str, units: int):
    """Helper: добавить одну OperationORM с payment_units (без nano-точности)."""
    op = models.OperationORM(
        operation_id=f"op-{op_type}-{units}",
        account_id=account_id,
        operation_type=op_type,
        payment_units=units,
        payment_nano=0,
        commission_units=0,
        commission_nano=0,
        price_units=0,
        price_nano=0,
        quantity=0,
        state="executed",
        executed_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
        payment_currency="rub",
        broker_account_id="seed-broker",
    )
    session.add(op)


def _sum(session, account_id: int, op_types):
    """Helper: Σ payment по списку op_types через SQL."""
    if not op_types:
        return 0.0
    row = session.query(
        func.coalesce(func.sum(models.OperationORM.payment_units), 0),
        func.coalesce(func.sum(models.OperationORM.payment_nano), 0),
    ).filter(
        models.OperationORM.account_id == account_id,
        models.OperationORM.operation_type.in_(tuple(op_types)),
        models.OperationORM.state == "executed",
    ).one()
    return float(row[0] or 0) + float(row[1] or 0) / 1e9


def test_breakdown_sums_match_total_costs_categories(db_session):
    """Σ(broker + margin + service + tax + income_tax) == raw_attr_fee + raw_broker + raw_taxes.

    Защищает что добавление новых op_types в категории не уйдёт мимо breakdown.
    Также подтверждает что margin+service ровно покрывают всю ATTRIBUTABLE_FEE.
    """
    aid = 99
    # broker
    _add_op(db_session, aid, "broker_fee", -100)
    # margin
    _add_op(db_session, aid, "margin_fee", -50)
    _add_op(db_session, aid, "overnight",  -10)
    _add_op(db_session, aid, "over_com",   -5)
    # service
    _add_op(db_session, aid, "service_fee",  -30)
    _add_op(db_session, aid, "track_mfee",   -20)
    _add_op(db_session, aid, "success_fee",  -15)
    # tax
    _add_op(db_session, aid, "tax",          -7)
    _add_op(db_session, aid, "dividend_tax", -3)
    db_session.commit()

    raw_broker  = _sum(db_session, aid, operation_types_in(CashFlowCategory.BROKER_COMMISSION))
    raw_margin  = _sum(db_session, aid, MARGIN_LIKE_FEE_TYPES)
    raw_service = _sum(db_session, aid, SERVICE_LIKE_FEE_TYPES)
    raw_tax     = _sum(db_session, aid, operation_types_in(CashFlowCategory.TAX))
    raw_inctax  = _sum(db_session, aid, operation_types_in(CashFlowCategory.INCOME_TAX))
    raw_attr    = _sum(db_session, aid, operation_types_in(CashFlowCategory.ATTRIBUTABLE_FEE))

    # Инвариант 1: margin + service == raw_attr (вся ATTRIBUTABLE_FEE покрыта)
    assert abs((raw_margin + raw_service) - raw_attr) < 0.01, (
        f"margin={raw_margin} + service={raw_service} != attr={raw_attr}"
    )

    # Инвариант 2: суммы выставлены правильно (seed corresponds expectations)
    assert raw_broker  == -100
    assert raw_margin  == -65   # 50 + 10 + 5
    assert raw_service == -65   # 30 + 20 + 15
    assert raw_tax     == -7
    assert raw_inctax  == -3
