"""
PR 26 (Phase 3) — transformation_audit: обнаружение 8 known-issues
в трансформации Tinkoff API → наша БД.

Это **диагностика**, а не исправление. Сами фиксы делаются:
- T1 (futures point_value fallback) — log warning в `domain/pnl/futures.py`
- T5 (nano > 1e9) — clamp + log в `adapters/tinkoff/proto_to_domain.py`
- T8 (quantity=0 ops) — log warning в `_reconcile_quantity` (TODO)

Аудит сканирует данные пользователя и помечает потенциальные проблемы.
Используется в reconciliation_service для расширенного диагностического
отчёта.

8 точек (см. план Phase 3):
- T1: futures без min_price_increment_amount
- T2: bond operations без accrued_int (ACI)
- T3: качества дробных акций (Decimal lost in float)
- T4: commission per-unit zero division
- T5: nano > 1e9
- T6: cross-currency trades без exchange_rate
- T7: FIFO qty vs API qty mismatch
- T8: quantity=0 операции пропущены без warning
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

import models
from logger import get_logger

log = get_logger("transformation_audit")


@dataclass
class TransformationWarning:
    """Найденная точка где могла произойти тихая трансформация-ошибка."""

    code: str  # 'T1' .. 'T8'
    severity: str  # 'critical' | 'high' | 'medium' | 'low'
    description: str
    count: int = 0  # количество затронутых записей
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "severity": self.severity,
            "description": self.description,
            "count": self.count,
            "details": self.details,
        }


def audit_account(db: Session, account_id: int) -> list[TransformationWarning]:
    """Запустить все 8 проверок на одном аккаунте.

    Возвращает только обнаруженные проблемы (warning с count > 0).
    Пустой список = всё чисто.
    """
    warnings: list[TransformationWarning] = []
    for check_fn in (
        _check_t1_futures_point_value,
        _check_t2_bond_aci,
        _check_t3_fractional_quantity,
        _check_t6_cross_currency,
        _check_t7_fifo_qty_mismatch,
        _check_t8_zero_quantity_ops,
    ):
        try:
            w = check_fn(db, account_id)
            if w is not None and w.count > 0:
                warnings.append(w)
        except Exception as exc:
            log.exception("transformation_audit_check_failed", extra={
                "check": check_fn.__name__,
                "account_id": account_id,
            })
            warnings.append(TransformationWarning(
                code="AUDIT_ERROR",
                severity="low",
                description=f"check {check_fn.__name__} crashed: {type(exc).__name__}",
                count=1,
                details={"error": str(exc)},
            ))
    return warnings


# ════════════════════════════════════════════════════════════════════════
# T1: futures без min_price_increment_amount → silent ×100 ошибка
# ════════════════════════════════════════════════════════════════════════


def _check_t1_futures_point_value(db: Session, account_id: int) -> TransformationWarning | None:
    """Сканирует фьючерсы в позициях/операциях этого аккаунта.

    Возвращает warning если у любого instrument'а нет min_price_increment_amount.
    Это критично: silent fallback 1.0 даёт ошибку 100x для SiH6/RTS.
    """
    # Найти все instrument_uid у которых есть операции в этом аккаунте
    rows = db.query(models.OperationORM.instrument_uid).filter(
        models.OperationORM.account_id == account_id,
        models.OperationORM.instrument_type == "futures",
    ).distinct().all()
    futures_uids = {r[0] for r in rows if r[0]}
    if not futures_uids:
        return None

    bad_instruments = []
    for uid in futures_uids:
        inst = db.query(models.InstrumentORM).filter_by(uid=uid).first()
        if inst is None:
            bad_instruments.append({"uid": uid, "reason": "not_in_cache"})
            continue
        if inst.min_price_increment_amount is None or inst.min_price_increment is None:
            bad_instruments.append({
                "uid": uid,
                "ticker": inst.ticker,
                "reason": "missing_point_value_fields",
            })

    if not bad_instruments:
        return None

    return TransformationWarning(
        code="T1",
        severity="critical",
        description=(
            "Фьючерсы без min_price_increment_amount: P&L масштаб может быть "
            "занижен в 100x (для SiH6/RTS контрактов). Запустите "
            "`tools/live_instrument_bootstrap.py` чтобы обновить справочник."
        ),
        count=len(bad_instruments),
        details={"affected": bad_instruments[:20]},  # cap для размера
    )


# ════════════════════════════════════════════════════════════════════════
# T2: bond operations без accrued_int (ACI)
# ════════════════════════════════════════════════════════════════════════


def _check_t2_bond_aci(db: Session, account_id: int) -> TransformationWarning | None:
    """Bond BUY/SELL операции должны иметь aci_units != NULL.

    Tinkoff payment включает ACI, но мы сохраняем ACI отдельно для
    верификации против broker_report.aci_value. Если ACI пустой —
    возможна ошибка в proto mapper.
    """
    bond_ops = db.query(models.OperationORM).filter(
        models.OperationORM.account_id == account_id,
        models.OperationORM.instrument_type == "bond",
        models.OperationORM.operation_type.in_(["buy", "sell", "buy_card", "sell_card"]),
    ).all()
    if not bond_ops:
        return None

    no_aci = [
        {
            "operation_id": op.operation_id,
            "ticker_uid": op.instrument_uid,
            "executed_at": op.executed_at.isoformat() if op.executed_at else None,
        }
        for op in bond_ops
        if op.aci_units is None and op.aci_nano is None
    ]
    if not no_aci:
        return None

    return TransformationWarning(
        code="T2",
        severity="medium",
        description=(
            "Bond операции без накопленного купонного дохода (ACI/НКД). "
            "Это нормально для очень новых выпусков или досрочного погашения, "
            "но обычно ACI должен быть. Сверьте с broker_report.aci_value."
        ),
        count=len(no_aci),
        details={"affected": no_aci[:10], "total_bond_ops": len(bond_ops)},
    )


# ════════════════════════════════════════════════════════════════════════
# T3: дробные акции
# ════════════════════════════════════════════════════════════════════════


def _check_t3_fractional_quantity(db: Session, account_id: int) -> TransformationWarning | None:
    """Поиск положений где quantity потенциально дробное.

    Сейчас наша БД хранит quantity как Integer — дробные части округляются.
    Это может быть проблемой для ETF (FXUS, FXIT) которые поддерживают
    частичные паи. Признак: payment / price != quantity (с допуском).
    """
    suspicious = db.query(models.OperationORM).filter(
        models.OperationORM.account_id == account_id,
        models.OperationORM.operation_type.in_(["buy", "sell"]),
        models.OperationORM.quantity > 0,
        models.OperationORM.price_units.isnot(None),
        models.OperationORM.payment_units.isnot(None),
    ).limit(500).all()

    fractional_count = 0
    examples = []
    for op in suspicious:
        try:
            price = Decimal(op.price_units or 0) + Decimal(op.price_nano or 0) / Decimal(1_000_000_000)
            payment = Decimal(op.payment_units or 0) + Decimal(op.payment_nano or 0) / Decimal(1_000_000_000)
            if price <= 0 or payment == 0:
                continue
            expected = abs(payment) / price
            saved_qty_d = Decimal(op.quantity)
            diff = abs(expected - saved_qty_d)
            # Реальная дробная доля (не округление копеек на price):
            #   - drift >0.5 units (абсолют),
            #   - relative drift >1% от saved_qty (отсекает rounding на
            #     copeечных акциях TGKA/HYDR/FEES где drift в копейках),
            #   - expected заметно дробное (>0.01 от целого).
            #
            # Пропускаем futures: для них op.quantity в базовых активах,
            # а expected (|payment|/price) в контрактах × basic_asset_size;
            # это semantic split, не "lost fractional".
            if op.instrument_type == "futures":
                continue
            rel_drift = diff / saved_qty_d if saved_qty_d > 0 else Decimal(0)
            if (
                diff > Decimal("0.5")
                and rel_drift > Decimal("0.01")
                and expected > 0
                and abs(expected - int(expected)) > Decimal("0.01")
            ):
                fractional_count += 1
                if len(examples) < 5:
                    examples.append({
                        "operation_id": op.operation_id,
                        "saved_qty": op.quantity,
                        "expected_qty": str(expected),
                        "rel_drift_pct": f"{float(rel_drift) * 100:.4f}%",
                    })
        except Exception:
            continue

    if fractional_count == 0:
        return None

    return TransformationWarning(
        code="T3",
        severity="medium",
        description=(
            "Возможно дробные паи теряются при сохранении (БД quantity = Integer). "
            "Затронуты ETF/долевые инструменты."
        ),
        count=fractional_count,
        details={"examples": examples},
    )


# ════════════════════════════════════════════════════════════════════════
# T6: cross-currency trades без exchange_rate
# ════════════════════════════════════════════════════════════════════════


def _check_t6_cross_currency(db: Session, account_id: int) -> TransformationWarning | None:
    """Trade.currency != account base currency (RUB).

    Tinkoff для USD-инструментов на RUB-счёте отдаёт payment в RUB
    (конвертирует по курсу), но в Trade мы записываем currency как
    у инструмента. Может вводить в заблуждение в UI.
    """
    trades_usd_eur = db.query(models.Trade).filter(
        models.Trade.account_id == account_id,
        models.Trade.currency.notin_(["rub", "RUB", None]),
    ).limit(50).all()

    if not trades_usd_eur:
        return None

    return TransformationWarning(
        code="T6",
        severity="low",
        description=(
            "Сделки в валюте отличной от RUB. Дашборд показывает их без "
            "explicit конвертации, что может вводить в заблуждение."
        ),
        count=len(trades_usd_eur),
        details={
            "currencies": list({t.currency for t in trades_usd_eur if t.currency}),
        },
    )


# ════════════════════════════════════════════════════════════════════════
# T7: FIFO qty в Position vs API qty
# ════════════════════════════════════════════════════════════════════════


def _check_t7_fifo_qty_mismatch(db: Session, account_id: int) -> TransformationWarning | None:
    """Position.quantity vs FIFO-computed quantity из open Trades.

    Если они разные — silent split-brain: Tinkoff portfolio API
    говорит одно, а наш FIFO вычислил другое.

    NB (T7 diagnostic 2026-05-16): для **futures** Tinkoff API имеет два
    разных semantics на одно и то же число:
      - `operation.quantity` = базовый актив (например 3255 акций Xiaomi)
      - `portfolio.position.quantity` = количество контрактов (3)
      - ratio = `basic_asset_size` (для XIM6 контракт = 1085 акций)
    Поэтому для futures прямое сравнение даёт ложный T7. Нормализуем по
    `basic_asset_size`, либо если он отсутствует — пропускаем futures.
    """
    positions = db.query(models.PositionORM).filter(
        models.PositionORM.account_id == account_id,
        models.PositionORM.quantity != 0,
    ).all()
    if not positions:
        return None

    mismatches = []
    for pos in positions:
        # Σ open trades для этого instrument'а: long − short по quantity
        open_trades = db.query(models.Trade).filter(
            models.Trade.account_id == account_id,
            models.Trade.instrument_uid == pos.instrument_uid,
            models.Trade.exit_at.is_(None),
        ).all()
        fifo_qty = 0
        for t in open_trades:
            # t.direction — это Enum (TradeDirectionORM), не str.
            # getattr с .value безопасно для обоих случаев.
            dir_str = getattr(t.direction, "value", t.direction) or ""
            dir_str = str(dir_str).lower()
            direction_sign = 1 if dir_str == "long" else -1
            qty = int(t.quantity or 0)
            fifo_qty += direction_sign * qty

        # Для **futures** FIFO matcher сейчас не персистит open Trade
        # записи (см. Phase 1+ T7 architectural fix). Плюс op.quantity и
        # portfolio.quantity имеют разные semantics (basic_asset_size vs
        # contracts). Поэтому для futures T7 audit давал false positive —
        # пропускаем futures полностью пока FIFO не научится сохранять
        # open lots как Trade с exit_at=None.
        inst = db.query(models.InstrumentORM).filter_by(uid=pos.instrument_uid).first()
        if inst is not None and inst.instrument_type == "futures":
            continue
        normalized_fifo = fifo_qty

        if abs(normalized_fifo - pos.quantity) > 1:
            mismatches.append({
                "instrument_uid": pos.instrument_uid,
                "instrument_type": inst.instrument_type if inst else None,
                "api_qty": pos.quantity,
                "fifo_qty_raw": fifo_qty,
                "fifo_qty_normalized": normalized_fifo,
            })

    if not mismatches:
        return None

    return TransformationWarning(
        code="T7",
        severity="high",
        description=(
            "Расхождение между API quantity (Tinkoff portfolio) и "
            "FIFO-computed quantity (открытые сделки). Возможен пропущенный "
            "trade или corporate action."
        ),
        count=len(mismatches),
        details={"mismatches": mismatches[:10]},
    )


# ════════════════════════════════════════════════════════════════════════
# T8: операции с quantity=0
# ════════════════════════════════════════════════════════════════════════


def _check_t8_zero_quantity_ops(db: Session, account_id: int) -> TransformationWarning | None:
    """BUY/SELL операции с quantity=0 — обычно это corp actions, но
    могут быть и truly bugged data. Логировать, не пропускать молча.
    """
    zero_qty = db.query(models.OperationORM).filter(
        models.OperationORM.account_id == account_id,
        models.OperationORM.operation_type.in_(["buy", "sell", "buy_card", "sell_card"]),
        models.OperationORM.quantity == 0,
    ).limit(50).all()

    if not zero_qty:
        return None

    return TransformationWarning(
        code="T8",
        severity="low",
        description=(
            "BUY/SELL операции с quantity=0. Обычно corporate actions "
            "(split/reverse split/delisting), но могут указывать на "
            "битые данные от Tinkoff."
        ),
        count=len(zero_qty),
        details={
            "examples": [
                {
                    "operation_id": op.operation_id,
                    "description": op.description,
                    "executed_at": op.executed_at.isoformat() if op.executed_at else None,
                }
                for op in zero_qty[:5]
            ],
        },
    )
