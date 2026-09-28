"""MATH-03 (Sprint 4, Task 5.1): nightly safety-net backfill MAE/MFE.

Trade.mae_price / Trade.mfe_price заполняются inline в routers/trades.py при
add_trade / close_trade / update_trade и в import-hook (post-commit hook
из import-эндпойнта). На случай если оба пути по какой-то причине пропустят
(сетевой сбой MOEX, race condition на крупном импорте, ручной INSERT) —
этот cron раз в 24h подметает recent трейды (entry_at >= now - 30 дней) с
NULL mae_price и backfill'ит их через `market_data_service.calculate_mae_mfe`.

Запускается ТОЛЬКО на scheduler-воркере (см. sync_scheduler._check_mae_mfe_backfill).

Сигнатура `calculate_mae_mfe` — см. market_service.py: kwargs ticker, direction,
entry_price, entry_time, exit_time, operations, exit_price. Возвращает (mae, mfe)
или (None, None) если данных не хватает (нет свечей, MOEX недоступен).
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy.orm import Session

import models

log = logging.getLogger(__name__)


def _utc_naive_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


async def backfill_missing_mae_mfe(
    session: Session,
    *,
    limit: int = 100,
    max_age_days: int = 30,
    market_service=None,
) -> dict:
    """Найти до `limit` recent трейдов без MAE/MFE и backfill через market_service.

    Args:
        session: DB session.
        limit: maximum trades to process per run.
        max_age_days: рассматривать только трейды с entry_at >= now - max_age_days.
        market_service: для DI в тестах. Если None — импортируем глобальный
            market_data_service (lazy, чтобы не дёргать MOEX при импорте модуля).

    Returns:
        {"processed": int, "succeeded": int, "failed": int}
    """
    if market_service is None:
        # routers/trades.py создаёт собственный singleton `market_data_service`
        # на module-level — у backend нет глобального синглтона в market_service.py.
        # Инстансируем тут (без I/O в __init__).
        from market_service import MarketService
        market_service = MarketService()

    cutoff = _utc_naive_now() - timedelta(days=max_age_days)
    missing = (
        session.query(models.Trade)
        .filter(
            models.Trade.mae_price.is_(None),
            models.Trade.exit_at.isnot(None),
            models.Trade.entry_at >= cutoff,
        )
        .order_by(models.Trade.entry_at.desc())
        .limit(limit)
        .all()
    )
    log.info("mae_mfe nightly backfill: %d candidates", len(missing))

    succeeded = 0
    failed = 0
    for t in missing:
        try:
            direction = t.direction.value if hasattr(t.direction, "value") else str(t.direction)
            mae, mfe = await market_service.calculate_mae_mfe(
                ticker=t.symbol,
                direction=direction,
                entry_price=float(t.entry_price),
                entry_time=t.entry_at,
                exit_time=t.exit_at,
                operations=t.operations if t.operations else None,
                exit_price=float(t.exit_price) if t.exit_price is not None else None,
            )
            if mae is not None and mfe is not None:
                t.mae_price = Decimal(str(mae))
                t.mfe_price = Decimal(str(mfe))
                succeeded += 1
            else:
                # MOEX вернул пустоту — не считаем фейлом, просто данных нет.
                log.debug("mae_mfe backfill: no data for trade %d (%s)", t.id, t.symbol)
        except Exception as exc:
            log.warning("nightly backfill failed for trade %d: %s", t.id, exc)
            failed += 1
    session.commit()
    return {"processed": len(missing), "succeeded": succeeded, "failed": failed}
