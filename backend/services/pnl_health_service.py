"""Phase 10 (2026-05-17): P&L Health Check core service.

Сравнивает результат двух независимых методологий расчёта P&L:

  Method A (Journal-based):
    journal_pnl = Σ closed Trade.net_pnl
                + Σ open Position.unrealized_pnl
                + account_level_adjustments  (orphan cash flows)

  Method B (Cash-truth):
    cash_pnl = Account.last_portfolio_value − Σ NET_DEPOSIT operations

В идеале A ≈ B (math identity при корректной работе FIFO + attribution + sync).
Расхождение |A − B| / |B| × 100 = diff_pct сигналит проблему:
  - status='ok' если < 0.5% (acc#4 после Phase 9: 0.09%)
  - status='warning' если 0.5–2%
  - status='mismatch' если ≥ 2%
  - status='na' если |B| < 1 ₽ (новый счёт без операций)

Performance: 6 SUM queries с indexed agg → ~50–150ms even for 10k-trade accounts.

Used by:
  - tasks/pnl_health_nightly.py (cron job для всех accounts 03:00 МСК)
  - application/sync/pipeline.py (post-sync hook)
  - routers/stats.py (on-demand refresh endpoint)
  - routers/admin.py (drill-down)
"""
from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Literal, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

import models
from domain.pnl.cash_flow_classification import (
    CashFlowCategory,
    operation_types_in,
)
from logger import get_logger
from utils.datetime_utils import utc_now_naive

log = get_logger("pnl_health")


HealthStatus = Literal["ok", "warning", "mismatch", "na", "stale"]

# Thresholds for status classification.
# Реалистично для трейдинга с фьючерсами: post-clearing варм-маржа MOEX + сборы
# Тинькофф (margin/service) часто создают orphan'ы 1-5% от cash_pnl, которые не
# attribute'ятся к конкретным Trade.net_pnl. Это технический разрыв, не реальная
# потеря — деньги уже сняты со счёта. До 1% → ✅ ok, до 5% → ⚠️ warning, выше → 🔴.
THRESHOLD_OK_PCT = Decimal("1.0")
THRESHOLD_WARNING_PCT = Decimal("5.0")
# Если |cash_pnl| < этого — divide-by-zero не имеет смысла, status='na'.
NA_CASH_TRUTH_RUB = Decimal("1.0")
# Если health check старше этого — UI помечает как 'stale' (см. router).
STALE_AFTER_DAYS = 7


@dataclass
class PnLHealthResult:
    account_id: int
    journal_pnl: Decimal
    cash_pnl: Decimal
    diff_rub: Decimal
    diff_pct: Decimal
    status: HealthStatus
    components: dict
    computed_at: datetime
    duration_ms: int

    def to_breakdown_json(self) -> dict:
        """Serializable dict for Account.last_pnl_health_breakdown JSON column."""
        out = {
            "journal_pnl": float(self.journal_pnl),
            "cash_pnl": float(self.cash_pnl),
            "diff_rub": float(self.diff_rub),
            "diff_pct": float(self.diff_pct),
            "status": self.status,
            "components": {
                k: float(v) if isinstance(v, Decimal) else v
                for k, v in self.components.items()
            },
            "computed_at": self.computed_at.isoformat(),
            "duration_ms": self.duration_ms,
        }
        return out


def _sum_cash_category(
    session: Session, account_id: int, category: CashFlowCategory
) -> Decimal:
    """Σ payment_units + payment_nano/1e9 для всех ops данной категории."""
    types = tuple(operation_types_in(category))
    if not types:
        return Decimal(0)
    row = session.query(
        func.coalesce(func.sum(models.OperationORM.payment_units), 0),
        func.coalesce(func.sum(models.OperationORM.payment_nano), 0),
    ).filter(
        models.OperationORM.account_id == account_id,
        models.OperationORM.state == "executed",
        models.OperationORM.operation_type.in_(types),
    ).one()
    return Decimal(int(row[0] or 0)) + Decimal(int(row[1] or 0)) / Decimal(1_000_000_000)


def _sum_trade_field(
    session: Session, account_id: int, field_name: str, *, closed_only: bool = False
) -> Decimal:
    """Σ Trade.<field> для аккаунта, опционально только closed."""
    col = getattr(models.Trade, field_name)
    q = session.query(func.coalesce(func.sum(col), 0)).filter(
        models.Trade.account_id == account_id
    )
    if closed_only:
        q = q.filter(models.Trade.exit_at.isnot(None))
    return Decimal(q.scalar() or 0)


def _sum_closed_futures_body(session: Session, account_id: int) -> Decimal:
    """Phase 9: для closed futures Trade.pnl содержит body=(exit-entry)*qty*pv.
    Используется в orphan_varmargin корректировке (см. routers/stats.py Phase 9.5b)."""
    return Decimal(
        session.query(func.coalesce(func.sum(models.Trade.pnl), 0)).filter(
            models.Trade.account_id == account_id,
            models.Trade.exit_at.isnot(None),
            models.Trade.instrument_type_v2 == "futures",
            models.Trade.point_value.isnot(None),
        ).scalar() or 0
    )


def _status_from_diff_pct(diff_pct: Decimal, cash_pnl: Decimal) -> HealthStatus:
    if abs(cash_pnl) < NA_CASH_TRUTH_RUB:
        return "na"
    pct = abs(diff_pct)
    if pct < THRESHOLD_OK_PCT:
        return "ok"
    if pct < THRESHOLD_WARNING_PCT:
        return "warning"
    return "mismatch"


def compute_health(session: Session, account_id: int) -> PnLHealthResult:
    """Single-query batch (~30-80ms). Не пишет в БД — call persist_health() отдельно.

    Phase 6.3 (2026-05-18, cash-anchored): journal_pnl proxy = Σ Trade.net_pnl(closed)
    + Σ Position.unrealized_pnl. БЕЗ orphan adjustments — это и есть «как Дневник
    сделок видит P&L». Health check теперь honest signal: насколько per-trade
    tracking explains broker cash truth. Diff отражает unattributed orphans
    (post-clearing varmargin, dividends на закрытых позициях, fees между сделок).

    До 2026-05-18 формула включала account_level_adjustments — это double-counted
    варм-маржу для open futures и давало false-positive 2% mismatch на здоровых
    аккаунтах. См. domain/pnl/dashboard_pnl.py для математической отсылки.
    """
    t_start = time.perf_counter()

    account = session.get(models.Account, account_id)
    if account is None:
        return PnLHealthResult(
            account_id=account_id,
            journal_pnl=Decimal(0),
            cash_pnl=Decimal(0),
            diff_rub=Decimal(0),
            diff_pct=Decimal(0),
            status="na",
            components={"reason": "account_not_found"},
            computed_at=utc_now_naive(),
            duration_ms=int((time.perf_counter() - t_start) * 1000),
        )

    # ===== Method A: per-trade tracking sum (Дневник view) =====
    total_pnl_closed = _sum_trade_field(session, account_id, "net_pnl", closed_only=True)
    unrealized_pnl = Decimal(
        session.query(func.coalesce(func.sum(models.PositionORM.unrealized_pnl), 0))
        .filter(models.PositionORM.account_id == account_id)
        .scalar() or 0
    )
    journal_pnl = total_pnl_closed + unrealized_pnl

    # ===== Method B: broker cash truth =====
    net_deposits = _sum_cash_category(session, account_id, CashFlowCategory.NET_DEPOSIT)
    portfolio_value = Decimal(account.last_portfolio_value or 0)
    cash_pnl = portfolio_value - net_deposits

    # ===== Compare =====
    diff_rub = journal_pnl - cash_pnl
    if abs(cash_pnl) >= NA_CASH_TRUTH_RUB:
        diff_pct = abs(diff_rub) / abs(cash_pnl) * Decimal(100)
    else:
        diff_pct = Decimal(0)
    status = _status_from_diff_pct(diff_pct, cash_pnl)

    components = {
        "total_pnl_closed": total_pnl_closed,
        "unrealized_pnl": unrealized_pnl,
        "net_deposits": net_deposits,
        "portfolio_value": portfolio_value,
    }

    duration_ms = int((time.perf_counter() - t_start) * 1000)
    result = PnLHealthResult(
        account_id=account_id,
        journal_pnl=journal_pnl,
        cash_pnl=cash_pnl,
        diff_rub=diff_rub,
        diff_pct=diff_pct,
        status=status,
        components=components,
        computed_at=utc_now_naive(),
        duration_ms=duration_ms,
    )

    log.info(
        "pnl_health.computed",
        extra={
            "account_id": account_id,
            "status": status,
            "diff_pct": float(diff_pct),
            "diff_rub": float(diff_rub),
            "duration_ms": duration_ms,
        },
    )
    return result


def persist_health(session: Session, result: PnLHealthResult) -> None:
    """UPDATE accounts SET last_pnl_health_* — idempotent."""
    account = session.get(models.Account, result.account_id)
    if account is None:
        log.warning("pnl_health.persist_skip_no_account", extra={"account_id": result.account_id})
        return
    account.last_pnl_health_at = result.computed_at
    account.last_pnl_health_status = result.status
    account.last_pnl_health_diff_pct = result.diff_pct
    account.last_pnl_health_diff_rub = result.diff_rub
    account.last_pnl_health_breakdown = result.to_breakdown_json()
    session.commit()


def compute_and_persist(session: Session, account_id: int) -> PnLHealthResult:
    """Convenience helper: compute + persist в одном transaction."""
    result = compute_health(session, account_id)
    persist_health(session, result)
    return result


def is_stale(account: "models.Account", now: Optional[datetime] = None) -> bool:
    """True если last_pnl_health_at старше STALE_AFTER_DAYS."""
    if account.last_pnl_health_at is None:
        return True
    now = now or utc_now_naive()
    age = now - account.last_pnl_health_at
    return age.days >= STALE_AFTER_DAYS
