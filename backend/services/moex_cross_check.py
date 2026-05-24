"""
PR 26 (Phase 3, D5) — MOEX ISS как третий независимый источник истины.

Сверяет ценовые данные из нашей БД с MOEX ISS API (третий источник в
3-way triangulation): MOEX ISS — это публичный API биржи, не зависит
от Tinkoff. Если наши цены значимо расходятся с MOEX close, значит
есть проблема в трансформации (например point_value для фьючерса).

Сверяется top-N инструментов по weight в портфеле:
- Stock/ETF/Bond: close price на last sync date vs PositionORM.current_price
- Futures: spec (minstep/stepprice) vs InstrumentORM (T1 detection)

Tolerance: 0.5% для price (могут быть corp actions, splits) — мягче чем
Reconciliation для финансовых метрик.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy.orm import Session

import models
from logger import get_logger

log = get_logger("moex_cross_check")

# 0.5% tolerance per план
PRICE_TOLERANCE_PCT = Decimal("0.5")
# Допуск для spec (точное совпадение нужно)
SPEC_TOLERANCE_PCT = Decimal("0")
# Сколько инструментов сверять (top по абс. позиции)
DEFAULT_TOP_N = 5


@dataclass
class MoexCheckResult:
    """Результат одного MOEX cross-check."""

    instrument_uid: str
    ticker: Optional[str]
    check_type: str  # 'price' | 'futures_spec'
    our_value: Optional[Decimal] = None
    moex_value: Optional[Decimal] = None
    diff_abs: Optional[Decimal] = None
    diff_pct: Optional[Decimal] = None
    status: str = "ok"  # 'ok' | 'warn' | 'mismatch' | 'no_moex_data'
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "instrument_uid": self.instrument_uid,
            "ticker": self.ticker,
            "check_type": self.check_type,
            "our": str(self.our_value) if self.our_value is not None else None,
            "moex": str(self.moex_value) if self.moex_value is not None else None,
            "diff_abs": str(self.diff_abs) if self.diff_abs is not None else None,
            "diff_pct": str(self.diff_pct) if self.diff_pct is not None else None,
            "status": self.status,
            "note": self.note,
        }


def cross_check_account(
    db: Session,
    account_id: int,
    *,
    top_n: int = DEFAULT_TOP_N,
) -> list[MoexCheckResult]:
    """Запустить cross-check для топ-N positions аккаунта.

    Возвращает list of результатов (по одной строке на проверку).
    Тяжёлый запрос (HTTP к MOEX ISS), запускается асинхронно из
    nightly cron или по кнопке в admin.
    """
    # 1. Получить топ позиций по abs(quantity × avg_entry_price) — proxy для weight
    positions = (
        db.query(models.PositionORM)
        .filter(
            models.PositionORM.account_id == account_id,
            models.PositionORM.quantity != 0,
        )
        .all()
    )
    if not positions:
        return []

    # Сортируем по «notional» — приблизительный размер позиции
    def _notional(pos) -> Decimal:
        try:
            qty = abs(Decimal(pos.quantity or 0))
            price = Decimal(str(pos.avg_entry_price or 0))
            return qty * price
        except Exception:
            return Decimal(0)

    top_positions = sorted(positions, key=_notional, reverse=True)[:top_n]

    results: list[MoexCheckResult] = []
    from moex_service import MoexService
    moex = MoexService()

    for pos in top_positions:
        instrument = db.query(models.InstrumentORM).filter_by(uid=pos.instrument_uid).first()
        if instrument is None or not instrument.ticker:
            results.append(MoexCheckResult(
                instrument_uid=pos.instrument_uid,
                ticker=None,
                check_type="price",
                status="no_moex_data",
                note="instrument not in cache or no ticker",
            ))
            continue

        # Stock/ETF/Bond — price check; Futures — spec check
        if (instrument.instrument_type or "").lower() == "futures":
            results.append(_check_futures_spec(moex, instrument))
        else:
            results.append(_check_price(moex, instrument, pos))

    log.info(
        "moex_cross_check_complete",
        extra={
            "account_id": account_id,
            "checks": len(results),
            "mismatches": sum(1 for r in results if r.status == "mismatch"),
        },
    )
    return results


def _check_price(moex, instrument, position) -> MoexCheckResult:
    """Сравнить current_price позиции с MOEX close на эту дату."""
    ticker = instrument.ticker
    our_price = (
        Decimal(str(position.current_price))
        if position.current_price is not None
        else None
    )
    if our_price is None:
        return MoexCheckResult(
            instrument_uid=position.instrument_uid,
            ticker=ticker,
            check_type="price",
            status="ok",
            note="no current_price in DB — nothing to compare",
        )

    last_priced = position.last_priced_at
    if last_priced is None:
        last_priced = datetime.utcnow()

    # Запрашиваем daily candle на дату последней цены
    start = last_priced - timedelta(days=2)
    end = last_priced + timedelta(days=1)
    try:
        candles = moex.get_candles(ticker, interval="1d", start=start, end=end)
    except Exception as exc:
        return MoexCheckResult(
            instrument_uid=position.instrument_uid,
            ticker=ticker,
            check_type="price",
            our_value=our_price,
            status="no_moex_data",
            note=f"MOEX query failed: {type(exc).__name__}",
        )

    if not candles:
        return MoexCheckResult(
            instrument_uid=position.instrument_uid,
            ticker=ticker,
            check_type="price",
            our_value=our_price,
            status="no_moex_data",
            note="MOEX returned no candles (weekend/delisted)",
        )

    # Берём last candle close
    last_candle = candles[-1]
    try:
        moex_close = Decimal(str(last_candle["c"]))
    except Exception:
        return MoexCheckResult(
            instrument_uid=position.instrument_uid,
            ticker=ticker,
            check_type="price",
            our_value=our_price,
            status="no_moex_data",
            note="MOEX close field unparseable",
        )

    if moex_close <= 0:
        return MoexCheckResult(
            instrument_uid=position.instrument_uid,
            ticker=ticker,
            check_type="price",
            our_value=our_price,
            moex_value=moex_close,
            status="no_moex_data",
            note="MOEX close is zero or negative",
        )

    diff_abs = abs(our_price - moex_close)
    diff_pct = (diff_abs / moex_close) * Decimal(100)
    status = "ok" if diff_pct <= PRICE_TOLERANCE_PCT else "mismatch"
    note = ""
    if status == "mismatch":
        note = (
            "Расхождение цены > 0.5%. Возможны: corporate action (split/dividend), "
            "stale our price, или ошибка трансформации (особенно для фьючерсов — "
            "проверьте point_value)."
        )
    return MoexCheckResult(
        instrument_uid=position.instrument_uid,
        ticker=ticker,
        check_type="price",
        our_value=our_price,
        moex_value=moex_close,
        diff_abs=diff_abs,
        diff_pct=diff_pct,
        status=status,
        note=note,
    )


def _check_futures_spec(moex, instrument) -> MoexCheckResult:
    """Сравнить наш point_value (= stepprice/minstep) с MOEX spec."""
    ticker = instrument.ticker
    try:
        spec = moex.get_futures_spec(ticker)
    except Exception as exc:
        return MoexCheckResult(
            instrument_uid=instrument.uid,
            ticker=ticker,
            check_type="futures_spec",
            status="no_moex_data",
            note=f"MOEX spec query failed: {type(exc).__name__}",
        )
    if spec is None:
        return MoexCheckResult(
            instrument_uid=instrument.uid,
            ticker=ticker,
            check_type="futures_spec",
            status="no_moex_data",
            note="MOEX has no spec for this ticker (delisted?)",
        )

    moex_point_value = spec.get("point_value")
    if moex_point_value is None:
        return MoexCheckResult(
            instrument_uid=instrument.uid,
            ticker=ticker,
            check_type="futures_spec",
            status="no_moex_data",
            note="MOEX spec has no point_value",
        )

    # Наш point_value = min_price_increment_amount / min_price_increment
    step = instrument.min_price_increment
    step_amount = instrument.min_price_increment_amount
    if step is None or step_amount is None or step == 0:
        return MoexCheckResult(
            instrument_uid=instrument.uid,
            ticker=ticker,
            check_type="futures_spec",
            moex_value=Decimal(str(moex_point_value)),
            status="mismatch",
            note="T1: наш справочник без min_price_increment_amount → fallback 1.0 (баг масштаба)",
        )

    try:
        our_point_value = Decimal(str(step_amount)) / Decimal(str(step))
    except Exception:
        return MoexCheckResult(
            instrument_uid=instrument.uid,
            ticker=ticker,
            check_type="futures_spec",
            status="no_moex_data",
            note="Failed to compute point_value from instrument",
        )

    moex_dec = Decimal(str(moex_point_value))
    if moex_dec <= 0:
        return MoexCheckResult(
            instrument_uid=instrument.uid,
            ticker=ticker,
            check_type="futures_spec",
            our_value=our_point_value,
            moex_value=moex_dec,
            status="no_moex_data",
            note="MOEX point_value is zero",
        )
    diff_abs = abs(our_point_value - moex_dec)
    diff_pct = (diff_abs / moex_dec) * Decimal(100)
    # spec должен совпадать exact (это математическая формула, не цена)
    status = "ok" if diff_pct <= Decimal("0.01") else "mismatch"
    note = "" if status == "ok" else (
        f"Расхождение point_value > 0.01%: наш {our_point_value} vs MOEX {moex_dec}. "
        f"P&L для этого фьючерса считается неправильно."
    )
    return MoexCheckResult(
        instrument_uid=instrument.uid,
        ticker=ticker,
        check_type="futures_spec",
        our_value=our_point_value,
        moex_value=moex_dec,
        diff_abs=diff_abs,
        diff_pct=diff_pct,
        status=status,
        note=note,
    )
