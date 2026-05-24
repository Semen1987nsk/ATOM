"""
PR 26 (Phase 3) — reconciliation_service: three-way correctness verification.

Сверяет наши агрегаты (P&L, commissions, dividends, NDFL, cash flow)
с **независимым** источником истины — официальным Tinkoff broker report
(GenerateBrokerReport + GetDividendsForeignIssuer).

Это отличается от `verify_service.py`:
- verify_service.py — CONSISTENCY (наша БД vs Tinkoff API сейчас)
- reconciliation_service.py — CORRECTNESS (мат. правильность через
  cross-check с независимым источником)

Tolerance: 10₽ или 0.1% от значения (whichever larger). Per user choice
в Phase 3 plan.

Структура результата ReconciliationResult совместима с
models.ReconciliationRunORM.metrics JSON field — её можно прямо туда
class-сериализовать.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy.orm import Session

import models
from domain.entities import BrokerReportSummary, BrokerReportTradeRow
from domain.enums import OperationType
from logger import get_logger
from utils.datetime_utils import utc_now_naive

log = get_logger("reconciliation")


# Tolerance константы (Phase 3 plan).
ABS_TOLERANCE_RUB = Decimal("10")
REL_TOLERANCE_PCT = Decimal("0.1")  # 0.1%


METRIC_KEYS = (
    "realized_pnl",
    "broker_commission_total",
    "exchange_commission_total",
    "clearing_commission_total",
    "dividends_gross",
    "ndfl_withheld",
    "net_cash_flow",
    "end_cash_balance",
)


# AU16: per-metric tolerance overrides + methodology notes.
# Дефолт: 10₽ / 0.1%. Для известных methodology mismatch — расширенные
# tolerance + inline note чтобы UI объяснил юзеру WHY есть разница.
_METRIC_TOLERANCES: dict[str, dict] = {
    "realized_pnl": {
        # FIFO closed trades по exit_at vs broker FIFO по rows за окно периода —
        # разные scope. Для позиций открытых до периода и закрытых внутри
        # него — наш realized_pnl > broker'ского (broker не видит entry
        # за окном).
        "abs_rub": Decimal("100"),
        "rel_pct": Decimal("5.0"),
        "note": (
            "ours = Σ Trade.net_pnl (closed trades, exit_at в периоде); "
            "broker = FIFO по rows broker_report за период. Разница ожидаема "
            "для позиций открытых до периода и закрытых в нём."
        ),
    },
    "broker_commission_total": {
        # AU15 verified ratio 1.0000 на live данных — strict.
        "abs_rub": Decimal("1"),
        "rel_pct": Decimal("0.001"),
        "note": "AU15: ours считается из BROKER_FEE ops (single source).",
    },
    "exchange_commission_total": {
        # broker_report делит commission на 3 категории (broker/exchange/
        # clearing); naya БД хранит всё в OPERATION_TYPE_BROKER_FEE.
        "abs_rub": Decimal("50"),
        "rel_pct": Decimal("50.0"),  # 50% — фактически informational
        "note": (
            "broker_report разбивает commission на broker/exchange/clearing; "
            "naya БД хранит всё в OPERATION_TYPE_BROKER_FEE. Asymmetry by "
            "design — реальный total commission совпадает (см. broker_commission_total)."
        ),
    },
    "clearing_commission_total": {
        # Тот же reason что exchange_commission_total — разный category split.
        "abs_rub": Decimal("50"),
        "rel_pct": Decimal("50.0"),
        "note": (
            "Аналогично exchange_commission — category split, не bug. "
            "ours = service_fee + margin_fee из ops (что Tinkoff наш sync видит "
            "как clearing-related)."
        ),
    },
    "end_cash_balance": {
        # broker_report не отдаёт end_cash_balance напрямую;
        # ours = Account.last_portfolio_value (proxy).
        "abs_rub": Decimal("200"),
        "rel_pct": Decimal("2.0"),
        "note": (
            "broker_report не отдаёт cash_balance напрямую; ours = "
            "Account.last_portfolio_value (snapshot после последнего sync). "
            "Если broker=0 — это означает что метрика недоступна, не реальный 0."
        ),
    },
}

_DEFAULT_TOLERANCE = {
    "abs_rub": ABS_TOLERANCE_RUB,
    "rel_pct": REL_TOLERANCE_PCT,
    "note": "",
}


@dataclass
class MetricCompare:
    """Сравнение одной метрики наших данных с broker report."""

    metric: str
    our_value: Decimal
    broker_value: Decimal
    diff_abs: Decimal
    diff_pct: Decimal
    status: str  # 'ok' | 'soft' | 'hard'
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "metric": self.metric,
            "ours": str(self.our_value),
            "broker": str(self.broker_value),
            "diff_abs": str(self.diff_abs),
            "diff_pct": str(self.diff_pct),
            "status": self.status,
            "note": self.note,
        }


@dataclass
class ReconciliationResult:
    account_id: int
    user_id: int
    period_start: datetime
    period_end: datetime
    started_at: datetime
    finished_at: Optional[datetime] = None
    status: str = "ok"  # ok | warning | break | error
    error_message: Optional[str] = None
    metrics: list[MetricCompare] = field(default_factory=list)
    # PR 26 (Phase 3, D4): дополнительные warnings из transformation_audit
    transformation_warnings: list[dict[str, Any]] = field(default_factory=list)

    @property
    def breaks_count(self) -> int:
        return sum(1 for m in self.metrics if m.status in {"hard", "soft"})

    @property
    def hard_breaks_count(self) -> int:
        return sum(1 for m in self.metrics if m.status == "hard")

    def compute_status(self) -> str:
        if self.error_message:
            return "error"
        if any(m.status == "hard" for m in self.metrics):
            return "break"
        if any(m.status == "soft" for m in self.metrics):
            return "warning"
        return "ok"

    def to_dict(self) -> dict[str, Any]:
        return {
            "account_id": self.account_id,
            "user_id": self.user_id,
            "period_start": self.period_start.isoformat(),
            "period_end": self.period_end.isoformat(),
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "status": self.status,
            "error_message": self.error_message,
            "metrics": [m.to_dict() for m in self.metrics],
            "breaks_count": self.breaks_count,
            "hard_breaks_count": self.hard_breaks_count,
            "transformation_warnings": self.transformation_warnings,
        }


def classify_diff(
    our: Decimal,
    broker: Decimal,
    *,
    metric: Optional[str] = None,
) -> tuple[Decimal, Decimal, str, str]:
    """Классификация расхождения по tolerance.

    AU16: per-metric tolerance overrides + methodology notes.
    Если `metric` указан и есть в `_METRIC_TOLERANCES` — используются его
    custom abs_rub/rel_pct и note. Иначе дефолт 10₽/0.1%, note пустой.

    Returns (diff_abs, diff_pct, status, methodology_note):
        status = 'ok'   — расхождение в пределах tolerance
        status = 'soft' — расхождение есть но малое (только один критерий)
        status = 'hard' — расхождение значительно превышает tolerance
    """
    tol = _METRIC_TOLERANCES.get(metric or "", _DEFAULT_TOLERANCE)
    abs_tol: Decimal = tol["abs_rub"]
    rel_tol: Decimal = tol["rel_pct"]
    note: str = tol.get("note", "")

    diff = our - broker
    diff_abs = abs(diff)
    base = max(abs(broker), Decimal("1"))
    diff_pct = (diff_abs / base) * Decimal("100")

    is_within_abs = diff_abs <= abs_tol
    is_within_pct = diff_pct <= rel_tol
    if is_within_abs or is_within_pct:
        return diff_abs, diff_pct, "ok", note

    # Hard break: оба критерия значительно превышены (10× от tolerance).
    # Soft break: иначе.
    if diff_abs > abs_tol * 10 and diff_pct > rel_tol * 5:
        return diff_abs, diff_pct, "hard", note
    return diff_abs, diff_pct, "soft", note


# ════════════════════════════════════════════════════════════════════════
# Our-side aggregates
# ════════════════════════════════════════════════════════════════════════


def _decimal(value: Any) -> Decimal:
    """Безопасный конвертер в Decimal (None → 0)."""
    if value is None:
        return Decimal(0)
    try:
        return Decimal(str(value))
    except Exception:
        return Decimal(0)


def _op_money_decimal(units: Any, nano: Any) -> Decimal:
    """Сборка Decimal из (units, nano) полей OperationORM."""
    u = int(units or 0)
    n = int(nano or 0)
    return Decimal(u) + Decimal(n) / Decimal(1_000_000_000)


def compute_our_aggregates(
    db: Session,
    account_id: int,
    period_start: datetime,
    period_end: datetime,
) -> dict[str, Decimal]:
    """Вычисляет наши агрегаты за период из БД (Trade + OperationORM).

    Используется как «our side» в сравнении с broker report.
    """
    # 1. Σ realized P&L из закрытых сделок (Trade.net_pnl где exit_at в периоде)
    trades = (
        db.query(models.Trade)
        .filter(
            models.Trade.account_id == account_id,
            models.Trade.exit_at.isnot(None),
            models.Trade.exit_at >= period_start,
            models.Trade.exit_at <= period_end,
        )
        .all()
    )
    realized_pnl = sum((_decimal(t.net_pnl) for t in trades), Decimal(0))

    # 2-4. Commissions: разделяем по типу из OperationORM
    # OPERATION_TYPE_BROKER_FEE — broker commission
    # OPERATION_TYPE_SERVICE_FEE / MARGIN_FEE — service/clearing
    # Exchange commission бывает в commission_units OperationORM на BUY/SELL
    broker_commission = Decimal(0)
    exchange_commission = Decimal(0)
    clearing_commission = Decimal(0)
    dividends_gross = Decimal(0)
    ndfl_withheld = Decimal(0)
    deposits = Decimal(0)
    withdrawals = Decimal(0)

    ops = (
        db.query(models.OperationORM)
        .filter(
            models.OperationORM.account_id == account_id,
            models.OperationORM.executed_at >= period_start,
            models.OperationORM.executed_at <= period_end,
        )
        .all()
    )

    for op in ops:
        op_type = (op.operation_type or "").lower()
        payment = _op_money_decimal(op.payment_units, op.payment_nano)
        commission = _op_money_decimal(op.commission_units, op.commission_nano)

        # AU15 fix: для cursor-based Tinkoff API broker_fee приходит как
        # ОТДЕЛЬНАЯ operation с parent_operation_id указывающим на BUY/SELL,
        # И параллельно записывается в op.commission родительского trade
        # (это видимо child-reference — диагностика на acc#4 показала ratio
        # 1.0000 между Σ |op.commission| и Σ |broker_fee.payment|).
        # Берём ОДНУ метрику — BROKER_FEE entries как source of truth
        # для broker commission. exchange_commission через op.commission
        # больше НЕ считаем — иначе double-count.
        if op_type in {"broker_fee", "broker_commission"}:
            broker_commission += abs(payment)
        elif op_type in {"exchange_fee", "exchange_commission"}:
            exchange_commission += abs(payment)
        elif op_type in {"service_fee", "margin_fee"}:
            clearing_commission += abs(payment)
        elif op_type == "dividend":
            dividends_gross += payment  # положительный знак для income
        elif op_type in {"benefit_tax", "tax", "ndfl"}:
            ndfl_withheld += abs(payment)
        elif op_type in {"input", "pay_in", "deposit"}:
            deposits += payment
        elif op_type in {"out", "pay_out", "withdrawal"}:
            withdrawals += abs(payment)

    # 7. Net cash flow = deposits - withdrawals
    net_cash_flow = deposits - withdrawals

    # 8. End-period cash balance — берём из Account.last_portfolio_value
    #    как proxy (точного cash balance мы пока не храним отдельно;
    #    P&L compute_balance_at используется в capital_service для UI).
    account = db.query(models.Account).filter_by(id=account_id).first()
    end_cash_balance = Decimal(0)
    if account is not None and account.last_portfolio_value is not None:
        end_cash_balance = _decimal(account.last_portfolio_value)

    return {
        "realized_pnl": realized_pnl,
        "broker_commission_total": broker_commission,
        "exchange_commission_total": exchange_commission,
        "clearing_commission_total": clearing_commission,
        "dividends_gross": dividends_gross,
        "ndfl_withheld": ndfl_withheld,
        "net_cash_flow": net_cash_flow,
        "end_cash_balance": end_cash_balance,
    }


# ════════════════════════════════════════════════════════════════════════
# Broker-side aggregates (from broker report)
# ════════════════════════════════════════════════════════════════════════


def _compute_broker_fifo_realized_pnl(trades: list[BrokerReportTradeRow]) -> Decimal:
    """AU13: FIFO realized P&L из rows broker_report (like-for-like с нашим).

    Раньше broker-side метрика была `sell_total - buy_total - commissions` —
    это cash-flow approximation, которая включает в realized PnL даже открытые
    позиции (купил в периоде и не продал — добавляется как −buy_total).
    Наша сторона же считает только closed-trade realized PnL через FIFO.
    Это давало false-positive `realized_pnl` break.

    Теперь broker-side тоже идёт через FIFO matching на broker_report rows:
    закрытие позиции по противоположному направлению → realized_pnl += diff.
    Открытые позиции в конце периода — НЕ дают realized P&L (как у нас).
    """
    from collections import defaultdict

    by_instr: dict[str, list[BrokerReportTradeRow]] = defaultdict(list)
    for r in trades:
        key = r.ticker or r.figi or r.trade_id
        by_instr[key].append(r)

    total_realized = Decimal(0)
    for key, rows in by_instr.items():
        rows_sorted = sorted(rows, key=lambda r: r.trade_datetime)
        # position: список dict-ов {qty, price, comm_per_unit, direction}
        position: list[dict[str, Any]] = []
        for r in rows_sorted:
            qty = int(r.quantity or 0)
            if qty <= 0:
                continue
            price = r.price or Decimal(0)
            total_comm = (
                abs(r.broker_commission or Decimal(0))
                + abs(r.exchange_commission or Decimal(0))
                + abs(r.exchange_clearing_commission or Decimal(0))
            )
            comm_per_unit = total_comm / qty if qty else Decimal(0)
            direction = r.direction

            remaining = qty
            # Closing opposite-direction positions FIFO style
            while remaining > 0 and position and position[0]["direction"] != direction:
                lot = position[0]
                close_qty = min(remaining, lot["qty"])
                if lot["direction"] == "buy" and direction == "sell":
                    # Closing long: pnl = (exit_price - entry_price) × qty
                    total_realized += (price - lot["price"]) * Decimal(close_qty)
                elif lot["direction"] == "sell" and direction == "buy":
                    # Closing short: pnl = (entry_price - exit_price) × qty
                    total_realized += (lot["price"] - price) * Decimal(close_qty)
                # subtract entry + exit commissions
                total_realized -= lot["comm_per_unit"] * Decimal(close_qty)
                total_realized -= comm_per_unit * Decimal(close_qty)
                lot["qty"] -= close_qty
                remaining -= close_qty
                if lot["qty"] == 0:
                    position.pop(0)

            if remaining > 0:
                position.append({
                    "qty": remaining,
                    "price": price,
                    "comm_per_unit": comm_per_unit,
                    "direction": direction,
                })

    return total_realized


def aggregate_broker_report(
    trades: list[BrokerReportTradeRow],
    foreign_dividends: list[dict[str, Any]],
    end_cash_balance: Optional[Decimal] = None,
) -> dict[str, Decimal]:
    """Агрегирует raw broker report rows в 8 метрик.

    AU13: realized_pnl теперь считается через FIFO matching на broker_report
    rows (см. `_compute_broker_fifo_realized_pnl`). Это like-for-like с нашей
    стороной (Σ Trade.net_pnl для closed trades в периоде).
    """
    broker_commission = Decimal(0)
    exchange_commission = Decimal(0)
    clearing_commission = Decimal(0)

    for r in trades:
        bc = r.broker_commission or Decimal(0)
        ec = r.exchange_commission or Decimal(0)
        cc = r.exchange_clearing_commission or Decimal(0)
        broker_commission += abs(bc)
        exchange_commission += abs(ec)
        clearing_commission += abs(cc)

    # AU13: FIFO realized PnL (commissions включены в формулу close-out).
    realized_pnl = _compute_broker_fifo_realized_pnl(trades)

    # Dividends from foreign issuer report
    dividends_gross = Decimal(0)
    ndfl_withheld = Decimal(0)
    for d in foreign_dividends:
        gross = d.get("dividend_gross")
        tax = d.get("tax")
        # Поля могут быть MoneyValue (proto) или None
        if gross is not None:
            units = getattr(gross, "units", 0) or 0
            nano = getattr(gross, "nano", 0) or 0
            dividends_gross += Decimal(units) + Decimal(nano) / Decimal(1_000_000_000)
        if tax is not None:
            units = getattr(tax, "units", 0) or 0
            nano = getattr(tax, "nano", 0) or 0
            ndfl_withheld += abs(Decimal(units) + Decimal(nano) / Decimal(1_000_000_000))

    return {
        "realized_pnl": realized_pnl,
        "broker_commission_total": broker_commission,
        "exchange_commission_total": exchange_commission,
        "clearing_commission_total": clearing_commission,
        "dividends_gross": dividends_gross,
        "ndfl_withheld": ndfl_withheld,
        # Net cash flow и end balance broker report не отдаёт прямо —
        # они вычисляются на нашей стороне. Для completeness ставим 0
        # чтобы метрики совпали dimensionally; reconcile_account
        # помечает их 'broker_unavailable' если нужно.
        "net_cash_flow": Decimal(0),
        "end_cash_balance": end_cash_balance if end_cash_balance is not None else Decimal(0),
    }


# ════════════════════════════════════════════════════════════════════════
# Main entry point
# ════════════════════════════════════════════════════════════════════════


async def reconcile_account(
    db: Session,
    account_id: int,
    *,
    period_start: datetime,
    period_end: datetime,
    fetch_broker_report: bool = True,
    cache_max_age_hours: int = 24,
    trigger: str = "admin_manual",
) -> ReconciliationResult:
    """Главная точка входа: запускает reconciliation для аккаунта за период.

    1. Считает наши агрегаты из БД (всегда быстро).
    2. Получает broker report (cache 24h по умолчанию, иначе fetch live).
    3. Сравнивает 8 метрик, классифицирует расхождения.
    4. Возвращает ReconciliationResult (для записи в ReconciliationRunORM).

    NB: записывание в БД делается на уровне caller-а (admin endpoint или
    nightly cron tool), чтобы service остался pure.
    """
    started_at = utc_now_naive()
    result = ReconciliationResult(
        account_id=account_id,
        user_id=0,  # заполним ниже
        period_start=period_start,
        period_end=period_end,
        started_at=started_at,
    )

    account = db.query(models.Account).filter_by(id=account_id).first()
    if account is None:
        result.error_message = f"account {account_id} not found"
        result.status = "error"
        result.finished_at = utc_now_naive()
        return result
    result.user_id = account.user_id

    # 1. Our aggregates (always)
    try:
        ours = compute_our_aggregates(db, account_id, period_start, period_end)
    except Exception as exc:
        log.exception("compute_our_aggregates_failed", extra={"account_id": account_id})
        result.error_message = f"compute_our_aggregates failed: {type(exc).__name__}: {exc}"
        result.status = "error"
        result.finished_at = utc_now_naive()
        return result

    # 2. Broker side
    broker: dict[str, Decimal] = {}
    if fetch_broker_report:
        try:
            broker = await _get_or_fetch_broker_aggregates(
                db,
                account=account,
                period_start=period_start,
                period_end=period_end,
                cache_max_age_hours=cache_max_age_hours,
            )
        except Exception as exc:
            log.exception("broker_report_fetch_failed", extra={"account_id": account_id})
            result.error_message = f"broker_report fetch failed: {type(exc).__name__}: {exc}"
            result.status = "error"
            result.finished_at = utc_now_naive()
            return result
    else:
        broker = {k: Decimal(0) for k in METRIC_KEYS}

    # 3. Compare 8 metrics. AU16: classify_diff теперь возвращает 4 элемента
    # — diff_abs, diff_pct, status, methodology_note (per-metric tolerance
    # из _METRIC_TOLERANCES применяется автоматически).
    for key in METRIC_KEYS:
        our_v = ours.get(key, Decimal(0))
        broker_v = broker.get(key, Decimal(0))
        diff_abs, diff_pct, status, note = classify_diff(our_v, broker_v, metric=key)
        if key in {"net_cash_flow", "end_cash_balance"} and not broker.get(key):
            # broker report не даёт эти метрики прямо — soft + override note
            status = "ok" if our_v == Decimal(0) else "soft"
            note = (
                "broker report doesn't expose this metric directly — "
                "local-only check (см. note)"
            )
        result.metrics.append(MetricCompare(
            metric=key,
            our_value=our_v,
            broker_value=broker_v,
            diff_abs=diff_abs,
            diff_pct=diff_pct,
            status=status,
            note=note,
        ))

    # 4. Transformation audit (T1–T8): looking for silent bugs in data conversion.
    try:
        from services.transformation_audit import audit_account
        warnings = audit_account(db, account_id)
        result.transformation_warnings = [w.to_dict() for w in warnings]
    except Exception as exc:
        log.exception("transformation_audit_failed", extra={"account_id": account_id})

    result.status = result.compute_status()
    # Любой critical transformation_warning эскалирует статус до warning
    if result.status == "ok" and any(
        w.get("severity") == "critical" for w in result.transformation_warnings
    ):
        result.status = "warning"

    result.finished_at = utc_now_naive()
    log.info(
        "reconciliation_complete",
        extra={
            "account_id": account_id,
            "status": result.status,
            "breaks": result.breaks_count,
            "hard_breaks": result.hard_breaks_count,
            "transformation_warnings": len(result.transformation_warnings),
            "trigger": trigger,
        },
    )
    return result


async def _get_or_fetch_broker_aggregates(
    db: Session,
    *,
    account: models.Account,
    period_start: datetime,
    period_end: datetime,
    cache_max_age_hours: int,
) -> dict[str, Decimal]:
    """Получает broker аggregaты с кэшированием в BrokerReportORM.

    Cache hit: если запись в broker_reports младше cache_max_age_hours —
    используем её. Иначе делаем live fetch + сохраняем.
    """
    cached = (
        db.query(models.BrokerReportORM)
        .filter_by(account_id=account.id, period_start=period_start, period_end=period_end)
        .first()
    )
    now = utc_now_naive()
    if cached is not None:
        age = now - cached.fetched_at
        if age < timedelta(hours=cache_max_age_hours):
            log.debug("broker_report_cache_hit", extra={"account_id": account.id})
            return {
                k: _decimal(getattr(cached, k, None))
                for k in METRIC_KEYS
            }

    # Live fetch
    conn = (
        db.query(models.BrokerConnection)
        .filter_by(account_id=account.id, is_active=1)
        .first()
    )
    if conn is None:
        log.warning("no_active_broker_connection", extra={"account_id": account.id})
        return {k: Decimal(0) for k in METRIC_KEYS}

    # PR 26 (Phase 3) — используем тот же TokenRepository что и orchestrator,
    # т.к. реальный токен зашифрован TokenEncryptionService (AES-GCM envelope),
    # не Fernet. Раньше я ошибочно дёргал crypto_utils.decrypt_token —
    # это давало "broker_token_decrypt_failed" и Tinkoff=0 в reconciliation.
    try:
        from adapters.persistence.token_repo import TokenRepository
        from adapters.security.token_encryption import TokenEncryptionService
        token_repo = TokenRepository(encryption=TokenEncryptionService())
        token = token_repo.decrypt(conn.api_token)
    except Exception as exc:
        log.warning(
            "broker_token_decrypt_failed",
            extra={"account_id": account.id, "error": str(exc)},
        )
        return {k: Decimal(0) for k in METRIC_KEYS}

    if not token:
        return {k: Decimal(0) for k in METRIC_KEYS}

    # AU12 fix: используем общую client_factory, чтобы reconciliation шёл
    # через тот же per-token rate-limiter (AU1) и broker_report sub-limiter
    # (AU2), что и обычный sync. Раньше прямой AsyncClient(token) обходил
    # endpoint config (sandbox vs prod), app_name metadata и all rate limits.
    from adapters.tinkoff.client_factory import client_factory
    from adapters.tinkoff.operations_client import TinkoffOperationsClient

    # Tinkoff API ожидает tz-aware datetime
    ps = period_start if period_start.tzinfo else period_start.replace(tzinfo=timezone.utc)
    pe = period_end if period_end.tzinfo else period_end.replace(tzinfo=timezone.utc)

    async with client_factory.async_client(token) as services:
        ops_client = TinkoffOperationsClient(services)
        trades = await ops_client.fetch_full_broker_report(
            conn.broker_account_id, from_dt=ps, to_dt=pe
        )
        try:
            foreign_dividends = await ops_client.get_dividends_foreign_issuer(
                conn.broker_account_id, from_dt=ps, to_dt=pe
            )
        except Exception:
            # Foreign dividend report часто отсутствует у новых аккаунтов
            foreign_dividends = []

    # Account end cash balance — берём snapshot из portfolio
    end_balance = (
        _decimal(account.last_portfolio_value)
        if account.last_portfolio_value
        else Decimal(0)
    )
    broker_aggs = aggregate_broker_report(trades, foreign_dividends, end_balance)

    # Save cache
    if cached is not None:
        for k, v in broker_aggs.items():
            setattr(cached, k, v)
        cached.fetched_at = now
        cached.trade_count = len(trades)
        cached.raw_trades = [_trade_to_json(t) for t in trades[:500]]  # cap для размера
    else:
        new_row = models.BrokerReportORM(
            account_id=account.id,
            period_start=period_start,
            period_end=period_end,
            fetched_at=now,
            trade_count=len(trades),
            raw_trades=[_trade_to_json(t) for t in trades[:500]],
            **{k: v for k, v in broker_aggs.items()},
        )
        db.add(new_row)
    db.commit()
    return broker_aggs


def _trade_to_json(t: BrokerReportTradeRow) -> dict[str, Any]:
    """Сериализация BrokerReportTradeRow в JSON-friendly dict для raw_trades."""
    return {
        "trade_id": t.trade_id,
        "order_id": t.order_id,
        "ticker": t.ticker,
        "figi": t.figi,
        "direction": t.direction,
        "trade_datetime": t.trade_datetime.isoformat() if t.trade_datetime else None,
        "quantity": t.quantity,
        "price": str(t.price) if t.price is not None else None,
        "order_amount": str(t.order_amount) if t.order_amount is not None else None,
        "total_order_amount": str(t.total_order_amount) if t.total_order_amount is not None else None,
        "aci_value": str(t.aci_value) if t.aci_value is not None else None,
        "broker_commission": str(t.broker_commission) if t.broker_commission is not None else None,
        "exchange_commission": str(t.exchange_commission) if t.exchange_commission is not None else None,
        "exchange_clearing_commission": str(t.exchange_clearing_commission) if t.exchange_clearing_commission is not None else None,
        "currency": t.currency,
    }


# ════════════════════════════════════════════════════════════════════════
# Persistence helpers
# ════════════════════════════════════════════════════════════════════════


def persist_reconciliation_run(
    db: Session,
    result: ReconciliationResult,
    *,
    trigger: str = "admin_manual",
    mode: str = "all",
) -> models.ReconciliationRunORM:
    """Сохраняет ReconciliationResult в БД (RunORM + BreakORM x N).

    Caller вызывает после await reconcile_account(). Здесь же
    db.commit() — caller получает persisted instance с id.
    """
    run = models.ReconciliationRunORM(
        account_id=result.account_id,
        user_id=result.user_id,
        period_start=result.period_start,
        period_end=result.period_end,
        started_at=result.started_at,
        finished_at=result.finished_at,
        status=result.status,
        breaks_count=result.breaks_count,
        mode=mode,
        trigger=trigger,
        error_message=result.error_message,
        metrics={m.metric: m.to_dict() for m in result.metrics},
    )
    db.add(run)
    db.flush()  # получить run.id

    for m in result.metrics:
        if m.status in {"hard", "soft"}:
            db.add(models.ReconciliationBreakORM(
                run_id=run.id,
                metric=m.metric,
                our_value=m.our_value,
                broker_value=m.broker_value,
                diff_abs=m.diff_abs,
                diff_pct=m.diff_pct,
                severity=m.status,
                note=m.note,
            ))
    db.commit()
    db.refresh(run)
    return run
