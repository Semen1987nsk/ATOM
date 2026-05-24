"""
Sync Health Audit (PR 20).

После каждого успешного pipeline.run проверяет состояние данных аккаунта
по набору правил и возвращает HealthReport. Результат сохраняется в БД
(SyncHealthCheckORM) — UI и admin читают последний снимок.

Правила (см. план в /plans/...):
- структурные: missing asset_name / entry_value / holding_time / ticker
- консистентность: pnl sign vs payments, weird currency, entry_at > exit_at
- разумность: pnl_pct anomaly (>200%)
- live-sync: positions count vs Tinkoff (если переданы)
- broker state: circuit_open_long, consecutive_failures_high
- sanity: canceled_ops_in_fifo

Каждое правило — самостоятельная функция, возвращает IssueRecord или None.
Если sync прошёл успешно, audit не блокирует — пишет статус и выходит.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from logger import get_logger
from models import (
    BrokerConnection,
    InstrumentORM,
    OperationORM,
    PositionORM,
    Trade,
)
from utils.datetime_utils import utc_now_naive

log = get_logger("sync_health_audit")


# ── public types ─────────────────────────────────────────────────────


SEVERITY_OK = "ok"
SEVERITY_WARNING = "warning"
SEVERITY_ERROR = "error"


@dataclass(frozen=True)
class IssueRecord:
    """Одна группа однотипных проблем."""

    check_id: str
    severity: str  # 'warning' | 'error'
    count: int
    description: str
    sample_ids: tuple[int, ...] = ()  # IDs затронутых Trade / Position для drill-down

    def to_dict(self) -> dict[str, Any]:
        return {
            "check_id": self.check_id,
            "severity": self.severity,
            "count": self.count,
            "description": self.description,
            "sample_ids": list(self.sample_ids),
        }


@dataclass
class HealthReport:
    account_id: int
    broker_account_id: str
    sync_id: Optional[str]
    checked_at: datetime
    total_trades_checked: int = 0
    trades_with_issues: int = 0
    issues: list[IssueRecord] = field(default_factory=list)

    @property
    def status(self) -> str:
        if any(i.severity == SEVERITY_ERROR for i in self.issues):
            return SEVERITY_ERROR
        if any(i.severity == SEVERITY_WARNING for i in self.issues):
            return SEVERITY_WARNING
        return SEVERITY_OK

    @property
    def main_issue(self) -> Optional[str]:
        """ID самой серьёзной проблемы для краткого summary в UI."""
        for sev in (SEVERITY_ERROR, SEVERITY_WARNING):
            for i in self.issues:
                if i.severity == sev:
                    return i.check_id
        return None

    def to_db_fields(self) -> dict[str, Any]:
        return {
            "account_id": self.account_id,
            "broker_account_id": self.broker_account_id,
            "sync_id": self.sync_id,
            "checked_at": self.checked_at,
            "status": self.status,
            "total_trades_checked": self.total_trades_checked,
            "trades_with_issues": self.trades_with_issues,
            "issues_json": [i.to_dict() for i in self.issues],
        }


# ── auditor ──────────────────────────────────────────────────────────


# Сколько IDs показывать в sample (для drill-down). Без ограничения JSON
# раздуется на больших аккаунтах.
_SAMPLE_LIMIT = 10

# Допуск для проверки pnl-знака (рубли). Защищает от округлений.
_PNL_TOLERANCE_RUB = 2.0

# Порог "необъяснимо большого процента" — выше скорее всего баг расчёта,
# а не реальная сделка.
_PNL_PCT_ANOMALY_THRESHOLD = 200.0

# Сколько часов unrealized_pnl считается актуальным.
_STALE_MARK_TO_MARKET_HOURS = 24

# Сколько часов открытого circuit_open считается критичным.
_CIRCUIT_OPEN_THRESHOLD_HOURS = 2

# Сколько подряд failures считается тревожным.
_CONSECUTIVE_FAILURES_THRESHOLD = 3

# Допустимые валюты (всё что не из этого списка — warning).
_VALID_CURRENCIES = {"rub", "rur", "usd", "eur", "cny", "hkd", "gbp"}


class SyncHealthAuditor:
    """
    Запускает набор проверок над account_id и собирает HealthReport.

    Каждая `_check_*` функция:
    - принимает session + контекст,
    - возвращает IssueRecord или None.

    Аудитор НЕ изменяет данные. Только наблюдает.
    """

    def audit_account(
        self,
        session: Session,
        *,
        account_id: int,
        broker_account_id: str,
        sync_id: Optional[str] = None,
        live_position_uids: Optional[set[str]] = None,
    ) -> HealthReport:
        """
        live_position_uids — set instrument_uid'ов которые сейчас открыты на
        счёте Tinkoff (берём из get_portfolio в pipeline). Если None — sync
        position check пропускаем (тогда аудит не зависит от вызовов API).
        """
        report = HealthReport(
            account_id=account_id,
            broker_account_id=broker_account_id,
            sync_id=sync_id,
            checked_at=utc_now_naive(),
        )

        # Загружаем все closed sync-trade'ы одним запросом — это база для
        # большинства проверок.
        sync_trades = (
            session.query(Trade)
            .filter(
                Trade.account_id == account_id,
                Trade.data_source == "tinkoff_v2",
                Trade.exit_at.isnot(None),
            )
            .all()
        )
        report.total_trades_checked = len(sync_trades)

        # Структура / консистентность по trade'ам (если есть trade'ы).
        affected_trade_ids: set[int] = set()
        if sync_trades:
            for issue, ids in self._check_trades(session, sync_trades):
                if issue:
                    self._collect(report, issue)
                    affected_trade_ids.update(ids)
        report.trades_with_issues = len(affected_trade_ids)

        # Положение по позициям (работает даже без trade'ов — у юзера могут
        # быть открытые позиции от первоначального переноса бумаг).
        self._collect(
            report, self._check_positions(session, account_id, live_position_uids)
        )
        self._collect(report, self._check_stale_mtm(session, account_id))

        # Broker connection state.
        self._collect(report, self._check_circuit_open(session, account_id))
        self._collect(report, self._check_consecutive_failures(session, account_id))

        # Sanity: canceled ops не должны попадать в FIFO (но мы фильтруем
        # на уровне operation_repo, эта проверка — последняя защита).
        if sync_trades:
            self._collect(
                report,
                self._check_canceled_ops_attached_to_trades(session, account_id),
            )

        return report

    # ── individual checks ─────────────────────────────────────────────

    @staticmethod
    def _collect(report: HealthReport, issue: Optional[IssueRecord]) -> None:
        if issue is not None and issue.count > 0:
            report.issues.append(issue)

    def _check_trades(
        self, session: Session, trades: list[Trade]
    ):
        """Проверки по trade-записям. Возвращает поток (IssueRecord, set[int])."""
        missing_name_ids: list[int] = []
        missing_holding_ids: list[int] = []
        missing_entry_value_ids: list[int] = []
        ticker_mismatch_ids: list[int] = []
        weird_currency_ids: list[int] = []
        entry_after_exit_ids: list[int] = []
        pnl_sign_diverges_ids: list[int] = []
        pnl_pct_anomaly_ids: list[int] = []

        # Подготовим map ticker'ов из Instrument (один запрос вместо N).
        uids = {t.instrument_uid for t in trades if t.instrument_uid}
        instr_tickers: dict[str, str] = {}
        if uids:
            rows = (
                session.query(InstrumentORM.uid, InstrumentORM.ticker)
                .filter(InstrumentORM.uid.in_(uids))
                .all()
            )
            instr_tickers = {uid: tk for uid, tk in rows if tk}

        for t in trades:
            tid = t.id

            if t.asset_name is None:
                missing_name_ids.append(tid)
            if t.holding_time_minutes is None:
                missing_holding_ids.append(tid)

            if t.instrument_uid:
                expected_ticker = instr_tickers.get(t.instrument_uid)
                if expected_ticker and t.symbol and t.symbol != expected_ticker:
                    ticker_mismatch_ids.append(tid)

            ev = float(t.entry_value) if t.entry_value is not None else None
            xv = float(t.exit_value) if t.exit_value is not None else None
            pnl = float(t.pnl) if t.pnl is not None else None

            if ev is None or ev <= 0:
                missing_entry_value_ids.append(tid)
            else:
                # PnL sign check (только для share/etf — у фьючерсов есть
                # варм-маржа, у бондов купоны, у опционов settlement).
                itype = (t.instrument_type_v2 or "").lower()
                if (
                    itype in ("share", "etf", "currency")
                    and xv is not None
                    and pnl is not None
                ):
                    direction = str(t.direction).lower().replace("tradedirection.", "")
                    expected_unsigned = xv - ev if direction == "long" else ev - xv
                    if abs(pnl - expected_unsigned) > max(
                        _PNL_TOLERANCE_RUB, abs(expected_unsigned) * 0.001
                    ):
                        pnl_sign_diverges_ids.append(tid)

                if pnl is not None:
                    pct = abs(pnl / ev * 100)
                    if pct > _PNL_PCT_ANOMALY_THRESHOLD:
                        pnl_pct_anomaly_ids.append(tid)

            if t.currency and t.currency.lower() not in _VALID_CURRENCIES:
                weird_currency_ids.append(tid)

            if t.entry_at and t.exit_at and t.entry_at > t.exit_at:
                entry_after_exit_ids.append(tid)

        def make(check_id: str, severity: str, ids: list[int], desc: str):
            if not ids:
                return None, set()
            return (
                IssueRecord(
                    check_id=check_id,
                    severity=severity,
                    count=len(ids),
                    description=desc,
                    sample_ids=tuple(ids[:_SAMPLE_LIMIT]),
                ),
                set(ids),
            )

        yield make("missing_asset_name", SEVERITY_WARNING, missing_name_ids,
                   "Trade.asset_name is NULL — выполните backfill_trade_metadata")
        yield make("missing_holding_time", SEVERITY_WARNING, missing_holding_ids,
                   "holding_time_minutes is NULL")
        yield make("missing_entry_value", SEVERITY_ERROR, missing_entry_value_ids,
                   "entry_value is NULL — pnl_pct работать не будет")
        yield make("ticker_mismatch", SEVERITY_ERROR, ticker_mismatch_ids,
                   "Trade.symbol не совпадает с Instrument.ticker")
        yield make("weird_currency", SEVERITY_WARNING, weird_currency_ids,
                   "Нестандартный код валюты (не RUB/USD/EUR/CNY/HKD/GBP)")
        yield make("entry_after_exit", SEVERITY_ERROR, entry_after_exit_ids,
                   "entry_at > exit_at — нарушение хронологии")
        yield make("pnl_sign_diverges_from_payments", SEVERITY_ERROR, pnl_sign_diverges_ids,
                   "Знак pnl не сходится с (exit_value - entry_value) для share/etf")
        yield make("pnl_pct_anomaly", SEVERITY_WARNING, pnl_pct_anomaly_ids,
                   f"|pnl_pct| > {_PNL_PCT_ANOMALY_THRESHOLD}% — возможно ошибка расчёта")

    def _check_positions(
        self,
        session: Session,
        account_id: int,
        live_position_uids: Optional[set[str]],
    ) -> Optional[IssueRecord]:
        """Сверка локальных PositionORM с live Tinkoff (если переданы)."""
        if live_position_uids is None:
            return None
        local_uids = {
            uid
            for (uid,) in session.query(PositionORM.instrument_uid)
            .filter(PositionORM.account_id == account_id)
            .all()
        }
        diff_local_only = local_uids - live_position_uids
        diff_live_only = live_position_uids - local_uids
        total_diff = len(diff_local_only) + len(diff_live_only)
        if total_diff == 0:
            return None
        return IssueRecord(
            check_id="position_count_mismatch_with_tinkoff",
            severity=SEVERITY_ERROR,
            count=total_diff,
            description=(
                f"Локально {len(local_uids)} позиций vs у Тинькова {len(live_position_uids)} "
                f"(в DB лишних {len(diff_local_only)}, у Тинькова лишних {len(diff_live_only)})"
            ),
        )

    def _check_stale_mtm(
        self, session: Session, account_id: int
    ) -> Optional[IssueRecord]:
        threshold = utc_now_naive() - timedelta(hours=_STALE_MARK_TO_MARKET_HOURS)
        rows = (
            session.query(PositionORM.id)
            .filter(
                PositionORM.account_id == account_id,
                or_(
                    PositionORM.last_priced_at.is_(None),
                    PositionORM.last_priced_at < threshold,
                ),
            )
            .all()
        )
        if not rows:
            return None
        ids = [r[0] for r in rows]
        return IssueRecord(
            check_id="stale_mark_to_market",
            severity=SEVERITY_WARNING,
            count=len(ids),
            description=(
                f"У {len(ids)} позиций last_priced_at старше "
                f"{_STALE_MARK_TO_MARKET_HOURS}ч — unrealized PnL устарел"
            ),
            sample_ids=tuple(ids[:_SAMPLE_LIMIT]),
        )

    def _check_circuit_open(
        self, session: Session, account_id: int
    ) -> Optional[IssueRecord]:
        threshold = utc_now_naive() + timedelta(hours=_CIRCUIT_OPEN_THRESHOLD_HOURS)
        conn = (
            session.query(BrokerConnection)
            .filter(
                BrokerConnection.account_id == account_id,
                BrokerConnection.is_active.is_(True),
            )
            .first()
        )
        if conn is None or conn.circuit_open_until is None:
            return None
        if conn.circuit_open_until <= threshold:
            return None
        return IssueRecord(
            check_id="circuit_open_long",
            severity=SEVERITY_ERROR,
            count=1,
            description=(
                f"Circuit breaker открыт до {conn.circuit_open_until.isoformat()} — "
                f"sync приостановлен"
            ),
        )

    def _check_consecutive_failures(
        self, session: Session, account_id: int
    ) -> Optional[IssueRecord]:
        conn = (
            session.query(BrokerConnection)
            .filter(
                BrokerConnection.account_id == account_id,
                BrokerConnection.is_active.is_(True),
            )
            .first()
        )
        if conn is None:
            return None
        n = conn.consecutive_failures or 0
        if n < _CONSECUTIVE_FAILURES_THRESHOLD:
            return None
        return IssueRecord(
            check_id="consecutive_failures_high",
            severity=SEVERITY_WARNING,
            count=n,
            description=(
                f"{n} подряд неудачных синхронизаций — проверь токен / лимиты"
            ),
        )

    def _check_canceled_ops_attached_to_trades(
        self, session: Session, account_id: int
    ) -> Optional[IssueRecord]:
        """
        Sanity check: если хоть одна операция с state='canceled' попала
        как entry/exit в Trade.operations — это баг fetch_for_instrument
        фильтра. Не должно случиться при корректной работе.
        """
        # Берём IDs всех canceled операций аккаунта.
        canceled_ids = {
            op_id
            for (op_id,) in session.query(OperationORM.operation_id)
            .filter(
                OperationORM.account_id == account_id,
                OperationORM.state == "canceled",
            )
            .all()
        }
        if not canceled_ids:
            return None

        # Сканируем trade'ы аккаунта на attached canceled operations.
        # Делаем лениво: проходим по trade.operations и ищем пересечение.
        bad: list[int] = []
        rows = (
            session.query(Trade.id, Trade.operations)
            .filter(
                Trade.account_id == account_id,
                Trade.data_source == "tinkoff_v2",
            )
            .all()
        )
        for tid, ops in rows:
            if not ops:
                continue
            for m in ops:
                if m.get("operation_id") in canceled_ids:
                    bad.append(tid)
                    break
        if not bad:
            return None
        return IssueRecord(
            check_id="canceled_ops_in_fifo",
            severity=SEVERITY_ERROR,
            count=len(bad),
            description=(
                "Trade ссылается на canceled-операцию — фильтр fetch_for_instrument "
                "должен был её отсеять"
            ),
            sample_ids=tuple(bad[:_SAMPLE_LIMIT]),
        )
