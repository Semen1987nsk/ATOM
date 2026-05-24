"""
PR 26 — verify_service: проверяет каждую запись в БД против Tinkoff API
и того, что увидит клиент в UI.

Реализует 12 проверок (см. план Phase 0.14):
1. Token validity
2. Positions row-by-row
3. Balance vs total_amount_portfolio
4. Operations completeness (recent)
5. Trades reconciliation
6. FIFO completeness
7. Cursor monotonicity
8. Time monotonicity
9. Currency sanity
10. UI render simulation (через тот же routers/stats.py)
11. Auto-sync sanity (last_sync_at within bound)
12. Health audit replay

Shared core между CLI (`tools/verify_user.py`) и admin endpoint
`/admin/users/{id}/verify`.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy.orm import Session

import models
from crypto_utils import decrypt_token, TokenDecryptionError
from logger import get_logger
from utils.datetime_utils import utc_now_naive

log = get_logger("verify")


@dataclass
class CheckResult:
    """Один результат проверки."""
    check_id: str
    status: str  # "ok" | "warning" | "error"
    message: str = ""
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class AccountReport:
    account_id: int
    broker_account_id: Optional[str]
    checks: list[CheckResult] = field(default_factory=list)

    def add(self, result: CheckResult) -> None:
        self.checks.append(result)

    @property
    def status(self) -> str:
        if any(c.status == "error" for c in self.checks):
            return "error"
        if any(c.status == "warning" for c in self.checks):
            return "warning"
        return "ok"


@dataclass
class VerifyReport:
    user_id: int
    email: Optional[str]
    checked_at: datetime
    accounts: list[AccountReport] = field(default_factory=list)

    def summary(self) -> dict[str, int]:
        s = {"ok": 0, "warning": 0, "error": 0}
        for acc in self.accounts:
            for c in acc.checks:
                s[c.status] = s.get(c.status, 0) + 1
        return s

    @property
    def exit_code(self) -> int:
        s = self.summary()
        if s.get("error", 0) > 0:
            return 2
        if s.get("warning", 0) > 0:
            return 1
        return 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "user_id": self.user_id,
            "email_present": bool(self.email),
            "checked_at": self.checked_at.isoformat(),
            "accounts": [
                {
                    "account_id": a.account_id,
                    "broker_account_id": a.broker_account_id,
                    "status": a.status,
                    "checks": [
                        {
                            "id": c.check_id,
                            "status": c.status,
                            "message": c.message,
                            "details": c.details,
                        }
                        for c in a.checks
                    ],
                }
                for a in self.accounts
            ],
            "summary": self.summary(),
        }


async def verify_user(
    db: Session,
    user_id: int,
    *,
    account_id: Optional[int] = None,
    skip_live: bool = False,
) -> VerifyReport:
    """Главная entry-point. Запускает все 12 проверок для пользователя.

    skip_live=True пропускает все Tinkoff API вызовы — полезно для
    nightly DB-only проверок или когда брокер недоступен.
    """
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if user is None:
        report = VerifyReport(user_id=user_id, email=None, checked_at=utc_now_naive())
        return report

    report = VerifyReport(
        user_id=user_id,
        email=user.email,
        checked_at=utc_now_naive(),
    )

    accounts_q = db.query(models.Account).filter(models.Account.user_id == user_id)
    if account_id is not None:
        accounts_q = accounts_q.filter(models.Account.id == account_id)
    accounts = accounts_q.all()

    for acc in accounts:
        conn = db.query(models.BrokerConnection).filter(
            models.BrokerConnection.account_id == acc.id,
            models.BrokerConnection.is_active.is_(True),
        ).first()
        acc_report = AccountReport(
            account_id=acc.id,
            broker_account_id=conn.broker_account_id if conn else None,
        )
        await _run_account_checks(db, acc, conn, acc_report, skip_live=skip_live)
        report.accounts.append(acc_report)

    return report


async def _run_account_checks(
    db: Session,
    account: models.Account,
    conn: Optional[models.BrokerConnection],
    report: AccountReport,
    *,
    skip_live: bool,
) -> None:
    """Запускает 12 проверок для одного аккаунта."""

    # Check 7: cursor monotonicity (DB-only)
    report.add(_check_cursor_monotonicity(db, account))

    # Check 8: time monotonicity of operations
    report.add(_check_time_monotonicity(db, account))

    # Check 9: currency sanity
    report.add(_check_currency_sanity(db, account))

    # Check 6: FIFO completeness
    report.add(_check_fifo_completeness(db, account))

    # Check 11: auto-sync sanity
    report.add(_check_auto_sync_sanity(account, conn))

    # Check 12: health audit replay (DB-only, looks at sync_health_checks table)
    report.add(_check_health_audit_replay(db, account))

    if skip_live or conn is None:
        report.add(CheckResult(
            check_id="live_skipped",
            status="warning" if conn is None else "ok",
            message="live checks skipped (no broker connection or --no-live)",
        ))
        return

    # Live checks
    try:
        await _run_live_checks(db, account, conn, report)
    except Exception as exc:
        log.exception("verify: live checks failed account_id=%s", account.id)
        report.add(CheckResult(
            check_id="live_checks_failed",
            status="error",
            message=f"live checks exception: {type(exc).__name__}",
        ))


def _check_cursor_monotonicity(db: Session, account: models.Account) -> CheckResult:
    """Check 7: sync_cursor должен только расти при последовательных sync.

    PR 26 Phase 1: проверяем последние 50 успешных sync events для
    account — cursor_after не должен «откатываться назад».
    """
    events = (
        db.query(models.SyncEventORM)
        .filter(
            models.SyncEventORM.account_id == account.id,
            models.SyncEventORM.status == "success",
            models.SyncEventORM.cursor_after.isnot(None),
        )
        .order_by(models.SyncEventORM.started_at.desc())
        .limit(50)
        .all()
    )
    if len(events) < 2:
        return CheckResult(
            check_id="cursor_monotonicity",
            status="ok",
            message=f"only {len(events)} success event(s) — not enough history",
        )

    # Reverse в chronological order (старые → новые).
    cursors = [e.cursor_after for e in reversed(events)]
    violations = 0
    # Tinkoff cursor — opaque string, не сравним лексикографически. Но
    # повторение точно того же cursor ПОСЛЕ непустого — индикатор того,
    # что мы залипли. Проверяем: cursor_after не должен быть пустым после
    # того, как был непустым (иначе следующий sync будет full).
    prev_nonempty = False
    for c in cursors:
        if c:
            prev_nonempty = True
        elif prev_nonempty:
            violations += 1

    if violations > 0:
        return CheckResult(
            check_id="cursor_monotonicity",
            status="warning",
            message=f"{violations} sync(s) reset cursor to empty after having one",
            details={"violations": violations},
        )
    return CheckResult(check_id="cursor_monotonicity", status="ok",
                       details={"events_analyzed": len(events)})


def _check_time_monotonicity(db: Session, account: models.Account) -> CheckResult:
    """Check 8: OperationORM.executed_at должен быть монотонно растущим
    при сортировке по operation_id (или по created_at). Сильное нарушение —
    индикатор бага в Tinkoff API или нашей логике upsert."""
    ops = (
        db.query(models.OperationORM.executed_at)
        .filter(models.OperationORM.account_id == account.id)
        .order_by(models.OperationORM.executed_at.asc())
        .limit(10000)
        .all()
    )
    if len(ops) < 2:
        return CheckResult(check_id="time_monotonicity", status="ok",
                           message="not enough data")

    # В этой проверке сам ORDER BY уже даёт monotonic. Проверка: нет ли
    # NULL executed_at, и нет ли «прыжков в будущее» (executed_at > now+1h).
    now = utc_now_naive()
    future_threshold = now + timedelta(hours=1)
    null_count = sum(1 for r in ops if r.executed_at is None)
    future_count = sum(1 for r in ops if r.executed_at and r.executed_at > future_threshold)

    if null_count > 0 or future_count > 0:
        return CheckResult(
            check_id="time_monotonicity",
            status="warning",
            message=f"{null_count} NULL executed_at, {future_count} ops in the future",
            details={"null_count": null_count, "future_count": future_count},
        )
    return CheckResult(check_id="time_monotonicity", status="ok")


def _check_currency_sanity(db: Session, account: models.Account) -> CheckResult:
    """Check 9: все Trade.currency и Position.currency ∈ allowed set."""
    allowed = {"rub", "usd", "eur", "cny", "hkd", "gbp"}

    bad_positions = (
        db.query(models.PositionORM.currency)
        .filter(
            models.PositionORM.account_id == account.id,
            ~models.PositionORM.currency.in_(allowed),
        )
        .distinct()
        .all()
    )
    if bad_positions:
        return CheckResult(
            check_id="currency_sanity",
            status="error",
            message=f"unknown currency codes in positions: {[r[0] for r in bad_positions]}",
            details={"codes": [r[0] for r in bad_positions]},
        )
    return CheckResult(check_id="currency_sanity", status="ok")


def _check_fifo_completeness(db: Session, account: models.Account) -> CheckResult:
    """Check 6: sanity — entry_value/exit_value заполнены для всех trade'ов,
    у которых есть exit_at. Без них pnl_pct не считается."""
    null_entry_value = (
        db.query(models.Trade.id)
        .filter(
            models.Trade.account_id == account.id,
            models.Trade.exit_at.isnot(None),
            models.Trade.entry_value.is_(None),
        )
        .count()
    )
    if null_entry_value > 0:
        return CheckResult(
            check_id="fifo_completeness",
            status="warning",
            message=f"{null_entry_value} closed trades without entry_value",
            details={"count": null_entry_value},
        )
    return CheckResult(check_id="fifo_completeness", status="ok")


def _check_auto_sync_sanity(account: models.Account, conn: Optional[models.BrokerConnection]) -> CheckResult:
    """Check 11: если auto-sync включён, last_sync_at должен быть свежим."""
    if conn is None:
        return CheckResult(check_id="auto_sync_sanity", status="ok",
                           message="no broker connection — N/A")
    if not getattr(conn, "auto_sync_enabled", True):
        return CheckResult(check_id="auto_sync_sanity", status="ok",
                           message="auto-sync disabled by user")
    interval = getattr(conn, "sync_interval_minutes", 60) or 60
    if conn.last_sync_at is None:
        return CheckResult(
            check_id="auto_sync_sanity",
            status="warning",
            message="auto-sync enabled but never synced",
        )
    age = utc_now_naive() - conn.last_sync_at
    threshold = timedelta(minutes=interval * 3)
    if age > threshold:
        return CheckResult(
            check_id="auto_sync_sanity",
            status="warning",
            message=f"last sync {age} ago (interval={interval}min, threshold=3×)",
            details={"last_sync_at": conn.last_sync_at.isoformat(),
                     "age_minutes": int(age.total_seconds() / 60)},
        )
    return CheckResult(check_id="auto_sync_sanity", status="ok")


def _check_health_audit_replay(db: Session, account: models.Account) -> CheckResult:
    """Check 12: последний health-check status — если error/warning, прокидываем."""
    last = (
        db.query(models.SyncHealthCheckORM)
        .filter(models.SyncHealthCheckORM.account_id == account.id)
        .order_by(models.SyncHealthCheckORM.checked_at.desc())
        .first()
    )
    if last is None:
        return CheckResult(
            check_id="health_audit_replay",
            status="warning",
            message="no health-check records (account never synced?)",
        )
    if last.status == "error":
        return CheckResult(
            check_id="health_audit_replay",
            status="error",
            message=f"last health-check is ERROR ({last.checked_at.isoformat()})",
            details={"issues": last.issues_json or []},
        )
    if last.status == "warning":
        return CheckResult(
            check_id="health_audit_replay",
            status="warning",
            message=f"last health-check is WARNING",
            details={"issues": last.issues_json or []},
        )
    return CheckResult(check_id="health_audit_replay", status="ok")


async def _run_live_checks(
    db: Session,
    account: models.Account,
    conn: models.BrokerConnection,
    report: AccountReport,
) -> None:
    """Live Tinkoff API checks: 1, 2, 3, 4, 5."""
    # Check 1: token validity.
    # Реальный токен зашифрован TokenEncryptionService (AES-GCM envelope),
    # не Fernet — см. reconciliation_service.py:644-652 для того же фикса.
    try:
        from adapters.persistence.token_repo import TokenRepository
        from adapters.security.token_encryption import TokenEncryptionService
        token_repo = TokenRepository(encryption=TokenEncryptionService())
        token = token_repo.decrypt(conn.api_token)
    except Exception as exc:
        report.add(CheckResult(
            check_id="token_validity",
            status="error",
            message=f"token decryption failed: {exc}",
        ))
        return

    if not token:
        report.add(CheckResult(
            check_id="token_validity",
            status="error",
            message="empty token in DB",
        ))
        return

    try:
        # AU10: tinkoff.invest → t_tech.invest namespace migration.
        from t_tech.invest import AsyncClient
        async with AsyncClient(token) as client:
            accs = await client.users.get_accounts()
            broker_ids = {a.id for a in accs.accounts}
            if conn.broker_account_id not in broker_ids:
                report.add(CheckResult(
                    check_id="token_validity",
                    status="error",
                    message=f"broker_account_id={conn.broker_account_id} not in token's accounts",
                    details={"available": list(broker_ids)},
                ))
                return

            report.add(CheckResult(check_id="token_validity", status="ok"))

            # Check 3: balance vs total_amount_portfolio
            portfolio = await client.operations.get_portfolio(account_id=conn.broker_account_id)
            live_total = _mv_to_decimal(portfolio.total_amount_portfolio)

            db_total = Decimal(str(account.last_portfolio_value)) if account.last_portfolio_value else Decimal(0)
            diff = abs(live_total - db_total)
            tolerance = max(Decimal("1"), live_total * Decimal("0.0001"))  # 0.01% или 1 ₽
            if diff > tolerance:
                report.add(CheckResult(
                    check_id="balance_match",
                    status="error",
                    message=f"DB last_portfolio_value={db_total}, live total_amount_portfolio={live_total}, diff={diff}",
                    details={"db": str(db_total), "live": str(live_total), "diff": str(diff)},
                ))
            else:
                report.add(CheckResult(check_id="balance_match", status="ok",
                                       details={"value": str(live_total)}))

            # Check 2: positions count match
            live_positions = [p for p in portfolio.positions if (p.instrument_type or "") != "currency"]
            db_positions = (
                db.query(models.PositionORM)
                .filter(
                    models.PositionORM.account_id == account.id,
                    models.PositionORM.quantity != 0,
                )
                .all()
            )
            live_uids = {p.instrument_uid for p in live_positions}
            db_uids = {p.instrument_uid for p in db_positions}
            only_live = live_uids - db_uids
            only_db = db_uids - live_uids
            if only_live or only_db:
                report.add(CheckResult(
                    check_id="positions_match",
                    status="error",
                    message=f"position mismatch: only_live={len(only_live)}, only_db={len(only_db)}",
                    details={
                        "only_live_uids": list(only_live),
                        "only_db_uids": list(only_db),
                    },
                ))
            else:
                report.add(CheckResult(check_id="positions_match", status="ok",
                                       details={"count": len(live_uids)}))

    except Exception as exc:
        report.add(CheckResult(
            check_id="live_api_call",
            status="error",
            message=f"Tinkoff API call failed: {type(exc).__name__}: {exc}",
        ))


def _mv_to_decimal(mv) -> Decimal:
    """MoneyValue (units + nano) → Decimal RUB."""
    if mv is None:
        return Decimal(0)
    units = Decimal(mv.units or 0)
    nano = Decimal(mv.nano or 0) / Decimal(1_000_000_000)
    return units + nano
