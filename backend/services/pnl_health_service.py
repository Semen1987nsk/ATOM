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
    CASH_FLOW_MAP,
    CashFlowCategory,
    operation_types_in,
)
from domain.pnl.data_quality import (
    cash_reconstruction_residual,
    ratio_sanity,
    trade_outliers,
    ReconStatus,
)
from logger import get_logger
from utils.datetime_utils import utc_now_naive

log = get_logger("pnl_health")


HealthStatus = Literal["ok", "warning", "investigate", "na", "stale"]

# Thresholds for status classification (ADR-0008: клиринг-band = ADR-0007 5/25).
# Post-clearing варм-маржа MOEX + сборы Тинькофф создают orphan'ы до ~5% от
# cash_pnl — технический разрыв, не реальная потеря. До 5% → ok, 5-25% → warning,
# ≥25% → investigate (вероятная проблема с attribution, требует разбора).
THRESHOLD_OK_PCT = Decimal("5.0")
THRESHOLD_WARNING_PCT = Decimal("25.0")
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
    return "investigate"


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
    # ADR-0010: эффективные депозиты = реальные + восстановленный баланс открытия
    # (для счёта с неполной историей). source='inferred_anchor'/'manual' → база
    # включает initial_balance; иначе initial_balance=0 → формула неизменна.
    initial_balance = Decimal(account.initial_balance or 0)
    effective_deposits = net_deposits + initial_balance
    cash_pnl = portfolio_value - effective_deposits

    # ===== Compare =====
    diff_rub = journal_pnl - cash_pnl
    if abs(cash_pnl) >= NA_CASH_TRUTH_RUB:
        diff_pct = abs(diff_rub) / abs(cash_pnl) * Decimal(100)
    else:
        diff_pct = Decimal(0)
    status = _status_from_diff_pct(diff_pct, cash_pnl)

    # ===== Data-quality layers (ADR-0008) =====
    # Слой 1 — non-deposit cash (futures buy/sell payments исключены: notional, не cash).
    net_deposit_types = tuple(operation_types_in(CashFlowCategory.NET_DEPOSIT))
    fut_trade_types = ("buy", "sell", "buy_card", "sell_card", "buy_margin", "sell_margin")
    non_dep_row = session.query(
        func.coalesce(func.sum(models.OperationORM.payment_units), 0),
        func.coalesce(func.sum(models.OperationORM.payment_nano), 0),
    ).filter(
        models.OperationORM.account_id == account_id,
        models.OperationORM.state == "executed",
        models.OperationORM.operation_type.notin_(net_deposit_types),
        # Exclude futures notional buy/sell (instrument_type IS NULL → не фьючерс).
        ~(
            models.OperationORM.operation_type.in_(fut_trade_types)
            & (models.OperationORM.instrument_type == "futures")
            & models.OperationORM.instrument_type.isnot(None)
        ),
    ).one()
    non_deposit_cash = (
        Decimal(int(non_dep_row[0] or 0))
        + Decimal(int(non_dep_row[1] or 0)) / Decimal(1_000_000_000)
    )
    layer1 = cash_reconstruction_residual(
        portfolio_value=portfolio_value,
        net_deposits=effective_deposits,
        non_deposit_cash=non_deposit_cash,
    )
    layer2 = ratio_sanity(journal_pnl=journal_pnl, cash_pnl=cash_pnl)

    # Слой 4 — per-trade outliers (символ + net_pnl закрытых).
    trade_rows = session.query(
        models.Trade.symbol, models.Trade.net_pnl,
    ).filter(
        models.Trade.account_id == account_id,
        models.Trade.exit_at.isnot(None),
    ).all()
    outlier_symbols = trade_outliers(
        trades=[(s, Decimal(p or 0)) for s, p in trade_rows],
        # ADR-0010: outlier base = effective deposits (incl. anchor), consistent with cash_pnl/layer1
        net_deposits=effective_deposits,
    )

    # Слой 6 — операции с cash-эффектом, тип которых не в CASH_FLOW_MAP.
    known_types = tuple(CASH_FLOW_MAP.keys())
    unknown_rows = session.query(
        models.OperationORM.operation_type,
        func.count(),
    ).filter(
        models.OperationORM.account_id == account_id,
        models.OperationORM.state == "executed",
        models.OperationORM.operation_type.notin_(known_types),
    ).group_by(models.OperationORM.operation_type).all()
    unknown_detail = {t: int(c) for t, c in unknown_rows}
    unknown_status = "warning" if unknown_detail else "ok"

    # Слой 5 — последний прогон трёхсторонней сверки (operations↔broker_report↔portfolio).
    last_recon = (
        session.query(models.ReconciliationRunORM)
        .filter(models.ReconciliationRunORM.account_id == account_id)
        .order_by(models.ReconciliationRunORM.started_at.desc())
        .first()
    )
    if last_recon is None:
        recon_status = "na"
    elif last_recon.status == "break":
        recon_status = "break"
    else:
        recon_status = last_recon.status

    band_status = status  # слой 3 (diff_pct band)
    # worst-of: RED любого слоя → 'investigate' (громкая страховка от ×1000)
    if ReconStatus.RED in (layer1.status, layer2.status):
        status = "investigate"
    elif outlier_symbols and status == "ok":
        status = "warning"
    if unknown_detail and status == "ok":
        status = "warning"
    if recon_status == "break" and status == "ok":
        status = "warning"

    components = {
        "total_pnl_closed": total_pnl_closed,
        "unrealized_pnl": unrealized_pnl,
        "net_deposits": net_deposits,
        "portfolio_value": portfolio_value,
        "clearing_adjustment": cash_pnl - journal_pnl,
        "layers": {
            "clearing_band": band_status,
            "cash_reconstruction": layer1.status.value,
            "ratio_sanity": layer2.status.value,
            "trade_outliers": "warning" if outlier_symbols else "ok",
            "unknown_types": unknown_status,
            "three_way_recon": recon_status,
        },
        "cash_reconstruction_residual": layer1.residual,
        "ratio": layer2.residual,
        "outlier_symbols": outlier_symbols,
        "unknown_types_detail": unknown_detail,
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
